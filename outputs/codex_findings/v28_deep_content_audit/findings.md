# V28 Deep Content Audit: Tirzepatide/T2D

Audit lens: clinical document review under PRISMA 2020, AMSTAR-2, GRADE, and clinical-epidemiology judgment. This is a content audit, not the M-49 metadata preservation audit.

## A. SURPASS-2: tirzepatide vs semaglutide 1 mg

**V28 says.** "In the head-to-head SURPASS-2 trial (N=1879, baseline HbA1c 7.0-10.5%), once-weekly tirzepatide at 5, 10, and 15 mg demonstrated superior reductions in HbA1c and body weight at 40 weeks compared to once-weekly semaglutide 1 mg.[20]" (outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm/report.md:13). V28 also says SURPASS-2 randomized N=1879 on metformin to tirzepatide 5/10/15 mg vs semaglutide 1 mg for 40 weeks (report.md:17), but [20] is "a post hoc analysis of the SURPASS-2 Trial" and tier T4 (report.md:112), not the Frías NEJM primary publication.

**ChatGPT says.** Its trial table gives "SURPASS-2" as a "40-week, open-label, randomized active-comparator trial" (state/compare_chatgpt_dr.txt:161-168), N=1,879 with mean HbA1c 8.28% and weight 93.7 kg (lines 169-177), tirzepatide 5/10/15 mg vs semaglutide 1 mg weekly (lines 178-183), and the primary endpoint at week 40 (lines 184-188). It reports HbA1c ETDs vs semaglutide of -0.15, -0.39, and -0.45 with CIs/P values (lines 189-198), and weight ETDs -1.9, -3.6, and -5.5 kg (lines 199-202).

**Gemini says.** "SURPASS-2 ... evaluat[ed] ... tirzepatide (5 mg, 10 mg, and 15 mg) against once-weekly injectable semaglutide 1 mg" (state/compare_gemini_dr.txt:110-114). It says 15 mg achieved HbA1c reduction of 2.46% from baseline 8.28%, 92.2% reaching HbA1c <7.0%, and 12.4 kg weight loss vs 6.2 kg with semaglutide (lines 117-127). It also gives 5 mg HbA1c reduction 2.09% and weight reduction 7.8 kg (lines 128-130).

**Critical appraisal.** V28 improved over V27 by naming the direct comparator, N, baseline HbA1c range, doses, and 40-week timepoint, but it still does not report the primary effect estimates requested for this topic: HbA1c ETDs -0.15/-0.39/-0.45% and weight ETDs -1.9/-3.6/-5.5 kg. It also cites a 2025 post-hoc article for the primary trial frame. ChatGPT is closest to systematic-review standard because it gives PICO, open-label design, endpoint/timepoint, effect estimate, uncertainty, and safety signals. Gemini is numerically useful but rhetorically inflated and lacks uncertainty.

**Winner: ChatGPT.**

## B. SURPASS-CVOT: MACE-3 vs dulaglutide

**V28 says.** No substantive SURPASS-CVOT claim appears in the report body or bibliography. The only MACE body sentence is generic: "Rates of serious adverse events such as adjudicated pancreatitis and major adverse cardiovascular events (MACE) were low in clinical trials" (report.md:9). The live corpus contains SURPASS-CVOT records, including design/baseline and news/topline items (live_corpus_dump.json:1741, 3163, 3185, 3240, 4659), but they were not selected into the report.

**ChatGPT says.** ChatGPT gives the trial frame: cardiovascular outcomes trial in adults with T2D and established ASCVD (state/compare_chatgpt_dr.txt:525-533), N=13,299 (line 534), tirzepatide up to 15 mg vs dulaglutide 1.5 mg (lines 538-542), time to first 3-point MACE over median about 4 years (lines 543-549), primary event 12.2% vs 13.1%, HR 0.92 (95% CI 0.83-1.01), P=0.003 for noninferiority and P=0.09 for superiority (lines 550-557). It correctly interprets this as not proving superiority (lines 952-959).

**Gemini says.** Gemini says SURPASS-CVOT was published in late 2025, randomized 13,299 patients with T2D and ASCVD to tirzepatide or dulaglutide (state/compare_gemini_dr.txt:419-425), and reports MACE-3 12.2% vs 13.1%, HR 0.92, 95.3% CI 0.83-1.01, P=0.003 for noninferiority, P=0.09 superiority trend (lines 428-433). It then overinterprets noninferiority as validating robust vascular benefit and cites numerical submetrics (lines 434-441), and later claims CVOT "definitively proven" cardiovascular/renal protection and "significantly reduce[d]" MACE (lines 664-669).

