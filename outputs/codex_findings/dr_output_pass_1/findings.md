---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_1_tirzepatide_v4
commit: 10bb23fc8a408f8697e9837ef982fbba5698a154
citations_verified: 24/24
t1_t2_percentage: "41.7% of report bibliography by assigned tier"
t7_percentage: "33.3% of report bibliography by assigned tier"
faithfulness_verdict: "Narrow numeric faithfulness is mostly acceptable in the sampled sentences, but DR faithfulness is not acceptable because many adjacent citations are low-authority substitutes for available primary evidence and several sections omit material qualifiers from the cited evidence."
coverage_gaps: [primary SURPASS-1/2/3/4/5 papers not used as lead evidence, SURMOUNT-2 not synthesized for T2D obesity, SELECT/LEADER/SUSTAIN comparator context absent, ADA/AACE/FDA label guidance absent, pancreatitis/gallbladder/gastroparesis/hypoglycemia not adequately covered, cardiovascular outcomes not synthesized, real-world evidence underdeveloped]
structural_hallucinations: [completeness gate says regulatory status and drug interactions covered but report body omits them, citation tier labels overstate some source authority, contradiction disclosures include extraction artifacts as if clinical contradictions]
quantification_quality: "Good local numerics for HbA1c/weight in many sentences, but not top-tier: little absolute clinical interpretation, limited denominators/time horizons, no heterogeneity/I2 discussion, and several dose/weight contradiction artifacts are left unresolved."
contradiction_handling: "Inadequate. The report lists 13 contradictions mechanically, but does not reconcile source type, population, endpoint, unit, or extraction errors in the analysis."
vs_gpt54_dr_verdict: "Below top-tier GPT-5.4 Deep Research. It is a short cited summary, not a rigorous evidence synthesis."
vs_gemini31_pro_dr_verdict: "Below Gemini 3.1 Pro DR quality. It lacks authoritative-source prioritization, guideline/regulatory synthesis, and balanced safety discussion."
rationale: |
  I read report.md cover to cover, then checked manifest.json, protocol.json, bibliography.json, live_corpus_dump.json, corpus_adequacy.json, verification_details.json, contradictions.json, qwen_judge_output.json, and run_log.txt. The run passed internal gates, but the manifest and corpus approval both record material deviation: T1 6.77% vs expected 30-60%, T7 33.55% vs expected <=10%. The report bibliography uses only 24 unique sources; 8 are T7 and 2 are T6. Multiple report claims cite PRNewswire, Pharmacy Times, ADA abstract stubs, Cureus PDFs, or Facebook when primary RCTs, FDA/label sources, and peer-reviewed trial papers are present in the corpus or should have been retrieved.
  Sentence-level audit: the first two efficacy sentences are numerically supported by the Lilly/PRNewswire page, but this is not acceptable lead evidence for SURPASS-3/5 when Lancet/JAMA primary trial papers exist. The SURPASS-2 head-to-head sentence cites an ADA late-breaking abstract, not the NEJM trial. The safety section cites a systematic review that explicitly flags high-dose hypoglycemia and discontinuation, but the report omits those material caveats. The boxed-warning sentence cites a Facebook post rather than an FDA label or prescribing information. The final type 1 diabetes sentence is outside the scoped adult T2D question. The limitations section honestly reports low-tier skew, but that admission does not cure the report.
---

**Verdict**
MATERIAL-GAPS-FIX-AND-RESWEEP. This output is directionally informative, but it is not top-tier Deep Research. The biggest problem is not that every number is fabricated; many sampled numbers are traceable. The problem is that the report repeatedly chooses low-quality adjacent evidence, omits major safety/guideline/regulatory material, and treats noisy extraction contradictions as if they were clinical contradictions.

**Quantitative Summary**
- Report citations: 36 citation occurrences, 24 unique bibliography sources.
- Assigned report-source tiers: T1=2, T2=8, T4=4, T6=2, T7=8. T1/T2=41.7%; T7=33.3%.
- Corpus tiers: T1=6.77%, T2=12.58%, T3=0.65%, T4=33.87%, T7=33.55%, UNKNOWN=9.35%; material_deviation=true.
- Report size: 1,458 words before bibliography/method metadata; 6 report sections including limitations; about 6 citation markers per analytic paragraph.
- strict_verify: 34 verified, 7 dropped, pass rate 82.9%. Drop reasons were 5 number-not-in-span and 2 no-integer-overlap failures.
- Faithfulness sample: 20/20 sampled sentence claims had at least plausible adjacent textual/numeric support, but only about 7/20 used DR-suitable evidence for the claim.

**Criterion-by-criterion**
(a) Faithfulness: narrow citation support is often present, but source faithfulness is weak. Examples: [1] supports the SURPASS-3/5 numbers but is a PRNewswire/Lilly release; [6] supports SURPASS-2 only as an ADA abstract despite NEJM availability; [14] supports a boxed-warning claim only through Facebook; [11] supports GI events but also reports high-dose hypoglycemia/discontinuation that the safety section does not integrate; [24] supports type 1 diabetes data but is outside the scoped T2D population. Additional checked claims [2], [3], [8], [13], [17], [18], [19], [22], and [23] mostly match their adjacent evidence but vary sharply in authority and applicability.

