---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_5_tirzepatide_v11
commit: 59b8f4a
delta_vs_pass4: M-25a materially improved trial-name binding; the pass-4 SURMOUNT/SURPASS misbinding pattern was not observed in kept V11 sentences, and strict_verify recorded 1 trial_name_mismatch drop. M-25b did not achieve DR-grade structure: V11 still produced only 3 sections and 710 words.
citations_verified: 9 live-fetched/12 total cited entries
citations_faithful: 8
citations_fabricated: 0
citations_embellished: 1
citations_unverifiable: 3
t1_t2_percentage_of_bibliography: 58.3%
t7_percentage_of_bibliography: 0.0%
live_fetch_method_used: mixed
faithfulness_verdict: No clear kept-sentence fabrication found, but one cost/NNT sentence overstates the cited source and three cited entries could not be verified from the cited source body in this audit. Faithfulness improved versus V10 but is not >95% verified.
coverage_gaps_remaining: [Primary trial coverage is too thin for a top-tier clinical DR answer, SURPASS/SURMOUNT primary RCTs are often replaced by reviews/news/cost analyses, T2D scope is diluted by obesity-without-diabetes evidence, contradiction disclosure remains evaluator-blocked.]
structural_hallucinations: [No off-template invented heading was found, but "Comparative" mixes T2D comparative evidence with obesity-only SURMOUNT evidence without enough separation.]
quantification_quality: Quantification is dense and generally numeric, but often listed rather than synthesized by population, dose, timepoint, comparator, and endpoint.
contradiction_handling: Inadequate. The report acknowledges 13 numeric disagreements but dismisses most as extraction artifacts and explicitly says a mechanical contradiction list is not required; evaluator PT08 correctly blocks release.
vs_gpt54_dr_verdict: Below top-tier DR. Too short, too dependent on secondary/T4 sources, weak contradiction adjudication, and insufficient population stratification.
vs_gemini31_pro_dr_verdict: Below top-tier DR for the same reasons; useful directional synthesis, not final research-grade output.
m25a_trial_gate_effective: Observed effective for the known pass-4 failure class: 1 trial_name_mismatch drop and no remaining live-confirmed trial-name fabrication among kept sentences. It does not solve source-tier choice or overbroad obesity evidence use.
section_count: 3 sections observed; insufficient for DR on this clinical question despite the M-25b prompt change toward 4-5 sections.
rationale: |
  V11 is materially cleaner than V10 on citation binding, especially for named-trial mismatches. However, final release is still blocked by the evaluator, the report is short and structurally shallow, and the citation audit did not reach top-tier reliability. The output should be reswept with primary RCT prioritization, explicit T2D vs non-diabetes obesity stratification, and real contradiction adjudication rather than a generic limitation paragraph.
---

**Verdict**

MATERIAL-GAPS-FIX-AND-RESWEEP. V11 is not TOP-TIER-DR-ACHIEVED.

I read `report.md` line by line, checked each citation-bearing sentence against `bibliography.json`, and live-fetched the cited sources or DOI-equivalent accessible bodies where possible. The pass-4 fabricated SURMOUNT/SURPASS mismatch appears fixed in the kept report text, but V11 remains below GPT-5.4 DR / Gemini 3.1 Pro DR quality because release is evaluator-blocked, source selection is too secondary, and contradiction handling is not substantive.

**Quantitative V11 vs V10 Summary**

V10 pass-4 live audit: 18 faithful / 1 fabricated / 1 embellished / 4 unverifiable of 24 citation-bearing sentences.

V11 audit by cited entry: 8 faithful / 0 fabricated / 1 embellished / 3 unverifiable of 12 unique cited entries.

V11 audit by citation-bearing sentence: 16 faithful / 0 fabricated / 1 embellished / 3 unverifiable of 20 report sentences. The sentence-level embellished defect is citation [10]'s NNT sentence.

