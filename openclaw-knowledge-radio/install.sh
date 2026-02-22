#!/usr/bin/env bash
set -euo pipefail

# Create venv
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# ffmpeg for MP3 concat
sudo apt-get update
sudo apt-get install -y ffmpeg

echo "✅ Install done. Run: ./.venv/bin/python run_daily.py"
