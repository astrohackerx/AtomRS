import os
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from dotenv import load_dotenv
import asyncio
import base58
from typing import List, Tuple
from supabase import create_client, Client
from logger import CollectorLogger

load_dotenv()

logger = CollectorLogger()

# Configuration
MIN_CLAIM = 0.01  # Minimum SOL to trigger auto-claim

PUMP_PROGRAM_ID = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PUMP_AMM_PROGRAM_ID = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
RAYDIUM_AMM_PROGRAM = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
ATOMID_PROGRAM_ID = Pubkey.from_string("rnc2fycemiEgj4YbMSuwKFpdV6nkJonojCXib3j2by6")
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

def load_wallet():
    private_key = os.getenv("WALLET_PRIVATE_KEY")
    if not private_key:
        raise ValueError("WALLET_PRIVATE_KEY not found in .env file")

    try:
        key_bytes = base58.b58decode(private_key)
        return Keypair.from_bytes(key_bytes)
    except Exception as e:
        raise ValueError(f"Invalid private key format: {e}")

def get_supabase_client() -> Client:
    """Initialize Supabase client"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

    return create_client(url, key)

def update_stats(claimed_amount: float):
    """Update statistics in Supabase after successful payout"""
    try:
        supabase = get_supabase_client()

        # Get current stats
        result = supabase.from_('fee_collector_stats').select('*').eq('id', '00000000-0000-0000-0000-000000000001').maybe_single().execute()

        if result.data:
            # Update existing record
            new_total = float(result.data['total_sol_paid']) + claimed_amount
            new_count = result.data['successful_executions'] + 1

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            supabase.from_('fee_collector_stats').update({
                'total_sol_paid': new_total,
                'successful_executions': new_count,
                'last_payout_amount': claimed_amount,
                'last_payout_at': now,
                'updated_at': now
            }).eq('id', '00000000-0000-0000-0000-000000000001').execute()
        else:
            # Insert first record
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            supabase.from_('fee_collector_stats').insert({
                'id': '00000000-0000-0000-0000-000000000001',
                'total_sol_paid': claimed_amount,
                'successful_executions': 1,
                'last_payout_amount': claimed_amount,
                'last_payout_at': now
            }).execute()

        print(f"📊 Statistics updated: +{claimed_amount:.9f} SOL")
    except Exception as e:
        print(f"⚠️  Warning: Failed to update statistics: {e}")

def update_execution_timestamp():
    """Update last execution timestamp without changing stats (for timer continuity)"""
    try:
        supabase = get_supabase_client()

        # Get current stats
        result = supabase.from_('fee_collector_stats').select('*').eq('id', '00000000-0000-0000-0000-000000000001').maybe_single().execute()

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        if result.data:
            # Update only the timestamp
            supabase.from_('fee_collector_stats').update({
                'last_payout_at': now,
                'updated_at': now
            }).eq('id', '00000000-0000-0000-0000-000000000001').execute()
            print(f"📊 Execution timestamp updated")
        else:
            # Insert initial record with zero stats
            supabase.from_('fee_collector_stats').insert({
                'id': '00000000-0000-0000-0000-000000000001',
                'total_sol_paid': 0,
                'successful_executions': 0,
                'last_payout_amount': 0,
                'last_payout_at': now
            }).execute()
            print(f"📊 Initial stats record created")
    except Exception as e:
        print(f"⚠️  Warning: Failed to update execution timestamp: {e}")

async def get_account_balance(client: AsyncClient, account: Pubkey) -> tuple[float, dict]:
    """Get native SOL balance from account (for pump vault)"""
    try:
        response = await client.get_account_info(account)
        if response.value is None:
            return 0.0, {"exists": False}

        lamports = response.value.lamports
        data_len = len(response.value.data) if response.value.data else 0

        rent_response = await client.get_minimum_balance_for_rent_exemption(data_len)
        rent_exempt_minimum = rent_response.value

        claimable_lamports = max(0, lamports - rent_exempt_minimum)
        sol_amount = claimable_lamports / 1_000_000_000

        debug_info = {
            "exists": True,
            "total_lamports": lamports,
            "total_sol": lamports / 1_000_000_000,
            "data_len": data_len,
            "rent_exempt_minimum": rent_exempt_minimum,
            "rent_exempt_sol": rent_exempt_minimum / 1_000_000_000,
            "claimable_lamports": claimable_lamports,
            "claimable_sol": sol_amount
        }

        return sol_amount, debug_info
    except Exception as e:
        return 0.0, {"error": str(e)}

async def get_token_account_balance(client: AsyncClient, token_account: Pubkey) -> tuple[float, dict]:
    """Get token balance from a token account (for AMM vaults which are ATAs holding WSOL)"""
    try:
        response = await client.get_token_account_balance(token_account)
        if response.value is None:
            return 0.0, {"exists": False}

        # Get token amount from the response
        amount = int(response.value.amount)
        decimals = response.value.decimals
        ui_amount = response.value.ui_amount

        sol_amount = amount / (10 ** decimals)

        debug_info = {
            "exists": True,
            "amount": amount,
            "decimals": decimals,
            "ui_amount": ui_amount,
            "sol_amount": sol_amount
        }

        return sol_amount, debug_info
    except Exception as e:
        return 0.0, {"error": str(e)}

async def collect_creator_fees(creator_keypair: Keypair):
    client = AsyncClient(RPC_URL)

    try:
        creator_pubkey = creator_keypair.pubkey()
        wsol_mint = Pubkey.from_string("So11111111111111111111111111111111111111112")

        print(f"Creator Wallet: {creator_pubkey}")
        print()

        # Check AMM vault (DEX trading fees)
        print("─" * 60)
        print("AMM VAULT (DEX trading fees):")
        print("─" * 60)

        total_amm_balance = 0.0
        amm_vaults_with_balance = []

        # Derive the vault authority using YOUR wallet (coin_creator)
        vault_authority = Pubkey.find_program_address(
            [b"creator_vault", bytes(creator_pubkey)],
            PUMP_AMM_PROGRAM_ID
        )[0]

        token_program = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

        # The AMM vault is a single ATA for all your tokens
        coin_vault = Pubkey.find_program_address(
            [bytes(vault_authority), bytes(token_program), bytes(wsol_mint)],
            Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
        )[0]

        print(f"Vault Authority: {vault_authority}")
        print(f"AMM Vault (ATA): {coin_vault}")
        print()

        balance, debug = await get_token_account_balance(client, coin_vault)

        if debug.get("exists"):
            print(f"Status: ✅ Vault exists")
            print(f"Token Balance: {debug.get('ui_amount', 0):.9f} WSOL")
            print(f"Claimable: {balance:.9f} SOL")
            print(f"Debug: amount={debug.get('amount', 0)}, decimals={debug.get('decimals', 9)}")
            print()

            if balance > 0:
                total_amm_balance = balance
                amm_vaults_with_balance.append((coin_vault, balance))
        else:
            print(f"Status: ❌ Vault not created yet (no AMM fees)")
            if "error" in debug:
                print(f"Error: {debug['error']}")

        print("─" * 60)
        print()

        total_balance = total_amm_balance
        print(f"💰 TOTAL CLAIMABLE: {total_balance:.9f} SOL")
        print(f"   └─ AMM Fees: {total_amm_balance:.9f} SOL")
        print()

        if total_balance == 0:
            print("No fees to claim.")
            update_execution_timestamp()
            return 0.0

        if total_balance < MIN_CLAIM:
            print(f"⏭️  Skipping claim (below {MIN_CLAIM} SOL threshold)")
            logger.info(f"Claimable amount {total_balance:.9f} SOL below threshold {MIN_CLAIM} SOL")
            update_execution_timestamp()
            return 0.0

        print(f"✅ Claimable amount >= {MIN_CLAIM} SOL, proceeding automatically...")
        logger.info(f"Found claimable amount: {total_balance:.9f} SOL", sol_amount=total_balance)
        print()

        from solders.transaction import Transaction as SoldersTransaction
        from solders.instruction import Instruction, AccountMeta

        claimed_total = 0

        if total_amm_balance > 0:
            print(f"\nClaiming {total_amm_balance:.9f} SOL from AMM vault...")

            amm_event_authority = Pubkey.find_program_address([b"__event_authority"], PUMP_AMM_PROGRAM_ID)[0]
            token_program = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
            ata_program = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
            system_program = Pubkey.from_string("11111111111111111111111111111111")

            creator_wsol_ata_pda = Pubkey.find_program_address(
                [bytes(creator_pubkey), bytes(token_program), bytes(wsol_mint)],
                ata_program
            )[0]

            coin_vault, balance = amm_vaults_with_balance[0]

            coin_creator_vault_authority = Pubkey.find_program_address(
                [b"creator_vault", bytes(creator_pubkey)],
                PUMP_AMM_PROGRAM_ID
            )[0]

            try:
                instructions = []

                # Check if WSOL ATA exists, if not create it
                ata_info = await client.get_account_info(creator_wsol_ata_pda)
                if ata_info.value is None:
                    print("Creating WSOL token account...")
                    # Create Associated Token Account instruction
                    create_ata_ix = Instruction(
                        ata_program,
                        bytes([]),  # Empty data for create instruction
                        [
                            AccountMeta(creator_pubkey, is_signer=True, is_writable=True),
                            AccountMeta(creator_wsol_ata_pda, is_signer=False, is_writable=True),
                            AccountMeta(creator_pubkey, is_signer=False, is_writable=False),
                            AccountMeta(wsol_mint, is_signer=False, is_writable=False),
                            AccountMeta(system_program, is_signer=False, is_writable=False),
                            AccountMeta(token_program, is_signer=False, is_writable=False),
                        ]
                    )
                    instructions.append(create_ata_ix)

                # collect_coin_creator_fee discriminator: [160,57,89,42,181,139,43,66]
                instruction_data = bytes([160, 57, 89, 42, 181, 139, 43, 66])

                accounts = [
                    AccountMeta(wsol_mint, is_signer=False, is_writable=False),
                    AccountMeta(token_program, is_signer=False, is_writable=False),
                    AccountMeta(creator_pubkey, is_signer=False, is_writable=False),
                    AccountMeta(coin_creator_vault_authority, is_signer=False, is_writable=False),
                    AccountMeta(coin_vault, is_signer=False, is_writable=True),
                    AccountMeta(creator_wsol_ata_pda, is_signer=False, is_writable=True),
                    AccountMeta(amm_event_authority, is_signer=False, is_writable=False),
                    AccountMeta(PUMP_AMM_PROGRAM_ID, is_signer=False, is_writable=False),
                ]

                claim_ix = Instruction(PUMP_AMM_PROGRAM_ID, instruction_data, accounts)
                instructions.append(claim_ix)

                # Add close WSOL account instruction to unwrap WSOL back to SOL
                close_account_ix = Instruction(
                    token_program,
                    bytes([9]),  # CloseAccount instruction discriminator
                    [
                        AccountMeta(creator_wsol_ata_pda, is_signer=False, is_writable=True),
                        AccountMeta(creator_pubkey, is_signer=False, is_writable=True),
                        AccountMeta(creator_pubkey, is_signer=True, is_writable=False),
                    ]
                )
                instructions.append(close_account_ix)

                recent_blockhash = await client.get_latest_blockhash()
                tx = SoldersTransaction.new_signed_with_payer(
                    instructions,
                    creator_pubkey,
                    [creator_keypair],
                    recent_blockhash.value.blockhash
                )

                result = await client.send_raw_transaction(bytes(tx), opts=TxOpts(skip_preflight=False))
                print(f"✅ AMM claim successful! WSOL automatically converted to SOL")
                print(f"   Signature: {result.value}")
                logger.success(f"Claimed {balance:.9f} SOL from AMM vault",
                             sol_amount=balance, tx_signature=str(result.value))
                claimed_total += balance
            except Exception as e:
                print(f"❌ AMM claim failed: {e}")
                logger.error(f"AMM claim failed: {str(e)}")

        if claimed_total > 0:
            print()
            print(f"✅ Total claimed: {claimed_total:.9f} SOL")
            logger.success(f"Total claimed: {claimed_total:.9f} SOL", sol_amount=claimed_total)

            # Update statistics in Supabase
            update_stats(claimed_total)

            return claimed_total

        return 0.0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 0.0

    finally:
        await client.close()

async def get_atomid_holders(client: AsyncClient) -> List[Tuple[Pubkey, int, int]]:
    """Get all AtomID holders with their burned amounts and ranks"""
    print(f"\n🔍 Fetching AtomID holders from program {ATOMID_PROGRAM_ID}...")

    try:
        from solana.rpc.types import MemcmpOpts
        from solana.rpc.commitment import Confirmed
        import struct

        # Fetch all AtomID accounts from the program
        response = await client.get_program_accounts(
            ATOMID_PROGRAM_ID,
            commitment=Confirmed,
            encoding="base64",
            filters=[
                # Account discriminator for AtomID accounts (8 bytes)
                # Data size filter: 8 (discriminator) + 32 (owner) + 8 (total_burned) + 1 (rank) + 204 (metadata) + 8 (created_at) + 8 (updated_at) + 1 (bump)
                270
            ]
        )

        if not response or not hasattr(response, 'value'):
            print(f"❌ Invalid response from RPC")
            return []

        print(f"📊 Processing {len(response.value)} AtomID accounts...")
        holders = []

        for account in response.value:
            try:
                # Decode base64 data
                data = base58.b58decode(account.account.data[0]) if isinstance(account.account.data, list) else account.account.data

                # AtomID account layout:
                # - 8 bytes: discriminator
                # - 32 bytes: owner (Pubkey)
                # - 8 bytes: total_burned (u64)
                # - 1 byte: rank (u8)
                # - 204 bytes: metadata (String with length prefix)
                # - 8 bytes: created_at_slot (u64)
                # - 8 bytes: updated_at_slot (u64)
                # - 1 byte: bump

                if len(data) >= 49:  # At least discriminator + owner + total_burned + rank
                    owner_bytes = data[8:40]  # Skip 8-byte discriminator
                    total_burned_bytes = data[40:48]
                    rank = data[48]

                    owner = Pubkey(owner_bytes)
                    total_burned = struct.unpack('<Q', total_burned_bytes)[0]

                    holders.append((owner, total_burned, rank))
            except Exception as e:
                print(f"⚠️  Error parsing account: {e}")
                continue

        print(f"✅ Found {len(holders)} AtomID holders")
        return holders

    except Exception as e:
        print(f"❌ Error fetching AtomID holders: {e}")
        import traceback
        traceback.print_exc()
        return []

async def distribute_rewards(wallet: Keypair, claimed_amount: float):
    """Distribute 80% of claimed rewards to AtomID holders based on burned amounts"""
    print("\n" + "=" * 60)
    print("Reward Distribution to AtomID Holders")
    print("=" * 60)

    client = AsyncClient(RPC_URL)

    try:
        holders = await get_atomid_holders(client)

        if not holders:
            print("❌ No AtomID holders found")
            return

        # Calculate distribution
        distributable = claimed_amount * 0.8
        total_burned = sum(burned for _, burned, _ in holders)

        print(f"\n💰 Distribution Details:")
        print(f"   Total Claimed: {claimed_amount:.9f} SOL")
        print(f"   Distributable (80%): {distributable:.9f} SOL")
        print(f"   Total ATOM Burned: {total_burned / 1e6:.0f}")
        print(f"   AtomID Holders: {len(holders)}")

        # Calculate rewards per holder (minimum 0.000005 SOL)
        MIN_AMOUNT_LAMPORTS = 5000
        MIN_AMOUNT_SOL = MIN_AMOUNT_LAMPORTS / 1e9

        rewards = []
        skipped_below_min = 0

        for owner, burned, rank in holders:
            share = (burned / total_burned) * distributable
            lamports = int(share * 1e9)

            if lamports < MIN_AMOUNT_LAMPORTS:
                skipped_below_min += 1
                continue

            rewards.append((owner, share))
            print(f"   • {owner}: Rank {rank}, {burned / 1e6:.0f} ATOM burned → {share:.9f} SOL")

        if skipped_below_min > 0:
            print(f"\n⚠️  {skipped_below_min} holders skipped (reward below {MIN_AMOUNT_SOL:.9f} SOL minimum)")

        if not rewards:
            print(f"\n❌ No holders qualify for rewards (all below minimum threshold)")
            return

        # Auto-confirm distribution
        print(f"\n✅ Sending {sum(r[1] for r in rewards):.9f} SOL to {len(rewards)} AtomID holders...")

        # Send rewards in batches
        from solders.system_program import transfer, TransferParams
        from solders.transaction import Transaction as SoldersTransaction

        print(f"\n📤 Sending rewards...")
        success_count = 0
        failed_count = 0

        for owner, amount in rewards:
            try:
                lamports = int(amount * 1e9)

                transfer_ix = transfer(TransferParams(
                    from_pubkey=wallet.pubkey(),
                    to_pubkey=owner,
                    lamports=lamports
                ))

                recent_blockhash = await client.get_latest_blockhash()
                tx = SoldersTransaction.new_signed_with_payer(
                    [transfer_ix],
                    wallet.pubkey(),
                    [wallet],
                    recent_blockhash.value.blockhash
                )

                result = await client.send_raw_transaction(bytes(tx), opts=TxOpts(skip_preflight=False))
                print(f"   ✅ Sent {amount:.9f} SOL to {owner}")
                logger.success(f"Distributed {amount:.9f} SOL to holder",
                             sol_amount=amount, tx_signature=str(result.value),
                             metadata={'recipient': str(owner)})
                success_count += 1

                await asyncio.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"   ❌ Failed to send to {owner}: {e}")
                failed_count += 1

        print(f"\n✅ Distribution complete!")
        print(f"   • Successful: {success_count}/{len(rewards)}")
        logger.info(f"Distribution completed: {success_count} successful, {failed_count} failed",
                   metadata={'total_distributed': sum(r[1] for r in rewards[:success_count]),
                            'recipients': success_count})
        if failed_count > 0:
            print(f"   • Failed: {failed_count}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await client.close()

async def main():
    logger.info("Fee collector started")
    print("=" * 60)
    print("AtomID Reward Distributor - Pump.fun Fee Collector")
    print("=" * 60)
    print()

    try:
        wallet = load_wallet()
        claimed_amount = await collect_creator_fees(wallet)

        if claimed_amount > 0:
            await distribute_rewards(wallet, claimed_amount)
        else:
            logger.info("No fees to claim, skipping execution")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"❌ {e}")
        print()
        print("Please check your .env file:")
        print("WALLET_PRIVATE_KEY=your_base58_encoded_private_key")
        print("SOLANA_RPC_URL=your_rpc_url (optional)")
        print("MAIN_TOKEN=token_mint_address")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise

    print()
    print("=" * 60)
    logger.info("Fee collector completed")

if __name__ == "__main__":
    asyncio.run(main())