(b) Evidence quality: fails. The report relies on T6/T7 for core efficacy, subgroup, immunogenicity, and boxed-warning claims. The bibliography includes PRNewswire, Pharmacy Times, Facebook, multiple ADA abstracts, Cureus, and a type 1 diabetes conference abstract. Some classifier tiers are also wrong: a PMC review is labeled T1, while a NEJM RCT is labeled T4.

(c) Coverage: incomplete for the requested DR bar. SURPASS-1/2/3/4/5 primary papers are not used as backbone citations. SURMOUNT-2 is not synthesized for T2D obesity. SELECT, LEADER, and SUSTAIN comparator context is absent. Pancreatitis appears only indirectly in retrieved evidence, not the final safety analysis; gastroparesis is missing; gallbladder disease is missing; hypoglycemia is omitted from the main safety synthesis despite cited evidence.

(d) Scope: partially covered. Efficacy, comparative effects, safety, dose response, and subgroups are present. Guidelines, regulatory status, contraindications, cardiovascular outcomes, drug interactions, and real-world evidence are missing or superficial despite the completeness gate claiming coverage.

(e) Argumentation: below DR grade. The report is mostly a sequence of findings. It does not reconcile populations, comparators, durations, estimands, baseline BMI/A1c, or direct vs indirect comparisons. It reports many effect sizes but gives little clinical interpretation.

(f) Balanced contradictions: inadequate. The report lists 13 contradictions, but several are extraction/unit artifacts: HbA1c percentages are misfiled as body-weight percentages, achievement rates are mixed with mean changes, and OSA AHI reductions are mixed into weight-loss contradictions. A top-tier report would adjudicate these rather than append them.

(g) No hallucinated structure: no obvious invented consensus section, but there is structural overclaiming. The methods/completeness metadata says regulatory status and drug interactions are covered; the report body does not cover them. Tier labels in the bibliography can mislead a reader about authority.

(h) Plain-English quantification: mixed. The report includes concrete HbA1c and kg/% weight changes, but it lacks plain-English clinical framing, denominators, time horizons in several sentences, heterogeneity, and direct statement of uncertainty.

**Citation-Level Audit Sample (20 citations)**
| Sentence | Evidence | Verdict |
| ... | ... | ... |
| SURPASS-3 15 mg reduced HbA1c 2.37% and weight 12.9 kg. | [1] PRNewswire/Lilly release. | Numerically supported; unacceptable lead evidence. |
| SURPASS-5 15 mg reduced HbA1c 2.59% and weight 10.9 kg. | [1] PRNewswire/Lilly release. | Numerically supported; should cite JAMA/SURPASS-5 primary paper. |
| Meta-analysis found HbA1c -1.94% and weight -8.47 kg vs control. | [2] MDPI Pharmaceutics SR/MA. | Supported; acceptable secondary evidence, not sufficient alone. |
| Meta-analysis found HbA1c WMD -1.07% and weight -7.99 kg. | [3] Frontiers Pharmacol SR/MA. | Supported. |
| HbA1c <7% ranged 81-97% across SURPASS. | [4] PMC review labeled T1. | Likely supported; tier overclassified, should use trials. |
| SURPASS-1 13-27% achieved >=15% weight loss. | [5] Pharmacy Times. | Supported only by trade article; not DR-grade. |
| SURPASS-2 achieved HbA1c/weight goals vs semaglutide. | [5] Pharmacy Times. | Directionally supported; low-quality and vague. |
| Tirzepatide superior to semaglutide 1.0 mg at 40 weeks. | [6] ADA abstract. | Supported; should cite NEJM SURPASS-2. |
| Direct comparative SR favors tirzepatide for weight. | [7] Cureus SR/MA. | Supported; lower-confidence venue. |
| Tirzepatide 10/15 mg exceeded semaglutide 2.4 mg by 2.57/4.79%. | [8] DOM indirect comparison. | Supported; indirect evidence needs stronger caveat. |
| Tirzepatide more effective than long-acting insulin. | [9] SR/MA. | Supported; phrasing too definitive. |
| Head-to-head obesity trial GI AEs mostly mild/moderate. | [10] NEJM obesity RCT labeled T4. | Supported but outside T2D-only scope. |
| Overall safety similar to GLP-1 RAs, GI events prominent. | [11] safety SR. | Supported. |
| Nausea/vomiting/diarrhea higher than placebo, consistent with GLP-1 RAs. | [11] safety SR. | Supported, but omits hypoglycemia/discontinuation caveat. |
| Anti-drug antibodies 51.1%, no PK/efficacy impact. | [12] ADA abstract. | Supported only by abstract; not enough for top-tier safety. |
| FAERS medullary thyroid cancer ROR 13.67. | [13] FAERS pharmacovigilance. | Supported; must frame as reporting signal, not causal risk. |
| Boxed warning for thyroid C-cell tumor risk. | [14] Facebook post. | Claim may be true; citation is unacceptable. Use FDA label. |
| Thyroiditis case report. | [15] case report. | Supported; low evidentiary weight. |
| Dose-dependence across 5/10/15 mg. | [16] ADA abstract. | Supported only by abstract; should cite pooled RCT/meta-analysis. |
| GADA subgroup effects in SURPASS 2-5. | [22] conference abstract. | Supported but niche and low-tier; not a core DR pillar. |

