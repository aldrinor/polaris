#!/usr/bin/env bash
# I-arch-007 SMOKE harness — deploy the current code to ONE VM and run a small-scale FAST Q90 smoke
# through the REAL Gate-B 4-role launcher (run_gate_b.py --smoke-scale).
#
# Why run_gate_b.py (not run_honest_sweep_r3.py --pathB-gate): run_gate_b.py is the ONLY CLI that
# fires the native 4-role D8 seam (its own docstring). --smoke-scale force-shrinks the breadth FLOOR
# + timeout backstops so the run is ~15-20 min (HANG known in <=40 min). Faithfulness gates, the A20
# funnel, and the 4-role seam are UNTOUCHED (verified: smoke_scale=False is byte-identical to a full run).
#
# Two modes (SPEND isolated to `launch`):
#   verify (default) : push current code to the box (preserve .env + outputs), clear stale bytecode,
#                      then NO-SPEND checks — the --smoke-scale flag is present in the deployed code,
#                      the iter1/over-strict sweep helpers are present, run_gate_b's built-in
#                      `--list` (NO-SPEND/NO-NETWORK dry-run) resolves the slug + 4-role transport.
#   launch           : start a FRESH (non-resume) Q90 run with --smoke-scale, backgrounded. PAID step.
#
# Usage:  bash scripts/iarch007_smoke_deploy_launch.sh [verify|launch]
set -euo pipefail

MODE="${1:-verify}"
PORT=39556
BOX="root@ssh8.vast.ai"
KEY="$HOME/.ssh/id_ed25519"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes -p "$PORT" "$BOX")
SCP=(scp -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -P "$PORT")
REMOTE=/root/polaris
# Codex iter-2: Q72 (drb_72_ai_labor) is the cleaner gate-check — academic-economic sources, lower
# corpus_inadequate risk than Q90's case-law stress (smoke.md). Q90 is for the full-scale run later.
SLUG=drb_72_ai_labor
OUT_ROOT=outputs/iarch007_smoke
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_HEAD="$(git -C "$ROOT" rev-parse --short HEAD)"
PY=/opt/conda/bin/python

echo "== I-arch-007 smoke harness =="
echo "   mode=$MODE  box=$BOX:$PORT  slug=$SLUG  local_HEAD=$LOCAL_HEAD  runner=run_gate_b.py --smoke-scale"

deploy() {
  echo "-- [1] build code tarball (exclude bytecode) --"
  local TGZ="/tmp/polaris_code_${LOCAL_HEAD}.tgz"
  ( cd "$ROOT" && tar czf "$TGZ" --exclude='__pycache__' --exclude='*.pyc' src scripts config )
  echo "   tarball: $TGZ ($(wc -c < "$TGZ") bytes)"
  echo "-- [2] push + extract over $REMOTE (PRESERVES .env + outputs) + clear stale bytecode --"
  "${SCP[@]}" "$TGZ" "$BOX:/root/polaris_code.tgz"
  "${SSH[@]}" "cd $REMOTE && tar xzf /root/polaris_code.tgz && find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null; echo extracted"
}

verify() {
  echo "-- [3] NO-SPEND verification --"
  "${SSH[@]}" bash -s <<REMOTE_EOF
set -euo pipefail
cd $REMOTE
fail=0
echo "  (a) --smoke-scale flag present in deployed run_gate_b.py:"
grep -q '"--smoke-scale"' scripts/dr_benchmark/run_gate_b.py && echo "      --smoke-scale OK" || { echo "      MISSING --smoke-scale (STALE CODE)"; fail=1; }
grep -q '_SMOKE_SCALE_OVERRIDES' scripts/dr_benchmark/run_gate_b.py && echo "      _SMOKE_SCALE_OVERRIDES OK" || { echo "      MISSING override dict"; fail=1; }
echo "  (b) iter1 + over-strict sweep helpers present (proves ad8dd596-class code):"
for sym in build_attempted_zero_emit_section_stub reconstruct_release_outcome_from_manifest ; do
  grep -q "def \$sym" scripts/run_honest_sweep_r3.py && echo "      \$sym OK" || { echo "      MISSING \$sym"; fail=1; }
done
grep -q "consolidate-keep-all" src/polaris_graph/generator/fact_dedup.py && echo "      fact_dedup keep-all OK" || { echo "      fact_dedup keep-all MISSING"; fail=1; }
grep -q "SAME-SOURCE guard" src/polaris_graph/retrieval/contradiction_detector.py && echo "      same-source guard OK" || { echo "      same-source guard MISSING"; fail=1; }
echo "  (c) 3 API keys present in .env:"
for k in OPENROUTER_API_KEY SERPER_API_KEY ZYTE_API_KEY ; do
  grep -qE "^\$k=" .env && echo "      \$k OK" || { echo "      \$k MISSING"; fail=1; }
done
echo "  (d) run_gate_b.py compiles:"
$PY -m py_compile scripts/dr_benchmark/run_gate_b.py && echo "      py_compile OK" || { echo "      py_compile FAILED"; fail=1; }
echo "  (e) Gate-B --list NO-SPEND dry-run (--only is mutually exclusive with --list, so list ALL + grep the slug):"
set -a; source .env; set +a
export PYTHONPATH=$REMOTE:$REMOTE/src
list_out=\$($PY -m scripts.dr_benchmark.run_gate_b --list 2>&1) || { echo "      --list FAILED"; echo "\$list_out" | tail -8; fail=1; }
echo "\$list_out" | tail -20
echo "\$list_out" | grep -q "$SLUG" && echo "      slug $SLUG resolves in --list OK" || { echo "      slug $SLUG NOT in --list"; fail=1; }
echo ""
[ "\$fail" -eq 0 ] && echo "  VERIFY: PASS (no spend incurred)" || { echo "  VERIFY: FAIL"; exit 3; }
REMOTE_EOF
}

launch() {
  echo "-- [4] LAUNCH — FRESH (non-resume) --smoke-scale Q90 (THIS SPENDS) --"
  "${SSH[@]}" bash -s <<REMOTE_EOF
set -euo pipefail
cd $REMOTE
mkdir -p $OUT_ROOT
set -a; source .env; set +a
export PYTHONPATH=$REMOTE:$REMOTE/src
setsid nohup $PY -m scripts.dr_benchmark.run_gate_b \
  --only $SLUG --smoke-scale --out-root $OUT_ROOT \
  > $OUT_ROOT/launch.log 2>&1 &
PID=\$!
echo "\$PID" > $OUT_ROOT/run.pid
date -u +%Y-%m-%dT%H:%M:%SZ > $OUT_ROOT/started_at.txt
echo "  LAUNCHED pid=\$PID  log=$REMOTE/$OUT_ROOT/launch.log  wall-backstop=2400s(40min)"
REMOTE_EOF
}

case "$MODE" in
  verify) deploy; verify ;;
  # launch ALWAYS deploys fresh code + runs the no-spend verify FIRST, so a standalone `launch`
  # can never spend against stale remote code or an unverified config (Codex iter-2 P1c).
  launch) deploy; verify; launch ;;
  *) echo "usage: $0 [verify|launch]"; exit 2 ;;
esac
