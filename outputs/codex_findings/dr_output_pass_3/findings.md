---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_3_tirzepatide_v6
commit: 35a0bc2
delta_vs_pass2: V6 materially improved bibliography tier mix and removed PRNewswire/T7 citations from the bibliography, but it still anchors pivotal SURPASS-1/2/3/5 efficacy claims to the Lilly review PMC10115620, leaves SURPASS-4 uncited in the report, keeps mechanical contradiction disclosures, and fails qwen citation-tightness with release_allowed=false.
citations_verified: 20/20
t1_t2_percentage_of_bibliography: 94.7%
t7_percentage_of_bibliography: 0.0%
faithfulness_verdict: Body sentences mostly match cited spans per verifier, but top-line efficacy is not DR-grade because major primary RCT claims are routed through a review when primary trials are present in corpus.
coverage_gaps_remaining: [SURPASS-2 primary trial not cited, SURPASS-3 primary trial not cited for main efficacy, SURPASS-4 primary trial not cited in report, SURPASS-5 primary trial not cited and mis-tiered T7 in corpus, SURMOUNT-2 primary not cited and mis-tiered T7 in corpus, SELECT/LEADER not used for comparator cardiovascular context]
structural_hallucinations: [Methods says corpus adequacy passed despite actual tier distribution missing expected T1/T2/T4/T7 bands, contradiction disclosures present unaudited numeric dumps without source attribution]
quantification_quality: Good plain-English quantification in efficacy and dose-response sections, but contradiction quantification is uninterpreted and mixes incompatible endpoints, populations, doses, and units.
contradiction_handling: Still mechanical. V6 lists 12 numeric contradiction clusters but does not adjudicate by endpoint, source tier, population, time horizon, or trial authority.
vs_gpt54_dr_verdict: Below top-tier Deep Research due to weak primary-source anchoring, shallow synthesis, no contradiction adjudication, and failed release gate.
vs_gemini31_pro_dr_verdict: Below top-tier Deep Research for the same reasons; improved citation hygiene is not sufficient for final-quality DR.
rationale: |
  M-19 worked directionally: V6 bibliography shifted from 63.0% T1+T2 and 22.2% T7 in V5 to 94.7% T1+T2 and 0% T7 in V6, and PRNewswire disappeared. However, the pass-2 material gap was not fully closed. The most important efficacy paragraph still cites the Lilly review for SURPASS-1/2/3/5 pooled facts instead of the primary RCT papers that are present in the corpus. SURPASS-4 is present in the corpus as T1 but absent from the report. SURPASS-5 and SURMOUNT-2 appear present but are classified T7 and not used. Qwen specifically flags citation tightness, and the manifest blocks release. Top-tier DR requires primary-trial anchoring and adjudicated contradictions, not just cleaner bibliography tiers.
---

**Verdict**

MATERIAL-GAPS-FIX-AND-RESWEEP. V6 is a substantial improvement over V5, but it does not meet top-tier Deep Research quality. The bibliography is now primary/review-heavy and excludes PRNewswire/T7 citations, but the report still fails the central pass-2 requirement: use primary pivotal SURPASS evidence when it is available, especially for the top-line efficacy claims.

**Quantitative V6 vs V5 Summary**

V5 bibliography: 27 citations - T1 6, T2 11, T6 2, T7 6, UNKNOWN 2. T1+T2 = 63.0%; T7 = 22.2%.

V6 bibliography: 19 citations - T1 10, T2 8, T4 1, T6 0, T7 0, UNKNOWN 0. T1+T2 = 94.7%; T7 = 0.0%.

V6 manifest: status `partial_qwen_advisory`; `release_allowed=false`; corpus count 311; corpus tier fractions T1 15.43%, T2 14.47%, T4 25.72%, T7 30.87%; generator words 984; limitations words 79; contradictions_found 12; qwen critical axis `citation_tightness`.

**Criterion-by-criterion**

a. Faithfulness: Mixed. The verifier kept 29 sentences and dropped 8. The kept body claims generally have adjacent evidence spans. However, source selection is not faithful to DR hierarchy: SURPASS-1/2/3/5 numeric efficacy facts are cited to [1], the review `PMC10115620`, while primary RCTs for SURPASS-1, SURPASS-3, and SURPASS-4 are present in the corpus. This is not top-tier citation practice.

