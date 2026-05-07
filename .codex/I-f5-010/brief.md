# Codex Brief Review — I-f5-010 (ITER 1 of 5)

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

- **Context:** I-f5-010 — three adversarial cases the Inspector must handle honestly:
  1. **Paywalled span:** source has no `full_text` (paywalled or 403); the cited span cannot be quoted. UI must show a `paywalled` badge with the URL still actionable.
  2. **Multi-span claim with one bad span:** sentence cites N spans of one source where one span is out-of-range. Inspector should render valid spans + flag the bad one explicitly.
  3. **T1-vs-T1 conflict:** two T1 sources cited for opposing factual claims (e.g. "X reduces" vs "X has no effect"). UI must render BOTH and a "conflict" indicator.

Multi-span out-of-range case (case 2) already partially covered by I-f5-005 + I-f5-003 (`inspector-span-out-of-range-{i}-{j}` testid). This Issue extends with adversarial fixtures and a "conflict" UI for case 3.

## Plan

### Backend
1. `src/polaris_graph/retrieval2/evidence_pool.py`: existing `Source.full_text: str | None` already supports the paywalled case (full_text=None, full_text_available=False, snippet still present). No new field needed.

### Frontend
2. `web/app/generation/components/sentence_inspector.tsx`: in `SourceCard`, when `source.full_text_available === false`, render a `paywalled` badge (`data-testid="inspector-paywalled-{idx}"`, amber border, tooltip explaining no quotable span available). Source URL + tier + trace still render; span fall-back gracefully shows "(snippet only)" instead of attempting to slice.
3. `web/app/generation/components/verified_report_view.tsx`: when a sentence has provenance tokens citing TWO OR MORE sources where any pair has T1 tier (i.e., multiple T1 sources cited for the same sentence — proxy for potential conflict), render an `inspector-t1-conflict` indicator on the row (small caption: "T1 sources may conflict — review Inspector"). This is a HEURISTIC indicator, not a semantic conflict detector — that's a future Issue's scope.
4. `web/app/sentence_hover_test/_demo.tsx`: APPEND:
   - `SRC_PAYWALLED`: `full_text_available: false`, `full_text: null`, T1.
   - sec_x:23: cites `src-paywalled` for paywalled-source case.
   - sec_x:24: cites src-0 with two spans, one out-of-range (already covered by I-f5-005 multi-span; extend as a labelled adversarial case).
   - sec_x:25: cites BOTH src-0 (T1) and src-1 (T1) for T1-conflict-heuristic case.
5. `web/tests/e2e/sentence_inspector_adversarial.spec.ts` (new):
   - Test 1 (sec_x:23): click → `inspector-paywalled-0` visible.
   - Test 2 (sec_x:24): click → `inspector-span-out-of-range-0-1` visible (extends I-f5-005 coverage).
   - Test 3 (sec_x:25): assert `inspector-t1-conflict` visible on the ROW (before click).

## Risks for Codex Red-Team
1. **Heuristic conflict signal honesty:** "two T1 sources in one sentence" is a HEURISTIC, not a semantic conflict. Tooltip + caption clearly say "may conflict — review Inspector." Honest substrate per CLAUDE.md §9.4 (no silent overclaim).
2. **Paywalled snippet fallback:** SourceCard already has `text = source.full_text ?? source.snippet ?? ""` (I-f5-003 P1 fix). Out-of-range guard kicks in if span exceeds snippet length. The new badge supplements this with explicit "paywalled — span not quotable" framing.
3. **Existing demo back-compat:** all sec_x:0..22 preserved; sec_x:23..25 appended.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~120 LOC. Under 200.

## Acceptance criteria

1. Paywalled badge `inspector-paywalled-{idx}` renders when `source.full_text_available === false`.
2. T1-conflict heuristic indicator `inspector-t1-conflict` renders on a row when ≥2 T1 sources are cited.
3. Demo fixture has SRC_PAYWALLED + sec_x:23 (paywalled), sec_x:24 (multi-span with bad span), sec_x:25 (T1-conflict heuristic).
4. Playwright covers all 3 adversarial cases.
5. Existing demo + specs preserved (no regression to I-f5-001..009).
6. Honest framing: T1-conflict is HEURISTIC ("may conflict — review"), not a semantic claim.
7. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-7.

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
