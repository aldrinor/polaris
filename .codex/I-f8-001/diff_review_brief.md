# Codex Diff Review — I-f8-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f8-001 — Inline ⚠ N sources disagree badge
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `241f5b99fff47d6048b9fc677384d504c12dd419a63683b1dbf86aa5e89c9104`
**LOC:** 104 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py            +18 (ContradictionSignal class + field)
tests/polaris_graph/generator2/test_verified_report.py     +30 (3 new tests + import)
web/lib/api.ts                                              +6 (ContradictionSignal interface + ?: field)
web/app/generation/components/verified_report_view.tsx     +10 (inline badge with title tooltip)
web/app/sentence_hover_test/_demo.tsx                      +13 (sec_x:26 with contradiction)
web/tests/e2e/sentence_inspector_contradiction.spec.ts     NEW +27 (positive + negative tests)
```

## What changed

### Backend
- `ContradictionSignal`: `disagreeing_source_count: int (ge=2, le=20)`, `summary: str (1..500 chars)`.
- `VerifiedSentence.contradiction: ContradictionSignal | None = None` (forward-ref string, resolves at first model_validate).
- 3 new schema tests: default None, with-signal, count<2 rejected.
- 46 generator2/test_verified_report.py tests pass.

### Frontend
- `web/lib/api.ts`: `ContradictionSignal` interface + optional `contradiction?: ContradictionSignal | null`.
- `verified_report_view.tsx`: inline ⚠ badge with `title=summary` tooltip per Codex iter-1 P2 (title attribute IS the tooltip, asserted in test).
- Demo sec_x:26 with 3-source contradiction signal.
- 2 Playwright tests: positive (badge + text + title) + negative (no badge on normal sentence).

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 46 passed.
- `npx tsc --noEmit` (web/): exit 0.
- `python -c "from polaris_graph.generator2.verified_report import VerifiedSentence; ..."` confirmed forward-ref resolution.

## Risks for Codex Red-Team

1. **Forward reference:** `contradiction: "ContradictionSignal | None"` defined as string before class definition. Pydantic resolves at validation time. Verified working via Python smoke check.
2. **Honest substrate:** generator does NOT populate contradiction; demo path is the only render today. Future Issue (F8-002+) wires real detection.
3. **Optional field back-compat:** `is None` default; existing fixtures untouched.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 104 net. Under 200.
6. **No new package dep.**

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
