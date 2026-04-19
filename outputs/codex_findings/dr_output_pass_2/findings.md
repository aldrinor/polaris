---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_2_tirzepatide_v5
commit: 17c16c1
delta_vs_pass1: "Material classifier-level improvement: V5 promoted NEJM SURMOUNT-5 to T1, removed Facebook from the bibliography, raised T1+T2 bibliography share from 41.7% to 63.0%, and reduced T7 bibliography share from 33.3% to 22.2%. Content quality still fails top-tier DR because core SURPASS claims rely on a Lilly-authored review/perspective and PRNewswire rather than primary SURPASS papers available in corpus; out-of-scope obesity/T1D material remains; contradiction disclosures are unadjudicated and uncited."
citations_verified: 14/20
t1_t2_percentage_of_bibliography: 62.96%
t7_percentage_of_bibliography: 22.22%
faithfulness_verdict: "Numerically often faithful to cited snippets, but not DR-grade: citation authority and adjacency fail for pivotal clinical claims, low-authority sources remain in core prose, and several cited claims are outside the T2D adult question."
coverage_gaps_remaining: ["Primary SURPASS-1 paper not cited despite corpus entry 78 T1 DOI 10.1016/S0140-6736(21)01324-6", "Primary SURPASS-2 NEJM paper absent from V5 corpus/bibliography; only abstract/post-hoc items found", "Primary SURPASS-3 paper not cited despite corpus entry 140 T1 DOI 10.1016/S0140-6736(21)01443-4", "Primary SURPASS-4 paper not cited despite corpus entry 170 T1 DOI 10.1016/S0140-6736(21)02188-7", "Primary SURPASS-5 paper not cited despite corpus entry 129 T1 JAMA DOI 10.1001/jama.2022.0078", "SURMOUNT-2 primary paper was in corpus but not cited; only a T7 abstract/post-hoc SURMOUNT-2 item was cited", "ADA/AACE guideline evidence not cited; FDA label/prescribing evidence not cited"]
structural_hallucinations: ["PMC review/perspective PMC10115620 is still classified and cited as T1 primary evidence", "Contradiction detector mixes unlike endpoints, units, populations, thresholds, and confidence interval percentages into spurious high-severity contradiction lists", "Report treats non-diabetes obesity trials as comparative evidence for a T2D question without consistently flagging population mismatch"]
quantification_quality: "Improved but insufficient: major numeric trial estimates are present, but quantification is source-collapsed, sometimes sourced to low-authority/news items, and contradiction numbers are not endpoint/population normalized."
contradiction_handling: "Fails DR standard: contradictions are listed mechanically, uncited in the disclosure section, not adjudicated by endpoint/population/dose/timepoint, and not integrated into the main conclusions."
vs_gpt54_dr_verdict: "Below GPT-5.4 Deep Research level. A top-tier DR answer would prioritize pivotal RCTs, guidelines/labeling, and endpoint-specific synthesis; V5 still reads as an evidence-collage with weak source selection."
vs_gemini31_pro_dr_verdict: "Below Gemini 3.1 Pro Deep Research level. It has better breadth than V4 but lacks disciplined clinical hierarchy, scope control, and contradiction adjudication."
rationale: |
  V5 is materially better than V4 at the classifier and bibliography-mix level. NEJM SURMOUNT-5 moved from T4 to T1, Facebook disappeared from the bibliography, and T1+T2 bibliography share rose from 41.7% to 63.0%.
  The Deep Research content gap remains material. The pivotal SURPASS program is summarized mainly through a Lilly-authored review/perspective, classified as T1, and a PRNewswire item. Primary SURPASS-1, SURPASS-3, SURPASS-4, and SURPASS-5 papers were present in the V5 corpus but not cited in the final report; SURPASS-2 primary NEJM was not present as a final cited source. SURMOUNT-2 primary evidence was in corpus but V5 cited only a T7 abstract/post-hoc item for a broad consistency claim.
  The report continues to include obesity-without-diabetes and type 1 diabetes claims in a question scoped to adults with type 2 diabetes. Some of those claims are clearly labeled, but their prominence in Comparative and Population Subgroups distorts the answer.
  Qwen's partial gate is substantively correct: citation tightness and hedging are not acceptable. The limitations and contradiction sections lack citations, and superiority language remains too broad given mixed populations and indirect comparisons.
---

**Verdict**

MATERIAL-GAPS-FIX-AND-RESWEEP. V5 is not top-tier Deep Research. It is better than V4, but the remaining defects are substantive, not cosmetic: primary evidence selection is still weak, source tiers still contain a major false T1, clinical scope remains leaky, and contradiction handling is not analytical.

