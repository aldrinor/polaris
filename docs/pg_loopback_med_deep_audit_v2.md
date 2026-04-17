# Deep Content Audit — PG_LOOPBACK_MED (v2)

This audit supersedes the earlier 6-gate table. That table was metadata theatre — it measured string presence, not content truth. This one reads the artifacts line by line, traces every assertion back to its fetched source, and applies PRISMA 2020, AMSTAR-2, and Cochrane-handbook criteria.

## Headline

**The 14-source, 2,549-word document titled a "systematic review" is not a systematic review. It is a narrative literature overview assembled from predominantly secondary sources (umbrella reviews, patient-education pages, a newsroom PR release, a university news post), with the three most consequential risk findings for the research question dropped during pipeline filtering despite being available in upstream evidence.**

Specifically, three atomic facts that should dominate a benefits-AND-risks review on intermittent fasting are absent from the final document:

1. **The Lin/Zhong 2024 NHANES signal of 91% higher cardiovascular mortality with under-8-hour eating windows.** Extensively surfaced during PageSummary/STORM phases (AHA newsroom PR, JAMA Network summary, Disease-a-Month scoping review), the finding never became an atomic fact in the SourceAnalysisBatch pool, so the synthesizer had nothing to cite. No variant of the number 91% or the author Zhong appears in the final report.
2. **The Mass General Brigham contraindication list** (over 65, still-growing adolescents, diabetes, heart/kidney/liver disease, eating-disorder history, pregnant/breastfeeding, low blood pressure, blood thinners/diuretics/BP/glucose medications). This WAS extracted as an atomic fact during SourceAnalysisBatch req_080afdea6512. The pipeline's post-analyze filter (off-topic, tier, pre-verification gate) discarded it. Only one MGB atomic fact survived — the "10-12 hour metabolic switch" — which is not a risk fact. The contraindications are invisible in the final report.
3. **Adolescent disordered-eating risk** (Helmholtz Munich warning, Kumar 2025 PMID 40936230, Albosta BMC Clinical Diabetes review). Discussed at length in STORM Public_Health round 2, never atomic-extracted from any source. Only the orthogonal Ramadan-DE study (n=28 vs 74) survived into evidence, with no accompanying adolescent framing.

The second-order finding is equally critical: **the operator for every LLM call in this run was the agent itself**. All 88 LLM calls were served from the agent's prior knowledge of the IF literature. Where this session's audit asked "is the quote a verbatim substring of the fetched content", the answer is yes for all 37 evidence pieces — the agent did not invent quotes. But "did not invent quotes" is a far weaker claim than "the pipeline processed real LLM outputs". This run validates pipeline plumbing, not content quality. The "$0.18 cost, 84 LLM calls" metric in the dashboard is misleading: 84 operator responses were synthesized by a human-equivalent generator with full topic knowledge. A paid GLM-5.1 run against the same prompts and sources could produce materially worse atomic_facts, worse verification verdicts, worse GRADE ratings, and worse rewrite decisions — because GLM-5.1 does not have the same domain priors the agent-operator used.

---

## Layer 0 — Provenance map

88 requests from this run, at `loopback/done/req_*.json` filtered by timestamp window 2026-04-16 19:37–20:37. Bucketed by call_type / schema:

| Count | call_type / schema | Notes |
|-------|--------------------|-------|
| 21 | generate / None | 7 section writes + 6 section rewrites + 2 abstract (write+rewrite) + 3 diagrams + 3 diagram refinements |
| 16 | reason / None | 8 GRADE batches (auto-served by `loopback_auto_grade.py`) + 1 study-extraction + remainder deepener queries |
| 11 | SourceAnalysisBatch | 11 batches covering ~23 source URLs, producing ~55 atomic_facts of which 37 survived filtering |
| 10 | StormQuestion | 5 personas × 2 rounds |
| 10 | StormAnswer | same 5 × 2 rounds; answers not evidence-extracted |
| 7 | VerificationBatch | auto-served by `loopback_auto_verify.py` via substring match |
| 5 | PageSummaryBatch | 11 URLs summarized during agentic search |
| 4 | AgenticRoundAnalysis | agentic-loop convergence decisions |
| 1 each | DiagramAnalysisResult, SeedQueryPlan, StormOutlinePlan, StormPersonaBatch | |

Every response was written by the agent. No OpenRouter/GLM-5.1 call occurred; `$0.18` in the final dashboard is an artifact of the token counters being fed operator-supplied token counts.

---

## Layer 1 — Operator contamination (quote-level)

**Verdict: at the direct_quote level, no operator fabrication.** For each of the 37 atomic_facts that survived into the final evidence pool, the `direct_quote` is a verbatim substring of the fetched `CONTENT` block in the corresponding SourceAnalysisBatch request. Script `scripts/audit_layer1_contamination.py` enumerates each pair; its output lives in `audit_layer1.txt`. Every line reads `VERBATIM`.

**But the bar must be set higher than quote verbatimness.** The operator wrote `statement` fields that paraphrase the quote, and the statement is what the synthesizer reads first. For example:

