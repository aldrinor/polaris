## INGESTION RECEIPT

/home/polaris/wt/faithoff/docs/race_fact_initiative/SCORING_SPEC.md | lines=245 | FIRST: "# SCORING_SPEC — RACE + FACT — LOSSLESS consolidation of Sol + Fable (Phase 1)" | MID(line 123): "(named-author/journal attribution); verification limited/run-dependent." | LAST: "replication (±0.027 noise, single-call judge)."

/home/polaris/wt/faithoff/docs/race_fact_initiative/phase1_sol_verdict.md | lines=462 | FIRST: "# Phase 1 Investigator Verdict: Definitive Map of DeepResearch Bench RACE + FACT Scoring" | MID(line 231): "### A6.5 Dataset-level leaderboard aggregation" | LAST: "The highest-leverage scoreable surfaces are: **(1)** task-specific Insight—causal/mechanistic analysis, cross-source synthesis, logical integration, uncertainty, and novel implications—because Insight averages 35.2% of RACE weight and reaches 42%; **(2)** Comprehensiveness—complete coverage of every requested dimension/entity/industry/time scope with representative evidence—because it averages 29.2%; **(3)** exact Instruction Following, especially source/type/language/output constraints, because omissions receive separate criteria and can carry up to 45% within that dimension; **(4)** clear structure and synthesis-oriented readability, usually lower-weight but as high as 25% for audience/data-presentation-heavy tasks; and **(5)** FACT’s independent supported-pair surface: inline, extractable, reachable citations attached to atomic claims, with more unique supported statement–URL pairs raising effective citations and unsupported pairs lowering code precision. For task 72, the four largest coefficients are mechanistic labor-market analysis (0.0800), critical cross-industry synthesis (0.0800), restructuring-dimension breadth (0.0725), and industry breadth (0.0725), so fixes that deepen mechanisms and synthesis while closing missing sector/effect coverage have the largest grounded RACE headroom (`criteria.jsonl:72`); citation-count work cannot substitute for those RACE surfaces because FACT is calculated separately (`run_benchmark.sh:35-95`)."

/home/polaris/wt/faithoff/docs/race_fact_initiative/phase1_fable_verdict.md | lines=472 | FIRST: "# Phase 1 Verdict — RACE + FACT scoring map (investigator: Fable)" | MID(line 236): "  criterion; the reported quantity is target/(target+reference) (A.5 step 4-5)." | LAST: "(`stat.py:26-30`)."

# Phase 2 independent verdict — reference and winner teardown mapped to RACE + FACT

## 0. Scope, evidence convention, and bottom line

I read the three Phase-1 artifacts above in full before beginning this phase. This verdict uses the exact 25 task-72 RACE cells and the FACT statement–URL mechanics established there. Local JSONL “article line N” means line N after splitting the `article` string on newlines; it does **not** mean physical line N of the one-record-per-line JSONL. For web artifacts, the URL is the source and line numbers refer to the fetched Markdown report where given.

The principal finding is not “make the report longer.” The reference and strongest accessible leaders repeatedly do four concrete things:

1. They turn evidence into **causal chains**—technology capability → task substitution/augmentation/control → firm response and output → occupation/skill/wage effect → distributional result—then name moderators that change the chain.
2. They turn sector coverage into **comparative inference**: a common matrix of task mix, demand elasticity, regulation, institutions, adoption frictions, worker level, and measurement level explains why results differ.
3. They give epistemic structure to synthesis: **consensus, disagreement, uncertainty, established finding, emerging pattern, conceptual argument, analytical hypothesis, and open test** are visibly separated.
4. They plan breadth into the outline and audit it in tables. The high-value cells appear as sections, not as a final paragraph improvised after serial source summaries.

That conclusion is grounded below in the frozen reference, the current GPT-5.5 leaderboard leaders, legacy/Gemini leaderboard leaders, official reports and method descriptions, and the local candidates. It is also bounded: RACE uses an LLM judge and task/reference ratio, so this teardown identifies observable report moves aligned to the rubric; it does not prove the causal contribution of any one move without ablation.

## 1. Frozen task-72 reference report

**Source:** `/home/polaris/wt/faithoff/third_party/deep_research_bench/data/test_data/cleaned_data/reference.jsonl`, record `id=72`, `article`.

### 1.1 Exact outline, in order

1. `# The Restructuring Impact of Artificial Intelligence on the Labor Market: A Literature Review`
2. `## 1. Introduction: AI and the Fourth Industrial Revolution`
3. `### 1.1. Defining the Fourth Industrial Revolution and Its Labor Market Context`
4. `### 1.2. Artificial Intelligence as a Catalyst`
5. `## 2. Theoretical Lenses on AI and Labor Market Restructuring`
6. `### 2.1. The Task-Based Framework: Displacement and Reinstatement`
7. `### 2.2. Skill-Biased, Task-Biased, and Routine-Biased Technological Change`
8. `### 2.3. Substitution, Complementarity, and Augmentation`
9. `## 3. Empirical Findings: Employment, Occupations, and Wages`
10. `### 3.1. Job Displacement and Job Creation`
11. `### 3.2. Aggregate Employment, Wages, and Polarization`
12. `### 3.3. Cross-Country and Regional Variations`
13. `## 4. Sectoral and Occupational Disruptions`
14. `### 4.1. Manufacturing and Logistics`
15. `### 4.2. Healthcare, Finance, and Transportation`
16. `### 4.3. Creative, Marketing, and Service Industries`
17. `### 4.4. Evolving Workforce Needs`
18. `## 5. Wages, Inequality, and Skills`
19. `### 5.1. Wage Structures and Labor Share`
20. `### 5.2. Income Inequality`
21. `### 5.3. The Future Skillset`
22. `## 6. Debating the Future: Pace, Scale, and Outlook`
23. `### 6.1. Optimistic and Pessimistic Perspectives`
24. `### 6.2. Moderating Factors`
25. `### 6.3. The Productivity Paradox`
26. `## 7. Policy Responses`
27. `### 7.1. Education, Reskilling, and Lifelong Learning`
28. `### 7.2. Social Safety Nets`
29. `### 7.3. Taxation and Regulation`
30. `## 8. Conclusion: Synthesis, Debates, and Future Directions`
31. `### 8.1. Areas of Consensus`
32. `### 8.2. Areas of Disagreement`
33. `### 8.3. Gaps and Future Research`

This is rubric-shaped without reproducing rubric wording mechanically: definition/4IR → mechanisms → aggregate evidence → industries → wages/inequality/skills → debate/moderators/productivity → policy → consensus/disagreement/gaps. Every major task-72 request receives a dedicated destination.

### 1.2 What earns the two 0.0800 Insight cells

#### Mechanisms of restructuring — 0.0800

The report does not stop at “automation displaces workers.” It distinguishes forces and follows their interaction:

> “The framework highlights two primary, opposing forces:”  
> — reference `id=72`, article line 29

It then defines the first as:

> “**Displacement Effect**: This occurs when automation technologies allow capital (machines, software, AI systems) to take over tasks previously performed by human workers.”  
> — reference `id=72`, article line 31

and the counterforce as:

> “**Reinstatement Effect**: Counterbalancing displacement is the potential for technology to create entirely *new tasks* in which labor holds a comparative advantage.”  
> — reference `id=72`, article line 32

It then identifies the dynamic balance and a policy-relevant design variable:

> “AI development primarily focused on substituting labor in existing tasks poses a greater inherent challenge to labor's economic standing than AI directed towards creating new tasks, augmenting human capabilities, or enabling entirely new industries.”  
> — reference `id=72`, article line 38

It also explains why a static routine/non-routine list is insufficient:

> “The advent of modern AI, particularly ML and generative AI, complicates the simpler routine/non-routine dichotomy. AI systems are increasingly capable of performing *non-routine cognitive* tasks that were previously the domain of high-skilled professionals.”  
> — reference `id=72`, article line 46

The resulting analytical unit is narrower than a skill category:

> “The key determinant appears to be less about the general skill level and more about the specific nature, predictability, and complexity of the tasks involved, a boundary that AI continues to push.”  
> — reference `id=72`, article line 48

The substitution/complementarity section makes the causal unit explicit and keeps it dynamic:

> “However, the distinction between substitution, complementarity, and augmentation may not be static or clear-cut. The relationship can be highly context-dependent, varying across different AI applications, industries, and job roles. Furthermore, it can evolve over time as AI technology matures and organizational processes adapt.”  
> — reference `id=72`, article line 60

That is mechanism analysis rather than listing: it names competing channels, the unit of impact (tasks), intermediate organizational choices, moderators, time dynamics, and downstream labor demand.

#### Critical cross-industry synthesis — 0.0800

The reference first supplies sector evidence, but its scoring move is to pull that evidence back into common explanations:

> “Across nearly all industries undergoing AI adoption, a common pattern of evolving workforce needs emerges:”  
> — reference `id=72`, article line 141

The next bullets specify rising digital/AI skill demand, the enduring value of “critical thinking, complex problem-solving, creativity” and social/emotional skills, and lifelong learning (lines 143–145).

It connects sector variation to new-task creation rather than merely enumerating jobs:

> “This generative aspect of AI contributes to the ‘reinstatement’ effect, creating demand for new types of work and skills associated with these novel applications.”  
> — reference `id=72`, article line 147

It then distinguishes AI from earlier waves:

> “Unlike earlier waves of automation that primarily impacted manufacturing and routine clerical work, AI is now directly affecting sectors like finance, healthcare, law, and creative industries.”  
> — reference `id=72`, article line 149

The empirical synthesis explicitly resists a single pooled conclusion:

> “The empirical literature does not offer a simple consensus on the net employment impact of AI and automation.”  
> — reference `id=72`, article line 81

The same paragraph grounds the variation in “the specific technology studied,” time period, geography, level of analysis, method, and outcome measured.

Finally, the report resolves apparently conflicting findings through temporal and analytical scale:

> “Furthermore, a potential temporal lag and scale mismatch complicates the empirical assessment of AI's impact.”  
> — reference `id=72`, article line 100

That paragraph explains how firm/task changes can precede aggregate effects because general-purpose technologies require diffusion and complementary innovation.

The high-scoring move is therefore **contrast + moderator + reconciliation**, not one sector paragraph after another.

### 1.3 Evidence for every other task-72 content cell

#### Comprehensiveness

