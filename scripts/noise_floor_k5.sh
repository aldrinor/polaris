#!/usr/bin/env bash
# Pin the TRUE per-call judge noise: score the BYTE-IDENTICAL rank10 report 5x.
# Every lever we chase is worth ~+0.010; our assumed noise is ~+/-0.016. If we cannot
# see our own effects, we cannot know if the new architecture worked. This fixes the ruler.
set -u
cd /home/polaris/wt/flywheel
set -a && . ./.env && set +a
R=outputs/rank10_sections_compose/report.md
for i in 1 2 3 4 5; do
  echo "=== [noise] replicate $i/5 ==="
  python scripts/score_report_race.py --report "$R" --task-id 72 --model-name "noise_r10_$i" 2>&1 | grep -E "Overall Score|Comprehensiveness|Insight|Instruction|Readability|Error" 
done
echo "=== [noise] ALL 5 DONE ==="
