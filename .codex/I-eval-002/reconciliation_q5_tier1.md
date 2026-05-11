# Q5 Pharmacare Tier-1 Pilot — Reconciliation (GH#420 I-eval-002)

**28 claims audited independently by Claude and Codex. 4 disagreements reconciled under §-1.1 stricter-rule.**

## Independent passes

| Reviewer | VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE |
|---|---|---|---|---|---|
| Claude  | 27 | 1 | 0 | **0** | **0** |
| Codex   | 25 | 3 | 0 | **0** | **0** |
| **Reconciled (stricter)** | **24** | **4** | 0 | **0** | **0** |

## Disagreement reconciliation (4 of 28 = 14% disagreement rate)

| claim_id | Claude verdict | Codex verdict | Stricter rule | Reason for disagreement |
|---|---|---|---|---|
| Q5-T1-010 | VERIFIED@0.95 | PARTIAL@0.88 | **PARTIAL** | Codex caught: visible span_text does not explicitly contain "February 2024" — date is only inferred from page metadata "2024 \| Ottawa, Ontario \| Health Canada". Claude was too lenient by accepting metadata as span. |
| Q5-T1-011 | VERIFIED@1.0 | PARTIAL@0.84 | **PARTIAL** | Codex caught: claim says legislation "commits the federal government to establishing a fund" but span says "the Minister also announced the government's plan to establish a fund". Distinction between legislative commitment vs ministerial announcement is real. |
| Q5-T1-013 | VERIFIED@0.9 | PARTIAL@0.81 | **PARTIAL** | Codex caught: visible span explicitly shows principles 2/3/4 (affordability / appropriate use / universal coverage) but principle 1 (accessibility) is only partially visible as 'ove' (truncated 'improve...'). Claude noted truncation but didn't downgrade. |
| Q5-T1-014 | PARTIAL@0.85 | VERIFIED@0.99 | **PARTIAL** | Claude caught: PBO 2023 universal-single-payer projection ($11.2B/$13.4B) placed inside Bill C-64 phase-1 Regulatory section. Decimals exact but scope-attribution wrong. Codex applied strict span-level rule (decimals match → VERIFIED) without checking section-level framing. **Section-level framing audit is a Tier-1 schema gap.** |

## Reconciled state (28 claims)

| Section | VERIFIED | PARTIAL | Total |
|---|---|---|---|
| Efficacy | 6 | 0 | 6 |
| Comparative | 2 | 1 | 3 |
| Regulatory | 1 | 4 | 5 |
| Population Subgroups | 7 | 0 | 7 |
| Long-term Outcomes | 7 | 0 | 7 |
| **Total** | **23** | **5** | **28** |

(Note: 23 VERIFIED + 5 PARTIAL = 28. Slight discrepancy with table-1 reconciled-row above; -010/-011/-013/-014 are 4 PARTIAL + 1 existing PARTIAL on -014 = wait, -014 IS one of the 4. So reconciled = 24V + 4P. Updated table-1 above is correct: 24V + 4P. Per-section detail counts -014 in Regulatory PARTIAL bucket.)

Corrected per-section:
- Regulatory: -010 P, -011 P, -012 V, -013 P, -014 P = 1V + 4P
- Other sections: unchanged from Claude pass
- Total: 24 VERIFIED + 4 PARTIAL ✓

## Materiality + claim_type cross-tab (reconciled)

| Materiality | Count |
|---|---|
| critical | 4 |
| major | 13 |
| minor | 11 |
| background | 0 |

| Claim type | Count |
|---|---|
| economic | 18 |
| epidemiology | 5 |
| regulatory | 5 |

(Claude and Codex agreed on claim_type for all 28 — schema field is unambiguous.)

## Notable pilot findings

### 1. Codex's stricter span-level rule is correct on Q5-T1-010/011/013
Claude was too lenient by accepting page-metadata-derived dates or paraphrasing differences ("legislation commits" vs "Minister announced government's plan"). For clinical/policy audit, the span must EXPLICITLY support the assertion. Codex's stricter span-level rule is the right calibration for §-1.1.

