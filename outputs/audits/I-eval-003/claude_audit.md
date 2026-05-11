# Claude Architect Audit — I-eval-003 Tier-1 v2 extension

## Scope
Extend the Q5 Tier-1 v2 pilot (PR #421) to Q1-Q4. Tooling: a deterministic `enumerate_tier1_claims.py` that parses report + bibliography + evidence_pool into the v2 YAML schema. Audit work-product: 29 Codex batches across 189 audit-grade claims, aggregated alongside Q5 for 217 total.

## What this PR actually establishes

Iter-2 verdict: POLARIS verified-findings claims hold against their cited evidence_pool direct_quote spans at 93.1% (202V / 15P / 0U / 0F across 217 claims).

Critical methodology lesson: iter-1 of this same audit shipped a tooling bug (600-char truncation of direct_quote) that produced a 50% UNSUPPORTED aggregate — a false catastrophe. Codex iter-1 brief review caught the bug in its first pass (P1: `scripts/enumerate_tier1_claims.py:114-123 slices span_text to 600 chars`). Iter-2 corrects.

This is exactly the §-1.1 line-by-line clinical-safety-critical posture working as designed: a metadata/pattern audit would have shipped iter-1's number as the headline finding. The line-by-line standard surfaced the per-claim discrepancy that revealed the truncation bug.

## Architecture

- `scripts/enumerate_tier1_claims.py`: pure-function parser. Reads `report.md` + `bibliography.json` + `evidence_pool.json`. Truncates at Analyst-Synthesis marker (synthesis sections are hedged per report header). Splits on sentence boundaries with inline `[N]` citation tokens. For each cited [N]: bibliography → evidence_id → full direct_quote.
- Output: Tier-1 v2 YAML matching `q5_claims_enumeration.yaml` schema.
- Tests: smoke validation via re-enumeration of all 4 reports producing same claim counts (Q1=31, Q2=46, Q3=61, Q4=51) confirming sentence extraction is stable.

## Verification of fix

- Per Codex iter-2: empirical re-run on Q1-Q4 = 178V/11P/0U (94.2%V); iter-1 same data = 34V/46P/109U (18%V). The fix isolates to the truncation removal.
- `direct_quote` length distribution across the 4 reports' evidence_pools: min 259, max 9046, mean 2422 chars. Iter-1's 600-char cap removed 70-95% of supporting context.
- Codex iter-2 brief APPROVE; iter-1 diff APPROVE.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Future evidence_pool may exceed Codex context window | Each batch caps at ≤7 claims. Largest direct_quote observed (9046 chars) × 7 = 63K chars, well under Codex 200K context. |
| Claude independent pass on Q1-Q4 is still incomplete (§-1.1 requires both passes) | Flagged explicitly in aggregate; documented as remaining work for a follow-up Issue. Q5 has paired Claude pass per PR #421. |
| Q2 has lower V rate (83% vs 98% on Q3/Q4) | Aggregate calls out the 8 PARTIALs concentrated on CUSMA decimal/date alignment between cited span and adjacent paragraphs not in the captured quote. Bounded risk; document for Tier-1 v3 to consider full-source-body audit. |
| `missing_biblio_nums` field surface might be missed by downstream readers | Visible in YAML output and surfaced as a P2 follow-up if any claim has dangling [N]. |

## Recommendation

APPROVE. Codex brief iter-2 + diff iter-1 both APPROVE. The PR establishes the audit tooling on a sound footing AND the corrected audit signal across 217 claims. Ship.
