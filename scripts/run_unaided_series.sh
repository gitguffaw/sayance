#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS_ROOT="$ROOT/results/unaided-scheduled-5h"
LOGS_DIR="$RESULTS_ROOT/logs"

mkdir -p "$LOGS_DIR"
cd "$ROOT"

# 2 runs/hour for 5 hours => 10 runs at 30-minute offsets.
for idx in {1..10}; do
  delay_seconds=$(( (idx - 1) * 1800 ))
  run_id=$(printf "%02d" "$idx")
  (
    sleep "$delay_seconds"
    python3 run_benchmark.py \
      --llms claude codex \
      --no-grade \
      --context-mode isolated \
      --claude-model claude-opus-4-6 \
      --codex-model gpt-5.4 \
      --results-dir "results/unaided-scheduled-5h/run${run_id}" \
      > "$LOGS_DIR/run${run_id}.log" 2>&1
  ) &
done

wait
