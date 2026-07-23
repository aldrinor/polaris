# Phase 1 Verdict — RACE + FACT scoring map (investigator: Fable)

All paths relative to `/home/polaris/wt/faithoff/third_party/deep_research_bench/` unless absolute.
Paper = arXiv 2506.11763 ("DeepResearch Bench", Du et al.), text extracted from the official PDF
(saved locally at `/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/drb_paper_raw.txt`).
Every claim below carries a file:line or paper-section anchor. Nothing here is guessed; unknowns are marked.

---

## A. RACE — complete map

### A.1 The four dimensions and their exact judge-facing definitions

Canonical definitions (paper Appendix B, Table 4; identical wording in the repo comment
`prompt/criteria_prompt_en.py:1-5`):

| Dimension | Definition given |
|---|---|
| Comprehensiveness (COMP) | "Article covers key areas of the industry, ensures overall understanding, and does not omit important parts." |
| Insight/Depth (DEPTH) | "Article deeply analyzes causes, impacts, and trends, providing valuable insights." |
| Instruction-Following/Relevance (INST) | "Article closely follows the research topic and directly answers questions." |
| Readability (READ) | "Article has a clear structure, fluent language, and is easy to understand." |

In every criteria-generation prompt and in the weight prompt the four are restated as:
1. Comprehensiveness = "The breadth, depth, and relevance of information coverage" (`prompt/criteria_prompt_en.py:22,103`)
2. Insight = "The depth, originality, logic, and value of the analysis and conclusions" (`:23,104`)
3. Instruction Following = "Whether the report accurately and completely responds to all requirements and constraints of the task" (`:24,105`)
4. Readability = "Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding" (`:25,106`)

The scoring judge itself is told only: "We will assess the articles across four dimensions:
Comprehensiveness, Insight, Instruction Following, and Readability" (`prompt/score_prompt_en.py:7`) —
the operative definitions at scoring time are the per-task criteria texts, not the abstract definitions.

### A.2 Dynamic dimension weighting — the exact rule

- Prompt: `generate_eval_dimension_weight_prompt` (`prompt/criteria_prompt_en.py:8-93`).
- The formula the model is given: "Total Score = Comprehensiveness * Comprehensiveness Weight + Insight * Insight Weight + Instruction Following * Instruction Following Weight + Readability * Readability Weight. (**Note: The sum of all weights must be exactly 1.0**)" (`criteria_prompt_en.py:27`).
- The rule is NOT a formula — it is an instruction to analyze the task and allocate flexibly:
  "different tasks have different focuses, and weights must be flexibly adjusted according to task
  characteristics, not fixed" (`criteria_prompt_en.py:31`), with reasons that "directly link ... to
  the requirements and characteristics of the <task>" (`:32`).
- Two worked examples teach the logic (`:41-85`), and the prompt explicitly says to learn the
  "thinking logic and analytical methods ... rather than simply imitating their content or weight values" (`:38`):
  - Example 1 (EV charging feasibility — an analysis/recommendation task): Insight 0.35, Comp 0.30,
    Inst 0.20, Readability 0.15 — readability is "important, but secondary to the depth and breadth
    of the study" (`:48-59`).
  - Example 2 (renewable-stock historical overview — a data-presentation task): Comp 0.40,
    Readability 0.25, Inst 0.20, Insight 0.15 — readability high because "Presenting a large volume
    of historical financial data clearly ... is a major challenge and key success factor" (`:71-83`).
  - Derived rule: readability weight rises for data-heavy overview/compilation tasks; insight weight
    rises for feasibility/analysis/strategy tasks; comprehensiveness rises when the task asks for
    breadth ("different X", "over a decade"). That is the entire rule as stated to the model.
- Mechanics (paper §3.1 Eq. 1 + `utils/generate_criteria.py`):
  - Weights sampled T=5 times (`DEFAULT_SAMPLE_COUNT = 5`, `generate_criteria.py:35`) and averaged
    (`:160-170`; paper Eq. (1): W_d = (1/T)·Σ w_d^(j)).
  - Averaged weights re-normalized to sum 1 (`:172-175`), rounded to 2 decimals, and any rounding
    residual is added to READABILITY specifically (`round_weights_and_adjust`, `:88-104`, line 102:
    `rounded_weights["readability"] = round(rounded_weights["readability"] + diff, ...)`).
  - Sum==1.0 validated with tolerance 1e-6 (`validate_weights`, `:70-86`).
- IMPORTANT: the criteria file is FROZEN — `data/criteria_data/criteria.jsonl` ships with the repo
  and is loaded directly (`deepresearch_bench_race.py:29,246`). Weight generation never reruns at
  scoring time. So per-task weights are fixed constants for us.
