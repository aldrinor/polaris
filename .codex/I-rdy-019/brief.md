# Codex BRIEF review — I-rdy-019 / GH #515: author the 22-type test matrix against the product journey

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

This is a **BRIEF review** — verify the acceptance criteria + scoping are
correct BEFORE the doc is authored. The deliverable of #515 is a single
markdown document (no code). You are NOT reviewing a diff yet.

## 1. The issue (GH #515 / I-rdy-019)

> Phase 5a (overlaps Phase 3). Author the Carney-plan 22 test types against
> the real product journey, not harness pages.
> Acceptance: matrix authored and committed; Codex APPROVE.
> Depends on: I-rdy-007.

## 2. Proposed deliverable

A new doc: **`docs/carney_handover/test_matrix.md`** — the carney-plan
testing matrix instantiated against the **real (non-harness) product
journey**, so #516 (I-rdy-020, "run the test matrix") has a concrete,
journey-grounded checklist to execute.

### 2.1 The test types (source of truth)

`docs/carney_delivery_plan_v6_2.md` lines 314-339 — "Testing matrix —
exhaustive per feature" — is a 24-row table. The issue says "22 test
types." **Proposed reconciliation:** the matrix doc covers all 24 rows of
the plan table verbatim as the test-type axis, with a note that the issue's
"22" predates two rows added in a later plan revision (`Codex code review`
and `Fixture governance + flake budget` are process/infra gates, not
product test types — if a strict 22 is required, those two are the
excludable pair). Enumerated test types:

1 Unit · 2 Integration · 3 Artifact contract/schema versioning · 4 Visual
regression · 5 E2E happy path · 6 E2E adversarial · 7 Cross-browser ·
8 Accessibility · 9 Multi-tab safety · 10 Network resilience · 11 Streaming
SSE ordering/backpressure · 12 Cancellation/resume · 13 Performance ·
14 Security · 15 Tenant isolation + data deletion · 16 Privacy/log
redaction · 17 Sovereignty (data-classification routing) · 18 Migration ·
19 LLM quality gates · 20 Semantic chart correctness · 21 Anti-sycophancy ·
22 Codex code review · 23 Layer-3 walkthrough · 24 Fixture governance.

### 2.2 The real product journey (the OTHER axis)

Grounded in the actual deployed `web/app/` routes — **real journey routes
only, harness pages explicitly excluded** (per the issue and the
`feedback_plan_from_running_system` standing lesson). Inventory: 33 page
routes — **15 real product routes, 18 harness/diagnostic**. Real journey
stages:

- **J1 Sign-in** — `/sign-in`
- **J2 Home / template discovery** — `/` (the real product entry surface;
  `web/app/page.tsx` renders the template-selection shell and links the
  chosen template into `/intake`)
- **J3 Scope intake + disambiguation** — `/intake`
- **J4 Retrieval** — `/retrieval`
- **J5 Generation** — `/generation`
- **J6 Live audit run (SSE)** — `/audit_live`
- **J7 Run view + graph** — `/runs/[runId]`, `/runs/[runId]/graph`
- **J8 Report inspection (click-through)** — `/inspector/[runId]`
- **J9 Document upload + grounding** — `/upload`
- **J10 Operator dashboard** — `/dashboard`
- **J11 Supporting surfaces** — `/contracts`, `/memory`, `/pin_replay`,
  `/benchmark`

**Excluded as harness/diagnostic pages** (named explicitly in the doc so
#516 does not test them as product — 18 routes): `/sse` (implemented as a
harness — `web/app/sse/page.tsx` exports `SSETestHarnessPage`,
`web/app/sse/_harness.tsx` renders `data-testid="sse-harness"`),
`/(test_harness)/disambiguation_modal_preview`, `/charts_test` + 4
subroutes (5 total), `/sentence_hover_test` + 10 subroutes (11 total).

(iter-1 P1-001 addressed: `/` added as the J2 real entry surface; `/sse`
reclassified from real journey to harness/diagnostic.)

### 2.3 Doc structure

Per test type (24 sections): the plan's Tool + Pass-criteria, then the
concrete journey stages it applies to (`J1..J11` + route), the specific
check at each, and an explicit "N/A — <reason>" for stages it does not
apply to (e.g. test type 11 SSE applies to J6 only). A leading journey map
+ a coverage summary (which J-stages each type touches).

## 3. The I-rdy-007 (#503) dependency — scoping decision (needs your APPROVE)

#515 declares "Depends on: I-rdy-007" (#503 "define the live-run artifact
contract"). **#503 is currently OPEN** (its own dependency #498 also open).

**Proposed scoping:** #515 is authorable now without #503 closed, because
the matrix is *test-type × journey-stage × check/pass-criteria* — it does
not need the artifact contract's field-level schema. The one coupling point
is test type 3 (Artifact contract / schema versioning): that row references
the live-run artifact contract. Proposed handling — that row's cells state
the check at the contract level ("the live-run artifact validates against
the contract defined in I-rdy-007; version migration tested") and carry an
explicit `forward-ref: I-rdy-007 (#503)` marker rather than inventing a
schema. This keeps #515 a standalone authored matrix; #516 binds the
concrete schema once #503 lands. **Confirm this scoping is acceptable, or
direct that #515 must wait on #503.**

## 4. Acceptance criteria (verify these are correct + complete)

1. `docs/carney_handover/test_matrix.md` authored + committed.
2. All 24 plan test types present, each with the plan's Tool + Pass-criteria
   carried faithfully (no silent drop, no invented criteria).
3. Every real journey stage J1-J11 mapped to a real `web/app/` route;
   all 18 harness/diagnostic routes explicitly listed as excluded.
4. Each test-type × journey-stage cell is concrete (what to verify) or an
   explicit reasoned "N/A" — no blank cells.
5. The I-rdy-007 coupling (test type 3) carried as a forward-ref, not faked.
6. Doc-only: no code, no test files, no production-path change (#516 runs
   the matrix; #515 only authors it).
7. snake_case filename; LAW II honesty (no overclaim that any test has been
   *run* — this issue authors the matrix, it does not execute it).

## 5. Files I have ALSO checked and they are clean / relevant

- `docs/carney_delivery_plan_v6_2.md:310-339` — the test-type source table
  (24 rows); `:76-164` — the 15 feature areas with per-feature test notes.
- `web/app/**/page.tsx` — full route inventory (33 routes; 18 harness, 15
  real-journey) — the journey axis is grounded in this, not in docs.
- `docs/carney_handover/` — existing handover docs (runbook.md,
  rehearsal_procedure.md, rehearsal_evidence.md, 5min_video_script.md);
  `test_matrix.md` is a new sibling, no collision.
- #503 (I-rdy-007) + #498 (I-rdy-003) — dependency chain, both OPEN
  (scoping in §3).
- No existing `test_matrix.md` / `.codex/I-rdy-019/` — greenfield.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
