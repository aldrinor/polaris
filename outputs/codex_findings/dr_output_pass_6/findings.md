---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_6_tirzepatide_v6
commit: 11f3b32
delta_vs_pass2: "Large bibliography-tier improvement versus V5: T1+T2 rose from 63.0% to 94.7%, T7 fell from 22.2% to 0%, and PRNewswire disappeared from the bibliography. However, the core SURPASS-1/2/3/4/5 claims are still anchored mainly to the Lilly review PMC10115620, misclassified as T1, while primary pivotal SURPASS papers are not individually cited. Contradictions remain mechanically listed, not clinically adjudicated."
citations_verified: 29/29
t1_t2_percentage_of_bibliography: "94.7%"
t7_percentage_of_bibliography: "0.0%"
faithfulness_verdict: "Mostly sentence-level faithful to cited spans by strict_verify, but not DR-grade because core efficacy claims rely on secondary review evidence mislabeled as T1 and several scope-mismatched obesity-only/safety extrapolations remain."
coverage_gaps_remaining: ["SURPASS-1 primary paper not individually cited", "SURPASS-2 primary paper not individually cited", "SURPASS-3 primary paper not individually cited except MRI substudy/time-to-threshold secondary analysis", "SURPASS-4 primary paper not individually cited", "SURPASS-5 primary paper not individually cited", "SELECT not discussed", "LEADER not discussed", "SURMOUNT evidence appears only as related obesity evidence and is not integrated as out-of-scope/contextual comparator"]
structural_hallucinations: ["No invented major section, but bibliography tiering hallucinates/overstates primary status for review-style sources including PMC10115620 and an MDPI mechanistic review."]
quantification_quality: "Improved and numerically dense, but not plain-English DR quality: many values are copied as trial deltas without absolute baseline context, endpoint definitions, populations, comparator hierarchy, or clinical interpretation."
contradiction_handling: "Not adequate. The report lists 12 detector contradictions with raw numeric arrays and relative differences; it does not adjudicate by endpoint, dose, population, unit, comparator, source tier, or extraction artifact status."
vs_gpt54_dr_verdict: "Below top-tier Deep Research: better source selection than V5, but fails on primary-evidence anchoring, contradiction adjudication, and synthesis."
vs_gemini31_pro_dr_verdict: "Below top-tier Deep Research for the same reasons; a strong DR answer would cite the pivotal trials directly and explain heterogeneity instead of dumping detector output."
rationale: |
  V6 is a material improvement over V5, but it is not top-tier DR. The bibliography now excludes T6/T7 citations and the body is mostly adjacent-cited, yet the central efficacy paragraph still uses the Lilly review PMC10115620 as citation [1] for SURPASS-1 through SURPASS-5 rather than citing the named primary trial publications. That directly leaves the main pass-2 gap unresolved. The report also preserves mechanical contradiction disclosures and contains scope leakage from obesity-only evidence. The auto-loop should continue.
---

**Verdict**

MATERIAL-GAPS-FIX-AND-RESWEEP.

Important artifact note: the task text names `outputs/full_scale_v9/...`, but that directory is not the run described in the pass context. Its manifest says `status: abort_evaluator_critical`, `release_allowed: false`, corpus count 259, generator words 702, and 15 bibliography entries. The pass-6/V6 metadata in the prompt matches `outputs/full_scale_v6/clinical/clinical_tirzepatide_t2dm`, so this audit judges that V6 artifact and records the mismatch as a process risk.

**Quantitative V6 vs V5 Summary**

V5 bibliography: 27 citations; T1+T2 = 17/27 = 63.0%; T7 = 6/27 = 22.2%; T6 = 2/27 = 7.4%; UNKNOWN = 2/27 = 7.4%.

V6 bibliography: 19 citations; T1+T2 = 18/19 = 94.7%; T7 = 0/19 = 0.0%; T6 = 0/19 = 0.0%; T4 = 1/19 = 5.3%.

This is a strong directional improvement. It is not sufficient for top-tier DR because the improvement is partly cosmetic: the pivotal SURPASS-1/2/3/4/5 claims are still routed through the broad Lilly review at PMC10115620, which is listed as T1. That source is the same review that pass 2 flagged. PRNewswire is gone from the V6 bibliography, but it remains present in the V6 contradiction pool as `ev_014`.

