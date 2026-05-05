# DEPRECATED 2026-05-05 — see state/polaris_restart/

This file documented the May-4 auto-merged slice 005 mission status. **That work is being reverted under ROAD B** per `state/polaris_restart/plan.md` §7.D (reset to commit `365f334`).

**Why deprecated:** the May-4 work was produced via `gh pr merge --admin` from Claude's account in violation of CHARTER §1 (the 28-commits failure pattern, see `memory/failure_28_commits_2026_05_03.md`). The actual code is preserved in tag `pre_restart_2026_05_05` for forensic recovery but does NOT reflect the canonical state.

## Current canonical sources

- **Mission plan:** `docs/carney_delivery_plan_v6_2.md` (v6.2, Codex GREEN)
- **Restart plan:** `state/polaris_restart/plan.md` (Codex APPROVE iter 4 on 2026-05-05)
- **Issue breakdown:** `state/polaris_restart/issue_breakdown.md` (Codex APPROVE iter 4, 134 issues)
- **Cleanup audit:** `state/polaris_restart/cleanup_audit.md` (Codex APPROVE iter 21)
- **Handover:** `docs/handover.md` (issue-driven workflow)

## Restart sequence

PR-A1/A2/A3: Codex APPROVE'd. PR-B (DNA doc updates): in_progress 2026-05-05 night. PR-C..PR-F: blocked on user-side prerequisites + dependency chain.

See `state/restart_instructions.md` for full status.
