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

# 3) 激活 venv（优先项目 .venv，回退全局）
if [ -f /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/.venv/bin/activate ]; then
  source /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/.venv/bin/activate
elif [ -f /home/eva/.openclaw/venv/bin/activate ]; then
  source /home/eva/.openclaw/venv/bin/activate
fi

# 4) 跑主流程
python /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/run_daily.py
/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/send_output_telegram.sh

# 5) Optional: upload merged mp3 to GitHub Release (preferred long-term hosting)
/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/tools/publish_release.sh || true

# 6) publish website + RSS
if [ -n "${WEBSITE_REPO_DIR:-}" ]; then
  /home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio/tools/publish_site.sh
else
  echo "INFO: WEBSITE_REPO_DIR not set, skipping website publish"
fi

# 7) local retention for Raspberry Pi: keep only recent output folders
python - <<'PY'
from pathlib import Path
from datetime import datetime, timedelta
base=Path('/home/eva/openclaw_workspace/openclaw-knowledge-radio/output')
keep_days=7
cut=(datetime.now()-timedelta(days=keep_days)).date().isoformat()
if base.exists():
    for d in base.iterdir():
        if d.is_dir() and d.name < cut:
            for p in sorted(d.rglob('*'), reverse=True):
                if p.is_file() or p.is_symlink(): p.unlink(missing_ok=True)
                elif p.is_dir():
                    try:p.rmdir()
                    except:pass
            try:d.rmdir()
            except:pass
print('retention complete')
PY