- ev_4b639367ef09852f, source AJCN Horne 2015: quote "Whereas the few randomized controlled trials and observational clinical outcomes studies support the existence of a health benefit from fasting, substantial further research in humans is needed before…" Statement: "Authors conclude that although few RCTs and observational studies support a health benefit from fasting, substantial further research in humans is needed before fasting can be recommended as a health intervention." — NOTE level: "Authors conclude" is operator-added attribution; the source text does not use that framing phrase. Not wrong, but statement is not a direct paraphrase of the quote, it's the operator's summary.
- ev_d8ed2b1cf17df9e2, source pik-potsdam.de Bangladesh Ramadan: statement says "A community-based survey of 852 young women was conducted in rural Sylhet division, Bangladesh, to describe Ramadan fasting practices and beliefs." — the quote says "described" not "to describe"; minor tense drift. NOTE.
- ev from MDPI Osman: statement "Ramadan fasting shows limited body-composition benefits via reductions in body mass in both healthy and obese individuals, with results often transient and heterogeneous" — verbatim. No drift.

At the quote level this run is clean. At the statement level, operator paraphrases are present but are generally conservative and do not add unsupported claims.

**Boilerplate-source handling.** The following fetched contents were Cloudflare challenges, cookie notices, journal-promotional testimonials, or navigation chrome — not article text:

- `journals.sagepub.com/doi/pdf/10.1177/2042018818781669` (DEAR program): 182 chars of "正在執行安全驗證" Cloudflare + Ray ID stub
- `doi.org/10.7860/jcdr/2014/8108.4092` (JCDR Cardiovascular abnormality, Muslim fasting): 20K chars but entirely journal-promotional content ("Dr Mohan Z Mani testimonials", "About Us Salient Features", nav chrome) — zero substantive research content
- `www.mayoclinic.org/...intermittent-fasting/faq-20441303`: 3-char stub ("---") returned from fetch
- `www.npjournal.org/article/S1555-4155%252823%252900395-1/fulltext`: 3-char stub

For all four, the agent-operator correctly emitted minimal (1 fact) descriptive atomic_facts noting content could not be extracted. The pipeline correctly filtered these to zero evidence in the final pool. This is the one place the loopback layer worked cleanly.

**But the PubMed content gap has a downstream consequence.** Two PubMed URLs entered PageSummary phase (`pubmed.ncbi.nlm.nih.gov/40731344`, `pubmed.ncbi.nlm.nih.gov/38500840`) and both returned Cloudflare browser-challenge pages. The same PubMed-mediated references (Turin 2016, Al-Jafar 2021, Almulhem 2020, Kumar 2025, Albosta 2023) appear throughout the synthesizer outline. These references exist only in the agent-operator's PageSummary narrative summaries, never as atomic_facts tied to fetched PMID content. When the synthesizer asked for evidence pieces to cite, none from these PubMed IDs were available.

---

## Layer 2 — Source reality

The bibliography lists 14 references. Actual source-type classification:

| [N] | URL | Type | Peer-reviewed? | Notes |
|-----|-----|------|----------------|-------|
| [1] | bmj.com/content/389/bmj-2024-082007 | BMJ 2024 NMA | YES | 99 RCTs, 6,582 adults, primary source |
| [2] | hopkinsmedicine.org/health/expert-qa | Patient-education FAQ | NO | Consumer-facing Q&A with Mark Mattson; not research paper |
| [3] | hsph.harvard.edu/news/the-health-benefits-of-intermittent-fasting | Harvard Chan news post | NO | Interview with Courtney Peterson; PR/news |
| [4] | pmc.ncbi.nlm.nih.gov/articles/PMC9946909 | Narrative review, Korean J Fam Med 2023 | YES | Narrative review (not a meta-analysis) |
| [5] | jamanetwork.com/journals/jamanetworkopen/fullarticle/2787246 | JAMA Network Open (Patikorn 2021) | YES | Umbrella review |
| [6] | thelancet.com/.../PIIS2589-5370(24)00098-1/fulltext | Lancet eClinicalMedicine 2024 | YES | Vasim 2024 umbrella review |
| [7] | mdpi.com/2072-6643/13/10/3450 | MDPI Nutrients 2021 | YES | Oosterwijk Ramadan-pregnancy review (MDPI has known rigor debates) |
| [8] | today.uic.edu/benefits-intermittent-fasting-research | University news release | NO | PR about Varady's research — hearsay about findings, not the findings themselves |
| [9] | pmc.ncbi.nlm.nih.gov/articles/PMC10945168 | PMC mirror of Lancet eClinicalMedicine 2024 | DUPLICATE OF [6] | Same paper cited twice under different URLs |
| [10] | mdpi.com/2072-6643/12/8/2478 | MDPI Nutrients 2020 | YES | Osman Ramadan TRE review |
| [11] | ajcn.nutrition.org/article/S0002-9165(23)12517-2/fulltext | AJCN 2015 | YES | Horne 2015 early systematic review (pre-dates most of the evidence base discussed) |
| [12] | bmcpregnancychildbirth.biomedcentral.com/track/pdf/10.1186/s12884-018-2048-y | BMC Pregnancy 2018 | YES | Ramadan perinatal systematic review |
| [13] | jacc.org/doi/10.1016/S0735-1097%2825%2901455-X | JACC 2025 | YES | Notta 2025 conference abstract — 865 chars of fetched content only (title+citation, no data) |
| [14] | massgeneralbrigham.org/...pros-and-cons-of-intermittent-fasting | Patient-education page | NO | Cardiac-rehab dietitian Mary Hyer consumer article |

