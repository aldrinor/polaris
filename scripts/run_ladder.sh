#!/usr/bin/env bash
# THE RELEASE LADDER — Sol's design, and the discipline turn 2 lacked.
#
# Turn 2 LOST (0.4382 -> 0.4224) because I changed the corpus, the structure, the contract and the
# attribution ALL AT ONCE. Comprehensiveness collapsed -1.14 and there was no way to know which change
# did it. A stacked arm that loses teaches you nothing. A stacked arm that WINS teaches you nothing either.
#
# So: build everything, but RELEASE IT AS A CUMULATIVE LADDER over ONE FROZEN CORPUS.
#
#   A0  integrity replay      new source-bound gate, OLD corpus, OLD content.
#                             It must PRESERVE supported claims and KILL every attack.
#                             Expected: ~0.000. Its purpose is validity, not points.
#   A1  evidence arm          + full-document mining (we have read 31.9% of each paper -- the
#                             introductions -- while 1,825+ findings sat in the results sections)
#   A2  argument arm          + comparison planner + fact-use ledger + native attributed/owned synthesis
#                             (THE highest-value fix: 28 subsections are written with NO shared argument
#                              state, so nobody ever decides what is being compared with what)
#   A3  final arm             + implications + restricted cohesion + generated abstract/conclusion
#
# A1's evidence snapshot is FROZEN and reused by A2 and A3, so the writing comparison is not
# confounded by corpus noise. Each arm is scored k=5 paired at the CRITERION level, because 20 of the
# 25 criteria cannot clear the +0.0094 kill rule even at a perfect 10/10 -- the scalar CANNOT SEE a
# single lever, and deciding on it is how you throw away levers that worked.
#
# THE RELEASE RULE: A3 ships ONLY if no faithfulness canary regresses. A win that fails the gate is a loss.
set -uo pipefail
cd /home/polaris/wt/flywheel
set -a && . ./.env && set +a

BASE=outputs/rank10_sections_compose/report.md      # the pinned baseline, 0.4292 in the k=5 frame
K=${K:-5}

step () { echo; echo "======================================================================"; echo "$@"; echo "======================================================================"; }

step "[GATE] the door must be shut before anything composes"
python scripts/test_gate_is_wired.py | tail -2
python scripts/test_gate_is_wired.py >/dev/null 2>&1 || { echo "!! CANARY RED — NOTHING SHIPS"; exit 1; }

step "[CORPUS] re-derive every label from its content (a label that asserts more than its content is how we got here)"
python scripts/corpus_truth.py --fix | tail -8

for ARM in A0 A1 A2 A3; do
  step "[$ARM] compose"
  OUT=outputs/arm_$ARM
  mkdir -p "$OUT"
  ARM=$ARM python -u scripts/cellcog_composer.py --write --arm "$ARM" --out "$OUT" 2>&1 | tail -14 || {
      echo "!! $ARM FAILED TO COMPOSE — stopping the ladder here, honestly"; break; }

  # what actually reached the page?
  python - "$OUT/report.md" <<'PY'
import re, sys
t = open(sys.argv[1]).read(); b = re.sub(r'(?m)^#.*$', '', t)
n = re.findall(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b', b)
w = len(b.split())
print(f'    words {w:,} | quantitative claims {len(n)} ({1000*len(n)/max(w,1):.1f}/1k) '
      f'| table rows {t.count(chr(10)+"|")} | H2 {len(re.findall(r"(?m)^## ", t))}')
print(f'    (turn 3: 8,012w, 2 claims, 0 rows | cellcog: 13,580w, 202 claims, 10 rows)')
PY

  step "[$ARM] score, k=$K paired, criterion-level"
  python -u scripts/criterion_ab.py --a "$BASE" --b "$OUT/report.md" --task-id 72 --k "$K" \
      --targets "Citation,Synthesis,Depth,Insight,Industry,Data,Cohesion,Foresight,Themes" \
      2>&1 | sed -n '/CRITERION-LEVEL/,$p'
  cp outputs/criterion_ab.json "outputs/criterion_ab_$ARM.json" 2>/dev/null || true
done

step "THE LADDER IS DONE. Read every criterion, not the top of the sort."
echo "  A scalar win can hide a structural loss: turn 3 gained +0.0310 while FOUR criteria regressed"
echo "  (industry scope -0.84, various industries -0.78, foresight -0.68, breadth -0.26) and I reported"
echo "  'no regressions' because I sorted by absolute move and read the top nine."
echo
echo "  RELEASE RULE: A3 ships ONLY if the canary is green. A win that fails the gate is a loss."
