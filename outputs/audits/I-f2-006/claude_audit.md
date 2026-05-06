# Claude Architect Audit — I-f2-006 (F2 adversarial: tirzepatide → no false disambiguation)

**Branch:** bot/I-f2-006 / **Diff SHA256:** `454d164cd28b3576eb3cc1cd485dd097ba7d6094c10464d8a29166bac7cd9ebf`
**LOC:** 104 net (well under CHARTER §1 200-cap)
**Format:** `npx prettier --check` clean.

## Files

```
web/tests/e2e/intake_disambiguation_negative.spec.ts                NEW +104
```

## Iter-2 brief P2 advisories — addressed in implementation

- **P2 #1 (stale risk note about `not.toBeVisible()`):** ADDRESSED. Both tests use `await expect(page.locator('[data-slot="disambiguation-modal"]')).toBeHidden()` consistently with the binding criteria.
- **P2 #2 (full intake response shape including `ambiguity_axes` + `clarifications_needed`):** ADDRESSED. Shared `baseDecision` const includes both fields as `[]`. ScopeDecisionView's `.length` access on these fields will not crash.

## Architecture review

1. **Two negative tests covering two trigger guards (Codex iter-1 P1 #1 fix).**
   - Test 1 (path #1): backend says `needs_disambiguation=false` → frontend never calls /api/disambiguation. Counter `disambigCalls === 0` is the regression marker.
   - Test 2 (path #2): backend says `needs_disambiguation=true` AND /api/disambiguation returns `is_ambiguous=false, clusters.length=2` (deliberately contradictory; isolates the `is_ambiguous` guard). Frontend's `if (dis.is_ambiguous && dis.clusters.length > 1)` short-circuits → modal stays closed.

2. **Modal-source-of-truth assertion (Codex iter-1 P1 #1 fix).** Both tests assert `[data-slot="disambiguation-modal"]` (the Popup element itself) is hidden, NOT just `disambiguation-cluster-0`. An empty-cards regression that opens the modal with zero cards would fail this assertion. The modal slot attribute lives on `DialogPrimitive.Popup` per `disambiguation_modal.tsx:55`.

3. **Path-execution proof (Codex iter-1 P1 #2 fix).** Both tests count intake + disambiguation route calls; assert exact counts. Both wait for `scope-decision-view` testid (proxies that intake response was processed by the form's success branch). 200ms grace window after surfaces any deferred /api/disambiguation call.

4. **Hermeticity.** Both tests use `page.route()` mocks. No real backend hit.

5. **`route.abort()` for Test 1.** If /api/disambiguation EVER fires in Test 1's path it's a regression: the counter will rise AND the abort will surface a frontend error. Belt-and-suspenders.

6. **Tirzepatide question wording.** A complete clinical question to ensure the form submit path is exercised normally; the question itself is irrelevant to the mocked backend.

## LAW + invariant checks

- **LAW II:** No silent fallbacks. Both tests assert exact call counts. ✓
- **LAW V:** snake_case file naming; `.spec.ts` follows project convention. ✓
- **§9.4:** No `unittest.mock`; tests use Playwright's built-in `page.route()`. ✓
- **§8.4:** No real network; mocks only. ✓
- **CHARTER §1 200-cap:** 104 net. ✓

## Test plan coverage

| Test | Trigger guard exercised | intakeCalls | disambigCalls |
|---|---|---|---|
| 1 (`tirzepatide single entity`) | `needs_disambiguation=false` short-circuits before disambiguation call | 1 | 0 |
| 2 (`needs_disambiguation=true but is_ambiguous=false`) | `is_ambiguous && clusters.length > 1` guard stays closed even with disambiguation call | 1 | 1 |

## Out of scope (deferred)

- F2 edge cases (French / PDF drop) → I-f2-007.
- Evaluator walkthrough → I-f2-008.
- Path #3 (`is_ambiguous=true && clusters.length=1`) negative test → not in spec; LAW V no-polish.

## Verdict

APPROVE for Codex diff review.