**CRITICAL: Citations [6] and [9] are the same paper** (Vasim 2024 Lancet eClinicalMedicine umbrella review). PMC 10945168 is the PubMed Central mirror of the Lancet article. The bibliography lists them separately, and they're cited in different sections. This is a duplication defect that AMSTAR-2 item 4 (comprehensive literature search + no duplication) would flag.

**MAJOR: Four of 14 citations are non-research sources** ([2] Johns Hopkins FAQ, [3] Harvard news, [8] UIC Today, [14] MGB patient-ed). They are cited and quoted as if co-equal to BMJ NMA. A real systematic review would either exclude them (AMSTAR-2 item 5) or list them in a separate "grey literature" tier.

**MAJOR: JACC 2025 [13] has only 865 chars of fetched content** — title, citation format, "Background/Methods/Results/Conclusion/Footnote Information" headers, no data. The single atomic_fact extracted from this source is essentially "this paper exists and is about IF vs CR in CAD patients". Citing this as evidence-of-benefit is misleading.

**MAJOR: AJCN [11] (Horne 2015)** searched literature through January 2015 — its data on IF evidence is now a decade out of date. Using it in a 2026 review is acceptable only if framed as historical; the final report uses it to support a current judgment "substantial further research is needed before fasting can be recommended as a health intervention" — which is true but using a 2015 review to make a 2026 claim without acknowledging the decade of new evidence is misleading.

---

## Layer 3 — Claim-to-evidence drift

Reading each `[N]` in the report against the evidence record it resolves to:

**Abstract sentence 1:** "Intermittent fasting works through an altered liver metabolism — the metabolic switch — in which the body periodically switches from liver-derived glucose to adipose cell-derived ketones during fasting periods [5]". Evidence record is verbatim from Patikorn JAMA Network Open 2021. Supported. No drift.

**Abstract sentence 2:** "Clinical trials have demonstrated the benefits of intermittent fasting for obesity, diabetes, and cardiovascular diseases through reduced weight and improved cardiometabolic parameters [5]". This is a generic trial-level summary from the SAME source [5]. The claim is conservative (Patikorn wrote these exact words) but **citing [5] twice in the abstract for two separate sentences recycles evidence and inflates the appearance of multi-source corroboration** — a problem that repeats throughout.

**Abstract sentence 3:** "Research at the University of Illinois Chicago finds that intermittent fasting is as effective as calorie counting for weight loss, producing on average 3-8% of baseline weight reduction depending on the fasting type [8]". Source [8] is `today.uic.edu` — a university news post quoting Varady. The source is PR, not peer review. The report does not disclose this. MINOR drift in the phrase "fasting type" versus source wording "type of fast they're doing". MAJOR concern: citing PR as if it were research.

**Abstract sentence 4:** "Among intermittent fasting strategies, alternate-day fasting showed a trivial weight-loss advantage over time-restricted eating with a mean difference of -1.69 kg (95% CI -2.49 to -0.88) at moderate certainty of evidence [1]". Source [1] is BMJ 2024 NMA. Verbatim, with CI and GRADE certainty preserved. The word "trivial" is verbatim from the BMJ abstract — this is the source authors' characterization of the effect size, faithfully preserved. No drift.

However, **this is the ONLY ADF-vs-IF comparison cited; the more important ADF-vs-CER comparison (MD -1.29 kg, the CORE finding of BMJ 2024 about whether IF beats continuous caloric restriction) is absent from the report** even though the BMJ abstract explicitly presents it. This is a severity-MAJOR selection bias: the report cites the within-IF comparison (which is clinically minor) but drops the between-IF-and-CER comparison (which is clinically central to "does IF work"). The ADF vs CER finding WAS in my atomic_fact for the BMJ source, but survived to final evidence only as the ADF-vs-TRE version.

**Abstract sentence 5:** "Documented adverse effects include dizziness, nausea, headache, and diarrhea during 4- and 6-hour time-restricted eating [9]". Source [9] is the Lancet umbrella review (mirror of [6]). Verbatim Cienfuegos list. Supported. No drift.

**Abstract sentence 6:** "some participants in intermittent fasting trials experienced reductions in bone density and lean body mass [4]". Source [4] is PMC 9946909 narrative review. Verbatim. The mitigation clause ("mitigable by protein-rich diet and resistance training" from my atomic_fact) is NOT in the abstract — the abstract asserts the harm without the mitigation context, which subtly tilts the benefit-risk framing. MINOR.

