# Codex Diff Review — I-f5-010 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only (do NOT spawn dev servers; sandbox blocks them).

**Issue:** I-f5-010 — F5 adversarial: paywalled / multi-span bad / T1-vs-T1 conflict
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `36aa1036cb541050930edab69b58a5116c2a3da38b08e2b0f0abf33313a7991b`
**LOC:** 140 net (under CHARTER §1 200-cap)

## Files

```
web/app/generation/components/sentence_inspector.tsx         +11 (paywalled badge)
web/app/generation/components/verified_report_view.tsx       +30 (T1-conflict heuristic + pool threading)
web/app/sentence_hover_test/_demo.tsx                        +49 (SRC_PAYWALLED + sec_x:23/24/25 + sources_per_tier 12→13)
web/tests/e2e/sentence_inspector_adversarial.spec.ts         NEW +52 (4 tests — 3 positive + 1 negative T1-conflict)
```

## What changed

### Frontend
- `sentence_inspector.tsx` `SourceCard`: when `source.full_text_available === false`, render `inspector-paywalled-{idx}` badge alongside tier badge. Source URL + tier + trace + snippet-fallback span all preserved.
- `verified_report_view.tsx` `SentenceRow`: now accepts `pool` prop and computes `t1_conflict` heuristic — set of distinct T1-source ids cited. ≥2 → render `inspector-t1-conflict` caption with explicit "may conflict — review Inspector" framing (honest substrate per CLAUDE.md §9.4).
- `verified_report_view.tsx` `SectionCard`: threads `pool` to `SentenceRow`. `VerifiedReportView` threads `pool` to `SectionCard`.

### Demo fixture
- New `SRC_PAYWALLED` source (T1, full_text_available=false, snippet only).
- POOL `sources_per_tier.T1` updated 12 → 13 per Codex iter-1 P2.
- sec_x:23 cites paywalled source.
- sec_x:24 cites src-0 with two spans, second out-of-range (5000-5050 vs ~80-char text).
- sec_x:25 cites BOTH src-0 AND src-1 (both T1) for T1-conflict heuristic.

### Playwright spec
- 4 tests: paywalled badge + URL still actionable; out-of-range second span flagged; T1-conflict on row; T1-conflict NOT on single-T1 sentence (negative test).

## Verification
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Heuristic honesty:** T1-conflict caption explicitly labels itself "may conflict — heuristic, not semantic detection." Tooltip clarifies.
2. **Multi-span overlay with I-f5-005:** uses existing `inspector-span-out-of-range-{i}-{j}` testid from I-f5-005's SpanQuote.
3. **Paywalled URL still actionable:** test asserts `inspector-source-url-0` href contains `nejm.org` per Codex iter-1 P2.
4. **Negative T1 test:** asserts conflict caption ABSENT for sec_x:5 (single-source).
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap:** 140 net. Under 200.
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
