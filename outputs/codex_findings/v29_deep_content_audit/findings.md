# V29 Deep Content Audit: Tirzepatide/T2D

Audit lens: clinical document review under PRISMA 2020, AMSTAR-2, GRADE, and clinical-epidemiology judgment. This is a content audit, not the M-49 metadata preservation audit.

## A. SURPASS-2: tirzepatide vs semaglutide 1 mg

**V29 says.** V29 mentions SURPASS-2 only through a pre-planned exploratory analysis: "a pre-planned analysis of SURPASS-2 and SURPASS-3 found the median time to achieve HbA1c <7.0% was 8.1 weeks ... compared to 12.0 weeks with semaglutide 1 mg" and "The median time to first achieve ≥5% weight loss in SURPASS-2 was faster with tirzepatide 5 mg (16.0 weeks) and 10/15 mg (12.4 weeks) than with semaglutide 1 mg (24.0 weeks).[1]" ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:5)). The bibliography confirms [1] is not the Frías NEJM primary but a 2023 exploratory analysis ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:66)). V29 also cites an indirect semaglutide 2 mg comparison rather than the requested head-to-head ETDs ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:5)).

**ChatGPT says.** ChatGPT gives the correct PICO and primary endpoint: "SURPASS-2 ... 40-week, open-label, randomized active-comparator trial in patients on metformin" with N=1,879 and semaglutide 1 mg comparator (state/compare_chatgpt_dr.txt:161-188). It reports the exact HbA1c ETDs versus semaglutide of "-0.15 ... -0.39 ... -0.45" with CIs/P values and weight ETDs "-1.9, -3.6, -5.5 kg" (state/compare_chatgpt_dr.txt:189-202).

**Gemini says.** Gemini states SURPASS-2 compared tirzepatide 5/10/15 mg with semaglutide 1 mg and gives headline reductions: 15 mg HbA1c reduction 2.46%, 92.2% achieving HbA1c <7%, and 12.4 kg weight loss versus 6.2 kg with semaglutide; it also gives 5 mg HbA1c reduction 2.09% and weight reduction 7.8 kg (state/compare_gemini_dr.txt:110-130).

**Critical appraisal.** V29 still fails the audit target. It does not provide the Frías NEJM 2021 primary publication, does not report the requested HbA1c ETDs, does not give uncertainty, and shifts toward time-to-threshold and indirect semaglutide 2 mg material. By PRISMA/AMSTAR-2 standards, that is selective and secondary rather than primary-trial centric. ChatGPT is closest to systematic-review standard because it gives PICO, open-label design, exact effect estimates, and uncertainty. Gemini is useful but lacks CIs and is rhetorically more promotional.

**Winner: ChatGPT.**

## B. SURPASS-CVOT: MACE-3 vs dulaglutide

**V29 says.** V29 mentions SURPASS-CVOT only once in the body: "In the SURPASS-CVOT trial ... tirzepatide was noninferior to dulaglutide for a composite of cardiovascular death, myocardial infarction, or stroke.[43]" ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:25)). Bibliography item [43] is the design/baseline paper, not the Nicholls NEJM 2025 primary outcomes publication ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:108)).

**ChatGPT says.** ChatGPT gives the trial frame and results: adults with T2D and established ASCVD, N=13,299, tirzepatide up to 15 mg vs dulaglutide 1.5 mg, time to first 3-point MACE over median about 4 years, with "Primary event in 12.2% vs 13.1%; HR 0.92 (95% CI 0.83 to 1.01), P=0.003 for noninferiority and P=0.09 for superiority" (state/compare_chatgpt_dr.txt:525-557).

**Gemini says.** Gemini reports the correct numeric frame: late-2025 publication, N=13,299, active-comparator design, 12.2% vs 13.1%, HR 0.92, 95.3% CI 0.83 to 1.01, P=0.003 for non-inferiority and P=0.09 trend toward superiority (state/compare_gemini_dr.txt:419-433). It then overinterprets the result as validating "robust systemic vascular benefits" and later claims definitive cardiovascular protection (state/compare_gemini_dr.txt:434-441, 664-669).

**Critical appraisal.** V29 improves over V28 only by at least naming noninferiority, but it still omits the HR, CI, event rates, follow-up, and superiority/noninferiority distinction detail, and it cites the wrong paper. For GRADE and clinical epidemiology, an active-comparator NI result against dulaglutide is reassuring cardiovascular safety, not proven superiority. ChatGPT gives the cleanest and most defensible interpretation. Gemini's numeric extraction is good, but its conclusion is materially overstated.

**Winner: ChatGPT.**

## C. SURPASS-4: 52/104-week high-CV-risk trial vs insulin glargine

