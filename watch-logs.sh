#!/bin/bash

# Real-time log viewer for Pump.fun Fee Collector
# Shows timer status and live execution logs

clear
echo "=========================================="
echo "  Pump.fun Fee Collector - Live Monitor"
echo "=========================================="
echo ""

# Show timer status
echo "📅 Timer Status:"
systemctl status pump-fee-collector.timer --no-pager | grep -E "(Active|Trigger)"
echo ""

# Show next scheduled runs
echo "⏰ Next Scheduled Runs:"
systemctl list-timers pump-fee-collector.timer --no-pager
echo ""

echo "=========================================="
echo "  📋 Live Execution Logs (Ctrl+C to exit)"
echo "=========================================="
echo ""

# Follow logs in real-time with timestamps
journalctl -u pump-fee-collector.service -f --since "5 minutes ago" -o short-iso
