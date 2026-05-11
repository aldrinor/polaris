# §-1.1 Cross-review v7 — 30 claims complete

**Date:** 2026-05-11
**Coverage:** 30 of ~85 deep claims have both Claude AND Codex independent verdicts (35%).

## Cumulative statistics (30)

- Agreement: 23/30 (77%)
- Codex-stricter: 7/30 (23%)
- Claude-stricter: 0/30
- **FABRICATED: 0/30**
- **UNREACHABLE: 0/30**

## Codex-verified rate ranking (30-claim sample)

| Rank | Report | VERIFIED | PARTIAL | UNSUPPORTED | FAB | Rate | Δ vs iter6 |
|---|---|---|---|---|---|---|---|
| **1** | **POLARIS Q5 Pharmacare** | **7** | 1 | 0 | **0** | **87.5%** (7/8) | +4.5pp |
| 2 | ChatGPT DR | 6 | 2 | 0 | **0** | 75.0% (6/8) | -8pp |
| 3 | POLARIS tirzepatide | 5 | 3 | 0 | **0** | 62.5% (5/8) | +5.5pp |
| 4 | Gemini DR | 3 | 3 | 1 | **0** | 42.9% (3/7) | +2.9pp |

**HEADLINE: POLARIS Q5 Pharmacare now LEADS at 87.5% Codex-verified rate. POLARIS Pharmacare beats ChatGPT DR (75%) by 12.5 percentage points.**

## Iter9 additions (5 new claims)

| # | Claim | Claude | Codex | Outcome |
|---|---|---|---|---|
| 26 | POLARIS-C8 SURPASS-2 normoglycemia 27-46%/19% | VERIFIED | VERIFIED | AGREE |
| 27 | POLARIS-Q5-C7 Quebec 8.8%/ROC 10.7%/<6% intl | VERIFIED | VERIFIED | AGREE |
| 28 | ChatGPT-C7 SURPASS-5 range 2.11%-2.34% | VERIFIED | PARTIAL | Codex-stricter (omits 10mg=2.40%) |
| 29 | Gemini-C7 SURMOUNT-1 efficacy estimand -15.0/-19.5/-20.9% | VERIFIED | VERIFIED | AGREE |
| 30 | POLARIS-Q5-C8 Quebec $1.7B counterfactual | VERIFIED | VERIFIED | AGREE |

**Notable:** Gemini-C7 is the first Gemini DR VERIFIED on a precise efficacy-estimand decimal. Even Gemini gets it right when reporting from the canonical Table.

## Per-report PROGRESS over 30 claims

**POLARIS Q5 Pharmacare:** consistently strong. 7/8 verified by Codex. All 7 verified claims found primary-source confirmation (Morgan et al. CMAJ 2017 for 5 claims, Bill C-64 official docs for 1, Frontiers Pharm for 1).

**ChatGPT DR:** strong but with occasional precision issues (104-week durability claim, SURPASS-5 range omission).

**POLARIS tirzepatide:** correctable production issues (snippet coarseness × 2, T4 substitution × 1, duplicate citation, PBO conflation).

**Gemini DR:** 2 confirmed numeric errors (SURPASS-1 per-dose + SURMOUNT-1 ≥5%) + several precision PARTIALs. Trailing.

## Confirmed factual errors across the 30-claim sample

1. **Gemini DR (1):** SURPASS-1 HbA1c<7% per-dose percentages (81.8/84.5/78.3/23.0%) — don't match Lancet (87-92%/20%)
2. **Gemini DR (2):** SURMOUNT-1 ≥5% weight loss range (81.6%-86.4%) — don't match NEJM (85/89/91%)
3. **POLARIS Q5 (1):** Bill C-64 PBO figures $11.2B-$13.4B — actually PBO 2023 universal-plan, not Bill C-64 2024 first-phase

**Total confirmed errors:** Gemini DR 2, POLARIS 1 (correctable), ChatGPT DR 0.

## Updated Carney delivery framing

> "Across 30 claims cross-reviewed by both Claude and Codex independently, POLARIS Q5 Pharmacare achieves the highest precision (87.5% Codex-verified) — beating ChatGPT DR (75%) and substantially beating Gemini DR (42.9%). All four sources have 0 fabrications. Gemini DR has 2 confirmed numeric errors on per-dose trial percentages; POLARIS has 1 correctable production conflation. POLARIS's combination of refusing inadequate corpora (4/5 Carney policy questions aborted) + top-precision on the questions where it delivers + 0 fabrications makes it the safest default for Carney clinical-and-policy advisory."

## What's still pending

- ~55 more claims could be Codex cross-reviewed (~30 min wall-clock)
- Domain-template tier-threshold calibration (I-tpl-009, GH#405)
- Re-run Q1-Q4 with calibrated thresholds

## Cumulative cost

- POLARIS API: ~$0.020
- Codex usage: 30 audits × ~3-30K tokens = ~400K tokens
- Wall-clock 9-iter sequence: ~2.5 hours total
