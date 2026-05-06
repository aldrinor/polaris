# Codex Diff Review — I-f2-006 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-006 — F2 adversarial: tirzepatide → no false disambiguation
**Branch:** bot/I-f2-006
**Brief:** APPROVED iter 2 (iter1 REQ_CH 2P1 → iter2 APPROVE 0/0/2P2 accept_remaining; both P2 addressed in implementation)
**Canonical-diff-sha256:** `454d164cd28b3576eb3cc1cd485dd097ba7d6094c10464d8a29166bac7cd9ebf`
**LOC:** 104 net (well under CHARTER §1 200-cap)
**Format:** `npx prettier --check` clean.

## Files

```
web/tests/e2e/intake_disambiguation_negative.spec.ts                NEW +104
```

## What changed

Two Playwright adversarial tests asserting the disambiguation modal does NOT render for unambiguous queries. Both use the question "Does tirzepatide reduce A1c in adults with type 2 diabetes?".

### Test 1: `tirzepatide single entity → no disambiguation modal`
- Mock /api/intake (intakeCalls++): `decision.needs_disambiguation=false`, no `candidate_snippets`.
- Mock /api/disambiguation (disambigCalls++; `route.abort()`).
- Submit form. Wait for `scope-decision-view`. 200ms grace.
- Assert `[data-slot="disambiguation-modal"]` hidden.
- Assert `intakeCalls === 1, disambigCalls === 0`.

### Test 2: `needs_disambiguation=true but is_ambiguous=false → no modal`
- Mock /api/intake: `needs_disambiguation=true`, 2 candidate_snippets.
- Mock /api/disambiguation: `is_ambiguous=false, clusters=[{0,...},{1,...}]` (deliberately contradictory data isolates the `is_ambiguous` guard).
- Submit form. Wait for `scope-decision-view`. 200ms grace.
- Assert `[data-slot="disambiguation-modal"]` hidden.
- Assert `intakeCalls === 1, disambigCalls === 1` (proves the disambiguation call DID fire yet modal stayed closed — guard isolation).

## Iter-2 brief P2 advisories addressed in implementation

- **P2 #1 (stale risk note `not.toBeVisible()`):** Both tests use `toBeHidden()` consistently.
- **P2 #2 (full intake response shape):** Shared `baseDecision` const includes `ambiguity_axes: []` + `clarifications_needed: []` so `ScopeDecisionView` does not crash.

## Risks for Codex Red-Team

1. **Two-guard coverage.** Both `needs_disambiguation` (path #1, Test 1) AND `is_ambiguous` (path #2, Test 2) trigger guards have negative-case coverage. The `clusters.length > 1` guard (path #3) is NOT separately exercised; covered implicitly by path #2 + LAW V no-polish.

2. **Toothless-pattern guard (Codex iter-1 P1 #1 fix).** Modal-Popup-element assertion `[data-slot="disambiguation-modal"]` toBeHidden catches even an empty-cards regression. Cluster-card-testid assertion would NOT catch that.

3. **Path-execution counters (Codex iter-1 P1 #2 fix).** Both tests assert exact `intakeCalls` + `disambigCalls`. A regression where intake never fires, or disambiguation fires unexpectedly, surfaces immediately.

4. **`route.abort()` in Test 1.** Hard-fails if /api/disambiguation ever fires in path #1 (the call SHOULD never happen). Counter is the structured regression marker; abort is the runtime safety net.

5. **`scope-decision-view` proxy.** Waiting for this testid to be visible proves the intake `.success` branch in `intake_form.tsx` ran (it renders ScopeDecisionView only when `state.kind === "ok"`). Without this, the test could pass even if intake silently failed.

6. **200ms grace window.** Allows any deferred /api/disambiguation call to fire before the modal-hidden assertion. Tests both async timing AND DOM state.

7. **`ScopeDecisionView` doesn't crash.** Per Codex iter-2 P2 #2, the shared `baseDecision` const includes `ambiguity_axes: []` + `clarifications_needed: []` so `.length` access (in the existing `ambiguity_modal.tsx` rendering of clarifications_needed) does not throw.

8. **Hermeticity.** No real backend hit. Both tests are self-contained.

9. **No new package.json dep.**

10. **CHARTER §1 LOC cap.** 104 net.

11. **Cancel idempotency / accessibility / focus management.** Out of scope per breakdown; covered by I-f2-004.

12. **Path #3 (clusters.length=1, is_ambiguous=true) NOT tested.** Defensive code path; not in spec. Brief author commits to NOT adding it unless flagged P0/P1.

## Out of scope (do NOT regress on these)

- F2 edge cases (French / PDF drop) → I-f2-007.
- Evaluator walkthrough → I-f2-008.

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
