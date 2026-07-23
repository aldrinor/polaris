# PHASE-2 ADDENDUM — Fable verdict: the SKIPPED above-reference top systems
Systems torn down here: Bodhi (#3), Lunon (#4), Dalpha (#5), Sourcery (#6) [GPT-5.5 tab], Xiaoyi (legacy 57.00).
All five task-72 reports fetched successfully from the leaderboard Space (curl, id=72 `article` field). This EXTENDS
COMPETITOR_TEARDOWN.md — nothing from its Parts 1-7 is repeated except where a new report confirms/refutes a ranked pattern.
Extracted articles cached at scratchpad/investigators/p2add/{bodhi,lunon,dalpha,sourcery,xiaoyi}_t72.md (line refs below
are into those files).

## INGESTION RECEIPTS (both mandatory files read IN FULL)
1. /home/polaris/wt/faithoff/docs/race_fact_initiative/SCORING_SPEC.md — **245 lines**
   - FIRST (:1): `# SCORING_SPEC — RACE + FACT — LOSSLESS consolidation of Sol + Fable (Phase 1)`
   - MID (:123): `(named-author/journal attribution); verification limited/run-dependent.`
   - LAST (:245): `replication (±0.027 noise, single-call judge).`
2. /home/polaris/wt/faithoff/docs/race_fact_initiative/COMPETITOR_TEARDOWN.md — **347 lines**
   - FIRST (:1): `# COMPETITOR_TEARDOWN — Phase 2, LOSSLESS consolidation of Sol + Fable`
   - MID (:174): `":322 exposure indices...upper-bound potential under scenarios, not forecasts"; forward-looking turns gaps into measurable`
   - LAST (:347): `synthesis with per-paragraph deductions — the exact substance Phase 3 must turn into wired, small-test-proven, generalized fixes.`

## AVAILABILITY (HF tree API, both dirs listed in full)
`data/raw_data/` (legacy, 30 files): xiaoyi_research_agent_0304.jsonl PRESENT. **NO zhipu file, NO iFlow file, NO ZTE file
exists in the legacy raw_data dir** (full listing checked; closest extras: baidu-qianfan-drs{,-pro}.jsonl, drb_cellcog{,_max},
kimi-researcher, doubao, tongyi, 1688AILab, deepinsight, deepsynth, ms_deepresearch, onyx, grep-v4, dr-tulu, RecallRadar,
TrajectoryKit, gensee, raaa, salesforce-air, tavily, thinkdepthai, claude-research, langchain×2, nvidia×2, kimi, openai,
perplexity, gemini). So the earlier [S] finding stands: Zhipu/iFlow task-72 reports are not fetchable from this Space — no claims made about them.
`data_gpt55/raw_data/` (10 files): WhaleCloud-DocChain_0612, bodhi, cellcog-max, dalpha-deepresearch, gemini-2.5-pro-deepresearch,
grok-deeper-search, lunon_full100_FINAL.submission, openai-deepresearch, perplexity-Research, sourcery. Note: `baidu-qianfan-drs-pro`
exists only in the LEGACY dir — the DuMate/Qianfan current-tab absence is real.

## STRUCTURAL SCOREBOARD (task-72 articles, measured)
| system | tab score (O/C/I/Inst/R) | chars | words | headings | table lines | bold | citation form | refs section |
|---|---|---|---|---|---|---|---|---|
| Bodhi | 54.07/54.15/54.60/54.41/51.87 | 41,791 | **4,361** | 50 | **0** | 88 | `[[n]](url)` inline, 105× | none (inline only) |
| Lunon | 53.51/—/54.83/—/50.48 | 96,707 | 11,476 | 65 | 24 | 237 | `[Title](url)` inline, 184× | `## References` **EMPTY** (:492) |
| Dalpha | 53.10 | 30,511 | **4,039** | 15 | **0** | 15 | `[n]`, 76× | 35 refs, ALL journal+DOI |
| Sourcery | 51.17 | 83,329 | 9,849 | 54 | 35 | 159 | HTML `<a href="#reference-n">[n]</a>`, 435× | 18 refs (mixed URLs) |
| Xiaoyi (legacy) | 57.00 | 161,723 | 19,095 | 44 | **292** | **953** | `[n]`, 368× (+~30× literal `[Blueprint State]`) | 81 refs under `参考文献：` |
Source jsonls: https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/raw_data/bodhi.jsonl ,
…/lunon_full100_FINAL.submission.jsonl , …/dalpha-deepresearch.jsonl , …/sourcery.jsonl ,
…/data/raw_data/xiaoyi_research_agent_0304.jsonl

════════════════════════════════════════════════════════════════════
## SYSTEM 1 — BODHI (current #3, 54.07) — the density existence proof
### (a) Outline (verbatim heading heads, in order)
Scope/assumptions → 1) Core conceptual frameworks (1.1 task-based, 1.2 GPT+lags, 1.3 strategic-mgmt/complements, 1.4 labor-process/
algorithmic control) → **2) Empirical measurement strategies** (2.1 O*NET/SML … 2.10 text-mining China — TEN methods) → 3) What the
evidence says (3.1 small-aggregate-vs-visible-firm … 3.5 direction of innovation) → 4) Industry-specific pathways (mfg/Industry 4.0,
radiology, finance, autonomous trucking, media/creative, professional+public) → 5) Firm/market reallocation → 6) Job quality/monitoring/
bargaining → 7) Institutions & policy → 8) Synthesis (8.1 convergence, 8.2 core debates, 8.3 open problems) → Concluding integration.
### (b) Big cells
- **Insight #7 (.0800)**: mechanism section FIRST and mechanically deduced. Every framework subsection ends in a bolded labeled
  clause — ":15 **Restructuring implication**: even when aggregate employment effects are small in the short run, firms may still be
  actively reorganizing work"; ":22 labor-market impacts may appear first as within-firm changes … and only later as sectoral
  reallocation". The spine is REUSED downstream, exactly the reference's §2→§3-8 move: ":122 a pattern consistent with GPT diffusion
  lags and within-firm reorganization preceding macro reallocation"; ":147 supporting the complementarity narrative from GPT and
  organizational-design perspectives".
