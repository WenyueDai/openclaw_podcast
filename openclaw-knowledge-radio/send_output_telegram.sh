#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/eva/openclaw_workspace/openclaw-knowledge-radio/output"
OUTBOUND="$HOME/.openclaw/media/outbound"
TARGET="8539595576"
MAX_BYTES=$((10 * 1024 * 1024))  # 10MB

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
  echo "WARN: Missing final mp3: $FINAL_MP3"
  openclaw message send \
    --channel telegram \
    --target "$TARGET" \
    --message "ℹ️ No new podcast audio generated for ${TODAY} (no fresh items in retrieval window)."
  exit 0
fi

SIZE=$(stat -c%s "$FINAL_MP3")
echo "INFO: FINAL_MP3_SIZE=$SIZE bytes"

# Send summary text first
SUMMARY="🎙️ Daily podcast is ready (${TODAY})."
if [ "$SIZE" -le "$MAX_BYTES" ]; then
  SUMMARY+=$'\n- Delivery: single file'
else
  SUMMARY+=$'\n- Delivery: chunked files (size > 10MB)'
fi
SUMMARY+=$'\n- Script: podcast_script_'"${TODAY}"$'_llm_clean.txt'

openclaw message send \
  --channel telegram \
  --target "$TARGET" \
  --message "$SUMMARY"

send_media_file() {
  local src="$1"
  local safe="$OUTBOUND/$(basename "$src")"
  cp "$src" "$safe"
  openclaw message send \
    --channel telegram \
    --target "$TARGET" \
    --media "$safe"
  rm -f "$safe"
}

if [ "$SIZE" -le "$MAX_BYTES" ]; then
  echo "INFO: Sending single final MP3"
  send_media_file "$FINAL_MP3"
else
  echo "INFO: Sending chunked MP3 files"
  shopt -s nullglob
  CHUNKS=("$DAY_DIR"/podcast_"$TODAY"_p*.mp3)
  shopt -u nullglob

  if [ ${#CHUNKS[@]} -eq 0 ]; then
    echo "ERROR: No chunk files found in $DAY_DIR"
    exit 1
  fi

  for chunk in "${CHUNKS[@]}"; do
    echo "sending chunk: $chunk"
    send_media_file "$chunk"
  done
fi

# Send cleaned script if present
if [ -f "$SCRIPT_TXT" ]; then
  send_media_file "$SCRIPT_TXT"
fi

find "$OUTBOUND" -type f -mtime +7 -print -delete

echo "DONE"