- Actual distribution across all 100 tasks (computed from `data/criteria_data/criteria.jsonl`):
  - comprehensiveness: min 0.20, max 0.37, mean 0.292
  - insight:          min 0.11, max 0.42, mean 0.352  ← highest-mean dimension
  - instruction_following: min 0.13, max 0.35, mean 0.215
  - readability:      min 0.10, max 0.25, mean 0.141  ← lowest-mean dimension
  - 50 zh + 50 en tasks (language via `data/prompt_data/query.jsonl`).
  - Examples: task 51 (en) {read .15, insight .33, comp .30, inst .22}; task 52 {.13/.39/.32/.16};
    task 53 {.15/.39/.31/.15}; task 72 {read .14, insight .32, comp .29, inst .25}.

### A.3 Per-dimension sub-criteria

- Generated once per task by four separate prompts, one per dimension
  (`generate_eval_criteria_prompt_comp/insight/Inst/readability`, `criteria_prompt_en.py:96-506`),
  each requiring: task-specific criteria, an `explanation` per criterion, weights summing to exactly
  1.0 within the dimension, and no overlap with the other three dimensions
  (e.g. `:113-118` for COMP; `:214-219` INSIGHT; `:315-320` INST; `:410-421` READ).
- Readability is the exception: its prompt asks for "relatively general" criteria
  (`criteria_prompt_en.py:410`) drawn from a fixed element list — language clarity/correctness,
  structure/logic, information presentation/density, data & visualization, formatting/layout,
  audience adaptation (`:412-418`). This is why readability criteria are near-identical across tasks
  (top tokens across all 50 en tasks: clarity 129, formatting 50, logical 50, layout 47, structure 46,
  precision 46, paragraph 45 — computed from criteria.jsonl).
- Counts and sub-weights across the 100 tasks (computed from criteria.jsonl):
  - comprehensiveness: 5–9 criteria/task (mean 6.40); sub-weights 0.05–0.30, mean 0.156 (n=640)
  - insight: 4–7 (mean 5.57); sub-weights 0.05–0.35, mean 0.180 (n=557)
  - instruction_following: 4–8 (mean 5.71); sub-weights 0.05–0.45, mean 0.175 (n=571)
  - readability: 6–10 (mean 7.49); sub-weights 0.03–0.30, mean 0.134 (n=749)
