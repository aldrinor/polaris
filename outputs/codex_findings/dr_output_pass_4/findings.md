---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_4_tirzepatide_v6
commit: e8b138d
delta_vs_pass2: "Major improvement in bibliography quality versus V5: PMC10115620 and PRNewswire are no longer cited, and V7 bibliography is 91.7% T1+T2 by count. However, the audited V7 files differ from the supplied 19-citation V6 summary: bibliography.json has 24 citations, including 2 T7 citations, and manifest.json still has release_allowed=false with Qwen needs_revision on citation tightness and hedging."
citations_verified: 24/24
t1_t2_percentage_of_bibliography: 91.7%
t7_percentage_of_bibliography: 8.3%
faithfulness_verdict: "Generally sentence-supported by the pipeline verifier (29 kept, 8 dropped), but not top-tier: several supported sentences are trivial trial-descriptor statements, weak T7/observational evidence is used for safety and subgroup claims, and key primary trial numerical results are absent from the final narrative."
coverage_gaps_remaining: ["SURPASS-2 primary paper not cited directly", "SURPASS-5 primary paper not cited directly despite retrieved corpus evidence", "SURPASS-6 absent from V7 bibliography/report", "SURMOUNT evidence present but obesity-only scope is peripheral", "SELECT absent", "LEADER absent", "SUSTAIN absent", "REWIND absent", "PIONEER absent", "STEP absent except corpus mention only"]
structural_hallucinations: ["Bibliography count mismatch: task context says 19 citations, audited V7 bibliography has 24", "Methods/limitations discuss corpus-tier distribution rather than evidence actually used in the report", "Contradiction disclosures are raw detector output, not adjudicated DR synthesis"]
quantification_quality: "Partial. Some comparative and dose-response estimates are quantified clearly, but the Efficacy section mostly lists trials without core HbA1c/weight effect sizes from SURPASS-1/3/4/J/CN-INS, and contradiction percentages are uninterpreted raw values."
contradiction_handling: "Mechanical and not top-tier. The report appends 12 contradiction bullets with implausible mixed metrics and no reconciliation by population, dose, endpoint type, comparator, timepoint, or evidence tier."
vs_gpt54_dr_verdict: "Below top-tier Deep Research. Improved source selection, but not enough synthesis, adjudication, or pivotal-trial coverage."
vs_gemini31_pro_dr_verdict: "Below top-tier Deep Research for the same reasons: advisory gate failed, Qwen flagged citation/hedging, and report remains list-like."
rationale: |
  M-19 materially improved citation discipline relative to V5, especially by removing the Lilly review and PRNewswire from the bibliography. That closes the most visible pass-2 citation-selection defect. But final-judge standard is top-tier DR or continue iterating. V7 still fails that bar: manifest release is blocked, Qwen flags citation tightness and hedging, the bibliography includes T7 citations used for substantive claims, several named pivotal programs are missing or only indirectly represented, and contradiction handling is not analytically adjudicated. The report is directionally useful, but not equivalent to GPT-5.4 Deep Research or Gemini 3.1 Pro Deep Research.
---

**Verdict**

MATERIAL-GAPS-FIX-AND-RESWEEP.

M-19 closed the most obvious citation-quality regression from pass 2, but V7 is not top-tier DR. The output is no longer dominated by press releases or review shortcuts, but it still reads as a compact evidence inventory rather than an expert synthesis. It also fails its own evaluator gate: `manifest.json` reports `status=partial_qwen_advisory`, `release_allowed=false`, and Qwen `needs_revision` for citation tightness and hedging.

**Quantitative V6 vs V5 Summary**

Audited files:

| Artifact | Total citations | T1 | T2 | T6 | T7 | UNKNOWN | T1+T2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V5 bibliography | 27 | 6 | 11 | 2 | 6 | 2 | 63.0% |
| V6 summary supplied in prompt | 19 | 10 | 8 | 0 | 0 | 0 | 94.7% |
| V7 audited bibliography | 24 | 16 | 6 | 0 | 2 | 0 | 91.7% |

