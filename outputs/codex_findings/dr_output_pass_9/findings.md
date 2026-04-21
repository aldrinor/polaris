---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_9_tirzepatide_v18
commit: 8c54cd541d1ee4e4f2ef88ad48daace3f38b9d1f
delta_vs_pass8: V18 expands the bibliography from 24 to 35 unique cites, adds 12 T3 regulatory cites, raises citation markers from 68 to 115, and materially closes V17's zero-regulatory-URL gap; however, the new regulatory paragraph introduces a jurisdictional overclaim by implying FDA boxed-warning/MTC-MEN2 contraindication language is shared by "both agencies" despite EMA SmPC contraindications being different.
citations_audited: 35/35
citations_faithful: 33
citations_fabricated: 0
citations_embellished: 2
citations_unverifiable: 0
regulatory_citations_found: 12
regulatory_citations_verified: 12/12
t1_t2_t3_percentage: 89
citation_markers_total: 115
citation_markers_per_sentence: 2.25
m28_impact: partial
regression_vs_v17: introduced_regulatory_jurisdiction_overclaim
rationale: |
  V18's manifest and run log confirm status=success, release_allowed=true, evaluator_gate.gate_class=pass, 12/13 rules passing, and PT13 advisory only. The corpus contains 46 T3 sources and the bibliography contains 12 T3 regulatory cites spanning FDA, EMA, and NICE. I live-fetched or live-index-verified all 35 bibliography URLs and found no fabricated source identity, no dead regulatory URL, and no M-25a trial-name regression.

  The stop condition is not met because the new regulatory content is not fully faithful. FDA Zepbound and Mounjaro labels support boxed warning language for thyroid C-cell tumors and FDA contraindications for personal/family MTC or MEN2. EMA Mounjaro product information resolves and supports T2D and weight-management indications, heart-rate/retinopathy/aspiration precautions, and other warnings, but its formal contraindication section is hypersensitivity-based, not FDA-style MTC/MEN2. The report says "A key safety warning from both agencies is a boxed warning..." and then applies the contraindication without jurisdictional qualification while citing only FDA label sources [31][32]. That is an embellished regulatory overclaim and a jurisdictional mix-up in precisely the gap M-28 was meant to close.
---

**Verdict**
MATERIAL-GAPS-FIX-AND-RESWEEP. Continue the loop with one targeted fix: regulatory synthesis must distinguish FDA boxed warning/contraindications from EMA SmPC contraindications and warnings.

**Manifest And Gate**
`manifest.json` and `run_log.txt` match the claimed V18 status: `status=success`, `release_allowed=true`, 12/13 evaluator rules passing, and PT13 only as advisory for unhedged superlatives. Corpus count is 359, selected evidence is 333, T3 full/selected count is 46, verified/dropped sentences are 51/29, and generator body-prose word count is 1780.

**Full Citation Audit**