Manifest status: `abort_evaluator_critical`; `release_allowed=false`; evaluator rule checks 12/13 pass; blocker PT08, `rule_pt08_contradiction_missing`. Qwen judged 5/5 axes GOOD: citation_tightness, hedging_appropriateness, tone_consistency, flow, completeness. Qwen flagged no critical axes.

Bibliography: 12 unique cited entries. Tier counts: T1=4, T2=3, T4=5, T7=0. T1+T2=58.3%; T4=41.7%; T7=0.0%. Publisher/source mix: Springer/Springer Nature=2, PMC/NCBI-hosted=3, URNCST=1, AHA/Circulation abstract DOI=1, Nature Medicine=1, MDPI=1, Frontiers=1, Drug Topics=1, Elsevier/Obesity Pillars=1. Named SURPASS/SURMOUNT papers are cited, but not consistently as primary T1 entries: SURPASS-2 is cited through a T4 post-hoc analysis and a T1 cost analysis, SURPASS-AP-Combo is primary T1, SURMOUNT-5 is cited through Drug Topics rather than the NEJM primary paper, and SURMOUNT-1/1-4 evidence is mixed through PMC/post-hoc sources.

**Citation Live-Fetch Audit Table (ALL 12+ citations)**

| Ref | Report sentence claim checked | Live source body checked | Verdict | Notes |
|---|---|---|---|---|
| [1] | SURPASS-2: tirzepatide superior to semaglutide 1 mg for glycemic and weight reduction in T2D on metformin. | DOI redirected content was inaccessible, but PubMed/LifeScience body for the exact paper states SURPASS-2 randomized adults with T2D to tirzepatide 5/10/15 mg or semaglutide 1 mg and concluded target attainment improved versus semaglutide. | FAITHFUL | The qualitative superiority claim is supported. |
| [1] | Post-hoc SURPASS-2: all tirzepatide doses increased odds of composite targets; 57% on 15 mg met three or more standard targets vs 34% semaglutide. | LifeScience/PubMed body states 34% semaglutide met three or more standard targets vs 42%, 53%, 57% for tirzepatide 5/10/15 mg, and reports increased odds for HbA1c, weight loss, and BP targets. | FAITHFUL | Exact numbers match. |
| [2] | Across SURPASS trials, HbA1c <7.0% ranged 81-97% and HbA1c <=6.5% ranged 66-95% with tirzepatide. | PMC source body was available through search/open text and states the same ranges across completed SURPASS trials. | FAITHFUL | Exact numeric ranges match. |
| [3] | Systematic review: dual GLP-1/GIP agonists like tirzepatide achieved greater HbA1c reductions up to 2.4% and body weight up to 22% versus GLP-1 RAs. | DOI `10.26685/urncst.1029` did not yield readable source body in this audit; exact-title searches did not expose the cited article body. | UNVERIFIABLE | Do not count as faithful without source-body verification. |
| [4] | IPD phase 3 meta-analysis: tirzepatide 15 mg/week reduced MACE, HR 0.67 (95% CI 0.51-0.87). | AHA/Circulation DOI body was not readable through the tool; secondary MIMS coverage of AHA abstract 4361308 repeats HR 0.67 and CI 0.51-0.87. | UNVERIFIABLE | Claim is plausibly true, but the cited DOI body itself was not verified. |
| [4] | Improvements in weight, waist circumference, DBP, and fasting glucose during therapy were associated with lower MACE hazard. | Same as above: secondary MIMS body reports an 81% lower MACE risk among tirzepatide-arm participants with improvements in weight, WC, DBP, and FBG. | UNVERIFIABLE | Not verified against cited AHA DOI body. |
| [5] | SURPASS-AP-Combo: most common AEs were mild/moderate decreased appetite, diarrhea, nausea; no severe hypoglycemia. | Nature Medicine body states the most common adverse events were mild to moderate decreased appetite, diarrhea, and nausea, with no severe hypoglycemia. | FAITHFUL | Exact claim supported. |
| [6] | SURPASS-3: any AE rates 61-73% for tirzepatide vs 54% insulin degludec; discontinuation due to AEs 7-11% vs 1%. | MDPI article body was live-fetched, but the exact trial-level numbers appear in included trial tables/supplements rather than readily exposed lines. Corroborating SURPASS-program review text reports the same table pattern. | FAITHFUL | Supported, but citation is a secondary meta-analysis rather than primary SURPASS-3. |
| [6] | SURPASS-1 any AE rates 69%, 67%, 64% vs 66%; serious AE rates 4%, 2%, 1% vs 3%. | Live source bodies for SURPASS-program review expose the exact SURPASS-1 adverse-event table values. MDPI article was live-fetched but not ideal for this trial-specific table claim. | FAITHFUL | Numerics match, but source choice should be primary or direct SURPASS review table. |
| [6] | SURPASS-1 discontinuation due to AEs 3%, 5%, 7% vs 3%. | Same live SURPASS-program table body gives discontinuation values 3, 5, 7 vs 3. | FAITHFUL | Numerics match. |
| [7] | Review: GLP-1-like GI effects including nausea 20-33%, diarrhea 18-22%, vomiting 8-13%, mostly mild/moderate during escalation. | PMC URL for the cited review hit browser/PMC access friction; alternate abstract pages did not expose the exact adverse-event sentence. | UNVERIFIABLE | Likely plausible, but not source-body verified. |
| [8] | Meta-analysis: mean weight reduction -10.39 kg vs placebo (95% CI -10.80 to -9.99). | Frontiers source body / LifeScience abstract states tirzepatide induced mean weight reduction -10.39 kg versus placebo with that CI. | FAITHFUL | Exact numbers match. |
| [8] | Safety: increased nausea, diarrhea, vomiting vs placebo; no increased headache risk OR=1.00, 95% CI 0.84-1.20. | Frontiers body states increased nausea/vomiting and gives headache OR=1.00, 95% CI 0.84 to 1.20. | FAITHFUL | Exact headache OR and CI match. |
| [9] | SURMOUNT-5 obesity without diabetes: tirzepatide 15 mg vs semaglutide 2.4 mg; body weight -20.2% vs -13.7%. | Drug Topics body states SURMOUNT-5 excluded diabetes and reports mean percentage body-weight reduction 20.2% vs 13.7%. | FAITHFUL | SURMOUNT-5 is real and numbers match, but source is T4 news; NEJM primary should be used. |
| [9] | SURMOUNT-5: tirzepatide patients were 1.3, 1.6, 1.8, 2 times more likely to reach >=10%, >=15%, >=20%, >=25% weight loss. | Drug Topics body states the same relative likelihoods for the same thresholds. | FAITHFUL | Exact numbers match. |
| [10] | Cost analysis: lower cost per responder than semaglutide for HbA1c <5.7% all doses and weight loss >=10% all doses. | Springer/PMC source body states lower cost per responder for HbA1c <5.7% all doses and weight loss >=10% all doses. | FAITHFUL | Supported. |
| [10] | NNT for all doses statistically significantly lower than semaglutide for weight loss endpoints >=5%, >=10%, >=15%. | Source body says NNTs were lower across weight-loss thresholds except the 5 mg dose at >=5% weight loss, where there was no statistical difference. | EMBELLISHED | The report drops the source's exception and overstates "all doses" for >=5%. |
| [11] | SURMOUNT-1 DXA substudy: fat mass -33.9% vs -8.2%; lean mass -10.9% vs -2.6% at week 72. | Northwestern/PMC-indexed body states body weight, fat mass, and lean mass changes were -21.3%, -33.9%, -10.9% with tirzepatide and -5.3%, -8.2%, -2.6% with placebo. | FAITHFUL | Exact body-composition numbers match; obesity-without-diabetes scope should be flagged more strongly. |
| [12] | SURMOUNT-1-4 post-hoc: macronutrient-malnutrition-related TEAEs such as abnormal weight loss/underweight were uncommon, 0.12% in tirzepatide-treated participants. | PMC/PubMed/ScienceDirect body reports abnormal loss of weight 0.03%, underweight 0.06%, hypoalbuminemia 0.03% with tirzepatide, totaling 0.12% for these three TEAEs. | FAITHFUL | Arithmetic synthesis is faithful. |
| [12] | Same analysis: 0.38% of tirzepatide-treated participants reached BMI <18.5 kg/m2. | Source body states BMI <18.5 was reached in 12/3141, 0.38%, tirzepatide-treated participants. | FAITHFUL | Exact number matches. |

