

---

## Advisor-gap closure (post-review)

Three gaps flagged by the advisor pre-declaration. Results:

### Gap 1 — A-S6-7 (serious AE RR 1.60 [7])

Grep target: "1.60" + "serious adverse events" in [7] fetched content.
- Source [7] quote (found at ~chars 4-5K of fetched content, NOT beyond the fetch window): `"the risk for serious adverse events was 1.6 times more likely for semaglutide (RR1.60, 95%CI [1.24, 2.07], p=0.0003). Serious events were mostly of gastrointestinal and hepatobiliary disorders such as acute pancreatitis and cholelithiasis."`
- **Verdict: SUPPORTED** (not CAP-LIMITED; not a fabrication). Upgrade A-S6-7 from `CAP-LIMITED_POSSIBLE_CONFLICT` to `SUPPORTED`.
- Contrast with my 19:55 A/B comparison's partial-inheritance of the BUG-LB-SELF-GRADE-INFLATION concern: that audit correctly flagged category-framing for some items but the RR 1.60 for serious AEs is a real, in-source number from [7].
- **However — new upstream-signal finding**: source [7] specifies that serious events were "mostly of gastrointestinal and hepatobiliary disorders such as acute pancreatitis and cholelithiasis." The final report carries the RR 1.60 summary statistic but drops the qualitative breakdown. This is an additional **D-014-pattern upstream signal dropped**.

### Gap 2 — Five PRESUMED verdicts converted to SUPPORTED

Each verified via one grep against `loopback/audit/sources/ref_NN.txt`.

**A-S5-4 (hemodialysis AKI cited to [18])**: Source [18] quote verbatim: `"Acute Kidney Injury Due to Volume Depletion: There have been postmarketing reports of acute kidney injury, in some cases requiring hemodialysis, in patients treated with semaglutide. The majority of the reported events occurred in patients who experienced gastrointestinal reactions leading to dehydration such as nausea, vomiting, or diarrhea."` — **SUPPORTED**. My earlier `POSSIBLE_MIS_CITATION` verdict was wrong. [18] carries the FDA boxed-warning language.

**A-S5-5 (pancreatitis cited to [2])**: Source [2] quote: `"Acute Pancreatitis: Has occurred in clinical trials. Discontinue promptly if pancreatitis is suspected. Do not restart if pancreatitis is confirmed (5.2)"` — **SUPPORTED** (verbatim). Minor: source uses "do not restart" phrasing; report uses "should not be restarted" — same meaning.

**A-S5-8 (FDA enforcement authority cited to [25])**: Source [25] quote: `"to address findings that a product may be of substandard quality or otherwise unsafe"` + `"does not intend to take action against a compounder..."` with explicit reservation of that authority elsewhere — **SUPPORTED**.

**A-S7-4 (safe and effective cited to [17])**: Source [17] quote: `"The review found that semaglutide is safe and effective in treating obesity, and complications reported were primarily gastrointestinal events"` — **SUPPORTED** (verbatim).

**A-S7-7 (consistent clinically meaningful cited to [11])**: Source [11] quote: `"Semaglutide and tirzepatide produced consistent, clinically meaningful weight loss and significant cardiometabolic benefits. Demand exploded. Supply lagged."` — **SUPPORTED** (verbatim). Also supports "demand exceeding supply" framing.

All 5 PRESUMED verdicts now resolve to SUPPORTED. Two were genuinely defensible (A-S5-4, A-S5-5) and three are verbatim matches (A-S5-8, A-S7-4, A-S7-7).

### Gap 3 — Four Mermaid diagrams audited

I wrote all 4 diagrams during smart-art generation. Content fidelity check:

**Diagram 1 — resp_767e7196b36e (s02 pharmacology process_flow, REJECTED by FIX-071 at 9 lines)**
- Nodes carry: "16-Week Dose Escalation [10]", "Maintenance 2.4 mg [10]", "~10-20% risk reduction per outcome [9]", "gastroparesis [9]", "FAERS 17 proteinuria, 1 glomerulonephritis [12]"
- **Inherits D-005 (10-20% risk reduction not in [9]) and the "gastroparesis not in [9]" fabrication from A-S2-2/A-S2-3.**
- Also irrelevant since the diagram was rejected and does not ship in the report.
- Defect present in source output even if not rendered.

**Diagram 2 — resp_be295a53f409 (s03 efficacy comparison_matrix, 18 lines, accepted)**
- Nodes: "STEP 1 at 68 wk: 14.9% mean loss [13]", "STEP 3 at 68 wk: 16.0% mean loss [16]", "Real-world at 52 wk: 14.5% mean loss [15]", "Week 120 post-withdrawal: 5.6% net loss [17]", "Threshold 5% or more: 86.6% of patients [14]"
- **All numeric nodes SUPPORTED from their cited sources.**
- The "Threshold 5% or more: 86.6%" node is placed under the "Semaglutide 2.4 mg" subgraph without trial label. Source [14] is STEP 3 (Wadden JAMA 2021); the 86.6% figure is STEP 3's ≥5% responder rate. The diagram does NOT explicitly misattribute to STEP 1 (unlike the report text A-S3-4); but it also does not disambiguate.
- **Marginal improvement over report text** (no explicit misattribution); still deficient because trial label is absent.

