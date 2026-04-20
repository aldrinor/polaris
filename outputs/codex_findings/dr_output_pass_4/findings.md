---
verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
pass: dr_output_pass_4_tirzepatide_v10
commit: ff68b86
delta_vs_pass3: "M-23/M-24 improved corpus scale and report citation count versus V6, but V10 still failed its own release gate and live citation audit found citation-source mismatches, unverifiable DOI/publisher bodies, and population/scope drift."
citations_verified: "24 live-audited cited claim sentences / 24 citation-bearing claim sentences in report.md; report contains only 16 unique bibliography entries, so >=25 distinct citation checks were not possible without duplication."
citations_faithful: 18
citations_fabricated: 1
citations_embellished: 1
citations_unverifiable: 4
t1_t2_percentage_of_bibliography: "75.0%"
t7_percentage_of_bibliography: "6.25%"
live_fetch_method_used: "mixed: direct WebFetch-equivalent browser open/search source body; DOI/source fallback via live search when direct publisher pages blocked; no metadata-only verdicts counted as faithful"
faithfulness_verdict: "Mostly directionally faithful, but below top-tier because 6/24 audited citation-bearing claims were fabricated, embellished, or unverifiable."
coverage_gaps_remaining: ["Only 16 unique cited sources in bibliography for an 834-word clinical DR report", "No NEJM/Lancet/JAMA primary SURPASS-1/2/3/4/5 papers in final bibliography except secondary/post-hoc summaries", "Obesity-only and type 1 diabetes evidence used in a type 2 diabetes question", "Unpaywall and winner-selection telemetry not exposed in run_log.txt"]
structural_hallucinations: ["Report has correct section headings, but a Safety sentence imports a non-tirzepatide GLP-1/GLP-2 phase I drug as if informative for tirzepatide safety", "A SURMOUNT-1 obesity claim is cited to SURMOUNT-3"]
quantification_quality: "Good numeric density, but some numeric claims are uncited in limitations/methods and at least one cited quantitative sentence is attached to the wrong source."
contradiction_handling: "Not DR-grade: manifest fails PT08; contradiction disclosure dismisses detector output without endpoint/dose/population adjudication and without citations."
vs_gpt54_dr_verdict: "Below GPT-5.4 Deep Research quality."
vs_gemini31_pro_dr_verdict: "Below Gemini 3.1 Pro Deep Research quality."
rationale: |
  V10 is an improvement over V6 in corpus size and citation density, but it is not top-tier DR. The local evaluator gate is abort/release_allowed=false. More importantly, line-by-line live source checking found one fabricated citation-source pairing, one embellished relevance claim, and four citation claims where the cited source body could not be fetched or verified directly. The final bibliography has only 16 unique cited entries and omits several primary SURPASS papers expected in a clinical tirzepatide/T2D report.
---

**Verdict**
MATERIAL-GAPS-FIX-AND-RESWEEP. I read `report.md` line by line, checked `bibliography.json`, and live-fetched or attempted to live-fetch every cited claim sentence in the report. V10 is not release quality.

The strongest immediate reason is simple: `manifest.json` says `status=abort_evaluator_critical`, `release_allowed=false`, with blockers `PT08` and `PT11`; `qwen_judge_output.json` flags `citation_tightness=needs_revision`. The content audit independently confirms that this is not just a metadata failure.

**Quantitative V10 vs V6 Summary**
V10 retrieved 309 sources, fetched 285, selected 277 evidence rows, generated 834 words, verified 24 sentences, and dropped 16 sentences. Final bibliography has 16 unique cited entries: T1=9, T2=3, T4=3, T7=1. T1+T2 among final citations is 75.0%; T7 is 6.25%.

Publisher/source mix in final bibliography: Nature/Springer Nature=3, NCBI/PMC/PubMed=6, Frontiers=1, Springer=1, Taylor & Francis=1, Diabetesjournals=1, AHA DOI abstract=1, URNCST DOI=1, Elsevier DOI=1. NEJM=0, Lancet=0, JAMA primary URL=0, FDA=0. Named SURPASS/SURMOUNT papers are present, but key primary SURPASS-1/2/3/4/5 papers are often absent or replaced by secondary summaries/post-hoc sources.

