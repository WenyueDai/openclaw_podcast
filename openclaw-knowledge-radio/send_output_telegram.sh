#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/eva/openclaw_workspace/openclaw-knowledge-radio/output"
OUTBOUND="$HOME/.openclaw/media/outbound"
TARGET="8539595576"

TODAY=$(date +%Y-%m-%d)
DAY_DIR="$BASE_DIR/$TODAY"
mkdir -p "$OUTBOUND"

echo "SCRIPT START $(date)"
echo "INFO: DAY_DIR=$DAY_DIR"

if [ ! -d "$DAY_DIR" ]; then
  echo "ERROR: No date folder found"
  exit 1
fi

FINAL_MP3="$DAY_DIR/podcast_${TODAY}.mp3"
SCRIPT_TXT="$DAY_DIR/podcast_script_${TODAY}_llm_clean.txt"

if [ ! -f "$FINAL_MP3" ]; then
  echo "ERROR: Missing final mp3: $FINAL_MP3"
  exit 1
fi

# Send a short text summary first
SUMMARY="🎙️ Daily podcast is ready (${TODAY}).\n- Audio: podcast_${TODAY}.mp3\n- Script: podcast_script_${TODAY}_llm_clean.txt"
openclaw message send \
  --channel telegram \
  --target "$TARGET" \
  --message "$SUMMARY"

# Send only the final merged mp3 (not chunk parts)
MP3_SAFE="$OUTBOUND/$(basename "$FINAL_MP3")"
cp "$FINAL_MP3" "$MP3_SAFE"
openclaw message send \
  --channel telegram \
  --target "$TARGET" \
  --media "$MP3_SAFE"

# Send cleaned script if present
if [ -f "$SCRIPT_TXT" ]; then
  TXT_SAFE="$OUTBOUND/$(basename "$SCRIPT_TXT")"
  cp "$SCRIPT_TXT" "$TXT_SAFE"
  openclaw message send \
    --channel telegram \
    --target "$TARGET" \
    --media "$TXT_SAFE"
  rm -f "$TXT_SAFE"
fi

rm -f "$MP3_SAFE"
find "$OUTBOUND" -type f -mtime +7 -print -delete

echo "DONE"