- INST criteria are literal decompositions of the task's explicit instructions and scope limits
  (prompt requires "Instruction-Centric ... directly correspond to the explicit requirements,
  questions, and limitations", `criteria_prompt_en.py:323`).

#### Task-72 FULL criteria list (from `data/criteria_data/criteria.jsonl`, id=72; prompt = AI labor-market literature review, "only cites high-quality, English-language journal articles")

Dimension weights: insight 0.32, comprehensiveness 0.29, instruction_following 0.25, readability 0.14.

comprehensiveness (6): effective overall weight = 0.29 × sub-weight
- 0.10 Grounding in AI and the Fourth Industrial Revolution (4IR) Context
- 0.25 Breadth of Labor Market Restructuring Dimensions Covered (job creation/displacement/transformation, skill demands, ...)
- 0.25 Scope of Industry-Specific Analysis
- 0.15 Exploration of AI's Disruptive Character and Scale
- 0.15 Depth and Representativeness of Literature Synthesized
- 0.10 Balanced Discussion of AI's Labor Market Impacts

insight (5): effective overall weight = 0.32 × sub-weight
- 0.25 Analytical Depth in Characterizing AI-Driven Labor Market Restructuring Mechanisms
- 0.25 Critical Synthesis and Nuanced Evaluation of AI's Disruptive Impacts Across Industries
- 0.15 Insightful Integration of AI's Role within the 4IR Context
- 0.20 Identification and Articulation of Emergent Themes, Theoretical Linkages, or Novel Perspectives
- 0.15 Value and Foresight in Delineating Implications and Future Research Agendas

instruction_following (7): effective overall weight = 0.25 × sub-weight
- 0.10 Adherence to 'Literature Review' Format and Purpose
- 0.20 Consistent Focus on 'Restructuring Impact of AI on the Labor Market'
- 0.15 Integration of 'AI as a Key Driver of the Fourth Industrial Revolution' Theme
- 0.15 Explicit Addressal of AI-Driven 'Significant Disruptions' in the Labor Market
- 0.15 Coverage of AI's Impact on 'Various Industries'
- 0.15 Exclusive Citation of 'High-Quality Journal Articles'
- 0.10 Exclusive Citation of 'English-Language' Journal Articles

readability (7): effective overall weight = 0.14 × sub-weight
- 0.20 L1: Language Clarity, Precision, and Academic Tone
- 0.20 S1: Overall Structure and Logical Organization
- 0.15 S2: Paragraph Cohesion and Transitions
- 0.15 P1: Clarity and Synthesis in Presenting Sourced Information
- 0.10 D1: Clarity of Data/Evidence Referenced or Summarized
- 0.10 F1: Formatting, Layout, and Visual Consistency
- 0.10 A1: Audience Adaptation and Explanation of Terms

Effective single-criterion weights on the task-72 overall (dim_weight × sub_weight): the two 0.25
insight criteria are worth 0.080 each; the two 0.25 comp criteria 0.0725 each; the INST 'Consistent
Focus' criterion 0.050; the biggest readability item only 0.028.

### A.4 The judge scoring mechanic (score_prompt_en.py)

- The prompt actually used by the scorer is `generate_merged_score_prompt`
  (imported at `deepresearch_bench_race.py:16`, formatted at `:99-104`). The static and point-wise
  variants (`score_prompt_en.py:82-248, 251-321`) and `vanilla_prompt` (`:324-358`) exist in the file
  but are NOT referenced anywhere in the RACE scorer.
- COMPARATIVE and reference-based: judge receives the task, `<article_1>` = the TARGET report,
  `<article_2>` = the REFERENCE report (`deepresearch_bench_race.py:99-104`: `article_1=target_article,
  article_2=reference_article`) plus the criteria list, and must "evaluate and compare these two
  articles based on ... **each criterion**" (`score_prompt_en.py:22,30-34`). The target is ALWAYS
  article_1; there is no position swap anywhere in the code.
- Scale: 0–10 CONTINUOUS per criterion per article (`score_prompt_en.py:36`), one shared judge call
  per task covering all ~20-27 criteria at once.
- The full anchoring rubric given (`score_prompt_en.py:36-41`):
  - 0-2: "Very poor performance. Almost completely fails to meet the criterion requirements."
  - 2-4: "Poor performance. Minimally meets the criterion requirements with significant deficiencies."
  - 4-6: "Average performance. Basically meets the criterion requirements, neither good nor bad."
  - 6-8: "Good performance. Largely meets the criterion requirements with notable strengths."
  - 8-10: "Excellent/outstanding performance. Fully meets or exceeds the criterion requirements."
  That five-band rubric is the ONLY partial-credit definition; there are no sub-checklists.
- Output: JSON with per-dimension arrays of {criterion, analysis, article_1_score, article_2_score}
  (`score_prompt_en.py:47-75`). All four dimension keys must be present or the call is retried, up
  to MAX_RETRIES=10 with exponential backoff (`deepresearch_bench_race.py:31,111-140`).
- The judge does NOT see criterion weights: `format_criteria_list` strips them ("without weight
  information", `deepresearch_bench_race.py:33-56`); only `criterion` + `explanation` texts are sent
  (`:44-49`). Weights are applied afterwards in the calculator.

### A.5 Aggregation — the exact formula

Chain (paper §3.1 Eq. 2–3 + `utils/score_calculator.py` + `deepresearch_bench_race.py`):

1. Per criterion c in dimension d: judge emits s_tgt,c and s_ref,c ∈ [0,10].
2. Dimension raw score (both articles): weighted mean over MATCHED criteria —
   `dim_avg = Σ(score_c × w_c) / Σ(w_c matched)` (`score_calculator.py:119-124,136-139`). Criterion
   texts from the judge are matched back to criteria.jsonl by exact match → case-insensitive →
   substring-either-way → fallback to the dimension's AVERAGE weight if unmatched
   (`score_calculator.py:94-117`).
3. Intermediate overall per article: `S_int = Σ_d dim_avg_d × W_d` (`score_calculator.py:149-151`).
4. Final RACE overall per task (paper Eq. 3): `S_final(tgt) = S_int(tgt) / (S_int(tgt) + S_int(ref))`
   (`deepresearch_bench_race.py:156-160`). A target exactly equal to the reference scores 0.5.
5. Per-dimension reported scores are normalized the same way per dimension:
   `dim_norm = tgt_dim / (tgt_dim + ref_dim)` (`deepresearch_bench_race.py:162-172`).
   NOTE: overall_score is therefore NOT the weighted mean of the reported normalized dims — it is a
   ratio of weighted sums, computed before normalization.
6. Benchmark score = unweighted arithmetic mean of per-task overall_score over all successfully
   scored tasks (`deepresearch_bench_race.py:491-505`), written to `race_result.txt` (`:509-514`).
- The reference report R_ref: per paper §4.1, "selected from deep research articles generated by the
  Gemini-2.5-pro-based Deep Research, as available in April 2025"; stored at
  `data/test_data/cleaned_data/reference.jsonl` (`deepresearch_bench_race.py:30`; 100 entries with
  keys id/prompt/article; task-72 reference = 69,284 chars).

### A.6 What the judge actually sees (post-cleaning)

- Target reports are cleaned by an LLM pass before scoring (`ArticleCleaner`, invoked at
  `deepresearch_bench_race.py:209-220`; prompt `prompt/clean_prompt.py:21-38`). Cleaning goal:
  "remove all citation links, citation marks (such as [1], [2] ...), reference lists, footnotes, and
  ensure the content reads smoothly. Keep all other original content; remove only citations. If a
  citation mark wraps content that is part of a sentence, keep the text inside and drop only the
  marks." (`clean_prompt.py:28-29`). A chunk that is entirely a reference/bibliography section
  returns empty string (`:31`).
- Therefore: SURVIVES → all headings, tables, bold/italic, bullet lists, markdown structure, inline
  data — everything except citation apparatus. STRIPPED → [n] markers, footnotes, reference list,
  citation URLs. RACE is judged on bibliography-free prose; citation volume per se cannot earn RACE
  points (it can only earn FACT points, section B).
- Cleaning is chunked at ~50k estimated tokens per chunk (`utils/clean_article.py:95-98,116-124`;
  en estimate = chars/3.5, `:104-114`), chunks cleaned in parallel and concatenated (`:200-223`),
  with recursive splitting on truncation (`:225-250`). Minimum valid cleaned length = 100 chars
  (`clean_article.py:25`).
- The reference article comes pre-cleaned from `cleaned_data/reference.jsonl` — both sides are
  bibliography-free at judge time.

### A.7 Full vs partial vs zero credit per criterion type (grounded)

There is exactly ONE scoring rule for every criterion type — the five-band 0-10 rubric of
`score_prompt_en.py:36-41` applied comparatively against the reference. Concretely, per criterion
family (the requirement text that the band rubric is applied to):

- COMP criteria ("Breadth of ... Covered", "Scope of ... Analysis"): full credit = the enumerated
  aspects in the criterion's `explanation` are all covered ("Fully meets or exceeds"); partial =
  bands 2-8 for covering some aspects; zero/near-zero = "Almost completely fails" (omits the area).
  The aspects are enumerated in each criterion's explanation field (e.g. task-72 comp#2 explanation
  lists "job creation, job displacement, job transformation, changes in skill demands, w..." —
  criteria.jsonl id=72).
- INSIGHT criteria: explanations explicitly gate credit on going beyond listing — e.g. "deeply
  analyzes their interplay and causal mechanisms, rather than a superficial listing"
  (`criteria_prompt_en.py:256`), "goes beyond obvious impacts to uncover subtle or second-order
  effects" (`:261`), "novel, actionable insights ... moving beyond generic advice" (`:276`).
  Mere information listing ≈ mid bands; mechanisms/second-order/novelty ≈ 8-10.
- INST criteria: binary-ish in wording ("Exclusive Citation of 'High-Quality Journal Articles'",
  "Strict Adherence to ... Scope", criteria.jsonl id=72; template `criteria_prompt_en.py:365-371`)
  but still scored on the continuous 0-10 band — "significant deviation" language in the
  explanations implies partial deviations cost partial credit. NOTE for task-72: two INST criteria
  (source quality + English-language sources, combined 0.25 of INST = 0.0625 overall) are judged on
  the CLEANED article, where the reference list has been stripped — the judge can only assess these
  from in-text attribution phrasing that survives cleaning ("(Autor, 2015)"-style or named-source
  prose). This is verifiable from the pipeline order: cleaning (`deepresearch_bench_race.py:209-220`)
  precedes prompt assembly (`:99-104`).
- READ criteria: full credit needs the structural artifacts named in the explanation (clear heading
  hierarchy, focused paragraphs, transitions, well-designed tables/charts "clearly labeled, easy to
  interpret", bolding/summary highlights, term explanation — `criteria_prompt_en.py:456-494`).
- All of this is comparative: an "8" only helps insofar as the reference scores lower on the same
  criterion; the reported quantity is target/(target+reference) (A.5 step 4-5).

---

## B. FACT — complete map

### B.1 What FACT measures and exact formulas

FACT = "Factual Abundance and Citation Trustworthiness" (paper §3.2). Two metrics
(paper Appendix E, Eq. 4-6):
- Per-task accuracy: `Acc_t = N_s,t / N_u,t` if N_u,t > 0, else 0 — where U_t = unique
  statement-URL pairs after dedup, N_s,t = pairs judged 'support' (Eq. 4).
- **Citation Accuracy (C. Acc.)** = (1/|T|) Σ_t Acc_t — macro-average over tasks (Eq. 5).
- **Average Effective Citations per task (E. Cit.)** = (Σ_t N_s,t) / |T| (Eq. 6).

The repo's implementation (`utils/stat.py:20-40`) computes and writes three numbers to
`fact_result.txt`:
- `total_citations` = (# non-'unknown' judgments) / total_num  — avg judged citations per task
- `total_valid_citations` = (# 'supported') / total_num — this is E. Cit.
- `valid_rate` = supported / non-unknown — a MICRO-average accuracy.
Deviations from the paper (see D): micro vs macro; tasks with zero citations are `continue`d and
excluded from total_num (`stat.py:21-22`) instead of contributing Acc_t = 0; 'unknown' judgments are
excluded from both numerator and denominator (`stat.py:26-30`).

### B.2 Pipeline — extraction, verification, what counts

Pipeline order (run_benchmark.sh:79-93): extract → deduplicate → scrape → validate → stat.
FACT runs on the RAW report (`RAW_DATA_PATH="$RAW_DATA_DIR/$TARGET_MODEL.jsonl"`,
`run_benchmark.sh:76,81`) — NOT the cleaned one.

1. **Extraction** (`utils/extract.py`, en prompt `:39-65`): an LLM extracts ALL
   (fact, ref_idx, url) triplets from the report body. Recognized citation forms (`:41-45`):
   (1) text + bare number; (2) text + `[n]`; (3) text + `[n†L..]`; (4) inline `[Title](url)`.
   Rules: fact must be a complete, verifiable statement with context (`:48`); a fact citing k
   references becomes k triplets (`:49`); **"If the main text does not specify the exact location of
   the citation (for example, only the reference list is listed at the end ...), please return an
   empty list"** (`:51`) — end-only bibliographies score ZERO on FACT. URLs are taken from the
   reference list or the inline parentheses (`:58`). `#:~:text=` fragments are truncated only for
   'openai' files (`:68-81,187-191`); `[title](url)` inside extracted facts is reduced to `[title]`
   (`:84-88,137`).
2. **Deduplication** (`utils/deduplicate.py`): triplets grouped by URL (`:47-53`); within a URL
   group an LLM keeps unique statements — duplicates only if they "express *exactly the same
   thing*" (`:21`); on LLM failure ALL statements are kept (`:105-106`). Output structure:
   `citations_deduped = {url: {facts: [...], url_content: None}}` (`:109-114`).
3. **Scraping** (`utils/scrape.py` + `utils/api.py:203-241`): each unique URL fetched via Jina
   Reader (`https://r.jina.ai/<url>`, `api.py:213`); reference text = `title\n\ndescription\n\ncontent`
   (`scrape.py:24-28`); 3 retries, then the literal string `"scrape failed: <err>"` becomes the
   reference content (`scrape.py:30`).
4. **Support judgment** (`utils/validate.py`, en prompt `:39-64`): one LLM call per URL judges all
   of that URL's statements as supported / unsupported / unknown:
   - Invalid reference (e.g. "page not found") → all 'unknown' (`:40-41`) — unknowns then drop out
     of both counts in stat.py.
   - "if the facts or data it contains can be found **entirely or partially** within the reference,
     it is considered 'supported' (**data accepts rounding**)" (`:41`).
   - 'unsupported' only if ALL facts and data in the statement are absent from the reference (`:41`).
   This is a lenient partial-support standard with numeric rounding tolerance.
5. **Stat** (`utils/stat.py`) as in B.1.

### B.3 Relation to RACE

Fully independent. RACE reads cleaned articles and never touches citation data
(`deepresearch_bench_race.py` has no import from extract/validate/stat); FACT reads raw articles and
never touches criteria or the reference report (`run_benchmark.sh:71-93` runs them as separate
phases into `results/race/` vs `results/fact/`). RACE `overall_score` is computed exclusively from
the four dimension scores (`deepresearch_bench_race.py:156-160`). Leaderboard-wise they are separate
columns (paper Table 1: RACE Overall/Comp/Depth/Inst/Read vs FACT C.Acc/E.Cit). The only coupling is
indirect and stated in the paper: high E. Cit. correlates with Comprehensiveness ("This finding is
consistent with its top score in the 'Comprehensiveness' dimension", paper §4.2.2).

---

## C. Scoreable-surface inventory

Every distinct way a report gains/loses score. Weights: eff = dimension_weight × sub_weight
(task-dependent; task-72 values given; means across 100 tasks per A.2/A.3). All RACE surfaces are
scored 0-10 comparatively vs the Gemini-2.5-Pro DR reference and pass through
S=tgt/(tgt+ref) (`deepresearch_bench_race.py:156-172`).

**COMP (dim weight mean 0.292; task-72: 0.29)**
1. Cover every key topic area the task implies (breadth). Each area is a named sub-criterion with
   its own weight (e.g. task-72 "Breadth of Labor Market Restructuring Dimensions", 0.25×0.29=0.0725).
   Anchor: criteria.jsonl id=72; template `criteria_prompt_en.py:113-118`.
2. Depth of detail per area — surface overviews land in the 4-6 band. Anchor: static-criteria analog
   "Information Depth and Detail" `score_prompt_en.py:113-116`; band rubric `:36-41`.
3. Data/facts/cases as evidence density inside prose (post-cleaning, so data must live in the text,
   not in citations). Anchors: `criteria_prompt_en.py:179-182` (example criterion "Breadth and
   Quality of Data Sources"); task-72 comp#5 "Depth and Representativeness of Literature Synthesized"
   (0.15×0.29).
4. Multi-perspective balance (challenges AND opportunities). Anchor: task-72 comp#6 "Balanced
   Discussion" (0.10×0.29); criteria.jsonl.
5. Contextual framing demanded by the task (task-72 comp#1 "Grounding in ... 4IR Context",
   0.10×0.29). Anchor: criteria.jsonl id=72.

**INSIGHT (dim weight mean 0.352 — the largest average lever; task-72: 0.32)**
6. Mechanism-level causal analysis, not listing ("interplay and causal mechanisms, rather than a
   superficial listing", `criteria_prompt_en.py:256`). Task-72 insight#1: 0.25×0.32=0.080.
7. Non-obvious / second-order effects ("goes beyond obvious impacts", `criteria_prompt_en.py:261`).
   Task-72 insight#2 critical synthesis: 0.080.
8. Logical coherence: conclusions/recommendations derived explicitly from the preceding analysis
   (`criteria_prompt_en.py:265-267`). Present in ~all tasks ('logical' 16, 'justification' 17
   occurrences in en insight criterion names — criteria.jsonl).
9. Originality / novel perspectives, "challenges conventional wisdom", beyond generic advice
   (`criteria_prompt_en.py:275-277`; 'originality' appears 38× in en insight criteria).
   Task-72 insight#4 emergent themes: 0.20×0.32=0.064.
10. Forward-looking implications + future research/strategy agendas (`criteria_prompt_en.py:280-282`;
    task-72 insight#5: 0.15×0.32=0.048).
11. Nuanced risk/trade-off assessment where the task involves decisions (`criteria_prompt_en.py:270-272`).

**INST (dim weight mean 0.215; task-72: 0.25)**
12. Directly and clearly answer each explicit task component (template weights 0.30+0.30 in the
    example, `criteria_prompt_en.py:355-362`; task-72 "Consistent Focus" 0.20×0.25=0.050).
13. Strict adherence to every scope limit — geography, time, subject, format (template
    `criteria_prompt_en.py:365-372`; task-72 has 5 such criteria incl. format-as-literature-review).
14. Complete coverage of all sub-questions, no omitted component (`criteria_prompt_en.py:374-377`).
15. Source-constraint compliance VISIBLE IN PROSE (task-72: "Exclusive Citation of High-Quality
    Journal Articles" 0.15×0.25 + "English-Language" 0.10×0.25 — judged on the cleaned text, so the
    signal must survive citation-stripping, i.e., named-author/journal attribution in sentences).
    Anchors: criteria.jsonl id=72; cleaning contract `clean_prompt.py:28-31`.

**READ (dim weight mean 0.141; task-72: 0.14)**
16. Clear macro-structure: intro/scope/roadmap, logically sequenced sections, distinct heading
    levels (`criteria_prompt_en.py:456-459`; task-72 S1 0.20×0.14=0.028).
17. Language clarity/precision/tone; correct terminology, explained where needed
    (`criteria_prompt_en.py:461-464`; task-72 L1 0.028).
18. Paragraph cohesion + transitions (`:466-469`; task-72 S2 0.021).
19. Clear, accurate data presentation in-text (`:471-474`; task-72 D1 0.014).
20. Effective, well-labeled tables/charts (`:476-479`; readability example weight 0.10). Note the
    static analog explicitly rewards "formatting, headings, lists, emphasis" (`score_prompt_en.py:190-192`).
21. Highlighting of key findings (bolding, bullets, summaries) (`:481-484`).
22. Formatting/layout consistency (`:486-489`) and audience adaptation (`:491-494`).

**Cross-cutting RACE mechanics (gain/lose score without changing content quality)**
23. Beat the reference, not an absolute bar: every point is worth tgt/(tgt+ref) share
    (`deepresearch_bench_race.py:158-160`). Raising a dim from parity 5v5 (0.5) to 6v5 (0.545)
    gains ~0.045 × dim weight on that task's overall.
24. Survive cleaning intact: content inside citation markers can be deleted by the cleaner if
    formatted as citation apparatus (`clean_prompt.py:28-31`); a chunk that looks like a pure
    reference section is dropped entirely (`:31`). Malformed markers risk collateral text loss.
25. Criterion-name echo: judge must repeat criterion text; mismatches fall back to fuzzy match then
    AVERAGE dimension weight (`score_calculator.py:94-117`) — a systematic reweighting risk, not a
    surface we control directly, but it makes per-criterion wins noisy.

**FACT surfaces**
26. In-text citation markers are mandatory — bibliography-only citing yields an empty extraction
    list → E. Cit. = 0 for the task (`extract.py:51`).
27. E. Cit. (volume): each unique, supported statement-URL pair counts 1; more supported claims
    across more URLs = linearly more E. Cit. (paper Eq. 6; `stat.py:28-30`). Duplicated claims to
    the same URL are collapsed (`deduplicate.py:21,105-114`) — only near-identical statements are
    merged, paraphrases survive.
28. C. Acc. (precision): every extracted pair judged 'unsupported' lowers accuracy
    (paper Eq. 4-5; `stat.py:37-40` micro version). Support standard is lenient: partial support +
    rounded numbers suffice (`validate.py:41`).
29. URL scrapability: dead/paywalled/anti-bot URLs → 'unknown' → the pair vanishes from both counts
    in the shipped stat.py (`validate.py:40-41`, `stat.py:26-27`) — it neither helps E. Cit. nor
    hurts valid_rate. (Under the paper's macro formula unknowns are not addressed; unknown-heavy
    tasks shrink N_u,t.)
30. One fact citing k sources = k pairs (`extract.py:49`) — multi-citing a supported fact multiplies
    E. Cit. if each source supports it.

---

## D. Judge / measurement caveats

1. **Judge model & migration.** Paper (§4.1): RACE judge = Gemini-2.5-pro; FACT judge =
   Gemini-2.5-flash (validated vs humans on 100 pairs: 96% agreement on 'support', 92% on
   'not support' — Appendix C). Official evaluator switched to **GPT-5.5** for RACE and
   **GPT-5.4-mini** for FACT as of 11 May 2026 (README.md:16-29): three candidates were benchmarked
   on the human-annotated subset (human inter-annotator agreement baseline 68.78%); GPT-5.5 won
   Overall/PAR/FAS (README.md:16-21). This local repo is the GPT-5 fork: defaults
   `openai/gpt-5.5` (RACE) and `openai/gpt-5.4-mini` (FACT) via OpenRouter or OpenAI backends,
   overridable by `RACE_MODEL`/`FACT_MODEL` env (`utils/api.py:41-75`; README.md:192-197).
2. **Two-leaderboard scale issue.** Dual-acceptance window until 31 May 2026 with SEPARATE
   leaderboards per evaluator; after 1 June 2026 only the GPT-5.5 board remains (README.md:26-29).
   Scores under different judges are not comparable; legacy code preserved on the `Gemini-2.5`
   branch (README.md:29).
3. **Temperature/variance.** Sampling params are intentionally UNSET — "gpt-5.x reasoning models
   reject non-default values anyway" (`utils/api.py:24-25`); stage reasoning_effort: clean=low,
   score=medium, fact=low (`api.py:84-88`); max_completion_tokens 64,000 (`api.py:81`). There is no
   seed and no multi-sample averaging at scoring time (weights were averaged over 5 samples at
   criteria-GENERATION time only, `generate_criteria.py:35`) → run-to-run RACE variance is
   irreducible in-pipeline; repeated runs are the only variance estimate.
4. **Absolute values are meaningless; ratios matter.** Paper §4.2.1: scores cluster (top DRAs
   46.98-48.88) by construction of Eq. 3; "focus on the rankings and proportional differences
   between the scores rather than the absolute score values."
5. **Fixed position, no swap.** Target is always article_1 (`deepresearch_bench_race.py:99-104`);
   any judge position bias is a constant offset in all runs.
6. **Criterion-matching fallback.** Judge-paraphrased criterion names get average-weight fallback
   (`score_calculator.py:113-117`) and are only logged as warnings (`:154-155`) — silently reweights
   dimensions when it happens.
7. **JSON salvage.** `extract_json_from_markdown` has 6 fallbacks incl. a regex reconstruction that
   keeps only min(len) aligned criterion/score triples (`utils/json_extractor.py:96-152`) — a
   truncated judge response can silently drop trailing criteria (they then simply don't contribute;
   dim average renormalizes over matched weight, `score_calculator.py:136-139`).
8. **Cleaning is an LLM step.** Nondeterministic; chunk boundaries at ~50k est. tokens
   (`clean_article.py:95-98`); a failed clean excludes the task (`deepresearch_bench_race.py:227-229`);
   over-aggressive cleaning can delete content and depress COMP.
9. **stat.py ≠ paper formulas.** Micro `valid_rate` vs paper's macro C. Acc. (Eq. 5); zero-citation
   tasks skipped (`stat.py:21-22`) vs paper's Acc_t=0 rule (Eq. 4); 'unknown' class (from validate)
   excluded from denominators (`stat.py:26-30`) — the paper's Appendix E doesn't model 'unknown' at
   all. Local FACT numbers are therefore not exactly the leaderboard definition.
10. **FACT scraping fragility.** Jina Reader failures inject "scrape failed: ..." as the reference
    (`scrape.py:30`), which validate treats as invalid content → 'unknown' (`validate.py:40-41`);
    JINA_API_KEY required (`api.py:203-209`). Time-drift: pages change after generation; support is
    judged against TODAY's page content.
11. **Reference era.** R_ref = Gemini-2.5-Pro Deep Research reports from April 2025 (paper §4.1
    footnote 3: "We cannot confirm if there were any Deep Research model iterations during the
    reference collection period"). The bar is frozen; the judge is not.
12. **Human-consistency scope.** Validation used 50 zh tasks × 4 agents × 3 annotators
    (600 reports; paper §4.3, Appendix G.1); filtered subset = 37 tasks (ICC(1,1)<0 removed,
    Appendix F.3). The en half was never human-validated in the paper.

---

## EXECUTIVE SUMMARY — highest-leverage scoreable surfaces

Grounded ranking by weight × plausible headroom: (1) **Insight is the single biggest RACE lever** —
mean dimension weight 0.352 across the 100 tasks (max 0.42; criteria.jsonl), and its sub-criteria
explicitly pay for causal mechanisms, second-order effects, novel synthesis and forward-looking
implications over listing (`criteria_prompt_en.py:256-282`); on task-72 the two 0.25-weight insight
criteria are worth 0.080 of the overall each — the two largest single cells on the whole scorecard.
(2) **Comprehensiveness (mean 0.29)** pays per named coverage area — each sub-criterion enumerates
concrete aspects in its explanation, so coverage is a checklist you can enumerate from criteria.jsonl
before writing. (3) **Instruction-following (mean 0.215, up to 0.35)** is the cheapest full-credit
dimension because its criteria are literal restatements of task text (scope, format, source
constraints); note constraints about sources must remain visible in prose because the judge sees a
citation-stripped article (`clean_prompt.py:28-31`, `deepresearch_bench_race.py:33-56` also strips
weights). (4) **Readability is structurally capped** (mean 0.141, max 0.25; task-72 top item = 0.028
overall) — polish only what the 6-10 near-universal criteria name: heading hierarchy, transitions,
labeled tables, bolded key findings. (5) Everything RACE is **relative to a frozen April-2025
Gemini-2.5-Pro reference** with S=tgt/(tgt+ref) (`deepresearch_bench_race.py:158-160`) — points only
count where the reference is beatable, and a 1-point per-criterion gain at 5v5 parity moves the task
overall by ≈0.009×(dim_weight/0.25)... concretely +0.045 normalized per dimension point. (6) **FACT
is independent of RACE** and has two hard mechanics: in-text citation markers are mandatory
(empty list otherwise, `extract.py:51`), and the support bar is lenient (partial support + rounding,
`validate.py:41`) — so E. Cit. scales nearly linearly with the number of distinct, scrapeable-URL-backed
factual statements, while unscrapeable URLs fall out of both counts in the shipped stat.py
(`stat.py:26-30`).