**Quantitative V5 vs V4 Summary**

- V4 bibliography: 24 citations; T1=2, T2=8, T4=4, T6=2, T7=8.
- V5 bibliography: 27 citations; T1=6, T2=11, T6=2, T7=6, UNKNOWN=2.
- T1+T2 share improved from 10/24 = 41.67% to 17/27 = 62.96%.
- T7 share improved from 8/24 = 33.33% to 6/27 = 22.22%.
- NEJM SURMOUNT-5 DOI 10.1056/NEJMoa2416394: cited in V4 as T4; cited in V5 as T1.
- Facebook post: cited in V4 bibliography as [14] T7; absent from V5 bibliography, though still present in the approved V5 live corpus as T6.
- PRNewswire: still cited in V5 bibliography [3] T6 and used in core efficacy prose.
- Pharmacy Times: absent from V5 bibliography but still present in live corpus as T6.
- Manifest gate: partial; release_allowed=false; critical axes are citation_tightness and hedging_appropriateness.
- Qwen said citation_tightness needs revision because contradiction disclosures and limitations lack citations; hedging_appropriateness needs revision because superiority claims are insufficiently hedged against contradiction disclosures.

**Criterion-by-criterion (a-h)**

a. Source authority and hierarchy: Fail. V5 still uses a Lilly-authored review/perspective, PMC10115620, as [1] T1 for the SURPASS program. That article is a review/perspective with multiple Lilly employees and Lilly funding, not a primary RCT. PRNewswire remains a cited core efficacy source.

b. Primary trial coverage: Fail. The V5 corpus contains primary SURPASS-1, SURPASS-3, SURPASS-4, and SURPASS-5 entries, but the report does not cite them. SURPASS-2 primary NEJM is absent from the cited bibliography and only abstract/post-hoc SURPASS-2 items appear in corpus search output. This repeats a central pass-1 gap.

c. Citation tightness and adjacency: Partial/fail. Numeric claims usually have adjacent markers, but several citations are the wrong authority layer. Limitations and contradiction disclosures are uncited. Qwen independently flagged this as needs_revision.

d. Scope discipline: Fail. The question is adults with T2D; the Comparative section heavily uses obesity-without-diabetes evidence, and Population Subgroups includes a T1D obesity retrospective abstract. These should be secondary context, not central answer material.

e. Causal and comparative hedging: Fail. "Superior to active comparators" is overbroad and uses a PRNewswire citation. Indirect treatment comparisons, network meta-analyses, real-world cohorts, and non-diabetes obesity RCTs are not consistently distinguished from direct T2D RCT evidence.

f. Contradiction adjudication: Fail. The report lists 11 contradictions but does not resolve them by endpoint, unit, population, dose, estimand, or timepoint. The contradiction engine itself appears to mix HbA1c percentages, body-weight percentages, threshold percentages, CI values, and comparator-adjacent values.

g. Quantification quality: Partial. Many headline values are plausible and match cited/source snippets, including SURPASS range estimates and SURMOUNT-5 weight loss. But estimates are source-collapsed through a review and low-authority articles rather than primary trials, and uncertainty is inconsistently carried through.

h. DR-grade synthesis and clinical usefulness: Fail. The report is organized and readable, but it is not a top-tier clinical evidence synthesis. A top-tier answer would separately synthesize SURPASS-1/2/3/4/5 primary RCTs, SURPASS-6, SURMOUNT-2 if relevant, guideline/label safety constraints, and endpoint-specific safety tradeoffs.

**Citation-Level Audit Sample (20 citations) - V5**

