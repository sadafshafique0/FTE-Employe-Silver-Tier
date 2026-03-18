#!/bin/bash
# AI Employee Silver Tier — Start All Watchers
# Run this from the project root directory

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo " AI Employee Silver Tier — Starting..."
echo "========================================"
echo ""

# Check if vault exists
if [ ! -d "vault" ]; then
    echo "ERROR: vault/ directory not found. Are you in the right directory?"
    exit 1
fi

PIDS=()

# 1. File System Watcher
echo "[1/5] Starting File System Watcher..."
python3 watchers/filesystem_watcher.py --vault ./vault &
PIDS+=($!)
sleep 1

# 2. Gmail Watcher
if [ -f "watchers/credentials.json" ]; then
    echo "[2/5] Starting Gmail Watcher..."
    python3 watchers/gmail_watcher.py --vault ./vault --credentials watchers/credentials.json &
    PIDS+=($!)
else
    echo "[2/5] SKIPPED Gmail Watcher (watchers/credentials.json not found)"
fi
sleep 1

# 3. WhatsApp Watcher
if [ -d "watchers/whatsapp_session" ]; then
    echo "[3/5] Starting WhatsApp Watcher..."
    python3 watchers/whatsapp_watcher.py --vault ./vault &
    PIDS+=($!)
else
    echo "[3/5] SKIPPED WhatsApp Watcher (run --setup first)"
    echo "       python3 watchers/whatsapp_watcher.py --vault ./vault --setup"
fi
sleep 1

# 4. LinkedIn Watcher
if [ -d "watchers/linkedin_session" ]; then
    echo "[4/5] Starting LinkedIn Watcher..."
    python3 watchers/linkedin_watcher.py --vault ./vault &
    PIDS+=($!)
else
    echo "[4/5] SKIPPED LinkedIn Watcher (run --setup first)"
    echo "       python3 watchers/linkedin_watcher.py --vault ./vault --setup"
fi
sleep 1

# 5. Orchestrator
if [ -f "watchers/credentials.json" ]; then
    echo "[5/5] Starting Orchestrator..."
    python3 watchers/orchestrator.py --vault ./vault --credentials watchers/credentials.json &
else
    echo "[5/5] Starting Orchestrator (no-Gmail mode)..."
    python3 watchers/orchestrator.py --vault ./vault --no-gmail &
fi
PIDS+=($!)

echo ""
echo "========================================"
echo " All watchers started!"
echo " PIDs: ${PIDS[*]}"
echo " To stop all: pkill -f 'watcher\|orchestrator'"
echo "========================================"
echo ""

# Save PIDs for stopping later
echo "${PIDS[*]}" > .watcher_pids
echo "PIDs saved to .watcher_pids"

# Wait for all background processes
wait
