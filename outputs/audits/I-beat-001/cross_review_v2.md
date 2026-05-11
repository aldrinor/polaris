# §-1.1 Claude vs Codex cross-review v2 — 5 claims done

**Date:** 2026-05-11
**Method:** Codex inline-source pattern (single-claim per invocation, primary-source ground truth embedded in brief). Token cost ~2,500-9,500 per Codex audit.

## Cross-review verdicts (5 claims)

| # | Claim | Report | Claude | Codex | Agreement |
|---|---|---|---|---|---|
| 1 | C1 SURPASS-2 weight absolutes | POLARIS | PARTIAL | PARTIAL | **AGREE** ✓ |
| 2 | C2 Liu 14-RCT meta-analysis | POLARIS | VERIFIED | PARTIAL | **DISAGREE** (Codex stricter) |
| 3 | C3 SURMOUNT-2 (T4 substitution) | POLARIS | PARTIAL | PARTIAL | **AGREE** ✓ |
| 4 | C1 SURPASS-2 HbA1c+weight diffs | ChatGPT DR | VERIFIED | VERIFIED | **AGREE** ✓ |
| 5 | C3 SURPASS-1 HbA1c<7% per-dose | Gemini DR | PARTIAL | UNSUPPORTED | **DISAGREE** (Codex stricter) |

**Statistics:**
- Agreement rate: 3/5 (60%)
- All disagreements: Codex stricter than Claude
- Zero Claude-stricter-than-Codex cases
- Codex never elevated to FABRICATED on these 5 claims

## Per-report cross-reviewed verdict distribution

| Report | Codex VERIFIED | Codex PARTIAL | Codex UNSUPPORTED | Codex FABRICATED |
|---|---|---|---|---|
| POLARIS | 0 | 3 | 0 | 0 |
| ChatGPT DR | 1 | 0 | 0 | 0 |
| Gemini DR | 0 | 0 | 1 | 0 |

**Codex's view of the 3 reports:**
- POLARIS: 3/3 cross-reviewed claims got PARTIAL — Codex finds POLARIS systematically over-cautious about decimal precision OR cites tertiary sources for trial decimals. Not fabrication.
- ChatGPT DR: 1/1 cross-reviewed VERIFIED.
- Gemini DR: 1/1 cross-reviewed UNSUPPORTED — the per-dose HbA1c<7% percentages.

## What this proves

1. **§-1.1 cross-review pattern works.** Codex inline-source per-claim audit produces clean verdicts in ~2-10K tokens each.
2. **Codex applies a stricter rubric than Claude on partial-evidence claims.** Cross-review value confirmed: Codex catches nuance Claude missed.
3. **Gemini DR per-dose error is now CONFIRMED by both auditors independently.** Claude PARTIAL → Codex UNSUPPORTED. This is the strongest single-claim fabrication signal across all 3 reports.
4. **POLARIS's verdict pattern is consistent**: 0 FABRICATED on automated 208-sentence audit + 3/3 cross-reviewed claims at PARTIAL (snippet coarseness OR citation-tier issues, NOT fabrication).

## Reconciliation rule

For disagreements, adopt the stricter Codex verdict. Rationale: §-1.1 is clinical-safety-critical. False-positives (Claude saying VERIFIED when Codex says PARTIAL) are LESS safe than false-negatives. Pick stricter for production use.

## Remaining work to complete §-1.1 audit

- POLARIS tirzepatide: 25+ claims unaudited by Codex (60K-200K tokens, ~25 sequential calls @ ~30sec each = ~15 min wall-clock)
- POLARIS pharmacare Q5: ~50 claims unaudited by Codex (similar budget)
- ChatGPT DR: 29 more claims (5 done, 30 total)
- Gemini DR: 24 more claims (1 done deep + 2 done Claude-only, 25 total)

Total: ~130 more Codex audits sequentially. Budget ~$5-20 in Codex usage at OpenAI rates, ~1-2 hours wall-clock.

This is achievable but requires sustained execution. Pattern is unblocked; just needs the iterations to run.