Manifest V7 actuals: corpus count 310, T1 corpus 17.74%, T2 14.19%, T4 28.06%, T7 26.45%, contradictions_found 12, generator words 1001, limitations_words 79, sentences_verified 29, sentences_dropped 8.

The V7 bibliography is much better than V5, but it is not the 19-citation, zero-T7 bibliography described in the prompt context. The audited file contains 24 citations, including two T7 citations.

**Criterion-by-criterion**

a. Faithfulness: mostly sentence-supported, not top-tier. `verification_details.json` reports 29 kept sentences and 8 dropped sentences. Kept claims usually have cited evidence spans, but many are low-information descriptors rather than synthesized findings. Several important dropped claims include SURPASS-5, SURPASS-6, and SURMOUNT-CN numerical results; those losses leave the report less clinically complete.

b. Evidence quality: substantially improved, still flawed. V7 cites SURPASS-1, SURPASS-3, SURPASS-4, J-mono, J-combo, CN-INS, indirect comparisons, meta-analyses, and some observational/post-hoc sources. However, two T7 citations remain, and citation [16] is used for a thyroid-cancer claim that should not carry strong safety weight in a top-tier clinical synthesis.

c. Coverage: incomplete for the named bar. Present: SURPASS-1, SURPASS-3, SURPASS-4, SURPASS J-mono, SURPASS J-combo, SURPASS-CN-INS, SURPASS-AP-Combo, SURMOUNT-4, SUMMIT, and GADA-positive SURPASS 2-5 abstract. Missing or not directly cited: SURPASS-2 primary, SURPASS-5 primary, SURPASS-6, SELECT, LEADER, SUSTAIN, REWIND, PIONEER, STEP. Some of those comparator programs may be peripheral to tirzepatide in T2DM, but the requested coverage list is not met.

d. Scope: improved but imperfect. T1D leakage from V5 is gone from the report. Obesity-only evidence is explicitly flagged as "without diabetes" in two places, which is better. Still, obesity-only and HFpEF/obesity evidence occupy meaningful space in a T2DM glycemic-control report without enough explanation of why they are secondary.

e. Argumentation: listed more than integrated. The Efficacy section names trials but often omits the actual effect sizes. The Comparative and Dose Response sections quantify better, but the report does not build a coherent hierarchy such as monotherapy vs metformin add-on vs insulin add-on vs active comparator vs subgroup modifiers.

f. Contradictions: still mechanical. The contradiction section lists raw detector conflicts such as weight-loss values spanning implausible ranges. It does not adjudicate whether values are percent weight change, kg change, responder percentages, placebo-adjusted effects, time-to-threshold estimates, or different populations/timepoints.

g. Structural hallucinations: no invented clinical sections, but structural quality problems remain. The methods and limitations blocks describe corpus composition more than the report's used evidence. The contradiction block is presented as if it were meaningful analysis, but it is detector output requiring interpretation.

h. Plain-English quantification: partial. Good examples include semaglutide comparisons, cardiorenal endpoint percentages, hypoglycemia RR, and time-to-threshold estimates. Weak examples include unquantified primary efficacy statements and unexplained contradiction percentages.

**Citation-Level Audit Sample (20 citations)**

