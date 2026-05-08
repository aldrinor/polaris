# Codex Brief Review — I-f13-004 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (existing tests break):** adding `2026-05-15` to the registry would shift `PIN_DATES[PIN_DATES.length - 1]` from `2026-04-30` to `2026-05-15`, breaking `pin_replay.spec.ts` (asserts initial B=2026-04-30, B pass-rate 85%, delta +13%) and `pin_replay_diff.spec.ts` (asserts delta +13%). Iter-2 plan: **pin the page default explicitly** — change `web/app/pin_replay/page.tsx` line 77 from `useState(PIN_DATES[PIN_DATES.length - 1])` to `useState("2026-04-30")`. Stable initial state regardless of registry growth; new entry remains user-selectable via dropdown. Single-line change, zero existing-test edits.
- **P2 fix (avoid double-attribution muddiness):** make `2026-05-15` pass_rate=0.83 (drop from 0.85 = 2pp, under 5pp threshold). Only sentence count alerts; retraction attribution applies cleanly to a single metric.
- **P2 fix (attribution scope):** `getRetractionContext(a, b)` returns IDs in `b.retracted_source_ids` but NOT in `a.retracted_source_ids` — newly attributed retractions between A and B only. With 2026-04-30.retracted=["demo-clin-002"] and 2026-05-15.retracted=["demo-clin-002","demo-clin-005"], only "demo-clin-005" attributes for the A=2026-04-30→B=2026-05-15 comparison.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Issue:** I-f13-004 — F13 adversarial: source retraction during replay. Scope: "retracted source mid-replay → handled". Acceptance: "test". LOC estimate 90.
- **Background:** PinSnapshot today carries aggregate metrics (pass_rate, sentence count). For the retraction adversarial: between snapshot A and snapshot B, the source pool changes (a source is retracted post-A, pre-B). The verified_sentence_count drops because retracted-source sentences are now invalid. The replay UI must show that the drop is *due to retraction*, not random regression.
- **Honest framing per CLAUDE.md §9.4:** ship a PinSnapshot field `retracted_source_ids: string[]` (NEW) that tracks sources retracted between A and B; render an inline note when retraction explains the drop. This is substrate-only — no live retraction monitoring yet.

## Plan

### Frontend

1. Extend `web/lib/pin_replay_demo.ts`:
   - Add `retracted_source_ids?: string[]` to `PinSnapshot` interface (optional, default `[]` semantics in helpers).
   - Update `2026-04-30` snapshot: `retracted_source_ids = ["demo-clin-002"]` (one source retracted between Jan and April).
   - Add 4th pin date `2026-05-15`:
     - pass_rate: 0.83 (drop from 0.85 = 2pp, **under** 5pp threshold — does NOT trigger pass_rate alert)
     - verified_sentence_count: 17 (drop from 23 = 6, **over** 3-sentence threshold — DOES trigger sentence alert)
     - section_count_kept: 4, section_count_dropped: 1
     - verdict: "success"
     - query: same canonical query
     - retracted_source_ids: ["demo-clin-002", "demo-clin-005"]

2. Extend `web/lib/pin_regression.ts`:
   - Add helper `getRetractionContext(a: PinSnapshot, b: PinSnapshot): { newly_retracted: string[] }` — returns IDs in `b.retracted_source_ids` but NOT in `a.retracted_source_ids`. Defensive: treat `undefined` as `[]`.
   - When `RegressionAlert` for `verified_sentence_count` AND `newly_retracted.length > 0`, the alert payload gets `attributed_to_retraction: string[]`. (Pass-rate alerts are NOT attributed to retraction in this issue's scope.)

3. Update `web/app/pin_replay/page.tsx`:
   - **P1 fix:** change line 77 from `useState(PIN_DATES[PIN_DATES.length - 1])` to `useState("2026-04-30")`. Pins default B; existing tests unchanged.
   - Compute `retraction_context = getRetractionContext(snap_a, snap_b)`; pass into alert payload (e.g., merge into the matching `verified_sentence_count` alert).
   - When an alert has `attributed_to_retraction`, render an inline `(attributed to retraction of: <ids>)` note in the alert `<li>`.
   - Add `data-testid="regression-retraction-attribution"` on the inline note span.

### Playwright

4. `web/tests/e2e/pin_retraction_handled.spec.ts` (NEW):
   - Visit `/pin_replay`.
   - `selectOption("2026-04-30")` for A, `selectOption("2026-05-15")` for B (adversarial scenario).
   - Assert `regression-alert` visible (sentence count drop fires).
   - Assert `regression-alert-pass_rate` is NOT visible (2pp drop under threshold; pass-rate alert should NOT exist).
   - Assert `regression-alert-verified_sentence_count` visible.
   - Assert `regression-retraction-attribution` text contains "demo-clin-005" (newly retracted between A and B; "demo-clin-002" carries over from A and is NOT attributed).

### Compatibility

5. Existing tests `pin_replay.spec.ts` + `pin_replay_diff.spec.ts` keep passing because the page default-B is now pinned to `2026-04-30`. Verified by line-by-line read of both spec files — every assertion (initial B-date, B pass-rate 85%, delta +13%, sentence delta) holds with the pinned default.

## Risks for Codex Red-Team

1. **Existing tests:** `pin_regression_alert.spec.ts` (I-f13-003) explicitly selects 2026-04-30 and 2026-01-15 — unaffected. `pin_replay.spec.ts` + `pin_replay_diff.spec.ts` rely on default initial B; pinned to "2026-04-30" so unchanged.
2. **Optional field:** `retracted_source_ids` is `string[] | undefined`; defensive default `[]` in helper. JSON serialization stable (optional missing field omitted).
3. **Pass-rate single-attribution choice:** scope limits attribution to sentence-count alerts only — keeps semantics tight; pass-rate retraction-attribution is a follow-up.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~30 LOC registry extension (incl. new pin date) + ~25 LOC regression helper extension + ~25 LOC page integration + ~30 LOC spec = ~110. Within budget.

## Acceptance criteria

1. `PinSnapshot` gains optional `retracted_source_ids?: string[]`.
2. New `getRetractionContext(a, b)` helper returns IDs newly retracted in B (in B but not A).
3. Sentence-count alert rendering includes inline retraction attribution when newly-retracted sources exist.
4. 4th pin date `2026-05-15` (pass_rate=0.83, sentence_count=17, retracted=["demo-clin-002","demo-clin-005"]) demonstrates the scenario.
5. Page default-B explicitly pinned to "2026-04-30" so existing tests don't break.
6. New Playwright spec asserts retraction-attributed alert renders correctly with "demo-clin-005" attributed (NOT "demo-clin-002" carried over).
7. Existing `pin_replay.spec.ts` + `pin_replay_diff.spec.ts` keep passing (initial defaults stable).
8. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-8.

**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
