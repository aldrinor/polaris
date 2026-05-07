# Codex Brief Review — I-f5-007 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (stale-fixture trap):** existing demo `_src()` uses `publication_date: "2024-03-15"` which is >730 days from 2026-05-07 — implementing stale badge would render it on EVERY existing sentence and fail the cleanness assertion in test 3. Fix: change `_src()` `publication_date` to a runtime-fresh date (e.g. `new Date(Date.now() - 30*24*3600*1000).toISOString().slice(0, 10)`, ~30 days ago — never stale, never on the threshold edge). Add module-level constant `FRESH_DATE`.
- **P1 fix (existing I-f5-003 assertion):** `web/tests/e2e/sentence_inspector_source.spec.ts:23` asserts `inspector-trace-0` contains `"2024-03-15"`. Replace with a stable assertion: `await expect(page.getByTestId("inspector-trace-0")).toContainText("Smith J");` (already present per existing test, line 27 — collapse to a single check that doesn't depend on date string).
- **P2 fix (POOL sources_per_tier):** when appending src-retracted and src-stale, update `adequacy.sources_per_tier.T1` from 10 → 12 (both new sources tier T1).

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan.

## Pre-flight

- **Context:** I-f5-007 — Inspector renders `retracted` and `stale (>2y)` badges per cited source. Two independent signals:
  - **retracted:** generator may not realize a source has been retracted post-publication. Add `Source.retracted: bool = False` field; UI shows red retracted badge when True.
  - **stale (>2y):** computed at UI from `publication_date` — if `now - publication_date > 730 days`, render an amber "stale" badge. Threshold defined per Carney plan §F (clinical sources should be ≤2y for current-of-knowledge).
- **Constraints:** No real LLM judge wired here. `retracted` is a backend-supplied field (today's fixed populator: False everywhere); future Issue may wire CrossRef/Retraction Watch lookup.
- **Done-when:** acceptance criteria 1-8 below.

**Independence directive:** prior round changelog markers are untrustworthy.

## Plan

### Backend
1. `src/polaris_graph/retrieval2/evidence_pool.py`: add `retracted: bool = Field(default=False, description="True iff source has been retracted post-publication. Default False — populated by future CrossRef/Retraction Watch wiring.")` to `Source`.
2. Tests in `tests/polaris_graph/retrieval2/test_evidence_pool.py` (or equivalent): 1 new test covering default=False and explicit=True round-trip. Search `rg "Source\\(" tests/` first to identify existing fixture sites; default=False keeps them all valid (no fixture sweep required).

### Frontend
3. `web/lib/api.ts`: add `retracted?: boolean` (OPTIONAL) to `RetrievalSource` interface. Defensive default behavior: undefined/false → no badge.
4. `web/app/generation/components/sentence_inspector.tsx`: in `SourceCard`, add two badges next to the tier badge:
   - **Retracted badge:** `data-testid="inspector-retracted-{idx}"`, red border, tooltip "Source retracted post-publication" — render iff `source.retracted === true`.
   - **Stale badge:** `data-testid="inspector-stale-{idx}"`, amber border, tooltip "Source >2 years old (per Carney plan §F currency-of-knowledge)" — render iff `publication_date` is set AND `(Date.now() - new Date(publication_date).getTime()) > 730 * 24 * 3600 * 1000`. Stale threshold defined in module-level constant `STALE_THRESHOLD_DAYS = 730`.
5. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:16 with token to a retracted source (need to mark one of the synthetic sources with `retracted: true`); APPEND sec_x:17 with token to a stale source (need a synthetic source with `publication_date` from 3 years ago). Add 2 new sources at end of POOL: src-retracted (retracted=true) and src-stale (publication_date 3y ago).
6. `web/tests/e2e/sentence_inspector_retracted_stale.spec.ts` (new):
   - Test 1: click sec_x:16 → assert `inspector-retracted-0` visible.
   - Test 2: click sec_x:17 → assert `inspector-stale-0` visible.
   - Test 3: click a normal sentence (sec_x:5) → assert NEITHER badge visible (cleanliness).

## Risks for Codex Red-Team
1. **Stale threshold determinism:** the test fixture uses `publication_date: "2023-01-15"` (3y ago from 2026-05-07); when run in 2027 or later, this stays stale. Avoiding a fixture date so close to the 2y boundary that timezones flip the test.
2. **Existing fixtures:** `Source(retracted=False)` default — no backend fixture sweep required.
3. **Frontend type:** `retracted?: boolean` is OPTIONAL; existing demo source literals stay valid.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~100 LOC net. Under 200.

## Acceptance criteria

1. `Source.retracted: bool = False` field added to evidence_pool schema.
2. 1 backend test covering retracted default + explicit roundtrip.
3. Frontend `RetrievalSource` includes `retracted?: boolean`.
4. Inspector renders `inspector-retracted-{idx}` badge when source.retracted is True.
5. Inspector renders `inspector-stale-{idx}` badge when publication_date >2y old, threshold 730 days, module-level constant.
6. Demo fixture has src-retracted and src-stale sources + sec_x:16/sec_x:17 sentences citing them.
7. Playwright covers retracted, stale, and absence on a normal sentence.
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
