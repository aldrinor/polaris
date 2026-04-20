---
verdict: TOP-TIER-DR-ACHIEVED
pass: dr_output_pass_8_tirzepatide_v17
commit: 14b50a9
delta_vs_pass7: V17 is shorter than V16 (1098 words vs pass-7 V16 larger retained output), uses 68 citation markers at 2.12/sentence vs V16 1.83/sentence, cites 24 unique entries, and improved from pass 7's 23 FAITHFUL / 1 FABRICATED / 1 EMBELLISHED / 5 UNVERIFIABLE to 23 FAITHFUL / 0 FABRICATED / 0 EMBELLISHED / 1 UNVERIFIABLE on the 24-entry bibliography.
citations_verified: 24/24
citations_faithful: 23
citations_fabricated: 0
citations_embellished: 0
citations_unverifiable: 1
citation_markers_total: 68
citation_markers_per_sentence: 2.12
t1_t2_percentage_of_bibliography: 70.8
t7_percentage_of_bibliography: 4
faithfulness_verdict: 95.8% faithful by cited-entry audit, with no fabricated or embellished claims found; one PubMed-only long-term source could not be independently body-verified beyond live metadata/access attempts.
m25a_hardening_effective: Effective. The pass-7 SURMOUNT-1/SURMOUNT-3 binding fabrication did not recur; trial names are now bound to the cited source identity fields and the remaining SURPASS/SURMOUNT/SUMMIT/CVOT uses map to the correct trial.
coverage_gaps_remaining: [Tier mix is acceptable but not ideal for DR clinical work because T4/T7 remain over expected distribution in the corpus, one T7 abstract remains in the bibliography, and cardiovascular outcome language should continue preferring the peer-reviewed NEJM SURPASS-CVOT paper over secondary news once available in the corpus.]
vs_gpt54_dr_verdict: Matches expected DR-grade threshold if GPT-5.4 requires clean gate plus zero fabricated citations; minor caveat is source-tier hygiene, not material faithfulness.
vs_gemini31_pro_dr_verdict: Should be accepted as top-tier directional-to-DR clinical synthesis because live citation binding is clean and remaining limitations are disclosed rather than hidden.
rationale: |
  V17 clears the decisive defects from pass 7. The manifest and run log show status=success, release_allowed=True, evaluator_gate.reasons=[] and 13/13 rule checks passing. I read the report end to end and audited all 24 cited bibliography entries against live-resolved source text or live source pages/search-index bodies where publisher pages were robot-gated. The only non-faithful classification is an access-limited PubMed-only long-term safety entry whose exact body text could not be read for 500 characters during live fetch; the sentence it supports is also independently supported by adjacent cited trial/meta-analysis evidence, so it is not a fabrication. No SURPASS/SURMOUNT trial-name substitution recurred. With 23/24 faithful, 0 fabricated, clean eval gate, and adequate clinical coverage, the loop should stop.
---

**Verdict**
TOP-TIER-DR-ACHIEVED. Stop the loop.

V17 is not perfect, but it meets the stop condition: 95%+ faithful live citation audit, zero fabricated citations, clean eval gate, 13/13 rule checks, and clinically adequate coverage of glycemic efficacy, weight loss, dose response, safety, comparators, subgroups, and cardiovascular outcomes.

**V17 vs V13 vs V16**

| Pass | Words | Verified sentences | Unique cited entries | Citation markers | Markers/sentence | Live audit result | Gate |
|---|---:|---:|---:|---:|---:|---|---|
| V13 | not re-read this pass | not re-read this pass | 13 | approx lower | approx 1.0 | prior stronger T1/T2 mix, less dense citation binding | prior loop state |
| V16 / pass 7 | larger retained output | not re-read this pass | 30 sampled/checked in pass 7 context | lower density | 1.83 | 23 faithful, 1 fabricated, 1 embellished, 5 unverifiable | MATERIAL-GAPS |
| V17 / pass 8 | 1098 | 32 | 24 | 68 | 2.12 | 23 faithful, 0 fabricated, 0 embellished, 1 unverifiable | pass, reasons=[] |

**Manifest And Gate**

`manifest.json` confirms `status=success`, `release_allowed=true`, `evaluator_gate.gate_class=pass`, `evaluator_gate.reasons=[]`, `rule_blockers=[]`, and 13 evaluator rule passes with zero failures.

`run_log.txt` independently confirms `[evaluator] rule_checks=13/13 pass`, `[eval_gate] class=pass release_allowed=True reasons=[]`, and `[status] ok`.

**Bibliography Mix**

The bibliography contains 24 entries: T1=12, T2=5, T4=6, T7=1. T1+T2 is 17/24 = 70.8%; T7 is 1/24 = 4.2%.

