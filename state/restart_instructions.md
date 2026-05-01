# Restart Instructions — 2026-05-01 (v6.2 Carney Delivery)

## Active state

**Canonical plan:** `docs/carney_delivery_plan_FINAL.md` (v6.2, Codex GREEN 2026-05-01)
**Active phase:** Phase 0 — Foundation (May 1-12)
**Current task:** Phase 0 Task 0.1
**Triangle loop protocol:** `memory/autoloop_v2_audit_cross_review.md`
**Codex Red-Team Checklist:** `.codex/codex_red_team_checklist.md`

## Resume sequence

1. Read `CLAUDE.md` completely (project directives)
2. Read `state/handover.md` (this session's context)
3. Read `docs/carney_delivery_plan_FINAL.md` (the canonical v6.2 plan)
4. Read `docs/substrate_audit_2026-05-01.md` (what's already built)
5. Read `docs/todo_list.md` (current task list)
6. Read `docs/task_acceptance_matrix.yaml` (Phase 0 GREEN criteria)
7. Check `logs/session_log.md` for last session's decisions
8. Find current task ID in todo_list.md (in progress or next pending)
9. Read its brief at `.codex/task_<id>_review_brief.md` if exists; else write one
10. Apply triangle loop per `state/handover.md` § "The triangle loop"

## Auto-loop status

User directive 2026-05-01: "make sure Claude and Codex continue working hard until full completion of the entire v6." Auto-loop is LIVE.

Halt conditions (only):
- 24h wall-clock per task exceeded
- $100/task spend cap exceeded
- Dimension regression detected
- Same root cause for 2 cycles in a row
- Cross-review-integrity halt (Codex won't engage with concrete evidence)
- Same P1 finding twice across cycles
- Acceptance criterion changed mid-task

If halt triggered: surface to user, wait for direction. Otherwise: continue.

## Where to find things

- Plan: `docs/carney_delivery_plan_FINAL.md`
- Substrate audit: `docs/substrate_audit_2026-05-01.md`
- Acceptance matrix: `docs/task_acceptance_matrix.yaml`
- Codex Red-Team Checklist: `.codex/codex_red_team_checklist.md`
- Codex review briefs (history): `.codex/carney_delivery_plan_v6*.md`
- Triangle loop runbook: `memory/autoloop_v2_audit_cross_review.md`
- Session log: `logs/session_log.md`
- Bug log: `logs/bug_log.md`
- Memory index: `memory/MEMORY.md` at `C:\Users\msn\.claude\projects\C--POLARIS\memory\`

## What just happened (last session)

2026-05-01: substrate audit completed → v6.1 plan drafted (substrate-aware) → Codex YELLOW with 8 surgical redlines → all applied → Codex YELLOW on line-214 contradiction → fixed → Codex GREEN. Triangle loop added (v6.2). Plan canonical. Todo and handover updated. Phase 0 Task 0.1 ready to start under triangle loop.
