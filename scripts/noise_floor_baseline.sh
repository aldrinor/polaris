#!/usr/bin/env bash
# Pin the BASELINE the same way we pinned Rank10 (k=5, identical bytes).
# Every arm was scored ONCE; the true judge SD is 0.0074. Without a k=5 baseline the
# "+0.026 for Rank10" claim rests on a single unlucky/lucky draw of the control.
set -u
cd /home/polaris/wt/flywheel
set -a && . ./.env && set +a
R=/home/polaris/wt/fw_ctrl/outputs/rank6_ctrl_compose/report.md
for i in 1 2 3 4 5; do
  echo "=== [baseline] replicate $i/5 ==="
  python scripts/score_report_race.py --report "$R" --task-id 72 --model-name "noise_ctrl_$i" 2>&1 | grep -E "Overall Score|Error"
done
echo "=== [baseline] ALL 5 DONE ==="
