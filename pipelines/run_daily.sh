#!/bin/bash
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; source .env.local; set +a
export PYTHONPATH=.

DAY="$(date +%Y-%m-%d)"
LOG="pipelines/logs/daily_$DAY.log"
FAILED=()

run_step() {
  local name="$1"; shift
  echo "--- $name ---"
  if ! "$@"; then
    FAILED+=("$name")
    echo "!! $name a échoué (exit non-zéro)"
  fi
}

{
  echo "=== run_daily START $(date -Iseconds) ==="
  run_step pull_ghl python pipelines/pull_ghl.py --days 7
  run_step pull_instagram python pipelines/pull_instagram.py
  run_step pull_meta python pipelines/pull_meta.py --days 7
  run_step pull_calendar_capacity python pipelines/pull_calendar_capacity.py
  echo "=== run_daily END $(date -Iseconds) ==="

  if [ ${#FAILED[@]} -gt 0 ]; then
    STEPS="${FAILED[*]}"
    echo "!!! ÉCHECS: $STEPS"
    # Notification macOS native — alerte si un pull a planté
    osascript -e "display notification \"Échec: $STEPS — voir logs/daily_$DAY.log\" with title \"Gigi KPI — pull quotidien\" sound name \"Basso\"" 2>/dev/null || true
    exit 1
  fi
  echo "→ tous les pulls OK"
} >> "$LOG" 2>&1
