# V27 Deep Content Audit: Tirzepatide/T2D

## A. SURPASS-2: tirzepatide vs semaglutide 1 mg

**V27 claim.** "A post hoc analysis of this trial found that all tirzepatide doses increased the proportion of patients achieving composite therapeutic targets ... compared to semaglutide 1 mg, with 57% ... versus 34% on semaglutide.[15]" (outputs/full_scale_v27/clinical/clinical_tirzepatide_t2dm/report.md:13). It also cites an aITC versus semaglutide 0.5 mg at week 40 rather than the primary head-to-head trial (line 13; bibliography [15]-[16] at report.md:78-79). The primary NEJM SURPASS-2 source is present in V27's live corpus (live_corpus_dump.json:44-45, 1202-1203) but not selected in the final bibliography.

**ChatGPT claim.** Its trial table gives the complete frame: "SURPASS-2 ... open-label ... N=1,879 ... mean HbA1c 8.28%; mean body weight 93.7 kg ... Tirzepatide 5/10/15 mg vs semaglutide 1 mg weekly ... Mean HbA1c change at week 40" (state/compare_chatgpt_dr.txt:161-188), with HbA1c ETDs and CIs/P values (lines 189-198) and weight "-7.6/-9.3/-11.2 vs -5.7 kg; ETD -1.9, -3.6, -5.5 kg" (lines 199-202).

**Gemini claim.** "SURPASS-2 ... evaluating ... tirzepatide (5 mg, 10 mg, and 15 mg) against once-weekly injectable semaglutide 1 mg" (state/compare_gemini_dr.txt:110-114), then says 15 mg reduced HbA1c 2.46% and weight 12.4 kg vs 6.2 kg with semaglutide (lines 124-127), and 5 mg reduced HbA1c 2.09% and weight 7.8 kg (line 130).

**Critical appraisal.** ChatGPT is closest to PRISMA/GRADE reporting: N, baseline HbA1c/weight, intervention doses, comparator, endpoint/timepoint, ETD, CI, P, and open-label status. Gemini gives numeric anchors but omits N and uncertainty and uses promotional language ("decisively," "gold standard"). V27 is weakest: it substitutes post hoc targets and indirect comparisons for primary trial effect estimates, so the claim frame is incomplete and lower certainty for the primary question.

**Winner:** ChatGPT.

## B. SURPASS-CVOT: MACE noninferiority vs dulaglutide

**V27 claim.** No substantive SURPASS-CVOT body claim. The report covers cardiovascular safety via SURPASS-4 and FDA/regulatory material, but the final bibliography has no SURPASS-CVOT primary citation; CVOT appears only in the corpus (live_corpus_dump.json:1720, 2051, 3164-3186). This is a material omission for a 2026 clinical review.

**ChatGPT claim.** "Tirzepatide up to 15 mg vs dulaglutide 1.5 mg ... Time to first 3-point MACE over median ~4 years ... 12.2% vs 13.1%; HR 0.92 (95% CI 0.83 to 1.01), P=0.003 for noninferiority and P=0.09 for superiority" (state/compare_chatgpt_dr.txt:535-557). It explicitly warns this "is not the same as proving superiority" (lines 955-959) and concludes CV evidence supports "noninferiority versus dulaglutide rather than clear superiority" (lines 1061-1064).

**Gemini claim.** It correctly states N=13,299, dulaglutide comparator, MACE-3 definition, 12.2% vs 13.1%, HR 0.92, CI 0.83-1.01, P=0.003 noninferiority and P=0.09 superiority trend (state/compare_gemini_dr.txt:419-433). But it later claims CVOT "definitively proven" durable cardiovascular/renal protection and that tirzepatide "significantly reduce[d]" MACE and outperformed active cardioprotective comparators (lines 664-669).

**Critical appraisal.** ChatGPT has the correct noninferiority frame and avoids superiority inflation. Gemini has the numeric frame but fails clinical-epidemiology interpretation: P=0.09 for superiority is not statistical superiority. V27 omits the key trial despite having corpus access.

