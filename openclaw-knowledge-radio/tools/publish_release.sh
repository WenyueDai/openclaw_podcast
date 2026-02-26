#!/usr/bin/env bash
set -euo pipefail

# Upload today's merged podcast mp3 to GitHub Release assets.
# Requires: GITHUB_TOKEN with repo scope.
# Optional: RELEASE_REPO (owner/repo), defaults WenyueDai/openclaw_podcast

RELEASE_REPO="${RELEASE_REPO:-WenyueDai/openclaw_podcast}"
TOKEN="${GITHUB_TOKEN:-}"
BASE_OUT="/home/eva/openclaw_workspace/openclaw-knowledge-radio/output"
INDEX_JSON="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/state/release_index.json"

DATE_STR="${RUN_DATE:-$(date +%F)}"
MP3="$BASE_OUT/$DATE_STR/podcast_${DATE_STR}.mp3"
TAG="episode-${DATE_STR}"
REL_NAME="Daily Podcast ${DATE_STR}"
ASSET_NAME="podcast_${DATE_STR}.mp3"

if [[ ! -f "$MP3" ]]; then
  echo "INFO: no merged mp3 found for $DATE_STR, skip release upload"
  exit 0
fi

if [[ -z "$TOKEN" ]]; then
  echo "INFO: GITHUB_TOKEN not set, skip release upload"
  exit 0
fi

api() {
  curl -sS -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" "$@"
}

# find or create release
RELEASE_JSON=$(api "https://api.github.com/repos/${RELEASE_REPO}/releases/tags/${TAG}" || true)
UPLOAD_URL=$(echo "$RELEASE_JSON" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("upload_url",""))' 2>/dev/null || true)
RID=$(echo "$RELEASE_JSON" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("id",""))' 2>/dev/null || true)

if [[ -z "$RID" || "$RID" == "None" ]]; then
  CREATE=$(curl -sS -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/${RELEASE_REPO}/releases \
    -d "{\"tag_name\":\"${TAG}\",\"name\":\"${REL_NAME}\",\"draft\":false,\"prerelease\":false}")
  UPLOAD_URL=$(echo "$CREATE" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("upload_url",""))')
  RID=$(echo "$CREATE" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("id",""))')
fi

if [[ -z "$RID" || "$RID" == "None" ]]; then
  echo "ERROR: failed to create/find release"
  exit 1
fi

# delete existing asset with same name if exists
ASSETS=$(api "https://api.github.com/repos/${RELEASE_REPO}/releases/${RID}/assets")
AID=$(echo "$ASSETS" | python3 -c 'import sys,json; a=json.load(sys.stdin); print(next((str(x.get("id")) for x in a if x.get("name")=="'"$ASSET_NAME"'"),""))')
if [[ -n "$AID" ]]; then
  curl -sS -X DELETE -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${RELEASE_REPO}/releases/assets/${AID}" >/dev/null
fi

UP_BASE=${UPLOAD_URL%%%\{*}
UPLOAD_RESP=$(curl -sS -X POST \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: audio/mpeg" \
  --data-binary @"$MP3" \
  "${UP_BASE}?name=${ASSET_NAME}")

DL_URL=$(echo "$UPLOAD_RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("browser_download_url",""))')
if [[ -z "$DL_URL" ]]; then
  echo "ERROR: upload failed"
  exit 1
fi

mkdir -p "$(dirname "$INDEX_JSON")"
python3 - "$INDEX_JSON" "$DATE_STR" "$DL_URL" <<'PY'
import json,sys,os
p,date,url=sys.argv[1:4]
d={}
if os.path.exists(p):
    with open(p,'r',encoding='utf-8') as f:
        try:d=json.load(f)
        except: d={}
d[date]=url
with open(p,'w',encoding='utf-8') as f: json.dump(d,f,indent=2,ensure_ascii=False)
print(f"recorded {date} -> {url}")
PY

echo "Release uploaded: $DL_URL"
