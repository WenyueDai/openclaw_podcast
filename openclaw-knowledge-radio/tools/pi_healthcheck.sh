#!/usr/bin/env bash
set -euo pipefail

TARGET="${TELEGRAM_TARGET:-8539595576}"
STATE_DIR="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/state"
mkdir -p "$STATE_DIR"
OUT="$STATE_DIR/healthcheck_last.txt"

{
  echo "=== Pi Healthcheck $(date -u +%FT%TZ) ==="
  echo "-- disk --"
  df -h / | tail -n 1
  echo "-- memory --"
  free -h | sed -n '1,2p'
  echo "-- openclaw security --"
  openclaw security audit --deep || true
  echo "-- openclaw update --"
  openclaw update status || true
} > "$OUT"

summary=$(awk 'NR<=25{print}' "$OUT" | sed ':a;N;$!ba;s/\n/\\n/g')
openclaw message send --channel telegram --target "$TARGET" --message "🛡️ Weekly Pi healthcheck finished.\n${summary}" || true
