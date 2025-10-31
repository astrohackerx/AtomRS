import os
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import asyncio
import base58
from typing import List, Tuple
import struct

load_dotenv()

# Configuration
ATOMID_PROGRAM_ID = Pubkey.from_string("rnc2fycemiEgj4YbMSuwKFpdV6nkJonojCXib3j2by6")
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# Rank titles
RANK_TITLES = {
    0: "Initiate",
    1: "Believer",
    2: "Devotee",
    3: "Guardian",
    4: "Keeper",
    5: "Oracle",
    6: "Architect",
    7: "Sage",
    8: "Ascended",
    9: "Eternal"
}

async def get_atomid_holders(client: AsyncClient) -> List[Tuple[Pubkey, int, int]]:
    """Get all AtomID holders with their burned amounts and ranks"""
    print(f"\n🔍 Fetching AtomID holders from program {ATOMID_PROGRAM_ID}...")
    print()

    try:
        from solana.rpc.commitment import Confirmed

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
        print()
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

        return holders

    except Exception as e:
        print(f"❌ Error fetching AtomID holders: {e}")
        import traceback
        traceback.print_exc()
        return []

async def main():
    print("=" * 80)
    print("AtomID Holders Viewer")
    print("=" * 80)
    print()

    client = AsyncClient(RPC_URL)

    try:
        holders = await get_atomid_holders(client)

        if not holders:
            print("❌ No AtomID holders found")
            return

        # Sort by burned amount (descending)
        holders_sorted = sorted(holders, key=lambda x: x[1], reverse=True)

        # Calculate totals
        total_burned = sum(burned for _, burned, _ in holders)
        total_holders = len(holders)

        print("=" * 80)
        print(f"📊 SUMMARY")
        print("=" * 80)
        print(f"Total AtomID Holders: {total_holders}")
        print(f"Total ATOM Burned: {total_burned / 1e6:,.2f}")
        print(f"Average Burned per Holder: {(total_burned / total_holders) / 1e6:,.2f}")
        print()

        print("=" * 80)
        print(f"{'#':<5} {'WALLET':<45} {'RANK':<12} {'BURNED':<20} {'%':<8}")
        print("=" * 80)

        for idx, (owner, burned, rank) in enumerate(holders_sorted, 1):
            rank_title = RANK_TITLES.get(rank, f"Rank {rank}")
            burned_amount = burned / 1e6
            percentage = (burned / total_burned) * 100

            print(f"{idx:<5} {str(owner):<45} {rank_title:<12} {burned_amount:>15,.2f} ATOM {percentage:>6.2f}%")

        print("=" * 80)
        print()

        # Rank distribution
        rank_distribution = {}
        for _, _, rank in holders:
            rank_title = RANK_TITLES.get(rank, f"Rank {rank}")
            rank_distribution[rank_title] = rank_distribution.get(rank_title, 0) + 1

        print("=" * 80)
        print("📈 RANK DISTRIBUTION")
        print("=" * 80)
        for rank_title in sorted(rank_distribution.keys(), key=lambda x: list(RANK_TITLES.values()).index(x) if x in RANK_TITLES.values() else 999):
            count = rank_distribution[rank_title]
            pct = (count / total_holders) * 100
            bar = "█" * int(pct / 2)
            print(f"{rank_title:<12} {count:>4} holders ({pct:>5.1f}%) {bar}")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