**Critical appraisal.** V28 fails the topic: no PICO, N, comparator, endpoint, HR, CI, noninferiority/superiority distinction, or primary Nicholls citation. ChatGPT and Gemini both have the numeric frame, but ChatGPT applies the correct clinical interpretation: active-comparator noninferiority versus dulaglutide is reassuring cardiovascular safety, not proven superiority. Gemini's later language is a material GRADE/clinical-epidemiology error.

**Winner: ChatGPT.**

## C. SURPASS-4: high-CV-risk T2D vs insulin glargine

**V28 says.** No substantive SURPASS-4 body claim appears. V28 discusses SURPASS-3 vs insulin degludec (report.md:5, 49) and SURPASS-5/6 in basal-insulin contexts (report.md:9, 53), but the report does not mention SURPASS-4 in the body, table, or bibliography. The live corpus did contain the Del Prato primary publication (live_corpus_dump.json:2478), but the selected bibliography omitted it.

**ChatGPT says.** ChatGPT describes SURPASS-4 as a "52-week, open-label, randomized active-comparator trial in high cardiovascular-risk patients on oral agents; extension to 104 weeks" (state/compare_chatgpt_dr.txt:309-320), N=1,995 with 87% history of cardiovascular disease (lines 321-334), tirzepatide 5/10/15 mg vs insulin glargine (lines 335-338), endpoint at week 52 (lines 339-343), HbA1c ETDs -0.80/-0.99/-1.14 with CIs, all P<0.0001 (lines 344-352), weight ETDs -9.0/-11.4/-13.5 kg (lines 353-356), and 104-week HbA1c/weight durability (lines 357-364). It also reports nausea, diarrhea, discontinuation, and MACE-4 HR 0.74 (lines 365-376).

**Gemini says.** Gemini says SURPASS-4 evaluated tirzepatide against titrated daily insulin glargine in participants with T2D and increased cardiovascular risk (state/compare_gemini_dr.txt:176-178). It reports tirzepatide 15 mg HbA1c reduction 2.58%, body-weight reduction 11.7 kg from baseline 90.3 kg, glargine HbA1c reduction 1.44% and 1.9 kg weight gain (lines 179-186), plus 84.9% vs 48.8% reaching HbA1c <7.0% (lines 186-187). It frames the finding as without glargine's hypoglycemic liabilities (lines 188-190).

**Critical appraisal.** V28 regressed relative to the stated M-44/M-50 target: SURPASS-4 is absent despite corpus availability. ChatGPT is strongest: it gives the PICO, high-CV-risk enrichment, open-label design, 52-week primary endpoint, effect estimates with uncertainty, safety caveats, and 104-week durability. Gemini is useful but thinner, with no uncertainty and more rhetorical clinical conclusion.

**Winner: ChatGPT.**

## D. Mechanism: dual GIP/GLP-1 agonism and clamp data

**V28 says.** V28 says dual agonism harnesses complementary incretin actions, GIP potentiates glucose-dependent insulin secretion, and the PK profile has a half-life of about 5 days and bioavailability around 80% (report.md:21). It also says tirzepatide is 99% albumin-bound and metabolized by proteolytic cleavage and beta-oxidation of the fatty diacid side chain (report.md:21). It does not mention the Thomas Lancet Diabetes & Endocrinology clamp paper, M-value 63%, biphasic insulin secretion, 39-aa peptide/C20 fatty diacid, receptor-affinity asymmetry, or any [ev_X] evidence IDs in the mechanism text.

**ChatGPT says.** No dedicated mechanism/clamp passage was found for the key audit terms in ChatGPT: 39-amino, C20, half-life, M-value, biphasic, insulin sensitivity, or first-phase secretion. Its relevant methodological caveat is about trial architecture rather than receptor biology: pivotal SURPASS studies were sponsored by Eli Lilly and mixed double-blind placebo-controlled and open-label active-comparator trials (state/compare_chatgpt_dr.txt:50-66).