**Winner:** ChatGPT.

## C. SURPASS-4: high-CV-risk population vs insulin glargine

**V27 claim.** "The SURPASS-4 trial specifically compared tirzepatide to insulin glargine in patients with type 2 diabetes and increased cardiovascular risk.[18]" (report.md:13), supported by the primary Lancet citation [18] (report.md:81). V27 adds that broader meta-analysis found reduced hypoglycemia versus insulin (line 13), but it does not give SURPASS-4 N, baseline risk, 52-week primary endpoint, 104-week durability, weight change, or hypoglycemia/event details.

**ChatGPT claim.** "SURPASS-4 ... open-label ... high cardiovascular-risk ... extension to 104 weeks ... N=1,995 ... HbA1c 8.52%; weight 90.3 kg; BMI 32.6 kg/m2; history of cardiovascular disease in 87%" (state/compare_chatgpt_dr.txt:309-334). It gives 52-week HbA1c ETDs with CIs/P values (lines 344-352), weight changes and 104-week values: HbA1c "6.43/6.13/6.11 vs 7.47" and weight "-5.8/-10.4/-11.1 kg vs +2.3 kg" (lines 357-364), plus nausea/discontinuation and MACE-4 HR 0.74 (lines 365-376).

**Gemini claim.** "SURPASS-4 evaluated tirzepatide against titrated daily insulin glargine in participants with type 2 diabetes and an increased baseline cardiovascular risk profile" (state/compare_gemini_dr.txt:176-178), gives 15 mg HbA1c -2.58%, weight -11.7 kg from baseline 90.3 kg, glargine HbA1c -1.44% and +1.9 kg (lines 179-186), and claims benefit "without the hypoglycemic liabilities of glargine" (line 189).

**Critical appraisal.** ChatGPT again supplies the tightest frame, including 104-week durability. Gemini is numerically useful but underframed and overphrases risk mitigation. V27 cites the right primary trial but fails PRISMA-style extraction and omits 104-week durability and trial-specific hypoglycemia.

**Winner:** ChatGPT.

## D. Mechanism of action

**V27 claim.** "This dual agonism produces synergistic effects on insulin secretion and glucagon suppression" and a phase 1 trial provides "direct mechanistic evidence" (report.md:17), citing Thomas/Lancet Diabetes & Endocrinology as [27] (report.md:90). V27 mentions beta cells, alpha cells, adipocytes, insulin sensitivity, and half-life, but gives no Kd/EC50, clamp M-value, or first-/second-phase secretion effect size.

**ChatGPT claim.** ChatGPT barely frames mechanism in the extracted passages; its strength is study architecture and comparator caveats, not receptor biology.

**Gemini claim.** Tirzepatide is a "39-amino acid peptide" with a "C20 fatty diacid moiety" and "mean half-life ... approximately five days" (state/compare_gemini_dr.txt:40-46). It describes imbalanced dual agonism (lines 47-53) and gives human clamp data: "hyperinsulinemic-euglycemic clamp ... tirzepatide ... 15 mg increased whole-body insulin sensitivity by ... 63%, as measured by the M-value" (lines 54-58), plus hyperglycemic clamp first-/second-phase insulin secretion (lines 60-63).

**Critical appraisal.** Gemini has the most clinically useful mechanistic anchors and links mechanism to human T2D clamp data. V27 identifies the right primary mechanistic paper but summarizes it too generally. None of the reports provide receptor Kd/EC50; Gemini's claim that weaker GLP-1 affinity was "clinically vital" to avoid GI intolerance is mechanistically plausible but overinterpreted without receptor/effect-size support.

**Winner:** Gemini.

## E. Regulatory divergence: US, EU, UK, Canada