**URL Quality Audit (20 URLs sampled)**
| URL | Assigned tier | Actual tier based on content | Agreement |
| ... | ... | ... | ... |
| prnewswire.com/...surpass-program | T6 | T6 press release | Agree; should not support core trial claims. |
| mdpi.com/1424-8247/14/10/991/pdf | T2 | T2 SR/MA | Agree. |
| frontiersin.org/...1016639/pdf | T2 | T2 SR/MA | Agree. |
| pmc.ncbi.nlm.nih.gov/articles/PMC10115620 | T1 | T4 review | Disagree; overclassified. |
| pharmacytimes.com/...type-2-diabetes | T6 | T6 trade/news | Agree; not suitable. |
| doi.org/10.2337/db21-84-lb | T7 | T7 conference abstract | Agree. |
| doi.org/10.7759/cureus.86080 | T2 | T2 SR/MA, lower-confidence venue | Mostly agree. |
| doi.org/10.1111/dom.16401 | T4 | Indirect treatment comparison | Borderline; must caveat. |
| doi.org/10.4103/jod.jod_213_24 | T2 | T2 SR/MA | Agree. |
| doi.org/10.1056/NEJMoa2416394 | T4 | T1 NEJM RCT | Disagree; underclassified. |
| frontiersin.org/...1121387/pdf | T2 | T2 safety SR | Agree. |
| doi.org/10.2337/db22-742-p | T7 | T7 abstract | Agree. |
| pmc.ncbi.nlm.nih.gov/articles/PMC11473560 | T1 | T1 observational pharmacovigilance | Agree, but causal limits needed. |
| facebook.com/clinicalpharmacyboard/... | T7 | Inadmissible social post | Too generous; exclude. |
| pmc.ncbi.nlm.nih.gov/articles/PMC12127604 | T4 | Case report | Agree. |
| doi.org/10.2337/db22-719-p | T7 | T7 abstract | Agree. |
| doi.org/10.1007/s40200-024-01412-8 | T2 | Network meta-analysis | Agree. |
| assets.cureus.com/...184390.pdf | T2 | Cureus meta-analysis | Mostly agree, lower confidence. |
| frontiersin.org/...990182/pdf | T2 | Meta-analysis | Agree. |
| doi.org/10.2337/db22-720-p | T7 | T7 abstract | Agree. |

**Run Log Anomalies**
- Retrieval took 4,909.9 seconds, fetched 307/310 with 3 failures.
- Corpus material_deviation=true, but run still approved.
- Selection used all 290 evidence rows, including 94 T7 and 29 UNKNOWN rows.
- Evaluator had 1 rule failure: PT13 unhedged superlatives.
- Qwen judge included one needs_revision for hedging and one acceptable for completeness, noting regulatory status omitted and contradictions not contextualized.
- live_corpus_dump has many R1_stub_content_length classifications and many DOI-host demotions, showing retrieval/classification noise.

**DR Quality Gap Analysis**
To reach top-tier DR, rebuild the report around primary RCTs and authoritative labels/guidelines. Lead efficacy with SURPASS-1, SURPASS-2, SURPASS-3, SURPASS-4, SURPASS-5, and SURMOUNT-2 where relevant; use meta-analyses only to integrate. Safety must cover GI intolerance, discontinuation, hypoglycemia with insulin/sulfonylureas, pancreatitis, gallbladder disease, gastroparesis/delayed gastric emptying, renal/dehydration risks, thyroid C-cell boxed warning, and cardiovascular outcomes. Comparative sections must distinguish semaglutide 1 mg T2D glycemic trials from semaglutide 2.4 mg obesity trials. Contradictions must be adjudicated by endpoint and population, not pasted from extractor output.

**Required Fix**
1. Replace PRNewswire, Pharmacy Times, Facebook, and abstract-only citations for core claims with peer-reviewed primary trial papers, FDA prescribing information, ADA/AACE guidelines, and high-quality SR/MAs.
2. Re-run classifier or manually pin tiers for NEJM/Lancet/JAMA primary RCTs and PMC review articles; do not allow review pages to masquerade as T1 primary evidence.
3. Rewrite safety and limitations with explicit causal-strength distinctions: RCT adverse events, pharmacovigilance disproportionality, label warnings, and case reports must not be blended.
4. Remove out-of-scope type 1 diabetes and obesity-only claims unless clearly marked as indirect context.
5. Convert contradiction disclosures into an adjudicated evidence table with units, endpoints, populations, comparators, and timepoints.
