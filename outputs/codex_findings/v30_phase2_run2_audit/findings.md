# V30 Phase-2 run-2 audit vs ChatGPT DR + Gemini DR

**7-dimension verdict**: BB=1/7 | BO=2/7 | LB=4/7 | TIE=0/7

## Primary-trial spot-check (run-1 regression guard)

1. SURPASS-2: correct tirzepatide content. Evidence: V30 now says "Comparator: semaglutide at a dose of 1 mg" with the expected HbA1c ETDs, CIs, and P values, and names Eli Lilly as sponsor [report.md:11].
2. SURPASS-4: correct. Evidence: V30 now describes "adults with type 2 diabetes and high cardiovascular risk" with comparator "insulin glargine" [report.md:17-19].
3. SURPASS-5: correct. Evidence: V30 describes add-on use in adults treated with once-daily insulin glargine with or without metformin and gives the week-40 HbA1c endpoint [report.md:21-23].
4. SURPASS-6: missing. Evidence: the report jumps from SURPASS-5 to SURMOUNT-2 and then Mechanism [report.md:21-31], even though the manifest marks `efficacy_surpass_6` as `status: "pass"` [manifest.json:412-415].
5. Thomas clamp: retrieval gap. Evidence: the report renders both requested secretion fields as "not extractable" [report.md:31-33]; the manifest classifies the paper as `abstract_only` [manifest.json:522-573], and the clamp diagnostic shows `match_count: 0` and `passes_threshold: false` [m47_mechanism_clamp_diagnostic.json:2-13].

Regression status: PARTIAL

## 7-dimension analysis

### 1. Citations
V30 says: "Comparator: semaglutide at a dose of 1 mg ... Etd with uncertainty ..." [report.md:11]; the bibliography lists SURPASS-1 to -5, SURMOUNT-2, and the Thomas clamp paper as T1 entries [report.md:99-105], but there is no SURPASS-6 entry and no regulatory bibliography block [report.md:98-121].
ChatGPT says: it "prioritizes the core SURPASS publications, the pre-approval statistical review from the FDA, the current U.S. prescribing information, [and] the product information from the EMA" [compare_chatgpt_dr.txt:51-53], and it includes detailed primary-trial coverage through SURPASS-6 [compare_chatgpt_dr.txt:161-218,309-520].
Gemini says: it narratively covers SURPASS-2/4/5/6 [compare_gemini_dr.txt:110-213], but the works cited lean heavily on PR and secondary sources such as "PR Newswire" for SURPASS-2 and SURPASS-4 [compare_gemini_dr.txt:699-704,730-736].
Critical appraisal: PRISMA/AMSTAR-2 favor direct primary-trial coverage with traceable references. V30 fixed the wrong-paper binding problem and has a better provenance taxonomy than Gemini, but missing SURPASS-6 and missing regulatory citations keep it behind ChatGPT. GRADE also favors ChatGPT here because it supplies more complete direct-trial effect estimates.
Winner: **ChatGPT** -> BO

### 2. Regulatory
V30 says: nothing substantive in the report body; it still claims "Completeness checklist: 7/7 topics covered" [report.md:75]. In the manifest, all regulatory rows are `fail_min_fields`, including FDA, EMA, NICE, and Health Canada [manifest.json:580-732].
ChatGPT says: "The U.S. prescribing information lists contraindications ..." while "The EMA product information is not identical" and clinicians should not assume U.S. and EU texts are interchangeable [compare_chatgpt_dr.txt:974-981].
Gemini says: "The most severe regulatory caution ... is its Boxed Warning (FDA) and Serious Warnings and Precautions box (Health Canada)" [compare_gemini_dr.txt:533-549], and it adds a Health Canada aspiration-risk update [compare_gemini_dr.txt:580-603].
Critical appraisal: Against the stated audit target, all three fall short of the full FDA-label + EMA-EPAR + NICE-TA + HC-monograph set. V30 is worst because its architecture expected these entities but the rendered report contains no regulatory conclusions at all, which is a PRISMA-style reporting failure.
Winner: **TIE** -> LB

### 3. Jurisdiction
V30 says: safety synthesis mentions "European EudraVigilance" and "US FDA Adverse Event Reporting System" [report.md:37], but there is no jurisdictional regulatory or access framing.
ChatGPT says: "align prescribing with local labeling, not assume the U.S. and EU texts are interchangeable" [compare_chatgpt_dr.txt:979-982].
Gemini says: the report explicitly synthesizes FDA plus Health Canada safety updates [compare_gemini_dr.txt:30-32,530-535,578-603].
Critical appraisal: The dimension asks for US/EU/UK/Canada coverage, not just drug-centric safety prose. V30 remains mostly drug-centric, while both competitors reach at least two jurisdictions; neither fully satisfies the jurisdiction brief because UK/NICE coverage is absent.
Winner: **TIE** -> LB