**Citation Live-Fetch Audit Table**
The report contains 24 citation-bearing claim sentences, not 25. I audited all 24. I did not invent an extra citation check.

| # | Report sentence quote | Cited source actually fetched/attempted | Source-body excerpt/check | Verdict |
|---:|---|---|---|---|
| 1 | "Across the SURPASS program...81% to 97%...66% to 95%...23% to 62%..." [1] | https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/ via live search body; direct open hit reCAPTCHA | Source table/body reports the same A1c target ranges across SURPASS: <7.0%, <=6.5%, and <5.7%. | FAITHFUL |
| 2 | "In that trial...75.4%, 86.0%, and 84.4%...versus 23.7%..." [2] | https://www.nature.com/articles/s41591-023-02344-1 | Nature abstract reports 75.4%, 86.0%, 84.4% vs 23.7% for HbA1c <7.0%. | FAITHFUL |
| 3 | "Tirzepatide also produced significant, dose-dependent weight loss..." [1] | https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/ via live search body; direct open blocked | Source reports dose-dependent A1c/body-weight reductions and weight loss ranging roughly -6.6% to -13.9%. | FAITHFUL |
| 4 | "A systematic review notes...HbA1c (up to 2.4%) and body weight (up to 22%)..." [3] | https://doi.org/10.26685/urncst.1029 attempted; no source body obtained | Could not fetch DOI body or OA body with the available web tool. | UNVERIFIABLE |
| 5 | "Beyond glycemic and weight control...fasting serum glucose...blood pressure...triglycerides..." [1] | https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/ via live search body; direct open blocked | Source body describes SURPASS improvements in glycemic, weight, lipid, and cardiometabolic parameters. | FAITHFUL |
| 6 | "IPD meta-analysis...MACE...hazard ratio 0.67 (95% CI, 0.51-0.87)." [4] | https://doi.org/10.1161/circ.152.suppl_3.4361308 attempted; secondary live page found | A secondary MIMS article repeats HR 0.67 and CI 0.51-0.87, but the cited AHA abstract body was not fetched. | UNVERIFIABLE |
| 7 | "The most frequent adverse events...nausea, diarrhea, and vomiting..." [5] | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11088184 attempted; direct source body not obtained | Direct cited PMC body was blocked/not returned; related sources support the general claim, but not the cited source body. | UNVERIFIABLE |
| 8 | "SURPASS Phase 3...nausea 20-33%, diarrhea 18-22%, vomiting 8-13%." [5] | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11088184 attempted; direct source body not obtained | Could not verify these exact ranges in the cited source body. | UNVERIFIABLE |
| 9 | "Systematic review/meta-analysis...GI effects are the most common adverse events." [6] | https://www.mdpi.com/1424-8247/18/5/668 | Source reports GI adverse events including nausea/vomiting/diarrhea more prevalent with tirzepatide. | FAITHFUL |
| 10 | "Type 1 diabetes and obesity...side effects 26%, nausea 15%, discontinued 4%." [7] | https://www.citedrive.com/en/discovery/1660-p-efficacy-and-safety-of-tirzepatide-for-the-treatment-of-obesity-in-adults-with-type-1-diabetesthe-mayo-clinic-experience/ | Abstract text gives side effects 26%, nausea 15%, discontinuation 4%, no severe hypoglycemia/DKA. | FAITHFUL |
| 11 | "SURMOUNT-1...90% late responders...>=5% by week 72..." [8] | https://pubmed.ncbi.nlm.nih.gov/40677091/ and https://www.ovid.com/journals/domet/fulltext/10.1111/dom.16554~weight-reduction-over-time-in-tirzepatidetreated | Source reports 250/278 late responders, 90%, achieved >=5% body-weight reduction at week 72. | FAITHFUL |
| 12 | "Serious adverse events appear uncommon; in a Phase I trial of a bispecific GLP-1/GLP-2 agonist..." [9] | https://www.nature.com/articles/s41467-026-71080-0 | Source says PG-102 had no serious AEs/discontinuations and GI events mild/moderate. It is not tirzepatide. | EMBELLISHED |
| 13 | "Type 1 diabetes...no severe hypoglycemia or DKA..." [7] | Same fetched Citedrive/Diabetes abstract as #10 | Abstract states no severe hypoglycemia or DKA were recorded. | FAITHFUL |
| 14 | "SURPASS-4...104 weeks...HbA1c -2.3/-2.5/-2.6 vs -1.0; weight -7.6/-10.0/-11.4 vs +2.1 kg." [10] | https://www.researchgate.net/publication/395390302_Long-term_efficacy... and PubMed attempted | Source abstract reports exactly those 104-week HbA1c and body-weight values. | FAITHFUL |
| 15 | "Meta-analysis of six RCTs...reduced body weight more than semaglutide 1 mg and dulaglutide 1.5 mg..." [11] | https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full | Source reports six RCTs and superior weight loss without increased hypoglycemia. | FAITHFUL |
| 16 | "Head-to-head SURPASS-2...superior HbA1c and weight reductions vs semaglutide 1 mg..." [12] | https://link.springer.com/content/pdf/10.1007/s13300-023-01470-w.pdf | Source PDF discusses SURPASS-2 target achievement/costs using tirzepatide vs semaglutide 1 mg trial data. | FAITHFUL |
| 17 | "Model-based simulation...HbA1c 1.95% to 2.46%; weight 6.50 to 12.1 kg by week 66." [13] | https://www.tandfonline.com/doi/full/10.1080/03007995.2024.2322072 | Source abstract gives the same predicted HbA1c and body-weight ranges by week 66. | FAITHFUL |
| 18 | "SURMOUNT-4...additional 5.5% reduction...placebo 14.0% regain..." [14] | https://jamanetwork.com/journals/jama/fullarticle/2812936 and PMC live search body | Source reports -5.5% with continued tirzepatide vs +14.0% with placebo from week 36 to 88. | FAITHFUL |
| 19 | "By week 88, 69.5%...>=20%...vs 12.6%..." [14] | Same JAMA/SURMOUNT-4 source as #18 | Source table reports >=20% body-weight reduction: 69.5% vs 12.6%. | FAITHFUL |
| 20 | "SURMOUNT-1...tirzepatide 15 mg...20.9% at 72 weeks versus 3.1% placebo." [15] | https://www.nature.com/articles/s41591-023-02597-w | Cited source is SURMOUNT-3, not SURMOUNT-1; it reports MTD -18.4% vs +2.5% from randomization. | FABRICATED |
| 21 | "Meta-analysis...did not increase hypoglycemia compared to semaglutide 1 mg." [11] | https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full | Source conclusion reports no increased hypoglycemia; comparator-specific claim is consistent with source discussion. | FAITHFUL |
| 22 | "GI adverse events...more common with tirzepatide than placebo...mild to moderate." [14] | https://jamanetwork.com/journals/jama/fullarticle/2812936 and PMC live search body | SURMOUNT-4 source says common AEs were mostly mild/moderate GI events, more common with tirzepatide. | FAITHFUL |
| 23 | "SURMOUNT-4 discontinuation due to AE...1.8% tirzepatide and 0.9% placebo." [14] | Same JAMA/SURMOUNT-4 source as #18 | Source safety table reports double-blind discontinuation due to AE at 1.8% vs 0.9%. | FAITHFUL |
| 24 | "Macronutrient malnutrition...uncommon, occurring in 0.12%..." [16] | https://pmc.ncbi.nlm.nih.gov/articles/PMC12865613/ and https://www.sciencedirect.com/science/article/pii/S2667368126000045 | Source reports 4/3141, 0.12%, tirzepatide-treated participants with TEAEs potentially related to macronutrient malnutrition. | FAITHFUL |

