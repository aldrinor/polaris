---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_7_tirzepatide_v16
commit: 16ee8c7
delta_vs_pass6: "V16 vs V13: words 1854 vs 1474; verified sentences 54 vs 44; unique cited entries 30 vs 26; citation markers 99 vs ~44; markers/sentence 1.83 vs ~1.0; live audit changed from pass-6 21F/0Fab/3Emb/2Unv to V16 23F/1Fab/1Emb/5Unv; T1+T2 bibliography share fell from 84.6% to 73.3%."
citations_verified: "27 live-fetched/30 total cited"
citations_faithful: 23
citations_fabricated: 1
citations_embellished: 1
citations_unverifiable: 5
citation_markers_total: 99
citation_markers_per_sentence: 1.83
t1_t2_percentage_of_bibliography: 73.3
t7_percentage_of_bibliography: 3
faithfulness_verdict: "Mostly faithful quantitative synthesis, but not top-tier because one retained SURMOUNT trial-name/source-binding error is fabricated and several lower-tier or inaccessible entries are used in clinically sensitive places."
m27_impact: "synthesis genuinely improved in core SURPASS efficacy/safety claims, but also introduced some co-citation/source-quality padding and did not prevent one material trial-name binding error."
coverage_gaps_remaining: ["Direct primary-source verification still fails for several DOI/paywall/blocked entries", "T6 Facebook warning source remains in the bibliography for a safety-critical boxed-warning claim", "Obesity-without-diabetes SURMOUNT evidence still appears inside a T2D-focused safety/efficacy report without enough separation"]
structural_hallucinations: ["SURMOUNT-1 sentence is cited to the SURMOUNT-3 Nature Medicine source", "Ambiguous 'in that same trial' transition in Population Subgroups after a pooled SURPASS sentence"]
quantification_quality: "Strong for SURPASS-1/2/3/4, SURPASS-AP-Combo, time-to-threshold, and most meta-analysis numbers; weaker when multi-citation diffuses attribution or cites review + primary together for one exact value."
contradiction_handling: "PT08 disclosure is materially better than earlier versions and names detector granularity limits, but it still leaves raw contradiction ranges as noisy inventory rather than fully adjudicated endpoint/population contrasts."
vs_gpt54_dr_verdict: "Below top-tier DR because a fabricated trial-source binding remains despite otherwise strong primary-trial quantification."
vs_gemini31_pro_dr_verdict: "Likely passable as directional research, not final DR, due source-quality dilution and one fabricated citation binding."
rationale: |
  V16 is directionally better than V13 on density, coverage, and contradiction disclosure, and most quantitative claims checked against live source text are faithful. However, top-tier DR requires no fabricated trial binding. The retained sentence 'In SURMOUNT-1...' cites the Nature Medicine SURMOUNT-3 paper, whose trial and numeric result are different. The T6 Facebook boxed-warning citation and several unverified DOI/abstract-only entries also prevent STOP.
---

**Verdict**
V16 should not stop the loop. It is substantially improved over V13 in citation density and in many core SURPASS claims, but the final report still has a material citation-faithfulness defect. The blocking defect is the Efficacy sentence: "In SURMOUNT-1, the maximum tolerated dose of tirzepatide led to a mean weight reduction of -20.9% at 72 weeks versus -3.1% with placebo.[9]" Entry [9] is the Nature Medicine SURMOUNT-3 intensive-lifestyle trial, not SURMOUNT-1, and the SURMOUNT-3 result is a different trial/result. Verdict: MATERIAL-GAPS-FIX-AND-RESWEEP.

**V16 vs V13**
| Metric | V13 pass 6 | V16 pass 7 | Judge read |
|---|---:|---:|---|
| Sections | 5 | 5 | Preserved |
| Words | 1474 | 1854 | More complete, slightly more inventory-like |
| Verified sentences | 44 | 54 | Improved |
| Unique cited entries | 26 | 30 | Improved breadth |
| Citation markers | ~44 | 99 | M-27 worked mechanically |
| Markers per verified sentence | ~1.0 | 1.83 | Real density gain |
| Bibliography T1+T2 | 84.6% | 73.3% | Still strong, but meaningful dilution |
| Live audit outcome | 21F / 0Fab / 3Emb / 2Unv | 23F / 1Fab / 1Emb / 5Unv | Regression on zero-fabrication standard |

