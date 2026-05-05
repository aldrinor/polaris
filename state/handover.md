# DEPRECATED 2026-05-05 — see docs/handover.md

This file is the **OLD** handover (2026-05-01 dated, autoloop-era). It described the triangle-loop autoloop pattern where Claude was both architect and executor.

**That pattern was REVOKED 2026-05-05** per CHARTER §1 + polaris-restart Plan §9.1 after the 28-commits failure (`memory/failure_28_commits_2026_05_03.md`).

## Current handover

**Read `docs/handover.md`** for the issue-driven workflow that supersedes the autoloop.

Key changes (per plan §7.A LOCKED A2 + §7.B LOCKED B1):
- Claude writes code (briefs + diffs); Codex reviews two times per Issue (brief + diff)
- B1 pure auto-merge: GitHub auto-merge fires on Codex APPROVE; user reads `git log` in morning
- Per-Issue 5-artifact triple required (CI will enforce post-PR-D; pre-PR-D, Codex review enforces)
- Cannot start Issue N+1 until Issue N completed
- No autonomous task pickup — user assigns via TaskCreate
- `gh pr merge --admin` REVOKED from Claude (CHARTER §1)

See `state/polaris_restart/plan.md` (Codex APPROVE iter 4) + `state/polaris_restart/issue_breakdown.md` (Codex APPROVE iter 4) + `state/polaris_restart/cleanup_audit.md` (Codex APPROVE iter 21) for the canonical specs.

See `CLAUDE.md` §3.0 (issue-driven workflow) + §10 (session boot ritual) for binding rules.
