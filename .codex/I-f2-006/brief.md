# Codex Brief Review — I-f2-006 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-006 — F2 adversarial: tirzepatide → no false disambiguation
**Phase:** 1 / **Feature:** F2 (disambiguation modal)
**LOC budget:** 80 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 #1 (Test 2 toothless — empty-cards regression would pass):** ADDRESSED. Both tests now assert `[data-slot="disambiguation-modal"]` is hidden (the modal Popup itself), not just `disambiguation-cluster-0`. An empty-cards regression that opened the modal with zero cards would now fail. Test 2 also pivots to `is_ambiguous=false, clusters.length=2` (contradictory data isolating the `is_ambiguous` guard specifically).

**P1 #2 (Tests don't prove intended path ran):** ADDRESSED. Both tests add `intakeCalls`, `disambigCalls` counters. Test 1 asserts `intakeCalls === 1, disambigCalls === 0`. Test 2 asserts `intakeCalls === 1, disambigCalls === 1`. Both wait for `data-testid="scope-decision-view"` (proxies that intake response was processed by the form).

## Mission

Add a Playwright adversarial test asserting the disambiguation modal does NOT render for an unambiguous query (e.g. "tirzepatide" — a single primary entity). Per Carney v6.2 §F2 the modal should only fire when ≥2 distinct entity clusters are detected; this Issue is the negative-case guard.

Per breakdown:
- **Scope:** single primary entity → no modal
- **Acceptance:** Playwright zero modal renders for unambiguous queries

## Substrate (HONEST)

- I-f2-005 just merged: intake page now wires `runDisambiguation()` after `runIntake()` when `decision.needs_disambiguation && candidate_snippets.length > 0`. Modal opens only when `is_ambiguous=true && clusters.length > 1` (Codex iter-2 P2 fix on I-f2-005 brief).
- `web/tests/e2e/intake_disambiguation.spec.ts` ships the positive BPEI flow.
- This Issue ships the negative tirzepatide flow.
- `intake_form.tsx` triple-guards the modal: `needs_disambiguation`, `is_ambiguous`, `clusters.length > 1`. Three negative-case branches we can exercise:
  1. Backend says `needs_disambiguation=false` → no /api/disambiguation call → no modal.
  2. Backend says `needs_disambiguation=true` but `/api/disambiguation` returns `is_ambiguous=false` → modal NOT opened.
  3. Backend says `needs_disambiguation=true` and `is_ambiguous=true` BUT `clusters.length <= 1` (e.g. 1 cluster after deduplication) → modal NOT opened.

This Issue exercises path #1 (the cleanest negative case representative of "tirzepatide" — backend correctly identifies it as unambiguous and never asks the frontend to disambiguate). Paths #2 and #3 are defensive double-guards covered implicitly by the trigger logic; we add a P2-level second test for path #2 to harden against backend-flag-leak regressions.

## Acceptance criteria (binding)