- **4IR grounding (0.0290):** the opening defines 4IR through “fusion of technologies that blur the lines between the physical, digital, and biological spheres” and emphasizes its “speed, scope, and systems impact” (lines 7–11). AI is then identified as “a central driving force” (line 9).
- **Restructuring-dimension breadth (0.0725):** line 17 defines restructuring as changes in “tasks,” “occupational demand,” and occupational structure; the outline separately covers displacement/creation, aggregate employment, wages, polarization, labor share, inequality, skills, productivity, and job quality. The table at lines 102–113 compares methods and outcomes.
- **Industry breadth (0.0725):** sections 4.1–4.3 cover manufacturing, logistics, healthcare, finance, transportation, creative work, marketing, and services (lines 121–139); line 141 performs the cross-sector synthesis.
- **Disruptive character/scale (0.0435):** the introduction frames 4IR by speed/scope/system impact (line 7), while line 149 explains why AI's cognitive reach may make disruption “more pervasive and rapid.”
- **Literature depth/representativeness (0.0435):** the report moves among formal task models, occupation studies, robot evidence, country comparisons, wage/labor-share evidence, organizational literature, and policy. Section 8 states it is a review of “high-quality journal articles” (line 274), although the article does not expose a reproducible search/selection method.
- **Balanced positive/negative impacts (0.0290):** line 19 poses the central tension as productivity/growth/new work versus displacement/inequality/insecurity; sections 6.1 and 8.2 preserve optimistic, pessimistic, and conditional positions (lines 194–207, 291–294).

#### Remaining Insight

- **4IR integration (0.0480):** AI is not merely named as 4IR. Lines 7–11 connect speed, interconnection, cyber-physical convergence, and system-wide change to labor restructuring.
- **Emergent themes/linkages/novel insight (0.0640):** line 172 elevates distribution from an afterthought to a causal/political issue: who captures productivity gains shapes inequality and legitimacy. Line 184 identifies a paradox: AI automates cognition yet raises the value of “uniquely human” social, creative, and judgment skills. Lines 211–219 connect the productivity paradox, J-curve, “so-so automation,” organizational complements, and adoption bottlenecks.
- **Implications/future agenda (0.0480):** policy is derived from mechanisms—education/reskilling, safety nets, taxation/regulation (sections 7.1–7.3)—and the conclusion itemizes gaps in longitudinal, sector, country, distributional, and institutional evidence (lines 300–307).

### 1.4 Structural and prose habits

- **Roadmap:** the introduction frames the problem, defines terms, and states the central tension before theory. Unlike reference task 100, it does not contain a literal “this report proceeds…” roadmap paragraph; the heading hierarchy supplies the roadmap.
- **Definitions before evidence:** 4IR, restructuring, displacement, reinstatement, substitution, complementarity, and augmentation are defined before empirical claims (lines 7–60).
- **Synthesis after inventory:** empirical and sector sections feed dedicated debate, moderator, consensus, disagreement, and gap sections. The conclusion does not merely repeat the introduction.
- **Paragraph scale:** 56 prose paragraphs; median 45 words, mean 57.6, maximum 168. This produces readable analytic units rather than wall paragraphs.
- **Transitions:** recurrent pivots include “however,” “by contrast,” “this helps explain,” “taken together,” “the balance depends,” and “temporal lags and scale mismatches.” They encode relationships, not cosmetic flow.
- **Tables:** one study/method/finding table (article lines 102–113) and one source-oriented table (lines 263–270). The latter has blank “Key Supporting Sources” cells, a real weakness.
- **Hedging/uncertainty:** “may,” “can,” “suggests,” “depends,” “varies,” “uncertain,” and explicit disagreement recur. This is calibrated in the analytic sections rather than appended only in limitations.
- **Forward-looking design:** policy and research gaps are separate, so normative recommendations are not confused with empirical findings.

### 1.5 Length, density, and claim-count boundary

The frozen task-72 article contains 69,284 characters, 8,848 alphanumeric word tokens (9,073 under the alternate broad tokenizer used during extraction), 309 lines, 33 headings, 56 prose paragraphs, 18 Markdown table lines, and a conservative 215 sentence-boundary proxy. It contains 66 numeric-token occurrences and 160 hedge-token occurrences under the extraction lexicons. These are structural descriptors, **not quality scores**.

An exact “number of distinct claims” cannot be grounded without a human proposition-level annotation protocol: one sentence may contain several claims and repeated paraphrases may be one claim. The defensible proxy is therefore 215 sentence-like propositions, explicitly not an exact distinct-claim count. Evidence density is qualitative here because the cleaned reference article has no surviving inline URL markers; RACE strips citations before judging, and FACT must be measured from the separately cited output rather than inferred from this cleaned article (`SCORING_SPEC.md`, FACT sections).

### 1.6 Reference weaknesses that leaders improve

1. **No reproducible methods section.** It asserts “high-quality journal articles” (line 274) but does not state databases, dates, inclusion/exclusion, screening, or study counts.
2. **Uneven sector evidence.** The report admits “limited specific journal evidence” for healthcare (line 127).
3. **Some sector prose remains catalog-like.** The synthesis at lines 141–149 is strong, but much of lines 121–139 is a serial sector tour.
4. **One incomplete table.** The “Key Supporting Sources” column is blank in the table at lines 263–270.
5. **No inline citations survive in the cleaned article.** That is not a RACE defect because citations are stripped for RACE, but it means the reference cannot demonstrate FACT behavior from this artifact.

## 2. How the reference adapts to other tasks

### 2.1 Data-heavy/inventory task: reference `id=91`

**Source:** the same local `reference.jsonl`, record `id=91`.

This report expands to 68,011 characters, 9,585 alphanumeric words, 221 lines, 22 headings, 45 table lines, and only 37 hedge-token occurrences. Its structure is entity/class driven: Bronze, Silver, and Gold Saints; Poseidon's Marina Generals; Hades' Specters; Asgard's God Warriors; protagonist analyses; a Twelve Zodiac table; and a concluding comparative class/theme analysis.

The style adapts by:

- defining the power system and hierarchy quantitatively at the start—Bronze up to Mach 1, Silver Mach 2–5, Gold light speed (article line 5);
- using repeated character fields (rank, armor, technique, arc role, fate) and a compact comparative table (`id=91`, lines 76–91);
- synthesizing after the roster. For example, after the Gold-Saint table it states that “immense power does not equate to inherent virtue” and compares Saga's corruption, Kanon's redemption, apparent betrayal, and final sacrifice to infer that the class explores “duty, morality, betrayal, and sacrifice” (`id=91`, line 93).

Thus, when the task demands entity coverage, the reference accepts longer entries, repeated schemas, and more tables; it still adds a thematic inference after the inventory.

### 2.2 Analysis task: reference `id=100`

**Source:** the same local `reference.jsonl`, record `id=100`.

This report contains 65,639 characters, 8,563 alphanumeric words, 270 lines, 24 headings, 17 table lines, and 181 hedge-token occurrences. It uses a much more analytical architecture:

- a literal roadmap: “Section 2 defines… Section 3 examines… Section 4 delves into the psychological and sociological mechanisms… Section 5 explores… Finally, Section 6 synthesizes…” (`id=100`, line 19);
- concept definitions and typology before claims (`id=100`, lines 21–72; Table 1, lines 44–52);
- balanced effects and a positive/negative comparison matrix (`id=100`, lines 74–129; Table 2, lines 112–123);
- mechanism chapters on anthropomorphism, parasocial interaction, CASA, cognitive dissonance, trust, attachment, identity, and sociological theory (`id=100`, starting line 131);
- a moderator synthesis: effects vary by AI embodiment, usage frequency, user traits, age, and prior loneliness, making broad generalization inadequate (`id=100`, line 125);
- an emergent feedback-loop inference: AI sought for loneliness may intensify dependence and make human connection harder (`id=100`, line 127);
- an ontological synthesis: human–AI bonds may redefine what connection is and to whom humans relate (`id=100`, lines 243–251);
- explicit unresolved causal and longitudinal questions (`id=100`, lines 253–264).

Compared with task 91, the analysis report uses fewer tables, much more hedging, more theory, and explicit causal/ethical synthesis. The frozen reference therefore adapts form to the scoring surface: schema/table coverage for an entity inventory; mechanisms/moderators/uncertainty for an analysis task.

## 3. Top scorers: leaderboard regimes and accessible reports

There are two distinct published leaderboard regimes and their scores must not be mixed. The current `data_gpt55` leaderboard lists cellcog-max first at 55.78 and WhaleCloud-DocChain_0612 second at 54.78. The legacy/Gemini leaderboard lists Qianfan/DuMate first at 58.03, ZTE second at 57.27, Zhipu fourth at 57.06, and NVIDIA-AIQ at 55.95. Sources: [current leaderboard CSV](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/leaderboard.csv) and [legacy leaderboard CSV](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data/leaderboard.csv).

