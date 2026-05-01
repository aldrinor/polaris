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

2026-05-01: substrate audit completed → v6.1 plan drafted (substrate-aware) → Codex YELLOW with 8 surgical redlines → all applied → Codex YELLOW on line-214 contradiction → fixed → Codex GREEN. Triangle loop added (v6.2). Plan canonical. Todo and handover updated.

**Phase 0 progress (v6.2 execution started, 2026-05-01):**
- ✅ Task 0.1 — `docs/blockers.md` (10 blockers register: 6 CONFIRMED, 4 ACTION-PENDING with dates+owners)
- ✅ Task 0.2 — `docs/agent_architecture.md` (Local+Global Verifier; no MiroThinker fork; 9 existing modules mapped)
- ⏳ Task 0.4 — frontend agent (background ID `aab25b18`) scaffolded `web/`: Next.js 16.2.4 + React 19.2.4 + shadcn 4.6 (MIT) + Tailwind v4 + TypeScript 5 + ESLint 9 + Prettier
- ⏳ Task 0.5 — `docs/backend_modernization.md` (FastAPI 0.136 + Pydantic v2.11 + Dramatiq 2.1 + 8-scenario acceptance test); code stubs pending
- ⏳ Task 0.8 — `docs/gemma_4_verification.md` (model card + license scan + vLLM recipe). **Errata E-1**: license is Apache 2.0 + Gemma Use Policy, LOW severity for Carney scope
- ⏳ Task 0.10 — `docs/opentelemetry_genai.md` (OTEL pin). **Errata E-2**: env var is `gen_ai_latest_experimental` (NOT `gen_ai_dev`); semconv baseline 1.36.0+ (NOT 1.30.0-dev). Plan amended with errata section.
- ⛔ Tasks 0.3, 0.6, 0.7, 0.9 — pending user $ commitment / downstream dependency

**Next action on resume:**
1. Check frontend agent (background ID `aab25b18`) completion notification — it was running at end of session
2. If complete: triangle-loop Task 0.4 (Claude self-audit + Codex audit + cross-review)
3. Resume Task 0.5 code-side: write `requirements-v6.txt` + FastAPI router skeleton + Dramatiq acceptance test stub
4. Surface Tasks 0.3 + 0.6 + 0.9 to user for $ commitment (per `docs/blockers.md` action-pending dates)
