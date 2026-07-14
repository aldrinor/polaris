#!/usr/bin/env bash
# A0 — the honest baseline. Fires the moment the P0 wheel reports 11/11.
#
# WHAT A0 MEASURES: the CURRENT 10-work corpus, through the REBUILT pipeline
# (integrity + argument planner + cohesion + fact-ledger). It answers three things
# BEFORE the 4-hour fetch finishes:
#   1. what did integrity COST?   (the 0.4603 was fake -- it cited working papers as journals)
#   2. do the new levers MOVE anything at all?
#   3. is the composer even HEALTHY? -- better to find out on a 1-hour cycle than after an 8-hour fetch
set -uo pipefail
cd /home/polaris/wt/flywheel
set -a && . ./.env && set +a

WF=/home/polaris/.claude/projects/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/subagents/workflows/wf_e74cf4e9-88c

echo "[a0] waiting for the P0 wheel's fresh adversary to report..."
for i in $(seq 1 120); do
  n=$(grep -c '"type":"result"' "$WF/journal.jsonl" 2>/dev/null || echo 0)
  # the reattack agent is the 2nd of 3
  if [ "${n:-0}" -ge 2 ]; then
    if grep -qiE '11/11|all eleven .*hold|11 of 11' "$WF/journal.jsonl" 2>/dev/null; then
      echo "[a0] ADVERSARY REPORTS 11/11 — the P0 is closed. Composing A0."
      break
    fi
    echo "[a0] *** ADVERSARY DID NOT REPORT 11/11 — A0 WILL NOT RUN ON A BROKEN GATE. ***"
    exit 1
  fi
  sleep 60
done

echo "[a0] canary must be green or nothing composes"
python scripts/test_gate_is_wired.py | tail -1
python scripts/test_gate_is_wired.py >/dev/null 2>&1 || { echo "[a0] CANARY RED — ABORT"; exit 1; }

echo "[a0] composing (draft -> publisher -> release)"
python -u scripts/cellcog_composer.py --write 2>&1 | tail -20

echo "[a0] scoring k=5 paired, criterion-level, against the pinned baseline"
python -u scripts/criterion_ab.py \
  --a outputs/rank10_sections_compose/report.md \
  --b outputs/release/report.md \
  --task-id 72 --k 5 \
  --targets "Synthesis,Depth,Themes,Industry,Cohesion,Data,Citation,Foresight" \
  2>&1 | sed -n '/CRITERION-LEVEL/,$p'

echo
echo "[a0] READ EVERY CRITERION, NOT THE TOP OF THE SORT."
echo "     Turn 3 gained +0.0310 while FOUR criteria regressed underneath it."
echo "     A positive total CANNOT override a criterion regression."
