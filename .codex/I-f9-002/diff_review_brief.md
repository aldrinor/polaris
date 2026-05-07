# Codex Diff Review — I-f9-002 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix:** Playwright assertion `toContainText("CI")` mismatched the demo string `"confidence interval"`. Changed assertion to `toContainText("confidence interval")` so it matches the rendered text.
- **P2 (unreachable empty fallback):** Acknowledged. The `evaluator-pane-empty` testid is defensive coverage for legacy/dropped payloads where a flag fires but the detail wasn't populated; the badge gate ensures it doesn't fire today, but the fallback remains as defensive UI rather than dead code. Kept as-is (non-blocking per Codex iter-1 P2 framing).

**Updated canonical-diff-sha256:** `ec3b747c596ad0eaca2ec75a5849ff9b036afa0c3bf6dbcee2cb8da217085d0a`

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn Next dev server, browsers, or Playwright runs (sandbox blocks them and burns RAM per CLAUDE.md §8.4).

**Issue:** I-f9-002 — Side pane: generator vs evaluator readings
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `7c20bb654a6ffb1e4e41e91c7da552c1a6675c60b44b5e080f7f57ed4ca2b02d`
**LOC:** 223 net (23 over CHARTER §1 200-cap; LOC exemption requested)

## Files

```
src/polaris_graph/generator2/verified_report.py            +20 (EvaluatorDisagreement model + field)
tests/polaris_graph/generator2/test_verified_report.py     +41 (3 new tests; including VerifiedSentence integration path per Codex iter-1 P2)
web/lib/api.ts                                              +8 (interface + ?: field)
web/app/generation/components/evaluator_pane.tsx           NEW +89 (Sheet pane with both readings, sources, model, empty fallback)
web/app/generation/components/verified_report_view.tsx     +41 (badge → button w/ stopPropagation+keyDown; SectionCard prop; root state + EvaluatorPane render)
web/app/sentence_hover_test/_demo.tsx                      +10 (sec_x:11 evaluator_disagreement payload)
web/tests/e2e/sentence_inspector_evaluator_flag.spec.ts    +24 (click → pane test with propagation guard)
```

## What changed

### Backend
- `EvaluatorDisagreement(generator_reading, evaluator_reading, cited_sources≥1, evaluator_model)`.
- `VerifiedSentence.evaluator_disagreement: EvaluatorDisagreement | None = None` (forward-ref string, resolves at validate time — same pattern as ContradictionSignal).
- 3 new tests: minimal construction, cited_sources min 1, integration through VerifiedSentence (Codex iter-1 P2 fix).
- 66 generator2/test_verified_report.py tests pass.

### Frontend
- `EvaluatorDisagreement` TS interface + optional `evaluator_disagreement?:` on `ReportVerifiedSentence`.
- `evaluator_pane.tsx`: Sheet (right, 40%) with generator/evaluator reading panels (color-coded: blue/rose), source list, model badge. Clear `evaluator-pane-empty` fallback when payload absent (Codex iter-1 P2).
- I-f9-001 row badge converted to `<button>` with `stopPropagation()` on click AND `onKeyDown` Enter/Space handlers (same pattern as I-f8-002 contradiction badge after that issue's iter-1 P1 keyboard-a11y fix). `min-h-6 px-2 py-1` for 24px target.
- `verified_report_view.tsx` root: new `evaluator_open` state + `EvaluatorPane` render. SectionCard accepts `onSelectEvaluator` and threads to SentenceRow.
- Demo sec_x:11 extended with full payload; existing I-f9-001 negative tests (sec_x:5/12) unaffected.
- Playwright test (Codex iter-1 P2): asserts both readings visible, source visible, model visible, AND SentenceInspector did NOT also open (propagation guard).

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 66 passed.
- `npx tsc --noEmit` (web/): exit 0.

## LOC exemption requested

CHARTER §1 200-cap exceeded by 23. Drivers: full Pydantic schema + 3 tests (~61 LOC); EvaluatorPane component with 4 distinct rendered surfaces and explicit empty fallback (~89 LOC); badge → button + Section/root prop threading (~41 LOC); demo + spec extensions (~34 LOC). Splitting Sheet from schema would surface schema field unused (substrate-only) — same anti-pattern as I-f5-003/4, I-f7-001, I-f8-002. Exemption analogous to those (245/246/217/253 LOC granted).

## Risks for Codex Red-Team

1. **Forward reference:** `evaluator_disagreement: "EvaluatorDisagreement | None"` resolves at validate time — verified in test_verified_sentence_with_evaluator_disagreement_field (passes).
2. **Optional null default:** existing fixtures unaffected.
3. **Click propagation guard:** stopPropagation + Enter/Space onKeyDown match I-f8-002 pattern; Playwright asserts `sentence-inspector-sheet` count=0 after badge click.
4. **Honest substrate:** generator does NOT yet populate evaluator_disagreement; demo only render path. Future Issue wires real two-family LLM judge output.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap:** 223 net; exemption requested.
7. **No new package dep.**

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
