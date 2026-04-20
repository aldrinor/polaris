---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_6_tirzepatide_v13
commit: 451f382
delta_vs_pass5: V13 is a substantial pipeline improvement over V11: M-25e fixed PT08 by adding per-flag contradiction enumeration, V12/V13 expanded the report from 3 to 5 sections, and cited-bibliography quality rose to 84.6% nominal T1+T2. The release gate now passes, but live audit still finds DR-grade source-quality and auditability gaps.
citations_verified: 26 live-attempted/26 total cited
citations_faithful: 21
citations_fabricated: 0
citations_embellished: 3
citations_unverifiable: 2
t1_t2_percentage_of_bibliography: 84.6%
t7_percentage_of_bibliography: 3.8%
live_fetch_method_used: mixed
faithfulness_verdict: Mostly faithful at the numeric sentence level, but not top-tier: several citations are source-type misclassified, one safety sentence mislabels a pharmacovigilance paper as an RCT systematic review, one obesity-only trial is used for general T2D safety, and two cited sources were not auditable from the live cited source body.
coverage_gaps_remaining: [primary-source anchoring is still diluted by reviews and tertiary/low-quality sources; FDA label should replace Facebook for boxed warning; trial-level primary RCTs are not consistently used where available; scope gate still allows obesity/AITD/general GLP-1 evidence into a T2D-focused report]
structural_hallucinations: [bibliography tier labels overstate evidence quality for systematic/narrative reviews as T1; Methods says inclusion/exclusion criteria listed but report only names template, not concrete criteria; contradiction disclosure lists detector artifacts as if clinically meaningful ranges]
quantification_quality: Stronger than V11 and mostly numeric, but often list-like and dependent on secondary reviews instead of integrated primary-trial synthesis.
contradiction_handling: PT08 is technically fixed, but the disclosure is mechanical and clinically confusing; it exposes detector artifacts rather than adjudicating endpoint/dose/population/timepoint conflicts.
pt13_superlative_context: Mostly valid source-attributed comparative language, not promotional overreach; however it should be hedged as trial- or meta-analysis-specific.
m25_cumulative_impact: M-25b/e delivered structural breadth and PT08 pass; M-25a reduced trial-name leakage in final text but did not guarantee primary-source anchoring; M-25c remains needed because scope leakage persists.
vs_gpt54_dr_verdict: Below top-tier Deep Research because source selection and contradiction adjudication remain weaker than expected, despite improved citation faithfulness.
vs_gemini31_pro_dr_verdict: Below top-tier Deep Research for the same reasons: adequate directional synthesis, insufficient source hygiene and clinical adjudication.
rationale: |
  V13 is the first pipeline-successful run and is much better than V11, but release_allowed=True is not equivalent to top-tier DR. Live source checks found no clear fabricated quantitative claim among auditable sources, but the bibliography includes Facebook, a T7 abstract, narrative reviews labeled T1, and an obesity-only SURMOUNT-3 source used in the T2D safety section. The report also relies heavily on meta-analyses/reviews where primary RCTs should anchor SURPASS-2, SURPASS-3, SURPASS-4, SURPASS-CVOT, and SURPASS J-mono. The contradiction section passes PT08 but remains a raw detector dump rather than an expert reconciliation.
---

**Verdict**
MATERIAL-GAPS-FIX-AND-RESWEEP. V13 should not terminate the auto-loop as TOP-TIER-DR-ACHIEVED. It is directionally correct and mostly faithful, but not GPT-5.4 DR / Gemini 3.1 Pro DR quality.

**Quantitative V13 vs V11 vs V10 Summary**
V13: status=success, release_allowed=True, 5 sections, 1474 words, 44 verified sentences, 26 dropped, 26 bibliography entries, 12/13 rule checks passed, PT13 advisory only.

V11/pass 5: MATERIAL-GAPS, 3 sections, 710 words, 12 citations, 16 faithful / 0 fabricated / 1 embellished / 3 unverifiable in sampled audit, PT08 still failing.

V10/V11 failure mode: insufficient structure and contradiction disclosure. V13 fixes the gate mechanics, especially PT08, but does not yet fix source-hygiene and clinical-adjudication quality.

Independent bibliography count: T1=16, T2=6, T4=2, T6=1, T7=1. T1+T2=22/26=84.6%; T7=1/26=3.8%. Host/publisher concentration: doi.org 7, Springer 3, Nature 3, MDPI 2, Frontiers 2, NEJM 2, plus JAMA, Wiley, ScienceDirect, PMC, Cureus assets, PubMed, and Facebook.