1. **`web/tests/e2e/intake_disambiguation_negative.spec.ts`** (NEW): Playwright file with 2 tests.

   - **Test 1: `tirzepatide single entity → no modal`** (path #1 — backend says no):
     - `let intakeCalls = 0; let disambigCalls = 0;`
     - Mock `**/api/intake` (intakeCalls++; route.fulfill returns `decision.status="in_scope"`, `decision.needs_disambiguation=false`, NO `candidate_snippets`).
     - Mock `**/api/disambiguation` (disambigCalls++; route.abort()) — if it ever fires it's a bug AND the counter rises.
     - Test flow:
       1. `goto /intake`.
       2. Fill `intake-question-input` with "Does tirzepatide reduce A1c in adults with type 2 diabetes?".
       3. Click `intake-submit`.
       4. `await expect(page.getByTestId("scope-decision-view")).toBeVisible()` — proxies that intake response was processed.
       5. `await page.waitForTimeout(200)` — grace window for any deferred /api/disambiguation call.
       6. `await expect(page.locator('[data-slot="disambiguation-modal"]')).toBeHidden()` — modal Popup is the source of truth, NOT `disambiguation-cluster-0` (catches empty-cards regression per Codex iter-1 P1 #1).
       7. `expect(intakeCalls).toBe(1); expect(disambigCalls).toBe(0);` (Codex iter-1 P1 #2 fix.)

   - **Test 2: `needs_disambiguation=true but is_ambiguous=false → no modal`** (path #2 — `is_ambiguous` guard isolation):
     - `let intakeCalls = 0; let disambigCalls = 0;`
     - Mock /api/intake (intakeCalls++; returns `needs_disambiguation=true` + 2 candidate_snippets).
     - Mock /api/disambiguation (disambigCalls++; returns `is_ambiguous=false, num_clusters=2, clusters=[{cluster_id:0, label:"x", sample_snippets:["..."]}, {cluster_id:1, label:"y", sample_snippets:["..."]}]`) — contradictory data (2 clusters but is_ambiguous=false) isolates the `is_ambiguous` guard.
     - Test flow steps 1-6 same as Test 1 (with the question "Does tirzepatide reduce A1c in adults with type 2 diabetes?").
     - `expect(intakeCalls).toBe(1); expect(disambigCalls).toBe(1);` — proves /api/disambiguation WAS called yet modal stayed closed.

   - LOC: ~95 pre-Prettier (Codex iter-1 P1 #1+#2 fixes added counters + popup-locator assertions).

## Planned diff shape

```
web/tests/e2e/intake_disambiguation_negative.spec.ts                NEW +95
```

LOC: +95 net pre-Prettier. Prettier reflow target: ≤140. CHARTER §1 200-cap easily satisfied.

## Out of scope (deferred per breakdown)

- F2 edge cases (French / PDF drop) → I-f2-007.
- Evaluator walkthrough → I-f2-008.

## Risks for Codex Red-Team

1. **Negative-test toothlessness.** "Modal not visible" is hard to assert robustly because the modal NEVER opening means there's no event to wait for. Mitigation: `route.abort()` + counter on /api/disambiguation. If the route ever fires, the test fails directly. Plus a `waitForTimeout(200)` grace window after submit to ensure any deferred async fires.

2. **Hermeticity.** Both tests use `page.route()` mocks; no real backend hit. Pattern from I-f2-005.

3. **Tirzepatide question wording.** Use a complete clinical question ("Does tirzepatide reduce A1c in adults with type 2 diabetes?") to ensure intake's existing scope-classifier path doesn't get confused. The question itself is irrelevant to the backend mock; we just need to exercise the form submit path.

4. **`route.abort()` semantics.** Playwright's `route.abort()` rejects the request. The frontend's `runDisambiguation()` will throw (caught by the existing try/catch in intake_form.tsx). The test asserts `disambigCalls === 0` so abort is only used as a regression marker — it should NEVER fire in test 1's path. For test 2, we mock with normal fulfill (not abort) since the call IS expected to fire there.

5. **Counter pattern.** `let disambigCalls = 0; await page.route(..., async (route) => { disambigCalls++; await route.abort(); });` — counter visible in test scope.

6. **No new package.json dep.**

7. **CHARTER §1 LOC cap.** ~80 net; well under.

8. **Path #3 (`is_ambiguous=true && clusters.length <= 1`) NOT tested.** Defensive code path; not in spec. Brief author commits to NOT adding it unless Codex flags as P0/P1 (LAW V no-polish).

9. **`intake_form.tsx` guard fail-loud.** If `runDisambiguation()` throws (e.g. real 503), the existing try/catch sets `state.kind=error`. Modal still NOT opened. This negative case is implicitly tested but not asserted explicitly here.

10. **Playwright `not.toBeVisible()` vs `toBeHidden()`.** Playwright's `not.toBeVisible()` resolves immediately if the element doesn't exist OR is hidden. `toBeHidden()` requires the element to exist + be hidden. We use `not.toBeVisible()` since the modal element never enters the DOM when not opened.

## Output schema (mandatory)

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
