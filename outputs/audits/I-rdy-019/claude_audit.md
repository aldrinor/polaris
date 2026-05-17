# Claude architect audit — I-rdy-019 / GH #515

**Branch:** `bot/I-rdy-019-test-matrix`
**Commits:** `b2ba1350` (author) + `efa77204` (diff iter-1) + `b02ff164` (diff iter-2 P1-003) + `56830c8b` (diff iter-3 P1-004 tenant-isolation J6 + P2-005 cancellation gap).
**Canonical diff:** `.codex/I-rdy-019/codex_diff.patch` — sha256 `17dd8d744c0b83a14adccd0c8e39dda63d82ac63514eaa3fbd273bf3672818e9`
**Diff:** 1 file, +374 (`docs/carney_handover/test_matrix.md`).

## Codex diff-review iter-1 findings — all addressed

Diff iter 1 returned 2 P1 + 4 P2 (journey-content accuracy). Each was
verified against the actual `web/app/` component code and corrected:
`/dashboard` re-described as "Start a research run"; Security applied to
J4/J5/J10 (own input forms); SSE applied to J7 (`subscribeToRun`); Artifact
contract applied to J5/J7 (bundle build/export); a concrete J2 Unit check
added; Performance applied to all UI stages (Core Web Vitals). The §4 grid
was updated to match. See `.codex/I-rdy-019/diff_brief.md` §0.1.

## What #515 delivers (Carney readiness Phase 5a)

`docs/carney_handover/test_matrix.md` — the carney-plan testing matrix
(`docs/carney_delivery_plan_v6_2.md:314-339`, 24 test types) instantiated
against the **real deployed product journey** (the 15 non-harness
`web/app/` routes, journey stages J1-J11), with the 18 harness/diagnostic
routes explicitly excluded. Per test type: the plan's Tool + pass criteria
carried verbatim, the concrete check at each applicable journey stage, a
reasoned N/A for every non-applicable stage, plus a 24×11 coverage grid.
#516 (I-rdy-020) executes this matrix.

## Self-audit against the brief's acceptance criteria (line-by-line)

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | `docs/carney_handover/test_matrix.md` authored + committed | VERIFIED | committed `b2ba1350`; 331 lines. |
| 2 | All 24 plan test types present, plan Tool + pass-criteria carried faithfully | VERIFIED | §3 has all 24 numbered rows; each carries the plan's exact Tool + Pass-criteria text from v6_2:316-339. No row dropped, no criterion invented. |
| 3 | Every real journey stage J1-J11 mapped to a real `web/app/` route; 18 harness routes listed excluded | VERIFIED | §1 maps J1-J11 → 15 routes; all 11 verified to exist on disk (`web/app/.../page.tsx`). §2 lists all 18 excluded harness/diagnostic routes. 15+18=33 = the full inventory. |
| 4 | Each test-type × journey-stage cell concrete OR reasoned N/A — no blank cells | VERIFIED | every §3 block has an "Applies to" (concrete check per stage) + an "N/A" line with a reason; §4 grid has no blank cell (`✓`/`—`/`≈`). |
| 5 | I-rdy-007 coupling (test type 3) carried as forward-ref, not faked | VERIFIED | row 3 + the grid both tag `forward-ref: I-rdy-007 (#503)`; §5 item 2 restates it; no invented schema. |
| 6 | Doc-only — no code, no test files, no production-path change | VERIFIED | diff is 1 file, a `.md` doc under `docs/carney_handover/`. |
| 7 | snake_case filename; LAW II honesty (no claim a test was run) | VERIFIED | `test_matrix.md` is snake_case; the header states explicitly "the matrix is *authored*, not *run* … no test … has been executed by #515". |

## Codex brief-review P2 applied

I-rdy-019-P2-001 (iter-2 P2): the excluded harness route is listed by its
**deployed URL** `/disambiguation_modal_preview`, with the route-group
filesystem path `web/app/(test_harness)/...` only in parentheses (§2). The
`(test_harness)` route group is not a URL segment — applied as Codex
directed.

## Risk assessment

- Doc-only; no production code path, no test file, no import. LOW.
- The `forward-ref: I-rdy-007 (#503)` on test type 3 is honest — #503 is
  OPEN; the row states checks at the contract level and explicitly defers
  the field-level schema to #503. #516 binds it once #503 lands. LOW.
- Test-type count: the issue says "22", the plan table has 24; the doc
  carries all 24 and documents the 22-vs-24 reconciliation (rows 22 + 24
  are the excludable process/infra gates). No silent drop. NONE.

## Codex diff-review outcome

Codex diff review: **APPROVE at iter 4** (0 P0, 0 P1; `convergence_call:
accept_remaining`, no blockers). Iteration progression — iter 1 (2 P1 +
4 P2) → iter 2 (1 P1) → iter 3 (1 P1 + 1 P2) → iter 4 (APPROVE). Every P1
was a journey-content accuracy issue verified against `web/app/` and
corrected (security input surfaces, SSE/`/runs` wiring, `/audit_live` as a
non-production test surface, tenant-isolation of `/stream/<runId>`,
cancellation as an honest gap). The 4 non-blocking iter-4 P2s are captured
as follow-up issue **#558**.

**Verdict: APPROVE'd — ready to ship.**