**Criterion-by-criterion**
a. Argumentation: Partly integrated, but still summary-like. The report lists trial results without building a hierarchy of evidence or explaining why secondary/post-hoc sources substitute for primary trials.

b. Quantification: Better than V6; many numbers are precise. However, PT11 found uncited numeric claims, and the live audit found one wrong-source numeric citation.

c. Scope fidelity: Not adequate. Type 1 diabetes evidence and obesity-without-diabetes evidence are used in a T2D answer. Some are flagged, but the safety section lets T1D evidence and a non-tirzepatide phase I drug influence the safety narrative.

d. Contradictions: Not adequate. `contradictions.json` has 14 high-severity numeric disagreements, and `manifest.json` fails PT08. The disclosure says most are extraction artifacts but does not adjudicate them by endpoint, dose, population, comparator, or tier.

e. Structural hallucinations: Headings match the clinical template, but content inside headings has structural drift: a non-tirzepatide GLP-1/GLP-2 agonist appears in tirzepatide safety, and SURMOUNT-1 is cited to a SURMOUNT-3 paper.

f. Citation tightness: Fails. Four audited claims were unverifiable from cited source body; one was fabricated relative to cited source; one was embellished.

g. Coverage: Not top-tier. Final bibliography has 16 entries, far below the 50-200 citation density expected for a top-tier clinical DR report, and misses key primary papers from NEJM/Lancet/JAMA.

