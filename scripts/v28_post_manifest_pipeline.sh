#!/usr/bin/env bash
# V28 post-manifest pipeline runner.
#
# Fires the moment manifest.json lands. Runs:
#   1. M-49 preservation regression suite
#   2. On pass: launches Codex DEEP content audit in background
#   3. Prepares scratch scratch files for Claude to write the parallel
#      audit. Claude runs the audit interactively (not this script).
#
# Exit codes:
#   0  — preservation passed, Codex audit launched
#   1  — manifest missing (can't proceed)
#   2  — preservation suite failed (regression detected; halt)

set -eo pipefail

V28_ROOT="${V28_ROOT:-outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm}"
MANIFEST="$V28_ROOT/manifest.json"

if [ ! -f "$MANIFEST" ]; then
  echo "[err] manifest missing: $MANIFEST"
  exit 1
fi

echo "=== Step 1: M-49 preservation regression suite ==="
if POLARIS_V28_SWEEP_ROOT="$V28_ROOT" \
   PYTHONPATH=src \
   python -m pytest -q tests/polaris_graph/test_m49_v28_preservation.py; then
  echo "[ok] preservation suite passed"
else
  echo "[err] preservation suite FAILED — V28 regressed a V27 floor."
  echo "      Inspect the failing test names above. Do NOT proceed to"
  echo "      audits — V28 cannot ship."
  exit 2
fi

echo ""
echo "=== Step 2: launch Codex DEEP content audit in background ==="
mkdir -p outputs/codex_findings/v28_deep_content_audit
codex exec --full-auto "$(cat archive/2026-05-11-root-hygiene/codex_historical/v28_deep_content_audit_brief.md)" \
  > outputs/codex_findings/v28_deep_content_audit/_codex_stdout.txt 2>&1 &
CODEX_PID=$!
echo "[ok] Codex DEEP content audit PID: $CODEX_PID"

echo ""
echo "=== Step 3: prepare V28 audit output dir for Claude ==="
mkdir -p outputs/audits/v28
echo "[ok] outputs/audits/v28/ ready"

echo ""
echo "Next steps (Claude interactive):"
echo "  1. Load $MANIFEST + report.md and the competitor baselines."
echo "  2. Write outputs/audits/v28/claude_deep_content_audit.md"
echo "     per topic A..F + additional V28 checks."
echo "  3. When Codex findings.md lands, cross-review + write"
echo "     outputs/audits/v28/gate_verdict.md"
echo "  4. If SHIPPABLE: PushNotification to user."
echo "  5. If PARTIAL: write V28→V29 fix_plan.md, submit to Codex."