- **Insight #8 (.0800)**: §8.1 four numbered convergence claims, §8.2 three debates each stated with BOTH poles and citations on both
  sides — ":295 The reviewed journal evidence supports both possibilities in different settings: strong AI skill premia and superstar
  concentration risks … alongside evidence of wage gains and restructuring toward creative/social jobs". BUT: the §4 sector tour has
  per-sector "Restructuring pathway" deductions and NO cross-sector matrix/table and no reconciliation-by-moderator paragraph after
  the tour → #8 is completed at debate level, not sector level. Consistent with Insight 54.60 < cellcog 57.08.
- **Comp #2 (.0725)**: coverage contract stated up front — ":3 persistent changes in **(i)** task composition … **(ii)** occupational
  and skill mix … **(iii)** hiring and training strategies, **(iv)** wage structures and bargaining power, and **(v)** market structure
  and geographic concentration" — then each dimension owns real estate (wages §3.2/§5.4, productivity §5.1, skills §2.4, displacement/
  creation §3.1/§3.3, market structure §5.2-5.3). This is Win-Map #3's "operationalize restructuring pre-writing" executed verbatim.
- **Comp #3 (.0725)**: six industries spanning regimes (physical mfg / regulated healthcare / finance / transport / creative / public),
  each closing with a derived "**Restructuring pathway**" clause (":183 front-office advisory and sales become more data-driven…;
  compliance/model risk functions expand"). Honest scope note performs the constraint: ":205 the research record here does not include
  extractable results … so claims must remain at the level of documented research focus."
- **Insight #10 (.0640)**: moderate — "AI divide" (:226), superstar reallocation (:221), job-quality/power as a restructuring channel
  (:240 "even absent job loss, AI-enabled monitoring can worsen job quality and shift power toward management"). No coined named themes
  at cellcog's "eight original syntheses" level.
### (c) Ranked patterns
1 deduction-appended ✔ (mechanical, labeled); 2 mechanism-first ✔; 3 explained-disagreement ✔ (§8.2 + ":129 This evidence is
correlational rather than a clean causal estimate"); 4 rubric-shaped coverage ✔ (the :3 contract); 5 prompt-echo ✔/partial (no title
H1 at all — report starts at "## Scope"; keywords in section heads); 6 in-prose source signaling: authors ALWAYS, journal names
almost never in prose (one: ":104 A 2025 Journal of Economic Behavior & Organization paper…"); epistemic labeling ✔ in prose
(Strength/Limitation pairs), no tier system.
### (d) NEW moves (not in COMPETITOR_TEARDOWN)
- **N1. The labeled-deduction template.** Pattern-1 turned into a visible recurring artifact: bolded "**Restructuring implication:**"
  / "**Interpretation:**" / "**Mechanism link:**" / "**Restructuring pathway:**" / "**Policy tension:**" after every evidence unit.
  The judge doesn't have to detect the deduction — it's typographically flagged. (Reference does this implicitly; NVIDIA prompts it;
  nobody in the teardown SHIPS it as a label.)
- **N2. Measurement-strategies chapter as a first-class section** (§2, TEN methods, each with an explicit bolded "**Strength**/
  **Limitation**" pair, e.g. ":46 feasibility ≠ adoption; indices can become stale"). Hits lit-review form (#12) + literature depth
  (#5, methodology column as a whole chapter) + insight (method critique = second-order) in one structure. The reference's own
  weakness #1 (no methods) attacked directly.
- **N3. First-person evidence-boundary protocol**: ":4 Where the research record contains only bibliographic indications of a paper's
  existence (without extractable results), I either do not use it or explicitly limit claims to what is visible on the journal
  landing page." Epistemic discipline about the retrieval record itself, stated as policy and then performed (§4.6, :205).
### HOW A 4,361-WORD REPORT IS #3 (the density evidence)
- 50 headings / 4,361 words ≈ **87 words per heading unit**; each subsection is a closed loop: named study → precise number
  (":67 sizeable posted-wage premia (11% within firm; 5% within job title)"; ":238 monitoring slightly decreases job satisfaction and
  increases stress, finds no relationship with performance") → method appraisal → labeled deduction. Zero scaffolding sentences, zero
  serial summary, zero empty sections, zero tables-without-interpretation (zero tables at all).
- It spends words ONLY where the weights are: frameworks+measurement+synthesis ≈ the two .0800 cells + .0435 lit-depth; the price is
  Readability 51.87 — **its lowest dim, same signature as cellcog-max (51.94)**. Confirms Pattern 9 from the winning side: length is
  not the lever, per-paragraph inferential density is; and extreme density is paid for in Read, which at weight .14 is the cheap dim.
- FACT posture: `[[n]](url)` at claim sites = extractable form; every claim atomic with number+population+direction (surface #42).

════════════════════════════════════════════════════════════════════
## SYSTEM 2 — LUNON (current #4, 53.51; Insight 54.83; Read 50.48)
### (a) Outline
Title (verbatim prompt echo + "A Literature Review") → 2-para thesis intro → 1 Framework/Scope/Methodology (1.1 defining restructuring,
1.2 scope, 1.3 three research questions, **1.4 Source-Quality Rubric table**, 1.5 core constructs) → 2 AI as 4IR driver (2.1-2.4 incl.
"The Restructuring Thesis") → 3 Theoretical Mechanisms (task-based / automation-vs-augmentation / productivity+reinstatement / SBTC+
algorithmic mgmt) → 4 Employment (displacement/creation/transformation/net synthesis + summary table) → 5 Wages/premium/inequality →
6 Skills/redesign/careers → 7 Sectoral (9-row matrix + three REGIME groups) → 8 Geographic/cross-country → 9 Distributional groups →
10 Contested Findings (4 debates) → **11 Synthesis: Coupled-Mechanism Forward Verdict (11.2 Maturity Tiers)** → 12 Policy →
13 Limitations (**13.3 Falsifiers**, 13.4 agenda) → `## References` (EMPTY).
### (b) Big cells
- **#7**: four named mechanisms as "a coupled system" — ":108 whose relative strengths determine a net outcome that is theoretically
  ambiguous and therefore an empirical question"; timing asymmetry ":114 displacement is contemporaneous with adoption, while
  reinstatement depends on the slower emergence of new task categories"; an original micro-mechanism for augmentation dominance —
  ":126 The observed persistence of hybridization is not caution but arithmetic: the expected cost of machine error exceeds the wage
  of the human who catches it."
- **#8**: the strongest sector-synthesis architecture in the current tab. Sectors GROUPED BY BINDING CONSTRAINT (goods=capital
  economics; regulated cognitive=regulation/liability; light cognitive=exposure tracks change), 9-row matrix with a "Binding
  Constraint" column (:255-265), and explicit "**Cross-sector claim:**" paragraphs after each group — ":287 That difference in binding
  constraint, not a difference in technical exposure, explains why two high-exposure sectors realise change at such different speeds."
  Chapter 10 resolves each debate as a design artifact: ":371 The disagreement is not an empirical contest with a winner but a
  design-induced artifact"; ":377 governed by three choices the analyst makes before touching the data"; ":387 any study claiming to
  measure '4IR exposure' must report the robot and AI components separately or risk cancelling them into a spurious null."
- **Comp #2**: ":15 labor-market restructuring is the joint operation of displacement, creation, and transformation of tasks and
  occupations — not the arithmetic of net jobs" + chapters 4/5/6; productivity via GPT J-curve (2.3, 11.1).
- **#10 emergent (.0640)**: several genuinely coined second-order themes — the reshoring-incidence inversion ":317 This cross-border
  channel has the opposite geographic incidence to domestic displacement"; the surveillance paradox ":359 the same monitoring that
  subjects workers to surveillance also generates an auditable record that could protect them. The constraint is the symmetry of data
  access"; the access/impact diffusion decoupling ":100 Fast adoption metrics will repeatedly be mistaken for fast restructuring."
### (c) Ranked patterns
1 ✔ (every chapter opens with a bolded thesis sentence; nearly every paragraph ends in a derived clause); 2 ✔; 3 ✔✔ (systematized —
disagreement resolved by margin/statistic/period/design in FOUR debates); 4 ✔ (1.3 three research questions as a causal ladder);
5 ✔ (title is the prompt verbatim); 6 in-prose signaling MIXED: names journals occasionally ("Eurasian Business Review" via link
titles — but link titles are citation markers and likely STRIPPED by the cleaner; plain-prose journal naming is rare); epistemic
labeling ✔✔ (Maturity tiers).
### (d) NEW moves
- **N4. Weighted source-inclusion rubric TABLE** (:39-45, R-1 peer-review .30 / R-2 English .15 / R-3 Q1-Q2 .20 / R-4 relevance .20 /
  R-5 recency .15) + the **"signpost convention"** — ":47 Such seminal works are handled through a signpost convention — named and
  located in the literature but never cited as evidence for a load-bearing claim." Inst #17/#18 performed as a scored methodology
  artifact, beyond the reference's single :274 sentence.
- **N5. Falsifiers section** (13.3): three named falsifiers with checkability ranking — ":479 This is the most quickly checkable
  prediction, answerable now with existing cross-country data." Extends teardown Pattern 11 from gap-listing to refutation-conditions
  for the review's OWN thesis.
- **N6. Confidence-tier → policy-verb mapping** (11.2): Mature/Partial/Open tiers each bound to an action — ":411 commit on the mature
  tier … stage on the partial tier … hedge on the open tier". Epistemic labeling made decision-relevant.
- **N7. Validity envelope**: ":488 The review's forward verdict is a conditional one, valid within a stated envelope … strongest where
  its filters are least binding and weakest where they bind most."
- **N8. Measurement reflexivity as the insight engine**: the instrument critique IS the through-line — opening hook ":3 the share of
  US occupations judged 'highly exposed' to AI ranges from under 3% to more than 51% — a 3.6-fold divergence … the field cannot yet
  agree on the size of the phenomenon it studies"; recurring "when the ruler is made of the thing it measures" (:118, :154, :373,
  :435). One critique, reused to explain four different disagreements = cheap repeated Insight credit.
### Caveats that explain #4-not-#3
- **Compliance theater vs practice**: despite the rubric table, LOAD-BEARING claims cite NBER WPs (":138 NBER 32430 asks directly how
  AI will affect the skill premium and finds…"), arXiv, Pew, SSIR, a vendor site (":283 roughly 22% higher pay for AI-skilled nursing
  roles" ← theaimarketpulse.com), genre.com, jobsdata.ai, a SEC 10-K, a GitHub dataset. The signpost convention is repeatedly broken.
- **Read 50.48 = lowest of the top five**: 11,476 words of unrelieved bolded-dialectic prose, only 24 table lines, and a dangling
  EMPTY `## References` heading as the literal last line (:492-493) — an orphan structural artifact (teardown Win-Map #24 defect).
- FACT posture: `[Title](url)` = extractable form 4; but many URLs are blogs/vendor pages → C.Acc risk where pages drift.

════════════════════════════════════════════════════════════════════
## SYSTEM 3 — DALPHA (current #5, 53.10) — the compliance existence proof
### (a) Outline
Title → Executive Summary → 1 Intro: AI and the 4IR → 2 Conceptual Foundations → 3 From Computerization and Robots to AI → 4 AI as a
Distinct GPT → 5 Employment/Wages/Occupational Restructuring → 6 Skill Restructuring & Human-AI Complementarity → 7 Generative AI and
Knowledge Work → 8 Industry Variation (9 bolded industry paras) → 9 Algorithmic Management/Job Quality → 10 Distributional/Firm/
International → 11 Methodological Limitations → Conclusion → Sources (35 numbered journal refs with DOIs).
### (b) Big cells
- **#7**: §2 canonical three-effect decomposition (":29 the **displacement effect** … the **productivity effect** … the
  **reinstatement effect**") plus a meta-deduction about why the framework matters: ":29 This framework is crucial because it prevents
  the literature from collapsing into either technological pessimism or optimism." Mechanism reuse is present but lighter than
  Bodhi/Lunon.
- **#8**: the cleanest one-move explained-disagreement in the corpus — ":41 These findings are not contradictory; they measure
  different levels of adjustment. Local labor-market studies capture concentrated regional harms. Industry and cross-country studies
  capture productivity, price, output, and reallocation effects." Plus the exposure→adoption→impact ladder as its OWN limitations
  chapter: ":145 First, exposure is not adoption … :147 Second, adoption is not impact … :149 Third, task-level productivity is not
  the same as labor-market welfare." And a conclusion that maps evidence-strength to channel: ":161 The strongest displacement
  evidence comes from robotics and online freelance markets. The strongest augmentation evidence comes from generative AI experiments
  … The strongest restructuring evidence comes from vacancy studies, exposure measures, firm-level adoption research…"
- **Comp #2/#3**: all six restructuring aspects present but compressed; §8 covers NINE industries (mfg, customer support, software,
  professional services, creative/freelance, finance, healthcare, retail, education/public) in single bolded paragraphs each, with an
  honest gap note ":115 strong claims about employment and wages in these sectors require more journal evidence."
- **#10 emergent**: modest — ":79 The emerging conclusion is that AI changes the meaning of skill. Some experience-based knowledge
  becomes embedded in tools, helping novices"; jagged-frontier as judgment-revaluation (:77). No coined themes, no tables (0), 15 bold.
### (c) Ranked patterns
1 ✔ (implicit, per-paragraph "the implication is clear:" :31); 2 ✔; 3 ✔ (:41, :91 "platform labor markets adjust faster … should not
be mechanically generalized"); 4 ✔ light; 5 ✔ (":19 This review therefore treats labor-market restructuring broadly. It includes
changes in employment, wages, occupational composition, task content, skill demand, productivity, job quality, worker autonomy,
surveillance, firm organization, and industry structure."); 6 **in-prose source signaling: the only system with GENUINE end-to-end
compliance** — ":19 It cites only English-language journal articles and distinguishes direct AI evidence from broader automation and
robotics evidence"; ":159 The high-quality journal literature supports a clear but nuanced conclusion"; all 35 refs are real journal
articles with DOIs (QJE, AER×2, JPE, JEP×3, REStat, JEEA, Economic Policy×2, Labour Economics×2, SMJ, JOLE, PNAS, Science×2, OrgSci×3,
QJE, ManSci×2, JEBO, AoM Annals, Big Data & Society, WES, MISQ, JFE, ISR, Research Policy, JEMS). Bibliography is stripped for RACE,
but the prose claims + wall-to-wall author-year attribution carry it; for a HUMAN-STYLE audit it is airtight.
### (d) NEW moves
- **N9. Evidence-provenance typing as a stated discipline**: ":19 distinguishes direct AI evidence from broader automation and
  robotics evidence" — then actually does it (":27 These studies are not direct evidence on modern generative AI, but they provide
  the core logic"; ":37 Robots are not equivalent to AI, but they provide a strong empirical bridge"). A compliance-adjacent honesty
  device the teardown doesn't list: label the evidential ROLE of each literature block (direct / bridge / background).
- **N10. Channel-attributed conclusion** (:161): closing paragraph assigns each conclusion to its strongest evidence family — a
  one-paragraph evidence map in prose.
### Verdict on the shape
4,039 words / 15 headings / no tables at 53.10 = second density existence proof, and the pattern-minimal one: it wins on clean
synthesis + perfect source discipline + explained disagreement, WITHOUT scenario sections, epistemic tiers, matrices, or labeled
deductions. The floor for top-5 is lower than the teardown's "~9,000-word bar" implies — on the CURRENT judge, ~4k flawless words
beats 9-11k flawed ones (Lunon 11,476 is only +0.41 above it; Sourcery 9,849 is 1.93 BELOW it).

════════════════════════════════════════════════════════════════════
## SYSTEM 4 — SOURCERY (current #6, 51.17) — the generic-template ceiling
### (a) Outline
Title → **Table of Contents** (anchor links) → Executive Summary → **Key Questions Answered** (4 direct Q&A) → Core Findings (13 subs)
→ Contradictions & Debates (7 named tensions) → Deep Analysis (10 subs) → Implications (5 audiences) → Future Outlook (Optimistic/
Base/Pessimistic, each with a Confidence paragraph) → Unknowns & Open Questions (13 numbered) → **Evidence Map** (21-row table:
Theme | Strongest | Moderate | Weak/Absent) → References (18).
### (b) Big cells
- **#7**: three-forces section (:98-108) + "so-so" technologies executed well — ":272 technologies with very high productivity gains
  generate enough surplus to increase labor demand through the productivity effect, while 'so-so' technologies displace workers
  without generating large productivity gains, making them the most threatening category for labor."
- **#8**: a dedicated Contradictions chapter that RESOLVES — ":292 These findings are not necessarily contradictory—they may reflect
  different levels of analysis … The resolution is that AI can be a net complement in aggregate while being a severe substitute for
  particular occupations and demographic groups"; ":296 driven primarily by divergent assumptions about task coverage, diffusion
  speed, and complementary investment rather than conflicting empirical data."
- **#10 emergent**: its best cell — "The Shifting Nature of Reinstatement" is a real second-order find: ":359 Before 1987:
  Reinstatement was associated with *lower* demand for skills … :360 After 1987: Reinstatement itself became *skill-biased* …
  :362 both displacement and reinstatement now reinforce rather than offset each other"; plus welfare-negative new tasks (":353
  AI-generated tasks … may represent as much as 2% of GDP but reduce welfare by 0.72%") and the career-ladder paradox (:174).
- **Comp #2**: partial — wages/displacement/productivity saturated with numbers; SKILLS thin; job-quality/algorithmic-management
  ABSENT entirely (no Kellogg/algorithmic-control strand at all).
- **Comp #3 industry scope (.0725): the visible failure.** Self-confessed: ":330 **Confidence assessment**: The sectoral evidence
  remains thin. Source 4's working paper acknowledges no industry-level variation analysis … No source provides AI-specific sectoral
  breakdowns"; ":457 Sectoral heterogeneity: No source provides AI-specific sectoral analysis…" There is no sector tour at all —
  sector content is two paragraphs plus DSGE aggregates. On a prompt whose title says "industry-level disruption", this forfeits
  Comp #3 (.0725) AND Inst #16 various-industries (.0375).
- **4IR grounding (Comp #1/Insight #9)**: near-zero — 4IR appears in the title and one sentence (:328); no 4IR definitional section.
### (c) Ranked patterns
1 ✔ (numbers always followed by meaning, e.g. ":157 The 38% decline in new skills … suggests that generative AI not only reduces
current labor demand … but actively constrains their future evolution"); 2 ✔ partial (framework first, but mechanisms restated rather
than reused); 3 ✔✔ (whole chapter); 4 ✘ — this is the differentiator: the outline is a GENERIC deep-research template
(Core Findings / Deep Analysis / Unknowns), NOT rubric/prompt-shaped; prompt keywords don't own headings; 5 ✘ (only the title echoes);
6 source signaling WEAK: claims only ":54 18 English-language academic sources" (never "journal"), and refs include a **Medium post**
(ref 9), a law-center blog (ref 8), NBER/HBS/World Bank/BIS working papers, arXiv — the weakest compliance claim + weakest practice
in the current tab. Epistemic labeling ✔✔ (Evidence Map + per-scenario Confidence + ":330 Confidence assessment" blocks).
### (d) NEW moves
- **N11. The Evidence Map artifact** (:487-509): a 21-row table grading every theme by Strongest/Moderate/Weak-Absent evidence with
  citations in cells — epistemic labeling promoted from sentence tags to a dedicated closing artifact. (Extends teardown Pattern
  "epistemic-label protocol" beyond cellcog's four inline tags.)
- **N12. Scenario triptych with per-scenario confidence** (:435-451): Optimistic/Base/Pessimistic each ending "**Confidence**:
  Low-to-moderate…" with the enabling conditions named — forward-looking-but-falsifiable in scenario form.
- **N13. Deep source-mining as a density strategy**: only 18 sources but 435 citation marks — Sources 5/15/16/18 are mined for
  10-20 distinct atomic quantitative claims each (propagation-matrix diagonal 0.84, −1.65 slope (SE 0.10), per-era displacement/
  reinstatement rates 0.49%/0.425% vs 0.55%/0.345% p.a.). Good for FACT E.Cit (many facts per URL = surface #49), but starves
  breadth cells — the score says the trade loses on this rubric.
### Verdict on the shape
Sourcery is the cautionary twin of Bodhi: similar per-paragraph density, orthogonal allocation. It shows that **the generic
deep-research house template (ToC/Key-Questions/Deep-Analysis/Unknowns/Evidence-Map) under-scores a rubric-shaped outline by ~3 pts**
even when insight moves are competent — the missing sector tour, missing 4IR grounding, missing job-quality strand, and weak
source-class compliance are exactly the cells the criteria list pre-enumerates.

════════════════════════════════════════════════════════════════════
## SYSTEM 5 — XIAOYI (legacy tab, 57.00) — the saturation strategy
### (a) Outline
`# 人工智能与劳动力市场重构：基于文献的系统性评估` (CHINESE H1 on the English task) → Abstract → 1 Conceptual Foundations (1.1-1.4 incl.
"Generative AI and the Revision of Classical Theory") → 2 Displacement & Automation Risks (2.1 cross-country econometrics …
2.3 ChatGPT natural evidence … 2.4 sector displacement) → 3 Creation/Augmentation/Productivity → 4 Industry-Specific Restructuring
(mfg / professional-business / healthcare+education / agriculture+creative / platform-gig) → 5 Distributional Consequences →
6 Workforce Adaptation → 7 Policy (portable benefits / EU AI Act / comparative high-income-vs-developing) → 8 Methodological Advances
(8.1 identification generations, 8.2 real-time assessment, 8.3 consensus/controversies/gaps) → 9 Conclusions → `参考文献：` 81 refs.
### (b) Big cells
- **#7**: mechanism content everywhere and TABULATED — 4-framework comparison table with "Prediction for AI Era" and "Empirical
  Traction" columns (:68-73); an original mechanism: ":44 The launch of ChatGPT in November 2022 triggered an immediate 8% decline in
  apprenticeship vacancy searches among young workers … This **expectation shock** reveals that AI's labor market impact operates
  through **anticipatory adjustment channels** absent in prior technological transitions"; ":42 a **double displacement mechanism**:
  continued erosion of remaining routine tasks alongside novel penetration of expert, managerial, and creative domains."
- **#8**: comparative synthesis as MATRICES — US/Germany/China robot-elasticity table with an "Institutional Mediator" row (:275-280);
  explicit reconciliations: ":336 Healthcare's **liability exposure** paradoxically **protects human employment** by mandating
  professional accountability; education's **public good status and democratic control** generates **political resistance to
  automation** absent in market-driven sectors." §8.3 formalizes it: an "Active Controversies" table with Position A / Position B /
  Resolution Status columns (:859-864, e.g. "This time is different … Methodologically unresolvable; requires decades of outcome
  data") and an "Emergent Consensus" table with a Confidence column (:849-855).
- **#10 emergent**: several coined — the abstract's organizing insight ":5 AI disrupts human capital accumulation pathways rather
  than displacing incumbents"; ":712 a 'measurement arms race' where the validity of findings decays with the publication lag";
  ":875 AI agent labor market participation … addresses the fundamental category error of treating AI exclusively as
  technology/capital."
- **Comp #2/#3**: the most complete coverage of any system reviewed in either phase — every restructuring aspect + EIGHT sector
  chapters each with its own schema table + platform/gig chapter with a traditional-vs-algorithmic control comparison table
  (:369-376). 292 table lines, all with surrounding interpretation.
### (c) Ranked patterns
1 ✔; 2 ✔; 3 ✔✔ (tabulated); 4 ✔ (every section closes coverage explicitly); 5 ✘/✔ — **title violates English/prompt echo** (Chinese
H1, `参考文献` footer) yet legacy Gemini scored it 57.00 → legacy judge did not police heading language; DO NOT copy under GPT-5.5
without evidence. 6 source signaling: prose claims "peer-reviewed literature" (:916) but the 81 refs are ~half non-journal (IBM,
McKinsey, Brookings, OECD, arXiv, preprints, Semantic Scholar pages, bankunderground blog, Anthropic blog, maadvisor.com) — worst
practice in this addendum. Epistemic labeling ✔✔✔ (confidence columns + gap blocks).
### (d) NEW moves
- **N14. "Critical Evidence Gap" labeled block in EVERY section** (":186 Critical Evidence Gaps: Creative industries and education
  remain systematically understudied…", :208, :288, :452, :478, :503, :542, :569, :659) — converts each coverage boundary into
  Insight #11 credit (gap→research-implication) instead of a silent omission. A systematic protocol, not an ad-hoc limitation section.
- **N15. Consensus/controversy TABLES with Confidence and Resolution-Status columns** (§8.3) — the #8 cell rendered as an auditable
  artifact; likewise a "Critical Knowledge Gaps" table with a "Research Implication" column (:868-875).
- **N16. Methodological-generations genealogy** used twice (exposure indices 1st/2nd/3rd generation :137-148; identification
  strategies 1st/2nd/3rd generation :718-748) — literature depth narrated as an evolution with per-generation limitation, similar
  to Bodhi N2 but genealogical.
- **N17. ANTI-PATTERN — leaked pipeline placeholder**: the literal token **"[Blueprint State]"** appears ~30 times as a citation
  (":184 employment growth (+6.4% in legal services) … [Blueprint State]") — an unresolved internal reference that survived to
  submission. Legacy Gemini tolerated it at 57.00; under FACT it is unextractable (0 pairs), and under GPT-5.5 it is exactly the
  cellcog_7703-class citation-shaped-filler risk. Strong caution: saturation + density can mask artifact leaks from a judge, but
  we must not rely on that.

════════════════════════════════════════════════════════════════════
## CROSS-SYSTEM FINDINGS THAT EXTEND COMPETITOR_TEARDOWN (not in Parts 1-7)
**F1. Word count is UNCORRELATED with rank inside the current top-6.** Bodhi #3 @4,361w and Dalpha #5 @4,039w sandwich Lunon #4
@11,476w and beat Sourcery #6 @9,849w; WhaleCloud #2 is 7,580w and cellcog #1 is 16,910w. The teardown's Pattern 9 ("winners long")
needs an amendment: on the GPT-5.5 judge, the operative variable is closed-loop paragraph density (study→number→appraisal→deduction)
and rubric-cell allocation; ~4k flawless words with full cell coverage ≈ 54, and 9-11k words with cell gaps ≤ 53.5.
**F2. The #1/#3 Readability signature.** Both cellcog (51.94) and Bodhi (51.87) bottom out on Read; Lunon is even lower (50.48).
Extreme analytic density systematically costs 2-4 Read points and the winners accept the trade (Read weight .14, t72 .25 — still
the cheapest of the four). Fits our champion diagnosis: fixing Read #19/#21/#22 matters for us because we're at 0.36, but the
competitive ceiling does NOT require winning Read.
**F3. Inst #17/#18 differentiates when Insight compresses.** Within the current tab, rank tracks source-discipline quality:
Bodhi (strong claim + protocol + near-journal practice) > Lunon (rubric table but broken practice) > Dalpha (perfect practice,
fewer insight artifacts) > Sourcery (weak claim "academic sources", Medium/blog refs). Dalpha proves genuine compliance is
ACHIEVABLE (35/35 journal DOIs) — the teardown's "leaders violate journal-only" (Qianfan/ZTE/NVIDIA caveats) is a legacy-tab
phenomenon, not a law.
**F4. Epistemic labeling has escalated from tags to ARTIFACTS.** New inventory across these five: Evidence Map strength table
(Sourcery), maturity-tier→policy-verb mapping + falsifiers + validity envelope (Lunon), consensus/controversy tables with
Confidence/Resolution-Status columns (Xiaoyi), per-scenario Confidence paragraphs (Sourcery), per-section Critical-Evidence-Gap
blocks (Xiaoyi), Strength/Limitation pairs per method (Bodhi). These are all pre-generation-plannable structures.
**F5. The labeled-deduction template (Bodhi N1) is the cheapest implementation of teardown Pattern 1** — a writer rule
("end every evidence unit with a bolded `Implication:` clause") that makes the .0800-cell behavior verifiable by our own gates
AND visible to the judge.
**F6. Methods/measurement chapter is now table stakes.** 4 of 5 systems have one (Bodhi §2 ten methods, Lunon 1.4+13.1,
Sourcery two-dimensional-exposure + evidence map, Xiaoyi §8 three generations); the reference has none (its known weakness #1).
This is a standing beatable surface the teardown listed only as a reference weakness — the top systems already exploit it.
**F7. Judge tolerance for structural defects is real but not bankable**: empty References heading (Lunon, #4), ~30 leaked
"[Blueprint State]" placeholders (Xiaoyi, 57.00 legacy), zero tables (Bodhi #3, Dalpha #5). None were fatal; all violate our own
quality bars and FACT extraction; treat as noise the judges happened to forgive, not as license.
**F8. Generic deep-research templates lose to rubric-shaped outlines** (Sourcery vs everyone above it): ToC/Key-Questions/
Deep-Analysis/Unknowns headings don't echo the prompt, and template time crowded out the sector tour + 4IR grounding the criteria
pre-enumerate. Confirms teardown Pattern 5 by counter-example from a 51-point system.