1. Line 5, SURPASS dose-dependent glycemic/weight improvement [1]: directionally supported, but [1] is a review/perspective misclassified as T1, not primary evidence. Partial.
2. Line 5, A1C range -1.87% to -2.59% [1]: numerically consistent with the review and known SURPASS summaries. Pass on numeric faithfulness; fail on authority.
3. Line 5, SURPASS-1 15 mg A1C -2.07% and 52% normoglycemia [1][2]: supported by SURPASS-1 summaries; [2] is T7 abstract and the primary Lancet RCT was in corpus but not cited. Partial.
4. Line 5, A1C <7.0% range 81-97% [1]: likely faithful to review table. Partial due non-primary citation.
5. Line 5, weight range -6.2 kg to -12.9 kg [1]: likely faithful to review table. Partial due non-primary citation.
6. Line 5, superior to semaglutide 1 mg and insulin regimens [1][3]: overbroad and cites PRNewswire. Fail.
7. Line 5, effects consistent across populations/background therapies [1][4]: overgeneralized; [4] is T7 SURMOUNT-2 post-hoc abstract, not adequate for broad SURPASS consistency. Fail.
8. Line 9, SURMOUNT-5 obesity without diabetes -20.2% vs -13.7% [5]: faithful to NEJM/PubMed abstract. Pass, but population is out-of-scope for the main question.
9. Line 9, more likely to achieve >=10/15/20/25% weight reductions [5]: faithful to NEJM/PubMed abstract. Pass, but out-of-scope.
10. Line 9, same -20.2% vs -13.7% from Drug Topics [6]: redundant and low/unknown authority when NEJM is already cited. Fail.
11. Line 9, 6-month real-world obesity without diabetes [7]: likely faithful to cited cohort title/summary. Partial because out-of-scope.
12. Line 9, meta-analysis says tirzepatide superior to semaglutide [8]: faithful to PubMed abstract. Partial because mixed obesity population and study designs need more hedging.
13. Line 9, T2D NMA comparable to semaglutide 2.0 and superior to 1.0/0.5 [9]: plausible and appropriately cites T2 systematic review. Pass.
14. Line 9, indirect comparison versus semaglutide 2.4 in obesity/T2D [10]: citation matches claim and indirect nature is stated. Pass.
15. Line 9, insulin meta-analysis with lower hypoglycemia [11]: plausible and appropriately cites T2 meta-analysis. Pass.
16. Line 9, SURPASS-6 HbA1c -2.1% vs -1.1% insulin lispro [12]: faithful to SURPASS-6 RCT. Pass.
17. Line 9, head-to-head obesity adverse-event percentage [5][6]: GI-common claim is supported by NEJM, but exact "76.7%/79%" is sourced to UNKNOWN Drug Topics. Fail.
18. Line 13, GI adverse event incidences by dose [15]: supported by cited meta-analysis. Pass.
19. Line 13, thyroid cancer FAERS ROR [19]: source is UNKNOWN EMJ news rather than primary FAERS analysis; pharmacovigilance causality is underemphasized. Fail.
20. Line 21, T1D obesity retrospective study [26]: likely faithful to abstract, but outside the scoped T2D question and T7. Fail for DR relevance.

**URL Quality Audit (20 URLs sampled)**

1. [1] PMC10115620: peer-reviewed review/perspective, not T1 primary; Lilly funding/COI. Misclassified and overweighted.
2. [2] DOI 10.2337/db21-100-or: ADA abstract, T7; acceptable only as backup, not primary SURPASS-1 evidence.
3. [3] PRNewswire Lilly release: T6 sponsor/news source; unacceptable for core clinical efficacy when primary RCTs exist.
4. [4] DOI 10.2337/db24-227-or: ADA abstract/post-hoc SURMOUNT-2; weak for broad consistency claims.
5. [5] DOI 10.1056/NEJMoa2416394: T1 RCT; classifier fix worked. Population is obesity without diabetes, so scope must be explicit.
6. [6] DrugTopics: UNKNOWN/news; should not duplicate NEJM primary result.
7. [7] DOI 10.1007/s40618-025-02792-1: observational/real-world obesity management; lower causal strength and not T2D-specific.
8. [8] DOI 10.7759/cureus.86080: systematic review/meta-analysis; usable with caution, Cureus quality should be treated conservatively.
9. [9] Springer Diabetologia PDF: T2 systematic review/NMA; appropriate for indirect comparative context.
10. [10] DOI 10.1111/dom.16401: indirect treatment comparison; useful but not primary, and should be hedged.
11. [11] DOI 10.1038/s41366-024-01621-4: T2 meta-analysis; acceptable secondary synthesis.
12. [12] PMC10548360: SURPASS-6 RCT; good primary evidence but not a substitute for SURPASS-1/2/3/4/5.
13. [13] DOI 10.4103/jod.jod_213_24: T2 review/meta-analysis; acceptable secondary source.
14. [14] DOI 10.1007/s13300-025-01728-5: T2 network meta-analysis; acceptable with indirect-comparison hedging.
15. [15] Oxford JES adverse-events meta-analysis: good safety synthesis, but should be complemented by label/guidance.
16. [16] Frontiers 2025 meta-analysis: acceptable with caution; title suggests weight-loss patients, not necessarily T2D-only.
17. [17] Frontiers 2023 safety review: acceptable safety synthesis, not primary.
18. [18] EndocrinologyAdvisor: T6 news; should not support hypoglycemia safety claims when primary/post-hoc papers are available.
19. [19] EMJ Reviews news: UNKNOWN; not adequate for thyroid cancer pharmacovigilance claims.
20. [20] Frontiers 2022 dose meta-analysis: acceptable secondary source; not a substitute for dose-specific RCT tables.

