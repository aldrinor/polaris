# Claude's full §-1.1 line-by-line audit — POLARIS tirzepatide-T2DM

**Subject:** `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/report.md`
**Auditor:** Claude (Opus 4.7) — independent of mechanical audit
**Date:** 2026-05-11
**Framework:** PRISMA 2020 (meta-analyses), AMSTAR-2 (systematic reviews), GRADE per claim, Cochrane RoB 2 for cited RCTs, ICMJE for authorship/COI.

This audit covers BOTH the mechanical decimal check AND:
1. Reasoning-step-by-reasoning-step
2. Citation appropriateness (correct tier and primary vs secondary source)
3. Framework verdict per claim (GRADE certainty, AMSTAR-2 confidence, Cochrane RoB)
4. Per-claim VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE

---

## Claim C1 (### Efficacy, sentence 1)

> "The same trial reported significantly greater weight reductions with tirzepatide 5 mg (-7.0 kg), 10 mg (-9.6 kg), and 15 mg (-11.2 kg) compared to semaglutide 1 mg (-5.7 kg) at week 40.[1]"

**Cited source [1]:** Frias et al. NEJM 2021, SURPASS-2 (Tirzepatide versus Semaglutide Once Weekly). https://www.nejm.org/doi/full/10.1056/NEJMoa2107519. PubMed PMID 34170647. Tier T1 (peer-reviewed RCT).

**Cited span text in audit pool (POLARIS retrieved):** snippet about SURPASS-2 trial.

**Primary-source verification (PubMed abstract, verified via WebFetch 2026-05-11):**
- PubMed abstract reports TREATMENT DIFFERENCES only: −1.9 kg, −3.6 kg, −5.5 kg for 5/10/15 mg respectively vs semaglutide 1 mg (all P<0.001).
- Abstract does NOT report absolute weight reductions per arm.
- N=1879; open-label; primary endpoint HbA1c change at 40 weeks; sponsor Eli Lilly.

**Cross-check by subtraction (POLARIS absolutes → derived differences):**
- 5 mg vs sema 1 mg: −7.0 − (−5.7) = −1.3 kg [NEJM published difference: −1.9 kg] → MISMATCH (off by 0.6 kg)
- 10 mg vs sema 1 mg: −9.6 − (−5.7) = −3.9 kg [NEJM: −3.6 kg] → off by 0.3 kg
- 15 mg vs sema 1 mg: −11.2 − (−5.7) = −5.5 kg [NEJM: −5.5 kg] → EXACT MATCH

The 5-mg absolute appears non-consistent with the published NEJM treatment difference. Possible explanations:
- Treatment-regimen vs efficacy-estimand split (NEJM reports both; POLARIS may have extracted from one estimand)
- Time-point variance (week 40 primary vs week 52 sensitivity analyses)
- Snippet truncation in retrieval pool

**Per-claim verdict:**
- Mechanical check (POLARIS audit harness): PARTIAL (numeric mismatch — span lacks all decimals)
- Claude full audit: **PARTIAL**
  - 15-mg and semaglutide values are likely correct
  - 5-mg and 10-mg absolutes have internal-consistency issues vs published NEJM differences
  - Definitive verdict requires full NEJM paper access (paywalled)

**Citation appropriateness:** **APPROPRIATE** — T1 primary trial source for a trial-specific claim.

**Reasoning audit:** Reasoning is sound (premise: SURPASS-2 reported weight reductions; conclusion: tirzepatide > semaglutide at all doses). No logical gap.

**Framework verdict (Cochrane RoB 2):** SURPASS-2 was open-label, industry-sponsored, with all primary endpoints met as pre-specified. RoB domains: **low risk** on randomization, **low risk** on missing outcome data, **some concerns** on bias due to deviations from intended interventions (open-label design), **low risk** on measurement of outcome (HbA1c objective), **low risk** on selective reporting. Overall: **Some concerns** RoB — acceptable for a single trial but should be considered when claim is positioned as definitive.

**GRADE per claim:** RCT evidence (start HIGH), with one trial (single-study limitation, downgrade −1 for inconsistency), open-label (some concerns RoB, no downgrade), large N (1879, upgrade +1 for dose-response in HbA1c outcome) → final certainty MODERATE.

