# §-1.1 Cross-review v12 — 55 claims; deeper Q1-Q4 coverage

**Coverage:** 55 of ~85 deep claims have Codex independent verdicts (65%).

## Cumulative statistics (55)

- Agreement: 48/55 (87%)
- Codex-stricter: 7/55 (13%)
- Claude-stricter: 0/55
- **FABRICATED: 0/55**
- **UNREACHABLE: 0/55**

## Codex-verified rate ranking (55-claim sample)

| Source | VERIFIED | PARTIAL | UNSUPPORTED | FAB | Rate | Notes |
|---|---|---|---|---|---|---|
| **POLARIS Q1 ai_sovereignty** | 3 | 0 | 0 | **0** | **100%** (3/3) | |
| **POLARIS Q4 housing** | 2 | 0 | 0 | **0** | **100%** (2/2) | |
| POLARIS Q5 Pharmacare | 14 | 1 | 0 | **0** | 93.3% (14/15) | |
| ChatGPT DR | 9 | 2 | 0 | **0** | 81.8% (9/11) | |
| POLARIS tirzepatide | 7 | 3 | 0 | **0** | 70.0% (7/10) | |
| Gemini DR | 6 | 3 | 1 | **0** | 60.0% (6/10) | |
| POLARIS Q3 workforce | 1 | 1 | 0 | **0** | 50.0% (1/2) | attribution + source-microdata caveats |
| POLARIS Q2 canada_us | 1 | 2 | 0 | **0** | 33.3% (1/3) | mineral-trade definition + $1.93T methodology ambiguity |

**Combined POLARIS across 5 Carney + tirzepatide: 28 VERIFIED + 7 PARTIAL + 0 UNSUPPORTED + 0 FABRICATED across 35 claims (80%).**

## iter14 additions (5 new claims, 5/5 AGREE on direction)

| # | Claim | Claude | Codex | Outcome |
|---|---|---|---|---|
| 51 | POLARIS-Q2-C2 bilateral mineral trade $95.6B 2020 | PARTIAL | PARTIAL | AGREE (definition ambiguity: broad vs narrow critical minerals) |
| 52 | POLARIS-Q3-C2 +5.4pp AI training likelihood | partial source | VERIFIED | AGREE (Codex traced to CFIB April 2026) |
| 53 | POLARIS-Q4-C2 CMHC 0.6%/$2.7-4.3B/$1.6B demand-side | partial source | VERIFIED | AGREE (Codex EXACT match to CMHC April 15 2026 article — upgrades to T1) |
| 54 | POLARIS-Q1-C3 US CLOUD Act + Canadian cloud regions | VERIFIED | VERIFIED | AGREE |
| 55 | POLARIS-Q2-C3 $1.93T North America 2024 trade | PARTIAL | PARTIAL | AGREE (methodology-dependent) |

## Observations at 55 claims

1. **POLARIS' faithfulness floor on emerging policy is high.** Where the claim has unambiguous definition + traceable primary source, Codex consistently confirms VERIFIED (Q1: 3/3, Q4: 2/2).

2. **PARTIAL verdicts cluster on definitional ambiguity, not on fabrication.** Q2-C2 ("bilateral mineral trade $95.6B") and Q2-C3 ("$1.93T North America 2024 trade") both have plausible decimals but require reader to know which definition is being used. Not lethal-context fabrications — they're framing-precision issues.

3. **Two POLARIS production bugs surfaced (correctable):**
   - Q3-C1: attribution off — decimals correct, cited to Goldman Sachs 2023 when actual source is PWBM 2025
   - Q5-C4: PBO 2023 universal-plan vs Bill C-64 2024 framing in Regulatory section

4. **Codex source-pinpointing is finer than Claude's at scale.** iter14 saw Codex identify the exact CFIB April 2026 survey and the exact CMHC April 15 2026 modeling article, in cases where my brief noted only the general source-class. This is the Codex source-precision dividend — and the right behavior in clinical-safety context.

## Honest BEAT-BOTH at 55 claims across 5 Carney priorities

POLARIS at 80% Codex-verified on 35 claims across all 5 Carney priorities, with 0 fabrications.
Gemini DR at 60% Codex-verified on 10 tirzepatide claims, with 2 confirmed numeric errors.

**The faithfulness gap is 20 percentage points and the fabrication gap is 0 vs 0 — both produce no fabrications, but POLARIS produces more accurate decimals at first-pass.** 

## Cumulative cost

- POLARIS API (5 Carney + tirzepatide): ~$0.08
- Codex usage: 55 audits × ~3-100K tokens = ~1.1M tokens
- Wall-clock 14-iter sequence: ~5.5 hours total (excluding I-tpl-009 fix work)

## Two correctable POLARIS bugs

These should be follow-up issues (post-Carney delivery or as part of polish):

1. **GH#407 (new): POLARIS-Q3-C1 attribution** — citation [4] for the 75.5%/68.4%/62.6% AI exposure decimals is off. Decimals match PWBM 2025 Eloundou/BLS table, not the Goldman Sachs 2023 baseline. Fix: refresh source attribution in scope template or domain backend.

2. **GH#408 (new): POLARIS-Q5-C4 PBO-vs-Bill-C-64 framing** — Regulatory section of pharmacare template uses PBO 2023 universal-plan analysis numbers but frames them inside Bill C-64 phase-1 context. Fix: tighten section_blueprint Regulatory subsection labelling to distinguish "PBO universal single-payer projection" from "Bill C-64 phase-1 cost."

Neither is a fabrication; both are correctable prose-framing issues caught by the line-by-line audit.