**Citation Live-Fetch Audit Table (ALL 26 citations)**
| # | Live source check | Report use checked | Category | Finding |
|---:|---|---|---|---|
| 1 | MDPI Pharmaceuticals 2025 systematic review/meta-analysis, DOI 10.3390/ph18050668 | SURPASS-2, SURPASS-3, J-mono weight values and GI incidence ranges | FAITHFUL | Numbers are consistent with the review tables, but this is not a primary T1 RCT despite being labeled T1. |
| 2 | Springer PDF, Diabetes Therapy 2023, DOI 10.1007/s13300-023-01398-1 | Time to HbA1c <7.0%, SURPASS-2/3 weight thresholds | FAITHFUL | Median times and threshold proportions match the source. |
| 3 | DOI resolved via PubMed/search to DOM 2025, DOI 10.1111/dom.70047 | SURPASS-4 104-week HbA1c and weight changes | FAITHFUL | Exact 104-week values match accessible abstract text; PubMed page itself was reCAPTCHA-blocked. |
| 4 | Nature Medicine SURPASS-AP-Combo page/PDF redirect | Week-40 HbA1c and weight vs insulin glargine | FAITHFUL | Exact numeric claims match the source. |
| 5 | Springer PDF, Diabetes Therapy 2024, DOI 10.1007/s13300-024-01561-2 | Subgroup consistency and higher baseline weight effect | FAITHFUL | Subgroup claims and >=75 kg weight-loss statement match. |
| 6 | Nature Medicine SURMOUNT-3 obesity trial | General GI tolerability sentence in Safety | EMBELLISHED | The sentence is true for tirzepatide but sourced to an overweight/obesity trial after lifestyle intervention, not adult T2D evidence. Scope leak. |
| 7 | ScienceDirect EudraVigilance pharmacovigilance analysis | GI reports, pancreatitis/vomiting common reports | EMBELLISHED | Numeric/source content is broadly supported, but report incorrectly calls it a systematic review/meta-analysis of RCTs. |
| 8 | Frontiers Endocrinology systematic review, DOI 10.3389/fendo.2023.1121387 | Dose-dependence of nausea/diarrhea and discontinuation RR | FAITHFUL | Claims match, though the review itself cautions heterogeneity/bias. |
| 9 | JAMA editorial/full text, DOI 10.1001/jama.2021.25016 | Hypoglycemia generally low when not used with secretagogues/insulin | FAITHFUL | Supported by editorial discussion of low hypoglycemia rates, but indirect and not ideal as a safety anchor. |
| 10 | PMC/Springer FAERS pharmacovigilance paper, DOI 10.1007/s40618-024-02441-z | MTC ROR 13.67 and similar risk vs GLP-1RA | FAITHFUL | Exact ROR and comparative interpretation match. |
| 11 | Facebook post URL | Boxed warning for thyroid C-cell tumors | UNVERIFIABLE | Live source body was not accessible. The claim is true from official labeling, but this citation is unacceptable for DR. |
| 12 | Cureus/PMC narrative review, DOI 10.7759/cureus.98153 | SURPASS program did not show meaningful AITD/thyroid dysfunction increases | FAITHFUL | Sentence matches the review, but source is a narrative review and should not be labeled T1. |
| 13 | Wiley/ResearchGate/EBSCO DOI 10.1111/dom.14775 | aITC vs semaglutide 2 mg, HbA1c and weight ETDs | FAITHFUL | Exact ETDs match. Industry-funded indirect comparison should be contextualized. |
| 14 | Springer Diabetologia PDF, DOI 10.1007/s00125-024-06144-1 | NMA vs semaglutide doses | FAITHFUL | Exact comparative conclusions match. |
| 15 | PubMed/search, DOI 10.1007/s00125-025-06637-7 | SURPASS-2 composite therapeutic targets 57% vs 34% | FAITHFUL | Exact percentages match accessible abstract text. |
| 16 | Journal of Diabetology/DOAJ, DOI 10.4103/jod.jod_213_24 | Meta-analysis vs long-acting insulin, HbA1c/weight MD ranges | FAITHFUL | Exact MD values match. |
| 17 | Springer Diabetes Therapy 2025, DOI 10.1007/s13300-025-01728-5 | Basal-insulin NMA vs GLP-1 RAs/dulaglutide | FAITHFUL | Directional claim matches, though report narrows to dulaglutide 1.5 mg while source conclusion covers selected GLP-1 RAs. |
| 18 | NEJM DOI attempted; accessible ACC summary of NEJM article | SURPASS-CVOT HR 0.92, 95.3% CI 0.83-1.01 | FAITHFUL | Exact value confirmed through live DOI-derived secondary summary; primary NEJM body was not accessible in full. |
| 19 | Nature Medicine 2025 open article | Real-world trial emulation HR 1.06 and HR 0.87 | FAITHFUL | Exact values match article abstract/results. |
| 20 | Frontiers Cardiovascular Medicine 2022 | Dose-response and safety ranking | FAITHFUL | Source supports dose-dependent efficacy and more favorable safety at 5 mg. |
| 21 | NEJM SURPASS-2 DOI page attempted; values cross-confirmed in live secondary/related sources | SURPASS-2 body weight -7.8/-10.3/-12.4 kg | FAITHFUL | Numeric claim is correct, but final report should cite the primary RCT directly and ensure the NEJM body is auditable. |
| 22 | PMC/Cureus 2023 meta-analysis, DOI 10.7759/cureus.44314 | 10 mg/15 mg extra weight loss vs 5 mg and total AE risk | FAITHFUL | Exact -2.64 kg and -4.26 kg values and AE-risk statement match. |
| 23 | ADA abstract DOI 10.2337/db22-743-p attempted/search | Age <65 vs >=65 consistency | UNVERIFIABLE | Could not obtain >=500 chars of source body. T7 abstract should not be needed for a top-tier report. |
| 24 | MDPI Geriatrics 2024 | Older Japanese pilot CGM time-in-range 53.2% to 78.9% | FAITHFUL | Exact values match, but n=4 observational pilot should be framed as very low certainty. |
| 25 | Lancet SURPASS-4 DOI/search plus publisher/press text | High-CV-risk SURPASS-4 superiority vs glargine | FAITHFUL | Trial-name binding and direction match; stronger to cite accessible Lancet/PubMed body rather than rely on secondary snippets. |
| 26 | SURPASS J-mono DOI/search and cross-confirmation from review | Japanese monotherapy safety consistency | FAITHFUL | Direction is supported, but final report uses it only in a broad multi-citation safety sentence; primary source should be directly auditable. |