| # | Tier | Live result | Verdict | Audit note |
|---:|---|---|---|---|
| 1 | T1 | NEJM/SURPASS-2 live-index verified | FAITHFUL | Supports HbA1c target attainment versus semaglutide 1 mg; no trial-name binding error. |
| 2 | T1 | MDPI full text live-fetched | FAITHFUL | Supports broad RCT meta-analysis efficacy/safety claims across diabetes/obesity. |
| 3 | T1 | Lancet DOI live-index verified | FAITHFUL | Supports SURPASS-3 degludec comparator and dose-specific HbA1c results. |
| 4 | T1 | Springer PDF live-fetched | FAITHFUL | Supports median time-to-HbA1c and weight-loss thresholds in SURPASS-2/3. |
| 5 | T1 | Lancet DOI live-index verified | FAITHFUL | Supports SURPASS-4 glargine comparator, T2D/increased CV-risk population, and efficacy claims. |
| 6 | T1 | Nature article live-fetched | FAITHFUL | Supports SURPASS-AP-Combo identity, insulin glargine comparator, HbA1c reductions, and hypoglycemia statement. |
| 7 | T2 | Oxford/JES live-fetched | FAITHFUL | Supports dose-dependent GI AEs, 15 mg discontinuation, mild hypoglycemia, and low pancreatitis/cholecystitis/MTC trial rates. |
| 8 | T2 | Frontiers full text live-fetched | FAITHFUL | Supports systematic-review safety comparison versus GLP-1 RAs and higher nausea/vomiting/discontinuation with higher doses. |
| 9 | T2 | Frontiers PDF/live source verified | FAITHFUL | Duplicate/supporting source for [8]; no added distortion. |
| 10 | T1 | JAMA live-index body verified | FAITHFUL | Supports SURMOUNT-4 lead-in GI rates and maintenance/withdrawal weight outcomes; clearly obesity-without-diabetes, but the report labels it as obesity trial. |
| 11 | T1 | PMC URL blocked by browser check, same JAMA article live-index verified | FAITHFUL | Source identity and content verified through the publisher live body; no claim conflict. |
| 12 | T4 | PMC/JAMA source live-index verified | FAITHFUL | Supports SURMOUNT-CN obesity trial thyroid-cancer/non-MTC statement; report labels obesity trial. |
| 13 | T4 | Publisher URL bot-gated, live search body verified | FAITHFUL | Supports FAERS T2D disproportionality signals for MTC and pancreatitis; report treats as pharmacovigilance signal. |
| 14 | T2 | Springer PDF live-fetched | FAITHFUL | Supports T2D NMA conclusion that tirzepatide is comparable to semaglutide 2.0 mg for HbA1c and stronger for weight. |
| 15 | T4 | DOI/live-index verified | FAITHFUL | Supports SURPASS-2 post hoc composite target claims. |
| 16 | T2 | Cureus DOI page live-fetched | FAITHFUL | Supports direct comparative meta-analysis favoring tirzepatide over semaglutide for weight loss. |
| 17 | T4 | medRxiv PDF live-index verified | FAITHFUL | Supports higher 5/10/15% weight-loss achievement with tirzepatide versus semaglutide in US real-world cohort. |
| 18 | T2 | Journal/DOAJ live-index verified | FAITHFUL | Supports tirzepatide versus long-acting insulin efficacy and hypoglycemia/GI tradeoff; report's 80-89%/49% and 62-83%/7% target numbers are directionally consistent with this evidence family. |
| 19 | T2 | Springer article live-fetched | FAITHFUL | Supports basal-insulin background NMA versus dulaglutide, exenatide, and lixisenatide. |
| 20 | T1 | Wiley DOI live-index verified | FAITHFUL | Supports indirect semaglutide 2 mg comparison and higher discontinuation odds with tirzepatide 10/15 mg. |
| 21 | T2 | Nature/IJO live-fetched | FAITHFUL | Supports long-acting insulin meta-analysis and lower hypoglycemia but higher GI AE tradeoff. |
| 22 | T2 | Frontiers full text live-fetched | FAITHFUL | Supports dose-response efficacy and safety ranking: 15 mg strongest efficacy, 5 mg safest. |
| 23 | T2 | Cureus PDF live-fetched | FAITHFUL | Supports additional body-weight reductions for 10/15 mg versus 5 mg and higher AE risks. |
| 24 | T3 | FDA summary review PDF live-fetched | FAITHFUL | Supports Mounjaro proprietary name, T2D adjunct-to-diet/exercise indication, dosing initiation/escalation, and approval recommendation. |
| 25 | T3 | FDA clinical pharmacology review live-index verified | FAITHFUL | Supports 2.5 mg initiation and 2.5 mg every-4-week titration in phase 3 dosing schedules. |
| 26 | T3 | EMA SmPC PDF live-fetched | FAITHFUL | Supports EMA T2D/weight indications and EMA precautions for severe GI disease, retinopathy, aspiration, and heart-rate-related labeling. |
| 27 | T3 | EMA overview PDF live-fetched | FAITHFUL | Supports EMA overview of Mounjaro use in T2D and weight management. |
| 28 | T3 | EMA variation report PDF live-fetched | FAITHFUL | Supports EMA weight-management expansion context. |
| 29 | T3 | FDA Zepbound summary review PDF live-fetched | FAITHFUL | Supports FDA approval/review basis for chronic weight management under Zepbound. |
| 30 | T3 | FDA Zepbound clinical review live-index verified | FAITHFUL | Supports Zepbound clinical-review context and device/approval linkage to Mounjaro. |
| 31 | T3 | FDA Zepbound 2026 label PDF live-fetched | EMBELLISHED | The source itself supports FDA boxed warning, contraindications, dosing, and warnings; the report misuses it in a sentence saying "both agencies" have a boxed warning. It does not support an EMA claim. |
| 32 | T3 | FDA Mounjaro 2025 label PDF live-fetched | EMBELLISHED | The source supports FDA Mounjaro boxed warning and MTC/MEN2 contraindication; the report overgeneralizes this FDA position across agencies and does not contrast EMA. |
| 33 | T3 | NICE draft/committee PDF live-fetched | FAITHFUL | Supports NICE T2D access conditions and lower BMI thresholds. |
| 34 | T3 | NICE TA924 PDF live-fetched | FAITHFUL | Supports final NICE T2D recommendation conditions: triple therapy failure/intolerance/contraindication plus BMI/occupational/obesity-complication criteria. |
| 35 | T3 | NICE TA1026 prescribing guide live-fetched | FAITHFUL | Supports obesity prescribing guide dose initiation, 2.5 mg increments every 4 weeks, and 5/10/15 mg maintenance doses. |

