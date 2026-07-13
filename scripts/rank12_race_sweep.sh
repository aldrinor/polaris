#!/usr/bin/env bash
# RANK12 — score every depth arm with the OFFICIAL RACE harness (task 72).
# Proxies (words, verified sentences, density) have never been checked against the score.
# 0.5 == parity with the human reference report.
set -u
cd /home/polaris/wt/flywheel
set -a && . ./.env && set +a

score () {  # name  report_path
  local name="$1" path="$2"
  if [ ! -f "$path" ]; then echo "[rank12] MISSING $name -> $path"; return; fi
  echo "=== [rank12] scoring $name ($(wc -w < "$path") words) ==="
  python scripts/score_report_race.py --report "$path" --task-id 72 --model-name "rank12_$name" 2>&1 \
    | tail -25
  echo "=== [rank12] done $name ==="
}

score ctrl   /home/polaris/wt/fw_ctrl/outputs/rank6_ctrl_compose/report.md
score rank7  /home/polaris/wt/flywheel/outputs/rank7_depth_compose/report.md
score rank8  /home/polaris/wt/fw_ctrl/outputs/rank8_menucap_compose/report.md
score rank9  /home/polaris/wt/flywheel/outputs/rank9_stack_compose/report.md
score rank10 /home/polaris/wt/flywheel/outputs/rank10_sections_compose/report.md
echo "=== [rank12] SWEEP COMPLETE ==="
