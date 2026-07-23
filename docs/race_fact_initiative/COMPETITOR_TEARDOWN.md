# COMPETITOR_TEARDOWN — Phase 2, LOSSLESS consolidation of Sol + Fable
Opus read BOTH full verdicts line-by-line (Sol 1148 ln, Fable 273 ln); both ingestion receipts verified against the
real Phase-1 files. Preserves every distinct point from both; [S]=Sol, [F]=Fable, [S+F]=both, deduping only literal
repeats. Raw verdicts: docs/race_fact_initiative/phase2_{sol,fable}_verdict.md. Grounded to file:line/URL; unknowns marked.
BOTTOM LINE [S+F]: the bar is a ~9,000-word MECHANISM-FIRST literature review that converts every evidence block into a
DEDUCTION. Beating it = out-deducing, not out-listing. Insight is where winners actually separate.

═══ PART 1 — TARGET A: the task-72 REFERENCE (RACE Overall = target/(target+reference), so this IS the bar) ═══
[F] reference.jsonl id=72: 69,284 chars, 9,029 words, 112 paragraphs, 33 headings (1 H1/8 H2/24 H3), 2 tables (18 pipe
rows), 119 bold spans, ZERO citations (pre-cleaned). Gemini-2.5-Pro DR, April 2025. [F] The generator
`gemini-2.5-pro-deepresearch` scores 49.98 Overall/49.92 Insight (GPT-5.5 tab), 49.71/49.45 (Gemini tab) — parity by
construction; every winner's margin is measured against THIS artifact. [S] structural descriptors: 309 lines, 56 prose
paragraphs, 18 table lines, ~215 sentence-proxy, 66 numeric-tokens, 160 hedge-tokens (NOT quality scores).

OUTLINE (in order) [S+F]: 1 Intro: AI/4IR/labor restructuring (1.1 define 4IR+AI role, 1.2 AI as catalyst) · 2 THEORETICAL
LENSES/MECHANISMS (2.1 task-based displacement/reinstatement, 2.2 SBTC/TBTC/RBTC, 2.3 substitute/complement/augment) · 3
Empirical effects (3.1 displacement/creation, 3.2 aggregate employment/wages/polarization, 3.3 cross-country) [Table 1:
8 study rows × 6 cols] · 4 Sectoral (4.1 mfg/logistics, 4.2 health/finance/transport, 4.3 creative/marketing/service, 4.4
evolving workforce needs) · 5 Wages/inequality/skills (5.1 labor share, 5.2 inequality, 5.3 skill demand) · 6 Debating the
future (6.1 optimist/pessimist, 6.2 moderators, 6.3 productivity paradox) · 7 Policy (7.1 reskilling, 7.2 safety nets, 7.3
tax/regulation) [Table 2: 6 policy areas] · 8 Conclusion (8.1 consensus, 8.2 disagreement, 8.3 gaps/future).
[S+F] Rubric-shaped without copying rubric wording: theory→evidence→sectors→distribution→debate→policy→synthesis. The
biggest cells each OWN top-level real estate: §2=Mechanisms(#7), §8.1/8.2=consensus/disagreement(#8), §8.3=future-agenda(#11).

HOW IT WINS THE TWO 0.0800 INSIGHT CELLS:
• #7 Mechanisms [S+F]: decomposes into opposing forces + net-effect condition, then a DERIVED implication.
  [F] ref:31-34 Displacement/Reinstatement/Productivity effects (+"so-so automation—displace workers but only marginal
  productivity"); :36 "net impact...depends on the dynamic balance"; the second-order gate (criteria_prompt:261 "beyond
  obvious...second-order effects") — :38 "the direction of AI innovation itself is a key determinant...and potentially a
  target for policy influence"; dynamic not static — :60 "augment...could lead to full automation...augmentation to
  substitution"; measurement-mechanism — :100 "temporal lag and scale mismatch...implementation lags inherent to GPTs...
  current aggregate statistics may not yet fully capture." [F] PATTERN: every mechanism paragraph ends with a
  "this implies/suggests" clause (the :256 "not a superficial listing" gate). [S] concrete output pattern: `AI capability →
  affected task → substitution/augmentation/control → firm response → output/demand/new tasks → employment/wage/skill/
  job-quality result`, moderators+time horizon at each arrow.
• #8 Cross-industry synthesis [S+F]: analyze heterogeneity, don't note it; extract cross-sector pattern after the tour;
  reconcile. [F] :73 names divergence drivers (geography/controls/sector focus/aggregation); :81 "does not offer a simple
  consensus...varies by technology/period/geography/level/methodology/outcome"; :147-149 cross-sector pattern + "unlike
  earlier waves...now directly affecting finance, healthcare, law, creative...more pervasive and rapid"; :291-294 (8.2) four
  named debates each with both poles. [S] the move is contrast+moderator+reconciliation, NOT sequential sector paragraphs;
  concrete pattern = sector×mechanism/outcome/evidence-strength/moderator matrix + 3-6 propositions. A table without the
  inference paragraph does not complete the cell.

OTHER CELLS (grounded):
• #9 4IR integration (.0480) [F]: :7 "fusion of physical/digital/biological...unprecedented speed and scale"; non-superficial
  :11 "requires consideration of these synergies and the overall technological system, rather than viewing AI in isolation."
  [S] use 4IR properties as explanatory variables (GPT/implementation-lag logic to explain empirical puzzles, :202).
• #10 Emergent themes (.0640) [F]: coins higher-order themes AFTER evidence — :98 "not predetermined by the technology...
  mediated by economic structure, institutional environment, policy choices"; :172 inequality→populism political-economy;
  :184 human-skills paradox (AI automates cognition yet elevates uniquely-human skills); :257 slow-down-vs-accelerate policy
  dilemma. [S] concrete: `Evidence A + Evidence B + moderator C → supported inference`, epistemically labeled.
• #11 Implications/future (.0480) [F]: §8.3 = 8 substantive research-gap bullets (:296-307, e.g. "reinstatement effect
  remains less understood"); §7 + Table 2 = policy. [S] each rec: mechanism-it-changes, population, trade-off, evidence
  strength, testable outcome.
• Comp #2 breadth (.0725) [F]: all six aspects own sections (displacement/creation=3.1; transformation=2.1-2.3; skills=5.3+
  4.4; wages=5.1; productivity=6.3, Productivity-Paradox with 5 candidate explanations :211-219); each 300-900 words. [S] the
  Productivity-Paradox links J-curve, "so-so automation", org complements, adoption bottlenecks.
• Comp #3 industry scope (.0725) [F]: §4 covers 8+ named industries with per-industry application AND labor consequence
  (:129 transport AVs threaten drivers + create remote-monitoring/maintenance/fleet tasks), then 4.4 common pattern.
• Comp #4 disruption scale (.0435) [F]: :7 speed/scale, :149 "more pervasive and rapid", §6 pace/scale debate. [S] triangulate
  exposure/realized/diffusion/horizon/system-reach; don't substitute one headline forecast.
• Comp #5 literature depth (.0435) [F]: Table 1 (:102-113) cols "Study(Author,Year,Source)|Technology|Geography|Methodology|
  Employment findings|Wage/Inequality findings" with PROSE-SAFE named attributions "Acemoglu & Restrepo (2020, JPE)",
  "Graetz & Michaels (2018, REStat)", "Damioli et al. (2021, Res Policy)" — HOW source-quality survives the bibliography
  strip; precise inline numbers :71 "each robot/thousand workers −0.39pp employment-to-pop, −0.77% wages... 50-70% of US wage
  structure change 1980-2016."
• Comp #6 balance (.0290) [F]: :19 promise-vs-peril "central tension explored throughout"; §6.1 formalizes optimist/pessimist/
  nuanced.
• Inst #12-16 [F]: title replays prompt "...A Literature Review" (:1); every prompt keyword is a top-level heading; :274
  "This review of high-quality journal articles reveals..." re-anchors genre.
• Inst #17/#18 journal/English (.0375/.0250) [S+F]: bibliography stripped ⇒ carriers = (a) explicit claim :274, (b) named
  author-year-journal in Table 1, (c) honest scope note :127 "(Available sources provided limited specific journal evidence
  ...healthcare)" — which itself performs the constraint.