The requested `Ayanami0730/deep_research_bench` Hugging Face dataset URL returned HTTP 401 during this investigation. The public [muset-ai/DeepResearch-Bench-Dataset](https://huggingface.co/datasets/muset-ai/DeepResearch-Bench-Dataset) is accessible, but it does not expose every leaderboard leader's report. I found actual task-72 reports for current cellcog and WhaleCloud in the leaderboard Space, official GitHub reports for Qianfan/DuMate and ZTE, and the Space report for NVIDIA. I did **not** find a publicly fetchable task-72 report or method paper for Zhipu in the accessible repositories; I therefore make no report-structure claim for Zhipu.

### 3.1 Current #1: cellcog-max

**Report:** [cellcog-max current raw reports](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/raw_data/cellcog-max.jsonl), record `id=72`.  
**Score:** overall 55.78; Comprehensiveness 56.34; Insight 57.08; Instruction Following 55.30; Readability 51.94 ([current CSV](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/leaderboard.csv)).

#### Outline

The report is 123,611 characters, 16,910 alphanumeric words, 592 lines, 50 headings, 241 non-list prose paragraphs, and 10 table lines. Its outline is:

1. Abstract
2. Introduction: scope, method, central finding, eight syntheses, roadmap
3. Conceptual framework
   - 4IR and technological-determinism critique
   - task-based, skill/routine-biased, and prediction/judgment lenses
   - “inefficient automation”
   - disciplinary bridge
4. Three empirical eras
   - industrial robots
   - software AI/algorithmic management
   - generative AI
5. Sectoral heterogeneity
   - manufacturing, professional/knowledge work, platforms/freelance, public and care work
6. Generative-AI exposure and productivity evidence
7. Cross-sector synthesis and comparison table
8. Cross-cutting outcomes
   - wages/labor share
   - inequality/gender
   - labor process/autonomy
   - institutional mediation
9. Eight “Contested Debates & Novel Insights”
   - routine-to-cognitive exposure inversion
   - freelance/population paradox
   - skill compression
   - autonomy–employment distinction
   - Turing Trap
   - jagged frontier
   - gender reversal
   - Global South informality buffer
10. Policy derived from mechanisms
11. Limitations and research gaps
12. Conclusion

The exact fetched heading inventory, in order, is:

1. `# The Restructuring Impact of Artificial Intelligence on the Labor Market: A Peer-Reviewed Literature Review`
2. `## Abstract`
3. `## 1. Introduction`
4. `### 1.1 The Fourth Industrial Revolution and the Labor Market Question`
5. `### 1.2 Scope, Methods, and Source Selection`
6. `### 1.3 Roadmap`
7. `## 2. Conceptual Framework`
8. `### 2.1 The 4IR Lens`
9. `### 2.2 Three Complementary Analytical Lenses`
10. `### 2.3 AI as Prediction Technology Complementary to Judgment`
11. `### 2.4 Inefficient Automation: The Efficiency Perspective`
12. `### 2.5 Bridging the Disciplinary Divide`
13. `## 3. Three Eras of Empirical Evidence`
14. `### 3.1 Era 1 — Computerization, SBTC, and Polarization (1990s–early 2010s)`
15. `### 3.2 Era 2 — Industrial Robots and Narrow AI (2010s–2022)`
16. `#### 3.2.1 Manufacturing: Causal Identification and Meta-Analytic Limits`
17. `#### 3.2.2 Narrow AI Diffusion and Vacancy-Based Evidence`
18. `#### 3.2.3 Sectoral Heterogeneity in Era 2`
19. `### 3.3 Era 3 — Generative AI and Large Language Models (2022–present)`
20. `#### 3.3.1 Exposure Methodologies and Their Peer-Reviewed Critiques`
21. `#### 3.3.2 Within-Firm Adoption and Productivity Evidence`
22. `#### 3.3.3 Displacement on Open Platforms`
23. `#### 3.3.4 The Null at National Scale`
24. `#### 3.3.5 Sectoral Evidence in Era 3`
25. `### 3.4 Cross-Sector Synthesis`
26. `## 4. Cross-Cutting Dimensions`
27. `### 4.1 Wages, Employment, and the Labor Share`
28. `### 4.2 Distributional Effects, Inequality, and Gender`
29. `### 4.3 Labor Process, Autonomy, and Algorithmic Management`
30. `### 4.4 Institutional Mediation Across Levels`
31. `## 5. Contested Debates and Novel Insights`
32. `### 5.1 The Inversion of Exposure: From Routine to Cognitive`
33. `### 5.2 The Freelance-Population Paradox`
34. `### 5.3 Augmentation as Skill Compression`
35. `### 5.4 The Autonomy-Employment Distinction`
36. `### 5.5 The Turing Trap: Technology Choice as Endogenous`
37. `### 5.6 The Jagged Frontier and the Limits of Exposure Measurement`
38. `### 5.7 The Gender Exposure Reversal`
39. `### 5.8 The Global South's Informality Buffer`
40. `## 6. Policy Responses`
41. `### 6.1 Reskilling, Upskilling, and Active Labor Market Policy`
42. `### 6.2 Redistribution: Robot Taxation and UBI`
43. `### 6.3 AI Governance: The EU AI Act`
44. `### 6.4 Sectoral Bargaining and Co-determination`
45. `## 7. Limitations, Gaps, and Future Research`
46. `### 7.1 Methodological Limitations`
47. `### 7.2 Geographic and Demographic Gaps`
48. `### 7.3 Frontier Questions`
49. `## 8. Conclusion`
50. `## References`

#### How it wins the large cells

It states an evidence boundary and count at the outset:

> “This review synthesizes approximately 96 English-language peer-reviewed journal articles…”  
> — cellcog current task 72, article line 7

It refuses a universal effect:

> “Heterogeneity, not displacement, is the central peer-reviewed finding.”  
> — line 9

The same paragraph grounds that statement in technology generation, sector, institutions, worker characteristics, and level of measurement.

It explicitly separates original synthesis from established evidence:

> “The review develops eight original syntheses, each epistemically tagged by evidentiary status”  
> — line 11

Mechanistically, it turns every framework into an explanatory chain. It says that “4IR framing without mechanism is narrative, not explanation” (line 51), then layers task allocation, prediction-to-judgment, organizational redesign, market expansion, labor process/control, and institutional mediation (lines 55–75). It contrasts bounded firm/professional contexts—where augmentation is more likely—with settings lacking institutional buffers—where displacement and control intensification are more likely (line 191).

Its cross-sector table is followed by inference, not left to speak for itself (lines 195–210). It distinguishes extensive-margin employment, intensive-margin task/hours effects, and labor-share/distribution outcomes (lines 218–224), preventing contradictory metrics from being collapsed.

The most distinctive Insight move is the epistemic-label protocol:

The section distinguishes `Established Finding`, `Emerging Pattern`, `Conceptual Argument`, and `Analytical Hypothesis / Our Synthesis` (line 258).

For example, it calls the shift from routine/manual exposure to cognitive/language exposure an established cross-study pattern, then proposes “pattern-predictable versus embodied/contextual” as a better emerging axis (lines 264–266). It resolves an apparent freelance-population paradox through worker level, market level, timing, and platform institutions (lines 272–274). It labels the skill-compression extension as a hypothesis and candidly states:

> “No peer-reviewed study has yet tested these long-run predictions.”  
> — line 282

That sentence is high-value calibrated uncertainty: novelty is not disguised as established fact.

Policy follows the causal levers—new-task incentives, diffusion and competition, adjustment capacity, worker voice, and measurement—not a generic policy list (lines 334–354). Gaps are tied to unresolved mechanisms and missing levels of analysis (lines 362–370).

#### Readability and limitations

The report's many short analytic paragraphs and explicit roadmap (line 35) make a 16.9k-word report navigable. The major risk is overproduction: 50 headings and 592 lines can impose search cost, and the current leaderboard's Readability score (51.94) trails its other dimensions. It also has unusually low lexical hedging relative to length; the epistemic labels partly compensate, but claims outside the labeled section can sound categorical. Finally, its own methods caveat says high-quality working papers are excluded but “where essential, we reference them as contextual rather than primary evidence” (line 31). Task 72 says **only** journal articles, so contextual inclusion is still a literal source-class risk even when load-bearing claims remain journal-grounded.

### 3.2 Current #2: WhaleCloud-DocChain_0612

**Report:** [WhaleCloud current raw reports](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/raw_data/WhaleCloud-DocChain_0612.jsonl), record `id=72`.  
**Score:** overall 54.78; Comprehensiveness 55.14; Insight 55.33; Instruction Following 54.85; Readability 52.48 ([current CSV](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/leaderboard.csv)).

The report contains 59,282 characters, 7,580 alphanumeric words, 461 lines, 44 headings, 129 non-list prose paragraphs, and 35 table lines. Its outline moves from executive findings and methods to:

1. 4IR framing and definitions
2. theory evolution and three mechanisms
3. displacement/reinstatement and “bottom-biased” automation
4. a cross-revolution comparison
5. robot, software-AI, algorithmic-management, and GenAI evidence
6. sector chapters
7. a cross-industry matrix and five moderators
8. a comparison of why estimates diverge
9. skills, policy, future agenda
10. balanced challenges/opportunities
11. limitations

The exact fetched heading inventory, in order, is:

1. `# The Restructuring Impact of Artificial Intelligence on the Labor Market: A Literature Review`
2. `## Executive Summary`
3. `## 1. Background and Scope`
4. `### 1.1 Defining AI Within the Fourth Industrial Revolution`
5. `### 1.2 Scope and Methodology`
6. `## 2. Theoretical Foundations: From Skill Bias to Task Automation`
7. `### 2.1 The Evolution of Labor–Technology Theory`
8. `### 2.2 Skill-Biased Technological Change (SBTC)`
9. `### 2.3 The Task-Based Model: Autor, Levy & Murnane (2003)`
10. `### 2.4 Acemoglu & Restrepo's Automation/Reinstatement Framework`
11. `### 2.5 Acemoglu's "Simple Macroeconomics of AI" (2025)`
12. `### 2.6 "Bottom-Biased" Technical Change: An Emergent Framework`
13. `### 2.7 Comparison Across Industrial Revolutions`
14. `## 3. Mechanisms of AI-Driven Labor Market Restructuring`
15. `### 3.1 Task Automation: The Core Mechanism`
16. `### 3.2 The Displacement vs. Productivity Debate`
17. `### 3.3 Job Polarization: An Evolving Pattern`
18. `### 3.4 Augmentation vs. Substitution: The Occupational Dualism`
19. `### 3.5 Wage Effects and Inequality`
20. `### 3.6 The Entry-Level and Early-Career Displacement Channel`
21. `## 4. Industry-Specific AI Disruption`
22. `### 4.1 Manufacturing`
23. `### 4.2 Healthcare`
24. `### 4.3 Finance`
25. `### 4.4 Retail and E-Commerce`
26. `### 4.5 Transportation`
27. `### 4.6 Education`
28. `### 4.7 Professional Services (Legal, Accounting, Consulting)`
29. `### 4.8 Cross-Industry Comparative Analysis`
30. `## 5. The Disruptive Character and Scale of AI-Driven Labor Market Change`
31. `### 5.1 Quantitative Estimates of AI's Labor Market Impact`
32. `### 5.2 Generative AI's Distinctive Disruption Pattern`
33. `### 5.3 The Productivity Paradox of AI`
34. `### 5.4 Geographic Variation`
35. `## 6. Skill Demands, Reskilling Imperatives, and Policy Responses`
36. `### 6.1 Shifting Skill Demands`
37. `### 6.2 Reskilling and Upskilling Evidence`
38. `### 6.3 Policy Responses in the Academic Literature`
39. `### 6.4 Future Research Agendas`
40. `## 7. Balanced Assessment: Challenges and Opportunities`
41. `### 7.1 Challenges`
42. `### 7.2 Opportunities`
43. `## 8. Information Gaps and Limitations`
44. `## References`

The opening explicitly combines scope and answer:

> “Artificial intelligence, as the signature technology of the Fourth Industrial Revolution (4IR), is reconfiguring labor markets through mechanisms qualitatively distinct from previous technological waves.”  
> — WhaleCloud task 72, article line 7

The next lines state five findings: non-routine cognitive automation, a displacement/reinstatement shift, skill compression, labor-demand restructuring, and large industry variation (lines 9–13), followed by a conditional dual-channel synthesis (line 15).

Its theory section uses a visual evolution from skill-biased and routine-biased change to task allocation, displacement/reinstatement, and generative-AI exposure (lines 39–57). Lines 80–88 define three mechanisms, and lines 90–100 link the Acemoglu/Restrepo task model to a possible “bottom-biased” effect in which AI disproportionately helps lower-performing workers.

The report's strongest cross-industry move is a standardized table followed by five explicit moderators (lines 230–248): task structure, demand elasticity, regulation, the white-collar frontier, and developing-economy conditions. A second table explains that divergent estimates often answer different questions—exposure, task productivity, local employment, national employment, wage structure, or worker control—rather than treating them as direct contradictions (lines 254–267).

It then derives an emergent inversion:

Unlike prior waves centered on routine tasks, its synthesis argues that generative AI reaches non-routine cognitive work and can compress within-occupation performance differences (WhaleCloud task 72, article lines 102–114 and 269–301).

Compared with cellcog, WhaleCloud is shorter and more table-driven. It has more lexical uncertainty and a better current Readability score (52.48 versus 51.94), but its novel syntheses are less sharply separated by epistemic status.

### 3.3 Legacy #1: Qianfan / DuMate-DeepResearch

**Official report:** [Qianfan/DuMate task 72](https://raw.githubusercontent.com/baidubce/qianfan-deepresearch/main/reports/deepresearch_bench/72.md).  
**Official method description:** [DuMate README](https://github.com/baidubce/qianfan-deepresearch#readme) and [DuMate paper](https://arxiv.org/abs/2606.07299).  
**Score:** overall 58.03; Comprehensiveness 59.48; Insight 61.48; Instruction Following 53.87; Readability 54.34 ([official README lines 118–125](https://github.com/baidubce/qianfan-deepresearch#leaderboard-snapshot)).

#### Architecture

The official README states:

> “An evolving DAG expands from coarse goals into fine-grained research actions, with reflection, re-planning, backtracking, and parallel branching.”  
> — DuMate README lines 53–56

It uses an “outer Research Agent” that delegates to “inner Searcher Agents,” each with its own planning loop, to keep noisy retrieval away from global strategy (README lines 58–61).

And it makes evaluation criteria operational during generation:

> “Dynamically generated quality criteria act as test-time reasoning scaffolds for evidence-grounded synthesis and adaptive stopping.”  
> — README lines 63–65

This architecture plausibly produces the observed report: broad chapters are decomposed recursively, research can reopen when gaps appear, and the rubric is present before final writing. This is an inference from the official method plus report, not an ablation-proven causal claim.

#### Report structure and scoring moves

The task-72 report is extreme in scale: 560,868 characters, 73,383 alphanumeric words, 1,516 lines, 557 non-list prose paragraphs, 98 headings, and 109 table lines. Its ten-chapter architecture covers:

1. introduction, boundaries, questions, chapter map
2. systematic-review methodology and quality policy
3. conceptual/theoretical frameworks
4. aggregate employment/productivity/wage evidence
5. occupations, tasks, and skills
6. sector-by-sector restructuring
7. distributional and demographic outcomes
8. cross-national/institutional differences
9. workplace organization and job quality
10. policy, integrative synthesis, consensus, disagreement, emerging frontiers, limitations

The introduction does not assume the 4IR frame is self-evident:

The report treats AI as a central 4IR driver but says that framing is not self-evident and is contested (Qianfan task 72, lines 4–14).

It supplies explicit guiding questions and a chapter map (lines 28–52), then a PRISMA-like methods chapter with databases, search boundaries, selection rules, and quality priorities (lines 54–80). The theory chapter distinguishes four causal mechanisms and diagrams their interaction (lines 193–218).

The sector synthesis explicitly says its purpose is “more than enumeration” (lines 596–639). It identifies propagation mechanisms, compares structural drivers, and states calibrated propositions: within-sector variation can exceed between-sector variation; institutions alter technological effects; upstream changes propagate through supply chains; and platforms change matching/control channels. These are the exact sort of moves the 0.0800 cross-industry cell asks for.

The final synthesis states:

> “AI's labor-market footprint is not a single phenomenon characterized by a uniform set of magnitudes and directions, but a family of institutionally projected configurations”  
> — Qianfan task 72, line 1399

The rest of that sentence grounds those configurations in technological capability, organizational implementation, institutional context, and policy architecture.

It then gives six consensus claims (lines 1403–1413), persistent disagreements (lines 1415–1425), emerging frontiers (line 1427), and the conclusion that outcomes are “not technologically determined” (line 1429). The final central proposition is explicitly conditional, mediated, and heterogeneous (line 1449).

#### Critical compliance caveat

The report's methods claim journal-only evidence, but its own notes include working papers, IMF material, and a GitHub/blog source. Thus its visible method statement is not sufficient evidence of Instruction Following. The report demonstrates a winning **structure**, but it also demonstrates why the pipeline must mechanically enforce source-type/language constraints instead of letting prose self-certify them. Source: Qianfan task-72 footnotes and references in the [official report](https://raw.githubusercontent.com/baidubce/qianfan-deepresearch/main/reports/deepresearch_bench/72.md).

### 3.4 Legacy #2: ZTE-Nebula-DeepResearch

**Official report:** [ZTE task 72](https://raw.githubusercontent.com/Adlik/ZTE-Nebula-DeepResearch/main/reports/72.md).  
**Official method description:** [ZTE README](https://github.com/Adlik/ZTE-Nebula-DeepResearch#how-zte-nebula-deepresearch-works).  
**Score:** overall 57.27; Comprehensiveness 58.37; Insight 59.76; Instruction Following 54.06; Readability 54.66 (README lines 10–21).

#### Architecture

ZTE documents five modules:

1. hierarchical planning guided by a rubric and detailed subtasks;
2. end-to-end subagents executing sequentially or in parallel as a DAG;
3. integration of subagent reports with additional “summaries, research analysis, and conclusions”;
4. chapter-by-chapter checks for comprehensiveness and factual correctness that can trigger more research;
5. final structure and citation verification.

Those are verbatim-described functions at [README lines 43–54](https://github.com/Adlik/ZTE-Nebula-DeepResearch#how-zte-nebula-deepresearch-works). The crucial design difference from a one-pass plan/write system is step 4: final chapters can reopen research based on observed gaps.

#### Report structure and scoring moves

The task-72 report contains 253,301 characters, 32,794 alphanumeric words, 1,822 lines, 419 non-list prose paragraphs, 178 headings, and 324 table lines. It opens with a one-sentence thesis, abstract, and reading guide (lines 9–17), then elevates three insights before the long review:

- seniority-biased polarization;
- a productivity–displacement coupling rather than a simple trade-off;
- a policy–evidence asymmetry.

Those are stated at lines 21–28 and then tested across theory, occupations, industries, countries, and policy.

The theory section defines four channels and differentiates AI from earlier automation (lines 34–115). The industry chapter uses matrices, rankings, causal chains, and failure modes, then ends with a “chapter insight” rather than a sector recap (approximately lines 846–915). The closing section answers seven subtasks one by one (lines 1684–1705), gives audience-specific recommendations (lines 1707–1727), exposes limitations/uncertainty (lines 1731–1739), provides a core comparison and best practices (lines 1743–1756), and ends with future time horizons, observable variables, and open questions (lines 1760–1773).

This is a highly explicit rubric-coverage strategy: executive insights → full evidence → matrices → per-chapter insight → checklist-like final answers.

#### Critical compliance caveat

The report metadata explicitly includes “NBER Working Papers” (official report line 5), while task 72 requires only high-quality English journal articles. ZTE therefore shows that even a system with the legacy leaderboard's best Instruction-Following score among the top two can visibly violate the narrow source constraint. As with Qianfan, the lesson is enforcement, not imitation of the self-description.

### 3.5 Legacy top-ten: NVIDIA-AIQ/Nemotron

**Report:** [NVIDIA task-72 raw reports](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data/raw_data/nvidia-aiq-nemotron-gpt52-updated.jsonl), record `id=72`.  
**Score:** overall 55.95; Comprehensiveness 56.90; Insight 58.49; Instruction Following 52.89; Readability 53.43 ([legacy CSV](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data/leaderboard.csv)).

The report has 70,982 characters, 9,321 alphanumeric words, 428 lines, 47 headings, and 43 table lines. Its outline is unusually rubric-literal:

- executive summary;
- definition of restructuring across employment, composition, tasks, skills, wages, job quality;
- four AI channels;
- explicit “journal-only; high-quality” inclusion rules;
- task models, labor share, GPT dynamics, institutions;
- definitions and measurement, including a worked exposure-index example;
- robot, software-AI, algorithmic-management, and GenAI evidence;
- cross-industry evidence-strength map;
- distribution/governance/open questions;
- PRISMA-style screening narrative;
- conclusion and a separate forward-looking synthesis.

The report states the six restructuring dimensions in a numbered list (lines 15–21) and defines four distinct technology channels (lines 25–32). The mechanism section explains displacement, reinstatement, skill-biased change, organizational complements, diffusion lags, and institutional mediation (lines 47–79). In particular, it explains German/U.S. differences through works councils, bargaining, apprenticeships, retraining, unionization, and geographic segmentation rather than attributing them to the robot itself (line 79).

Its cross-industry matrix standardizes channel, outcome, evidence strength, mechanism, and representative journal anchors (lines 282–297). The next paragraph supplies the inference:

> “A consistent pattern is that industries differ less in whether tasks are affected and more in **how**: substitution, augmentation, or control.”  
> — NVIDIA task 72, line 300

It correctly disciplines exposure:

> “Exposure indices (including LLM exposure frameworks) should be interpreted as **upper-bound potential** under scenarios, not as forecasts of actual job losses”  
> — line 322

The same paragraph distinguishes technical feasibility from economic profitability, organizational readiness, and institutional permissibility.

The final forward-looking section turns gaps into measurable research designs: deployment data linked to worker outcomes, firm RCTs, regulatory natural experiments, service-sector causal identification, and spatial divergence (lines 391–401).

However, its source compliance is internally inconsistent. Lines 36–41 claim only English peer-reviewed journals, yet the prose uses McKinsey/IFR benchmarks (line 23), product-launch/user figures (line 32), FDA/NHTSA/OCC material (line 279), Gartner/Forrester estimates (line 300), and EU legal provisions (line 332). Some may be contextual rather than load-bearing research, but the criterion says “only,” so the clean solution is explicit source-role separation or exclusion, not an unconditional journal-only claim.

No public artifact located during this investigation documented the specific NVIDIA deep-research workflow that generated this report. The [NVIDIA NeMo Agent Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit) describes a general framework-agnostic agent toolkit, observability, evaluation, and optimization, but that is not enough to infer the report generator's concrete architecture. I therefore do not invent one.

## 4. Local named competitor outputs

These files are useful controlled comparators, but filenames such as `cellcog_7703.jsonl` must not be conflated with the current official cellcog-max report above.

### 4.1 `cellcog_7703.jsonl`

**Source:** `/home/polaris/wt/faithoff/third_party/deep_research_bench/data/test_data/cleaned_data/cellcog_7703.jsonl`, record `id=72`.

The report contains 52,036 characters, 7,719 alphanumeric words, 170 lines, 31 headings, 50 prose paragraphs, and median prose-paragraph length 124.5 words. Its useful moves are:

**Exact heading path:** Artificial Intelligence and the Restructuring of the Labor Market → Abstract → Scope, Methods, and Source Selection → AI as the Driver of the Fourth Industrial Revolution → Why AI is a general-purpose technology → scale and speed → Theoretical Frameworks → skill-biased change → task-based displacement/reinstatement/labor share → prediction machines → Measuring Exposure, Adoption, and Realized Outcomes → exposure theories → exposure ≠ adoption ≠ impact → Employment, Displacement, and Job Creation → occupational displacement → reinstatement/new tasks → firm/aggregate divergence → Wages, Skills, and Labor Share → recomposed skill demand → Sectoral Disruption → manufacturing → professional/financial/knowledge services → healthcare/education/care → creative/GenAI → Critical Synthesis → established → disagreement → unresolved → Implications and Research Agenda → mechanism-derived implications → evidence gaps. Source: local `cellcog_7703.jsonl`, article heading lines 1–168.

- an abstract and explicit methods/source-compliance section;
- a corpus inventory (“820 passages” and “279 sources” in its own text);
- planned sections for definitions, theory, technology channels, sectors, distribution, policy, and “Critical Synthesis”;
- many quantitative anchors.

But a line-by-line read reveals severe content-integrity problems:

- line 60 mixes labor-market material with unrelated social integration, sodium reformulation, and recidivism evidence;
- line 98 repeats a boilerplate sentence about “unit labels” seven times;
- lines 148 and 152 repeat the same boilerplate;
- source descriptions include obscure or apparently off-scope 2026 material despite the claimed high-quality-journal boundary.

This report demonstrates that outline completeness and citation volume can coexist with semantic contamination. It may look broad to a shallow judge, but it is not a model for grounded synthesis.

### 4.2 `claude-3-7-sonnet-latest.jsonl`

**Source:** `/home/polaris/wt/faithoff/third_party/deep_research_bench/data/test_data/cleaned_data/claude-3-7-sonnet-latest.jsonl`, record `id=72`.

The report has 19,470 characters, 2,867 words, 127 lines, 26 headings, 38 prose paragraphs, and median paragraph length 68.5 words. It is the cleanest short local comparator:

**Exact heading path:** Literature Review → Introduction → AI and 4IR → definition/context → industrial-revolution history → employment/displacement → projected displacement → job creation → recent studies → industries/occupations → healthcare → legal → education/knowledge work → polarization/inequality → jobs/skills → skill gaps → inequality → augmentation/replacement → complementarity → productivity → policy → education/training → labor policy/safety nets → ethics/governance → conclusion. Source: local `claude-3-7-sonnet-latest.jsonl`, article heading lines 1–119.

- exposure is distinguished from realized displacement (article line 31);
- displacement and new-job creation are balanced (lines 35–37);
- complementarity, decision support, prediction, and productivity channels are covered (lines 89–97);
- the conclusion is conditional rather than deterministic (lines 121–125).

Its weakness is depth: many headings contain short serial summaries rather than multi-study mechanisms or cross-industry reconciliation. It also uses World Economic Forum, IMF, and similar non-journal sources in prose, violating task 72's “only high-quality English journal articles” constraint.

### 4.3 `chatgpt_scoped.jsonl`

**Source:** `/home/polaris/wt/faithoff/third_party/deep_research_bench/data/test_data/cleaned_data/chatgpt_scoped.jsonl`, record `id=72`.

This is **not actually an answer to the full task-72 prompt**. It answers a narrower question about generative AI before June 2023 and explicitly includes working papers, preprints, and editorials. Its 20,116 characters, 2,764 words, 7 headings, and 12 table lines therefore cannot satisfy the required 4IR/general-AI/various-industry/journal-only breadth.

**Exact headings:** Generative AI and the Future Labor Market Before June 2023 → Scope and evidence base → Positive views → Negative views → Specific challenges → Future opportunities → Summary table of industry and occupational cases. Source: local `chatgpt_scoped.jsonl`, article heading lines 1–53.

Still, it exhibits three transferable prose habits:

- it states scope and evidence-strength limits immediately (article line 5);
- it says exposure is not displacement (line 7);
- it uses a comparative table and then synthesizes mechanisms and disagreements rather than treating values as directly commensurable (lines 43–66).

### 4.4 `champ_ourcorpus.jsonl`

**Source:** `/home/polaris/wt/faithoff/third_party/deep_research_bench/data/test_data/cleaned_data/champ_ourcorpus.jsonl`, record `id=72`.

This report has 18,481 characters, 2,591 words, 51 lines, 13 headings, 13 prose paragraphs, and median paragraph length 187 words. Its outline covers the requested domains, but the body is dense and source-serial. Claims recur across lines 19 and 23, and the entire cross-study synthesis is essentially one short paragraph at line 39.

**Exact headings:** literature-review title → Introduction → Theoretical Frameworks → Aggregate Employment → Wage Polarization/Inequality → Task Content/Skills → Sectoral Case Studies → Geographic Disparities → Workforce Transition/HRM → Cross-Study Synthesis → Conclusions/Gaps → Additional Corroborated Findings → Limitations. Source: local `champ_ourcorpus.jsonl`, article heading lines 1–49.

Its limitations paragraph is commendably candid: only 2% of sources are T1 primary studies, while 69% are T3 review-tier material (`champ_ourcorpus.jsonl`, article line 51).

That candor, however, establishes a task failure: the corpus does not meet the journal-quality constraint. A local audit records an overall RACE score of 0.3671 for this candidate; that value is run-specific and should not be compared numerically with public leaderboard percentages without confirming identical judge/reference settings.

### 4.5 Structural comparison

| Report | Approx. words | Headings | Prose paragraphs | Median prose paragraph | Sentence-like proxy |
|---|---:|---:|---:|---:|---:|
| Frozen reference 72 | 8,848 | 33 | 56 | 45 | 215 |
| Local cellcog_7703 | 7,719 | 31 | 50 | 124.5 | 125 |
| Local Claude 3.7 | 2,867 | 26 | 38 | 68.5 | 105 |
| Local ChatGPT scoped | 2,764 | 7 | 20 | 109.5 | 84 |
| Local champ_ourcorpus | 2,591 | 13 | 13 | 187 | 75 |
| POLARIS `faithoff_t72` | 7,942 | 14 | 14 | 608.5 | 199 |

Source for every row: the corresponding local cleaned-data JSONL, record `id=72`; counts were computed directly from the article strings. Again, these figures describe form. The local cellcog file proves that counts cannot establish quality.

## 5. Related architectures and papers: what is grounded, and what is not

These papers are not all leaderboard systems and do not all expose task-72 reports. Their value is architectural: they independently converge on mechanisms visible in the winners.

### 5.1 WebWeaver

The paper's abstract identifies two failures: static pipelines that separate planning from evidence acquisition, and monolithic generation over redundant/irrelevant evidence. Its solution is:

The planner operates by “iteratively interleaving evidence acquisition with outline optimization”; the writer then performs hierarchical, section-by-section retrieval and writing ([WebWeaver, arXiv:2509.13312](https://arxiv.org/abs/2509.13312)).

Concrete report implication: evidence can alter the outline; each section retrieves only its evidence basket; citation hallucination and lost-in-context risks are reduced. This matches cellcog's well-populated mechanism/novelty sections and the leaders' ability to reopen gaps.

### 5.2 AgentCPM-Report

AgentCPM rejects a fixed plan-then-write boundary. Its “Writing As Reasoning Policy” dynamically revises the outline while alternating:

> “Evidence-Based Drafting and Reasoning-Driven Deepening.”  
> — [AgentCPM-Report, arXiv:2602.06540](https://arxiv.org/abs/2602.06540)

It trains this behavior through cold start, atomic-skill reinforcement learning, and holistic pipeline reinforcement learning. The paper specifically reports substantial Insight gains. The grounded design lesson is not “use an 8B model”; it is that drafting exposes knowledge gaps and synthesis opportunities that should trigger deeper research and outline change.

### 5.3 DualGraph

DualGraph separates:

> “what the agent knows from how it writes.”  
> — [A Tale of Two Graphs, arXiv:2602.13830](https://arxiv.org/abs/2602.13830)

An Outline Graph tracks report structure; a Knowledge Graph stores entities, concepts, and relationships. Joint topology/structure signals generate targeted searches. That is directly relevant to task 72: the outline can ensure coverage of sectors/effects while the knowledge graph detects missing causal links, disagreements, and cross-sector relations.

### 5.4 DRAGged into Conflicts

This paper supplies a taxonomy of retrieved-source conflicts and desired responses, then finds:

The experiments find that models “often struggle to appropriately resolve conflicts,” while explicit conflict reasoning “significantly improves” response quality ([DRAGged into Conflicts, arXiv:2506.08500](https://arxiv.org/abs/2506.08500)).

This grounds a core winner habit: do not flatten U.S. local-displacement, German reallocation, cross-country productivity, exposure, and task-experiment findings into one average. Classify whether differences are direct conflict, different outcomes, different levels, different periods, or different institutional settings.

### 5.5 Requested systems/papers without a fetchable report or sufficient method artifact

- **Zhipu GLM deep research:** the public legacy leaderboard score is available, but I did not locate an actual task-72 report or an official method paper in the accessible artifacts. No structure claim is made.
- **AgentCPM-Report, WebWeaver, DualGraph, DRAGged into Conflicts:** papers were accessible, but their task-72 generated reports were not found in the official DeepResearch-Bench Space paths inspected. I report architecture only.
- **NVIDIA AI-Q:** the report is accessible; the exact generator architecture is not publicly established by the general NeMo Agent Toolkit README.
- **Baidu Qianfan:** this is the DuMate/Qianfan system above; both report and official method description are accessible.
- **ZTE-Nebula:** both report and official five-module description are accessible.

This availability boundary is important: method architecture cannot be reverse-engineered confidently from prose style alone.

## 6. Per-sub-item WIN MAP — all 25 task-72 RACE cells

The cells below are ordered by absolute task coefficient, starting with the two 0.0800 and two 0.0725 cells. “Winning move” means a grounded report behavior aligned with the criterion, not a claim that the behavior's isolated causal effect was experimentally measured.

### 6.1 Highest-leverage cells

#### 1. Insight — mechanisms of restructuring (0.0800)

**Winning move:** define competing causal channels, trace intermediate steps, name moderators, and state the conditions under which one channel dominates.

- Reference: “displacement effect” versus “reinstatement effect” (reference 72, lines 31–38), followed by substitution/complementarity/augmentation and organizational co-evolution (lines 54–60).
- Cellcog: “4IR framing without mechanism is narrative, not explanation” and then layers task, prediction/judgment, organization, market, labor-process, and institutional channels (current cellcog task 72, lines 51–75).
- NVIDIA: task substitution/creation plus firm complements and institutional mediation; German redeployment versus sharper U.S. local displacement is explained through works councils, bargaining, apprenticeships, retraining, unionization, and segmentation (NVIDIA task 72, lines 47–79).

**Concrete output pattern:** `AI capability → affected task → substitution/augmentation/control → workflow/firm response → output/demand/new tasks → employment/wage/skill/job-quality result`, with moderators and time horizon attached at each arrow.

#### 2. Insight — critical cross-industry synthesis (0.0800)

**Winning move:** use the same comparison dimensions across sectors, then explain variation, disagreements, and common patterns.

- Reference: sectors share vulnerability of predictable tasks and complementarity of creativity/judgment (line 141); outcomes vary by technology, horizon, geography, level, method, and outcome (line 81).
- WhaleCloud: after its industry table, it names task structure, demand elasticity, regulation, the white-collar frontier, and developing-economy conditions as five moderators (task 72, lines 230–248).
- NVIDIA: “industries differ less in whether tasks are affected and more in **how**: substitution, augmentation, or control” (task 72, line 300).
- Qianfan: the sector chapter says it aims at “more than enumeration” and derives cross-sector propositions about within-sector variation, institutions, propagation, and platforms (task 72, lines 596–639).

**Concrete output pattern:** a sector × mechanism/outcome/evidence-strength/moderator matrix, followed by 3–6 explicit propositions that explain the matrix. A table without the inference paragraph does not complete the cell.

#### 3. Comprehensiveness — restructuring-dimension breadth (0.0725)

**Winning move:** operationalize “restructuring” before research and give every dimension an evidence destination.

- NVIDIA lists employment, occupational/industrial composition, task content, skills, wages/inequality, and job quality/bargaining power (task 72, lines 15–21).
- Reference allocates dedicated sections to displacement/creation, aggregate employment, wages/polarization, workforce needs, labor share, inequality, skills, productivity, and policy (reference outline, sections 3–7).
- ZTE's closing section answers seven subtasks one by one (task 72, lines 1684–1705).

**Concrete output pattern:** a coverage ledger keyed to job creation, displacement, task transformation, skills, wages, labor share/inequality, productivity/output, job quality/control, occupational composition, geography, and time. Populate each with representative evidence and cross-links; do not hide missing cells under “labor-market impact.”

#### 4. Comprehensiveness — industry scope (0.0725)

**Winning move:** cover materially different task/institution regimes, not many synonymous sectors.

- Reference covers manufacturing/logistics; healthcare/finance/transport; creative/marketing/services, then synthesizes common task patterns (lines 121–149).
- NVIDIA's matrix covers manufacturing, professional/ICT, platforms, healthcare, finance, public administration, and creative/media with a common schema (task 72, lines 282–297).
- Cellcog compares manufacturing, professional/knowledge work, platform/freelance work, and public/care work, then applies the same institutional/worker-level moderators (current report, lines 195–252).

**Concrete output pattern:** select sectors to span physical versus cognitive tasks, regulated versus lightly regulated settings, salaried versus platform work, high versus low adoption complements, and advanced versus developing institutions.

#### 5. Insight — emergent themes, linkages, and novel insight (0.0640)

**Winning move:** derive a new, falsifiable relationship from multiple evidence baskets and label its epistemic status.

- Reference: AI's automation of cognition paradoxically raises the value of social, creative, and judgment skills (line 184); distribution of gains is a central political mechanism, not a secondary outcome (line 172).
- Cellcog: “pattern-predictable versus embodied/contextual” as a new exposure axis (lines 264–266); freelance decline versus population-level effects reconciled through levels/institutions (lines 272–274); skill compression explicitly labeled a hypothesis and accompanied by “No peer-reviewed study has yet tested these long-run predictions” (line 282).
- WhaleCloud: connects GenAI to a non-routine/cognitive exposure inversion and performance compression (lines 102–114, 269–301).

**Concrete output pattern:** `Evidence A + Evidence B + moderator C → supported inference`; separately label an established finding, emerging pattern, conceptual argument, and analytical hypothesis, and state the missing test. Novelty without epistemic labeling risks unsupported invention.

### 6.2 Next-highest content and compliance cells

#### 6. Instruction Following — fully on-topic (0.0500)

**Winning move:** define scope, use a question-to-section map, and exclude tangents at both retrieval and composition.

- Reference stays on AI/4IR/labor restructuring throughout its 33-heading outline.
- Cellcog provides an explicit roadmap (current report line 35).
- Counterexample: local `cellcog_7703` line 60 introduces sodium reformulation and recidivism; it is broad but not on-topic.

**Concrete output pattern:** every paragraph should answer a task-72 coverage item, mechanism, comparison, limitation, or implication. Off-topic material is deleted only after semantic confirmation; it is not rescued by a citation.

#### 7. Insight — integration with the 4IR frame (0.0480)

**Winning move:** use 4IR properties as explanatory variables, not as an introductory label.

- Reference links AI to 4IR speed, scope, system impact, interconnection, and physical/digital/biological convergence (lines 7–11).
- Cellcog critiques technological determinism and says 4IR without mechanism is narrative (lines 49–51).
- NVIDIA treats AI as a general-purpose prediction/decision capability embedded across sectors and workplace functions (lines 23–32).

**Concrete output pattern:** explain why general-purpose applicability, cognitive reach, low diffusion friction, data/network complementarity, and cyber-physical integration alter pace, breadth, organizational redesign, and institutional pressure.

#### 8. Insight — implications and future agenda (0.0480)

**Winning move:** derive intervention and research priorities from the unresolved causal chain.

- Reference separates education/reskilling, safety nets, tax/regulation, and evidence gaps (sections 7 and 8.3; lines 300–307).
- NVIDIA proposes linked deployment/worker data, firm RCTs, regulatory natural experiments, service-sector causal identification, and spatial analysis (lines 391–401).
- Cellcog derives new-task incentives, worker voice, adjustment capacity, competition/diffusion, and measurement priorities from its mechanisms (lines 334–370).

**Concrete output pattern:** for each recommendation, state the mechanism it changes, target population, trade-off, evidence strength, and testable outcome.

#### 9. Comprehensiveness — disruptive character and scale (0.0435)

**Winning move:** triangulate scale across exposure, realized outcomes, diffusion speed, time horizon, and system reach; do not substitute a single headline forecast.

- Reference qualifies disruption as potentially “more pervasive and rapid” because AI reaches cognition, while still varying by sector/task (line 149).
- NVIDIA distinguishes exposure as “upper-bound potential” from realized job loss (line 322).
- Cellcog uses separate empirical eras and levels of analysis (lines 81–111).

**Concrete output pattern:** report potential exposure, observed task productivity, realized employment/wage evidence, adoption/diffusion, and uncertainty as different quantities.

#### 10. Comprehensiveness — literature depth and representativeness (0.0435)

**Winning move:** cover theories, causal and descriptive methods, countries, sectors, worker groups, outcomes, and dissenting findings; expose selection method.

- Qianfan includes guiding questions, databases, boundaries, inclusion/quality rules, and chapter map (lines 28–80).
- Cellcog states an approximately 96-journal-article scope and disciplinary bridge (lines 7 and 75).
- NVIDIA exposes 26 synthesized articles and eight core anchors (lines 36–41, 363–375).

**Concrete output pattern:** a method block plus evidence map by design/setting/outcome, with explicit gaps. Caveat: Qianfan and NVIDIA both include non-journal contextual material despite journal-only claims, so counts and self-certification are not enough.

#### 11. Instruction Following — explicitly AI as a 4IR driver (0.0375)

**Winning move:** put the relationship in the thesis and revisit it analytically.

- Reference calls AI a “central driving force” of 4IR (line 9).
- NVIDIA's title is “AI-Driven Labor-Market Restructuring in the Fourth Industrial Revolution,” and line 23 identifies AI as a core 4IR technology.

**Concrete output pattern:** exact explicit sentence in introduction, then mechanism evidence in theory/sector/conclusion.

#### 12. Instruction Following — explicitly significant disruption (0.0375)

**Winning move:** use the requested significance framing but qualify its dimensions.

- Reference frames speed/scope/system impact (line 7) and broad cognitive reach (line 149).
- Cellcog states sharply heterogeneous but material effects across technology, sector, institution, skill, and level (line 9).

**Concrete output pattern:** “significant” must be unpacked as magnitude, breadth, pace, distribution, and institutional consequence; avoid deterministic mass-unemployment prose.

#### 13. Instruction Following — across various industries (0.0375)

**Winning move:** make sector variation an organizing axis, not a list of examples.

- NVIDIA's cross-industry table and interpretation (lines 282–300).
- WhaleCloud's sector table plus five moderators (lines 230–248).

**Concrete output pattern:** at least one section and one synthesis artifact devoted explicitly to industry comparison, using representative—not repetitive—industries.

#### 14. Instruction Following — only high-quality journal articles (0.0375)

**Winning move:** enforce source type and quality at retrieval/selection and surface an auditable methods statement.

- NVIDIA states: “Only English-language, peer-reviewed journal articles are cited” and prioritizes top economics, management, and multidisciplinary journals (lines 34–41).
- Qianfan exposes search/quality rules (lines 54–80).
- Counterevidence: NVIDIA nevertheless uses industry/government/legal material in prose; Qianfan uses working papers/IMF/blog material; ZTE explicitly includes NBER working papers. These are visible violations of “only.”

**Concrete output pattern:** each load-bearing source has verified publication type, venue, peer-review status, DOI/journal landing page, and source role. Non-journal context must be excluded for this task or separately disclosed if the task permits it—it does not here.

### 6.3 Remaining Comprehensiveness, Instruction, and Readability cells

#### 15. Comprehensiveness — balanced positive and negative impacts (0.0290)

**Winning move:** analyze how the same mechanism can produce benefit and harm under different conditions.

- Reference's “promise and peril” tension (line 19) is resolved through moderators (lines 194–207).
- NVIDIA pairs displacement with output expansion/new tasks and productivity with labor-share/inequality effects (lines 49–64, 308–324).

**Concrete output pattern:** benefit/harm matrix by stakeholder and time horizon, then identify distribution—not net aggregate alone.

#### 16. Comprehensiveness — 4IR grounding (0.0290)

**Winning move:** define the term, distinguish the current wave from earlier industrial/IT automation, and connect definition to task scope.

- Reference lines 7–11.
- WhaleCloud's cross-revolution comparison (task 72, lines 102–114).

**Concrete output pattern:** definition + historical contrast + why the contrast changes the labor question.

#### 17. Readability — language quality (0.0280)

**Winning move:** short analytic units, explicit referents, controlled terminology, and calibrated modality.

- Reference median prose paragraph is 45 words and repeatedly uses relationship-bearing transitions.
- Cellcog uses epistemic labels rather than vague hedges (lines 258 onward).
- Counterexample: `faithoff_t72` has a 608.5-word median prose paragraph.

**Concrete output pattern:** one main inferential move per paragraph; define acronyms and avoid raw retrieval fragments.

#### 18. Readability — overall structure/roadmap/thematic headings/synthesis conclusion (0.0280)

**Winning move:** announce the argument, mirror the coverage map in headings, and close with consensus/disagreement/gaps.

- Reference task 100 provides a literal section-by-section roadmap (line 19).
- Reference task 72 ends with “Areas of Consensus,” “Areas of Disagreement,” and “Gaps and Future Research.”
- Cellcog has an explicit roadmap (line 35) and a separate contested-debates section.

**Concrete output pattern:** executive thesis → definitions/method → mechanisms → evidence → comparisons → synthesis → implications/gaps.

#### 19. Instruction Following — literature-review form (0.0250)

**Winning move:** synthesize a body of studies by theme/method/debate, not provide an essay or annotated bibliography.

- Reference organizes by theoretical lens, empirical outcome, sector, debate, and gap.
- Qianfan supplies a systematic-review method and final consensus/disagreement.

**Concrete output pattern:** source selection, thematic synthesis, comparative appraisal, limitations, and research agenda.

#### 20. Instruction Following — only English journal articles (0.0250)

**Winning move:** verify both language and publication type per source.

- NVIDIA explicitly states English-language journal inclusion (lines 34–41).
- Cellcog states approximately 96 English peer-reviewed articles (line 7).
- The leaders' source-type violations show that a prose claim does not prove compliance.

**Concrete output pattern:** metadata validation and an exception count of zero; language detection alone is insufficient because an English working paper still fails.

#### 21. Readability — paragraph cohesion and transitions (0.0210)

**Winning move:** transitions encode logic—contrast, cause, scope, time, level, or reconciliation.

- Reference: “Temporal lags and scale mismatches help reconcile some contradictions” (line 100).
- NVIDIA: line 300 moves from industry inventory to a common substitution/augmentation/control pattern.

**Concrete output pattern:** start with the proposition, integrate evidence, state the relation to prior evidence, end with implication/moderator.

#### 22. Readability — sourced information synthesis; avoid serial summaries/density/redundancy (0.0210)

**Winning move:** consolidate studies into claim baskets and explicitly compare them.

- Reference line 81 explains why studies differ rather than listing findings.
- WhaleCloud's lines 254–267 distinguish the questions behind divergent estimates.
- Counterexamples: local Claude's many short serial source sections; `champ_ourcorpus` repeated claims and one-paragraph synthesis; `cellcog_7703` boilerplate repetitions.

**Concrete output pattern:** organize paragraphs around claims/contrasts, not author names. Keep all corroborating citations in a basket without repeating the claim.

#### 23. Readability — data/evidence clarity and tables (0.0140)

**Winning move:** tables use shared dimensions and are followed by interpretation.

- NVIDIA's channel comparison records affected tasks/workers, mechanism, evidence, gaps, geography, institutions, and policy (lines 336–350).
- Reference task 100's Table 2 directly compares benefits and harms on the same relational dimensions (lines 112–123).

**Concrete output pattern:** use tables for exact repeated-field comparison; never dump a table without prose explaining the dominant patterns and exceptions.

#### 24. Readability — layout consistency (0.0140)

**Winning move:** stable heading depth, repeated table schemas, consistent labels, and separation of evidence from synthesis.

- Reference task 72 uses eight numbered top-level sections and consistent numbered subsections.
- ZTE uses repeated chapter artifacts—matrix, failure modes, chapter insight, limitations.

**Concrete output pattern:** no orphan heading, broken table, heading-depth jump, or repeated boilerplate. The reference's blank source-table cells are a defect to avoid.

#### 25. Readability — audience fit and term explanation (0.0140)

**Winning move:** define technical terms before using them and translate measures into interpretation.

- Reference defines 4IR, displacement, reinstatement, substitution, complementarity, and augmentation before empirical sections (lines 7–60).
- NVIDIA distinguishes robots, software AI, algorithmic management, and GenAI, then demonstrates an exposure index with a worked example (lines 25–32, 83–138).

**Concrete output pattern:** definition → intuition/example → limitation. Do not assume the reader knows exposure versus realized outcome or local versus aggregate effects.

## 7. FACT WIN MAP — all 13 FACT surfaces from the 52-item inventory

FACT standings cannot be inferred for the current GPT-5.5 leaders because the official CSV displays `-` for both FACT columns ([current leaderboard CSV](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data_gpt55/leaderboard.csv)). The map below therefore applies the executable mechanics established in `SCORING_SPEC.md` lines 162–183 to concrete report design. It does not claim an unavailable leaderboard result.

### 40. Attach citations at exact claim locations

**Move:** cite immediately after the smallest complete factual proposition. A bibliography-only source produces no extractable pair (`SCORING_SPEC.md`, lines 168–171).

**Winner example:** NVIDIA places `[5]` directly after its robot employment/wage estimate and `[6]` after the cross-country productivity estimate (NVIDIA task 72, line 7), with DOI URLs in the source list (lines 406–410). Qianfan and ZTE also use dense inline markers in their official reports. Whether each pair validates is a separate support question.

### 41. Use extractable citation forms and real URLs

**Move:** use `[n]` tied to a URL-bearing reference or `[Title](URL)`; avoid opaque author-year text without a URL mapping. FACT recognizes four forms and requires a URL (`SCORING_SPEC.md`, lines 168–171).

**Winner example:** NVIDIA's numbered in-text markers map to DOI/journal URLs, e.g. Acemoglu–Restrepo DOI entries at report lines 406–410.

### 42. Make each cited claim complete and understandable

**Move:** the sentence surrounding a marker must express the fact, population, measure, direction, and context; do not cite a fragment such as “by 0.42%.”

**Winner example:** NVIDIA line 7 states the unit (“each additional robot per thousand workers”), outcomes (employment-to-population ratio and wages), magnitudes, and U.S. commuting-zone setting before `[5]`.

### 43. Use reachable URLs whose page text can be fetched

**Move:** prefer stable DOI/journal full-text/abstract URLs that Jina can retrieve; preflight reachability. Unreachable pages become `unknown` and disappear from the executable denominator and supported count (`SCORING_SPEC.md`, lines 173–177, 178–181).

**Winner example:** NVIDIA's core references use DOI or journal URLs (report lines 406–410). This is a reachability-oriented habit, not proof that every URL succeeds through Jina today.

### 44. Ensure source text supports at least part of the exact attached statement

**Move:** preserve source-specific wording and numeric context. FACT accepts partial support and rounding, but a narrower atomic sentence is less ambiguous (`SCORING_SPEC.md`, lines 174–176).

**Winner example:** the robot estimate in NVIDIA line 7 is attached to the named robot study `[5]`; the reference entry identifies Acemoglu and Restrepo's “Robots and Jobs: Evidence from US Labor Markets” with its JPE DOI (line 410). Actual validation still requires fetching the page content.

### 45. Avoid sources containing none of the statement's facts/data

**Move:** remove decorative or topic-adjacent citations. An unsupported pair adds to the precision denominator but not the supported numerator (`SCORING_SPEC.md`, lines 175–177).

**Counterexample:** local `cellcog_7703` line 60 mixes unrelated sodium-reformulation and recidivism material into labor-market prose. Citation presence cannot repair semantic mismatch.

### 46. Increase unique supported statement–URL pairs

**Move:** widen **supported evidence**, not citation-marker volume. Each retained unique supported statement–URL pair raises effective citations linearly (`SCORING_SPEC.md`, lines 178–181).

**Winner habit:** Qianfan and cellcog cover mechanisms, outcomes, sectors, countries, and debates with inline sourcing across distinct propositions. The relevant transferable structure is many atomic evidence-bearing propositions; their exact FACT yield is unavailable here.

### 47. Avoid exact duplicate same-URL claims

**Move:** consolidate repeated claim/source pairs into one claim basket. Exact semantic duplicates for a URL are intended to deduplicate (`SCORING_SPEC.md`, lines 171–173).

**Counterexamples:** local `champ_ourcorpus` repeats claims at article lines 19 and 23; local `cellcog_7703` repeats boilerplate at line 98 and again near lines 148/152. Repetition raises density but not unique-pair value.

### 48. Multiple independent supporting URLs for one fact can each count

**Move:** when independent studies support the same claim, attach all relevant URLs to the same atomic proposition. One fact citing `k` URLs becomes `k` pairs (`SCORING_SPEC.md`, lines 168–170, 178–181).

**Winner habit:** the strongest synthesis paragraphs juxtapose multiple study settings rather than selecting one exemplar—for example, cellcog's U.S., German, Finnish, and meta-analytic contrast (current task 72, lines 21–23). To turn that RACE habit into FACT value, each study-specific proposition must carry its own real URL.

### 49. Multiple distinct supported facts from one source can each count

**Move:** if one study supports several genuinely different results, write separate atomic claims; grouping is by URL but validation occurs per fact (`SCORING_SPEC.md`, lines 171–176, 180–181).

**Winner example:** NVIDIA line 7 distinguishes employment and wage effects from one robot study. Splitting them into separate sourced sentences would make their support boundaries clearer while retaining the same URL.

### 50. Do not rely on uncited factual abundance to improve FACT

**Move:** cite all score-worthy empirical propositions. Uncited factual claims are invisible to FACT; there is no citation-recall metric (`SCORING_SPEC.md`, lines 178–181).

**Implication:** the frozen reference's 215 sentence-like propositions and 66 numeric-token occurrences establish no FACT value because the cleaned artifact contains no inline URL mappings. RACE quality and FACT extraction are separate.

### 51. Do not assume high source prestige improves FACT

**Move:** optimize textual support and reachability for FACT; enforce journal quality separately for task-72 Instruction Following. FACT has no credibility, prestige, recency, or primary-source component (`SCORING_SPEC.md`, lines 178–181).

**Implication:** an AER/JPE citation can fail FACT if attached to the wrong statement; a low-prestige page can pass FACT if it contains the text. The task nevertheless separately requires high-quality journal sources.

### 52. Do not optimize RACE Overall by citations alone

**Move:** maintain two independent acceptance surfaces: RACE content/analysis after citation stripping, and FACT supported-pair precision/abundance on raw output. `RACE Overall` does not include FACT (`SCORING_SPEC.md`, lines 162–167).

**Winner evidence:** high-ranking reports devote substantial prose to mechanisms, sector comparisons, epistemic synthesis, and conclusions, not just citations. Their observable RACE strength is consistent with the content cells that survive cleaning; citation apparatus is stripped before RACE (`SCORING_SPEC.md`, lines 144–154).

### FACT operational cautions

1. Under executable code, `unknown` and validation-error groups are excluded; `unsupported` hurts micro precision; zero-citation tasks are skipped. The published paper's macro formula differs (`SCORING_SPEC.md`, lines 165–183).
2. FACT accepts partial support and rounding. That makes atomic claims prudent even though the validator is permissive (`SCORING_SPEC.md`, lines 174–181).
3. There is no uncited-hallucination penalty, citation recall, or independent truth check beyond page-text support (`SCORING_SPEC.md`, lines 178–181). The pipeline's faithfulness gates must remain stricter than the benchmark.

## 8. Cross-report patterns — ranked by apparent RACE impact

“Apparent impact” is ranked from the task-72 coefficients plus recurrence in the frozen reference and accessible leaders. It is not a causal ablation.

### 1. Causal mechanisms with moderators — highest

**Why ranked first:** mechanism analysis is one of the two largest cells (0.0800). Every strong report names displacement, augmentation/complementarity, reinstatement/new tasks, output/productivity, organizational redesign, and institutional mediation. Reference lines 31–60, cellcog lines 51–75, NVIDIA lines 47–79, and Qianfan lines 193–218 all do this.

**What lower reports lack:** local Claude and champ often state study findings without completing the path from task change through organization/demand to labor outcome.

### 2. Comparative synthesis that explains heterogeneity — tied highest

**Why:** the second 0.0800 cell explicitly penalizes catalogs. Reference line 81 gives six sources of heterogeneity; WhaleCloud lines 230–267 standardize sector moderators and measurement differences; NVIDIA line 300 compresses sectors into substitution/augmentation/control; Qianfan lines 596–639 derive propositions.

**What lower reports lack:** a section titled “synthesis” is not enough. `champ_ourcorpus` has one short synthesis paragraph; local Claude has many independent summaries.

### 3. Coverage architecture for dimensions and industries

**Why:** the two 0.0725 cells reward dimension and industry breadth. Leaders define coverage dimensions early, build them into the outline, and audit them with matrices/final answers (NVIDIA lines 15–21; ZTE lines 1684–1705).

**What lower reports lack:** broad headings may exist, but missing evidence is not detected and research is not reopened.

### 4. Epistemically labeled novelty

**Why:** emergent themes carry 0.0640, but unsupported novelty is dangerous. Cellcog's four-way protocol—Established Finding, Emerging Pattern, Conceptual Argument, and Analytical Hypothesis / Our Synthesis (lines 258–326)—is the clearest winning pattern; the sentence admitting no direct test (line 282) is especially strong.

**What lower reports lack:** they either avoid novel synthesis or present an inference with no boundary between source finding and author deduction.

### 5. Separate levels, outcomes, and time horizons

**Why:** this is how winners resolve contradictions. Local worker/firm/region/nation, exposure/productivity/employment/wage/control, and near-/medium-/long-term results cannot be pooled. Reference line 100, cellcog line 111, WhaleCloud lines 254–267, and NVIDIA line 322 all enforce this.

### 6. Mechanism-derived policy and research design

**Why:** implications carry 0.0480 and emerge throughout the leaders. NVIDIA lines 391–401 specify data/designs; cellcog lines 334–370 link policy to new tasks, institutions, diffusion, and worker voice.

**What lower reports lack:** generic “reskill and regulate” advice unconnected to a diagnosed channel.

### 7. Methods and source-boundary transparency

**Why:** representative literature is 0.0435 and the two source restrictions total 0.0625. Cellcog, Qianfan, and NVIDIA all expose selection boundaries.

**Critical qualification:** all three visible legacy leaders examined here have at least some source-boundary inconsistency. The pattern to copy is auditability; the defect to fix is self-certified compliance without mechanical enforcement.

### 8. Tables as reasoning interfaces

**Why:** direct readability weight is only 0.0140, but well-designed matrices also enable the two 0.0800 synthesis/mechanism cells. NVIDIA's tables encode mechanism, evidence strength, gaps, geography, institutions, and policy; WhaleCloud follows tables with explicit patterns.

**What lower reports lack:** no common comparison schema, or tables left uninterpreted.

### 9. Roadmap, short analytic paragraphs, and layered summaries

**Why:** structure/language/paragraph/synthesis readability totals 0.0980. The reference's median 45-word paragraph and 33-heading hierarchy are dramatically more navigable than POLARIS's 608.5-word median.

**Qualification:** more headings are not automatically better. Cellcog's current Readability is its lowest dimension, and ZTE's 178 headings risk fragmentation. The useful unit is a coherent thematic hierarchy with one inferential move per paragraph.

### 10. Forward-looking but falsifiable analysis

**Why:** leaders state what evidence is missing and what observation would resolve it. Reference lines 300–307, cellcog lines 362–370, NVIDIA lines 391–401, and ZTE lines 1760–1773 all do this.

## 9. What POLARIS currently does differently — brief Phase-3 handoff

**Source:** `/home/polaris/wt/faithoff/third_party/deep_research_bench/data/test_data/cleaned_data/faithoff_t72.jsonl`, record `id=72`.

The POLARIS task-72 output is not thin: it has 52,671 characters, 7,942 alphanumeric words, 14 headings, and a conservative 199 sentence-like units. Its strongest sections are:

- a task-based displacement/productivity/reinstatement explanation (article line 11);
- substantial robot, exposure, GenAI-productivity, country, skill, industry, and policy evidence (lines 15–39);
- an explicit “Cross-Study Synthesis and Contradictions” section (lines 41–43);
- candid source telemetry (line 55).

The highest-leverage gaps are visible without a full Phase-3 root-cause audit:

1. **Paragraph architecture:** only 14 prose paragraphs, median 608.5 words and maximum 838, versus reference median 45. This directly impairs the 0.0280 language, 0.0210 cohesion, and 0.0210 sourced-synthesis surfaces and makes reasoning boundaries hard to inspect.
2. **Coverage is evidence-dense but not matrixed:** sectors appear in one enormous case-study paragraph (line 35), without a common mechanism/evidence-strength/moderator table or multiple sector subsections. This weakens both 0.0725 industry breadth and 0.0800 critical synthesis despite raw sector volume.
3. **Synthesis is too late and too compressed:** line 43 contains valuable contrasts, but one wall paragraph must carry consensus, disagreement, measurement differences, country variation, and implications. Leaders allocate multiple sections and explicit epistemic labels.
4. **No tables:** repeated quantitative fields and sector comparisons remain prose, forfeiting the clarity and reasoning leverage seen in NVIDIA/WhaleCloud.
5. **Source constraint failure is self-disclosed:** line 55 says only 4% of sources are T1, 1% T2, 25% unknown; the prompt requires only high-quality English journal articles. The report also includes obvious policy/industry/working-paper material in lines 7–51. This is a direct 0.0375/0.0250 Instruction risk.
6. **Retrieval artifacts leak into prose:** line 27 begins mid-word (“neously emerge”), line 47 begins mid-word (“hare of people”), and line 51 opens with a pasted Stanford page header. These are concrete language/layout defects.
7. **Novelty is not epistemically tagged:** the report makes cross-study conclusions but does not distinguish established findings, emerging patterns, conceptual arguments, and analytical hypotheses as cellcog does.
8. **No explicit methods/selection workflow:** the opening describes span grounding, but not databases, inclusion dates, journal/language verification, screening, or study-design balance.

The main Phase-3 question is therefore not “retrieve more.” It is where breadth and evidence baskets fail to become section-scale, comparison-scale, and epistemically labeled synthesis—and where source-class enforcement fails before composition.

## 10. Executive summary — highest-leverage grounded patterns

1. **Build the mechanism before the prose.** The frozen reference earns analytical depth by separating displacement, reinstatement, substitution, complementarity, augmentation, productivity, organization, and institutions (reference 72, lines 31–60). Cellcog makes the standard explicit: “4IR framing without mechanism is narrative, not explanation” (current task 72, line 51).

2. **Make cross-industry synthesis a comparison engine.** Winners use shared dimensions—task structure, demand elasticity, regulation, institutions, adoption complements, worker level, outcome, time, and evidence strength—then state patterns and exceptions. WhaleCloud lines 230–267, NVIDIA lines 282–300, and Qianfan lines 596–639 show the complete pattern.

3. **Plan the four biggest cells into the outline.** Mechanisms (0.0800), critical synthesis (0.0800), restructuring breadth (0.0725), and industry breadth (0.0725) together account for 0.305 of task RACE. Leaders give them dedicated sections, matrices, and closing propositions; they do not hope they emerge from a long serial narrative (`SCORING_SPEC.md`, lines 104–123).

4. **Label epistemic status.** Cellcog's strongest transferable practice is separating Established Finding, Emerging Pattern, Conceptual Argument, and Analytical Hypothesis / Our Synthesis, including the admission “No peer-reviewed study has yet tested these long-run predictions” (current report, lines 258–282). That enables novelty without laundering inference into fact.

5. **Resolve disagreement; do not average it away.** Exposure, task productivity, local displacement, national employment, wages, and worker control answer different questions. The reference (lines 81 and 100), WhaleCloud (lines 254–267), and NVIDIA (line 322) use level/method/time/institution distinctions to reconcile apparent conflict.

6. **Derive policy and future research from causal levers.** NVIDIA's linked data, RCT, natural-experiment, services, and spatial agenda (lines 391–401) is stronger than generic recommendations because every proposal targets a missing mechanism or measurement.

7. **Enforce source restrictions mechanically.** Qianfan, ZTE, and NVIDIA all visibly contradict some form of their journal-only framing in the inspected task-72 reports. A polished Methods claim does not earn real compliance. Verify journal, peer review, language, venue, and source role before composition; task-72 gives these source constraints a combined 0.0625 RACE coefficient (`SCORING_SPEC.md`, lines 113–123).

8. **Use readable analytic units.** The reference's median 45-word paragraph allows claims, evidence, contrast, and implication to remain inspectable. POLARIS's 608.5-word median hides those boundaries. Section and paragraph restructuring is a scoring change, not cosmetic editing, because language/cohesion/synthesis structure carries 0.0980 directly and supports the larger Insight cells.

9. **Keep RACE and FACT separate.** RACE rewards content that survives citation stripping; FACT rewards unique supported statement–URL pairs. Inline atomic citations, real reachable URLs, claim-specific support, consolidation of duplicates, and multi-source baskets are the FACT moves (`SCORING_SPEC.md`, lines 162–183). Citation volume cannot substitute for mechanism or synthesis.

10. **Architecturally, let evidence change the plan.** DuMate's evolving DAG and rubric-grounded stopping, ZTE's chapter audit that triggers more research, WebWeaver's evidence–outline loop, AgentCPM's drafting/deepening alternation, and DualGraph's separate knowledge/outline graphs all converge on the same design: coverage and insight are discovered iteratively, not frozen in a one-pass outline ([DuMate README](https://github.com/baidubce/qianfan-deepresearch#readme), [ZTE README](https://github.com/Adlik/ZTE-Nebula-DeepResearch#how-zte-nebula-deepresearch-works), [WebWeaver](https://arxiv.org/abs/2509.13312), [AgentCPM-Report](https://arxiv.org/abs/2602.06540), [DualGraph](https://arxiv.org/abs/2602.13830)).

**Definitive Phase-2 conclusion:** the bar is not the reference's word count. The bar is a report whose coverage plan is complete, whose claims are built from faithful evidence baskets, whose reasoning exposes mechanisms and moderators, whose sectors are compared through a shared causal schema, whose disagreements are resolved by level/method/time/institution, whose novel insights are epistemically labeled, whose policy follows from diagnosed levers, and whose paragraphs/tables make every inference inspectable. The frozen reference already does much of this; current cellcog and WhaleCloud sharpen epistemic novelty and comparative matrices; Qianfan and ZTE show how recursive/rubric-guided research produces enormous coverage; and POLARIS's immediate visible gap is converting abundant evidence into readable, source-compliant, matrixed, cross-sector causal synthesis.
