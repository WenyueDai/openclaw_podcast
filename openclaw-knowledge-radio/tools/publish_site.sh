#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   WEBSITE_REPO_DIR  (local clone of your GitHub Pages repo)
# Optional:
#   WEBSITE_BRANCH (default: main)

WEBSITE_REPO_DIR="${WEBSITE_REPO_DIR:-}"
WEBSITE_BRANCH="${WEBSITE_BRANCH:-main}"
SRC_SITE_DIR="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/public_site"

if [[ -z "$WEBSITE_REPO_DIR" ]]; then
  echo "ERROR: set WEBSITE_REPO_DIR to your GitHub Pages repo path"
  exit 1
fi

python3 /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/tools/build_site.py

mkdir -p "$WEBSITE_REPO_DIR"
rsync -av --delete "$SRC_SITE_DIR/" "$WEBSITE_REPO_DIR/"

cd "$WEBSITE_REPO_DIR"
git add .
if git diff --cached --quiet; then
  echo "No site changes to publish"
  exit 0
fi

git commit -m "Update daily podcast site $(date +%F)"
git push origin "$WEBSITE_BRANCH"

echo "Published site to $WEBSITE_REPO_DIR ($WEBSITE_BRANCH)"
