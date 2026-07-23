# Phase 2 Verdict — Reference + Top-Scorer Teardown, Per-Sub-Item Win Map (investigator: Fable)

## INGESTION RECEIPT (Phase-1 files read IN FULL)

/home/polaris/wt/faithoff/docs/race_fact_initiative/SCORING_SPEC.md | lines=245 | FIRST: "# SCORING_SPEC — RACE + FACT — LOSSLESS consolidation of Sol + Fable (Phase 1)" | MID(line 122): "[S+F] #17,#18 judged on CLEANED text (bibliography stripped) → journal/English compliance must be in-PROSE" | LAST: "replication (±0.027 noise, single-call judge)."

/home/polaris/wt/faithoff/docs/race_fact_initiative/phase1_sol_verdict.md | lines=462 | FIRST: "# Phase 1 Investigator Verdict: Definitive Map of DeepResearch Bench RACE + FACT Scoring" | MID(line 231): "### A6.5 Dataset-level leaderboard aggregation" | LAST: "The highest-leverage scoreable surfaces are: **(1)** task-specific Insight—causal/mechanistic analysis, cross-source synthesis, logical integration, uncertainty, and novel implications—because Insight averages 35.2% of RACE weight and reaches 42%; **(2)** Comprehensiveness—complete coverage of every requested dimension/entity/industry/time scope with representative evidence—because it averages 29.2%; **(3)** exact Instruction Following, especially source/type/language/output constraints, because omissions receive separate criteria and can carry up to 45% within that dimension; **(4)** clear structure and synthesis-oriented readability, usually lower-weight but as high as 25% for audience/data-presentation-heavy tasks; and **(5)** FACT’s independent supported-pair surface: inline, extractable, reachable citations attached to atomic claims, with more unique supported statement–URL pairs raising effective citations and unsupported pairs lowering code precision. For task 72, the four largest coefficients are mechanistic labor-market analysis (0.0800), critical cross-industry synthesis (0.0800), restructuring-dimension breadth (0.0725), and industry breadth (0.0725), so fixes that deepen mechanisms and synthesis while closing missing sector/effect coverage have the largest grounded RACE headroom (`criteria.jsonl:72`); citation-count work cannot substitute for those RACE surfaces because FACT is calculated separately (`run_benchmark.sh:35-95`)."

/home/polaris/wt/faithoff/docs/race_fact_initiative/phase1_fable_verdict.md | lines=472 | FIRST: "# Phase 1 Verdict — RACE + FACT scoring map (investigator: Fable)" | MID(line 236): "  criterion; the reported quantity is target/(target+reference) (A.5 step 4-5)." | LAST: "(`stat.py:26-30`)."

All local artifacts below are from `/home/polaris/wt/faithoff/third_party/deep_research_bench/` (checkout 469cce54). Extracts saved under `/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/investigators/p2/` (ref_72.md, ref_{4,51,73,91,100}.md, top_*_72.md, aiq_*.j2, lb.html). Every claim below carries a file path, line number, or URL. Web fetches used shell curl only, per the operator brief.

---

# PART 1 — TARGET A: the task-72 REFERENCE report (the bar we are divided by)

Source: `data/test_data/cleaned_data/reference.jsonl`, id=72. **69,284 chars, 9,029 words, 112 paragraphs, 33 headings (1 H1 + 8 H2 + 24 H3), 2 tables (18 pipe rows), 119 bold spans, zero citations** (pre-cleaned). Gemini-2.5-Pro Deep Research, April 2025 (paper §4.1; SCORING_SPEC I.10). On the live leaderboard the system that produced it, `gemini-2.5-pro-deepresearch`, scores 49.98 Overall / 49.92 Insight (GPT-5.5 tab) and 49.71/49.45 (Gemini tab) — i.e., the reference sits at parity by construction, and every winner's margin is measured against exactly this artifact (leaderboard gradio config, muset-ai-deepresearch-bench-leaderboard.hf.space, fetched 2026-07-23, saved lb.html).

## 1.1 Full outline (verbatim heading list, in order)

```
# The Restructuring Impact of Artificial Intelligence on the Labor Market: A Literature Review
## 1. Introduction: AI, the Fourth Industrial Revolution, and Labor Market Restructuring
   1.1 Defining the Fourth Industrial Revolution (4IR) and AI's Role
   1.2 AI as a Catalyst for Labor Market Transformation
## 2. Theoretical Lenses: Understanding AI's Mechanisms of Impact
   2.1 The Task-Based Framework: Displacement and Reinstatement Dynamics
   2.2 Skill-Biased, Task-Biased, and Routine-Biased Technical Change (RBTC)
   2.3 AI as Substitute, Complement, or Augmentation Tool
## 3. Empirical Findings: AI's Measured Effects on Employment
   3.1 Job Displacement and Creation: Evidence from Automation and AI Studies
   3.2 Impact on Aggregate Employment, Wages, and Job Polarization
   3.3 Cross-Country and Regional Variations
   [Table 1: Summary of Key Empirical Studies on AI/Robot Impact — 8 study rows × 6 columns]
## 4. Sectoral Disruptions: How AI is Reshaping Industries
   4.1 Manufacturing and Logistics · 4.2 Healthcare, Finance, Transportation
   4.3 Creative, Marketing, Service · 4.4 Evolving Workforce Needs Across Sectors
## 5. Consequences for Wages, Inequality, and Skills
   5.1 Wage Structures and the Labor Share · 5.2 AI Adoption and Income Inequality
   5.3 Shifting Landscape of Skill Demand
## 6. Debating the Future: Pace, Scale, and Outlook
   6.1 Optimistic vs. Pessimistic Scenarios · 6.2 Factors Moderating AI's Impact
   6.3 Addressing the Productivity Paradox
## 7. Navigating the Transition: Policy Responses and Strategies
   7.1 Education, Reskilling, Lifelong Learning · 7.2 Social Safety Nets and Labor Market Policies
   7.3 Taxation and Regulatory Approaches
   [Table 2: Summary of Policy Recommendations from Literature — 6 policy areas]
## 8. Conclusion: Synthesis, Debates, and Future Research Agenda
   8.1 Recap of Established Findings and Consensus Points
   8.2 Highlighting Key Areas of Disagreement in the Literature
   8.3 Identifying Research Gaps and Directions for Future Inquiry
```

