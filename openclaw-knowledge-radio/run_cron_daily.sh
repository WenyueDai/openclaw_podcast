#!/usr/bin/env bash
set -euo pipefail

# 1) 进入项目目录（避免相对路径炸裂）
cd /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio

# 2) 加载你需要的环境变量（推荐放这里，而不是指望 cron 继承）
#    你可以把 OPENROUTER_API_KEY 等都写到 ~/.openclaw_env 里
if [ -f /home/eva/.openclaw_env ]; then
  set -a
  source /home/eva/.openclaw_env
  set +a
fi

# 3) 激活 venv（你现在用的是 .venv，不是 conda）
source /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/.venv/bin/activate

# 4) 跑主流程
python /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/run_daily.py
