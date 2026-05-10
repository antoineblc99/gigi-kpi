#!/bin/bash
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; source .env.local; set +a
export PYTHONPATH=.

LOG="pipelines/logs/daily_$(date +%Y-%m-%d).log"
{
  echo "=== run_daily START $(date -Iseconds) ==="
  echo "--- pull_ghl ---"
  python pipelines/pull_ghl.py --days 7
  echo "--- pull_instagram ---"
  python pipelines/pull_instagram.py
  echo "--- pull_meta ---"
  python pipelines/pull_meta.py --days 7
  echo "--- pull_calendar_capacity ---"
  python pipelines/pull_calendar_capacity.py
  echo "=== run_daily END $(date -Iseconds) ==="
} >> "$LOG" 2>&1
