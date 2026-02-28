#!/usr/bin/env bash
# Daily podcast generation — minimal wrapper for cron or manual runs.
# Activates the local venv, loads .env, then runs the pipeline.
# Publishing to GitHub Releases + GitHub Pages is handled inside run_daily.py.
#
# Usage:
#   bash run_cron_daily.sh
#   LOOKBACK_HOURS=72 bash run_cron_daily.sh
#   RUN_DATE=2026-02-28 REGEN_FROM_CACHE=true bash run_cron_daily.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [[ -f ".env" ]]; then
    set -a
    source .env
    set +a
fi

# Activate virtual environment
source .venv/bin/activate

python run_daily.py