| Citation | Tier | Audit judgment |
|---|---:|---|
| [1] SURPASS-1 primary phase 3 | T1 | Appropriate primary anchor, but report does not provide core HbA1c/weight numbers. |
| [2] SURPASS-3 primary phase 3 | T1 | Appropriate; used mostly as trial descriptor. |
| [3] SURPASS-4 primary phase 3 | T1 | Appropriate; used mostly as trial descriptor. |
| [4] SURPASS J-mono | T1 | Appropriate regional primary evidence. |
| [5] SURPASS J-combo | T1 | Appropriate regional primary evidence. |
| [6] SURPASS-CN-INS | T1 | Appropriate but 2025 regional insulin-add-on evidence should be contextualized. |
| [7] SURMOUNT-4 | T1 | High-quality RCT but obesity-only; correctly flagged as without diabetes. |
| [8] Tirzepatide vs semaglutide 2 mg indirect comparison | T1 label | Relevant, but classification as T1 is questionable because it is an adjusted indirect comparison, not a primary RCT. |
| [9] Tirzepatide vs semaglutide 2.4 mg indirect comparison | T1 label | Relevant to obesity/T2DM, but indirect-comparison design should be tiered/hedged more cautiously. |
| [10] Tirzepatide vs semaglutide obesity trial | T1 | High-quality but obesity-only; correctly flagged as without diabetes. |
| [11] Cardiorenal outcomes vs dulaglutide | T1 | Relevant but narrow cardiovascular/cardiorenal endpoint; not a substitute for full CVOT context. |
| [12] Direct comparative studies meta-analysis | T2 | Acceptable supportive evidence, mostly obesity/weight-loss oriented. |
| [13] Safety systematic review | T2 | Acceptable safety synthesis; report uses it appropriately for GI and hypoglycemia. |
| [14] GLP-1/GIP vs GLP-1 safety review | T2 | Supportive; obesity/overweight population should be emphasized. |
| [15] FAERS real-world safety profile | T1 label | Misleading tier. FAERS disproportionality/post-marketing analysis is not T1 clinical evidence. |
| [16] Thyroid cancer abstract | T7 | Not acceptable as substantive reassurance against medullary thyroid cancer in top-tier DR. |
| [17] Dose meta-analysis | T2 | Acceptable for dose-response synthesis. |
| [18] Dose meta-analysis | T2 | Acceptable; Cureus venue warrants quality caution but not exclusion by itself. |
| [19] Network meta-analysis | T2 | Acceptable supportive dose evidence. |
| [20] SURPASS-2/3 exploratory analysis | T1 | Useful, but does not replace direct citation of SURPASS-2 primary trial. |

Additional inspected citations: [21] is a case report but labelled T1, inappropriate for strong subgroup inference; [22] SUMMIT HFpEF/obesity analysis is relevant only peripherally; [23] SURPASS-AP-Combo subgroup paper is useful; [24] GADA-positive abstract is T7 and should not drive substantive conclusions.

**Did M-19 Prompt Changes Close the DR Pass 2 Gaps?**

Partially.

Closed:

- Lilly review PMC10115620 is no longer cited in V7 bibliography/report.
- PRNewswire is no longer cited in V7 bibliography/report.
- Bibliography quality improved sharply from V5's 63.0% T1+T2 to V7's 91.7% T1+T2.
- Obesity-only evidence is now explicitly flagged as outside diabetes in relevant sentences.
- T1D report leakage appears removed.

Not closed:

- Named primary trial coverage remains incomplete: SURPASS-2, SURPASS-5, and SURPASS-6 are not in the V7 bibliography/report, despite SURPASS-5 and SURPASS-6 appearing in dropped verifier material or prior V5 output.
- T7 citations remain in the final bibliography and are cited in the report.
- Tier labels are overgenerous for some evidence types, including indirect comparisons, FAERS analysis, and a case report.
- Contradiction handling is still raw and mechanical.
- Qwen still blocks release on citation tightness and hedging.
- The narrative is not integrated enough for top-tier DR.

**Remaining DR Gaps After M-19**

1. Replace remaining T7-dependent claims with higher-tier evidence or remove them.
2. Directly cite and synthesize SURPASS-2, SURPASS-5, and SURPASS-6 primary papers.
3. Add proper comparator context if SELECT/LEADER/SUSTAIN/REWIND/PIONEER/STEP are required by the benchmark, or explicitly justify their exclusion as comparator-program context rather than tirzepatide evidence.
4. Rebuild contradiction handling into adjudication by endpoint, unit, population, dose, comparator, and follow-up duration.
5. Correct evidence-tier classification for indirect comparisons, FAERS, and case reports.
6. Expand the Efficacy section beyond trial naming; include primary HbA1c and body-weight effect sizes from the pivotal T2DM trials.

**Required Fix**

Run another iteration. The next sweep should require zero T6/T7 citations in the final bibliography unless explicitly quarantined in limitations, enforce primary SURPASS-2/5/6 inclusion, and reject raw contradiction dumps unless each conflict is reconciled or explicitly marked as an unresolved evidence-quality problem.