**Abstract sentence 7:** "Johns Hopkins states that intermittent fasting can be used to manage weight and may prevent or even reverse some forms of disease, while explicitly cautioning that 'intermittent fasting isn't for everyone' and advising consultation with a physician before starting [2]". Source [2] is Hopkins patient-ed FAQ. Verbatim. NOTE: cites patient-ed as authoritative without flagging it.

**Abstract sentence 8:** "Ramadan fasting shows limited body-composition benefits, with results often transient and heterogeneous [10]". Source [10] MDPI Osman. Verbatim. Supported.

**Section s01 "Definitions and Taxonomy" drift:**

The rewritten section s01 cites [2] (Hopkins), [3] (Harvard Chan news), and [1] (BMJ lipid comparison). **None of these three evidence pieces are about taxonomy.** The section explicitly admits "further precision on specific protocol definitions, feeding windows, or calorie allowances is not attempted here where no cited claim supports it" — acknowledging the section has no taxonomic evidence. This is HONEST but structurally broken: a section titled "Definitions and Taxonomy" that cannot cite any taxonomy. The hallucination detector pressure (FIX-5 at 0.25) forced this collapse. The synthesizer should have either used an un-cited definitional paragraph (acceptable for non-controversial nomenclature) or not produced a taxonomy section at all. Severity: MAJOR structural defect.

**Section s02 "Biological Mechanisms" drift:**

Only cites [4] (PMC narrative review) and [5] (Patikorn umbrella). The AMPK/mTOR/FOXO cascade is correctly described. No drift in the cascade; faithful to sources.

**Section s03 "Cardiometabolic and Glycemic Outcomes" drift:**

Cites [5] (clinical trials demonstrated benefits — same recycled sentence from abstract), [6] (Roman 2018 meta-analysis: 6 studies, 553 adults, weight/WC/hip/lean/fat outcomes), and [7] (Oosterwijk Ramadan-pregnancy "three quarters of children exposed to Ramadan fasting during gestation"). **The Oosterwijk Ramadan-pregnancy citation [7] is placed in a "Cardiometabolic and Glycemic Outcomes" section — the citation is about perinatal population exposure, not cardiometabolic or glycemic outcomes.** Severity: MAJOR scope drift.

The section does not cite: BMJ 2024 NMA (the authoritative network meta-analysis), the Vasim umbrella review [6]/[9] specific effect-size data from the table, the AJCN Horne 2015 systematic review, the MDPI Osman Ramadan lipid findings, or any specific meta-analysis's numerical effect sizes beyond the Roman 2018 descriptive mention.

**Section s04 "Comparison with Caloric Restriction and the Isocaloric Question" drift:**

Cites [8] (UIC Today/Varady PR) for the 3-8% weight loss claim AND for blood-pressure and insulin-resistance benefits, and [1] (BMJ 2024) for within-IF comparisons. **The section title promises discussion of the isocaloric question. The ChronoFast study (Ramich 2025 Science Translational Medicine) — the single most direct isocaloric-TRE test — is discussed in my PageSummary responses but has no atomic_fact representation and is not cited.** The Sun 2024 systematic review (PMID 39732588, the definitive IF-vs-isocaloric-CR synthesis) is named in my StormAnswer but also has no atomic_fact representation. The section cannot answer its titular question from its citations. Severity: MAJOR — section promises an analysis the evidence pool does not support.

**Section s05 "Risks, Adverse Effects, and Safety Considerations" drift:**

Cites [4] (bone density/lean mass) and [9] (Cienfuegos/Harvie adverse events). **This is the LARGEST gap in the document.** The section is 3 terse paragraphs. Missing risks available in upstream pipeline phases:

- Lin/Zhong 2024 NHANES 91% CVD mortality signal — absent
- MGB contraindication list — absent (the MGB atomic_fact I wrote was filtered out)
- Adolescent / eating-disorder risk — absent
- Pregnancy-related harm signal from Oosterwijk high-quality study ("one of three high-quality studies found lower birth weight") — absent from s05 but referenced obliquely in s06
- Hypoglycemia in diabetic patients — absent
- Sex-specific TRE effects (glucose tolerance suppressed in nonobese women per Heilbronn/Ravussin, from PMC 9946909) — absent
- BMJ 2024 adverse LDL signal (TRE increases LDL vs whole-day fasting) — absent
- Lowe 2020 JAMA lean body mass finding with specific weight-loss numbers — absent (the general "bone density and lean body mass" claim is cited but the specific Lowe 2020 -0.94 kg RCT that prompted the concern is not)

Severity: CRITICAL. The section name promises risk coverage and delivers only a catalogue of minor side-effects while omitting the two most consequential risk signals.

**Section s06 "Population-Specific Considerations and Cultural-Religious Fasting" drift:**

Cites [10] (Osman), [11] (AJCN Horne 2015), [7] (Oosterwijk). The Oosterwijk "43 articles, mean quality 5.4, 3 high-quality, one found lower birth weight" is accurately presented. The Horne 2015 conclusion "substantial further research is needed" is quoted but without noting that this is a 2015 paper whose date bounds its relevance to 2026. Severity: NOTE (date context omitted).

**Section s07 "Methodological Quality, Evidence Certainty, and Clinical Implications" drift:**