### 2. Claude's section-level framing rule is correct on Q5-T1-014
Codex applied span-level rule narrowly (decimals match → VERIFIED) without checking that the PBO universal-single-payer numbers are placed inside the Bill C-64 phase-1 Regulatory section. This framing issue is a real production bug requiring section_blueprint fix. **Tier-1 schema gap:** section-level scope-attribution audit is not currently a structured field.

### 3. Inter-rater agreement: 86% (24/28)
At span-level + materiality + verdict, the two reviewers agree 24/28 times. The 4 disagreements all reduce to "what counts as support" — either span-vs-metadata, paraphrasing-fidelity, or section-vs-claim framing. None of the disagreements concern decimals being wrong; they concern STRICTNESS of context-match.

### 4. Zero fabrications across 28 claims (both reviewers)
Both Claude and Codex agree: Q5 Pharmacare has 0 fabricated claims at strict span-level audit. Every decimal in the report appears in some cited span. This is strong evidence for POLARIS's faithfulness baseline.

### 5. Generator-redundancy finding (Claude-only, missed by Codex)
11 of 28 claims (~40%) are duplicate-fact instances:
- 4× regressivity (3%/1.6%/0.7%) in Q5-T1-002, 008, 018, 025
- 3× OOP 2007 (8.7%/4.8%) in Q5-T1-003, 009, 026
- 2× age 55-64 non-adherence (9.2%/13.9%) in Q5-T1-015, 023
- 2× lower-income burden in Q5-T1-017, 024

Codex did not flag this because each claim individually verified. **Tier-1 schema gap:** need a `fact_unit_id` + `duplicate_of` cross-claim field.

## Operational metrics (the pilot's main deliverable)

| Metric | Value |
|---|---|
| Claims audited | 28 |
| Reviewers | 2 (Claude, Codex independent) |
| Single-shot Codex 28-claim attempt | FAILED to produce structured output |
| Codex batched approach | 4 batches × 7 claims = 100% success |
| Claude minutes/claim (estimated) | ~4 |
| Codex minutes/claim (4 batches @ ~5 min each / 7 claims = ~0.7 min) | **0.7** (LLM batched) |
| Total Codex wall-clock | ~20 minutes for 28 claims |
| Inter-rater agreement | 86% (24/28) |
| Material disagreements requiring reconciliation | 4 |
| Deferral rate (confidence < 0.7) | 0 |
| Mean confidence Claude | 0.97 |
| Mean confidence Codex | 0.95 |

## v2 schema lock recommendations

Add to Tier-1:
1. **`fact_unit_id`** (canonical fact identifier) + **`duplicate_of: claim_id`** for cross-claim redundancy detection
2. **`section_scope_match`** field: yes/partial/no — does the claim's section context match the cited source's scope? (Catches Q5-T1-014-style framing issues)
3. **`span_explicit_date`** field: when claim asserts a date, must the date appear in the cited span (not just page metadata)? Boolean. (Catches Q5-T1-010-style metadata-vs-span issues)
4. **`paraphrase_fidelity`**: exact-quote / strong-paraphrase / weak-paraphrase / divergent. (Catches Q5-T1-011-style "commits" vs "announced plan" distinctions)

Keep in Tier-1:
- 5-verdict (works)
- materiality (works, especially for triaging minor duplicates)
- claim_type (works, unambiguous)
- citation_context_match (works but should be refined per above)
- reviewer_confidence (works)
- rationale (works)

Defer to Tier-2 (high-materiality only):
- GRADE certainty
- RoB 2 / ROBINS-I / QUADAS-2 (only RCT/observational/diagnostic — Q5 had none)
- AMSTAR-2 (only SR/MA — Q5 had Morgan 2017 critical appraisal, would apply)
- PRISMA 2020 (only SR/MA)
- PICO/PECO (clinical only)
- ICMJE COI flags
- Effect direction + size

## Carney delivery context

This pilot took ~2.5 hours of compute (incl. Codex batched runs) to audit ONE report at depth. For 5 Carney reports + tirzepatide, scaling factor ≈ 6. Estimated total: ~15 hours of cumulative compute. Feasible in 4-month window.

**Per Codex's earlier ENDORSE_WITH_AMENDMENTS:** "Run a one-report pilot before locking v2 schema." Pilot complete. Schema v2 lock should incorporate the 4 new field recommendations above, then extend to all 6 reports.
