#!/usr/bin/env bash
# scripts/cleanup/count_hits.sh — preflight count, no exit-on-hit
# iter 11 CLEAN-PR5-PRECONDITION-INVERTED-1 + iter 12 CLEAN-COUNT-HITS-ERRMASK-2 fix
set -euo pipefail
PATTERN="$1"
EXPECTED_COUNT="${2:-}"  # optional; if provided, exits non-zero on mismatch
# iter 12 CLEAN-COUNT-HITS-ERRMASK-2 fix: explicit exit-code handling instead of `|| echo 0`.
# `git grep -l` returns 0 on hits, 1 on no matches, 2+ on real error.
set +e
HITS=$(git grep -l -E "$PATTERN" -- \
    ':!archive/' ':!state/polaris_restart/' ':!outputs/audits/' \
    ':!outputs/codex_findings/' ':!.codex/_archive_pre_v6_2/' \
    ':!.codex/continuous/' ':!.codex/round_*/' ':!.codex/deep_dive_round_*/' \
    ':!logs/session_log.md' ':!.legacy/')
RC=$?
set -e
case $RC in
    0) COUNT=$(echo "$HITS" | wc -l | tr -d ' ') ;;
    1) COUNT=0 ;;
    *)
        echo "ERROR: git grep failed (rc=$RC)" >&2
        exit $RC
        ;;
esac
echo "$COUNT"
if [ -n "$EXPECTED_COUNT" ] && [ "$COUNT" -ne "$EXPECTED_COUNT" ]; then
    echo "ERROR: expected $EXPECTED_COUNT files, got $COUNT" >&2
    exit 1
fi