Cites [10] (Osman Ramadan lipid / glucose) and [12] (BMC Pregnancy Ramadan perinatal). **The section title promises a methodological-quality audit OF THE INTERMITTENT FASTING EVIDENCE BASE. The actual content only discusses Ramadan lipid-vs-glucose endpoint divergence and perinatal study design.** It does not address methodological quality of the broader IF literature (heterogeneity in the Vasim umbrella review was 42% high/very-high, 48% of meta-analyses had <10 studies — I wrote this as atomic_fact, it was filtered). It does not address GRADE certainty across endpoints. It does not address risk-of-bias. Severity: MAJOR — section name/promise does not match content.

---

## Layer 4 — Research-question balance

Paragraph-level classification (heuristic count): **18 benefit-leaning, 6 risk-leaning of 29 content paragraphs**. The document is 3:1 benefit-weighted on a query explicitly asking "benefits AND risks".

The risks section is 3 paragraphs and names:
- Bone density and lean body mass loss (with mitigation clause)
- Cienfuegos 4/6h TRE: dizziness, nausea, headache, diarrhea
- Harvie broader IF: physical (cold, constipation) and psychological (headache, lack of energy, irritability, difficulty concentrating)

What's missing from Risks as documented in upstream pipeline:

1. **Lin/Zhong 2024 NHANES** — the AHA newsroom PR (`newsroom.heart.org`) was fetched during PageSummary and provided full text including:
   - 20,000 U.S. adults, mean age 49, median 8-year follow-up (max 17 years)
   - 91% higher CVD mortality with <8-hour eating window
   - 66% higher heart/stroke mortality with 8-10h window in existing-CVD patients
   - Null all-cause mortality effect
   - Presented at AHA EPI Lifestyle Chicago March 2024 by Victor Wenze Zhong (Shanghai Jiao Tong)
   - Disease-a-Month 2024 scoping review (PMID 38910053) confirms this signal and calls for balanced reporting
   
   None of this made it to the atomic_fact pool. The sources `newsroom.heart.org` and `jamanetwork.com/journals/jama/fullarticle/2817556` were not among the 23 source URLs processed in SourceAnalysisBatch. The PageSummary outputs were available to the synthesizer via `seen_pages` but are not [CITE:evidence_id]-addressable.

2. **Mass General Brigham contraindications** — fetched in full (10,179 chars), I wrote 4 atomic_facts including the explicit contraindication list. Pipeline filtering reduced MGB to 1 atomic_fact (the 10-12 hour metabolic switch). The contraindications are not in the final evidence pool and thus not citable by the synthesizer.

3. **Adolescent / eating-disorder risk** — PageSummary captured Helmholtz Munich "might come with risks for children and teenagers", Kumar 2025 PMID 40936230 "may exacerbate disordered eating patterns in adolescents", and the Mass General Brigham contraindication for "still growing" individuals. None of these made it to atomic_fact.

4. **ChronoFast isocaloric null finding** (Ramich 2025 Science Translational Medicine) — available in PageSummary, no atomic_fact, not cited.

5. **BMJ 2024 HbA1c and HDL null findings** — "No differences were noted between intermittent fasting, continuous energy restriction, and ad-libitum diets for HbA1c and HDL cholesterol" — I wrote this as atomic_fact, filtered out.

6. **BMJ 2024 adverse LDL signal** — "time restricted eating resulted in a small increase in total cholesterol, LDL cholesterol, and non-HDL cholesterol" vs whole-day fasting — I wrote this, filtered out. This is an adverse signal, not merely a null.

The word "proven" in the query receives no direct treatment. The BMJ 2024 abstract's "moderate certainty" qualifier is preserved in abstract sentence 4. No summary-of-findings GRADE grid is presented. The document does not distinguish between proven benefits (hard endpoints: weight, CVD events) and surrogate benefits (blood pressure, fasting glucose), which is central to the PRISMA-compliant framing of the research question.

---

## Layer 5 — Verification integrity

`scripts/loopback_auto_verify.py` served all 7 VerificationBatch calls. The heuristic: if `direct_quote[:60]` appears as a substring in the source excerpt, mark SUPPORTED (confidence 0.88); if `direct_quote[:30]` matches, confidence 0.80; otherwise PARTIALLY_SUPPORTED (0.65). NOT_SUPPORTED is explicitly commented never-emitted "because that would trigger the faithfulness gate and drop evidence".

Consequence: verification in this run is structural (substring), not semantic. Examples:

- **Claim scope drift passes verification**: my Roman 2018 statement says "meta-analysis compared intermittent vs continuous dieting in 6 studies with 553 adults age 39.6-61.5 with overweight, obesity, or diabetes on lean mass, body weight, waist circumference, hip circumference, and fat mass outcomes." The quote is a table row from the Lancet umbrella review. The quote is verbatim. But if the report narrows scope ("overweight adults with obesity seeking weight loss"), the verifier sees the verbatim quote substring and marks SUPPORTED even if the claim's scope has drifted.
- **Attribution drift passes**: my "Krista Varady's body of research at UIC finds intermittent fasting is as effective as calorie counting for weight loss, producing 3-8% of baseline weight reduction depending on the fasting type" — quote contains "type of fast they're doing"; the operator's paraphrase "fasting type" substrings the quote's first 60 chars, so SUPPORTED passes even on paraphrase drift.