**Citation Live-Fetch Audit Table**
| # | Tier | Source / claim checked | Live-fetch verdict |
|---:|---|---|---|
| 1 | T1 | MDPI systematic review tables for SURPASS/SURMOUNT HbA1c, weight, GI, SAE, dose-response values | FAITHFUL |
| 2 | T1 | SURPASS-3 Lancet DOI; direct body not accessible in this pass, exact values supported by [1] but not this entry | UNVERIFIABLE |
| 3 | T1 | SURPASS-4 Lancet/ScienceDirect abstract: HbA1c -2.43/-2.58 vs -1.44 and high-risk T2D population | FAITHFUL |
| 4 | T1 | Nature SURPASS-AP-Combo: 66 hospitals, 83.2% China, HbA1c -2.24/-2.44/-2.49 vs -0.95, weight -5.0/-7.0/-7.2 vs +1.5 | FAITHFUL |
| 5 | T1 | SURPASS-AP-Combo subgroup PDF: higher baseline HbA1c and >=75 kg subgroup effects | FAITHFUL |
| 6 | T1 | Time-to-threshold PDF: 8.1 weeks to HbA1c <7.0%, 12.0/12.1 comparator, 16.0/12.4/24.0 weight threshold | FAITHFUL |
| 7 | T1 | SURPASS-2 NEJM/PubMed: HbA1c and weight superiority, hypoglycemia <54 mg/dL low | FAITHFUL |
| 8 | T1 | SURMOUNT-2 baseline HbA1c subgroup: placebo-corrected -17.7% for HbA1c <7% | FAITHFUL |
| 9 | T1 | Nature Medicine SURMOUNT-3 cited for a SURMOUNT-1 -20.9% vs -3.1% sentence | FABRICATED |
| 10 | T2 | OUP adverse-event meta-analysis: all GI AEs 39.05%, 45.57%, 49.25% and discontinuation/hypoglycemia tables | FAITHFUL |
| 11 | T1 | SURPASS J-mono direct body not fetched; J-mono safety rates only indirectly supported by [1] | UNVERIFIABLE |
| 12 | T1 | JAMA SURMOUNT-4: open-label GI rates, double-blind continuation AEs | FAITHFUL |
| 13 | T1 | PMC duplicate of SURMOUNT-4; PMC blocked but JAMA source body for same article fetched | FAITHFUL |
| 14 | T6 | Facebook boxed-warning source could not be body-fetched; safety-critical claim should cite FDA label/official PI | UNVERIFIABLE |
| 15 | T4 | FAERS safety profile: ROR 13.67 and similar MTC risk vs GLP-1RA supported, but "another similar analysis" is not supported by the same repeated citation | EMBELLISHED |
| 16 | T1 | Cureus/PMC thyroid review: SURPASS/GLP-1RA trials did not report meaningful AITD or sustained dysfunction increases | FAITHFUL |
| 17 | T4 | aITC vs semaglutide 0.5 mg: greater HbA1c/weight/BMI, comparable AE profile | FAITHFUL |
| 18 | T4 | 2025 SURPASS-2 composite target post-hoc not body-fetched | UNVERIFIABLE |
| 19 | T2 | Cureus meta-analysis vs semaglutide: weight-reduction superiority and pooled effect direction | FAITHFUL |
| 20 | T1 | TandF model simulation: switching from semaglutide/dulaglutide to tirzepatide can further lower HbA1c/weight | FAITHFUL |
| 21 | T2 | Springer NMA in basal insulin: greater HbA1c/body-weight reductions; nausea signal; discontinuation mostly not different | FAITHFUL |
| 22 | T2 | Frontiers dose meta-analysis: dose-dependent glycemic/weight benefit conclusion | FAITHFUL |
| 23 | T2 | Cureus dose meta-analysis: additional HbA1c reductions 0.20/0.30/0.10 by dose comparisons | FAITHFUL |
| 24 | T4 | ITC vs semaglutide 2.4 mg in T2D obesity: greater weight/BMI/HbA1c reductions | FAITHFUL |
| 25 | T4 | Older adults without obesity: HbA1c -1.97% to -2.10% | FAITHFUL |
| 26 | T7 | 743-P ADA abstract direct body not found; broad age-subgroup claim remains abstract-only | UNVERIFIABLE |
| 27 | T1 | JACC HFpEF/T2D stratified analysis: T2D vs non-T2D weight loss -10.4% vs -12.9%; claim is faithful but transition is ambiguous | FAITHFUL |
| 28 | T1 | SURPASS J-combo ScienceDirect: Japanese add-on trial design and efficacy/safety | FAITHFUL |
| 29 | T1 | SURPASS-CVOT NEJM/ACC: 12%/13%, HR 0.92, noninferiority | FAITHFUL |
| 30 | T4 | BMJDRC SURPASS-SWITCH subgroup: greater HbA1c/weight reductions across subgroups, few interaction exceptions | FAITHFUL |