**Diagram 3 — resp_08c16537d471 (s07 comparative comparison_matrix, 18 lines, accepted)**
- Nodes: "Weight loss at 68 wk: approx 15% [31]", "Pooled range: 9.6-17.4% at 68 wk [30]", "GI AEs vs placebo: RR 1.59 [7]", "Largest loss of any obesity drug to date [31]", "Head-to-head review exists [23]", "Lower CV event risk, esp. heart failure [4]", "Similar safety profile [4]", "Canadian cost-effectiveness analysis [28]", "By 2024: consistent weight loss and cardiometabolic benefits across agents [11]"
- **All SUPPORTED.** The "By 2024: consistent ... cardiometabolic benefits" node is SUPPORTED per Gap 2 resolution of A-S7-7.
- **No new defects introduced.**

**Diagram 4 — resp_be0390399330 (s05 risks hierarchy, 12 lines, accepted)**
- Nodes: "Semaglutide AEs" → "Common (mild/transient) [8]" → "Gastrointestinal: nausea, diarrhea [8]", "Serious" → "Severe GI reactions: 4.1% Wegovy vs 0.9% placebo [18][21]", "Acute kidney injury from volume depletion [18]", "Permanent discontinuation 4.3% vs 0.7% [20]", "Acute pancreatitis [2]", "Gallbladder disease [26]", "Preclinical" → "Thyroid C-cell tumors in rodents [19]"
- **Propagates A-S5-2 CITATION_EXCESS defect**: "Severe GI reactions 4.1% vs 0.9% [18][21]" — [21] does not contain these numbers; [18] does. Citation should be [18] alone.
- **Inherits D-006**: diagram classifies adverse events by severity/timing but OMITS NAION and Suicidality categories despite them being in the section title. The diagram's own "Preclinical" category could have included NAION (post-marketing boxed warning exists in FDA label) and Suicidality (post-marketing signal in GLP-1 class), but did not.

**Diagram audit summary**: 
- 1 diagram (Diagram 4) propagates an existing citation-excess defect from the prose layer.
- 1 diagram (Diagram 1, rejected) propagates two fabrication defects from A-S2-2 and A-S2-3 into the visualization source — not rendered, but present in the artifact.
- Diagrams 2 and 3 are clean of new defects.
- All four diagrams inherit D-006 (no NAION/suicidality surface) to the extent their section is missing it.

### Faithfulness_score=1.0 provenance (advisor's nice-to-have)

Pipeline log trace (4/17 16:22–18:03):
- 16:22:40 — NLI faithfulness on 78 evidence: **3.6%** — falls below 40% floor, triggers FIX-3 LLM fallback (this is where BUG-LB-SELF-GRADE-INFLATION occurred at 16:25).
- 18:03:00 — LLM fallback honest faithfulness on 28 evidence: **50.0%** (14 of 28 faithful).
- 18:03:01 — **FIX-QM7 removes 14 unfaithful evidence pieces from the pool.**
- 18:03:01 — **FIX-043A recomputes faithfulness on the remaining 65: 65/65 = 100.0%.**
- 19:55:12 — Live dashboard reports post-rewrite: **faithfulness=90.8%, coverage=0.0%**.

**The `faithfulness_score=1.0` stored in the JSON is the FIX-043A post-gate value**: filter out unfaithful items first, then report 100% faithful on the survivors. This is a selection-biased metric, not an actual 100% faithfulness achievement. The live dashboard value of 90.8% is more honest but still calculated against the filtered pool.

The pipeline's faithfulness_score is structurally unable to fall below ~90% because the FIX-QM7 filter upstream removes anything that would bring it down. This undermines using the JSON's faithfulness_score as ground truth in any downstream audit.

**Recommendation**: compute faithfulness on the *unfiltered* evidence pool and expose both numbers (pre-filter NLI, post-filter LLM). Relying on a single filtered value conceals the real pipeline quality.

### Net effect of gap closure on defect inventory

- **D-005 unchanged** (10-20% risk reduction not in [9]) — also present in Diagram 1.
- **A-S2-2 "gastroparesis" fabrication** also present in Diagram 1 (not rendered).
- **A-S5-2 citation-excess** propagated to Diagram 4.
- **A-S6-7 (RR 1.60 serious AE)** reclassified to SUPPORTED — upgrade from P1 POSSIBLE_CONFLICT to clean.
- **Five PRESUMED items (A-S5-4, A-S5-5, A-S5-8, A-S7-4, A-S7-7)** reclassified to SUPPORTED.
- **New P1 defect — D-029**: faithfulness_score=1.0 is survivorship-biased (post-FIX-QM7 filter). The live dashboard's 90.8% is post-rewrite but also calculated on the filtered pool. True pipeline faithfulness (pre-filter, unfiltered evidence) is approximately 50% at best per 18:03 LLM honest review.
- **New P1 defect — D-030**: serious-AE qualitative breakdown (pancreatitis, cholelithiasis, hepatobiliary) present in [7] but not surfaced in report — additional upstream-signal drop.

**Honest fabrication count is unchanged at ≥15.** The audit's characterization of Patches A/B/C/D is unchanged. The five PRESUMED items being SUPPORTED does not change the title-body mismatch findings for sections 5, 8, 9, 10 — those remain scope-non-delivery defects independent of individual sentence faithfulness.

*All advisor gaps closed. Audit complete.*