**Gemini says.** Gemini gives the structural and pharmacologic frame: tirzepatide is a synthetic "39-amino acid peptide" (state/compare_gemini_dr.txt:39-42), has a "C20 fatty diacid moiety" (lines 42-44), and has a mean half-life of approximately five days (lines 44-46). It describes "imbalanced" dual agonism, with native-like GIP affinity and weaker GLP-1 affinity (lines 47-53). It reports clamp findings: tirzepatide 15 mg increased whole-body insulin sensitivity by 63% by M-value (lines 54-58) and hyperglycemic clamp studies enhanced first- and second-phase insulin secretion (lines 60-63).

**Critical appraisal.** V28 remains below the M-47 target. It has generic mechanism and PK statements, mostly from reviews/StatPearls-style sources, not primary human clamp extraction. It gives only one of the requested key findings, half-life, and misses the central quantitative mechanistic evidence. Gemini is the clear winner for clinical mechanistic content, although it sometimes overstates mechanistic certainty ("clinically vital") without direct uncertainty.

**Winner: Gemini.**

## E. Regulatory coverage: FDA / EMA / NICE / Health Canada

**V28 says.** V28 covers FDA diabetes/weight-management indications, dosing, boxed warning, contraindications, and warnings (report.md:25). It covers EMA authorization date, T2D indication including adults/adolescents/children aged 10 years and above, weight-management indication, additional monitoring, and OSA indication (report.md:25). It covers Health Canada authorization date, T2D indication, combinations, and thyroid warning box (report.md:25). It covers NICE TA924-style T2D criteria, including triple-therapy failure/intolerance/contraindication, BMI >=35 with obesity-related problems, BMI <35 occupational/complication exceptions, lower BMI thresholds for some ethnic backgrounds, and commercial arrangement (report.md:25). Bibliography includes FDA labels/reviews, EMA EPAR/product information, Health Canada Product Monograph, and NICE guidance (report.md:127-138).

**ChatGPT says.** ChatGPT covers U.S. and EMA dosing and warning differences (state/compare_chatgpt_dr.txt:967-982), including U.S. MTC/MEN2/hypersensitivity contraindications and warnings for pancreatitis, hypoglycemia, hypersensitivity, kidney injury, severe GI reactions, retinopathy, gallbladder disease, and pulmonary aspiration (lines 974-979). It lacks NICE and Health Canada specificity in the cited passage.

**Gemini says.** Gemini covers FDA/Health Canada hypoglycemia dose-reduction guidance (state/compare_gemini_dr.txt:529-532), FDA boxed warning and Health Canada serious warning for thyroid C-cell tumors (lines 533-541), pulmonary aspiration safety review (lines 580-603), KwikPen sharing/visual-impairment warnings (lines 608-625), and Health Canada counterfeit/unauthorized product warnings (lines 626-643). But it says the Mounjaro formulation carries "FDA label allowances for pediatric patients 10 years of age and older" (lines 567-572), which conflicts with the audit target that the pediatric >=10 indication is EMA-specific. Gemini also lacks NICE and EMA breadth.

**Critical appraisal.** V28 is the most jurisdiction-complete and best preserves the V27 regulatory win. It misses the requested Health Canada/KwikPen/counterfeit advisory depth that Gemini has, but Gemini's pediatric-label claim is a serious jurisdictional conflation and it omits NICE/EMA breadth. ChatGPT is accurate but too narrow. V28 is therefore the best clinical regulatory reference among the three, though not perfect.

**Winner: V28.**

## F. Contradictions and uncertainty

**V28 says.** V28 states the corpus is weighted toward lower-tier sources, with T1 only 15% and T4 narrative reviews 31%, and says the pipeline detected 14 high-severity contradictions, especially for body weight/weight loss magnitudes (report.md:57). It enumerates 14 numeric-disagreement flags, including dose-specific weight/body-weight ranges across tiers (report.md:72-87). It explains many flags are extraction artifacts from grouping different endpoints, doses, populations, comparators, timepoints, and tiers (report.md:72). It also includes some sponsor/open-label disclosure in per-trial summaries: SURPASS-1 funded by Eli Lilly (report.md:45), SURPASS-3 open-label and sponsored by Eli Lilly (report.md:49), and SURPASS-5 has no safety caveat specified (report.md:53). It does not clearly explain semaglutide 1 mg vs current semaglutide 2 mg as an indirectness/comparator-evolution caveat, despite citing an indirect semaglutide 2 mg comparison (report.md:17).