Of the 37 evidence pieces, I would flag approximately 5-8 for PARTIALLY_SUPPORTED under rigorous review — primarily those where the statement's attribution or scope subtly drifts from the quote's context. The final faithfulness score of 86.2% is an artifact of this heuristic matching; a GRADE-trained reviewer would likely land closer to 70-75%.

**Specific claim I would flag as PARTIALLY_SUPPORTED** on rigorous review:
- ev for JACC 2025 Notta: the atomic_fact asserts a systematic review and meta-analysis exists for IF-vs-CR in CAD patients. The fetched content (865 chars) provides the title and citation only — no methodology, no effect sizes, no CI, no date of search. The atomic_fact is correct-as-far-as-it-goes but its claim "focuses on the coronary artery disease (CAD) patient population as a high-cardiovascular-risk subgroup where the IF vs CR tradeoff is most clinically consequential" adds operator interpretation ("most clinically consequential") not in the source.
- ev for PMC 9946909 Stekovic reference: my atomic_fact asserts "Stekovic et al. 6-month alternate-day fasting in healthy nonobese subjects reduced total cholesterol, LDL, VLDL, triglycerides, and systolic blood pressure WITHOUT reducing fat-free mass or bone density." The quote supports the outcome list; the "WITHOUT reducing fat-free mass or bone density" part is from a separate sentence in the source. The statement COMBINES two separate claims from the source into one, which is summary but not verbatim. NOTE.

---

## Layer 6 — PRISMA 2020 / AMSTAR-2 / GRADE conformance (CRITICAL)

The report's title section names section titles like "Methodological Quality, Evidence Certainty, and Clinical Implications" and uses the phrase "this systematic review" and "this review" throughout section text. It is thus claiming the mantle of a systematic review. Under PRISMA 2020 and AMSTAR-2, the report fails nearly every structural item:

| PRISMA 2020 / AMSTAR-2 item | Present? | Location / Notes |
|--------|---|---|
| Eligibility criteria (population, intervention, comparator, outcomes) | ABSENT | No PICO statement anywhere in the document |
| Information sources (databases, date range) | ABSENT | No list of databases or search date range |
| Search strategy (actual query strings per database) | ABSENT | Not disclosed |
| Study-selection process (dual reviewers, conflict resolution) | ABSENT | The "dual reviewer" is the agent-operator serving responses; not disclosed |
| Data-extraction process | ABSENT | Not disclosed |
| Risk-of-bias assessment per included study (AMSTAR-2 item 9) | ABSENT | No RoB table, no tool named (ROBINS-I, Cochrane RoB 2), no per-study assessment |
| Synthesis methods (narrative vs pooled; heterogeneity handling) | ABSENT | Not disclosed |
| Certainty grading per outcome (GRADE per PICO) | ABSENT | The phrase "moderate certainty of evidence" appears in s04 as direct quote from BMJ 2024; no GRADE assessment BY the report authors |
| PRISMA flow diagram (identification → screening → eligibility → inclusion) | ABSENT | No flow diagram; search/screening counts absent |
| Protocol registration (PROSPERO etc.) | ABSENT | No registration; the word "protocol" only appears as "fasting protocol" |
| Conflict-of-interest / funding disclosure | ABSENT | No declaration |
| Limitations section | ABSENT | No dedicated limitations section; some limitations embedded in s07 |
| Implications for practice / research (PRISMA 2020 item 24) | PARTIAL | s07 has some clinical-implications language; not structured |

This is AMSTAR-2 "critically low" quality: the report fails multiple "critical domains" including protocol registration (AMSTAR-2 item 2), comprehensive search (item 4), study-selection duplication (item 5), risk-of-bias (item 9), appropriateness of pooling (item 11), and consideration of RoB in synthesis (item 13).

**Severity: CRITICAL.** Calling this "a systematic review" in section prose (e.g., s02 "This systematic review synthesizes...") violates reporting-transparency norms. It should be titled "a narrative overview of intermittent fasting benefits and risks" and revised to drop the "systematic review" framing throughout.

---

## Layer 7 — Hallucination-detector pressure effects

The NLI detector (flan-t5-large MiniCheck, FIX-3/4/5 active at 0.25 threshold) flagged every section for rewrite (8/8 sections including abstract). Average ratio 0.58; range 0.29 (abstract post-rewrite) to 0.75 (s02 initial draft).

The rewrite rounds had a specific effect: **they removed every analytical overlay, cross-evidence inference, and synthesis paragraph.** Examples:

- s01 initial: included an IF taxonomy list ("16:8, ADF, 5:2, MADF, IER, FMD") — NLI-flagged because no atomic_fact named these modalities. Rewrite removed the list entirely; the final s01 contains no taxonomy list.
- s02 initial: "This shift in fuel selection, rather than any single metabolic endpoint, organizes much of the biological signal attributable to intermittent fasting" — flagged, removed.
- s05 initial: "The body-composition risks are among the best characterized" and "the shorter eating windows in these protocols, which concentrate the daily food intake into a narrower period, may contribute to the mix of vasomotor, gastrointestinal, and neurological symptoms" — flagged, removed.