h. Release readiness: Not release-ready. The pipeline itself marks abort/release_allowed=false.

**M-23 + M-24 Impact Assessment**
Unpaywall hit rate: not assessable from `run_log.txt`. The log reports `fetched=285, failed=24`, but does not expose Unpaywall hit/miss counts or DOI-to-OA swaps.

Crawl4AI/content winner selection: not assessable from `run_log.txt`. The log does not include M-23c quality-score winner telemetry or source-length comparisons.

Citation count: improved versus V6, but only to 16 unique final bibliography entries and 24 verified claim sentences. That is still not Deep Research grade.

T1/T2 fraction: final cited bibliography has a strong T1/T2 fraction (75.0%), but the full corpus still has material deviation: T1=20%, T2=14%, T4=38%, T7=22%. Final citation quality is also weakened by secondary summaries classified as T1 and missing primary SURPASS papers.

**Remaining DR Gaps**
1. Own-gate failure remains: `release_allowed=false`, `status=abort_evaluator_critical`.
2. Citation audit pass rate is 18/24 faithful = 75%, below the >95% required for top-tier DR.
3. The report has too few cited sources and too few citation-bearing sentences for a high-stakes clinical research answer.
4. Primary evidence coverage is incomplete: NEJM/Lancet/JAMA SURPASS primaries should be directly cited.
5. Contradiction handling is conclusory, not adjudicated.
6. Scope contamination remains from T1D, obesity-only, and non-tirzepatide evidence.
7. Run telemetry does not prove M-23 worked: no Unpaywall hit rate, no legal OA PDF substitution summary, no winner-selection quality logs.

**Required Fix**
Fix and resweep. Required changes before another final-judge pass:

1. Force primary-paper coverage for SURPASS-1 through SURPASS-5, SURPASS-AP-Combo, SURMOUNT-2 if discussing T2D weight loss, and SURMOUNT-4/3/1 only when explicitly labeled as obesity-without-diabetes or mixed population.
2. Require citation adjacency for every numeric claim in limitations, methods, and contradiction disclosures.
3. Reject source bindings where the cited source title/trial does not match the sentence trial name.
4. Add population-scope gating: T1D, obesity-only, preclinical, and non-tirzepatide drug evidence must be quarantined unless the sentence explicitly says why it is indirect.
5. Emit M-23 telemetry into `run_log.txt`: DOI count, Unpaywall queried count, OA PDF hit count, OA substitution count, paywall/stub rejects, winner backend, content length, and quality score.
6. Replace contradiction prose with a table grouped by endpoint, dose, population, comparator, timepoint, and tier, or suppress artifact groups with explicit machine-readable reasons.