Manifest check: V6 is `status: partial_qwen_advisory`, `release_allowed: false`, `gate_class: partial`, with Qwen flagging `citation_tightness` as `needs_revision`. Corpus tier mix remains poor: T1 15.43%, T2 14.47%, T4 25.72%, T7 30.87%, UNKNOWN 9.32%. Generator reports 29 verified sentences, 8 dropped sentences, 984 words, and 79 limitations words.

**Criterion-by-criterion**

a. Faithfulness: Conditional pass at sentence-span level, fail at DR level. `verification_details.json` records 29 kept sentences and 8 dropped. I read all kept report sentences. The kept sentences generally map to cited spans, but strict verification is not a substitute for source-quality discipline. The largest problem is citation [1]: the report uses one review article for detailed SURPASS-1/2/3/4/5 efficacy claims rather than the primary RCT papers. That is faithful to the review but not top-tier DR practice.

b. Evidence quality: Numerically improved but still materially defective. The visible bibliography is 94.7% T1/T2 and 0% T7, but T1 classification is inflated. Citation [1] is the Lilly review PMC10115620. Citation [16] is a mechanistic review, also marked T1. Citation [7] is real-world pharmacovigilance and marked T1. DR-grade clinical synthesis should separate primary RCTs, pooled analyses, reviews, pharmacovigilance, and mechanistic reviews clearly.

c. Coverage: SURPASS-6 and SURPASS-AP-Combo now appear directly. SURPASS-3 MRI and a SURPASS-2/3 time-to-threshold analysis appear. However, SURPASS-1/2/3/4/5 primary papers still do not appear individually in the bibliography. SURMOUNT appears indirectly through obesity/overweight evidence, but the report does not make a disciplined scope distinction. SELECT and LEADER are absent. Their absence may be clinically defensible for a tirzepatide T2D efficacy/safety answer, but the audit checklist explicitly asked to check them, so coverage is incomplete against the requested standard.

d. Scope: Improved but still leaky. The report correctly says one dose-response source is a "related obesity trial without diabetes," but it still uses that obesity-only evidence to support dose response in a T2D question. The comparative section uses an overweight/obesity direct-study meta-analysis without sufficiently separating non-diabetes obesity trials from adults with T2D. There is no T1D leakage in the V6 body, unlike V5.

e. Argumentation: Better than V5 but still more list than synthesis. The report strings trial and meta-analysis findings into sections, but it does not build a hierarchy: pivotal RCTs first, then comparative/indirect evidence, then real-world safety, then limitations. It rarely explains why results differ across comparators, background therapy, dose, diabetes status, or time horizon.

f. Contradictions: Fail. V6 still prints 12 raw contradiction bullets with arrays such as `[-62.0, -19.44, 1.29, ... 99.0]` and relative differences. These are visibly mixed units/endpoints/extraction artifacts: HbA1c percentages, body-weight kg/percent, threshold attainment percentages, confidence-interval values, and unrelated obesity endpoints are grouped together. The report does not adjudicate them clinically.

g. Structural hallucinations: No major invented section. Section headings match the topic: Efficacy, Comparative, Safety, Dose Response, Mechanism, Limitations, Methods, Contradiction disclosures. The structural defect is not a fake heading; it is the misleading evidence-tier presentation and the raw contradiction appendix.

h. Plain-English quantification: Partial. The report gives many concrete numbers: HbA1c deltas, kg changes, RORs, mean differences, and time-to-threshold medians. It does not consistently translate them into clinically readable meaning, absolute risk, baseline context, endpoint hierarchy, or population comparability.

**Citation-Level Audit Sample (20 citations)**