b. Evidence quality: Improved at bibliography level. The visible bibliography is 94.7% T1+T2 and 0% T7. But citation [1] is still the prior Lilly review, classified T1 by the pipeline, and it dominates the core efficacy paragraph. A high T1+T2 count does not fix mis-anchoring of the most important claims.

c. Coverage: Partial. V6 cites SURPASS-6 [2], SURPASS-AP-Combo [3], SURPASS-2/3 exploratory timing [14], and SURPASS-3 MRI [19]. It mentions SURPASS-1/2/3/5 through review [1]. It does not cite the primary SURPASS-1, SURPASS-2, SURPASS-3, SURPASS-4, or SURPASS-5 main trial papers for their core efficacy/safety results. SURPASS-4 is absent from report text. SURMOUNT evidence appears only as related obesity/non-diabetes dose-response context, not as properly scoped SURMOUNT-2 T2D-obesity evidence. SELECT/LEADER are not used, though for this question they are comparator/contextual rather than mandatory tirzepatide evidence.

d. Scope: Improved from V5. The explicit V5 type 1 diabetes subgroup leakage is gone. Obesity-only content remains in line 17 but is flagged as a related obesity trial without diabetes, which is acceptable as supportive context. Safety line 13 uses a related obesity/overweight population and flags the mismatch. Remaining issue: comparative section still leans heavily into obesity/overweight semaglutide comparisons rather than centering adults with T2D.

e. Argumentation: Directional but not integrated enough. Sections mostly list findings: efficacy trials, comparative meta-analyses, safety observations, dose-response, mechanism. There is limited synthesis of when tirzepatide is strongest, how background insulin/metformin/SGLT2 therapy changes interpretation, or how the safety tradeoff should be weighted against glycemic and weight endpoints.

f. Contradictions: Not adjudicated. Lines 42-53 list 12 contradiction clusters as raw values and relative differences. They do not identify which values are from RCTs versus T4/T7/news, which are percent body-weight change versus percent achieving threshold, which are HbA1c values mistakenly extracted as weight values, or which are obesity-only versus T2D populations. This remains mechanical.

g. Structural hallucinations: No invented clinical topic section like V5's Population Subgroups, but the Methods/Limitations create structural overclaim. The report says corpus adequacy passed 7/7 while also reporting actual tier distribution far outside expected T1/T2/T4/T7 ranges. The contradiction section gives an appearance of audit rigor without source-level attribution.

h. Plain-English quantification: Good in the main prose. A1C, body weight, confidence intervals, ROR, and dose-response quantities are readable. Poor in contradictions: the numeric dumps are not plain-English explanations and would confuse a clinical reader.

**Citation-Level Audit Sample (20 citations)**