**Run Log Anomalies**

- Run log status line says status ok_qwen_advisory while manifest.status is partial_qwen_advisory and release_allowed=false. The run log itself notes the mismatch.
- Corpus material_deviation=true: actual distribution T1=15%, T4=22%, T7=32%, UNKNOWN=11% against expected T1 30-60%, T4 0-20%, T7 0-10%.
- Adequacy still proceeds despite T7=32%, because threshold allows T7 up to 40%. That threshold is too permissive for clinical DR.
- Evidence selection selected all 235 rows with dropped_count=0; no final selection pressure removed lower-authority sources.
- Verification dropped 9 generated sentences, including thyroid boxed warning text with malformed provenance tokens. The final report still lacks authoritative label/guideline safety framing.
- PT13 failed: 6 unhedged comparative/superlative claims.

**Did M-18 Classifier Fixes Close the DR Pass 1 Gaps?**

- Social platform exclusion effect: Partially closed. Facebook moved out of the V5 bibliography, but the Facebook URL remains in approved live corpus as T6. The exclusion should prevent citation/selection, not merely demote.
- NEJM head-to-head RCT tier promotion effect: Closed for SURMOUNT-5. DOI 10.1056/NEJMoa2416394 is now T1 and cited. However, it is obesity without diabetes, so the content generator must keep it secondary to T2D evidence.
- T7 reduction effect: Improved but not closed. Bibliography T7 fell from 33.3% to 22.2%, but V5 still cites six T7 items, including abstracts for SURPASS/SURMOUNT subgroup claims. Corpus T7 remains 31.9%.

**Remaining DR Gaps After M-18**

- Primary SURPASS papers are not used as the backbone of the answer despite being available in corpus for SURPASS-1, SURPASS-3, SURPASS-4, and SURPASS-5.
- SURPASS-2 primary NEJM is not cited; the corpus search found only post-hoc/abstract SURPASS-2 records and an exploratory SURPASS-2/3 analysis.
- SURMOUNT-2 primary trial is in the corpus as a T7 entry but not cited; classifier likely under-ranked it and generator cited a weaker abstract.
- Guideline/label coverage is inadequate. ADA/AACE/FDA prescribing-label sources are absent from the final report; safety section relies on meta-analyses and news for thyroid risk instead.
- Source-tier classification still mislabels PMC review/perspective [1] as T1. This is a direct recurrence of the pass-1 "PMC review as T1" problem.
- Low-authority sources remain in bibliography and main prose: PRNewswire [3], EndocrinologyAdvisor [18], DrugTopics [6], EMJ Reviews [19].
- Out-of-scope material remains prominent: obesity without diabetes, T1D obesity, HFpEF obesity strata. These can be context, but not central answer content for adults with T2D.
- Contradiction disclosures are not useful: they are uncited, not adjudicated, and include obvious extraction artifacts such as 95% confidence interval values treated as body-weight outcomes.

**Required Fix**

1. Enforce a clinical generator/source-selection rule: pivotal trial claims must cite primary RCTs when present. For this topic, force SURPASS-1 DOI 10.1016/S0140-6736(21)01324-6, SURPASS-2 DOI 10.1056/NEJMoa2107519, SURPASS-3 DOI 10.1016/S0140-6736(21)01443-4, SURPASS-4 DOI 10.1016/S0140-6736(21)02188-7, and SURPASS-5 DOI 10.1001/jama.2022.0078 where available.
2. Fix classifier logic so reviews/perspectives in PMC are not T1 unless article type and content prove primary study design. PMC hosting alone must not imply T1.
3. Add a "do not cite low-authority source when same claim has T1/T2 support" selection rule for PRNewswire, DrugTopics, EndocrinologyAdvisor, EMJ Reviews, Pharmacy Times, Facebook, and similar sources.
4. Add scope gating in generator: for a T2D question, obesity-without-diabetes, type 1 diabetes, HFpEF obesity, and GADA-positive subgroup evidence must be explicitly labeled as adjacent/limited and kept secondary.
5. Add contradiction adjudication by endpoint, unit, population, dose, comparator, timepoint, and estimand before disclosure. Do not compare HbA1c reductions, body-weight percent changes, threshold percentages, and CI values as the same predicate.
6. Require citations in Limitations and Contradiction disclosures, or suppress numeric contradiction lists until they can be source-adjacent and adjudicated.
7. Retrieve and cite current ADA Standards/ADA-EASD consensus, AACE guidance if applicable, and FDA prescribing information/label for boxed warning, contraindications, pancreatitis/gallbladder/hypoglycemia cautions, and indication boundaries.