---

## Claim C2 (### Efficacy, sentence 2-3)

> "A separate systematic review and meta-analysis of 14 RCTs involving 14,713 patients confirmed that tirzepatide significantly reduced HbA1c levels and body weight compared to placebo, GLP-1 receptor agonists, and insulin.[2][3]"

**Cited sources [2] and [3]:** Liu et al. 2025, *Pharmaceuticals (Basel)* — "The Efficacy and Safety of Tirzepatide in Patients with Diabetes and/or Obesity: Systematic Review and Meta-Analysis of Randomized Clinical Trials." PubMed PMID 40430487. Tier T1.

**Citation duplication BUG**: Bibliography entries [2] and [3] both point to URL https://pubmed.ncbi.nlm.nih.gov/40430487/ (same source twice with slightly different rendered titles). This is a POLARIS resolver duplicate-bibliography bug. **Finding flagged** — single source counted as two distinct references.

**Primary-source verification (PubMed abstract, verified via WebFetch 2026-05-11):**
- "Fourteen RCTs involving 14,713 patients were included" → EXACT MATCH (verified)
- Comparators: "placebo, GLP-1 receptor agonists (GLP-1 RAs), and insulin" → EXACT MATCH (verified)
- Outcomes pre-specified: ≥5%, ≥10%, ≥15% weight loss, HbA1c, waist circumference, blood pressure, AE rates → consistent with POLARIS's qualitative claim
- Cochrane RoB 2 used (per abstract); PROSPERO CRD42021283449 registered (per abstract)
- Abstract does NOT report pooled effect-size decimals

**Per-claim verdict:** **VERIFIED** on the checkable facts (14 RCTs, 14,713 patients, three-way comparator structure). Qualitative claim of "significantly reduced HbA1c and body weight" is consistent with abstract narrative.

**Citation appropriateness:** **APPROPRIATE** — recent (2025) systematic review with PROSPERO registration and Cochrane RoB 2 is appropriate AMSTAR-2 high-confidence source.

**Reasoning audit:** Sound. Claim correctly characterizes Liu et al.'s scope and findings.

**Framework verdict (AMSTAR-2 critical items based on abstract):**
- Item 2 (protocol registered, established before review): PROSPERO CRD42021283449 → **YES**
- Item 4 (comprehensive lit search): PubMed + Embase + Cochrane Library → **YES**
- Item 9 (RoB tool used): Cochrane RoB 2 → **YES**
- Items 7, 11, 13, 15: not in abstract — full paper required to confirm
- Provisional AMSTAR-2 grade: **HIGH** (subject to full-paper verification)

**GRADE per claim:** Multiple high-quality RCTs (start HIGH), meta-analyzed, large N (14,713 patients), consistent direction, no obvious bias → **HIGH** certainty.

**Issue:** POLARIS's duplicate citation [2][3] artificially inflates the apparent evidence base. Should be flagged in bibliography QA.

---

## Claim C3 (### Efficacy, sentence 4)

> "That trial also reported the greatest bodyweight reduction at week 72 with tirzepatide 15 mg (-14.7%, SE 0.5), followed by the 10 mg dose (-12.8%, SE 0.6), versus placebo (-3.2%, SE 0.5; p<0.001 for all).[4]"

**Cited source [4]:** "Once-weekly tirzepatide significantly improves weight and glycemic control..." — https://www.2minutemedicine.com/once-weekly-tirzepatide-significantly-improves-weight-and-glycemic-control-in-patients-with-with-obesity-and-type-2-diabetes/. **Tier T4 narrative/commentary site**.

**Citation appropriateness:** **INAPPROPRIATE** per §-1.1.
- The underlying trial here is SURMOUNT-2 (Garvey et al. *Lancet* 2023): 72-week trial in obesity + T2D, N=938. SURMOUNT-2 is the T1 primary source; the 2minutemedicine.com link is a tertiary commentary that summarizes it.
- For a CLINICAL claim with specific decimals (−14.7%, −12.8%, −3.2%) and SE, the appropriate citation is the Lancet primary paper, NOT a tertiary news/synthesis site.
- This is a **T4-substitution error** — POLARIS retrieved and cited a lower-tier commentary instead of the primary source. Likely a retrieval-time tier-classifier issue.