1. Line 5 claim, "pivotal SURPASS phase 3 trials ... superiority" cites [1]. Supported by review, but not primary anchored. Not DR-grade.
2. Line 5 SURPASS-1 A1C -1.87% cites [1]. Primary SURPASS-1 T1 is present in corpus but not cited.
3. Line 5 SURPASS-5 A1C -2.59% cites [1]. Main SURPASS-5 article appears in corpus but is classified T7 and not cited.
4. Line 5 SURPASS-2 A1C reductions vs semaglutide cites [1]. Main SURPASS-2 primary paper is not cited; only abstract/post-hoc entries appear in corpus search output.
5. Line 5 A1C <7.0% 81-97% cites [1]. Review-supported, but should be backed by individual SURPASS primary trials.
6. Line 5 SURPASS-5 weight -6.2 kg cites [1]. Review-supported, not primary anchored.
7. Line 5 SURPASS-3 weight -12.9 kg cites [1]. Primary SURPASS-3 T1 is present but not cited for this main efficacy claim.
8. Line 5 SURPASS-6 HbA1c -2.1% vs -1.1% cites [2]. Properly anchored to T1 primary SURPASS-6.
9. Line 5 SURPASS-AP-Combo HbA1c reductions cites [3]. Properly anchored to T1 primary AP-Combo.
10. Line 5 AP-Combo body weight reductions cites [3]. Properly anchored to T1 primary AP-Combo.
11. Line 9 indirect comparison tirzepatide vs semaglutide 2.4 mg cites [4]. Citation matches population with obesity/overweight and T2D, but it is indirect and should be framed as such.
12. Line 9 direct comparative meta-analysis cites [5]. Citation supports comparison but is obesity/overweight focused, not pure T2D.
13. Line 9 basal-insulin GLP-1 RA network meta-analysis cites [6]. Appropriate T2 support, but secondary evidence.
14. Line 13 safety profile similar to GLP-1RAs cites [7]. Bibliography labels [7] T1, but title is real-world safety profile; this is not RCT primary evidence despite prose saying "In randomized controlled trials."
15. Line 13 GI adverse events systematic review cites [8]. Appropriate T2 support.
16. Line 13 pharmacovigilance nausea/vomiting/diarrhea cites [9]. Appropriate T4 support for real-world reporting, with inherent reporting-bias limitations.
17. Line 13 severe hypoglycemia in related obesity/overweight population cites [10]. Scoped as related population, acceptable but not central T2D safety evidence.
18. Line 17 dose-response meta-analysis cites [11]. Appropriate T2 support.
19. Line 17 obesity without diabetes dose-response cites [13]. Scope mismatch is flagged, acceptable as supportive only.
20. Line 21 SURPASS-3 MRI mechanism claim cites [19]. Properly anchored to a T1 substudy, but mechanism section remains secondary to the clinical question.

**Did M-19 Prompt Changes Close the DR Pass 2 Gaps?**

Partially.

Closed: PRNewswire is gone from V6 bibliography. T7 citations are gone from the bibliography. Explicit T1D section leakage is removed. Obesity-only material is more often flagged as related/non-diabetes context.

Not closed: Lilly review `PMC10115620` is still citation [1] and still anchors the lead efficacy paragraph. Primary SURPASS-1/3/4 papers are present in the corpus but not used for main efficacy claims. SURPASS-4 is not discussed. SURPASS-5 is not properly classified or used as a primary source. Contradiction handling is still a raw detector dump. Qwen still flags citation tightness and the run is not release allowed.

**Remaining DR Gaps After M-19**

1. Primary-source anchoring gap: Replace review-based SURPASS-1/2/3/4/5 efficacy claims with direct citations to the primary RCTs wherever present. If a primary article is absent or mis-tiered, fix retrieval/tier classification before generation.
2. SURPASS-4 omission: Include the SURPASS-4 primary RCT, especially because it addresses high cardiovascular-risk T2D patients and insulin glargine comparison.
3. SURPASS-5 mis-tiering: The JAMA SURPASS-5 randomized clinical trial is classified T7 in corpus output. That classification is materially wrong and likely prevents proper use.
4. Contradiction adjudication gap: Replace raw contradiction lists with a clinical adjudication table or prose that separates endpoints, time horizons, populations, units, and source tiers.
5. Citation-tightness gate: Qwen flags uncited limitations and contradiction values. The manifest has `release_allowed=false`; top-tier DR cannot pass while the system's own evaluator blocks release.
6. Synthesis gap: The report is concise but too list-like. It needs an integrated conclusion that weighs glycemic efficacy, weight loss, dose escalation, GI tolerability, hypoglycemia with insulin/sulfonylureas, and population/background therapy.

**Required Fix**

Run another iteration. Required changes are substantive, not cosmetic:

1. Fix tier classification for primary clinical RCT PDFs/articles, especially SURPASS-5 and SURMOUNT-2.
2. Force citation selection for top-line efficacy to primary RCTs before reviews: SURPASS-1, SURPASS-2, SURPASS-3, SURPASS-4, SURPASS-5, SURPASS-6, and AP-Combo.
3. Keep reviews/meta-analyses for synthesis only after primary trials are cited.
4. Regenerate contradiction handling as adjudication, with source-tier/source-url attribution and endpoint normalization.
5. Do not release until qwen citation_tightness is at least good and `release_allowed=true`.