**Criterion-by-Criterion**
Argumentation: Better than V13. The core efficacy section now connects SURPASS-1/2/3/4, AP-Combo, and time-to-threshold data coherently. Comparative and dose-response sections are more evidence-rich but sometimes read as an evidence inventory.

Quantification: Strong for primary SURPASS values and most meta-analysis/ITC claims. The problem is attribution diffusion: exact values are sometimes attached to a review plus primary source even when only one source carries the exact table, and one SURMOUNT claim is attached to the wrong trial.

Scope fidelity: Still imperfect. Obesity-without-diabetes SURMOUNT-1/3/4 evidence appears in a T2D-focused report. Some use is acceptable as contextual safety/weight evidence, but it must be explicitly segregated and cannot be used as if it were direct adult T2D evidence.

Contradictions: PT08 is substantially improved. The limitations now explains that the detector groups different endpoints, populations, doses, and comparators. This is acceptable as disclosure, but not yet a clinical adjudication.

Structure: Five template sections plus limitations and contradiction disclosures are present. No missing section hallucination. The structural issue is local: ambiguous transitions and the SURMOUNT-1/SURMOUNT-3 binding failure.

PT13 advisory: Acceptable as advisory only. "Superior" is mostly used where the trial/source itself reports superiority, though hedging could be cleaner for ITCs and pharmacovigilance.

**M-27 Impact**
M-27 is not merely cosmetic. It improved traceability for several multi-source claims, especially SURPASS-3/SURPASS-4 values cited to both the broad review and primary trial, and safety claims that pair trial data with meta-analysis data. However, the implementation also creates co-citation padding in places: [1] is repeatedly used as a catch-all review citation, [15] is repeated as if it were two analyses, and lower-tier comparative/abstract sources are allowed to carry clinical conclusions. Most importantly, M-27 did not prevent a wrong-source trial-name fabrication.

**Remaining Gaps**
- Replace [14] Facebook with FDA label / prescribing information or remove it.
- Fix SURMOUNT-1/SURMOUNT-3 binding: cite the actual SURMOUNT-1 source for -20.9% vs -3.1%, or change the sentence to the SURMOUNT-3 result.
- Require each multi-cited numeric sentence to identify at least one source that directly contains every exact number.
- Reduce reliance on T4/T7 in leading comparative/subgroup claims, or label them as indirect/post-hoc/abstract-only.
- Separate T2D trials from obesity-without-diabetes trials more explicitly.

**STOP or CONTINUE**
CONTINUE, targeted. Do not broaden retrieval. Patch source-binding and citation-quality rules, then resweep V17. The target is narrow: zero fabricated trial binding, no T6 source for boxed warnings, and direct-source support for every exact numeric sentence.
