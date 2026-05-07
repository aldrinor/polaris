# Codex Diff Review — I-f5-007 (ITER 2 of 5)

## Iter 2 directive — STATIC review only

Iter 1 attempted to spawn a Next.js dev server for browser verification, which the sandbox blocked. **Do NOT spawn dev servers, browsers, or Playwright runs.** Static review only: read the diff, check schema/UI consistency, verify TypeScript would compile, verify tests would pass against the new field. Local pytest run + `npx tsc --noEmit` were already verified by Claude (results in the brief).

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**Issue:** I-f5-007 — Inspector retracted + stale (>2y) badges
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `fa65f6f8e87681e5a2568f05bfeac19c36927fc93d55440be53bc50d0162f753`
**LOC:** 157 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/retrieval2/evidence_pool.py            +11 (Source.retracted field)
tests/polaris_graph/retrieval2/test_evidence_pool.py     +24 (1 new test, default + roundtrip)
web/lib/api.ts                                           +1 (retracted? on RetrievalSource)
web/app/generation/components/sentence_inspector.tsx     +30 (STALE_THRESHOLD_DAYS const + isStale + 2 badges)
web/app/sentence_hover_test/_demo.tsx                    +63/-13 (FRESH_DATE/STALE_DATE consts + SRC_RETRACTED + SRC_STALE + sec_x:16/17)
web/tests/e2e/sentence_inspector_source.spec.ts         -3 (drop the date assertion that breaks under fresh-date fixture)
web/tests/e2e/sentence_inspector_retracted_stale.spec.ts NEW +37 (3 Playwright tests)
```

## What changed

### Backend
- `Source.retracted: bool = Field(default=False, ...)` added to evidence_pool schema. Default keeps all existing fixtures valid; explicit True drives the UI badge.

### Backend tests
- 1 new test `test_source_retracted_default_false_and_explicit_true` covering default + explicit + JSON roundtrip.
- Full retrieval2 suite: 23 passed.

### Frontend
- `web/lib/api.ts`: `retracted?: boolean` added to `RetrievalSource` (OPTIONAL).
- `sentence_inspector.tsx`: module-level `STALE_THRESHOLD_DAYS = 730`. `isStale(publication_date)` helper handles null/NaN. `SourceCard` renders Retracted badge (`inspector-retracted-{idx}`) when `source.retracted === true` and Stale badge (`inspector-stale-{idx}`) when isStale returns true; both alongside the tier badge.
- `_demo.tsx`: `FRESH_DATE` (now-30d) and `STALE_DATE` (now-3y) module-level consts. `_src()` uses FRESH_DATE; `SRC_RETRACTED` (FRESH_DATE + retracted=true) and `SRC_STALE` (STALE_DATE) appended to POOL. `sources_per_tier.T1` updated 10 → 12 (Codex iter-1 P2 fix).
- 3 Playwright tests: retracted, stale, clean-non-retracted-fresh-source.

### Existing test update
- `sentence_inspector_source.spec.ts`: dropped the assertion expecting `2024-03-15` text in trace (date now dynamic via FRESH_DATE; Codex iter-1 P1 fix). The remaining trace assertions (Cochrane review + Smith J) keep coverage stable.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/retrieval2/`: 23 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Date determinism:** STALE_DATE = now - 3*365d, well past 730d cutoff in any timezone. FRESH_DATE = now - 30d, well below cutoff. No timezone edge.
2. **isStale null/NaN guards:** `publication_date` can be null per type; helper returns false in those cases.
3. **Future-proofing:** field defaults to False — when real CrossRef wiring lands, populator just flips the flag. No breaking change.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 157 net. Under 200.
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