• Read #19-25 [F]: S1 numbered 2-level hierarchy + roadmap intro + synthesizing conclusion; S2 explicit micro-transitions
  (:64 "Moving beyond theoretical frameworks...", :85 "Despite the mixed evidence...", :153 "profound consequences..."); P1
  claim-organized w/ studies as support (:87), NEVER "Paper A found...Paper B found..."; D1/F1 two labeled tables + 119 bold
  spans; A1 every framework defined at first use (4IR/SBTC/RBTC/"so-so automation"/J-Curve :216); calibrated hedging that
  still ends in committed syntheses. [S] reference median prose paragraph = 45 words, mean 57.6, max 168.

REFERENCE WEAKNESSES leaders improve [S]: 1 no reproducible methods (asserts "high-quality journal articles" :274 but no
databases/dates/inclusion/screening/counts); 2 uneven sector evidence (admits limited healthcare evidence :127); 3 some
sector prose still catalog-like (:121-139); 4 one incomplete table (blank "Key Supporting Sources" col :263-270); 5 no inline
citations survive (not a RACE defect; means FACT can't be shown from this artifact). [S+F] these are BEATABLE surfaces:
roadmap/abstract/exec-summary absent; journal-compliance thin.

REFERENCE ADAPTS FORM TO WEIGHTS (other entries):
[S+F] Task 91 (Saint Seiya inventory; .37C/.11I/.32Inst/.20R): [S] 68,011 chars, 9,585 words, 45 table lines, 37 hedges;
entity/class sections + repeated schema (rank/armor/technique/arc/fate) + comparison tables; STILL synthesizes after roster
(:93 "immense power does not equate to inherent virtue"→ class explores "duty, morality, betrayal, sacrifice"). [F] even at
Insight .11 closes with "VI. Synthesis: A Universe Defined by Conflict and Hierarchy" (:205 "rank is not absolute").
[S+F] Task 100 (AI & relationships; .29/.40/.16/.15): [S] 65,639 chars, 24 headings, 181 hedges; LITERAL roadmap (:19 "Section
2 defines...Section 3 examines...Section 4 delves into...mechanisms..."); concept defs+typology before claims; balanced
matrix Table 2; mechanism chapters (anthropomorphism/parasocial/CASA/cognitive-dissonance/trust/attachment/identity);
moderator synthesis (:125 effects vary by embodiment/frequency/traits/age/loneliness); emergent feedback-loop (:127); ontological
synthesis (:243-251). [F] when Insight weight rises, mechanism/theory real estate rises with it.
[F-only] Task 4 (gold+mind-map, zh; .20/.38/.26/.16): 11,202 chars but 41 table rows/22 headings — scenario-structured (bull/
bear/consolidation) w/ per-scenario support/resistance tables + mind-map framework section (answers the format instruction);
density adapts: data task → tables dominate. Task 73 (novice EFL; Read .25 highest in corpus): 62,438 chars, 35 headings —
most finely sectioned, practice-first headings + a keywords/indexing section; audience adaptation is STRUCTURAL. Task 51 (Japan
elderly consumption, data-heavy): 63,118 chars, 32 table rows but only ONE heading — heading-sparse references exist (a beatable
Readability surface on some tasks). EN reference length stats (ids 51-100): mean 69,500 chars, median 68,715, min 37,975, max
116,950 — beating the bar = competing against ~9,000-word/30-heading/2-table reports as the TYPICAL case.

═══ PART 2 — TARGET B: leaderboard ground truth + top-scorer teardowns ═══
LEADERBOARD (live, fetched 2026-07-23) [F, Overall/Comp/Insight/Inst/Read]:
GPT-5.5 tab: Cellcog Max 55.78/56.34/57.08/55.30/51.94 · WhaleCloud-DocChain 54.78/55.14/55.33/54.85/52.48 · Sapient Bodhi
54.07/54.15/54.60/54.41/51.87 · Lunon 53.51/…/54.83/…/50.48 · Dalpha 53.10 · Sourcery 51.17 · gemini-2.5-pro-deepresearch
49.98/50.01/49.92/50.22/49.58 · openai-deepresearch 47.84/48.05/46.69/49.29/47.62 · perplexity 43.05 · grok 41.22.
Gemini(legacy) tab: DuMate/Qianfan 58.03/59.48/61.48/53.87/54.34 · ZTE-Nebula 57.27/58.37/59.76/54.06/54.66 · iFlow 57.08 ·
Zhipu 57.06/58.15/60.14/53.47/53.88 · Xiaoyi 57.00 · WhaleCloud 56.81 · Cellcog 56.67/57.40/60.01/53.25/53.21 · NVIDIA-AIQ
(Nemotron-3, GPT-5.2) 55.95/56.90/58.49/52.89/53.43 · DualGraph-class ~53 (paper 53.08 w/ GPT-5).
FACT (legacy, where present) [F]: gemini-2.5-pro-deepresearch C.Acc 78.3 / E.Cit 165.34; openai-deepresearch 75.01/39.79;
langchain-ODR 32.94-34.74/21.06-22.44.
[S+F] THE DECISIVE READ: winners separate on INSIGHT (Qianfan +11.5 above 49.9 parity; every top-10 legacy ≥58.5) and Comp
(+7 to +9.5), while Inst (53-54) and Read (53-55) compress within ~1.5 pts. Scoreboard independently confirms Phase-1 SI#1:
Insight is where the bar is beatable; Inst/Read near-saturated. [F] ZTE README: "Every single query (100/100) scored above
the expert-written reference" — winning is consistent, not variance.

LOCAL HEAD-TO-HEAD (results/race/*/raw_results.jsonl; per-run judge not recorded → indicative) [F]:
| run | overall | comp | insight | inst | read | words | headings | tables |
| fable5_scoped | **0.5065** | .4992 | **0.5131** | .4941 | .5262 | 3,071 | 11 | 14 |
| claude-3-7-sonnet t72 | 0.4316 (full-100 mean .4218) | — | — | — | — | 2,873 | 26 | 0 |
| chatgpt_scoped | 0.4286 | .4164 | .4206 | .4163 | .4859 | 2,718 | 7 | 12 |
| champ_ourcorpus (OUR champion) | **0.3671** | .3924 | .3411 | .3717 | .3640 | 2,563 | 13 | 0 |
| polaris_best_compose | 0.3023 | .3391 | .2875 | .2775 | .2966 | 5,481 | 6 | 0 |
| cellcog_7703 (local file) | 0.2691 | .3167 | .2336 | .2847 | .2153 | 7,703 | 31 | 8 |
[S] structural comparison adds POLARIS faithoff_t72: 7,942 words, 14 headings, 14 prose paragraphs, median 608.5 w/paragraph,
199 sentence-proxy.

TOP-SCORER TEARDOWNS:
• cellcog-max (current #1, 55.78; Insight 57.08) [S]: 123,611 chars, 16,910 words, 592 lines, 50 headings, 241 prose paragraphs.
  Full outline incl. Abstract → Intro(scope/method/central-finding/eight-syntheses/roadmap) → Conceptual Framework(4IR+determinism
  critique, task/skill/prediction lenses, "inefficient automation", disciplinary bridge) → Three Empirical Eras(robots/software-
  AI/GenAI) → Sectoral heterogeneity → GenAI exposure&productivity → Cross-sector synthesis+table → Cross-cutting outcomes(wages/
  labor-share, inequality/gender, labor-process/autonomy, institutional mediation) → §5 "Contested Debates & Novel Insights"
  (8 named: routine-to-cognitive-inversion, freelance-population-paradox, skill-compression, autonomy-employment, Turing Trap,
  jagged frontier, gender reversal, Global-South informality buffer) → policy-from-mechanisms → limitations → conclusion. WINS:
  states evidence boundary/count ":7 approximately 96 English-language peer-reviewed journal articles"; ":9 Heterogeneity, not
  displacement, is the central peer-reviewed finding"; ":11 eight original syntheses, each epistemically tagged by evidentiary
  status"; ":51 4IR framing without mechanism is narrative, not explanation"; distinguishes extensive/intensive/labor-share
  margins (:218-224); EPISTEMIC-LABEL PROTOCOL — Established Finding / Emerging Pattern / Conceptual Argument / Analytical
  Hypothesis-Our-Synthesis (:258), and calibrated uncertainty ":282 No peer-reviewed study has yet tested these long-run
  predictions." RISK [S]: Readability 51.94 (its LOWEST dim) — 50 headings/592 lines impose search cost; low lexical hedging;
  contextual working-paper inclusion is still a source-class risk under "only journals."
• WhaleCloud-DocChain (current #2, 54.78) [S]: 59,282 chars, 7,580 words, 44 headings, 129 prose paragraphs, 35 table lines.
  Exec summary → 4IR → theory-evolution(SBTC→task→displacement/reinstatement→"Acemoglu Simple Macroeconomics 2025"→"bottom-biased
  technical change" emergent framework→cross-revolution comparison) → mechanisms → sector chapters → cross-industry MATRIX + FIVE
  moderators (task structure/demand elasticity/regulation/white-collar frontier/developing-economy) → a second table explaining
  divergent estimates answer DIFFERENT questions (exposure/task-productivity/local-employment/national-employment/wage/control,
  :254-267) → skills/policy/agenda → balanced challenges/opportunities → limitations. Better current Readability (52.48) than
  cellcog; novel syntheses less sharply epistemically separated.
• Qianfan/DuMate (legacy #1, 58.03; Insight 61.48) [S]: report 560,868 chars, 73,383 words, 1,516 lines, 98 headings, 109 table
  lines. ARCHITECTURE (official README): "An evolving DAG expands from coarse goals into fine-grained research actions, with
  reflection, re-planning, backtracking, and parallel branching"; outer Research Agent delegates to inner Searcher Agents each
  with its own planning loop; "Dynamically generated quality criteria act as test-time reasoning scaffolds for evidence-grounded
  synthesis and adaptive stopping." PRISMA-like methods chapter (databases/boundaries/selection/quality); sector synthesis
  explicitly "more than enumeration" (:596-639) deriving propositions (within-sector variation can exceed between-sector;
  institutions alter effects; upstream propagation; platform matching/control); final synthesis :1399 "not a single phenomenon
  ...but a family of institutionally projected configurations"; six consensus + persistent disagreements + emerging frontiers +
  ":1429 not technologically determined." COMPLIANCE CAVEAT [S]: claims journal-only but includes working papers/IMF/GitHub-blog.
• ZTE-Nebula (legacy #2, 57.27; Insight 59.76) [S]: report 253,301 chars, 32,794 words, 1,822 lines, 178 headings, 324 table
  lines. FIVE MODULES (README): 1 hierarchical planning guided by a RUBRIC+subtasks; 2 end-to-end trained subagents in a DAG;
  3 draft integration w/ added summaries/analysis/conclusions; 4 per-chapter comprehensiveness+factual audit that TRIGGERS more
  research; 5 final structure+citation verification. Opens with one-sentence thesis+abstract+reading guide; elevates 3 insights
  before the review (seniority-biased polarization; productivity-displacement coupling; policy-evidence asymmetry); industry
  chapter uses matrices/rankings/causal-chains/failure-modes ending in a "chapter insight"; closing answers seven subtasks one
  by one (:1684-1705) + audience-specific recs + limitations + best-practices + future horizons/observables/open-questions.
  COMPLIANCE CAVEAT: metadata explicitly includes "NBER Working Papers" — violates journal-only.
• NVIDIA-AIQ/Nemotron (legacy, 55.95; Insight 58.49) [S]: report 70,982 chars, 9,321 words, 428 lines, 47 headings, 43 table
  lines; unusually rubric-literal outline; six restructuring dimensions in a numbered list (:15-21); four tech channels (:25-32);
  mechanisms displacement/reinstatement/skill-bias/org-complements/diffusion-lags/institutional-mediation (:47-79, German-vs-US via
  works-councils/bargaining/apprenticeships); cross-industry matrix (channel/outcome/evidence-strength/mechanism/journal anchors,
  :282-297) + ":300 industries differ less in whether tasks are affected and more in how: substitution, augmentation, or control";
  ":322 exposure indices...upper-bound potential under scenarios, not forecasts"; forward-looking turns gaps into measurable
  research designs (:391-401). COMPLIANCE CAVEAT [S]: claims English-peer-reviewed-journals-only (:34-41) yet uses McKinsey/IFR/
  FDA/NHTSA/OCC/Gartner/Forrester/EU-legal in prose — violates "only".
  [F] NVIDIA AI-Q drb1 branch ships its FULL PROMPT STACK (richest public artifact, github.com/NVIDIA-AI-Blueprints/aiq tree drb1):
  orchestrator delegates to planner + multiple researcher subagents then synthesizes. `mechanism_explorer.j2`: "Find WHY things
  happen...Trace causal chains: A causes X, X enables Y, Y produces B — do not accept 'A causes B' without understanding the
  pathway...Distinguish correlation from causation...confounders/mediators/moderators...feedback loops and compounding effects."
  Specialists: comparator ("Extract shared dimensions...conditional rankings"), critic ("find evidence that challenges the
  mainstream narrative...Challenge assumptions"), horizon_scanner, generalist, evidence_gatherer. `architect.j2`: prompt-enumerated
  topics "must appear verbatim as section or subsection headers"; open-ended → "organize by analytical dimensions rather than
  items...compare and analyze rather than enumerate"; "Generate 24-32 queries" typed factual/causal/comparative/critical/trend;
  "24-32 constraints...Mechanism constraints: 'Explain the causal mechanism behind [key finding]'". `orchestrator.j2`: "show how
  they compound and reinforce each other—don't just list them"; "Each section must introduce a new analytical layer"; "After each
  table, write 2-3 sentences interpreting...A table without interpretation is inventory, not analysis"; "commit to a ranked answer
  ...Specify under what conditions your ranking would change"; "Connect an observed trend with an identified mechanism to reach a
  plausible projection"; target 5000-8000+ words; mandatory exec summary + committed conclusion; optional Forward-Looking Synthesis.
  `rewrite_report.py` (Batch rewrite w/ Claude Opus) — 10 editor instructions ≈ 1:1 the RACE surfaces: quantify every claim; deepen
  entity/case coverage; cut scaffolding to ≤15-20%; execute frameworks with worked examples; ground risks in real incidents
  ("2017 Equifax breach...147M records...$700M settlement"); consolidated comparison tables; strengthen causal reasoning (macro↔
  micro mechanisms); preserve ALL citations EXACTLY; length cap "~50% longer than original, no more no less." [F NOTE + S+F]: a
  ranked competitor literally runs a rubric-shaped post-gen Opus rewrite — but OUR no-post-gen rule means we must produce the same
  surfaces PRE-generation.

LOCAL COMPETITOR DETAIL:
• fable5_scoped (0.5065, only local to beat parity) [F]: reconciliation-as-thesis (TL;DR:5 "genuinely divided but reconcilable";
  :7 "Outcomes are a policy and design choice, not technological destiny"); named mechanism spine (:11 "jobs are bundles of tasks
  ...displacement vs productivity+reinstatement"); author-journal-number attribution in prose (:44 "one more robot/thousand −0.2pp
  employment, −0.42% wages"; :32 "Brynjolfsson,Li&Raymond...+14% productivity, +34% for novices"); identification-strength meta-
  analysis (:36 conceptual vs observational-IV vs randomised; :52 "robots tangible/rivalrous, AI intangible/non-rivalrous, robot-
  era estimates may not transfer"); table WITH a "Key Risks/Limitations" column (12 rows, :80-93); conditional evidence-tied recs
  (:98 "Threshold that would change this: quasi-experimental studies detecting significant aggregate wage/employment effects in
  LLM-exposed occupations"); tension resolution (:114 "not contradictory: different margins...technologies...time horizons"). Beat a
  9,029-word reference at 3,071 words — DENSITY of reasoning, not length.
• chatgpt_scoped (0.4286) [F/S]: answers a DIFFERENT prompt ("Generative AI...Before June 2023") → Inst/Comp bleed, Read holds
  (.4859); transferable: claim-then-caveat + exposure-vs-outcome distinction (:7).
• claude-3-7 (0.4316) [F]: 26 headings but SERIAL-SUMMARY prose (figures dropped without mechanism; "4.1 Healthcare" = 1-2
  sentences), no tables/bold, one "Autor(2022)" — the shape of "coverage without synthesis", loses everywhere ~equally.
• cellcog_7703 LOCAL file (0.2691, DEGENERATE counter-example, NOT leaderboard cellcog) [S+F]: verbatim boilerplate repeated
  (":98 'unit labels...not directly comparable' ×7 consecutively, again :148/:152/:170"), empty section bodies (:84-85), citation-
  shaped filler (":13 820 verified passages"), off-topic evidence (:60 sodium-reformulation/recidivism CVD stats). Insight 0.2336/
  Read 0.2153 — worst cells. LESSON [S+F]: outline completeness + citation volume can coexist with semantic contamination; robotic
  "synthesis templates" without content are ACTIVELY TOXIC (worse than plain serial summary).
• champ_ourcorpus (OUR champion, 0.3671) [S+F]: covers domains but body dense/source-serial; recurring claims (:19/:23); entire
  cross-study synthesis ≈ one short paragraph (:39/:43); candid limitations (:51 only 2% T1 primary, 69% T3 review-tier — which
  ESTABLISHES a journal-quality task failure).

═══ PART 3 — PER-SUB-ITEM WIN MAP (all 25 RACE cells; [S] concrete-output-pattern + [F] moves/quotes) ═══
#7 Mechanisms (.0800): own top-level section BEFORE evidence; name framework+originator+forces+net-condition; END every mechanism
para with a derived implication; model as dynamic; pipeline: mechanism-explorer subagent + "Mechanism constraints" + writer rule
"explain mechanisms/causes not surface descriptions". #8 Cross-industry synthesis (.0800): reconciliation thesis up front; extract
cross-sector pattern after tour; EXPLAIN why studies disagree (units/margins/tech/horizon; exposure≠adoption≠impact); dedicated
consensus/disagreement sections both poles; NEVER template-fake it. #3 Comp restructuring breadth (.0725): operationalize
"restructuring" pre-writing; coverage ledger (creation/displacement/task-transformation/skills/wages/labor-share/inequality/
productivity/job-quality/composition/geography/time), each with evidence+cross-links, no hiding gaps under "labor-market impact".
#4 Comp industry scope (.0725): span materially different task/institution regimes (physical vs cognitive, regulated vs light,
salaried vs platform, high vs low adoption, advanced vs developing) — not synonymous sectors; common schema. #10 Emergent themes
(.0640): derive a NEW falsifiable relationship from multiple baskets + label epistemic status + state the missing test. #13 Inst
on-topic (.0500): scope def + question-to-section map + delete tangents at retrieval AND composition (off-topic not rescued by a
citation). #9 4IR integration (.0480): 4IR properties as explanatory variables (general-purpose/cognitive-reach/low-diffusion-
friction/data-network-complementarity/cyber-physical) explaining pace/breadth/redesign/institutional-pressure. #11 Implications
(.0480): each rec states mechanism-changed/population/trade-off/evidence-strength/testable-outcome; forward-looking must be grounded.
#9b Comp disruptive scale (.0435): report potential-exposure, observed-task-productivity, realized-employment/wage, diffusion, and
uncertainty as DIFFERENT quantities. #10b Comp literature depth (.0435): methods block + evidence map by design/setting/outcome +
gaps (but counts/self-cert insufficient — leaders violate journal-only). #11-16 Inst themes: exact explicit sentence in intro then
mechanism evidence; unpack "significant" as magnitude/breadth/pace/distribution/institutional-consequence (avoid deterministic
mass-unemployment); make sector variation an ORGANIZING AXIS + one synthesis artifact; enforce source-type at retrieval + auditable
methods statement (per-source publication-type/venue/peer-review/DOI/source-role; non-journal excluded or disclosed). #15 Comp
balance (.0290): benefit/harm matrix by stakeholder+time-horizon, identify distribution not net-aggregate. #16 Comp 4IR grounding
(.0290): definition + historical contrast + why-contrast-changes-labor-question. #17 Read language (.0280): one inferential move
per paragraph, define acronyms, no raw retrieval fragments (counter: faithoff 608.5-w median). #18 Read structure/roadmap (.0280):
exec-thesis→definitions/method→mechanisms→evidence→comparisons→synthesis→implications/gaps. #19 Inst lit-review form (.0250): source
selection + thematic synthesis + comparative appraisal + limitations + agenda. #20 Inst English-only (.0250): metadata validation,
exception-count zero (English working paper still fails). #21 Read cohesion (.0210): transitions encode contrast/cause/scope/time/
level/reconciliation. #22 Read synthesis-not-serial (.0210): organize paragraphs around claims/contrasts not author names; keep
corroborating cites in a basket without repeating the claim. #23 Read data/tables (.0140): shared-dimension tables FOLLOWED by
interpretation; numbers followed by meaning. #24 Read layout (.0140): stable heading depth, repeated schemas, no orphan headings/
broken tables/boilerplate (ref's blank source-table cells are the defect to avoid). #25 Read audience/terms (.0140): definition →
intuition/example → limitation.

═══ PART 4 — FACT WIN MAP (13 surfaces; [S], + [F] leaderboard read) ═══
[S+F] FACT standings for GPT-5.5 leaders UNAVAILABLE (CSV shows "-"); map applies executable mechanics. [F] FACT champion is the
reference generator itself (gemini DR E.Cit 165.34 @ C.Acc 78.3 vs openai 39.79 @ 75.01) → at near-equal precision, E.Cit is a 4×
VOLUME game (many unique inline statement-URL pairs). WebWeaver's precision fix was STRUCTURAL: retrieve-only-cited-evidence per
section during writing → citation accuracy 25%→85.9%. AI-Q prompts extractable form into every research unit ("Use [1],[2],[3]...
Every factual claim must have a numbered citation. MANDATORY Sources section...[N] Title: URL", mech.j2:96-97).
[S] the 13 surfaces: #40 cite immediately after the smallest complete proposition (bibliography-only → 0, extract.py:51) — NVIDIA
[5] after robot estimate w/ DOI list. #41 extractable forms + real URLs ([n]↔URL or [Title](URL), 4 recognized forms). #42 each
cited claim complete (fact/population/measure/direction/context; not "by 0.42%"). #43 reachable fetchable URLs (unreachable→unknown→
vanishes from denom+supported). #44 source supports ≥ part of exact statement (partial+rounding accepted; atomic = less ambiguous).
#45 avoid sources with none of the facts (unsupported hurts micro precision; counter: cellcog_7703:60 off-topic). #46 maximize
unique SUPPORTED pairs (widen supported evidence not marker volume; linear E.Cit). #47 avoid exact duplicate same-URL claims
(counter: champ :19/:23; cellcog_7703 boilerplate). #48 one fact→k URLs = k pairs (each study-specific proposition carries its own
URL). #49 k distinct facts/URL each count (write separate atomic claims). #50 don't rely on uncited abundance (no citation-recall).
#51 prestige doesn't help FACT (AER/JPE fails if attached to wrong statement; low-prestige page passes if it contains the text;
enforce journal-quality SEPARATELY for Inst). #52 don't optimize RACE via citations (stripped; RACE Overall excludes FACT).
[S] FACT cautions: unknown/validate-error excluded, unsupported hurts micro, zero-cit tasks skipped (code≠paper macro); partial+
rounding accepted; NO uncited-hallucination penalty/recall/truth-check beyond page support → OUR faithfulness gates must stay
STRICTER than the benchmark.

═══ PART 5 — CROSS-REPORT PATTERNS, RANKED BY APPARENT IMPACT (merged [S] 10 + [F] 10) ═══
1. DEDUCTION APPENDED TO DESCRIPTION [S+F, the single biggest winner-vs-midscorer difference] — end evidence paragraphs with
   derived implications, coin named higher-order themes, state reconciliation theses (ref "this implies/suggests" :38/:98/:100/:147/
   :172/:184/:207/:257; fable5 thesis→0.5131 Insight vs claude-3-7 implication-free 0.4218; AgentCPM Insight gains from "Reasoning-
   Driven Deepening"; leaderboard Insight spread ~2× the Inst/Read spread). 2. MECHANISM-FIRST ARCHITECTURE [S+F] — early theory/
   mechanism section reused by the rest (ref §2→§3-8; AI-Q mechanism_explorer + "Mechanism constraints"; Qianfan :193-218). 3.
   EXPLAIN DISAGREEMENT not report it [S+F] — name WHY studies diverge + consensus/debate/uncertainty own sections (ref :73/:81/
   :291-294; fable5 :36/:52/:114; DRAGged: must "explicitly reason about the conflict"); the #8 cell + Comp #5 in one move. 4.
   RUBRIC-SHAPED COVERAGE AUDIT before/while writing [S+F] — enumerate required dimensions/industries + verify each (ZTE per-chapter
   audit triggers re-research; AI-Q SATISFIED/PARTIALLY/UNSATISFIED per constraint; architect 24-32 acceptance criteria; rewrite
   err-on-inclusion). Comp cells are checklists — winners run them as checklists. 5. PROMPT-ECHO STRUCTURE [S+F] — task keywords
   verbatim in title+headers, genre named, every listed item covered (cheap near-full Inst credit). 6. EVIDENCE DENSITY WITH
   INTERPRETATION [F] — precise inline numbers each followed by meaning; study tables w/ methodology/limitations cols; worked
   examples not framework descriptions. 7. IN-PROSE SOURCE-QUALITY SIGNALING [S+F] — author-year-journal + explicit source-policy
   sentences + flagged exclusions (only route to Inst #17/#18's 0.0625, bibliographies stripped). 8. CALIBRATED COMMITMENT [F] —
   hedge-with-attribution then still commit + "under what conditions your ranking would change"; evasion loses logical-coherence
   credit, unhedged overclaiming loses to the critic-informed reference. 9. LENGTH NECESSARY BUT NOT SUFFICIENT [S+F] — winners
   long (ref ~9k; AI-Q 5000-8000+; AgentCPM +6 by ~9 deepen steps then plateau) BUT polaris_best_compose (5,481w, 0.3023) and
   cellcog_7703 (7,703w, 0.2691) lose badly to fable5 at 3,071w; every added section must add "a new analytical layer"; more
   headings NOT automatically better (cellcog Readability lowest; ZTE 178 headings risk fragmentation) — unit = coherent thematic
   hierarchy, one inferential move/paragraph. 10. ANTI-PATTERN CONFIRMED [S+F] — templated synthesis boilerplate/empty sections/
   repeated sentences/off-topic evidence (cellcog_7703 0.2691, Read 0.2153) score worse than plain serial summary. 11. FORWARD-
   LOOKING BUT FALSIFIABLE [S] — state what evidence is missing + what observation resolves it (ref :300-307; NVIDIA :391-401;
   ZTE :1760-1773). 12. ARCHITECTURALLY, LET EVIDENCE CHANGE THE PLAN [S+F] — DuMate evolving DAG + rubric stopping; ZTE chapter
   audit → re-research; WebWeaver evidence↔outline loop; AgentCPM drafting/deepening alternation; DualGraph separate knowledge/
   outline graphs — coverage+insight discovered ITERATIVELY, not frozen in a one-pass outline.

═══ PART 6 — WHAT POLARIS DOES DIFFERENTLY (Phase-3 handoff; [S] faithoff_t72 + [F] champ_ourcorpus) ═══
[S] faithoff_t72 (52,671 chars, 7,942 words, 14 headings, 199 sentence-proxy) — NOT thin. Strengths: task-based displacement/
productivity/reinstatement explanation (:11); substantial robot/exposure/GenAI-productivity/country/skill/industry/policy evidence
(:15-39); explicit "Cross-Study Synthesis and Contradictions" (:41-43); candid source telemetry (:55). GAPS: 1 PARAGRAPH
ARCHITECTURE — only 14 prose paragraphs, median 608.5 words, max 838 (vs reference median 45) → cripples Read #19/#21/#22 and hides
reasoning boundaries. 2 COVERAGE NOT MATRIXED — sectors in one enormous case-study paragraph (:35), no common mechanism/evidence-
strength/moderator table → weakens 0.0725 industry breadth + 0.0800 synthesis despite raw sector volume. 3 SYNTHESIS TOO LATE/
COMPRESSED — :43 valuable contrasts but ONE wall paragraph must carry consensus/disagreement/measurement/country/implications. 4
NO TABLES. 5 SOURCE-CONSTRAINT FAILURE self-disclosed (:55 only 4% T1, 1% T2, 25% unknown; policy/industry/working-paper material
:7-51) → 0.0375/0.0250 Inst risk. 6 RETRIEVAL ARTIFACTS LEAK — :27 begins mid-word "neously emerge", :47 "hare of people", :51 opens
with a pasted Stanford page header → language/layout defects. 7 NOVELTY NOT EPISTEMICALLY TAGGED (no Established/Emerging/Conceptual/
Hypothesis distinction). 8 NO EXPLICIT METHODS/SELECTION WORKFLOW.
[F] champ_ourcorpus (0.3671) vs winner habits: 1 STATISTIC-STITCHING WITHOUT IMPLICATION ("R² of 0.9325...XGBoost captures majority
of variability" — numbers w/o so-what; almost no paragraph ends with a derived implication → Pattern 1 missing). 2 ORPHANED/
DUPLICATED sentences (redundancy the winners' "every sentence must contribute new information" rule prevents). 3 THIN MECHANISM SPINE
(cites SBTC/taxonomies but never decomposes displacement/reinstatement/productivity or states net-effect condition; later sections
don't reuse it → Pattern 2 missing). 4 ANONYMOUS EVIDENCE (almost no author-year-journal in prose → weak Inst #17/#18 + Comp #5).
5 NO TABLES/BOLD (Read 0.3640, D1/F1 forfeited). 6 polaris_best_compose kept scoped-prompt structure (title "I am researching...",
6 headings/5,481 words → heading-sparse, prompt-mismatched, Inst 0.2775). POSITIVES ALREADY PRESENT [F]: cross-study synthesis
section exists, scope framing exists, span-grounding discipline exists — the SKELETON of Patterns 3/4 without the analytic flesh.
[S] The main Phase-3 question is NOT "retrieve more" — it is where abundant evidence fails to become SECTION-scale, COMPARISON-scale,
epistemically-labeled synthesis, and where source-class enforcement fails BEFORE composition.

═══ PART 7 — ARCHITECTURES / PAPERS (grounded; [S+F]) ═══
• WebWeaver (Alibaba Tongyi, arXiv 2509.13312) [S+F]: dual-agent; planner "iteratively interleaves evidence acquisition with
  outline optimization" → citation-grounded outline linked to an evidence memory bank; writer does HIERARCHICAL per-section
  retrieval+writing (only that section's evidence) → mitigates long-context + citation hallucination; RL result citation accuracy
  25%→85.90%. • AgentCPM-Report (arXiv 2602.06540) [S+F]: "Writing As Reasoning Policy" dynamically revises outline, alternating
  Evidence-Based Drafting ↔ Reasoning-Driven Deepening; sparse initial outline (section titles + intents); conditions retrieval on
  accumulating narrative; DOSE-RESPONSE: Comp+Insight rise ~6 points shallow→deep, plateau ~9 steps; "substantial gains in Insight".
  • DualGraph (arXiv 2602.13830) [S+F]: separates "what the agent knows from how it writes" — Outline Graph + Knowledge Graph co-
  evolve; KG-topology + OG signals generate targeted searches (explicit knowledge-gap detection, not implicit); 53.08 RACE w/ GPT-5.
  • DRAGged into Conflicts (arXiv 2506.08500) [S+F]: taxonomy of inter-source conflicts; models "struggle to appropriately resolve
  conflicts" but explicit conflict reasoning "significantly improves" quality → basis for the consensus/disagreement surface. •
  DuMate/Qianfan + ZTE architectures: see Part 2. [S] AVAILABILITY BOUNDARY: Zhipu — no fetchable task-72 report or method paper
  (no structure claim). HF raw-outputs `Ayanami0730/deep_research_bench` = 401-gated (Qianfan/ZTE/real-Cellcog task-72 reports not
  pullable that way; Qianfan/ZTE reports obtained via their own GitHub instead). Method architecture cannot be reverse-engineered
  from prose style alone.

═══ PART 8 — REMAINING TOP-10 TEARDOWN (addendum, [F2]=Fable addendum; extends Parts 1-7) ═══
Closes the top-10 gap: the first pass did cellcog-max/WhaleCloud/Qianfan/ZTE/NVIDIA; this adds the skipped ABOVE-reference systems,
all fetched from the leaderboard Space raw_data. AVAILABILITY [F2]: legacy dir has NO zhipu/iFlow/ZTE file (full tree listed) → those
task-72 reports are NOT fetchable from this Space; no claims made. Current-tab has all 10.
STRUCTURAL SCOREBOARD (measured): Bodhi 54.07/54.15/54.60/54.41/51.87 — 4,361 words, 50 headings, 0 tables, `[[n]](url)`×105. Lunon
53.51/—/54.83/—/50.48 — 11,476 words, 65 headings, 24 table lines, `[Title](url)`×184, EMPTY `## References` (:492). Dalpha 53.10 —
4,039 words, 15 headings, 0 tables, 35 refs ALL journal+DOI. Sourcery 51.17 — 9,849 words, 54 headings, 35 table lines, 18 refs mixed.
Xiaoyi (legacy) 57.00 — 19,095 words, 44 headings, 292 table lines, Chinese H1 + ~30 literal `[Blueprint State]` placeholder citations.

• BODHI (#3, 54.07) — DENSITY EXISTENCE PROOF [F2]: 4,361 words, 0 tables, yet #3. 50 headings/4,361w ≈ 87 words/heading; each subsection
  = closed loop study→precise number→Strength/Limitation appraisal→bolded LABELED deduction. #7 mechanism-first + reused downstream
  (:15 "**Restructuring implication**: even when aggregate employment effects are small... firms may still be actively reorganizing";
  :122 "consistent with GPT diffusion lags"). #8 completed at DEBATE level (§8.2 both poles w/ cites) but NO cross-sector matrix/
  moderator-reconciliation after the sector tour → Insight 54.60 < cellcog 57.08. #2 coverage contract up front (:3 five enumerated
  changes). Read 51.87 = its lowest (same signature as cellcog). NEW: N1 THE LABELED-DEDUCTION TEMPLATE — Pattern-1 shipped as a
  recurring bolded tag ("**Restructuring implication:**"/"**Interpretation:**"/"**Mechanism link:**"/"**Policy tension:**") after every
  evidence unit (judge needn't detect the deduction — it's typographically flagged; reference does it implicitly, nobody else SHIPS it
  as a label). N2 MEASUREMENT-STRATEGIES CHAPTER as a first-class section (§2, TEN methods each w/ Strength/Limitation) → hits lit-review
  form + literature depth + method-critique-as-second-order-insight in one structure (attacks the reference's own weakness #1). N3
  first-person evidence-boundary protocol (:4 "Where the research record contains only bibliographic indications... I either do not use
  it or explicitly limit claims").
• LUNON (#4, 53.51; Read 50.48 lowest) [F2]: 11,476w, most-engineered epistemics in the tab. #8 STRONGEST sector-synthesis architecture:
  sectors GROUPED BY BINDING CONSTRAINT + 9-row matrix w/ a "Binding Constraint" column + "**Cross-sector claim:**" paragraphs (:287
  "That difference in binding constraint, not technical exposure, explains why two high-exposure sectors realise change at different
  speeds"); ch10 resolves each debate as a "design-induced artifact" (:371,:377). #7 coupled-system w/ timing asymmetry (:114) + original
  micro-mechanism (:126 "persistence of hybridization is not caution but arithmetic: expected cost of machine error exceeds the wage of
  the human who catches it"). #10 coined themes (reshoring-incidence inversion :317; surveillance paradox :359). NEW: N4 WEIGHTED
  SOURCE-INCLUSION RUBRIC TABLE (R-1 peer-review .30/R-2 English .15/R-3 Q1-Q2 .20/R-4 relevance .20/R-5 recency .15) + "signpost
  convention" (seminal works named but "never cited as evidence for a load-bearing claim"). N5 FALSIFIERS section (three named, ranked by
  checkability). N6 confidence-tier→policy-verb mapping ("commit on mature... stage on partial... hedge on open"). N7 validity envelope.
  N8 measurement-reflexivity as the insight engine ("when the ruler is made of the thing it measures", reused 4×). CAVEATS (why #4 not #3):
  rubric table but LOAD-BEARING claims cite NBER/arXiv/Pew/vendor blogs (signpost broken); empty `## References` as literal last line.
• DALPHA (#5, 53.10) — COMPLIANCE EXISTENCE PROOF [F2]: 4,039w, 15 headings, 0 tables — the ONLY system with genuine end-to-end journal
  compliance (35/35 real journal DOIs: QJE/AER/JPE/JEP/REStat/Science/PNAS/ManSci/...); cleanest one-move explained-disagreement (:41
  "These findings are not contradictory; they measure different levels of adjustment"); exposure→adoption→impact as its own limitations
  chapter (:145-149); channel-attributed conclusion (:161 assigns each conclusion to its strongest evidence family). NEW: N9 evidence-
  provenance typing ("distinguishes direct AI evidence from broader automation/robotics evidence" — labels each block direct/bridge/
  background). N10 channel-attributed conclusion (one-paragraph prose evidence map). SHAPE: 4k flawless words beats 9-11k flawed — the
  "~9,000-word bar" is not a floor; clean synthesis + perfect source discipline + explained disagreement WITHOUT scenarios/tiers/matrices.
• SOURCERY (#6, 51.17) — GENERIC-TEMPLATE CEILING [F2]: 9,849w but a house template (ToC/Key-Questions/Core-Findings/Deep-Analysis/
  Unknowns/Evidence-Map) NOT rubric-shaped → Pattern 4 ✘, Pattern 5 ✘. Competent insight (so-so tech :272; reinstatement sign-flip
  before/after 1987 :359-362; welfare-negative new tasks 2% GDP/−0.72% welfare :353) but FORFEITS Comp #3 industry scope (.0725) —
  self-confessed :330 "sectoral evidence remains thin... No source provides AI-specific sectoral breakdowns", no sector tour — and near-
  zero 4IR grounding. Weak compliance ("18 academic sources", Medium/blog/WP refs). NEW: N11 EVIDENCE MAP artifact (21-row Theme×
  Strongest/Moderate/Weak-Absent table w/ cell citations). N12 scenario triptych w/ per-scenario Confidence. N13 deep source-mining (18
  sources, 435 marks; 10-20 atomic claims per source → good FACT E.Cit surface #49 but starves breadth cells → loses on this rubric).
• XIAOYI (legacy, 57.00) — SATURATION STRATEGY [F2]: 19,095w, 292 table lines — most complete coverage of any system in either phase;
  every mechanism/consensus/controversy as TABLES w/ Confidence + Resolution-Status columns (§8.3 "Active Controversies" table :859-864;
  "Emergent Consensus" table :849-855); original mechanisms (:44 ChatGPT "expectation shock"/anticipatory-adjustment channel; :42 "double
  displacement mechanism"; :336 healthcare liability paradoxically protects employment). NEW: N14 "Critical Evidence Gap" LABELED BLOCK in
  EVERY section (converts each coverage boundary into Insight #11 gap→research-implication credit). N15 consensus/controversy tables w/
  Confidence+Resolution-Status + "Research Implication" column. N16 methodological-generations genealogy (exposure indices/identification
  1st-2nd-3rd generation w/ per-gen limitation). N17 ANTI-PATTERN: literal "[Blueprint State]" placeholder as a citation ~30× survived to
  submission — legacy Gemini tolerated it at 57.00; under GPT-5.5/FACT it's cellcog_7703-class filler. DO NOT bank on judge tolerance;
  Chinese H1 on an English task likewise forgiven by the legacy judge only.

CROSS-SYSTEM FINDINGS THAT EXTEND PARTS 1-7 [F2]:
F1. WORD COUNT UNCORRELATED WITH RANK in the current top-6 (Bodhi #3 @4,361w, Dalpha #5 @4,039w beat Lunon #4 @11,476w and Sourcery #6
   @9,849w). AMENDS Pattern 9: on the GPT-5.5 judge the operative variable is closed-loop paragraph DENSITY (study→number→appraisal→
   deduction) + rubric-cell allocation; ~4k flawless words w/ full cell coverage ≈ 54, 9-11k words w/ cell gaps ≤ 53.5.
F2. THE #1/#3 READABILITY SIGNATURE: cellcog 51.94, Bodhi 51.87, Lunon 50.48 all bottom out on Read — extreme analytic density costs
   2-4 Read points and winners ACCEPT the trade (Read weight .14). The competitive ceiling does NOT require winning Read (relevant to
   our 0.36 — fix Read for our own floor, but it's not the ceiling lever).
F3. Inst #17/#18 DIFFERENTIATES WHEN INSIGHT COMPRESSES: current-tab rank tracks source-discipline (Bodhi > Lunon broken-practice >
   Dalpha perfect-practice > Sourcery weak-claim+Medium-refs). DALPHA PROVES genuine journal-only compliance is ACHIEVABLE (35/35 DOIs)
   → "leaders violate journal-only" (Qianfan/ZTE/NVIDIA caveats) is a LEGACY-tab phenomenon, not a law.
F4. EPISTEMIC LABELING HAS ESCALATED FROM TAGS TO ARTIFACTS: Evidence Map strength table (Sourcery), maturity-tier→policy-verb + falsifiers
   + validity envelope (Lunon), consensus/controversy tables w/ Confidence/Resolution columns (Xiaoyi), per-scenario Confidence (Sourcery),
   per-section Critical-Evidence-Gap blocks (Xiaoyi), Strength/Limitation pairs per method (Bodhi) — all PRE-generation-plannable.
F5. THE LABELED-DEDUCTION TEMPLATE (Bodhi N1) is the cheapest implementation of Pattern 1 — a writer rule "end every evidence unit with a
   bolded `Implication:` clause" makes the .0800-cell behavior verifiable by OUR gates AND visible to the judge.
F6. METHODS/MEASUREMENT CHAPTER IS NOW TABLE STAKES — 4/5 systems have one (Bodhi §2, Lunon 1.4+13.1, Sourcery, Xiaoyi §8); the reference
   has NONE (its weakness #1). A standing beatable surface the top systems already exploit.
F7. JUDGE TOLERANCE FOR STRUCTURAL DEFECTS is real but NOT BANKABLE: empty References heading (Lunon #4), ~30 "[Blueprint State]" leaks
   (Xiaoyi 57.00), zero tables (Bodhi #3, Dalpha #5) — none fatal, all violate our quality bars + FACT extraction; treat as forgiven noise.
F8. GENERIC DEEP-RESEARCH TEMPLATES LOSE TO RUBRIC-SHAPED OUTLINES (Sourcery vs everyone above it) — confirms Pattern 5 by counter-example.

═══ DEFINITIVE CONCLUSION [S+F] ═══
The bar is NOT the reference's word count. It is a report whose coverage plan is COMPLETE, whose claims are built from faithful
evidence baskets, whose reasoning EXPOSES MECHANISMS AND MODERATORS, whose sectors are compared through a shared causal schema,
whose disagreements are RESOLVED by level/method/time/institution, whose novel insights are EPISTEMICALLY LABELED, whose policy
follows from diagnosed levers, and whose paragraphs/tables make every inference inspectable. Winners engineer these Insight cells
PRE-generation (mechanism-explorer subagents, rubric-guided planning, per-chapter audits, evidence↔outline loops); one competitor
even runs a rubric-shaped post-gen rewrite — which our no-post-gen rule forbids, so we must hit the same surfaces pre-generation.
POLARIS's immediate visible gap is converting abundant evidence into READABLE, SOURCE-COMPLIANT, MATRIXED, CROSS-SECTOR CAUSAL
SYNTHESIS with per-paragraph deductions — the exact substance Phase 3 must turn into wired, small-test-proven, generalized fixes.