In principle this is FIX-5 working as intended: anti-hallucination pressure eliminates un-grounded synthesis overlay. In practice, it produces a document that reads as a claim-list more than a literature synthesis. Section s05 in particular is reduced to three one-line claims followed by restatement. This is the tradeoff FIX-5 was designed to accept, but the cost is:

1. The document loses its narrative-synthesis character (Cochrane Handbook 12.2 "textual narrative description of included studies" becomes impossible if every synthesis sentence is NLI-flagged).
2. Context that would normally link claims (e.g., "bone density loss is clinically consequential because it takes years to reverse") is removed.
3. The reader is given facts but not told which facts matter more or how they relate.

A correct FIX-5 threshold may be higher than 0.25, or the NLI detector may need quote-centered context windows that are less aggressive on meta-synthesis prose. The advisor-recommended next calibration step is to run the same pipeline with FIX-5 threshold at 0.40 and compare content quality.

---

## Layer 8 — Cross-section contradictions and recycling

**Citation recycling (severity: MAJOR):**
- Citation [5] (JAMA Network Open Patikorn) used in Abstract (×2 — mechanism + clinical trials) + s02 (mechanism) + s03 (clinical trials) = 6 citations across 3 sections from the SAME source's 3 atomic_facts.
- Citation [8] (UIC Today Varady PR) used in Abstract + s04 (×4) = 5 citations from 2 atomic_facts. Every benefit claim in s04 traces to UIC PR.
- Citation [10] (MDPI Osman) used in Abstract + s06 + s07 (×2 for lipid and glucose) = 4 citations.
- Citation [1] (BMJ 2024) used in Abstract + s01 (×1) + s04 (×2) = 4 citations from 2 atomic_facts.

Source-recycling here is not merely stylistic — it reflects an evidence pool too narrow for the 7-section outline. 14 references supporting 32 sentences across 7 sections means average 2.3 citations per reference, but the distribution is skewed: [13] JACC has 1 citation total, [11] AJCN has 1; [5] Patikorn carries 6.

**Cross-section scope drift (severity: MAJOR):**
- s01 "Definitions and Taxonomy" cites BMJ [1] lipid-comparison (belongs in s03/s04) and Peterson RCT overview [3] (belongs in s07)
- s03 "Cardiometabolic and Glycemic Outcomes" cites Oosterwijk [7] Ramadan-pregnancy (belongs in s06)
- s04 "Comparison with Caloric Restriction and the Isocaloric Question" never addresses the isocaloric question; ChronoFast is unavailable as evidence

**Silent contradictions (severity: NOTE):**
- s03 claims "clinical trials have demonstrated the benefits" while s04 (citing the same source neighborhood) says IF is "as effective as calorie counting" — these are not direct contradictions but the juxtaposition "benefits demonstrated" with "no better than CR" is never reconciled.
- s06 cites Horne 2015 [11] for "substantial further research needed before fasting can be recommended as a health intervention" — this is a conclusion that contradicts the abstract's framing of established benefit [5]/[8]. The contradiction is not flagged.

---

## Layer 9 — Pipeline artifact observations

- Evidence pool sizes: initial analyzer 56 → off-topic filter removed 8 (iteration 1) → 48 → tier/relevance 37 → deepener added 20 in iter 2 → 15 after pre-verify gate → 37 merged final pool. The filtering that occurred between analyzer output (my 55ish atomic_facts) and final pool (37) dropped risk-side facts disproportionately: MGB contraindications, BMJ null HbA1c/HDL, BMJ TRE-increases-LDL, hypoglycemia context, sex-specific TRE effects, adolescent eating disorder — these all existed as atomic_facts in my SourceAnalysisBatch responses, none survived.
- The filtering criterion is embedding-based relevance to the query. For a query "benefits AND risks of IF", relevance to "risks" via embedding may score lower than relevance to "IF mechanisms" because the risks vocabulary is scattered (dizziness, hypoglycemia, eating disorder) while mechanisms vocabulary is concentrated (autophagy, mTOR, AMPK). This is a documented limitation of cosine-similarity relevance filtering for multi-axis queries. See `memory/fix_RC5.md` for prior work on adjustable relevance gates.
- The auto-grade script assigned HIGH to any evidence whose `statement` or source title matched `STATS_SIGNAL` regex (meta-analysis/systematic review/RCT/SMD/MD/95% CI). The final "86.2% faithfulness" and "GRADE-PASS: Assigned certainty ratings to 20/20" are heuristic outputs from a hand-crafted regex, not from an LLM. The pipeline does not actually grade; it labels.
- "FIX-QG2: Synthesis converged (gate=passed, iter=2)" — the quality gate checks word count ≥2000 (2549), citation count ≥5 (17), unique sources ≥5 (14). It does not check benefit-vs-risk balance, coverage of stated research-question axes, or evidence-pool completeness against the outline. The gate passes the report despite the MGB contraindication and Lin/Zhong mortality omissions.

