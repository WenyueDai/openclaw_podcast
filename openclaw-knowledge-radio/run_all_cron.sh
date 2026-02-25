#!/usr/bin/env bash
set -euo pipefail

BASE="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio"
LOG="$BASE/cron_master.log"
LOCK="/tmp/podcast_daily.lock"

# single instance guard
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date)] another run is active, skipping" >> "$LOG"
  exit 0
fi

# append logs to file
exec >> "$LOG" 2>&1

echo "===== START $(date) ====="
echo "USER=$(whoami) HOST=$(hostname)"

# load env for cron (API keys etc.)
if [ -f /home/eva/.openclaw_env ]; then
  set -a
  source /home/eva/.openclaw_env
  set +a
fi

# activate virtual env
source "$BASE/.venv/bin/activate"

cd "$BASE"

echo "[1/2] run_cron_daily.sh"
./run_cron_daily.sh

echo "===== DONE $(date) ====="
