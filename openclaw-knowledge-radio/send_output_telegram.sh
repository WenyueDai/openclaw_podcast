#!/bin/bash
set -euo pipefail

echo "SCRIPT START $(date)"

BASE_DIR="/home/eva/openclaw_workspace/openclaw-knowledge-radio/output"

TODAY=$(date +%Y-%m-%d)
DAY_DIR="$BASE_DIR/$TODAY"

echo "INFO: DAY_DIR=$DAY_DIR"

if [ ! -d "$DAY_DIR" ]; then
  echo "ERROR: No date folder found"
  exit 1
fi

OUTBOUND="$HOME/.openclaw/media/outbound"
mkdir -p "$OUTBOUND"



TXT_FILE=$(find "$DAY_DIR" -name "*clean.txt" | head -n 1)
#MP3_FILE=$(find "$DAY_DIR" -name "*.mp3" | head -n 1)

for MP3_FILE in "$DAY_DIR"/*.mp3; do
  echo "sending $MP3_FILE"
  MP3_SAFE="$OUTBOUND/$(basename "$MP3_FILE")"
  cp "$MP3_FILE" "$OUTBOUND/"
  openclaw message send \
    --channel telegram \
    --target 8539595576 \
    --media "$MP3_SAFE"
  case "$MP3_SAFE" in "$OUTBOUND"/*) rm -f "$MP3_SAFE" ;; esac
done


echo "INFO: TXT=$TXT_FILE"
#echo "INFO: MP3=$MP3_FILE"

if [ -z "$TXT_FILE" ]; then
  echo "ERROR: Missing TXT"
  exit 1
fi


cp "$TXT_FILE" "$OUTBOUND/"
#cp "$MP3_FILE" "$OUTBOUND/"

TXT_SAFE="$OUTBOUND/$(basename "$TXT_FILE")"
#MP3_SAFE="$OUTBOUND/$(basename "$MP3_FILE")"

echo "INFO: SAFE_TXT=$TXT_SAFE"
#echo "INFO: SAFE_MP3=$MP3_SAFE"

openclaw message send \
  --channel telegram \
  --target 8539595576 \
  --media "$TXT_SAFE"


# 删除本次复制的两个文件（安全：必须在 OUTBOUND 下才删）
case "$TXT_SAFE" in "$OUTBOUND"/*) rm -f "$TXT_SAFE" ;; esac
#case "$MP3_SAFE" in "$OUTBOUND"/*) rm -f "$MP3_SAFE" ;; esac

# 可选：清理 7 天前的旧文件，防止堆积
find "$OUTBOUND" -type f -mtime +7 -print -delete

echo "DONE"


