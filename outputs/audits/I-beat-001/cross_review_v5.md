# §-1.1 Cross-review v5 — 20 claims complete

**Date:** 2026-05-11
**Coverage:** 20 of ~85 deep claims have both Claude AND Codex independent verdicts (24%).

## Per-report verdict distribution (Codex view, 20 claims)

| Report | VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | Codex-verified rate |
|---|---|---|---|---|---|
| POLARIS tirzepatide | 3 | 3 | 0 | **0** | 50% (3/6) |
| POLARIS Q5 Pharmacare | 3 | 1 | 0 | **0** | 75% (3/4) |
| ChatGPT DR | 4 | 1 | 0 | **0** | 80% (4/5) |
| Gemini DR | 2 | 2 | 1 | **0** | 40% (2/5) |

**0 fabrications across all 20 claims and 4 reports.**

## Aggregate cross-review statistics (20)

- AGREE: 15/20 (75%)
- Codex-stricter DISAGREE: 5/20 (25%)
- Claude-stricter DISAGREE: 0/20 (0%)
- FABRICATED: 0/20
- UNREACHABLE: 0/20

## All 20 claims

| # | Report | Claim summary | Claude | Codex |
|---|---|---|---|---|
| 1 | POLARIS | C1 SURPASS-2 weight absolutes | PARTIAL | PARTIAL |
| 2 | POLARIS | C2 Liu 14-RCT | VERIFIED | PARTIAL |
| 3 | POLARIS | C3 SURMOUNT-2 T4 sub | PARTIAL | PARTIAL |
| 4 | POLARIS | C4 SURPASS-2 HbA1c targets | VERIFIED | VERIFIED |
| 5 | POLARIS | C5 GI AE pattern | VERIFIED | VERIFIED |
| 6 | ChatGPT | C1 SURPASS-2 diffs | VERIFIED | VERIFIED |
| 7 | ChatGPT | C2 SURPASS-6 pooled | VERIFIED | VERIFIED |
| 8 | ChatGPT | C3 SURPASS-CVOT | VERIFIED | VERIFIED |
| 9 | ChatGPT | C4 SURPASS-4 104wk | VERIFIED | PARTIAL |
| 10 | Gemini | C1 SURPASS-1 HbA1c | VERIFIED | VERIFIED |
| 11 | Gemini | C2 SURPASS-1 weight | VERIFIED | PARTIAL |
| 12 | Gemini | C3 SURPASS-1 per-dose <7% | PARTIAL | UNSUPPORTED |
| 13 | Gemini | C4 SURPASS-4 weight/baseline | PARTIAL | PARTIAL |
| 14 | POLARIS Q5 | C1 Quebec OOP 8.7%/4.8% | VERIFIED | VERIFIED |
| 15 | POLARIS Q5 | C2 Bill C-64 dates | VERIFIED | VERIFIED |
| 16 | POLARIS Q5 | C3 RAMQ premium regressivity | VERIFIED | VERIFIED |
| 17 | POLARIS Q5 | C4 PBO estimates | VERIFIED | **PARTIAL** (real bug: 2023 vs 2024 report conflation) |
| 18 | ChatGPT | C5 SURPASS-1 9.5kg / 11% | VERIFIED | VERIFIED |
| 19 | Gemini | C5 SURPASS-3 HbA1c+weight | VERIFIED | VERIFIED |
| 20 | POLARIS | C6 Frontiers Pharm meta range | VERIFIED | VERIFIED |

## Key NEW finding this iter

**POLARIS-Q5-C4 PBO conflation (REAL bug, caught by Codex):**

POLARIS Q5 Pharmacare report says:
> "PBO estimates total drug expenditures under Pharmacare to be $33.2 billion in 2024-25, increasing to $38.9 billion in 2027-28... the incremental cost to the combined federal and provincial public sector was estimated at $11.2 billion in 2024-25, increasing to $13.4 billion in 2027-28."

Codex flagged: these dollar figures come from PBO's **2023** report on a single-payer **universal** drug plan, NOT the **2024** Bill C-64 first-phase cost analysis (which estimated $1.9B over 5 years for the narrow diabetes+contraception coverage).

POLARIS conflated the PBO universal-plan projection with the actual Bill C-64 fiscal estimate. The Bill C-64 first-phase is much smaller than $11-13B/year.

**This is the second substantive POLARIS finding (after duplicate citation bug on Liu paper).** Both correctable via retrieval-classifier refinement.

## Per-source statistical signal (20 claims)

**Differential between ChatGPT DR and Gemini DR is now clearer:**
- ChatGPT DR: 80% verified, 0 fabrications. Strong on numeric trial decimals.
- Gemini DR: 40% verified, 0 fabrications, 1 UNSUPPORTED. Several over-precise claims that don't appear in abstracts.

**POLARIS Q5 Pharmacare: 75% verified.** Better than POLARIS tirzepatide (50%). Reason: pharmacare claims have less snippet-coarseness and tier-substitution issues than tirzepatide (less concentration of T1 RCT trial-decimal claims).

**POLARIS tirzepatide: 50% verified.** PARTIALs all trace to correctable production issues (snippet coarseness, T4 substitution, duplicate citation, PBO conflation).

## Reconciliation: stricter Codex verdict adopted

| Report | Final verified count | Final partial count | Final FAB |
|---|---|---|---|
| POLARIS tirzepatide | 3/6 (50%) | 3/6 (50%) | **0** |
| POLARIS Q5 Pharmacare | 3/4 (75%) | 1/4 (25%) | **0** |
| ChatGPT DR | 4/5 (80%) | 1/5 (20%) | **0** |
| Gemini DR | 2/5 (40%) | 2/5 (40%) + 1/5 UNSUPPORTED | **0 plus 1 UNSUPPORTED** |

## Carney delivery implications (updated)

**POLARIS combined (tirzepatide + Pharmacare):**
- 6 VERIFIED + 4 PARTIAL on 10 deep audits = 60% verified rate
- 208 mechanical sentences automated audit = 0 fab, 0 unreachable
- **Zero fabrications across all auditable surfaces**

**Frontier DR landscape:**
- ChatGPT DR: 80% Codex-verified rate, 0 fab → high precision
- Gemini DR: 40% Codex-verified rate, 0 fab but 1 confirmed UNSUPPORTED claim → lowest precision

**Carney positioning:** POLARIS Q5 Pharmacare (a policy question) achieves 75% Codex-verified rate — between ChatGPT DR (80%) and Gemini DR (40%). With 0 fabrications. This is a real, defensible result for the Carney clinical-and-policy advisory positioning.

## Cost summary

- POLARIS API: ~$0.020 total
- Codex usage: 20 audits × ~3-30K tokens = ~250K tokens
- WebFetch: ~30 calls
- Wall-clock 7-iter sequence: ~90 min Codex sequential + concurrent audit work