**ChatGPT says.** ChatGPT explicitly states all pivotal SURPASS studies were sponsored by Eli Lilly (state/compare_chatgpt_dr.txt:50-54). It says the program mixes double-blind placebo-controlled and open-label active-comparator trials and explains open-label bias for symptom reporting, discontinuation, and behavioral co-interventions while HbA1c is objective (lines 60-62). It flags comparator evolution: SURPASS-2 used semaglutide 1 mg, while semaglutide 2 mg is now used in practice, so some modern comparisons rely on indirect evidence (lines 63-66, 1081-1086). It also correctly says SURPASS-CVOT supports noninferiority rather than clear superiority (lines 1055-1064).

**Gemini says.** Gemini uses strong certainty language. It states SURPASS-CVOT "definitively proven" that metabolic corrections translate into cardiovascular and renal protection and that tirzepatide "significantly reduce[d]" MACE and outperformed active cardioprotective comparators (state/compare_gemini_dr.txt:664-669). This conflicts with the HR 0.92, CI crossing 1.0, and P=0.09 superiority result it reported earlier (lines 428-433).

**Critical appraisal.** V28 is best on explicit contradiction enumeration and corpus-tier transparency. ChatGPT is best on clinical uncertainty: sponsorship, open-label bias, comparator evolution, indirectness, and CVOT interpretation. Because this topic requires both numeric heterogeneity enumeration and clinical uncertainty, this is a split. Gemini is clearly worst because it converts noninferiority/trends into definitive benefit language.

**Winner: Tie (ChatGPT / V28).**

## Additional V28 checks

**1. M-42b Trial Summary table.** Present but fails. It has only 2 rows (SURPASS-5 and SURMOUNT-4), below the >=6-row target (report.md:27-32). Cells are badly populated: SURPASS-5 has N=586 while the per-trial summary says 475 (report.md:31, 53), baseline "7.0%" appears to be an endpoint target rather than baseline HbA1c, endpoint is blank, and result "10.5%" is uninterpretable (report.md:31). SURMOUNT-4 has no baseline and no endpoint (report.md:32). Both rows cite bibliography markers, but the table is not a usable trial-summary artifact.

**2. M-50 Per-Trial Summaries block.** Present and has 3 subsections: SURPASS-1, SURPASS-3, SURPASS-5 (report.md:41-53). SURPASS-1 and SURPASS-3 cover N, population, comparator, endpoint, timepoint, effect, and sponsor/open-label or safety caveat (report.md:45, 49). SURPASS-5 covers N, population, comparator, endpoint, timepoint, effect with uncertainty, but explicitly says "The quote does not specify a key safety caveat" (report.md:53), so it fails the 7-element requirement. The block includes only T2D-direct trials, which is good, but it omits the most clinically important direct-comparator trials requested here: SURPASS-2, SURPASS-4, and SURPASS-CVOT.

**3. M-47 Mechanism extraction.** Fails. The mechanism section contains no [ev_X] same-sentence evidence IDs and lacks >=3 inline quantitative findings from the Thomas clamp paper. The only quantitative mechanism-adjacent values are half-life approximately 5 days, bioavailability around 80%, and albumin binding 99% (report.md:21), none tied to [ev_X] in the same sentence and none addressing the M-value/insulin secretion clamp target.

**4. M-44 primary-trial coverage.** Fails. Primary publications cited in the final report/bibliography include SURPASS-1 [1], SURPASS-3 [2]/[3], SURPASS-3 CGM [4], SURMOUNT-4 [11], SURPASS-5 [17], and SURPASS-6 [18] (report.md:93-110). SURPASS-2 is cited through a 2025 post-hoc T4 article [20], not the Frías NEJM primary (report.md:112). SURPASS-4 primary is in live corpus but not selected (live_corpus_dump.json:2478). SURPASS-CVOT is in corpus but not selected (live_corpus_dump.json:1741, 3163, 3185). SURMOUNT-2 is in corpus but not selected (live_corpus_dump.json:1366). SURMOUNT-1/3 are not in the final bibliography. Depending on whether SURPASS-3 CGM is counted separately, V28 reaches about 5-6 primary trial publications, not >=7 of 11 pivotal trials. Trial-name mentions often lack same/adjacent-sentence primary [N] citations; SURPASS-2 mentions cite [20] post-hoc, and SURPASS-4/CVOT are absent.

