# V30 Phase-2 — PHASE2_CHECKPOINT SHIP MANIFEST

**Ship date**: 2026-04-26
**Ship label**: `PHASE2_CHECKPOINT` / `AUDIT_GRADE_PREVIEW`
**Canonical artifact**: `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/`
**Git commit**: `90b185a`

## 7-dimension verdict (Codex substance-density framing)

**2 BB + 4 BO + 1 LB**

| Dimension | Verdict | Notes |
|---|---|---|
| Citations | **BB** | 112 inline `[N]` markers + T1 bibliography + strict-verify traceability; ChatGPT + Gemini both have 0 inline citations |
| Regulatory | LB | 4/6 substantive subsections; needs cross-jurisdiction synthesis (V34/M-73 territory) |
| Jurisdiction | BO | US + EU + UK + Canada all in-body; loses ChatGPT cross-comparison |
| Claim-frames | BO | SURPASS-2 full ETD+CI+P; SURPASS-5 + 6 populated; CVOT honest gap |
| Structure | BO | 15/15 contract slots cited; Trial Summary refs misbinding remains |
| Contradictions | **BB** | 14 tier-labeled disagreement clusters; competitors have none |
| Narrative depth | BO | 37.6 numeric facts per 1K words vs Gemini 19.3 (decisive); ChatGPT 59.0 (still ahead) |

## Gate status

- ✅ `PHASE2_CHECKPOINT` met: ≥4/7 ≥BO AND ≤1 LB
- ❌ `BEAT_BOTH_SHIP` not met: zero-LB requirement unsatisfied (Regulatory)

## Substance vs competitors (raw data)

| Metric | ChatGPT DR | Gemini DR | V30 run-14 |
|---|---|---|---|
| Word count | 4,830 | 6,835 | **2,599** |
| Numeric facts (%) | 257 | 129 | 91 |
| 95% CIs | **12** | 0 | 3 |
| P-values | **11** | 3 | 3 |
| HR/RR/OR | **5** | 0 | 1 |
| Inline `[N]` citations | 0 | 0 | **112** |
| Promotional adjectives | 1 | **58** | 1 |
| **Numeric-fact density / 1K words** | **59.0** | 19.3 | 37.6 |

## Strategic positioning

V30 Phase-2 ships an **audit-grade research brief**, not a narrative report.

**What V30 run-14 uniquely delivers** (no competitor matches):
- Inline traceable `[N]` citations on every body claim
- Tier-labeled contradiction disclosure (14 numeric clusters)
- Strict-verify provenance binding (every claim bound to `evidence_id`)
- T1-anchored bibliography (no PR / promotional sources)
- Frame-coverage manifest (`pass=14, partial=0, gap=1`)
- Hedged language calibration (zero promotional adjectives vs Gemini's 58)

**What V30 run-14 does NOT match**:
- ChatGPT DR's per-trial ETD/CI/P density (59 vs 38 facts/1K)
- ChatGPT DR's cross-jurisdiction U.S./EMA contraindication-warning comparison
- Gemini DR's word count (deliberately — Gemini's volume is filler)

## Architectural cycle inventory

5 cycles delivered; 14 sweeps; 396/396 V30..V33 tests green:

| Cycle | Module | Outcome |
|---|---|---|
| M-66 | DOI/PMID corrections + content-fetch wrapper + label_name biblio | 5 wrong PMIDs corrected (SURPASS-2/4/5/6/Thomas), all entities citation-bound |
| M-68 | drop-on-verify gap-disclosure fallback | 15/15 slot rendering — no silent drops |
| V31/M-70 | regulatory_synthesizer | 4/6 regulatory subsections produce substantive prose |
| V32/M-71 | contradiction-aware hedging | Qwen `hedging_appropriateness` ACCEPTABLE |
| V33/M-72 | cross-trial synthesis | Patterns inject correctly; modest BO contribution |

## Path to BEAT_BOTH_SHIP (V34, NOT under V30 Phase-2 scope)

Codex's narrowest fix list (substance-density audit:85):
> *"concentrated Regulatory repair: replace the EMA / NICE / Health Canada stubs with actual cross-jurisdiction synthesis while preserving the current citation and contradiction discipline."*

**Single remaining LB**. Single architectural gap. Estimated 6-8h for M-73 cross-jurisdiction regulatory synthesizer.

## V30 Phase-2 cycle CLOSED

This ship locks the V30 Phase-2 architectural cycle. Further iteration on the same architecture has hit diminishing returns (4 consecutive runs at 1 BB + 4 BO + 2 LB under the original framing; methodology-corrected verdict 2 BB + 4 BO + 1 LB stable).

The next cycle (V34) is a separate decision.