**Criterion-by-criterion**

a. Citation faithfulness: materially improved; no live-confirmed fabrication. Still not top-tier because 3/12 cited entries were not source-body verified and [10] is embellished.

b. Source quality: inadequate for top-tier clinical DR. Only 4/12 bibliography entries are T1, and several pivotal trial claims rely on T4 reviews/news rather than primary RCTs or high-quality systematic reviews.

c. Argumentation: the report mostly lists trial findings. It does not integrate by dose, baseline T2D status, comparator class, timepoint, or endpoint hierarchy.

d. Quantification: strong numeric density, but weak synthesis. Plain-English interpretation of clinical magnitude, certainty, and applicability is limited.

e. Scope fidelity: mixed. The question asks adults with T2D. The report includes obesity-without-diabetes SURMOUNT-5 and SURMOUNT-1 body-composition evidence; it sometimes flags "without diabetes" but still gives those data prominent comparative weight.

f. Contradictions: inadequate. The body does not adjudicate the 13 detector flags; the disclosure section dismisses them as mostly extraction artifacts without endpoint-level resolution. PT08 failure is valid.

g. Structure: insufficient. Three sections plus limitations/methods is too thin for DR-grade output on efficacy and safety. M-25b did not deliver the intended 4-5 section depth.

h. Structural hallucinations: no invented out-of-scope heading found, but "Comparative" is too broad and blends clinical populations that should be separated.