This is acceptable for this DR-grade clinical report. It is lower than V13's stated 84.6%, but the bibliography itself is still dominated by primary trials and systematic reviews/meta-analyses. The weak spots are the continued use of pharmacovigilance T4 sources for safety signals and one T7 ADA abstract for age subgroups; neither creates a material distortion because the report labels those areas appropriately and does not overstate causality from T4/T7 evidence.

**Citation Live-Fetch Audit**

| # | Evidence | Source checked live | Claim checked | Verdict | Notes |
|---:|---|---|---|---|---|
| 1 | ev_133 | NEJM DOI page / live index for SURPASS-2 | Tirzepatide achieved higher HbA1c target proportions and greater weight loss than semaglutide 1 mg. | FAITHFUL | Correct SURPASS-2 binding; no SURMOUNT substitution. |
| 2 | ev_196 | Lancet DOI resolution / live indexed abstract context | SURPASS-3 compared tirzepatide with insulin degludec and showed superior glycemic/weight outcomes. | FAITHFUL | Trial identity is correct. |
| 3 | ev_176 | Springer PDF full text | Faster HbA1c threshold attainment in SURPASS-2/3; median HbA1c <7% 8.1 weeks vs 12.0/12.1 weeks. | FAITHFUL | Source body directly contains the quoted numbers and comparator names. |
| 4 | ev_006 | PubMed/MDPI live source text for 2025 meta-analysis | Tirzepatide reduced HbA1c/body weight vs placebo, GLP-1 RAs, and insulin. | FAITHFUL | Broad meta-analysis claim matches source scope. |
| 5 | ev_017 | JAMA full text | SURMOUNT-4 lead-in produced 20.9% loss, continued treatment -5.5%, placebo regain 14.0%. | FAITHFUL | This fixes the pass-7 class defect: the 20.9% claim is tied to SURMOUNT-4 lead-in, not SURMOUNT-1. |
| 6 | ev_083 | PMC/JAMA duplicate live path | SURMOUNT-4 GI rates, maintenance-period diarrhea/nausea, no pancreatitis. | FAITHFUL | PMC page was robot-gated, but same JAMA article body was live-readable. |
| 7 | ev_092 | PMC live search body | Obesity-trial post hoc weight-threshold patterns over time. | FAITHFUL | Claim is general and matches source topic. |
| 8 | ev_096 | Nature Medicine live article body | MC4R-deficiency subgroup responded similarly to tirzepatide. | FAITHFUL | Source explicitly states similar response in MC4R mutation carriers and noncarriers. |
| 9 | ev_269 | Frontiers/PMC full text | GI AEs common; safety similar to GLP-1 RAs; 15 mg hypoglycemia RR 3.83; discontinuation dose effects. | FAITHFUL | Numbers and caveats match. |
| 10 | ev_274 | Springer/PMC live source body | FAERS signals: nausea ROR 4.01, pancreatitis 3.63, retinopathy 4.14, MTC 13.67. | FAITHFUL | The report properly treats these as pharmacovigilance signals, not causal proof. |
| 11 | ev_254 | PubMed/PMC live body for Endocrine Connections | T2D FAERS analysis reports GI disorders and signals including pancreatitis, hypoglycemia, MTC. | FAITHFUL | Report says "also reported MTC signals"; that is supported. |
| 12 | ev_279 | PMC live body | Painless biphasic thyroiditis after tirzepatide, normalized after discontinuation. | FAITHFUL | Exact clinical course is present. |
| 13 | ev_041 | PubMed/life-science live abstract | SURPASS-2 post hoc: 57% on tirzepatide 15 mg vs 34% semaglutide met >=3 standard targets. | FAITHFUL | Correct trial, comparator, and numbers. |
| 14 | ev_103 | Cureus DOI page/live metadata and indexed article context | Tirzepatide superior to semaglutide for weight reduction; SMD 0.75 and OR 0.21 reported. | FAITHFUL | Direction of OR should be clearer in prose, but not a material distortion because the superiority claim is supported. |
| 15 | ev_244 | Springer full text | Basal-insulin NMA: tirzepatide 5/10/15 mg reduced HbA1c and weight more than dulaglutide/exenatide/lixisenatide comparators. | FAITHFUL | Source directly lists these comparators. |
| 16 | ev_282 | PubMed/NEJM live abstract | SURPASS-CVOT noninferiority vs dulaglutide, HR 0.92, 95.3% CI 0.83-1.01. | FAITHFUL | Correctly says noninferior; does not falsely claim superiority. |
| 17 | ev_185 | Frontiers full text | Dose-response across 5-15 mg; 15 mg strongest efficacy; higher total/GI AEs at 10/15 mg. | FAITHFUL | The report slightly compresses the authors' recommendation but keeps the efficacy/safety tradeoff. |
| 18 | ev_198 | Cureus PDF full text | 10/15 mg vs 5 mg reduced HbA1c by 0.20/0.30% and weight by 2.64/4.26 kg; 15 mg best. | FAITHFUL | Source body directly contains the numbers. |
| 19 | ev_001 | PubMed live fetch attempted; body blocked/insufficient | Long-term hypoglycemia low/comparable across doses without insulin/SU. | UNVERIFIABLE | Adjacent citations [1] and [17] support the sentence, but this specific PubMed entry could not be body-verified to the required 500 characters. |
| 20 | ev_148 | ADA abstract DOI/live indexed citation | Age subgroup analysis across SURPASS trials reported consistent HbA1c effect by <65 and >=65. | FAITHFUL | T7, but used only for subgroup consistency. |
| 21 | ev_221 | Lancet/ScienceDirect live abstract | SURPASS-4 enrolled T2D with increased CV risk and compared tirzepatide to insulin glargine. | FAITHFUL | Correct binding; no CVOT confusion. |
| 22 | ev_229 | PubMed/JACC live abstract | SUMMIT HFpEF obesity analysis: HR 0.64 with diabetes, 0.61 without, no interaction. | FAITHFUL | Exact HRs and diabetes stratification match. |
| 23 | ev_287 | PubMed live page | SURPASS-CVOT baseline: mean age 64.1, diabetes duration 14.7, HbA1c 8.4, BMI 32.6. | FAITHFUL | Source body directly contains values. |
| 24 | ev_291 | MPR/EMPR live article | SURPASS-CVOT topline: MACE-3 HR 0.92, 8% lower risk, all-cause mortality 16% lower. | FAITHFUL | Secondary/news source, but the numbers match later NEJM/PubMed data. |

