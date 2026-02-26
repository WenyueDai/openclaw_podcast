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

TELEGRAM_TARGET="${TELEGRAM_TARGET:-8539595576}"

notify_tg() {
  local text="$1"
  openclaw message send --channel telegram --target "$TELEGRAM_TARGET" --message "$text" || true
}

on_error() {
  local code=$?
  local tail_log
  tail_log=$(tail -n 20 "$LOG" | sed 's/"/'"'"'/g')
  notify_tg "⚠️ Daily podcast failed (stage: ${CURRENT_STAGE:-unknown}, code: ${code}). Check cron_master.log."
  echo "ERROR stage=${CURRENT_STAGE:-unknown} code=$code"
  echo "$tail_log"
  exit $code
}
trap on_error ERR

# load env for cron (API keys etc.)
if [ -f /home/eva/.openclaw_env ]; then
  set -a
  source /home/eva/.openclaw_env
  set +a
fi

# activate virtual env (prefer project .venv, fallback global)
if [ -f "$BASE/.venv/bin/activate" ]; then
  source "$BASE/.venv/bin/activate"
elif [ -f /home/eva/.openclaw/venv/bin/activate ]; then
  source /home/eva/.openclaw/venv/bin/activate
else
  echo "ERROR: no usable venv found" >&2
  exit 1
fi

cd "$BASE"

CURRENT_STAGE="run_cron_daily"
echo "[1/2] run_cron_daily.sh"
timeout 2h ./run_cron_daily.sh

CURRENT_STAGE="finalize"
echo "===== DONE $(date) ====="
notify_tg "✅ Daily podcast run finished. Feed: https://wenyuedai.github.io/openclaw_podcast/feed.xml"
