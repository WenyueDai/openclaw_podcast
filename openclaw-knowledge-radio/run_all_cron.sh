#!/bin/bash
set -euo pipefail
set -e
set -x
BASE="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio"
LOG="/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/cron_master.log"

export NODE="/home/eva/.nvm/versions/node/v22.22.0/bin/node"
export PATH="/home/eva/.nvm/versions/node/v22.22.0/bin:$PATH"
export NVM_DIR="$HOME/.nvm"
source /home/eva.openclaw_env
source "$NVM_DIR/nvm.sh" 
nvm use 22 >/dev/null

source /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/.venv/bin/activate


# 同时输出到 log + 如果有终端则输出到终端（cron 没终端也没关系）
exec > >(tee -a "$LOG") 2>&1

echo "===== START $(date) ====="
echo "USER=$(whoami)  HOST=$(hostname)"
echo "PWD=$(pwd)"
echo "PATH=$PATH"
echo "SHELL: $SHELL"
echo "LOGIN SHELL: $0"
echo "OPENAI:${OPENAI_API_KEY:+YES}"
echo "PATH: $PATH"


cd "$BASE"

echo "[1/4] run_cron_daily.sh"
./run_cron_daily.sh
sleep 60


