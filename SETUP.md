# AtomID Reward Distributor - Setup Guide

Complete step-by-step guide to install and run the AtomID reward auto-distributor every hour on Linux.

**Important:** This script distributes rewards to AtomID holders based on their burned ATOM amounts, NOT to token holders.

---

## 1. Install Python 3 and Required Tools

```bash
# Update package list
sudo apt update

# Install Python 3 and pip
sudo apt install python3 python3-pip python3-venv -y

# Verify installation
python3 --version
pip3 --version
```

---

## 2. Setup Project Directory and Virtual Environment

```bash
# Navigate to your project directory (example: /home/user/pump-fee-collector)
cd /home/user/pump-fee-collector

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

**Important Notes:**
- Modern Python distributions require using a virtual environment to avoid conflicts
- The virtual environment isolates your project dependencies
- You must activate the venv before running the script manually
- The systemd service will automatically use the venv (configured in the service file)
- The project uses Supabase to track statistics. Supabase credentials are already configured in the `.env` file.

**Troubleshooting:** If you get dependency errors, you may need to upgrade pip first:
```bash
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Configure Environment Variables

Edit the `.env` file with your wallet private key and RPC URL:

```bash
nano .env
```

Add/update these required values:
```
WALLET_PRIVATE_KEY=your_base58_private_key_here
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

**Supabase credentials are already configured** (SUPABASE_URL and SUPABASE_KEY). Do not change these unless you have your own Supabase instance.

Save and exit (Ctrl+X, then Y, then Enter)

---

## 4. Test Manual Run

Before setting up automation, test that it works:

```bash
# Make sure venv is activated
source venv/bin/activate

# Run the script
python3 automain.py
```

If successful, proceed to automation setup.

**Note:** Always activate the venv before running the script manually. The systemd service handles this automatically.

---

## 5. Setup Systemd Timer (Run Every Hour)

### Step 5.1: Update Service File with Your Project Path

Edit the service file:

```bash
nano pump-fee-collector.service
```

Replace `YOUR_PROJECT_PATH_HERE` with your actual project path. For example, if your project is in `/home/user/atomid-rewards`:

```ini
WorkingDirectory=/home/user/atomid-rewards
ExecStart=/home/user/atomid-rewards/venv/bin/python3 /home/user/atomid-rewards/automain.py
```

**Important:** Note that `ExecStart` uses the Python binary from the virtual environment (`venv/bin/python3`), not the system Python. This ensures all dependencies are available.

Save and exit (Ctrl+X, then Y, then Enter)

### Step 5.2: Copy Files to Systemd Directory

```bash
sudo cp pump-fee-collector.service /etc/systemd/system/
sudo cp pump-fee-collector.timer /etc/systemd/system/
```

### Step 5.3: Enable and Start the Timer

```bash
# Reload systemd to recognize new files
sudo systemctl daemon-reload

# Enable timer to start on boot
sudo systemctl enable pump-fee-collector.timer

# Start the timer now
sudo systemctl start pump-fee-collector.timer
```

### Step 5.4: Verify It's Running

```bash
# Check timer status
sudo systemctl status pump-fee-collector.timer

# List all timers to see next run time
sudo systemctl list-timers pump-fee-collector.timer
```

You should see the timer is active and the next trigger time.

---

## 6. View Logs in Real-Time (Perfect for Screen Sharing!)

### Easy Way - Use the Watch Script

```bash
# Make the script executable (first time only)
chmod +x watch-logs.sh

# Shows timer status + live logs in one view
./watch-logs.sh
```

This displays:
- Timer status and next run time
- Live execution logs with timestamps
- Perfect for sharing screen with users

Press `Ctrl+C` to exit.

### Manual Commands

```bash
# View live logs (follow mode)
sudo journalctl -u pump-fee-collector.service -f

# View last 50 lines
sudo journalctl -u pump-fee-collector.service -n 50

# View logs from today
sudo journalctl -u pump-fee-collector.service --since today

# Show timer + logs together
systemctl list-timers pump-fee-collector.timer && sudo journalctl -u pump-fee-collector.service -f
```

---

## 7. Testing with Devnet Before Mainnet

**IMPORTANT:** Always test with devnet/testnet first before using real mainnet funds!

### Testing Workflow:

#### Phase 1: Test with Devnet

```bash
# 1. Edit .env with devnet configuration
nano .env
```

Use devnet values:
```
WALLET_PRIVATE_KEY=your_test_wallet_private_key
SOLANA_RPC_URL=https://api.devnet.solana.com
```

```bash
# 2. Test manually first
source venv/bin/activate
python3 automain.py

