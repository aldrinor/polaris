#!/usr/bin/env bash
# scripts/hooks/session_start_check.sh
#
# Per polaris-restart Plan §9.6a — Persisted session-start hook (CRITICAL).
# Fires BEFORE any Bash/Edit/Write/MultiEdit tool call. Behavior (iter 7 PRB6-P1-001 +
# iter 8 PRB7-P2-003 update):
# - ALWAYS verifies BOTH polaris-controls/CHARTER.md AND polaris-controls/PLAN.md
#   blob hashes against state/polaris_restart/charter_sha_pin.txt on EVERY tool call.
#   No same-day-stamp shortcut.
# - If both SHAs match pins: refresh stamp (informational only — last successful
#   check time + observed SHAs) and exit 0 to allow tool call.
# - If either SHA mismatches / pin missing / file missing: emit PreToolUse deny
#   JSON with reconciliation reason and exit 0 (Claude Code reads the decision
#   from stdout JSON regardless of exit code).
#
# DNA doc updates alone are insufficient because LLM compaction can erase the
# memory of practice. This persistent hook enforces the ritual structurally —
# not by Claude remembering to read CLAUDE.md, but by the hook re-verifying
# CHARTER + PLAN SHAs on every tool call.
#
# CODEOWNERS-protected per §10.0. Claude cannot edit this file.
#
# Created: 2026-05-05 night (PR-B)

set -euo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
STAMP="${REPO_ROOT}/state/polaris_restart/session_started_$(date +%Y%m%d).stamp"

# iter 7 PRB6-P1-001 fix: ALWAYS verify SHAs on every tool call. Earlier the
# hook auto-skipped if stamp existed → if CHARTER/PLAN changed mid-day, the cage
# would not detect drift. Now verify every call; stamp is informational only.

# Verify CHARTER+PLAN blob hashes match polaris-controls files (via `git hash-object`, not HEAD)
PIN_FILE="${REPO_ROOT}/state/polaris_restart/charter_sha_pin.txt"
PIN_SHA=""
PIN_CHARTER=""
PIN_PLAN=""
if [[ -f "$PIN_FILE" ]]; then
    PIN_CHARTER=$(grep -E '^[a-f0-9]{40}  polaris-controls/CHARTER.md$' "$PIN_FILE" | awk '{print $1}' | head -1 || echo "")
    PIN_PLAN=$(grep -E '^[a-f0-9]{40}  polaris-controls/PLAN.md$' "$PIN_FILE" | awk '{print $1}' | head -1 || echo "")
fi

# iter 21 PRB2-P2-003 + iter 4 PRB3-P2-002 fix: multi-path + multi-file
SISTER_ROOT=""
for ROOT in \
    "${REPO_ROOT}/../polaris-controls" \
    "/c/polaris-controls" \
    "C:/polaris-controls"; do
    if [[ -d "$ROOT" ]]; then
        SISTER_ROOT="$ROOT"
        break
    fi
done

LIVE_CHARTER=""
LIVE_PLAN=""
if [[ -n "$SISTER_ROOT" ]]; then
    [[ -f "${SISTER_ROOT}/CHARTER.md" ]] && LIVE_CHARTER=$(git -C "$SISTER_ROOT" hash-object CHARTER.md 2>/dev/null || echo "")
    [[ -f "${SISTER_ROOT}/PLAN.md" ]] && LIVE_PLAN=$(git -C "$SISTER_ROOT" hash-object PLAN.md 2>/dev/null || echo "")
fi

DRIFT=""
if [[ -z "$LIVE_CHARTER" ]] || [[ -z "$PIN_CHARTER" ]] || [[ "$LIVE_CHARTER" != "$PIN_CHARTER" ]]; then
    DRIFT="${DRIFT}CHARTER.md pin=${PIN_CHARTER:-MISSING} live=${LIVE_CHARTER:-UNREADABLE}; "
fi
if [[ -z "$LIVE_PLAN" ]] || [[ -z "$PIN_PLAN" ]] || [[ "$LIVE_PLAN" != "$PIN_PLAN" ]]; then
    DRIFT="${DRIFT}PLAN.md pin=${PIN_PLAN:-MISSING} live=${LIVE_PLAN:-UNREADABLE}; "
fi

if [[ -n "$DRIFT" ]]; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "SHA pin drift: ${DRIFT}Halt per Plan §10. Resolution requires user-side reconciliation: user reads polaris-controls/CHARTER.md + PLAN.md, decides whether the live SHAs are the new canonical, then signs a commit updating state/polaris_restart/charter_sha_pin.txt. Hook will allow tool calls again on next invocation after reconciliation. Claude must NOT write the stamp file directly."
  }
}
EOF
    exit 0
fi

# Read active issue state. If active issue is in_progress, stamp acknowledges it.
ACTIVE='{}'
ACTIVE_FILE="${REPO_ROOT}/state/active_issue.json"
if [[ -f "$ACTIVE_FILE" ]]; then
    ACTIVE=$(cat "$ACTIVE_FILE")
fi

mkdir -p "$(dirname "$STAMP")"
{
    echo "session_started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "active_issue: $ACTIVE"
    echo "charter_sha: $LIVE_CHARTER"
    echo "plan_sha: $LIVE_PLAN"
} > "$STAMP"

exit 0