**V29 says.** V29 does not substantively discuss SURPASS-4 in the body. The report body never names SURPASS-4 outside generic program references, and the bibliography does not contain the Del Prato Lancet 2021 primary trial publication ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:5), [report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:66), [report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:108)).

**ChatGPT says.** ChatGPT describes SURPASS-4 as a "52-week, open-label, randomized active-comparator trial in high cardiovascular-risk patients on oral agents; extension to 104 weeks," N=1,995 with 87% prior cardiovascular disease, tirzepatide 5/10/15 mg vs insulin glargine, week-52 HbA1c ETDs of -0.80/-0.99/-1.14 with CIs, weight ETDs -9.0/-11.4/-13.5 kg, 104-week durability, and MACE-4 HR 0.74 (95% CI 0.51 to 1.08) (state/compare_chatgpt_dr.txt:309-376).

**Gemini says.** Gemini says SURPASS-4 enrolled people with increased cardiovascular risk and reports headline week-52 numbers at 15 mg: HbA1c reduction 2.58%, weight reduction 11.7 kg from baseline 90.3 kg, versus glargine HbA1c reduction 1.44% and 1.9 kg weight gain, plus HbA1c <7% in 84.9% vs 48.8% (state/compare_gemini_dr.txt:176-190).

**Critical appraisal.** V29 still misses a clinically central trial despite M-51/M-52 being specifically intended to preserve it. This is a major content failure. ChatGPT again performs best because it captures the high-CV-risk population, open-label design, week-52 primary result, 104-week durability, and cardiovascular-safety caveat. Gemini is useful but thinner and less explicit about uncertainty.

**Winner: ChatGPT.**

## D. Mechanism: dual GIP/GLP-1 agonism and clamp evidence

**V29 says.** V29 gives general PK and mechanism statements: bioavailability about 80%, Tmax 8-72 hours, half-life about 5 days, 99% albumin binding, C20 fatty diacid metabolism, nuanced GIP effect on glucagon, and HOMA2-IR/HOMA2-B improvements ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:17)). It does not report the requested clamp findings such as 63% M-value improvement or enhanced first- and second-phase insulin secretion, and it does not bind such numbers to inline evidence IDs in the same sentence.

**ChatGPT says.** ChatGPT does not meaningfully cover the mechanistic clamp target. Its strongest relevant uncertainty content is methodological rather than biologic: sponsorship, open-label design, and comparator-evolution caveats (state/compare_chatgpt_dr.txt:50-66).

**Gemini says.** Gemini provides the requested mechanistic content: tirzepatide is a synthetic "39-amino acid peptide" with a "C20 fatty diacid moiety" and mean half-life about five days; it describes imbalanced dual agonism and reports that clamp studies showed a 63% increase in whole-body insulin sensitivity by M-value and enhanced first- and second-phase insulin secretion (state/compare_gemini_dr.txt:39-63).

**Critical appraisal.** V29 remains below the M-47 target. It has mostly review-style PK/mechanism prose instead of primary human clamp extraction. Gemini is the only artifact that actually answers the mechanistic question with quantitative human physiology data. ChatGPT is largely nonresponsive to this topic.

**Winner: Gemini.**

## E. Regulatory coverage: FDA / EMA / NICE / Health Canada

**V29 says.** V29 gives broad cross-jurisdiction coverage: FDA Mounjaro and Zepbound approvals, boxed warning, contraindications, dosing, pulmonary aspiration warning, EMA authorization and age >=10 T2D indication, Health Canada authorization and boxed warning, and NICE TA924-style access criteria and commercial arrangement ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:21)).

**ChatGPT says.** ChatGPT accurately summarizes current U.S./EMA dosing and key warning differences, including U.S. contraindications and warnings and the fact that EMA handles some items as warnings rather than formal contraindications (state/compare_chatgpt_dr.txt:967-982). It is narrower on NICE and Health Canada.

**Gemini says.** Gemini includes useful FDA/Health Canada warning detail, including hypoglycemia co-therapy caution and thyroid-tumor warnings (state/compare_gemini_dr.txt:529-552), but it also states that Mounjaro has specific FDA pediatric allowances for patients age 10 years and older (state/compare_gemini_dr.txt:567-572), which is a serious jurisdictional conflation relative to the EMA-specific pediatric language.

**Critical appraisal.** V29 preserves the best four-jurisdiction clinical reference among the three. It is not perfect, but it most closely matches what a clinician actually needs when asking what can be prescribed under FDA/EMA/NICE/Health Canada rules. ChatGPT is accurate but narrower. Gemini has more 2026 warning texture but introduces a material FDA/EMA mix-up.