**Criterion Review**

a. Factual faithfulness: Pass. 23/24 entries faithful, 0 fabricated, 0 embellished. The one unverifiable entry is access-limited and non-decisive.

b. Citation tightness: Pass. Claims are adjacent to citations and the citation density is materially improved at 2.12 markers/sentence.

c. Trial-name binding: Pass. SURPASS-2, SURPASS-3, SURPASS-4, SURMOUNT-4, SUMMIT, and SURPASS-CVOT are used in the correct contexts.

d. Clinical balance: Pass. Efficacy, weight loss, GI tolerability, hypoglycemia, thyroid/pancreatitis/retinopathy pharmacovigilance caveats, dose response, and CV outcomes are all covered.

e. Safety causality: Pass with caveat. FAERS signals are described as real-world/pharmacovigilance analyses; the report should continue avoiding causal wording for those signals.

f. Comparative accuracy: Pass. Semaglutide, insulin degludec, insulin glargine, dulaglutide, and GLP-1 RA comparators are correctly distinguished.

g. Limitations: Pass. The report explicitly discloses tier-distribution weakness and contradiction-detector artifacts.

h. Readability and DR utility: Pass. The report is concise, clinically useful, and no longer padded by weak generated claims.

**M-25a Hardening Impact**

The hardening appears effective. Pass 7's blocker arose because direct_quote text let a SURMOUNT-3 source pass a SURMOUNT-1 claim. In V17, I found no recurrence of that class. The report's 20.9% weight-loss sentence is tied to SURMOUNT-4 sources, not SURMOUNT-1; SURPASS-3 claims are tied to insulin degludec/SURPASS-3; SURPASS-4 claims are tied to insulin glargine/high cardiovascular risk; and SURPASS-CVOT claims are tied to dulaglutide and MACE.

**Remaining Gaps**

The bibliography tier mix is acceptable but not ideal. T1+T2 is strong enough at 70.8%, but V13's 84.6% was cleaner. The main remaining hygiene issue is over-representation of T4/T7 in the full corpus and one T7 cited abstract.

The Cureus direct-comparison OR wording in citation [14] should be clarified in future output so odds-ratio direction is explicit.

Cardiovascular outcome claims should prefer the peer-reviewed NEJM SURPASS-CVOT source over MPR/EMPR news where possible. In this report, the news citation is numerically faithful and is paired with peer-reviewed CVOT sources, so it is not a blocker.

**STOP Or CONTINUE**

STOP. V17 satisfies the user's stop condition for TOP-TIER-DR-ACHIEVED: clean eval gate, 13/13 rules, >=95% faithful cited-entry audit, no fabricated citations, no recurrence of the M-25a trial-binding defect, and clinically adequate coverage.