**V27 claim.** V27 names US Mounjaro 2022 T2D, Zepbound 2023 chronic weight management, boxed warning/contraindications, aspiration and KwikPen warnings; EMA adult/adolescent/child age >=10 T2D and weight-management indications; Health Canada indications and serious-warning boxes; NICE TA924 T2D criteria with BMI/ethnic/occupational details; and TA1026 obesity stopping rule (report.md:25; sources [35]-[47] at report.md:98-110).

**ChatGPT claim.** It covers FDA/EMA dosing and contraindication/warning differences: U.S. MTC/MEN2/hypersensitivity contraindications and warnings for pancreatitis, hypoglycemia, retinopathy, gallbladder disease, aspiration; EMA hypersensitivity formal contraindication and local-label caveat (state/compare_chatgpt_dr.txt:966-982). It lacks NICE and Health Canada specificity.

**Gemini claim.** It covers FDA/Health Canada hypoglycemia dose-reduction warnings (state/compare_gemini_dr.txt:530-532), FDA/Canada thyroid warning (lines 533-541), pediatric language but incorrectly attributes age 10 allowance to FDA Mounjaro (lines 567-572), Health Canada aspiration review (lines 580-603), KwikPen warning (lines 608-625), and counterfeit advisories (lines 626-639). It lacks EMA and NICE.

**Critical appraisal.** V27 is the most jurisdiction-complete and least conflated. Gemini has valuable Canada/KwikPen/counterfeit detail but likely misrepresents pediatric divergence by assigning age >=10 T2D to FDA rather than the EU/EMA item specified for this audit. ChatGPT is accurate but too narrow.

**Winner:** V27.

## F. Contradictions and uncertainty

**V27 claim.** V27 explicitly discloses extractor heterogeneity: "tirzepatide / body weight (15 mg): cited values range 1.87 to 95.0%" (report.md:47) and states detector flags are artifacts across endpoints, doses, populations, comparators, timepoints, and tiers (lines 43-44). It also acknowledges "low proportion of primary research" (line 29). It does not discuss open-label limitations or Eli Lilly sponsorship bias.

**ChatGPT claim.** "All pivotal SURPASS studies were sponsored by Eli Lilly and Company" (state/compare_chatgpt_dr.txt:50-54). It states the program mixes "double-blind placebo-controlled trials and open-label active-comparator trials" and that open-label designs may influence symptom reporting, discontinuation, and behavioral co-interventions (lines 60-62). It flags semaglutide 1 mg vs current 2 mg practice (lines 63-66, 1081-1086).

**Gemini claim.** It uses strong certainty language: "definitively proven" and "significantly reduce[d]" MACE (state/compare_gemini_dr.txt:664-669). It does cite or use some lower-authority sources for SURPASS-4 and CVOT claims, including PR Newswire and media-style CVOT items in works cited (lines 730-735, 806-823), but does not foreground sponsorship/open-label bias or heterogeneity.

**Critical appraisal.** V27 is best on explicit contradiction disclosure, but it reports artifacts rather than adjudicating them clinically. ChatGPT is best on AMSTAR-2/GRADE limitations: sponsor, open-label bias, indirectness, and comparator evolution. Gemini is weakest because it converts uncertainty into conclusory benefit language.

**Winner:** ChatGPT, with V27 close for contradiction disclosure.

## Final aggregate

Topic wins: ChatGPT 4 (A, B, C, F); V27 1 (E); Gemini 1 (D). No ties.

Closest to systematic-review standard: ChatGPT. It most consistently gives PICO elements, study design, endpoints/timepoints, effect estimates with uncertainty, and GRADE-relevant caveats. It is not a full PRISMA/AMSTAR-2 systematic review, but among the three it behaves most like one.

Most clinically useful for a physician: ChatGPT for efficacy/CV/safety decision-making, because it gives the trial numbers a clinician needs at point of care. V27 is best as a regulatory cross-jurisdiction reference. Gemini is useful for mechanism and Canadian safety color, but its cardiovascular overstatement and promotional certainty make it less safe as a clinical summary.
