#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   WEBSITE_REPO_DIR  (local clone of your GitHub Pages repo)
# Optional:
#   WEBSITE_BRANCH (default: main)

WEBSITE_REPO_DIR="${WEBSITE_REPO_DIR:-}"
WEBSITE_BRANCH="${WEBSITE_BRANCH:-main}"
PROJECT_REPO_DIR="/home/eva/openclaw_workspace/openclaw_podcast"
SRC_SITE_DIR="$PROJECT_REPO_DIR/docs"

if [[ -z "$WEBSITE_REPO_DIR" ]]; then
  echo "ERROR: set WEBSITE_REPO_DIR to your GitHub Pages repo path"
  exit 1
fi

python3 /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/tools/build_site.py

if [[ "$WEBSITE_REPO_DIR" == "$PROJECT_REPO_DIR" ]]; then
  # Same repo mode: publish by committing updated public_site in this repo.
  cd "$PROJECT_REPO_DIR"
  git add docs openclaw-knowledge-radio/tools/build_site.py openclaw-knowledge-radio/tools/publish_site.sh
else
  # Separate repo mode: sync built site into dedicated website repo.
  mkdir -p "$WEBSITE_REPO_DIR"
  rsync -av --delete "$SRC_SITE_DIR/" "$WEBSITE_REPO_DIR/"
  cd "$WEBSITE_REPO_DIR"
  git add .
fi

if git diff --cached --quiet; then
  echo "No site changes to publish"
  exit 0
fi

git commit -m "Update daily podcast site $(date +%F)"
git push origin "$WEBSITE_BRANCH"

echo "Published site to $WEBSITE_REPO_DIR ($WEBSITE_BRANCH)"
