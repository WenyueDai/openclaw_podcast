#!/usr/bin/env bash
set -euo pipefail

BLOGWATCHER_BIN="${BLOGWATCHER_BIN:-/home/eva/go/bin/blogwatcher}"
TARGET="${TELEGRAM_TARGET:-8539595576}"
STATE_DIR="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/state"
LOG="$STATE_DIR/blogwatcher_last.log"
mkdir -p "$STATE_DIR"

if [[ ! -x "$BLOGWATCHER_BIN" ]]; then
  echo "blogwatcher not installed: $BLOGWATCHER_BIN" | tee "$LOG"
  exit 0
fi

# Curated blog pages for discovery (blogwatcher works better on pages than raw RSS URLs)
declare -a BLOGS=(
  "Nature News|https://www.nature.com/news"
  "Nature Biotechnology|https://www.nature.com/nbt/"
  "Nature Methods|https://www.nature.com/nmeth/"
  "Endpoints News|https://endpts.com"
  "Quanta Magazine|https://www.quantamagazine.org"
)

for row in "${BLOGS[@]}"; do
  name="${row%%|*}"
  url="${row#*|}"
  "$BLOGWATCHER_BIN" add "$name" "$url" >/dev/null 2>&1 || true
done

{
  echo "=== $(date -u +%FT%TZ) blogwatcher scan ==="
  "$BLOGWATCHER_BIN" scan || true
  echo "--- unread ---"
  "$BLOGWATCHER_BIN" articles || true
} | tee "$LOG"

# Lightweight notify if there are unread items
if grep -qi "No unread articles!" "$LOG"; then
  exit 0
fi

openclaw message send --channel telegram --target "$TARGET" --message "📰 blogwatcher found updates today. I can fold these topics into tomorrow's podcast selection." || true
