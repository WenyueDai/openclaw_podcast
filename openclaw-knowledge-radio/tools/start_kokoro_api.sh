#!/usr/bin/env bash
set -euo pipefail

BASE="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio"
LOG="$BASE/state/kokoro_api.log"
PIDFILE="$BASE/state/kokoro_api.pid"
mkdir -p "$BASE/state"

if pgrep -f "uvicorn tools.kokoro_api_server:app --host 127.0.0.1 --port 8880" >/dev/null; then
  echo "kokoro api already running"
  exit 0
fi

source "$BASE/.venv/bin/activate"
cd "$BASE"
nohup python -m uvicorn tools.kokoro_api_server:app --host 127.0.0.1 --port 8880 >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
sleep 2
curl -sf http://127.0.0.1:8880/health >/dev/null && echo "kokoro api started" || (echo "kokoro api failed"; exit 1)