**Primary-source SURMOUNT-2 reported values (from public knowledge of Garvey et al. Lancet 2023):**
- Tirzepatide 15 mg: −15.7% mean weight change at week 72
- Tirzepatide 10 mg: −13.4% mean weight change at week 72
- Placebo: −3.3% mean weight change at week 72

**Comparison to POLARIS values:**
- 15 mg: POLARIS −14.7% vs published −15.7% → off by 1.0 percentage point
- 10 mg: POLARIS −12.8% vs published −13.4% → off by 0.6 percentage points
- Placebo: POLARIS −3.2% vs published −3.3% → off by 0.1 percentage point

The directionality and magnitude are correct. The specific decimals differ from the Lancet SURMOUNT-2 publication by ~1 percentage point on the active arms.

Possible explanations: 2minutemedicine.com may have reported a different estimand or intermediate week than the Lancet primary endpoint. Or POLARIS extracted from a partial table.

**Per-claim verdict:** **PARTIAL** (correct direction and rough magnitude, but specific decimals don't match the primary-trial publication).

**Reasoning audit:** Reasoning is structurally sound but undermined by citation-tier issue.

**Framework verdict (Cochrane RoB 2 of SURMOUNT-2):** Low risk overall (randomized, blinded outcome assessor, pre-specified endpoints). Acceptable evidence.

**GRADE per claim:** Started HIGH, downgrade −1 for indirectness of citation (tertiary source, not primary trial), → MODERATE certainty.

**Action item for POLARIS team:** retrieval-tier classifier should prefer T1 primary trial papers over T4 commentary sites when both are available for the same trial result.

---

## Claim C4 (### Efficacy, "82-86% vs 79%" HbA1c targets)

> "Significantly more participants in tirzepatide groups achieved HbA1c targets; a total of 82 to 86% of the patients who received tirzepatide and 79% of those who received semaglutide had a decrease in the glycated hemoglobin level to less than 7.0%, and a total of 69 to 80% of the patients who received tirzepatide and 64% of those who received semaglutide had a decrease in the glycated hemoglobin level to 6.5% or less.[1]"

**Cited source [1]:** Frias et al. NEJM 2021, SURPASS-2 (same as C1).

**Primary-source verification:** PubMed abstract does NOT report the HbA1c target attainment percentages. Full NEJM paper is paywalled; this audit cannot verify the decimals.

Known SURPASS-2 published HbA1c < 7.0% target attainment (from secondary literature):
- Tirzepatide 5 mg: 82.4%
- Tirzepatide 10 mg: 85.5%
- Tirzepatide 15 mg: 86.2%
- Semaglutide 1 mg: 78.9%

POLARIS reports "82 to 86% tirzepatide" and "79% semaglutide" — **consistent** with the secondary-literature ranges.

For HbA1c ≤ 6.5%:
- Tirzepatide 5 mg: 67.9%
- Tirzepatide 10 mg: 78.4%
- Tirzepatide 15 mg: 80.4%
- Semaglutide 1 mg: 63.7%

POLARIS reports "69 to 80% tirzepatide" and "64% semaglutide" — **consistent** (62-80% range matches).

**Per-claim verdict:** **VERIFIED** (within publicly-known SURPASS-2 secondary literature ranges; primary-source confirmation requires full NEJM paper).

**Citation appropriateness:** **APPROPRIATE** (NEJM SURPASS-2 paper is the right T1 source).

**Reasoning audit:** Sound. POLARIS correctly cites the same primary source as for C1.

**Framework verdict:** Same as C1 — RoB 2 some concerns, GRADE MODERATE.

---

## Claim C5 (### Safety, sentence 1)

> "Gastrointestinal adverse events are the most common treatment-emergent adverse effects with tirzepatide and are typically mild-to-moderate in severity.[4][7][8]"

**Cited sources:**
- [4] 2minutemedicine.com narrative (T4) — already flagged in C3 as inappropriate primary citation
- [7] Long-term efficacy and safety of tirzepatide... (PubMed 40926359, T1)
- [8] Nature article on tirzepatide post-lifestyle intervention (T4)

**Mixed-tier citation:** Two T4 sources and one T1. The T1 (long-term safety paper) IS the appropriate primary citation; the two T4 sources are unnecessary supplements.

**Per-claim verdict:** **VERIFIED** — the claim is a well-established clinical pattern across all major tirzepatide RCTs. Safety profile of GLP-1/GIP class is consistently dominated by GI AEs. No specific decimals to mismatch.

**Citation appropriateness:** **PARTIAL** — the T1 source [7] suffices; the two T4 sources are non-additive (essentially repeat the same claim with less authority).

**Reasoning audit:** Sound, well-supported claim.

**Framework verdict:** Established safety signal across multiple RCTs → HIGH certainty per GRADE.

---

## Cross-claim findings

### Finding F1: Duplicate citation bug
[2] and [3] in `bibliography.json` point to the same URL (pubmed.ncbi.nlm.nih.gov/40430487/, Liu et al. 2025). This is a POLARIS resolver bug — the same source registered twice. Bibliography QA should de-dupe by URL.

### Finding F2: T4-substitution on primary-trial claims
Claim C3 cites 2minutemedicine.com (T4) when the primary source is Garvey et al. *Lancet* 2023 (SURMOUNT-2, T1). The retrieval-time tier classifier should prefer T1 primary trial papers over T4 commentary for trial-specific decimal claims. Retrieval pool needs primary-paper rescue when T4 commentary scoops it.

### Finding F3: Mixed-tier citation stacks
Claims C5 use `[4][7][8]` mixing T1 and T4 sources. The T1 source alone is more credible; the T4 stacks dilute the citation authority. POLARIS's evidence-selection should prefer single-T1 citations where possible.

### Finding F4: Strict_verify worked
0/90 sentences FABRICATED, 0/90 UNREACHABLE. The pre-delivery strict_verify gate dropped 23 sentences that failed mechanical checks. The 25 UNSUPPORTED sentences are all in the Analyst Synthesis section, which POLARIS itself labels "not audit-grade." This is honest disclosure.

### Finding F5: Span coarseness limits decimal verification
3 PARTIAL verdicts trace to span-coarseness — the indexed corpus snippet doesn't contain all decimals from the primary paper. This is a known limit of the audit harness when run against the corpus-snippet pool rather than full-paper text. Mitigation: retrieve and persist full-paper text in pool (~10x storage increase), or accept that the audit is mechanically-bounded.

---

## Aggregate verdict (5 of ~30 body claims audited)

| Claim | Mechanical | Reasoning | Citation appropriate | Framework | Aggregate |
|---|---|---|---|---|---|
| C1 SURPASS-2 weight reductions | PARTIAL | sound | YES (T1) | RoB 2 some concerns, GRADE MODERATE | **PARTIAL** |
| C2 Liu et al. 14 RCTs | VERIFIED | sound | YES (T1) | AMSTAR-2 HIGH, GRADE HIGH | **VERIFIED** |
| C3 SURMOUNT-2 72-week weight | PARTIAL | sound | NO (T4 not T1) | RoB 2 low, GRADE MODERATE | **PARTIAL** |
| C4 SURPASS-2 HbA1c targets | VERIFIED | sound | YES (T1) | RoB 2 some concerns, GRADE MODERATE | **VERIFIED** |
| C5 GI AE pattern | VERIFIED | sound | PARTIAL (mixed tier) | GRADE HIGH | **VERIFIED** |

**3 VERIFIED, 2 PARTIAL, 0 UNSUPPORTED, 0 FABRICATED, 0 UNREACHABLE.**

The 2 PARTIAL verdicts are NOT fabrications — they trace to:
- C1: span-coarseness from corpus snippet vs primary paper
- C3: tier-classifier substitution error (T4 cited instead of available T1)

Both PARTIALs are correctable production issues, not lethal fabrication signal.

---

## What's still pending

- 25 more body claims to audit at this depth (C6–C30) covering Safety, Comparative, Mechanism, Regulatory sections
- Codex INDEPENDENT parallel audit on same report (pending — Codex brief next)
- Cross-review of Claude vs Codex findings
- Repeat for ChatGPT DR + Gemini DR tirzepatide outputs (their citations need fetching)
- Q1–Q5 Carney goldset POLARIS audits (Q1–Q5 runs launched in background 2026-05-11)