**Winner: V29.**

## F. Contradictions and uncertainty: sponsorship, open-label bias, noninferiority

**V29 says.** V29 explicitly discloses corpus weakness: only 14% T1, 9% T2, 28% T4, and 27% T7/UNKNOWN combined, with 15 numeric contradiction flags across body weight/weight-loss claims ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:29), [report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:43)). It also correctly says SURPASS-CVOT was noninferior to dulaglutide ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:25)). But it does not clearly discuss sponsorship, open-label bias, or semaglutide 1 mg versus modern 2 mg indirectness.

**ChatGPT says.** ChatGPT explicitly states all pivotal SURPASS studies were sponsored by Eli Lilly, explains that the evidence base mixes double-blind and open-label trials and why open-label design matters, and flags that SURPASS-2 used semaglutide 1 mg while semaglutide 2 mg is now used in practice, so some comparisons are indirect (state/compare_chatgpt_dr.txt:50-66). It also correctly interprets SURPASS-CVOT as noninferiority rather than superiority (state/compare_chatgpt_dr.txt:550-557).

**Gemini says.** Gemini numerically reports the NI result, but later says SURPASS-CVOT "has definitively proven" cardiovascular and renal protection and that tirzepatide "significantly reduce[d]" MACE while outperforming active cardioprotective comparators (state/compare_gemini_dr.txt:664-669), which conflicts with its own earlier HR/CI/P values.

**Critical appraisal.** This remains split. V29 is best on explicit contradiction disclosure and corpus-tier transparency. ChatGPT is best on trial-design bias, sponsorship, indirectness, and correct CVOT interpretation. Gemini is worst because it converts NI plus a superiority miss into definitive benefit language.

**Winner: Tie (ChatGPT / V29).**

## V29-specific checks

### 1. Custody telemetry

Read first as instructed. The custody file shows the V29 preservation fix did not land for the intended anchor set.

| Anchor | found | selected | injected | cited | quote_adequate | Readout |
|---|---|---|---|---|---|---|
| SURPASS-1 | true | true | true | false | true | Present in custody pipeline, but still not cited in verified prose. |
| SURPASS-2 | false | false | false | false | false | Primary never found in live corpus by custody logic; M-51/M-52 did not rescue it. |
| SURPASS-3 | false | false | false | false | false | Same failure pattern. |
| SURPASS-4 | true | true | true | false | true | Only anchor clearly preserved into selection/injection, but still not cited in verified prose. |
| SURPASS-5 | true | true | true | false | true | Preserved into pipeline, not cited in verified prose. |
| SURPASS-6 | false | false | false | false | false | Not found by custody logic despite bibliography presence via a secondary source. |
| SURPASS-CVOT | false | false | false | false | false | Nicholls primary did not survive; bibliography keeps only the design paper. |
| SURMOUNT-1 | false | false | false | false | false | Not preserved. |
| SURMOUNT-2 | false | false | false | false | false | Garvey Lancet 2023 not preserved; bibliography keeps only a T7 post hoc abstract. |
| SURMOUNT-3 | false | false | false | false | false | Not preserved. |
| SURMOUNT-4 | false | false | false | false | false | Not preserved. |

Supporting diagnostics:

- `manifest.json` records `m42e_primary_floor matched=1 ... anchors=['SURPASS-1']` and `m51_anchor_primary_custody matched=1 inserted=1 ... anchors=['SURPASS-4']`, showing only one M-51 anchor rescue actually fired.
- `m44_primary_citation_telemetry.json` shows injections only for SURPASS-1, SURPASS-4, and SURPASS-5, with no validator violations, but none reached verified-prose citation.

### 2. M-42b Trial Summary table

**Fail.** No usable trial-summary table is present in the V29 report. `report.md` is the short six-section markdown artifact with no trial table, no per-trial rows, and no structured cells at all ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:1), [report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:31)). Therefore the ">=6 rows with real numbers" target is not met.

### 3. M-50 Per-Trial Summaries

**Fail, and regression from V28.** `m50_per_trial_subsections.json` reports `total_subsections: 0` and `entries: []`, meaning no per-trial subsection block survived into V29. This is worse structurally than V28, which at least had partial trial summaries.

### 4. M-47 Mechanism extraction

**Fail.** `m47_mechanism_clamp_diagnostic.json` reports `any_passes_threshold=false` and `m47_mechanism_extraction_incomplete=true`. In the report itself, the mechanism section contains no same-sentence quantitative clamp findings with inline evidence IDs; it only gives generic PK values and review-level mechanism prose ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:17)).

### 5. Bibliography delta check against the intended V29 rescue set