Structural reading: the outline is **theory → evidence → sectors → distributional consequences → debate → policy → synthesis**. Section 2 is a dedicated MECHANISMS section (Insight #7); section 8.1/8.2 is a dedicated consensus/disagreement synthesis (Insight #8); 8.3 is a dedicated future-agenda section (Insight #11). The rubric's biggest cells each own named top-level real estate.

## 1.2 How the reference earns each big cell — quoted evidence

### Insight #7 "Mechanisms of AI-driven restructuring" (eff 0.0800)
The reference doesn't just name the task-based framework; it decomposes it into opposing forces, states the net-effect condition, and then draws a NON-OBVIOUS implication:
- ref_72.md:31-34: "**Displacement Effect**: This occurs when automation technologies allow capital … to take over tasks previously performed by human workers … tends to decrease the overall share of national income going to labor" / "**Reinstatement Effect**: Counterbalancing displacement is the potential for technology to create entirely *new tasks* in which labor holds a comparative advantage" / "technology also generates a **Productivity Effect** … concerns about 'so-so automation'—technologies that displace workers but offer only marginal productivity improvements."
- ref_72.md:36: "The *net impact* … ultimately depends on the dynamic balance between the displacement, reinstatement, and productivity effects."
- The second-order move that separates 8–10 from mid-band (`criteria_prompt_en.py:261` "goes beyond obvious impacts to uncover subtle or second-order effects"): ref_72.md:38: "This perspective suggests that **the direction of AI innovation itself is a key determinant of labor market outcomes and potentially a target for policy influence**, aiming to foster technologies that complement rather than solely replace human labor."
- Dynamic mechanism, not static taxonomy — ref_72.md:60: "An AI tool might initially serve to augment a worker's capabilities, but subsequent improvements in the AI or redesign of the workflow could lead to the full automation of the task, transforming the relationship from augmentation to substitution."
- Mechanism-of-measurement insight — ref_72.md:100: "a potential temporal lag and scale mismatch complicates the empirical assessment … might be explained by **implementation lags inherent to general-purpose technologies** … This suggests that current aggregate statistics may not yet fully capture the potentially transformative effects underway."
Pattern: every mechanism paragraph ends with a "this implies/suggests" clause that converts description into deduction — exactly the ":256 deeply analyzes interplay and causal mechanisms, rather than a superficial listing" gate (phase1_fable_verdict.md §A.7).

### Insight #8 "Critical cross-industry synthesis" (eff 0.0800)
- Heterogeneity is analyzed, not just noted — ref_72.md:73: the meta-analysis paragraph names the DRIVERS of divergence: "significant *heterogeneity* in results, driven by factors such as the geographical scope of the study (broader country samples yielded more positive results), the inclusion of control variables … the sector focus (manufacturing-focused studies reported more negative effects), the level of data aggregation …"
- Explicit consensus/no-consensus verdicts — ref_72.md:81: "**Overall Assessment**: The empirical literature does not offer a simple consensus on the net employment impact … The observed balance between these forces varies significantly depending on the specific technology studied … time period … geographical context … level of analysis … methodology … outcome measured."
- Cross-sector pattern extraction after the sector tour — ref_72.md:147-149: "the sectoral analysis reveals that AI's impact extends beyond merely automating existing processes … It also acts as an enabling technology" and "unlike earlier waves of automation that primarily impacted manufacturing and routine clerical work, AI is now directly affecting sectors like finance, healthcare, law, and creative industries … the disruptive and restructuring effects of the current technological wave could be **more pervasive and rapid** than those experienced previously."
- A dedicated disagreement section — ref_72.md:291-294 (8.2) lists four named debates ("Net Employment Outcome … Pace and Scale of Disruption … Magnitude of Wage Effects … Optimal Policy Mix"), each stating both poles and why evidence is unresolved.

### Insight #9 4IR integration (0.0480)
- ref_72.md:7: "Unlike previous industrial revolutions characterized by mechanization, mass production, or early automation, the 4IR represents a new paradigm … marked by the fusion of physical, digital, and biological spheres. Its defining characteristics are the unprecedented *speed and scale*…"
- The non-superficial move (`criteria_prompt_en.py` insight gate "not a superficial mention"): ref_72.md:11: "This interconnectedness implies that analyzing AI's labor market impact requires consideration of these synergies and the overall technological system, rather than viewing AI in isolation."

### Insight #10 Emergent themes / novel perspectives (0.0640)
The reference repeatedly coins higher-order themes AFTER evidence blocks:
- ref_72.md:98: "The pronounced heterogeneity in empirical findings … strongly indicates that the labor market effects of AI and automation are **not predetermined by the technology itself**. Instead, they are heavily mediated by the specific economic structure, institutional environment, and policy choices."
- ref_72.md:172: inequality is elevated to societal risk with a political-economy linkage: "Research linking economic hardship among losers of technological change to support for populist political movements underscores these risks … The focus shifts from merely maximizing efficiency to ensuring that the gains from AI are broadly shared."
- ref_72.md:184: the human-skills paradox: "While AI demonstrates increasing prowess in automating complex analytical and cognitive tasks, it simultaneously appears to elevate the importance of skills that are considered uniquely *human*… precisely because these are areas where AI currently lags."
- ref_72.md:257: policy tension as an emergent theme: "Exploring these policy options reveals an inherent tension. On one hand, policies like automation taxes aim to *slow down* technological adoption … On the other hand, capturing the potential productivity benefits … requires *accelerating* adoption … a complex policy dilemma."

### Insight #11 Implications & future agendas (0.0480)
- Section 8.3 (ref_72.md:296-307) is 8 bulleted research-gap paragraphs, each substantive ("the 'reinstatement effect' remains less understood. More research is needed on the processes through which AI leads to the creation of new tasks…", "research that moves beyond static comparisons to better understand the *dynamics* of the adjustment process"). Policy implications occupy the whole of section 7 plus Table 2.

### Comp #2 Breadth of restructuring dimensions (0.0725)
All six enumerated aspects of the criterion (`criteria.jsonl:72` comp[1]: job creation, displacement, transformation, skill demands, wages, productivity) own dedicated sections: displacement/creation = 3.1; transformation/task content = 2.1-2.3; skills = 5.3 and 4.4; wages = 5.1; productivity = 6.3 (the Productivity Paradox section, with 5 candidate explanations, ref_72.md:211-219). Nothing is a one-liner; each dimension gets 300-900 words.

### Comp #3 Industry-specific scope (0.0725)
Section 4 covers manufacturing, logistics, healthcare, finance, transportation, creative/media, marketing, customer service — 8+ named industries with per-industry named applications AND per-industry labor consequences (e.g., ref_72.md:129 transportation: "AVs directly threaten the livelihoods of millions employed as taxi, ride-hail, and truck drivers … also the complex reorganization of work, including the emergence of new tasks related to remote monitoring, system maintenance, and fleet management"). Then 4.4 extracts the common cross-sector pattern (Comp#3's "common and sector-specific patterns" requirement).

### Comp #4 Disruptive character & scale (0.0435)
- ref_72.md:7: "unprecedented *speed and scale* of technological change"; ref_72.md:149: "more pervasive and rapid than those experienced previously"; section 6 is entirely devoted to pace/scale debate.

### Comp #5 Literature depth/representativeness (0.0435)
Table 1 (ref_72.md:102-113) is a literature-synthesis table: 8 rows, columns "Study (Author(s), Year, Source) | Technology Studied | Geography/Context | Methodology | Key Findings on Employment | Key Findings on Wages/Inequality" — including named authors/journals in PROSE-safe form: "Acemoglu & Restrepo (2020, JPE)", "Graetz & Michaels (2018, REStat)", "Damioli et al. (2021, Res Policy)". This is how source-quality signal survives the bibliography strip (SCORING_SPEC I.7 note on #17/#18).
Precise numbers are carried inline: ref_72.md:71: "each additional robot per thousand workers reduced the local employment-to-population ratio by 0.39 percentage points and local wages by 0.77% … approximately 0.2 percentage points … and 0.42% … (50-70%) of the changes in the US wage structure between 1980 and 2016."

### Comp #6 Balanced impacts (0.0290)
Duality is installed as the report's spine at the outset — ref_72.md:19: "The literature frequently juxtaposes the potential economic benefits of AI – such as enhanced productivity, efficiency, and innovation – with these substantial risks … This inherent duality, the simultaneous promise and peril of AI, forms the central tension explored throughout academic research." Section 6.1 then formalizes optimist/pessimist/nuanced positions.

### Instruction #12-#16 (form/focus/4IR/disruption/industries; 0.0250-0.0500)
The title itself replays the prompt: "The Restructuring Impact of Artificial Intelligence on the Labor Market: **A Literature Review**" (ref_72.md:1); every prompt keyword (4IR driver, disruption, various industries) is a top-level heading. The conclusion re-anchors the genre: ref_72.md:274: "This review of high-quality journal articles reveals…"

### Instruction #17/#18 journal-only/English-only (0.0375/0.0250)
With the bibliography gone, the compliance signal is (a) the explicit claim "review of high-quality journal articles" (ref_72.md:274), (b) named author-year-journal attributions in Table 1, (c) one honest scope note: ref_72.md:127: "(Note: Available sources provided limited specific journal evidence on labor market employment impacts within healthcare)" — which itself performs the journal-only constraint.

### Readability #19-#25 (0.0140-0.0280)
- S1 structure: numbered 2-level hierarchy, roadmap intro (1.1/1.2 define terms and set the central question), synthesizing conclusion (8.1 recap → 8.2 debates → 8.3 gaps).
- S2 cohesion: explicit micro-transitions everywhere: ref_72.md:64 "Moving beyond theoretical frameworks, a growing body of empirical research…"; ref_72.md:85 "Despite the mixed evidence on net employment, several broader trends…"; ref_72.md:153 "The restructuring driven by AI has profound consequences…".
- P1 synthesis-not-serial-summary: paragraphs are organized by CLAIM with studies as support (e.g., ref_72.md:87 wage paragraph aggregates "consistently linked … frequently cited … strongly associated"), never "Paper A found… Paper B found…" run-ons.
- D1/F1: two labeled tables ("**Table 1: Summary of Key Empirical Studies…**", "**Table 2: Summary of Policy Recommendations from Literature**"), bold key terms (119 bold spans), definition-bearing bullets.
- A1 term explanation: every framework is defined at first use (4IR, SBTC, RBTC, displacement/reinstatement, "so-so automation", Productivity J-Curve — ref_72.md:216).
- Hedging register is calibrated, not evasive: "Some analyses suggest", "may not be static or clear-cut", "remains challenging in some large economies" — uncertainty is attributed to the literature, and sections still end with committed syntheses.

## 1.3 Reference style across dimension-weight shifts (other entries)

- **Task 91** (Saint Seiya inventory; weights .37 Comp/.11 Ins/.32 Inst/.20 Read — SCORING_SPEC I.5): ref_91.md = 68,011 chars, 9,976 words, 45 table rows, 22 headings. The reference converts the inventory into per-class sections with per-character entries + comparison tables, then still spends its final section on synthesis: ref_91.md:205: "Crucially, the narrative consistently demonstrates that rank is not absolute. The protagonist Bronze Saints repeatedly defy the hierarchy…" — even at Insight weight 0.11 the reference closes with comparative analysis ("VI. Synthesis: A Universe Defined by Conflict and Hierarchy"). Breadth dominates: enumerated coverage of Bronze/Silver/Gold Saints, Marina Generals, Specters, God Warriors (headings list, ref_91.md).
- **Task 100** (AI & interpersonal relations; .29/.40/.16/.15): ref_100.md = 65,639 chars, 24 headings; the outline gives mechanisms their own top-level section ("4. Underlying Mechanisms: Psychological and Sociological Drivers of Change" with "4.1 Anthropomorphism, Parasocial Interaction…", "4.3 Theoretical Frameworks…") and a debate-framed conclusion ("6.1 Evaluating the Potential for Fundamental Change"). When Insight weight rises, the reference's mechanism/theory real estate rises with it.
- **Task 4** (gold + mind map, zh; .20/.38/.26/.16): ref_4.md is only 11,202 chars but 41 table rows in 22 headings — scenario-structured ("情景一：牛市延续 / 情景二：熊市修正 / 情景三：盘整阶段" = bull/bear/consolidation scenarios) with per-scenario support/resistance tables and a mind-map framework section ("思维导图框架指引") answering the format instruction. Density adapts: data task → tables dominate prose.
- **Task 73** (novice EFL teachers; Read weight 0.25 — highest in corpus): ref_73.md = 62,438 chars, 35 headings — the most finely sectioned of the set, with practice-first headings ("5. Practical Classroom Implementation: Strategies for Novice Teachers") and a keywords section ("10. Keywords for Indexing and Discoverability"). Audience adaptation is structural, not just tonal.
- **Task 51** (Japan elderly consumption; data-heavy): 63,118 chars, 32 table rows but only ONE markdown heading — long-form data narrative; shows reference formatting is not uniform and heading-sparse references exist (a beatable Readability surface on some tasks).
- EN reference length stats (ids 51-100): mean 69,500 chars, median 68,715, min 37,975, max 116,950 (computed from reference.jsonl). Beating the bar means competing against ~9,000-word, 30-heading, 2-table reports as the TYPICAL case.

---

# PART 2 — TARGET B: top-scorer teardowns

## 2.1 Leaderboard ground truth (fetched live, gradio config of muset-ai/DeepResearch-Bench-Leaderboard space, 2026-07-23)

GPT-5.5 (current) tab, top 10 Overall/Comp/Insight/Inst/Read: Cellcog Max 55.78/56.34/57.08/55.30/51.94 · WhaleCloud-DocChain 54.78/55.14/55.33/54.85/52.48 · Sapient Bodhi-DeepResearch 54.07/54.15/54.60/54.41/51.87 · Lunon 53.51/53.42/54.83/53.41/50.48 · Dalpha 53.10 · Sourcery 51.17 · **gemini-2.5-pro-deepresearch 49.98/50.01/49.92/50.22/49.58** · openai-deepresearch 47.84/48.05/46.69/49.29/47.62 · perplexity 43.05 · grok 41.22.
Gemini-2.5 (legacy) tab: DuMate/Qianfan-DeepResearch 58.03/59.48/**61.48**/53.87/54.34 · ZTE-Nebula 57.27/58.37/59.76/54.06/54.66 · iFlow-Researcher 57.08 · Zhipu Deep Research 57.06/58.15/60.14/53.47/53.88 · Xiaoyi 57.00 · WhaleCloud 56.81 · Cellcog Max 56.67/57.40/60.01/53.25/53.21 · … nvidia-aiq (Nemotron 3, GPT 5.2) 55.95/56.90/58.49/52.89/53.43 · AgentCPM/DualGraph-class open systems ~53-55 (DualGraph paper reports 53.08 RACE with GPT-5, arXiv 2602.13830 abstract).
FACT column (legacy tab, where present): gemini-2.5-pro-deepresearch **C.Acc 78.3 / E.Cit 165.34**; openai-deepresearch 75.01/39.79; langchain-ODR variants 32.94-34.74/21.06-22.44.

**The decisive read**: winners separate on Insight (Qianfan +11.5 above the 49.9 reference parity; every top-10 legacy system ≥58.5 Insight) and Comp (+7 to +9.5), while Inst (53-54) and Read (53-55) are compressed within ~1.5 points of each other. The scoreboard's dimensional spread independently confirms Phase-1's Strategic Implication #1: Insight is where the bar is beatable; Inst/Read are near-saturated. ZTE's README adds distribution data: "Every single query (100/100) scored above the expert-written reference" (github.com/Adlik/ZTE-Nebula-DeepResearch README.md) — winning is consistent, not variance-lottery.

## 2.2 Local top-scorer teardowns (task-72 head-to-head vs the same reference; results/race/*/raw_results.jsonl)

Caveat: local runs were made at different times; the judge model per-run is not recorded in raw_results.jsonl (only id/prompt/4 dims/overall), so cross-run deltas are indicative, not controlled. Dimension values are the published relative shares D_t/(D_t+D_ref).

| run | overall | comp | insight | inst | read | words | headings | table rows |
|---|---|---|---|---|---|---|---|---|
| fable5_scoped_calibration | **0.5065** | 0.4992 | **0.5131** | 0.4941 | 0.5262 | 3,071 | 11 | 14 |
| claude-3-7-sonnet-latest (t72) | 0.4316 | — | — | — | — | 2,873 | 26 | 0 |
| chatgpt_scoped_calibration | 0.4286 | 0.4164 | 0.4206 | 0.4163 | 0.4859 | 2,718 | 7 | 12 |
| champ_ourcorpus (OUR champion) | 0.3671 | 0.3924 | 0.3411 | 0.3717 | 0.3640 | 2,563 | 13 | 0 |
| polaris_best_compose_t72 | 0.3023 | 0.3391 | 0.2875 | 0.2775 | 0.2966 | 5,481 | 6 | 0 |
| cellcog_7703 (local file) | 0.2691 | 0.3167 | 0.2336 | 0.2847 | 0.2153 | 7,703 | 31 | 8 |

### fable5_scoped — the only local report to beat parity (0.5065; Insight 0.5131)
What it does (top_fable5_scoped_72.md):
- **Reconciliation-as-thesis**: TL;DR line 5: "The academic literature is genuinely divided **but reconcilable**…"; line 7: "Outcomes are a policy and design choice, not technological destiny: the decisive variable is whether AI is steered toward augmenting labour and creating new tasks or toward pure displacement." A committed organizing claim, stated up front — the Insight #8 move.
- **Named mechanism spine**: "1. The task-based framework unifies the debate. Nearly all rigorous work builds on the model in which jobs are bundles of tasks … Net labour-market outcomes depend on the balance between a *displacement effect* and countervailing *productivity* and *reinstatement* effects" (line 11).
- **Author-journal-number attribution in prose** (survives cleaning, feeds Inst #17/#18 AND Comp #5): "'one more robot per thousand workers reduces the employment-to-population ratio by 0.2 percentage points and wages by 0.42%'" (line 44), "Brynjolfsson, Li & Raymond … 'increases productivity … by 14% on average, including a 34% improvement for novice and low-skilled workers'" (line 32).
- **Identification-strength meta-analysis** (the second-order gate): "Methodological note: these positive findings rest on different foundations — conceptual/theoretical; observational IV panel studies; and randomised experiments. The experiments offer clean causal identification but on narrow, short-duration tasks" (line 36); "A recurring limitation is external validity: robots are tangible, rivalrous capital, whereas AI is intangible and non-rivalrous, so robot-era estimates may not transfer to AI" (line 52).
- **Table with a limitations column** (12 study rows, "Key Risks / Limitations" per row, lines 80-93) — a literature table that itself performs critical synthesis.
- **Conditional, evidence-tied recommendations**: "*Threshold that would change this:* the appearance of quasi-experimental studies detecting statistically significant aggregate wage/employment effects in LLM-exposed occupations would justify upgrading exposure findings to outcome claims" (line 98).
- **Tension resolution in Caveats**: "The optimistic and pessimistic findings are not necessarily contradictory: they often describe different margins … different technologies … and different time horizons" (line 114).
- Note: at 3,071 words it beat a 9,029-word reference — density of reasoning, not length, carried it.

### chatgpt_scoped (0.4286) — good epistemics, but answers a DIFFERENT prompt
Title "Generative AI and the Future Labor Market Before June 2023" (top_chatgpt_scoped_72.md:1) — it's a scoped GenAI-cutoff report scored against the task-72 reference, so Inst/Comp bleed (0.4163/0.4164) while Read holds (0.4859). Its transferable strengths: claim-then-caveat discipline ("Read narrowly, this is a productivity story; read more broadly, it suggests that generative AI can act as a mechanism for **faster skill transfer**", line ~9) and exposure-vs-outcome distinctions ("the early literature should be read as identifying the **direction and magnitude of potential labor-market pressure**, not as proving that a given percentage of jobs would disappear", line 7).

### claude-3-7-sonnet t72 (0.4316; full-100 mean 0.4218)
26 headings but serial-summary prose: "In the Fourth Industrial Revolution, STARA … is predicted to replace a third of the jobs" → "It is forecast that by 2025, 85 million jobs may be displaced" (top_claude-3-7-sonnet-latest_72.md, §3.1) — figures are dropped in without mechanism or reconciliation; sections like "4.1 Healthcare" are 1-2 sentences ("AI could have a substantial impact on healthcare through applications such as robots for surgery."). No tables, no bold, no named-author-journal pattern (one "Autor (2022)"). It loses everywhere roughly equally — the shape of "coverage without synthesis."

### cellcog_7703 (LOCAL file, 0.2691) — the degenerate-template counter-example
NOT the leaderboard Cellcog output (name aside, this is a local 7,703-word artifact). It shows what the judge punishes: verbatim boilerplate repeated dozens of times — "The unit labels are declared metadata and are not fully stated in the quoted findings, so this is an indirect comparison of employment across different units of analysis (economy versus firm) and is not directly comparable." appears 7 times consecutively in one section (top_cellcog_7703_72.md:98) and again at :148,:152,:170; empty section bodies ("### Evidence for displacement at the occupational level" has NO text, :84-85); citation-shaped filler ("The findings below rest on eight hundred and twenty verified passages", :13); off-topic evidence (sodium-reformulation CVD statistics, :60). Insight 0.2336, Read 0.2153 — the worst cells. Mechanical "synthesis templates" without content are actively toxic.

### champ_ourcorpus / polaris_best_compose — ours (see Part 5).

## 2.3 Leaderboard leaders' methods (web; shell curl)

**NVIDIA AI-Q (nvidia-aiq, 55.95 legacy tab)** — the single richest public artifact: the drb1 branch ships its full prompt stack (github.com/NVIDIA-AI-Blueprints/aiq, tree drb1; files saved aiq_*.j2).
- Architecture (README drb1): "an orchestrator that delegates to a planner (evidence-grounded planning via web search) and multiple researcher subagents (ensemble web search + academic paper search), then synthesizes findings into a final report."
- **A researcher subagent dedicated to mechanisms** (`mechanism_explorer.j2`): "1. **Find WHY things happen**: For every finding or claim encountered, search specifically for the causal mechanism … 3. **Trace causal chains**: When A leads to B, investigate the intermediate steps (A causes X, X enables Y, Y produces B) — do not accept 'A causes B' without understanding the pathway. 4. **Distinguish correlation from causation** … search for confounders, mediators, and moderators. 5. **Look for feedback loops and compounding effects**."
- Other specialists: comparator ("Extract shared dimensions for consistent comparison … Identify leaders per dimension and conditional rankings"), critic ("Your job is to find evidence that challenges the mainstream narrative … Challenge assumptions: What do most sources take for granted that may not hold universally?"), horizon_scanner (recency), generalist, evidence_gatherer.
- **Architect** (`architect.j2`): "When the user's prompt explicitly enumerates topics … those terms must appear **verbatim** as section or subsection headers"; "For open-ended topics, **organize by analytical dimensions rather than items** … This produces reports that compare and analyze rather than enumerate"; "Generate 24-32 queries covering DIVERSE analytical needs" typed as factual/causal/comparative/critical/trend; "Generate 24-32 constraints … 3. **Mechanism constraints**: 'Explain the causal mechanism behind [key finding]'".
- **Orchestrator writing rules** (`orchestrator.j2`): "When the topic involves multiple interacting forces, show how they compound and reinforce each other — don't just list them"; "Each section must introduce a new analytical layer the reader didn't have before"; "After each table, write 2-3 sentences interpreting the key pattern it reveals. A table without interpretation is inventory, not analysis"; "commit to a ranked answer with evidence. Specify under what conditions your ranking would change"; "Ground any forward-looking analysis in evidence from the report body. Connect an observed trend with an identified mechanism to reach a plausible projection"; "Target length: 5000-8000+ words"; mandatory Executive Summary, mandatory committed Conclusion ("Commit to a position or range … note what would change the answer"), optional "Forward-Looking Synthesis" section ("3-5 emerging trends, open questions, or predicted developments").
- **A benchmark-submission rewrite pass** (`frontends/benchmarks/deepresearch_bench/scripts/rewrite_report.py` — "Batch rewrite articles using Claude Opus"): 10 editor instructions that are a near-1:1 map of the RACE surfaces: "1. QUANTIFY EVERY EVALUATIVE CLAIM… 2. DEEPEN ENTITY AND CASE STUDY COVERAGE… 3. CUT SCAFFOLDING AND ELIMINATE REDUNDANCY [to] no more than 15-20% of total report length… 4. EXECUTE FRAMEWORKS WITH WORKED EXAMPLES… 5. GROUND RISKS IN REAL INCIDENTS ('the 2017 Equifax breach exposed 147 million records and resulted in a $700M settlement')… 8. BUILD CONSOLIDATED COMPARISON TABLES… 9. STRENGTHEN CAUSAL REASONING: Where the report makes macro-level claims … connect them to specific micro-level mechanisms… 10. IMPROVE SOURCE QUALITY FRAMING"; with citation-preservation ("Preserve ALL existing citations … EXACTLY") and a length cap ("approximately 50% longer than the original — no more, no less"). A ranked competitor literally runs a knowledge-injecting editorial pass tuned to the rubric. (Note for us: our operating rules ban post-gen edits — this is evidence of what competitors do, not a recommendation.)
- **ZTE-Nebula (57.27, #2 legacy)** — README (github.com/Adlik/ZTE-Nebula-DeepResearch): five modules: "1. **Planning**: A hierarchical mechanism and a rubric are introduced to guide the planning process … 2. **Research**: end-to-end trained sub-agents execute … in a Directed Acyclic Graph (DAG) manner … 3. **Research Draft**: reports written by sub-agents are deeply integrated, supplemented with necessary summaries, research analysis, and conclusions … 4. **Draft Optimization**: Each chapter is examined for comprehensiveness and factual correctness. Further research is triggered when necessary, and the draft is iteratively improved. 5. **Final Report**: after verifying that the document structure and citations comply with the required standards." Pattern: rubric-guided planning + per-chapter completeness audit + iterative re-research.
- **WebWeaver (Alibaba Tongyi, arXiv 2509.13312)**: "dual-agent framework … The planner operates in a dynamic cycle, iteratively interleaving evidence acquisition with outline optimization to produce a comprehensive, **citation-grounded outline** linking to a memory bank of evidence. The writer then executes a **hierarchical retrieval and writing process, composing the report section by section** … targeted retrieval of only the necessary evidence from the memory bank via citations for each part … mitigates long-context issues and citation hallucinations" (abstract). Their RL result: "citation accuracy from a nearly unusable 25% to a reliable 85.90%" (§ analysis, arxiv.org/html/2509.13312v3). Outline evolves WITH evidence; writing is per-section against retrieved evidence only.
- **AgentCPM-Report (arXiv 2602.06540)**: "Writing As Reasoning Policy (WARP), which enables models to dynamically revise outlines during report generation. Under this policy, the agent alternates between **Evidence-Based Drafting** and **Reasoning-Driven Deepening** … outperforms leading closed-source systems, **with substantial gains in Insight**" (abstract). Mechanics: "our O₀ is intentionally sparse, consisting only of high-level section titles and brief writing intents … we enforce contextual consistency by conditioning retrieval queries on the accumulating narrative" (§2.2). Dose-response evidence: "performance increases steadily with deeper expansion and begins to plateau at around nine steps … both Comprehensiveness and Insight rise strongly with deepening, improving by nearly 6 points from shallow to sufficiently deep regimes" (§3.3.3, arxiv.org/html/2602.06540v1).
- **DualGraph (arXiv 2602.13830)**: "separates what the agent knows from how it writes. DualGraph maintains two co-evolving graphs: an Outline Graph (OG), and a Knowledge Graph (KG) … By analyzing the KG topology together with structural signals from the OG, DualGraph generates targeted search queries … reaches a 53.08 RACE score on DeepResearch Bench with GPT-5" (abstract). Knowledge-gap detection is made explicit rather than left to the LLM "to implicitly infer knowledge gaps from the outline alone."
- **DRAGged into Conflicts (arXiv 2506.08500)**: taxonomy of inter-source knowledge conflicts + finding that "LLMs often struggle to appropriately resolve conflicts between sources. While prompting LLMs to explicitly reason about the potential conflict…" — the research basis for the consensus/disagreement surface (Insight #8's "consensus, debate, and uncertainty").
- **NOT FETCHABLE** (stated per brief, not invented): the HF raw-outputs dataset `Ayanami0730/deep_research_bench` returns 401 through this egress (also via hf-mirror) — actual task-72 winner reports (Qianfan/ZTE/Cellcog-real) could not be pulled; Baidu Qianfan-DeepResearch, Zhipu Deep Research, iFlow, Xiaoyi, WhaleCloud, Sapient Bodhi, Cellcog publish no method paper findable on arXiv (searches logged); their entries above rest on leaderboard numbers + linked product pages only.

---

# PART 3 — PER-SUB-ITEM WIN MAP (every SCORING_SPEC task-72 cell → the winning moves, with quotes)

Format: cell (eff. weight) → concrete moves, each grounded. "+0.045/dim-pt at parity" leverage per SCORING_SPEC I.9.

**INSIGHT #7 Mechanisms of restructuring (0.0800 — largest cell)**
1. Give mechanisms their own top-level section BEFORE evidence (ref: "2. Theoretical Lenses: Understanding AI's Mechanisms of Impact").
2. Name the framework + originator + core logic, then decompose into opposing forces with the net-effect condition (ref_72.md:31-36 displacement/reinstatement/productivity; fable5 line 11 "jobs are bundles of tasks").
3. End every mechanism paragraph with a derived implication ("This perspective suggests that the direction of AI innovation itself is a key determinant…", ref_72.md:38) — the :256 "not a superficial listing" gate.
4. Model the mechanism as DYNAMIC (augmentation→substitution over time, ref_72.md:60; "so-so automation" boundary case, ref_72.md:34).
5. Pipeline embodiment: a dedicated mechanism-explorer subagent ("Trace causal chains … A causes X, X enables Y, Y produces B", aiq_mech.j2:43) + planner "Mechanism constraints" (aiq_architect.j2) + writer rule "explain mechanisms and causes, not just surface descriptions" (aiq_orch.j2:139).

**INSIGHT #8 Critical cross-industry synthesis (0.0800)**
1. State a reconciliation thesis up front ("genuinely divided but reconcilable", fable5:5) and use it to connect sections ("Where the research reveals a central argument or organizing insight, plan to use it to connect sections into a narrative", aiq_orch.j2:100).
2. After the sector tour, extract the cross-sector pattern in a dedicated passage (ref_72.md:147-149).
3. Explain WHY studies disagree — name heterogeneity drivers (geography/controls/sector/aggregation, ref_72.md:73), different units/margins/technologies/horizons (fable5:114), exposure≠adoption≠impact (fable5:19).
4. Dedicated consensus/disagreement sections with both poles argued (ref_72.md 8.1/8.2; four named debates).
5. Never fake it with templates: cellcog_7703's repeated "not directly comparable" boilerplate scored Insight 0.2336 — the anti-pattern.

**INSIGHT #9 4IR integration (0.0480)**: define 4IR vs prior revolutions at the top, then USE the GPT/implementation-lag logic to explain empirical puzzles (ref_72.md:7,100,202: "the economic impact of general-purpose technologies (GPTs) like AI often materializes with significant lags").

**INSIGHT #10 Emergent themes / novel perspectives (0.0640)**: coin explicit higher-order themes after evidence blocks — "not predetermined by the technology itself" (ref_72.md:98), the human-skills paradox (:184), the slow-down-vs-accelerate policy dilemma (:257), populism linkage (:172). Fable5's "skill compression / democratization of expertise" framing and "Exposure ≠ realised impact" (fable5:15,19) are the same move. Writer rule: "What tensions or trade-offs does the evidence reveal? … These insights should form the analytical backbone" (aiq_orch.j2:99).

**INSIGHT #11 Implications & future agendas (0.0480)**: a full policy section + a research-gap section with 8 concrete gaps (ref_72.md sections 7, 8.3); recommendations tied to identified mechanisms with change-conditions ("Specify under what conditions your ranking would change", aiq_orch.j2:72; fable5:98 "Threshold that would change this"). Forward-looking content must be grounded: "Connect an observed trend with an identified mechanism to reach a plausible projection" (aiq_orch.j2:73).

**COMP #2 Breadth of restructuring dimensions (0.0725)**: one section per enumerated aspect (creation/displacement/transformation/skills/wages/productivity each get 300-900 words in ref); enumerate the rubric aspects pre-writing (SCORING_SPEC Part V #2 "pre-enumerable checklist"); planner-level: "When the user lists items to cover, cover each one" (aiq_orch.j2:138).
**COMP #3 Industry scope (0.0725)**: 8+ named industries, each with application AND labor consequence, then a common-patterns subsection (ref_72.md §4, 4.4). Architect: dimensional organization for the analysis + per-entity coverage checks; rewrite pass "check whether major well-known entities … have been omitted … err on the side of inclusion" (aiq_rewrite.py instruction 2).
**COMP #4 Disruption scale (0.0435)**: explicit speed/scale/transformative-potential passages + a whole pace-and-scale debate section (ref_72.md:7, §6).
**COMP #5 Literature depth (0.0435)**: a study-summary table with author/year/journal/methodology/findings columns (ref Table 1) or with a limitations column (fable5 table); precise effect sizes inline (0.39pp/0.77%, 14%/34%, 55.8%).
**COMP #6 Balance (0.0290)**: install promise-vs-peril duality as the report's declared central tension (ref_72.md:19), then formalize optimist/pessimist/nuanced (ref §6.1).

**INST #12-#16 (0.0250-0.0500)**: echo prompt keywords verbatim in title + headings ("must appear verbatim as section or subsection headers", aiq_architect.j2; ref title = prompt restated + "A Literature Review"); every prompt topic owns a heading; genre re-anchored in conclusion (ref_72.md:274).
**INST #17 journal-only (0.0375) & #18 English-only (0.0250)**: post-cleaning the ONLY carriers are (a) explicit in-prose claims ("This review of high-quality journal articles…", ref_72.md:274), (b) author-year-journal attributions in prose/tables ("Acemoglu & Restrepo (2020, JPE)"; fable5's "in a widely-cited *Journal of Economic Perspectives* essay"), (c) source-policy statements ("draws exclusively on peer-reviewed journal articles… admits only articles published in English" — cellcog_7703:7, the one thing that file did right, Inst 0.2847 was its second-best dim), (d) honest exclusion notes (ref_72.md:127; fable5:109 "Webb was subsequently withdrawn and is flagged as a working paper").

**READ #19 L1 (0.0280)**: precise academic register with attributed hedging ("Some analyses suggest…") but committed section-closing verdicts.
**READ #20 S1 (0.0280)**: numbered 2-level hierarchy; roadmap intro; synthesizing conclusion (ref outline); AgentCPM: sparse-then-deepened outline; architect: "2-5 subsections per top-level section", no generic titles.
**READ #21 S2 (0.0210)**: explicit inter-section transition sentences (ref_72.md:64,85,153).
**READ #22 P1 anti-serial-summary (0.0210)**: organize paragraphs by claim with multi-source support (ref_72.md:87); "Synthesize insights across sources rather than summarizing each separately" (aiq_mech.j2:56); "Researcher outputs are your raw material, not your template" (aiq_orch.j2:129). Claude-3-7's serial-summary shape (0.4218) vs fable5's claim-led shape (0.5065) is the local A/B.
**READ #23 D1 (0.0140)**: labeled tables + interpretation ("After each table, write 2-3 sentences interpreting the key pattern", aiq_orch.j2:67); numbers always followed by meaning ("Follow every significant data point with what it means and why it matters", :71).
**READ #24 F1 (0.0140)**: bold key terms (ref: 119 bold spans), consistent table formatting, "Table N:" captions.
**READ #25 A1 (0.0140)**: define every framework at first use (ref defines 4IR/SBTC/RBTC/J-curve); audience-targeted depth ("A researcher needs methodology sections; an investor needs risk and return comparisons", aiq_architect.j2:52).

**FACT surfaces (#26-#30 Fable / #40-52 Sol)**: the leaderboard's FACT champion is the reference generator itself — gemini-2.5-pro-deepresearch E.Cit 165.34 at C.Acc 78.3 vs openai-deepresearch's 39.79 at 75.01 (lb.html): at near-equal precision, E.Cit is a 4× VOLUME game — many unique inline statement-URL pairs. WebWeaver's fix for precision was structural: retrieve-only-cited-evidence per section during writing ("targeted retrieval of only the necessary evidence from the memory bank via citations for each part … mitigates … citation hallucinations", abstract), lifting citation accuracy 25%→85.9%. AI-Q enforces extractable form at the subagent level: "Use [1], [2], [3] format … Every factual claim must have a numbered citation. MANDATORY Sources section … [N] Source Title: URL" (aiq_mech.j2:96-97) — i.e., inline-marker + URL-resolvable discipline is prompted into every research unit, satisfying extract.py:51's in-text-location requirement.

---

# PART 4 — CROSS-REPORT PATTERNS, RANKED BY APPARENT IMPACT

1. **Deduction appended to description** (drives both 0.0800 Insight cells; the single biggest visible difference between winners and mid-scorers). Winners end evidence paragraphs with derived implications, coin named higher-order themes, and state reconciliation theses. Evidence: ref_72's "this implies/suggests" cadence (:38,:98,:100,:147,:172,:184,:207,:257); fable5's TL;DR thesis + 0.5131 Insight vs claude-3-7's implication-free serial summary at 0.4218; AgentCPM's Insight gains from "Reasoning-Driven Deepening"; leaderboard Insight spread (61.5 top vs 49.9 parity) being ~2× the Inst/Read spread.
2. **Mechanism-first architecture**: an early theory/mechanism section that the rest of the report keeps reusing (ref §2 feeding §3-§8; AI-Q's dedicated mechanism_explorer + "Mechanism constraints"; AgentCPM/WebWeaver interleaving reasoning with drafting). This simultaneously feeds Insight #7/#9 and structures P1/S1.
3. **Explaining disagreement instead of reporting it**: name WHY studies diverge (units of analysis, identification, sector, era, exposure≠outcome) and give consensus/debate/uncertainty their own sections (ref_72.md:73,81,291-294; fable5:36,52,114; DRAGged: models must "explicitly reason about the potential conflict"). This is the #8 cell plus Comp #5 credit in one move.
4. **Rubric-shaped coverage audit before/while writing**: enumerate required dimensions/industries and verify each is substantively covered (ZTE "Each chapter is examined for comprehensiveness … further research is triggered"; AI-Q "Structured Constraint Review: SATISFIED/PARTIALLY/UNSATISFIED" per constraint; architect's 24-32 acceptance-criteria constraints; NVIDIA rewrite instruction 2 err-on-inclusion). Comp cells are checklists — winners literally run them as checklists.
5. **Prompt-echo structure**: task keywords verbatim in title + section headers; genre named; every listed item covered (aiq_architect.j2 "verbatim as section or subsection headers"; ref title/headings; aiq_orch.j2:135 "The reader — and evaluator — will look for direct correspondence"). Cheap, near-full Inst credit (SCORING_SPEC Part V #3).
6. **Evidence density with interpretation**: precise numbers inline, each followed by its meaning; study tables with methodology/limitations columns; worked examples instead of framework descriptions (ref Table 1; fable5's 12-row table; aiq_orch.j2:67,71; NVIDIA rewrite 1/4/5). Feeds Comp #5, Read D1, Insight logical-coherence.
7. **In-prose source-quality signaling**: author-year-journal attribution + explicit source-policy sentences + flagged exclusions, because bibliographies are stripped before judging (ref_72.md:274,:127; fable5:44,50,109; cellcog_7703:7). The only route to Inst #17/#18's 0.0625.
8. **Calibrated commitment**: hedge with attribution, then still commit ("commit to a ranked answer with evidence. Specify under what conditions your ranking would change", aiq_orch.j2:72; ref's committed conclusion; fable5's threshold-conditioned recommendations). Evasion loses Insight logical-coherence credit; unhedged overclaiming loses to the critic-informed reference.
9. **Length is necessary but nowhere near sufficient**: winners are long (ref ~9k words; AI-Q targets "5000-8000+"; AgentCPM +6 Comp/Insight from deepening to ~9 steps, plateau after), but polaris_best_compose (5,481 w, 0.3023) and cellcog_7703 (7,703 w, 0.2691) both lose badly to fable5 at 3,071 words, and every added section must add "a new analytical layer" (aiq_orch.j2:66) — repetition and filler are actively punished.
10. **Anti-pattern (confirmed locally)**: templated synthesis boilerplate, empty sections, repeated sentences, off-topic evidence — cellcog_7703's 0.2691 with Read 0.2153. Robotic "critical-synthesis phrases" without content score worse than plain serial summary.

---

# PART 5 — WHAT WE DO DIFFERENTLY (brief; deep gap audit is Phase 3)

Our champion (champ_ourcorpus, 0.3671; Insight 0.3411) vs the winners' habits:
1. **Statistic-stitching without implication**: "Machine learning approaches have been applied to model these outcomes, with one analysis reporting an R² of 0.9325 indicating that XGBoost captures the majority of variability" (top_champ_ourcorpus_72.md, Introduction) — numbers appear without a "so-what"; almost no paragraph ends with a derived implication (Pattern 1 missing).
2. **Orphaned/duplicated sentences**: "Between both cases, this implies a difference in better employment of 22% in the next three years" opens a section with no antecedent; "By 2026, jobs that require social and cognitive skills … most common in the job market" appears twice in consecutive sentences — redundancy the winners' "every sentence must contribute new information" rule (aiq_orch.j2:141) exists to prevent.
3. **Thin mechanism spine**: our "Theoretical Frameworks" section cites SBTC and four-group taxonomies but never decomposes displacement/reinstatement/productivity or states a net-effect condition, and later sections don't reuse the framework (Pattern 2 missing).
4. **Anonymous evidence**: almost no author-year-journal in-prose attribution → weak carriers for Inst #17/#18 and Comp #5 (Pattern 7 missing; ref/fable5 do this pervasively).
5. **No tables, no bold** in champ_ourcorpus (0 pipe rows vs ref's 2 labeled tables) — Read 0.3640 with D1/F1 left on the table.
6. **polaris_best_compose** additionally kept the scoped-prompt structure (title literally starts "I am researching the impact of Generative AI…", 6 headings for 5,481 words) — heading-sparse, prompt-mismatched (Inst 0.2775).
Positives already in place: cross-study synthesis section exists ("Cross-Study Synthesis: Consensus and Divergence"), scope framing exists, span-grounding discipline exists ("Every quantitative claim is span-grounded to a cited source") — the skeleton of Patterns 3/4 without the analytic flesh.

---

# EXECUTIVE SUMMARY — highest-leverage grounded patterns

1. **The bar is a 9,000-word mechanism-first literature review that converts every evidence block into a deduction** — the task-72 reference wins its two 0.0800 Insight cells with a dedicated theoretical-lenses section (displacement/reinstatement/productivity + net-balance condition, ref_72.md:31-38) and a closing consensus/disagreement/gaps triad (ref_72.md:276-307), with "this implies/suggests" implications appended throughout (:98,:147,:172,:184,:257). Beating it means out-deducing it, not out-listing it.
2. **The scoreboard says Insight is where winners actually win**: at parity the reference generator scores 49.9; leaders hit 58.5-61.5 Insight and 57-59.5 Comp while Inst/Read compress to 53-55 (live leaderboard tables, lb.html). Every point of headroom is worth +0.045 normalized per dimension point at parity (SCORING_SPEC I.9).
3. **Winners engineer the Insight cells into their pipelines**: NVIDIA ships a mechanism-explorer subagent ("Trace causal chains … do not accept 'A causes B' without understanding the pathway"), typed causal/comparative/critical query mixes, mechanism constraints, and writer rules ("show how they compound … a table without interpretation is inventory, not analysis"); ZTE runs rubric-guided planning + per-chapter comprehensiveness audits with re-research; WebWeaver/AgentCPM interleave outline-revision with evidence-grounded per-section writing (AgentCPM: Comp+Insight rise ~6 points with deepening, plateau ~9 steps; explicit "substantial gains in Insight").
4. **Local causal evidence matches**: fable5_scoped beat the reference (0.5065, Insight 0.5131) at one-third its length via a reconciliation thesis, named-framework spine, identification-strength meta-analysis, limitations-column table, and threshold-conditioned recommendations; serial-summary claude-3-7 sits at 0.4218; our stat-stitching champion at 0.3671; degenerate synthesis-template filler at 0.2691. Density of reasoning ≻ length; templates without content are toxic.
5. **Post-cleaning, source constraints live only in prose**: winners carry Inst #17/#18 (0.0625 combined) via author-year-journal attribution, explicit source-policy sentences, and flagged exclusions — the reference's own "This review of high-quality journal articles…" plus Table 1's "(2020, JPE)"-style rows.
6. **FACT is a volume game at maintained precision** (E.Cit 165.3 vs 39.8 at ~equal C.Acc on the leaderboard), won structurally by citation-grounded outlines and per-section evidence retrieval (WebWeaver 25%→85.9% citation accuracy) and by prompting every research unit to emit inline-numbered, URL-resolved, claim-adjacent citations (AI-Q researcher output contract).
7. **One ranked competitor (NVIDIA, drb1 branch) openly runs a rubric-shaped Opus rewrite pass** (quantify claims, add missing entities, worked examples, named incidents, consolidated tables, micro-mechanisms, ≤20% scaffolding, +50% length cap) — direct evidence that the frontier treats RACE surfaces as an explicit editorial checklist. Our no-post-gen-edit rule means we must achieve the same surfaces pre-generation.