1. Report claim: SURPASS phase 3 trials show superiority for A1C and body weight. Citation [1]. Status: supported by review, not primary trial evidence; not DR-grade.
2. A1C range from -1.87% in SURPASS-1 to -2.59% in SURPASS-5. Citation [1]. Status: span-verified, but should cite primary SURPASS-1 and SURPASS-5 papers.
3. SURPASS-2 A1C reductions versus semaglutide 1 mg. Citation [1]. Status: span-verified through review; primary SURPASS-2 absent.
4. A1C <7.0% range 81-97%. Citation [1]. Status: span-verified through review; lacks trial-by-trial source attribution.
5. Body-weight range -6.2 kg to -12.9 kg across SURPASS-5/SURPASS-3. Citation [1]. Status: span-verified through review; primary SURPASS-3/5 absent.
6. SURPASS-6 HbA1c -2.1% vs -1.1% with lispro. Citation [2]. Status: supported by primary RCT.
7. SURPASS-AP-Combo HbA1c -2.24/-2.44/-2.49 vs -0.95. Citation [3]. Status: supported by primary RCT.
8. SURPASS-AP-Combo weight changes -5.0/-7.0/-7.2 kg vs +1.5 kg. Citation [3]. Status: supported by primary RCT.
9. Tirzepatide 10/15 mg vs semaglutide 2.4 mg mean percent weight differences 2.57/4.79. Citation [4]. Status: supported but indirect comparison; needs stronger caveat.
10. Direct comparative meta-analysis SMD 0.75. Citation [5]. Status: supported, but overweight/obesity population is not cleanly T2D-specific.
11. Basal-insulin network meta-analysis vs dulaglutide/exenatide/lixisenatide. Citation [6]. Status: supported as T2 evidence.
12. Safety profile similar to GLP-1RAs. Citation [7]. Status: weakly placed; real-world/pharmacovigilance source marked T1 and overused for general RCT safety framing.
13. GI adverse event incidence consistent with GLP-1RAs. Citation [8]. Status: supported by systematic review.
14. Nausea/vomiting/diarrhea in pharmacovigilance. Citation [9]. Status: supported; T4 pharmacovigilance is appropriate as signal evidence only.
15. Severe hypoglycemia risk in obesity/overweight network meta-analysis. Citation [10]. Status: scope-mismatched for T2D safety unless explicitly contextualized.
16. Real-world hypoglycemia heightened by concomitant hypoglycemic drugs. Citation [9]. Status: plausible and cited, but source tier and causal limits should be clearer.
17. Dose-response mean differences vs 5 mg. Citation [11]. Status: supported by network meta-analysis, not primary.
18. Separate dose meta-analysis 15 mg vs 5 mg. Citation [12]. Status: supported by T2 evidence.
19. Obesity-without-diabetes dose-response trial. Citation [13]. Status: flagged as related, but still used in a T2D dose-response section.
20. Time to HbA1c and weight-loss thresholds in SURPASS-2/3. Citation [14]. Status: supported by preplanned analysis; useful but secondary to primary trial reporting.

**Did M-19 Prompt Changes Close the DR Pass 2 Gaps?**

Partially, not substantially.

Closed or mostly closed: PRNewswire is gone from the bibliography; T7 citations are gone from the bibliography; obvious T1D leakage is absent from the V6 body; citations are denser and more adjacent; primary-ish SURPASS-6 and AP-Combo sources now appear.

Not closed: Lilly review PMC10115620 is still citation [1] and remains the anchor for the central SURPASS-1/2/3/4/5 efficacy paragraph. The named primary SURPASS-1/2/3/4/5 papers are still not individually cited. Contradiction handling remains mechanical. Scope discipline remains incomplete for obesity-only evidence. Qwen still blocks release on citation tightness.

**Remaining DR Gaps After M-19**

1. Replace citation [1] review anchoring with individual primary SURPASS-1, SURPASS-2, SURPASS-3, SURPASS-4, and SURPASS-5 RCT citations.
2. Correct tier classification: reviews and mechanistic reviews must not be labeled T1 unless the taxonomy explicitly defines T1 differently from primary studies.
3. Rebuild contradiction handling into adjudicated prose: endpoint, unit, dose, population, comparator, timepoint, and source tier must be separated.
4. Remove or quarantine obesity-only evidence unless it is clearly framed as external context and not as direct evidence for adults with T2D.
5. Add a clinical synthesis layer: what is known with high confidence, what is comparator-specific, what is uncertain, and what safety signals require post-marketing caution.
6. Address Qwen citation-tightness failure; contradiction values need source attribution or should not be printed.

**Required Fix**

Run another fix-and-resweep. The fix should not be prompt-only unless retrieval/citation selection can be forced to prioritize primary RCT records. Required behavior:

1. Hard-prefer primary trial papers for SURPASS-1/2/3/4/5/6 and AP-Combo in the final bibliography.
2. Permit reviews/meta-analyses only for synthesis after primary RCT findings are anchored.
3. Add a contradiction adjudicator that clusters by endpoint, unit, dose, population, comparator, and timepoint before anything is surfaced in the report.
4. Add a scope gate that excludes obesity-only/T1D sources from direct T2D conclusions unless the sentence explicitly labels them as indirect contextual evidence.
5. Fail release if the evaluator is `partial` or `abort`, or if Qwen has any `needs_revision` axis.