**Criterion-by-criterion**
(a) Argumentation: improved but still semi-listed. Sections assemble correct trial facts, yet they rarely synthesize why differences across comparators, timepoints, and populations matter clinically.

(b) Quantification: strong numeric density. Most values are faithful. Weakness is over-reliance on secondary analyses and insufficient plain-English clinical interpretation of absolute vs relative effects.

(c) Scope fidelity: imperfect. SURMOUNT-3 obesity-without-T2D/lifestyle-intervention evidence and autoimmune thyroid narrative-review material leak into a T2D-focused report.

(d) Contradictions: technically disclosed per M-25e, but too mechanical. A top-tier report would adjudicate: endpoint mismatch, percent vs kg mismatch, HbA1c target percentages misread as weight, obesity vs T2D populations, and source-tier authority.

(e) Structure: 5 sections are within the intended template and no major section hallucination appears. However, Methods overclaims inclusion/exclusion disclosure.

(f) PT13: “superior” is generally valid source language for SURPASS-AP-Combo, meta-analyses, and SURPASS-4, but should be hedged to trial/source context.

(g) Bibliography quality: nominal T1+T2 is high, but tiering is unreliable. Systematic reviews/narrative reviews are labeled T1; Facebook appears as T6; a T7 abstract remains for a subgroup claim.

(h) Primary RCT anchoring: insufficient. SURPASS-2, SURPASS-3, SURPASS-4, SURPASS-CVOT, and J-mono should be cited directly and consistently for core efficacy/safety claims.

**M-25 Impact Assessment**
M-25a partially delivered: trial-name mismatches were dropped before final output, and no obvious SURPASS/SURMOUNT binding error remains in the final report. It did not force primary RCT anchoring.

M-25b delivered: the report now has 5 sections and substantially better coverage.

M-25e delivered for the evaluator: PT08 passes because every subject/predicate substring appears. For human DR quality, it is still a raw detector appendix.

M-25c is still needed: scope leakage and low-authority source leakage remain visible.

**Remaining DR Gaps**
Replace Facebook boxed-warning citation with FDA prescribing information or DailyMed.

Re-tier bibliography correctly: primary RCTs as T1, systematic reviews/meta-analyses as T2, narrative reviews lower, T7 abstracts only when unavoidable.

Use primary RCTs for core claims: SURPASS-2 NEJM, SURPASS-3 Lancet, SURPASS-4 Lancet, SURPASS-CVOT NEJM, SURPASS J-mono Lancet Diabetes Endocrinology, SURPASS-AP-Combo Nature Medicine.

Add clinical adjudication to contradictions instead of raw ranges.

Remove or explicitly quarantine obesity-only and autoimmune-thyroid material from the adult T2D efficacy/safety answer unless used as clearly labeled indirect context.

**STOP or CONTINUE decision**
CONTINUE. V13 is a real engineering milestone and a successful release-gate pass, but not top-tier Deep Research. The next iteration should be targeted, not broad: implement M-25c scope/source gate, correct tier taxonomy, force primary RCT citation for pivotal trials, and replace the contradiction dump with an adjudicated contradiction note.
