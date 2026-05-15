# Restart Instructions — Carney demo readiness execution (updated 2026-05-15)

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely (§3.0 issue-driven + §10 boot ritual).
2. Read `polaris-controls/CHARTER.md` and `PLAN.md`; verify SHAs against `state/polaris_restart/charter_sha_pin.txt`. Mismatch = HARD STOP.
3. Read this file + `state/carney_demo_execution_plan_2026_05_15.md` (the Codex-approved execution plan) + `docs/polaris_locked_scope.md` (the scope lock).
4. State to user: active issue + current step + next action.

## CURRENT WORKSTREAM (resume point 2026-05-15)

**Carney demo readiness — execution plan v2 (Codex-approved).** Plan:
`state/carney_demo_execution_plan_2026_05_15.md`. 9 phases, closing the gap
between "GitHub issues completed" and "coherent demo-ready product."

**Locked scope:** `docs/polaris_locked_scope.md` — V4 Pro generator + Gemma 4
31B evaluator, 1 concurrent; Canadian sovereign GPU only; v6 stack
architecture; BPEI name banned; single-venue June demo.

**20 readiness GitHub issues created 2026-05-15:** #497-#516 (`I-rdy-001`
through `I-rdy-020`). Map to plan phases 0A/1/0B/3/L/4/5.

**Per-task loop (operator-directed 2026-05-15):** GH issue → Claude builds →
smoke test → Codex review at highest standard → iterate to APPROVE or 5-iter
cap → close issue → next.

### Progress

- **I-rdy-001 (#497) — DONE.** `docs/polaris_locked_scope.md` written; Codex
  review iter 1 REQUEST_CHANGES (1 P1: OVH over-claim; 2 P2) → all fixed →
  iter 2 APPROVE. Artifacts in `.codex/I-rdy-001/`.
- **NEXT: commit I-rdy-001 + close #497, then I-rdy-002 (#498)** — Phase 1:
  verify every P0/P1 gap in `state/carney_readiness_gaps_2026_05_15.md`
  against the live deployed system (SSH the orchestrator, drive the UI),
  marking each CONFIRMED-BROKEN vs WORKS-UNTESTED.

### Dependency order for the readiness backlog

0A done → 1 (#498) → 0B (#499) → 3.1-3.11 (#500-510) → assemble (#510) →
Workstream L (#511-513, parallel) → 4 (#514) → 5 (#515-516).
Phase 6 GPU = #90 + operator. Phase 7-9 = #200-206 + #473 (GPU-blocked).

## GPU blocker (operator-tracked)

Canadian sovereign GPU not secured. Vexxhost (Support Hub) + ISAIC
(`info@isaic.ca`) outreach sent 2026-05-15. Hard decision gate **2026-05-24**.
OVH Canada has NO Hopper GPU — dead path. See
`state/canada_gpu_research_2026_05_15.md`.

## Live infrastructure

- Orchestrator (CPU box): OVH BHS5, `polarisresearch.ca` / `51.79.90.35`,
  v6 stack (redis+api+worker+webui) all healthy. See `state/ovh_infra.md`.
- Generation path inert (no `OPENROUTER_API_KEY`, no GPU) — returns
  `400 completion_backend_unavailable` honestly.

## Workflow rules (binding — per CLAUDE.md §3.0)

- Claude writes briefs + diffs; Codex reviews (5-iter cap §8.3.1); Claude has
  NO admin-merge authority; CI `polaris/codex-required` gates.
- Per-issue artifacts under `.codex/<issue_id>/`.
- Halt conditions: canonical/CHARTER pin mismatch, issue jump, missing
  artifact triple, Codex unavailable >1h, 2-cycle repeated root cause,
  200-LOC cap, 3+ PRs queued for user in 24h.

## Key state docs (2026-05-15)

- `state/carney_demo_execution_plan_2026_05_15.md` — the plan (Codex-approved)
- `state/carney_readiness_gaps_2026_05_15.md` — the gap register
- `state/canada_gpu_research_2026_05_15.md` — GPU research
- `state/gpu_vendor_outreach_2026_05_15.md` — Vexxhost/ISAIC emails
- `state/ovh_infra.md` — orchestrator deploy record
- `docs/polaris_locked_scope.md` — the scope lock