**5. M-48 SURMOUNT population-scope discipline.** Mostly passes for the final report's limited SURMOUNT use. SURMOUNT-4 is explicitly framed as "adults with obesity or overweight without diabetes" in the safety section (report.md:9), so it is not merged into T2D efficacy. The Trial Summary table includes SURMOUNT-4 without a population-scope label (report.md:32), which is weaker, but it is not used to support T2D glycemic efficacy. SURMOUNT-1 and SURMOUNT-3 are not cited in the report body.

## Final aggregate

Topic wins:

| Topic | Winner |
|---|---|
| A. SURPASS-2 | ChatGPT |
| B. SURPASS-CVOT | ChatGPT |
| C. SURPASS-4 | ChatGPT |
| D. Mechanism | Gemini |
| E. Regulatory | V28 |
| F. Contradictions/uncertainty | Tie: ChatGPT / V28 |

Counting the tie as 0.5 each: ChatGPT 3.5, V28 1.5, Gemini 1. If ties are counted as full topic credit: ChatGPT 4, V28 2, Gemini 1.

## Closest-to-systematic-review-standard

**ChatGPT.** It most consistently supplies PICO, study design, endpoint/timepoint, effect estimate with uncertainty, comparator caveats, sponsorship/open-label limitations, and correct CVOT noninferiority interpretation. V28 is more transparent about corpus contradictions and has broader jurisdictional coverage, but it fails multiple primary-trial extraction targets and its structural additions are incomplete. Gemini is strongest on mechanism but too often uses promotional or over-certain clinical language.

## Clinical usefulness verdict

| Physician question | Best report | Reason |
|---|---|---|
| "How much better is tirzepatide than semaglutide 1 mg for HbA1c and weight in SURPASS-2?" | ChatGPT | Gives ETDs, CIs, P values, timepoint, open-label design, and safety signals. |
| "Does tirzepatide improve cardiovascular outcomes versus dulaglutide?" | ChatGPT | Gives CVOT HR/CI/P values and correctly frames noninferiority without claiming superiority. |
| "What happened in high-CV-risk patients versus insulin glargine and did effects persist?" | ChatGPT | Gives SURPASS-4 52-week ETDs and 104-week durability. |
| "What is the biological mechanism and human clamp evidence?" | Gemini | Gives 39-aa/C20/half-life/imbalanced agonism and M-value/insulin-secretion clamp findings. |
| "What can I prescribe under FDA/EMA/NICE/Health Canada rules?" | V28 | Broadest four-jurisdiction coverage, including NICE TA924 and EMA pediatric >=10 indication. |
| "What should I worry about in evidence certainty?" | ChatGPT for clinical caveats; V28 for pipeline contradiction flags | ChatGPT is better for GRADE-style limitations; V28 is better for numeric heterogeneity enumeration. |

## Autoloop stop-criterion table

The V28 target projection was 5 BEAT_BOTH + 2 BEAT_ONE + 0 LOSE_BOTH. This deep content audit does not support that projection.

| Dimension | V28 vs ChatGPT/Gemini | Rationale |
|---|---|---|
| 1. Citations | LOSE_BOTH | SURPASS-2 uses post-hoc [20]; SURPASS-4/CVOT primaries omitted; mechanism primary not mined. |
| 2. Regulatory | BEAT_BOTH | Best all-jurisdiction coverage despite missing HC KwikPen/counterfeit detail. |
| 3. Jurisdictional | BEAT_BOTH | FDA/EMA/NICE/HC all represented with jurisdiction-specific distinctions. |
| 4. Claim frames | LOSE_BOTH | Fails primary ETDs for SURPASS-2, omits SURPASS-CVOT and SURPASS-4, and table cells are malformed. |
| 5. Structural depth | LOSE_BOTH | Trial Summary has only 2 weak rows; per-trial summaries omit key trials and one admits no safety caveat. |
| 6. Contradiction handling | BEAT_BOTH | Preserves explicit 14-item contradiction enumeration and corpus-tier limitation disclosure. |
| 7. Narrative depth | LOSE_BOTH | Mechanism remains generic and far below Gemini; trial narrative is less clinically extracted than ChatGPT. |

Adjudicated V28 aggregate on 7 dimensions: **3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH**.

**Shippable verdict: NOT SHIPPABLE.** V28 does not meet the unchanged stop criterion of 7/7 BEAT_BOTH.
