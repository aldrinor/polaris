# Restart Instructions — issue-driven workflow (post 2026-05-05 restart)

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely (project directives, especially §3.0 + §10).
2. Read `polaris-controls/CHARTER.md` and `PLAN.md` (admin-only sister repo nested under POLARIS at `C:\POLARIS\polaris-controls\` per PR-B2 relocation 2026-05-05; gitignored from POLARIS).
3. Verify BOTH `polaris-controls/CHARTER.md` AND `polaris-controls/PLAN.md` SHAs against `state/polaris_restart/charter_sha_pin.txt`. Either-file mismatch = HARD STOP per §3.1 step 0.
4. Read `state/active_issue.json` — if shows in_progress issue, resume ONLY that issue.
5. If no active issue, list TaskCreate tasks unblocked, present to user, wait for assignment.
6. State explicitly to user: active issue ID + current step + next action.

## Active state

**Restart plan:** `state/polaris_restart/plan.md` (Codex APPROVE iter 4 on 2026-05-05).
**Issue breakdown:** `state/polaris_restart/issue_breakdown.md` (Codex APPROVE iter 4, 134 issues).
**Cleanup audit:** `state/polaris_restart/cleanup_audit.md` (Codex APPROVE iter 21, 10-PR sequential schedule).
**Mission plan:** `docs/carney_delivery_plan_v6_2.md` (v6.2, Codex GREEN).

## Current PR sequence (where we are)

- PR-A1/A2/A3 (plan + issue_breakdown + cleanup_audit): COMPLETE 2026-05-05
- PR-B (DNA doc updates): in_progress (this session)
- PR-C (cleanup execution): blocked on USER ACTIONS 1+2
- PR-D (mechanical gates): blocked on PR-C
- PR-E (open Issues): blocked on PR-D
- PR-F (execute Issue #1): blocked on PR-E

**USER ACTIONS (user-side prerequisites):**
- USER ACTION 1: G2 signed commit on polaris-controls
- USER ACTION 2: §10.0 mechanical isolation live before Claude resumes Cleanup-PR-1

## Workflow rules (binding)

Per CLAUDE.md §3.0 + plan §7.A LOCKED A2 + §7.B LOCKED B1:

- **Claude:** writes code (briefs AND diffs). Author of `.codex/<issue_id>/brief.md` AND `.codex/<issue_id>/codex_diff.patch` AND `outputs/audits/<issue_id>/claude_audit.md`.
- **Codex:** reviews. Two APPROVE gates per Issue (brief + diff).
- **User:** spec owner + after-the-fact merge gate. Reads `git log` in morning (B1 pure auto-merge). Does NOT click merge per-PR. CI required check `polaris/codex-required` enforces.

**Per-Issue 5-artifact triple (CI will reject PR without these once PR-D installs the gate; pre-PR-D, Codex review enforces):**
- `.codex/<issue_id>/brief.md`
- `.codex/<issue_id>/codex_brief_verdict.txt` (APPROVE)
- `.codex/<issue_id>/codex_diff.patch`
- `.codex/<issue_id>/codex_diff_audit.txt` (APPROVE)
- `outputs/audits/<issue_id>/claude_audit.md`

**Forbidden:**
- `gh pr merge --admin` (REVOKED per CHARTER §1)
- Issue jump (start `I-X-NNN+1` before `I-X-NNN` merged)
- Autonomous task pickup (user assigns via TaskCreate; Claude doesn't pick)
- "While we're at it" polish in same PR
- STATUS blocks / recap text between work items

## Halt conditions (each emits `state/halt_<utc>_<reason>.md`)

- canonical pin SHA mismatch
- CHARTER.md OR PLAN.md SHA pin mismatch
- issue jump attempt
- PR opened with missing artifact triple
- Codex unavailable >1h
- 2-cycle repeated root cause
- 200-LOC PR cap exceeded
- 3+ PRs queued for user in 24h (reviewer fatigue)

## Critical memory entries

- `polaris_restart_2026_05_05.md` — cage tightened, role split, per-Issue triple
- `forbidden_admin_merge.md` — `gh pr merge --admin` REVOKED
- `feedback_codex_iteration_5cap_2026_05_06.md` — **CRITICAL CURRENT (2026-05-06).** 5-iter hard cap per Codex review per CLAUDE.md §8.3.1; force-APPROVE at iter 5 if still REQUEST_CHANGES. SUPERSEDES `feedback_codex_iteration_no_cap_no_toothpaste.md` (2026-05-05; the no-cap rule is REVOKED).
- `failure_28_commits_2026_05_03.md` — DO NOT REPEAT. The 28-commits failure is what the cage prevents.

## Old auto-loop pattern (REVOKED 2026-05-05)

The previous "triangle loop" + auto-resume + `gh pr merge --admin` pattern is REVOKED. See `state/handover.md` (deprecation pointer) and `failure_28_commits_2026_05_03.md` for why.

If a future session reads this and sees auto-loop framing in `memory/autoloop_v2_audit_cross_review.md` or `memory/autoloop_beat_tier1_mandate.md`, those memories are HISTORICAL. Current binding rule = issue-driven workflow per CLAUDE.md §3.0.