**M-25a + M-25b Impact Assessment**

M-25a appears effective for the known pass-4 failure class. The kept V11 sentences did not bind SURMOUNT-1 claims to SURMOUNT-3 or import a non-tirzepatide PG-102 safety paper. `verification_details.json` records one `trial_name_mismatch` drop, demonstrating the gate is active.

M-25a is not sufficient for DR-grade quality because it does not force primary-source selection, population stratification, or contradiction adjudication. It also cannot prevent true-but-low-tier claims, such as using Drug Topics for SURMOUNT-5 when the NEJM paper is available.

M-25b did not achieve the structural target. The output remained 3 sections, 710 words, and 20 verified sentences, which is closer to a compact evidence brief than top-tier Deep Research.

**Remaining DR Gaps**

Primary evidence selection remains weak: SURPASS-2, SURPASS-3, SURPASS-1, SURMOUNT-5, and SURMOUNT body-composition claims should cite primary RCTs/substudies whenever available.

Population separation is insufficient: T2D efficacy/safety, obesity with T2D, and obesity without diabetes need separate synthesis lanes.

Contradictions are not adjudicated: dose, endpoint, timepoint, comparator, source tier, and population must be used to explain which numeric disagreements are real versus extraction artifacts.

The report is too short and too shallow for a top-tier DR answer: no evidence grading, no certainty language by endpoint, no adverse-event discontinuation synthesis by comparator, and no clinical bottom line.

**Required Fix**

Resweep V11 with a primary-source-first citation policy for named RCTs and post-hoc analyses, then regenerate with 4-5 substantive sections: glycemic efficacy in T2D, weight efficacy in T2D, safety/tolerability, comparator-specific evidence, and applicability/limitations.

Add a contradiction adjudication table grouped by endpoint/population/dose/timepoint/comparator. Do not dismiss detector output globally.

Fix citation [10]'s NNT sentence to preserve the source exception for tirzepatide 5 mg at >=5% weight loss, or cite a source that actually supports the broader claim.

Replace T4 news/review citations for primary trial claims where primary RCT papers are available, especially SURMOUNT-5 and SURPASS trial-specific safety/efficacy claims.