**Fail.** The V29 bibliography still does **not** contain the intended rescued primaries:

- SURPASS-2 primary (Frías NEJM 2021): absent. Replaced by a 2023 exploratory analysis ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:66)).
- SURPASS-4 primary (Del Prato Lancet 2021): absent.
- SURPASS-CVOT primary (Nicholls NEJM 2025): absent. Only design/baseline paper retained ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:108)).
- SURMOUNT-1 primary (Jastreboff NEJM 2022): absent.
- SURMOUNT-2 primary (Garvey Lancet 2023): absent. Only T7 post hoc abstract retained ([report.md](/C:/POLARIS/outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md:107)).

## Final aggregate

Topic wins:

| Topic | Winner |
|---|---|
| A. SURPASS-2 | ChatGPT |
| B. SURPASS-CVOT | ChatGPT |
| C. SURPASS-4 | ChatGPT |
| D. Mechanism | Gemini |
| E. Regulatory | V29 |
| F. Contradictions/uncertainty | Tie: ChatGPT / V29 |

Counting the tie as 0.5 each: ChatGPT 3.5, V29 1.5, Gemini 1. If ties are counted as full topic credit: ChatGPT 4, V29 2, Gemini 1.

## 7-dimension cross-review scoreboard

| Dimension | V29 vs ChatGPT/Gemini | Rationale |
|---|---|---|
| 1. Citations | LOSE_BOTH | Intended primaries still missing from bibliography and custody: Frías, Del Prato, Nicholls, Jastreboff, Garvey absent. |
| 2. Regulatory | BEAT_BOTH | Best four-jurisdiction clinical coverage across FDA/EMA/NICE/Health Canada. |
| 3. Jurisdictional | BEAT_BOTH | Best preservation of jurisdiction-specific distinctions, especially EMA pediatric >=10 and NICE access criteria. |
| 4. Claim frames | LOSE_BOTH | SURPASS-2 is secondary-analysis framed, SURPASS-4 absent, CVOT reduced to a thin NI sentence without HR/CI/event rates. |
| 5. Structural depth | LOSE_BOTH | No trial-summary table and no per-trial subsections; this is a regression from V28. |
| 6. Contradiction handling | BEAT_BOTH | Strong explicit contradiction ledger plus tier-distribution transparency. |
| 7. Narrative depth | LOSE_BOTH | Mechanism remains generic and review-derived; clinical trial narration is materially thinner than ChatGPT and mechanistic content is far below Gemini. |

Adjudicated V29 aggregate on 7 dimensions: **3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH**.

## Closest-to-systematic-review-standard

**ChatGPT.** It most consistently supplies PICO, study design, effect estimate with uncertainty, clinically relevant caveats, and correct CVOT interpretation. V29 retains the best contradiction ledger and the broadest regulatory section, but it still fails core primary-trial preservation and structural synthesis requirements. Gemini remains strongest only on mechanism.

## Clinical usefulness verdict

| Physician question | Best report | Reason |
|---|---|---|
| "How much better is tirzepatide than semaglutide 1 mg in SURPASS-2?" | ChatGPT | Gives the exact HbA1c/weight ETDs, CIs, P values, timepoint, and design. |
| "Does tirzepatide improve cardiovascular outcomes versus dulaglutide?" | ChatGPT | Gives the HR/CI/P values and correctly frames noninferiority without claiming superiority. |
| "What happened in high-CV-risk patients versus insulin glargine?" | ChatGPT | Gives the 52-week and 104-week SURPASS-4 result and safety context. |
| "What is the human mechanistic evidence?" | Gemini | Gives the clamp-derived quantitative mechanism details V29 lacks. |
| "What can I prescribe under FDA/EMA/NICE/Health Canada rules?" | V29 | Broadest and most clinically useful cross-jurisdiction coverage. |
| "What are the major evidence weaknesses?" | ChatGPT for design bias; V29 for contradiction ledger | ChatGPT is better on sponsorship/open-label/indirectness; V29 is better on corpus contradiction disclosure. |

## Stop-criterion adjudication

The V29 target projection was 4-5 BEAT_BOTH + 2-3 BEAT_ONE + 0-1 LOSE_BOTH. This deep content audit does not support that projection.

Two conclusions matter operationally:

1. V29 is **not shippable**. It remains far below the unchanged stop criterion of 7/7 BEAT_BOTH.
2. One dimension **regressed from V28**: structural depth. V28 at least had partial trial-summary/per-trial scaffolding; V29 has none (`m50_per_trial_subsections.json` shows zero subsections). Under the user's rule, this triggers the halt condition.

**Shippable verdict: NOT SHIPPABLE.**
