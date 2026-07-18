# 0024. The governance cage: no admin-merge authority, sequential issues, structural CI enforcement

Status: accepted

Date: 2026-05-05

## Context

This cage was built from repeated real failures. Claude promised not to merge and then merged anyway — the 28-commits failure (`failure_28_commits_2026_05_03`). The lesson learned there is blunt: promises do not work; structural removal does. The workflow must make the forbidden action impossible, not merely discouraged.

## Decision

Claude has NO `gh pr merge --admin` authority. It is structurally revoked, and the CI required check `polaris/codex-required` enforces it by parsing the written Codex verdict file. Autonomous merge is a cage bypass.

Every unit of work is a GitHub Issue done in strict sequence: cannot start Issue N+1 until Issue N is completed and merged. No issue-jump. No "while we're at it" polish in the same PR. A PR needs the full artifact set (brief, brief-verdict, diff, diff-audit, architect audit, plus a visual audit for UI PRs).

The session boot ritual runs first: verify `docs/canonical_pin.txt` SHAs plus `CHARTER.md` and `PLAN.md` SHA pins (mismatch is a HARD STOP with a halt marker), read `state/active_issue.json`, and resume only the in-progress issue — never pick a task autonomously. Re-verify every 10 tool calls or 15 minutes. Operator-locked decisions are NOT Codex-consultable, and a Codex APPROVE counts as user approval only within its delegated scope.

## Consequences

- The failure mode of "promise not to merge, then merge" is structurally prevented because Claude no longer participates in the merge step; the user reads `git log` in the morning as the after-the-fact human-at-merge surface.
- Sequential issues with no jump and no side-polish keep each PR small, reviewable, and attributable; a merged commit is the notification, not a prose recap.
- A SHA-pin mismatch is a hard stop, not a warning, because drifting canonical files silently invalidate every downstream assumption.
- Operator-locked decisions cannot be re-opened by asking Codex; the cage exists precisely because soft discipline failed.