### 4. Claim-frames
V30 says: SURPASS-2 is well framed with population, comparator, endpoint, timepoint, ETD, CI, P value, design, and sponsor [report.md:11]; SURPASS-5 still gives background therapy and the week-40 endpoint [report.md:23]. But SURPASS-4 is reduced to population/comparator/sponsor only [report.md:19], and SURPASS-6 is absent [report.md:21-31].
ChatGPT says: SURPASS-2/4/5/6 are consistently framed with N, baseline profile, dose stratification, comparator, timepoint, ETD, CIs, P values, and safety [compare_chatgpt_dr.txt:161-218,309-520].
Gemini says: SURPASS-2/4/5/6 are dose- and timepoint-aware [compare_gemini_dr.txt:110-213], but uncertainty framing is weak and interpretation is often assertive, including "definitive" and "essential" language [compare_gemini_dr.txt:176-190,205-213].
Critical appraisal: GRADE rewards precise, population-specific effect estimates with explicit uncertainty. V30 is cleaner and more conservative than Gemini on uncertainty handling, so it has closed part of the V29 gap, but it still does not match ChatGPT's ETD/CI/P-depth across the full trial set.
Winner: **ChatGPT** -> BO

### 5. Structure
V30 says: the efficacy contract ends after SURPASS-5, then jumps to SURMOUNT-2 and Mechanism [report.md:21-31]; the trial summary and timeline are malformed and only two rows deep [report.md:47-59].
ChatGPT says: the report moves from executive summary to study architecture, per-trial table, efficacy, safety, regulation, NNT/NNH, evidence gaps, and timeline [compare_chatgpt_dr.txt:50-66,592-630,966-1118].
Gemini says: it has a recognizable arc from mechanism to SURPASS evidence to safety/regulation/future trajectory [compare_gemini_dr.txt:33-213,469-679], though its formatting is also noisy.
Critical appraisal: PRISMA-style reporting needs coherent section order and complete domain coverage. V30's malformed table/timeline plus the missing regulatory subsection are major presentation defects that materially weaken the auditability of the report.
Winner: **ChatGPT** -> LB

### 6. Contradictions
V30 says: "The contradiction detector flagged 14 numeric disagreements ..." and then enumerates numeric ranges with source tiers [report.md:77-95].
ChatGPT says: it acknowledges "genuine evidence gaps" and notes open-label design plus the semaglutide-1-mg comparator limitation [compare_chatgpt_dr.txt:60-66,1065-1086], but it does not inventory contradictions.
Gemini says: uncertainty is limited to narrow points such as rodent-thyroid relevance remaining "undetermined" [compare_gemini_dr.txt:539-551], while elsewhere it makes highly confident synthesis claims [compare_gemini_dr.txt:664-669].
Critical appraisal: PRISMA and GRADE both reward explicit handling of inconsistency. V30 is best here because it surfaces inconsistency and tier context, although AMSTAR-2 would still want endpoint- and population-level adjudication rather than raw detector output alone.
Winner: **V30** -> BB

### 7. Narrative depth
V30 says: the main free-form synthesis is concentrated in Safety, Comparative, and Population Subgroups [report.md:37-45], while the core efficacy section remains slot-bound and terse [report.md:5-23].
ChatGPT says: it adds comparative framing, target-attainment synthesis, safety context, NNT/NNH, patient selection, and ongoing-trial implications [compare_chatgpt_dr.txt:592-630,907-1047,1055-1118].
Gemini says: it is expansive and broad [compare_gemini_dr.txt:26-32,386-407,653-679], but part of that depth is noisy or overstated, including claims of outperforming established cardioprotective comparators [compare_gemini_dr.txt:664-669].
Critical appraisal: Narrative depth is not just length; it is clinically useful synthesis with disciplined scope. ChatGPT clearly outperforms V30, and Gemini still exceeds V30 on volume and synthesis even after downgrading for overreach.
Winner: **ChatGPT** -> LB

## Summary

Tally: BB=1 BO=2 LB=4 TIE=0

## Next

ITERATE with a specific fix plan.
1. Render passed contract slots into the report body before release, starting with `SURPASS-6` (`manifest.json:412-415` vs report gap at `report.md:21-31`).
2. Restore regulatory sections from the six failed contract rows and refuse `7/7 topics covered` unless FDA/EMA/NICE/HC conclusions are actually rendered (`report.md:75`, `manifest.json:580-732`).
3. Upgrade M-58 efficacy slots so SURPASS-4/5/6 carry comparator, dose, timepoint, ETD, CI, and P-value fields, not just minimal identity fields.
4. Treat the Thomas clamp row as an abstract-only retrieval/extraction gap, not a claim-frame bug, unless a licensed full text is supplied (`manifest.json:522-573`, `m47_mechanism_clamp_diagnostic.json:2-13`).