---

## Layer 10 — Specific high-risk findings

1. **Courtney Peterson's "1,600+ citations" and Harvard Chan move**: VERIFIED verbatim in fetched `hsph.harvard.edu` content. Not operator-added. Harvard Chan news itself is a PR/news source not a primary research paper — citing Peterson's "largest RCT of IF in humans" via this PR source is secondhand; the primary trial protocol or publication is not cited.

2. **BMJ 2024 numbers (-1.29 kg ADF-vs-CER, -1.69 kg ADF-vs-TRE, -1.05 kg ADF-vs-whole-day, 99 RCTs, 6,582 adults)**: All four were in fetched BMJ content (verified). But **only -1.69 kg (ADF-vs-TRE) made it into the final evidence pool**. The core -1.29 kg ADF-vs-CER finding — the only IF strategy showing benefit versus continuous caloric restriction at moderate certainty — was filtered out. This is the most important single finding for the "does IF beat CR" question and it is absent.

3. **Cienfuegos and Harvie adverse-event lists**: VERIFIED verbatim in PMC 10945168 content. Attribution and symptom lists match source exactly. No operator injection.

4. **Mass General Brigham contraindication list**: VERIFIED verbatim in fetched MGB content. I extracted as atomic_fact. **Filtered out by pipeline before reaching final pool.** The contraindication list is invisible to the final report despite being verbatim-available in source.

5. **Varady "3-8% of baseline weight" quote**: VERIFIED verbatim in `today.uic.edu` source. But citing the UIC Today news post as primary evidence for a weight-loss claim understates source type — the underlying papers (Varady et al.) are not themselves cited.

---

## Synthesis — what this audit reveals about pipeline quality

1. **The loopback cannot validate content quality; it validates plumbing.** The agent-operator supplied all 88 responses using domain knowledge of the IF literature. The verbatim quote check passed for 37/37 evidence pieces because the operator knew which source contains which quote. GLM-5.1 running the same prompts against the same fetched content would likely produce atomic_facts with higher rates of fabrication, higher misquotation, and poorer topic alignment. The 86.2% faithfulness number reported by the dashboard has no predictive value for paid-LLM runs.

2. **Pipeline filtering is the primary content-quality bottleneck, not the LLM.** The MGB contraindications, BMJ ADF-vs-CER, BMJ null HbA1c/HDL, and ~18 other substantive atomic_facts were written correctly by the operator and then removed by embedding-relevance/tier/off-topic filters before reaching synthesis. The FIX-1 (query-aware Risks section), FIX-3 (abstract audit), and FIX-5 (threshold 0.25) changes work as designed — but they operate downstream of a filter that is discarding risk-side evidence. The higher-leverage fix is to widen the filter or add a risk-axis-specific evidence-retention rule.

3. **PRISMA conformance is zero.** The document does not describe its eligibility criteria, search strategy, databases, dates, study-selection process, risk-of-bias assessment, synthesis method, or GRADE certainty. Calling this "a systematic review" (as the report text does repeatedly) is structurally false. For a "deep research" product this is the headline conformance defect — it is a brand-safety issue as well as an accuracy issue.

4. **The 3:1 benefit-to-risk paragraph ratio reflects the filter bias, not the underlying evidence.** Every major risk signal available in the fetched content and PageSummary outputs failed to reach the final report. A reader cannot distinguish "we looked at risks and found little" from "risks were filtered out of our evidence pool" — the report claims the former in its introduction framing while the latter is what actually happened.

5. **Specific remediation priorities, ordered by expected impact:**
   - **Most urgent**: audit why high-relevance-score atomic_facts (MGB contraindications marked 0.95, BMJ null HbA1c marked 0.85-0.96) were filtered out. This is a FIX-RC5 / off-topic-gate regression test.
   - **Next**: require the synthesizer to include ≥1 risk-axis citation per 2 benefit-axis citations when the query contains "risks" or "adverse". This is a new FIX — call it FIX-RISK-QUORUM.
   - **Next**: drop the "systematic review" self-labeling or actually produce a PRISMA-conformant skeleton (eligibility/methods/flow diagram/RoB/GRADE). The former is a 10-minute prompt change; the latter is a pipeline redesign.
   - **Next**: resolve the [6]/[9] duplicate citation and detect same-paper-different-URLs before bibliography assembly.
   - **Next**: reconsider the 0.25 NLI rewrite threshold. At 0.25 the rewrites flatten synthesis prose into claim-lists. A graduated threshold (0.25 for per-claim hallucinations, 0.40+ for cross-claim synthesis sentences) may preserve narrative while catching fabrication.

6. **The loopback should not be re-run as a validation tool until the agent-operator is replaced by a consistency fixture.** A static response corpus (pre-written SourceAnalysisBatch/StormAnswer responses hashed and served deterministically) would make the loopback reproducible and would allow quality changes to be attributed to pipeline changes rather than operator variance. Without that, every loopback run is nondeterministic and validates only plumbing.