**Regulatory Sentences**
Regulatory source retrieval itself is effective: all 12 T3 bibliography entries resolve or are live-index verified, including FDA accessdata PDFs, EMA PDFs, and NICE PDFs/pages. The report also uses regulatory evidence for content V17 could not support: FDA Mounjaro T2D indication, FDA Zepbound weight-management indication, EMA Mounjaro T2D/weight indications, and NICE T2D recommendation criteria.

The blocker is wording. The report says, "A key safety warning from both agencies is a boxed warning for risk of thyroid C-cell tumors..." while citing FDA labels [31][32]. EMA is not shown as having a boxed warning, and EMA product information does not match FDA's formal MTC/MEN2 contraindication framing. The correct synthesis is: FDA labels carry boxed warning and MTC/MEN2 contraindications; EMA SmPC includes warnings/precautions and has hypersensitivity as the formal contraindication. The current report conflates jurisdictions.

NICE is handled cleanly. TA924 recommends tirzepatide for T2D only under defined criteria after ineffective/not tolerated/contraindicated triple oral therapy, BMI thresholds/occupational implications/obesity-related complications, and lower BMI thresholds for specified ethnic backgrounds. TA1026 obesity prescribing guidance is correctly kept separate from T2D recommendation logic.

**M-25a Regression Check**
No SURPASS/SURMOUNT binding regression found. SURPASS-3, SURPASS-4, SURPASS-AP-Combo, SURMOUNT-4, and SURMOUNT-CN are tied to the correct source identities. Obesity-only SURMOUNT evidence is not silently presented as T2D efficacy; it is used in safety/weight-management contexts, though direct T2D trial evidence remains preferable for headline T2D claims.

**V17 vs V18**
V18 improves materially over V17 on the regulatory-framing gap. V17 had no regulatory-agency URLs and relied on trial/pharmacovigilance sources for safety. V18 has a dedicated Regulatory section, 12 T3 cites, FDA/EMA/NICE source diversity, and practical dosing/contraindication/recommendation content. Integration is reasonably clean as a final section rather than a pasted appendix: it follows efficacy, safety, comparative, and dose-response sections and links dosing/indications/warnings to earlier safety material.

The T2D focus is mostly maintained. FDA Mounjaro, EMA Mounjaro, and NICE TA924 directly answer adult T2D; Zepbound/NICE TA1026 obesity material is relevant to the weight-loss side of the user question but should stay explicitly separate from glycemic-control labeling.

Jurisdiction differences are only partially surfaced. FDA vs EMA indications are separated, and NICE is named as UK guidance. But the safety warning/contraindication sentence conflates FDA and EMA. This is the decisive regression versus V17: V17 lacked regulatory framing, but it also lacked this regulatory overclaim.

**Tier-1 DR Comparison**
Compared with `state/compare_chatgpt_dr.txt`, V18 is closer to tier-1 DR on jurisdiction-aware framing because it now cites FDA, EMA, and NICE and includes label/guidance-level practical prescribing content. It still falls short of ChatGPT DR's regulatory precision, which explicitly states that U.S. labeling and EMA SmPC are not interchangeable.

Compared with `state/compare_gemini_dr.txt`, V18 has cleaner source quality and less promotional tone, but Gemini's regulatory breadth included Health Canada and safety-update material that V18 still does not cover. V18's main weakness is narrower and more fixable: jurisdiction grammar, not lack of source discovery.

**STOP Or CONTINUE**
CONTINUE. Next fix: add a regulatory-jurisdiction verifier that flags any sentence combining FDA/EMA/NICE/Health Canada claims unless each jurisdiction-specific clause is supported by a source from that jurisdiction, and require label contraindications to be stated per jurisdiction. For this report, rewrite the FDA/EMA safety sentence to separate FDA boxed warning/MTC-MEN2 contraindications from EMA SmPC hypersensitivity contraindication and warnings/precautions, then resweep the output.