# 3. If successful, setup systemd timer (follow steps 5.1-5.4 above)

# 4. Monitor test runs
./watch-logs.sh
```

#### Phase 2: Switch to Mainnet

Once testing is complete and everything works correctly:

```bash
# 1. Stop the timer
sudo systemctl stop pump-fee-collector.timer

# 2. Clear test data from database (IMPORTANT!)
# Go to Supabase Dashboard → SQL Editor and run:
```

**Clear devnet test data:**
```sql
-- Delete all test logs
DELETE FROM collector_logs;

-- Reset stats to zero
UPDATE fee_collector_stats
SET total_sol_paid = 0,
    successful_executions = 0,
    last_payout_amount = 0,
    last_payout_at = NULL,
    updated_at = now()
WHERE id = '00000000-0000-0000-0000-000000000001';
```

```bash
# 3. Update .env with mainnet credentials
nano .env
```

Update to mainnet values:
```
WALLET_PRIVATE_KEY=your_mainnet_wallet_private_key
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

```bash
# 4. Test manually with mainnet config
source venv/bin/activate
python3 automain.py

# 5. If successful, start the timer again
sudo systemctl start pump-fee-collector.timer

# 6. Verify it's running
sudo systemctl status pump-fee-collector.timer

# 7. Monitor mainnet runs
./watch-logs.sh
```

**That's it!** No need to reload systemd when only changing `.env` - the timer automatically picks up the new configuration on the next run.

---

## 8. How to Update After Changes

### When you change `.env` or `automain.py`:

The timer will automatically use the new version on the next run. **No systemctl restart needed!**

Changes apply within 1 hour (next scheduled run).

### When you change `MIN_CLAIM` in `automain.py`:

```bash
# Just edit the file
nano automain.py

# Change this line at the top:
MIN_CLAIM = 0.1  # Change to your desired value

# Save and exit - changes will apply on next run (within 10 minutes)
```

**No restart needed** - systemd automatically uses the updated file.

### When you change the service or timer files:

```bash
# 1. Copy updated files
sudo cp pump-fee-collector.service /etc/systemd/system/
sudo cp pump-fee-collector.timer /etc/systemd/system/

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Restart the timer
sudo systemctl restart pump-fee-collector.timer
```

---

## 9. Useful Management Commands

```bash
# Stop the timer (stops automatic runs)
sudo systemctl stop pump-fee-collector.timer

# Start the timer again
sudo systemctl start pump-fee-collector.timer

# Disable timer (won't start on boot)
sudo systemctl disable pump-fee-collector.timer

# Run manually right now (doesn't affect timer schedule)
sudo systemctl start pump-fee-collector.service

# Check when it will run next
sudo systemctl list-timers pump-fee-collector.timer
```

---

## 10. Troubleshooting

### Timer shows as "dead" or "inactive"
```bash
sudo systemctl status pump-fee-collector.timer
sudo journalctl -u pump-fee-collector.timer
```

### Service fails to run
```bash
# Check service logs for errors
sudo journalctl -u pump-fee-collector.service -n 100

# Common issues:
# - Wrong path in service file
# - Missing Python dependencies
# - Invalid .env configuration
```

### Test service manually
```bash
# This runs the service once and shows any errors
sudo systemctl start pump-fee-collector.service
sudo systemctl status pump-fee-collector.service
```

---

## Summary

✅ Runs every hour automatically
✅ Distributes rewards to AtomID holders based on burned amounts
✅ Starts automatically on server reboot
✅ Logs to systemd journal
✅ Easy to monitor and manage
✅ Updates to code apply automatically (no restart needed)
✅ **Tracks statistics in Supabase**:
   - Total SOL paid out (cumulative)
   - Number of successful executions
   - Last payout amount and timestamp

The collector will claim fees and distribute to AtomID holders whenever the balance exceeds `MIN_CLAIM` SOL (default: 0.01 SOL).

### How Rewards Are Distributed

- 80% of collected fees go to AtomID holders
- 20% stays in creator wallet
- Distribution is proportional to total ATOM burned (not token balance)
- Higher rank = more burned = larger reward share
- Minimum payout: 0.000005 SOL per holder

### View Statistics

You can query the statistics from the Supabase dashboard or via SQL:

```sql
SELECT
  total_sol_paid,
  successful_executions,
  last_payout_amount,
  last_payout_at
FROM fee_collector_stats;
```
