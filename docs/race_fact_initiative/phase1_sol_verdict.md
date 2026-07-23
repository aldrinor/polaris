# Phase 1 Investigator Verdict: Definitive Map of DeepResearch Bench RACE + FACT Scoring

**Investigation date:** 2026-07-23  
**Local benchmark checkout:** `third_party/deep_research_bench/`, commit `469cce54ea7f6a63c163d3d9fec879cf289ec484` (2026-05-11).  
**Scope discipline:** read-only investigation. No repository file was modified. This verdict is the only written artifact.

## 0. Source hierarchy and important version distinction

1. **The executable code is the authority for what a local run actually computes.** The current `main` branch has switched the default RACE judge to `openai/gpt-5.5` and the default FACT judge to `openai/gpt-5.4-mini` under OpenRouter, or `gpt-5.5` / `gpt-5.4-mini` under the direct OpenAI backend (`utils/api.py:40-75`). The official repository README announces that switch and says the previous Gemini implementation is preserved on the `Gemini-2.5` branch (`README.md:15-31`).
2. **The arXiv paper describes the original, legacy evaluator regime.** It specifies Gemini-2.5-Pro for RACE and Gemini-2.5-Flash for FACT, with Gemini-2.5-Pro Deep Research reports as references (arXiv 2506.11763, §3.3 “Implementation Details”; source `drbench.tex:243-248`). The legacy branch pins `gemini-2.5-pro-preview-06-05` and `gemini-2.5-flash-preview-05-20` (`Gemini-2.5` branch `utils/api.py:18-21`).
3. **There are officially two judge-specific leaderboard frames.** The current Hugging Face Space labels the main tab “GPT-5.5 (race) + GPT-5.4-mini (fact-check)” and a separate Gemini-2.5 tab “gemini-2.5-pro + gemini-2.5-flash” (`create_leaderboard.py:81-98`; `tabs/leaderboard_tab_gpt55.py:184-190`, HF Space commit `e2463da8c1d42ca92c9a56b30cb97801ff4087fd`). The repository explicitly required separate leaderboards during migration because scores are comparable within, not across, evaluator regimes (`README.md:24-29`).
4. **Paper formulas and current code are not identical for FACT.** RACE’s paper formula matches the core code. FACT’s paper defines macro-averaged per-task citation accuracy over all tasks, assigning zero to no-citation tasks (paper Appendix “Detailed Calculation of Citation Metrics,” equations at `drbench.tex:555-590`). Current `utils/stat.py` instead computes a micro support rate over successfully judged, non-`unknown` pairs and excludes tasks with no extracted citations from its task denominator (`utils/stat.py:13-40`). This discrepancy is material and is detailed in §B.5.
5. **The model that originally generated the stored `criteria.jsonl` is not recorded in that file.** The paper says the Judge LLM generated criteria in the legacy setup, but `data/criteria_data/criteria.jsonl` contains only task IDs, prompts, weights, and criteria. Therefore the exact model/version used to create this already-frozen file is **unknown** from the artifact itself. The current scorer does not regenerate criteria; it loads this file (`deepresearch_bench_race.py:28-30,245-248`).

---

# A. RACE — complete map

## A1. What RACE measures and the four exact top-level dimensions

RACE is the report-quality half of the benchmark. The paper describes it as a **Reference-based Adaptive Criteria-driven Evaluation framework with Dynamic Weighting**: generate task-specific dimension weights and sub-criteria, jointly score target and reference reports criterion by criterion, then convert those raw scores into a relative target score (paper §3.1; `drbench.tex:195-220`). The README likewise states dynamic criteria, reference-based scoring, and task-adapted weighted assessment (`README.md:87-99`).

The exact definitions given to the criteria generator and score judge are:

1. **Comprehensiveness:** “The breadth, depth, and relevance of information coverage.” (`prompt/criteria_prompt_en.py:101-106`). The paper’s shorter definition is: covering key areas, ensuring overall understanding, and not omitting important parts (`drbench.tex:483-500`).
2. **Insight:** “The depth, originality, logic, and value of the analysis and conclusions.” (`prompt/criteria_prompt_en.py:101-106`). The paper’s shorter definition emphasizes deep analysis of causes, impacts, and trends and the production of valuable insights (`drbench.tex:501-502`).
3. **Instruction Following:** “Whether the report accurately and completely responds to all requirements and constraints of the task.” (`prompt/criteria_prompt_en.py:101-106`). The paper’s shorter definition is close adherence to the research topic and direct answers to questions (`drbench.tex:504-505`).
4. **Readability:** “Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of understanding.” (`prompt/criteria_prompt_en.py:101-106`). The paper’s shorter definition requires clear structure, fluent language, and ease of understanding (`drbench.tex:507-508`).

The English and Chinese scoring prompts implement the same four dimensions and same five score bands; the Chinese file is a translation rather than a different scoring algorithm (`prompt/score_prompt_en.py:1-79`; `prompt/score_prompt_zh.py:1-79`). Tasks are split evenly: 50 Chinese and 50 English (`data/prompt_data/query.jsonl:1-100`; language selection at `deepresearch_bench_race.py:232-240`).

## A2. Dynamic dimension weighting: exact rule and implementation

### A2.1 Rule given to the weight-generating LLM

There is **no hard-coded rule such as “financial tasks always receive readability 0.15.”** The rule is semantic and task-adaptive:

- Analyze the task’s specific content, implicit goals, potential difficulties, and core value (`prompt/criteria_prompt_en.py:29-30`).
- Allocate decimal weights to the four dimensions, summing to exactly 1.0 (`prompt/criteria_prompt_en.py:21-27,31`).
- Adjust weights flexibly according to the task’s characteristics rather than use fixed weights (`prompt/criteria_prompt_en.py:31`).
- Explain why each dimension receives its weight and link that reason directly to the task (`prompt/criteria_prompt_en.py:32-33`).

The two prompt examples define the intended decision logic:

- **EV investment-feasibility task:** Insight 0.35 because feasibility mechanisms and strategy quality are central; Comprehensiveness 0.30 because technical/economic/social/environmental factors all matter; Instruction Following 0.20 for the exact suburban-EV-investment scope; Readability 0.15 because communication is important but secondary to breadth/depth (`prompt/criteria_prompt_en.py:41-59`).
- **Renewable-stock historical overview:** Comprehensiveness 0.40 because the prompt explicitly demands different stocks over a decade; Readability 0.25 because a large volume of financial data must be presented and compared clearly; Instruction Following 0.20 for the renewable-stock/past-decade/historical-performance constraints; Insight 0.15 because trend interpretation is useful but not primary (`prompt/criteria_prompt_en.py:64-82`).

**Therefore, what changes readability from 0.15 to 0.25 is not a keyword or formula.** It is the judge’s task analysis of whether clear organization/data presentation is a secondary communication concern (EV feasibility) or a major success condition because the task is dominated by broad comparative historical data (renewable stocks). This conclusion is exactly what the examples instruct; any more deterministic rule is **unknown because none exists in code or prompt**.

### A2.2 Sampling, averaging, normalization, and rounding

For each task, criteria generation performs five weight-generation samples by default (`utils/generate_criteria.py:30-35,129-154`). It:

1. Keeps only samples that parse as nonempty dictionaries and whose values sum to 1.0 within `1e-6` (`utils/generate_criteria.py:44-84,139-148`).
2. Averages each dimension across successful samples, provided the dimension appears in every retained sample (`utils/generate_criteria.py:160-170`).
3. Renormalizes the averages to sum to 1 (`utils/generate_criteria.py:172-175`).
4. Rounds to two decimals; if rounding creates a residual, the entire residual is added to **readability** (`utils/generate_criteria.py:88-104,177-180`).

That last rule means stored readability weight includes any two-decimal rounding correction. It is not necessarily the exactly rounded independent sample mean.

### A2.3 Actual distribution across all 100 stored tasks

The following figures were computed line by line from all 100 records in `data/criteria_data/criteria.jsonl:1-100`. All 100 dimension-weight vectors sum exactly to 1.0, and all 400 within-dimension criterion-weight lists sum exactly to 1.0.

| Dimension | Mean | Median | Min (task) | Max (task) | Most frequent exact weights |
|---|---:|---:|---|---|---|
| Comprehensiveness | 0.2920 | 0.30 | 0.20 (4, 30) | 0.37 (91) | 0.30: 25 tasks; 0.29: 18; 0.31: 10; 0.28: 10 |
| Insight | 0.3520 | 0.36 | 0.11 (91) | 0.42 (34) | 0.35: 12; 0.38: 11; 0.39: 11; 0.40: 10 |
| Instruction Following | 0.2147 | 0.20 | 0.13 (43) | 0.35 (48) | 0.19: 16; 0.20: 12; 0.22: 11 |
| Readability | 0.1413 | 0.14 | 0.10 (32, 54) | 0.25 (73) | 0.15: 24; 0.13: 19; 0.12: 14; 0.14: 14 |

Language-stratified means are close but not identical: Chinese tasks average 0.2866/0.3540/0.2204/0.1390 and English tasks 0.2974/0.3500/0.2090/0.1436 for Comprehensiveness/Insight/Instruction/Readability respectively (`criteria.jsonl:1-50` versus `criteria.jsonl:51-100`; languages in `query.jsonl:1-100`).

Illustrative actual tasks:

- Task 4 (gold analysis plus required mind map): 0.20 Comp / 0.38 Insight / 0.26 Instruction / 0.16 Readability; the required mind-map format itself receives 0.30 inside Instruction Following (`criteria.jsonl:4`).
- Task 30 (theory-driven analysis with four mandatory lenses): 0.20 / 0.38 / 0.31 / 0.11; each named theoretical lens becomes a separate instruction sub-criterion (`criteria.jsonl:30`).
- Task 73 (practical paper for novice elementary English teachers): 0.23 / 0.30 / 0.22 / **0.25**; novice accessibility, examples, pedagogical aids, and tone are central (`criteria.jsonl:73`).
- Task 91 (large Saint Seiya character/armor inventory): **0.37** / **0.11** / 0.32 / 0.20; breadth and structured fulfillment dominate originality (`criteria.jsonl:91`).
- Task 100 (conceptual paper on AI interaction and interpersonal relations): 0.29 / **0.40** / 0.16 / 0.15; deep treatment of fundamental relational change dominates (`criteria.jsonl:100`).

## A3. Per-dimension sub-criteria generation and corpus distribution

### A3.1 Generation rules

Each dimension is generated in a separate LLM call after the dimension weights are fixed (`utils/generate_criteria.py:182-224`). A generated list is accepted only if it is nonempty and its sub-weights sum to exactly 1.0 within `1e-6` (`utils/generate_criteria.py:70-84,198-214`). The model chooses the number of criteria; code sets no fixed count.

- **Comprehensiveness generation:** identify key information areas, perspectives, and required depths; maximize coverage diversity while minimizing overlap and omissions; each item must be task-centric and justified (`prompt/criteria_prompt_en.py:112-125`).
- **Insight generation:** identify areas needing deep analysis, deduction, synthesis, or value judgment; focus on analytical depth, logical consistency, originality, and conclusion value; exclude mere information listing (`prompt/criteria_prompt_en.py:213-226`).
- **Instruction generation:** decompose explicit questions, required outputs, scope limits such as geography/time/subject, and core objectives; score directness, completeness, on-topic behavior, and strict adherence to constraints (`prompt/criteria_prompt_en.py:314-327`).
- **Readability generation:** systematically cover language clarity, structure, information density, data/visualization, formatting/layout, and audience adaptation; weights may be adjusted to task type (`prompt/criteria_prompt_en.py:409-432`).

### A3.2 Counts and sub-weight distribution across all 100 tasks

There are **2,517 actual sub-criteria** in `criteria.jsonl:1-100`:

| Dimension | Total sub-criteria | Per-task count distribution | Mean count | Sub-weight range | Median sub-weight |
|---|---:|---|---:|---:|---:|
| Comprehensiveness | 640 | 5:14, 6:43, 7:33, 8:9, 9:1 | 6.40 | 0.05–0.30 | 0.15 |
| Insight | 557 | 4:1, 5:45, 6:50, 7:4 | 5.57 | 0.05–0.35 | 0.20 |
| Instruction Following | 571 | 4:9, 5:39, 6:31, 7:14, 8:7 | 5.71 | 0.05–0.45 | 0.15 |
| Readability | 749 | 6:12, 7:40, 8:38, 9:7, 10:3 | 7.49 | 0.03–0.30 | 0.10 |

This distribution proves that “the rubric” is not four generic scores. The operational score surface is task-specific and normally contains roughly 23–27 separately judged items per task.

### A3.3 Full task-72 criteria and effective pre-normalization weights

Task 72 asks for a literature review on AI-driven labor-market restructuring, AI as a Fourth Industrial Revolution driver, disruptions across industries, and **only high-quality English-language journal articles** (`data/prompt_data/query.jsonl:72`). Its dimension weights are Readability 0.14, Insight 0.32, Comprehensiveness 0.29, Instruction Following 0.25 (`data/criteria_data/criteria.jsonl:72`). The “effective weight” below is `dimension_weight × subcriterion_weight`; it is the criterion’s coefficient in the target/reference intermediate raw score before relative normalization.

### Comprehensiveness (dimension weight 0.29)

1. **Grounding in AI and the Fourth Industrial Revolution context** — sub-weight 0.10; effective 0.0290. Full fulfillment defines AI in 4IR and explains its driver role; partial treatment merely mentions 4IR or weakly links it; near-zero omits/misframes the context (`criteria.jsonl:72`, JSON path `.criterions.comprehensiveness[0]`; score bands `score_prompt_en.py:35-41`).
2. **Breadth of labor-market restructuring dimensions** — 0.25; effective 0.0725. Surface includes job creation, displacement, transformation, skills, wages, and productivity (`criteria.jsonl:72`, `.comprehensiveness[1]`).
3. **Scope of industry-specific analysis** — 0.25; effective 0.0725. Surface requires a diverse set of industries plus common and sector-specific patterns (`criteria.jsonl:72`, `.comprehensiveness[2]`).
4. **AI’s disruptive character and scale** — 0.15; effective 0.0435. Surface includes magnitude, speed, and transformative potential (`criteria.jsonl:72`, `.comprehensiveness[3]`).
5. **Depth and representativeness of synthesized literature** — 0.15; effective 0.0435. Surface includes broad/current/high-quality literature, main themes, findings, and debates (`criteria.jsonl:72`, `.comprehensiveness[4]`).
6. **Balanced impacts** — 0.10; effective 0.0290. Surface requires challenges and opportunities, including displacement/skills/inequality and jobs/productivity/work quality (`criteria.jsonl:72`, `.comprehensiveness[5]`).

### Insight (dimension weight 0.32)

7. **Mechanisms of AI-driven restructuring** — 0.25; effective **0.0800**. Surface includes task automation, augmentation, job creation/destruction dynamics, organizational adaptation, and effects on roles/skills/structures (`criteria.jsonl:72`, `.insight[0]`).
8. **Critical synthesis across industries** — 0.25; effective **0.0800**. Surface requires patterns, sector variation, consensus, debate, and uncertainty rather than a catalog (`criteria.jsonl:72`, `.insight[1]`).
9. **Insightful 4IR integration** — 0.15; effective 0.0480. Surface requires the 4IR framework to explain nature, scale, and interconnectedness, not a superficial mention (`criteria.jsonl:72`, `.insight[2]`).
10. **Emergent themes/theoretical linkages/novel perspectives** — 0.20; effective 0.0640. Surface rewards synthesis-derived higher-order themes and conceptual connections (`criteria.jsonl:72`, `.insight[3]`).
11. **Implications and future research agendas** — 0.15; effective 0.0480. Surface includes policy, education, workforce adaptation, research gaps, and future agendas (`criteria.jsonl:72`, `.insight[4]`).

### Instruction Following (dimension weight 0.25)

12. **Literature-review format and purpose** — 0.10; effective 0.0250. Must synthesize published research rather than present an original empirical study or pure opinion (`criteria.jsonl:72`, `.instruction_following[0]`).
13. **Consistent focus on AI labor-market restructuring** — 0.20; effective 0.0500. Digressions into unrelated AI applications or untethered economic theory lose credit (`criteria.jsonl:72`, `.instruction_following[1]`).
14. **Explicit AI-as-4IR-driver theme** — 0.15; effective 0.0375 (`criteria.jsonl:72`, `.instruction_following[2]`).
15. **Explicit significant-disruption treatment** — 0.15; effective 0.0375 (`criteria.jsonl:72`, `.instruction_following[3]`).
16. **Various-industries coverage** — 0.15; effective 0.0375 (`criteria.jsonl:72`, `.instruction_following[4]`).
17. **Only high-quality journal articles** — 0.15; effective 0.0375. Books, proceedings, news, blogs, and non-peer-reviewed reports violate this criterion (`criteria.jsonl:72`, `.instruction_following[5]`).
18. **Only English-language journal articles** — 0.10; effective 0.0250 (`criteria.jsonl:72`, `.instruction_following[6]`).

### Readability (dimension weight 0.14)

19. **Language clarity, precision, correctness, and academic tone** — 0.20; effective 0.0280 (`criteria.jsonl:72`, `.readability[0]`).
20. **Overall structure and logical organization** — 0.20; effective 0.0280; includes scope-setting introduction, thematic headings, logical sequencing, and synthesizing conclusion (`criteria.jsonl:72`, `.readability[1]`).
21. **Paragraph cohesion and transitions** — 0.15; effective 0.0210 (`criteria.jsonl:72`, `.readability[2]`).
22. **Clarity and synthesis of sourced information** — 0.15; effective 0.0210; rewards multi-source synthesis and penalizes serial paper summaries, excessive density, and redundancy (`criteria.jsonl:72`, `.readability[3]`).
23. **Clarity of data/evidence** — 0.10; effective 0.0140; includes understandable study findings and clear summary tables/figures if used (`criteria.jsonl:72`, `.readability[4]`).
24. **Formatting/layout/visual consistency** — 0.10; effective 0.0140 (`criteria.jsonl:72`, `.readability[5]`).
25. **Audience adaptation and term explanation** — 0.10; effective 0.0140 (`criteria.jsonl:72`, `.readability[6]`).

## A4. What the RACE judge actually sees

### A4.1 Cleaning contract

Before RACE scoring, the target article is passed through an LLM cleaner (`deepresearch_bench_race.py:202-229`). The cleaner is instructed to:

- remove all citation links, citation marks, reference lists, and footnotes;
- retain every other original element;
- preserve text contained inside citation markers while dropping the markers;
- return empty text for a chunk that consists only of bibliography/footnote definitions;
- not invent or complete content outside the provided chunk (`prompt/clean_prompt.py:21-37`).

The cleaner does **not** contain deterministic markdown-removal code. Therefore:

- **Headings, paragraphs, bold text, bullet lists, and tables are supposed to survive**, because the prompt says retain all non-citation content (`clean_prompt.py:28-31`).
- **Citations, URLs used as citations, citation markers, footnotes, and bibliography sections are supposed to disappear** (`clean_prompt.py:28-31`).
- Exact preservation of markdown/table syntax is **not guaranteed** because this is an LLM rewrite, not a parser. What survives in a particular run depends on cleaner output; the only code-level validity test is at least 100 non-whitespace characters (`utils/clean_article.py:22-33`).

Long reports are split around paragraph/newline boundaries, cleaned chunkwise, and concatenated without an inserted delimiter (`utils/clean_article.py:95-182,200-223`). This can affect formatting at chunk boundaries. A failed or truncated chunk can trigger recursive halving to depth 3 (`utils/clean_article.py:225-250`). Existing cleaned output is cached by ID and reused unless explicitly forced through file handling (`utils/clean_article.py:327-370`; `deepresearch_bench_race.py:365-369`).

### A4.2 Inputs to the score judge

The actual comparative score prompt contains:

1. The original task prompt.
2. `article_1` = cleaned target article.
3. `article_2` = high-quality cleaned reference article.
4. The task-specific criterion names and explanations.

The criterion **weights are deliberately stripped before prompting** (`deepresearch_bench_race.py:33-54`). Thus the score judge does not know which criteria carry more downstream weight; weighting occurs only after the LLM returns scores. The articles and criteria are formatted into `generate_merged_score_prompt` (`deepresearch_bench_race.py:80-104`; `prompt/score_prompt_en.py:1-26`).

## A5. Judge scoring mechanic: scale, reference basis, and partial credit

1. **Comparative/reference-based, not absolute single-report scoring.** The judge is asked to deeply compare target and reference on each criterion and score both separately (`prompt/score_prompt_en.py:1-33`). The production scorer imports `generate_merged_score_prompt`, not the point-wise or vanilla alternatives (`deepresearch_bench_race.py:14-17,95-104`).
2. **Scale:** continuous 0–10 per criterion for each article (`prompt/score_prompt_en.py:35-41`). Decimal values are allowed.
3. **Generic anchors:**
   - 0–2: almost completely fails.
   - 2–4: minimally meets, significant deficiencies.
   - 4–6: basically meets, average.
   - 6–8: largely meets, notable strengths.
   - 8–10: fully meets or exceeds (`prompt/score_prompt_en.py:35-41`).
4. **Partial credit:** any continuous value is permitted. The only formal partial-credit rule is the five-band continuum above. There are **no criterion-specific point schedules, required evidence counts, or deterministic “half points.”** Criterion-specific full/partial/zero meaning comes from the criterion text/explanation combined with those generic bands.
5. **Full versus partial versus zero for every criterion type:**
   - **Full (8–10):** the target fully meets or exceeds the complete criterion explanation, including named components and constraints.
   - **Partial (2–8, severity dependent):** it satisfies some named components, lacks depth/breadth/directness, or has notable omissions; 4–6 is “basically meets,” 6–8 “largely meets.”
   - **Zero/near-zero (0–2):** it almost completely fails the criterion, omits it, contradicts it, or violates the relevant instruction.
   These are the only grounded universal rules (`score_prompt_en.py:35-41`). Any more granular universal rubric is **unknown because the prompt does not provide one**.
6. **No hard score validation:** returned values are cast to float but not range-clamped (`utils/score_calculator.py:69-89`). A judge output outside 0–10 would be used as-is.
7. **Response validation:** top-level presence of all four dimension keys is required, but the code does not require every expected sub-criterion to appear (`deepresearch_bench_race.py:118-132`). JSON extraction has multiple permissive fallbacks and can reconstruct a simplified object from criterion/score regexes (`utils/json_extractor.py:4-100,129-149`).

## A6. Exact aggregation formula

Let task dimension weights be `W_d`; within dimension `d`, criterion weights be `w_dk`; judge raw score for report `R` and criterion `k` be `s_R,dk`.

### A6.1 Code’s dimension raw score

For returned and matched criterion items:

`D_R,d = Σ_k (s_R,dk × w_dk) / Σ_k w_dk`

This follows `utils/score_calculator.py:53-64,91-124,136-147`. Because stored sub-weights sum to 1, this is ordinarily the standard weighted average. However, if a sub-criterion is missing or skipped, its weight is omitted from both numerator and denominator, so the remaining returned criteria are renormalized rather than the missing criterion receiving zero (`score_calculator.py:64-89,119-144`).

Criterion matching proceeds by exact string, then case-insensitive equality, then substring containment. If no match is found, the code assigns the **average criterion weight for that dimension** (`score_calculator.py:91-118`).

### A6.2 Intermediate report score

`I_R = Σ_d (W_d × D_R,d)`

implemented at `score_calculator.py:146-158`. This matches paper §3.1 “Overall Score Calculation” (`drbench.tex:217-220`).

### A6.3 Final Overall

`Overall_target = I_target / (I_target + I_reference)`

implemented at `deepresearch_bench_race.py:151-160` and paper equation in §3.1 (`drbench.tex:217-221`). It lies near 0.5 when target and reference receive similar raw scores. It is not an absolute percentage of rubric fulfillment.

### A6.4 Published dimension scores

For each dimension:

`PublishedDim_target,d = D_target,d / (D_target,d + D_reference,d)`

implemented at `deepresearch_bench_race.py:162-175`. Thus the displayed Comprehensiveness/Insight/Instruction/Readability values are also relative target shares, not raw 0–10 scores.

### A6.5 Dataset-level leaderboard aggregation

The output file averages each successful task’s published relative dimension and Overall scores arithmetically (`deepresearch_bench_race.py:478-514`). Failed tasks are excluded (`deepresearch_bench_race.py:491-498`). Leaderboard tooling multiplies these 0–1 values by 100 for display (`utils/rank_leaderboard.py:16-37`; GPT-5.5 equivalent `utils/rank_leaderboard_gpt55.py:16-41`).

### A6.6 Non-obvious consequences

- Overall is **not** `Σ W_d × PublishedDim_d`; the ratio is applied after weighting target and reference raw dimension scores (`deepresearch_bench_race.py:151-170`).
- A criterion’s leverage depends on target improvement **and** the reference score because the final transform is relative.
- Missing returned sub-criteria are not automatically zeroed; remaining weights renormalize (`score_calculator.py:119-144`).
- The variable used to decide whether to compute a reference dimension average is the last loop’s `article_2_score`; if that final item lacks a reference score, the whole reference dimension becomes zero despite earlier reference entries (`score_calculator.py:136-140`). Normal comparative output should contain all reference scores, but the edge case exists.

---

# B. FACT — complete map

## B1. What FACT measures

FACT is explicitly separate from report-quality scoring. It evaluates factual grounding and web retrieval through **Factual Abundance** and **Citation Trustworthiness**: extraction/deduplication of statement–URL pairs, retrieval of cited webpages, support judgment, and two citation metrics (paper §3.2; `drbench.tex:225-236`; README `README.md:100-109`).

The two intended metrics are:

1. **Citation Accuracy (C. Acc.):** how accurately cited sources support the statements attached to them.
2. **Average Effective Citations per Task (E. Cit.):** how many unique, verifiably supported statement–URL pairs are produced per task.

There is **no citation recall metric in the code or paper.** FACT does not determine how many true claims should have been cited, nor how many relevant sources were missed. “Recall” is therefore **unknown/not defined** in this benchmark.

## B2. End-to-end executable FACT pipeline

The root script runs the stages independently after RACE: extraction, deduplication, scraping, validation, and statistics (`run_benchmark.sh:71-95`). FACT uses the **raw report**, not the RACE-cleaned report (`run_benchmark.sh:75-90`).

### B2.1 Citation extraction

The FACT judge receives the full raw report and is instructed to find **all** in-text citation instances in four formats: trailing numeric citations, bracketed numbers, line-annotated bracket citations, and markdown links (`utils/extract.py:39-51`). It must output `(fact, ref_idx, url)` triplets with enough nearby context to make the fact complete and independently understandable (`extract.py:47-58`).

Rules:

- A fact citing multiple references becomes multiple statement–URL triplets (`extract.py:47-50`).
- A report with references only in a bibliography but no in-text citation location yields an empty list (`extract.py:51`).
- Markdown links inside extracted fact text are reduced to `[title]` before storage (`extract.py:84-88,134-138`).
- For paths containing `openai`, browser text fragments `#:~:text=` are removed from markdown-link URLs before extraction for fairness (`extract.py:68-81,187-191`). This special case depends on the raw file path string, not report metadata.
- The model call occurs once before the three-attempt JSON parse loop. Parse failures retry the same response rather than call the model again (`extract.py:124-149`). If all parse attempts fail, the task is not written with a `citations` field (`extract.py:151-152`).

### B2.2 Deduplication

Extracted triplets are first grouped by exact URL string (`utils/deduplicate.py:47-53`). For a URL with one fact, that fact is retained. For a URL with multiple facts, the FACT judge receives numbered statements and is told that two statements are duplicates **only if they express exactly the same thing** (`deduplicate.py:21-29,73-110`). The result is a dictionary keyed by URL whose value contains the retained unique facts.

If deduplication fails, returns an invalid list, returns index zero, or returns too many indices, the fallback retains **every fact**, not one (`deduplicate.py:90-110`). Therefore dedup failure can increase pair counts but does not delete facts.

### B2.3 Web retrieval

Each unique URL is fetched through Jina Reader at `https://r.jina.ai/{url}`. The request asks for JSON and generated alt text and uses a 60-second Jina timeout header (`utils/api.py:202-233`). Scraping retries up to three times (`utils/scrape.py:12-20`). A successful reference concatenates title, description, and page content; a failure becomes literal text `scrape failed: ...` (`scrape.py:22-35`).

### B2.4 Support judgment

For each URL, all unique facts associated with that URL are numbered and judged together against the retrieved content (`utils/validate.py:67-106`). The judge labels each:

- `supported` if the statement’s facts/data can be found **entirely or partially** in the reference; rounded numerical agreement is accepted.
- `unsupported` if all facts/data in the statement cannot be found.
- `unknown` if the reference has no valid information, e.g. page not found (`utils/validate.py:39-64`).

The “entirely or partially” rule means a compound statement can receive `supported` even when only part is present. The current code does not require full entailment of every clause.

Validation retries the LLM up to three times and requires the result count to equal the fact count (`validate.py:116-140`). Failed validations store an empty result plus an error (`validate.py:137-140,206-211`).

## B3. What counts as valid/effective and how precision is computed

### B3.1 Code definitions

For each validated result:

- `unknown` is excluded entirely from both the citation denominator and supported count (`utils/stat.py:23-30`).
- `unsupported` contributes one to `total_citations` and zero to `total_valid_citations` (`stat.py:26-30`).
- `supported` contributes one to both (`stat.py:26-30`).
- Any URL group with `validate_error != None` is excluded (`stat.py:23-25`).

Thus under current executable code:

- **Judged citation count per included task** = `N_nonunknown / N_tasks_with_nonempty_extracted_citations` (`stat.py:20-39`).
- **Effective citations per included task** = `N_supported / N_tasks_with_nonempty_extracted_citations` (`stat.py:20-39`).
- **Citation accuracy / valid_rate** = `N_supported / N_nonunknown` across the entire run (`stat.py:37-40`). This is a **micro precision** over non-unknown, successfully validated unique statement–URL pairs.

A “valid/effective citation” therefore means one retained statement–URL pair whose fetched content is judged `supported`; it is not merely a reachable URL and not merely a high-quality domain.

### B3.2 No quality/credibility scoring

FACT does not score publisher reputation, peer review, recency, authority, primary-versus-secondary status, or source diversity. Those can affect task-specific RACE criteria if explicitly present, but FACT’s executable support test is only whether retrieved content supports the statement (`validate.py:39-64`). A low-quality webpage can earn FACT support if it contains the claim.

### B3.3 No recall or uncited-fact penalty

FACT extracts only facts that have a citation marker/location (`extract.py:47-51`). Uncited factual claims are invisible to FACT. Therefore:

- unsupported cited claims lower accuracy;
- supported unique cited claims increase effective citations;
- uncited claims neither help nor directly hurt FACT;
- bibliography-only sourcing produces no pairs;
- there is no denominator of “all factual claims that should have citations.”

## B4. Paper’s intended FACT formulas

Paper Appendix “Detailed Calculation of Citation Metrics” defines, for task `t`, `U_t` as deduplicated statement–URL pairs, `N_u,t` as judged pairs, and `N_s,t` as supported pairs (`drbench.tex:555-564`). It then defines:

`Acc_t = N_s,t / N_u,t` when `N_u,t > 0`, otherwise `0` (`drbench.tex:566-576`).

`C.Acc = (1 / |T|) × Σ_t Acc_t` (`drbench.tex:578-581`).

`E.Cit = (Σ_t N_s,t) / |T|` (`drbench.tex:583-590`).

This is macro accuracy across all benchmark tasks plus supported-pair abundance over all tasks.

## B5. Code-versus-paper FACT discrepancy

The current code does **not** implement the paper’s citation-accuracy formula:

1. It skips every task with empty `d['citations']` before incrementing `total_num` (`utils/stat.py:20-22,33`). The paper explicitly assigns no-citation tasks accuracy 0 and retains them in `|T|` (`drbench.tex:569-580`).
2. It computes `valid_rate = total_valid_citations / total_citations`, a global micro ratio (`stat.py:37-40`), rather than averaging each task’s `supported/judged` ratio.
3. It excludes `unknown` pairs and validation-error groups from the denominator (`stat.py:23-30`), whereas the paper describes binary support/not-support after judgment (`drbench.tex:560-563`).
4. It divides effective citations by `total_num`, meaning tasks with no extracted citations are excluded (`stat.py:20-39`), whereas the paper divides by all tasks (`drbench.tex:583-590`).

**Operational conclusion:** for reproducing this checkout’s leaderboard-generation artifacts, use the code formula. For describing the published methodological ideal, use the paper formula. They must not be conflated.

## B6. Failure behavior and gaming-relevant mechanics

1. **Broken/unreadable source:** scrape failure text should yield `unknown`; unknown is excluded from precision and effective count (`scrape.py:22-35`; `validate.py:39-41`; `stat.py:23-30`). It therefore usually does not directly lower code `valid_rate`, but it cannot increase effective citations.
2. **Partial source support:** counts as `supported`, even for a compound statement (`validate.py:39-42`). Narrow, atomic claims make support judgment less ambiguous; the extractor itself requests complete contextual facts (`extract.py:47-58`).
3. **Repeated same claim and URL:** intended to count once (`deduplicate.py:21-29,73-110`).
4. **Same claim with multiple URLs:** becomes multiple pairs and each can count as supported (`extract.py:47-50`).
5. **Multiple distinct claims using one URL:** each retained unique fact is judged and can count separately (`deduplicate.py:47-53,73-114`; `validate.py:67-70`).
6. **Only reference list, no inline mapping:** zero extracted pairs (`extract.py:47-51`).
7. **No extracted citations:** current `stat.py` excludes that task from all reported FACT denominators; if every task had no citations, division by zero would occur (`stat.py:20-40`).

## B7. Relationship between FACT and RACE

RACE and FACT are independent outputs:

- RACE runs first and writes `race_result.txt`; FACT runs separate modules and writes `fact_result.txt` (`run_benchmark.sh:35-95`).
- RACE Overall uses only the four RACE dimension scores and weights (`score_calculator.py:146-158`; `deepresearch_bench_race.py:151-160`).
- FACT citation accuracy/effective citations do **not** enter RACE Overall.
- Citation behavior can still indirectly affect RACE before cleaning if source restrictions or evidence quality are represented in task-specific criteria, but citation links/markers/reference lists are removed before the RACE judge sees the report (`clean_prompt.py:28-31`). For task 72, source-type and language constraints are explicit Instruction Following criteria (`criteria.jsonl:72`), yet the cleaner removes the bibliography. Whether the judge can verify those constraints from the remaining cleaned prose is consequently limited and run-dependent; the exact verification ability is **unknown** because the source metadata has been stripped.

---

# C. Scoreable-surface inventory

This inventory is the union of the explicit generation prompts, the actual stored 2,517 criteria, the full task-72 rubric, and FACT mechanics. Task-specific criterion wording varies; no fixed global checklist exists. Each RACE item’s actual coefficient is `task dimension weight × task sub-weight`, followed by reference-relative normalization. Representative task lines prove concrete instances.

1. **Cover every explicitly named topic/sub-question.** Dimension: Comprehensiveness + Instruction Following. Weight: task-specific; often 0.15–0.30 within the dimension. Proof: generation requires all key areas and no omissions (`criteria_prompt_en.py:113-124`) and direct/full answers (`criteria_prompt_en.py:315-326`); examples task 30’s four named theories (`criteria.jsonl:30`) and task 72’s labor-market dimensions (`criteria.jsonl:72`).
2. **Cover the requested breadth of entities, sectors, cases, populations, or categories.** Dimension: Comprehensiveness/Instruction. Proof: task 72 industries, effective 0.0725 Comp plus 0.0375 Instruction (`criteria.jsonl:72`); task 91 armor classes/character groups (`criteria.jsonl:91`).
3. **Respect geography.** Dimension: Instruction Following. Proof: generation explicitly names geography as a scope limitation (`criteria_prompt_en.py:316-324`); numerous actual task criteria encode national/city scope (`criteria.jsonl:1-100`).
4. **Respect time period and temporal cutoff.** Dimension: Instruction Following and sometimes Comprehensiveness. Proof: task 4 requires 2010-present and gives time adherence sub-weight 0.20 (`criteria.jsonl:4`); scope-generation rule (`criteria_prompt_en.py:316-324`).
5. **Use the required deliverable/form.** Dimension: Instruction Following + Readability. Proof: task 4 mind map receives 0.30 of Instruction (`criteria.jsonl:4`); task 72 literature-review form receives 0.10 (`criteria.jsonl:72`).
6. **Give every requested output field for every item.** Dimension: Instruction/Comprehensiveness. Proof: task 91 requires power, techniques, arcs, and fate for each selected character (`criteria.jsonl:91`).
7. **Provide the requested number of recommendations/options.** Dimension: Instruction Following. Proof: criteria generator decomposes exact questions/constraints (`criteria_prompt_en.py:315-326`); actual tasks with “2–3” predictions encode that output requirement (`criteria.jsonl:2,32`).
8. **Remain on the central topic; avoid material digressions.** Dimension: Instruction Following. Proof: directness/relevance requirement (`criteria_prompt_en.py:317,323-325`); task 72 focus criterion effective 0.0500 (`criteria.jsonl:72`).
9. **Define key concepts and establish task context.** Dimension: Comprehensiveness. Proof: task 72 4IR grounding effective 0.0290 (`criteria.jsonl:72`); task 73 defines “new paradigm” and “holistic empowerment” (`criteria.jsonl:73`).
10. **Provide breadth and depth, not a surface list.** Dimension: Comprehensiveness. Proof: exact dimension and generation definitions (`criteria_prompt_en.py:103,113-124`).
11. **Use sufficient concrete data, facts, cases, or study evidence.** Dimension: Comprehensiveness and Readability. Proof: readability prompt includes data accuracy/clarity and charts/tables (`criteria_prompt_en.py:411-418`); task 72 literature representativeness and data clarity (`criteria.jsonl:72`).
12. **Represent the literature/current evidence broadly and fairly.** Dimension: Comprehensiveness. Proof: task 72 representative current high-quality literature, themes/findings/debates, effective 0.0435 (`criteria.jsonl:72`).
13. **Cover multiple perspectives and balance benefits against risks/costs.** Dimension: Comprehensiveness and Insight. Proof: task 72 balanced impacts effective 0.0290 (`criteria.jsonl:72`); generation seeks perspectives and diversity (`criteria_prompt_en.py:114-124`).
14. **Compare entities/dimensions systematically rather than describe them independently.** Dimension: Comprehensiveness + Insight. Proof: task 2 and task 32 horizontal-comparison criteria (`criteria.jsonl:2,32`).
15. **Analyze causal mechanisms.** Dimension: Insight. Proof: insight generation requires deduction/logical depth (`criteria_prompt_en.py:214-225`); task 72 mechanisms effective 0.0800 (`criteria.jsonl:72`).
16. **Explain relative importance and interaction among drivers.** Dimension: Insight. Proof: analytical-depth and synthesis requirements (`criteria_prompt_en.py:215-224`); task 4 driver linkage (`criteria.jsonl:4`).
17. **Synthesize across sources/industries/cases; do not serially summarize.** Dimension: Insight + Readability. Proof: task 72 critical cross-industry synthesis effective 0.0800 and sourced-information synthesis effective 0.0210 (`criteria.jsonl:72`).
18. **Identify consensus, disagreement, uncertainty, limitations, and research gaps.** Dimension: Insight. Proof: task 72 critical synthesis and future agenda criteria, effective 0.0800 and 0.0480 (`criteria.jsonl:72`).
19. **Develop emergent themes, conceptual linkages, or novel perspectives.** Dimension: Insight. Proof: task 72 effective 0.0640 (`criteria.jsonl:72`); “originality” is in the exact dimension definition (`criteria_prompt_en.py:104`).
20. **Make reasoning logically consistent from evidence to conclusions.** Dimension: Insight. Proof: generation explicitly requires logical consistency/rigor (`criteria_prompt_en.py:216,223-225`); task 30 argument rigor (`criteria.jsonl:30`).
21. **Use scenarios/forecasting when the task asks about the future.** Dimension: Insight and Instruction. Proof: task 4 future scenarios and justified support/resistance (`criteria.jsonl:4`); task 32 future topic prediction (`criteria.jsonl:32`).
22. **Prioritize alternatives and justify rankings.** Dimension: Insight. Proof: tasks requiring “most likely” selections encode logical chain and comparative judgment (`criteria.jsonl:2,32`).
23. **Provide actionable recommendations linked to the preceding analysis.** Dimension: Insight + Instruction. Proof: insight is value of conclusions (`criteria_prompt_en.py:104,216-224`); task 73 actionable novice guidance (`criteria.jsonl:73`).
24. **Discuss implications for relevant stakeholders.** Dimension: Insight. Proof: task 72 policy/education/workforce implications effective 0.0480 (`criteria.jsonl:72`).
25. **Use only allowed source classes when specified.** Dimension: Instruction Following. Proof: task 72 journal-only requirement effective 0.0375 (`criteria.jsonl:72`).
26. **Use only allowed source languages when specified.** Dimension: Instruction Following. Proof: task 72 English-only criterion effective 0.0250 (`criteria.jsonl:72`).
27. **Match intended audience knowledge and needs.** Dimension: Readability. Proof: readability generation requires audience adaptation (`criteria_prompt_en.py:411-420`); task 73 novice-teacher tone/accessibility and task 72 academic audience (`criteria.jsonl:73,72`).
28. **Use clear, grammatical, precise, fluent language.** Dimension: Readability. Proof: exact definition and readability generation (`criteria_prompt_en.py:103-106,411-418`); task 72 effective 0.0280 (`criteria.jsonl:72`).
29. **Use terminology accurately and explain specialized terms.** Dimension: Readability. Proof: audience/terminology requirements (`criteria_prompt_en.py:411-419`); task 72 effective 0.0140 (`criteria.jsonl:72`).
30. **Maintain an appropriate tone/style for the requested genre.** Dimension: Readability/Instruction. Proof: task 72 academic tone and literature-review form (`criteria.jsonl:72`); task 73 novice-helpful tone (`criteria.jsonl:73`).
31. **Use a clear macro-structure with introduction, logical sections/headings, synthesis, and conclusion.** Dimension: Readability. Proof: task 72 effective 0.0280 (`criteria.jsonl:72`); readability prompt structure requirements (`criteria_prompt_en.py:411-418`).
32. **Make headings informative and hierarchy navigable.** Dimension: Readability. Proof: task 72 structure explanation (`criteria.jsonl:72`); task 30 headings/subheadings criterion (`criteria.jsonl:30`).
33. **Keep paragraphs focused and transitions explicit.** Dimension: Readability. Proof: task 72 effective 0.0210 (`criteria.jsonl:72`).
34. **Control information density and redundancy.** Dimension: Readability. Proof: readability generation (`criteria_prompt_en.py:415`) and task 72 sourced-information criterion (`criteria.jsonl:72`).
35. **Present quantitative/qualitative evidence clearly and interpret it.** Dimension: Readability. Proof: task 72 effective 0.0140 (`criteria.jsonl:72`).
36. **Use tables/charts/visual aids when they improve comparison or comprehension, and label them clearly.** Dimension: Readability. Proof: readability generation includes data/visualization (`criteria_prompt_en.py:416`); remote-work example assigns a separate 0.10 sub-weight to visualizations (`criteria_prompt_en.py:471-478`).
37. **Highlight key findings and summaries with formatting/bullets where useful.** Dimension: Readability. Proof: remote-work example 0.05 sub-weight (`criteria_prompt_en.py:481-483`).
38. **Maintain professional, consistent formatting/layout.** Dimension: Readability. Proof: readability generation (`criteria_prompt_en.py:417`) and task 72 effective 0.0140 (`criteria.jsonl:72`).
39. **Preserve useful non-citation structure through RACE cleaning.** Dimension: all RACE dimensions indirectly. Proof: cleaner retains all non-citation content but removes citation apparatus (`clean_prompt.py:25-36`). Tables/headings can help; bibliography text cannot reach the RACE judge.
40. **Attach citations at exact claim locations.** Metric: FACT extraction eligibility. Proof: bibliography-only references return no pairs (`extract.py:47-51`).
41. **Use extractable citation forms and real URLs.** Metric: FACT. Proof: supported forms and URL extraction (`extract.py:39-65`).
42. **Make each cited claim complete and understandable.** Metric: FACT. Proof: extractor requests surrounding context (`extract.py:47-58`).
43. **Use reachable URLs whose page text can be fetched.** Metric: FACT effective citations. Proof: Jina retrieval (`api.py:211-233`; `scrape.py:12-35`).
44. **Ensure source text supports at least part of the exact attached statement.** Metric: FACT accuracy/effective citations. Proof: support rule (`validate.py:39-42`).
45. **Avoid attaching sources that contain none of the statement’s facts/data.** Metric: FACT accuracy loss. Proof: unsupported definition and denominator (`validate.py:39-42`; `stat.py:26-30`).
46. **Increase the number of unique supported statement–URL pairs.** Metric: FACT effective citations. Proof: extraction multiplicity, exact dedup, and supported count (`extract.py:47-50`; `deduplicate.py:21-29`; `stat.py:26-39`).
47. **Avoid exact duplicate same-URL claims.** Metric: FACT abundance. Proof: deduplication retains one representative for exact semantic duplicates (`deduplicate.py:21-29,73-110`).
48. **Multiple independent supporting URLs for one fact can each count.** Metric: FACT abundance/accuracy. Proof: one fact citing multiple references becomes multiple triplets (`extract.py:47-50`).
49. **Multiple distinct supported facts from one source can each count.** Metric: FACT abundance. Proof: grouping is by URL but retains a list of unique facts, each separately validated (`deduplicate.py:47-53,73-114`; `validate.py:67-70`).
50. **Do not rely on uncited factual abundance to improve FACT.** Metric: FACT. Proof: extraction examines only citation instances and returns empty for unmapped reference lists (`extract.py:47-51`).
51. **Do not assume high source prestige improves FACT.** Metric: none in FACT; possible RACE task criterion only. Proof: support prompt checks textual support, not credibility (`validate.py:39-64`).
52. **Do not optimize RACE Overall by citations alone.** RACE citations are cleaned and FACT is separate (`clean_prompt.py:28-31`; `run_benchmark.sh:35-95`; `deepresearch_bench_race.py:151-160`).

---

# D. Judge and measurement caveats

1. **Current versus legacy judge:** Current official main defaults are GPT-5.5 RACE and GPT-5.4-mini FACT (`utils/api.py:43-55,72-75`; `README.md:15-31`). Paper/legacy results use Gemini-2.5-Pro RACE and Gemini-2.5-Flash FACT (`drbench.tex:243-248`; legacy `utils/api.py:20-21`).
2. **Two scales are empirically different and not transformable by one constant.** On five models appearing in both official HF CSVs, GPT-5.5 minus Gemini Overall deltas are: cellcog-max −0.89, Gemini Deep Research +0.27, OpenAI Deep Research +1.39, Perplexity +2.59, Grok +3.00 (`data_gpt55/leaderboard.csv:2,8-11`; legacy `data/leaderboard.csv:8,28,30,39-40`). Rank/score comparison must stay within judge regime.
3. **RACE scores are reference-relative, compressed around 50.** The paper explicitly says to focus on rankings/proportional differences rather than absolute score values because of the reference-relative frame (`drbench.tex:345`). The formula itself guarantees 0.5 for equal intermediate target/reference scores (`deepresearch_bench_race.py:155-160`).
4. **Current sampling parameters:** temperature and `top_p` are intentionally omitted; current requests set model, `max_completion_tokens=64000` by default, and reasoning effort low/medium/low for clean/score/fact (`utils/api.py:22-25,80-96,158-174`). The provider’s default sampling behavior therefore governs; exact effective temperature is **unknown** from this repository.
5. **Legacy sampling parameters:** Gemini code sets a 16,000-token thinking budget but no explicit temperature, top-p, or seed (`Gemini-2.5` branch `utils/api.py:34-63`). Exact effective sampling defaults are **unknown** from the repository.
6. **No score-repeat averaging:** RACE scoring makes one successful judge call per task; retries happen only on errors/invalid JSON, up to ten attempts (`deepresearch_bench_race.py:106-149`). Therefore run-to-run judge variance is not averaged out. The exact variance magnitude is **unknown without repeated controlled runs on identical cleaned inputs**.
7. **Criteria-weight variance is partially averaged:** criteria generation uses five samples for dimension weights but only one accepted generated criterion list per dimension (`generate_criteria.py:129-180,182-224`). Stored criteria are then fixed for scoring.
8. **Reference quality and contamination:** the historical reference is a Gemini-2.5-Pro Deep Research report (`drbench.tex:246-248`). A target close to that report’s style/content can benefit from pairwise comparison. Current repo still loads the static `reference.jsonl` (`deepresearch_bench_race.py:28-30,257-264`).
9. **Weights hidden from judge:** the LLM cannot allocate scoring attention according to downstream weights because weights are stripped (`deepresearch_bench_race.py:33-54`). It sees criterion names/explanations only.
10. **Cleaner nondeterminism and information removal:** source lists and citation markers are removed by an LLM rewrite before RACE (`clean_prompt.py:21-37`; `clean_article.py:48-84`). Criteria requiring source class/language may therefore be difficult for the RACE judge to verify after cleaning.
11. **Long-report chunk effects:** cleaner chunks, processes in parallel, and concatenates outputs (`clean_article.py:95-223`). Formatting and cross-chunk continuity can change; minimum accepted output is only 100 characters (`clean_article.py:31-33`).
12. **Parser permissiveness:** RACE JSON extractor can fall back to regex reconstruction (`json_extractor.py:95-149`). Missing sub-criteria are renormalized rather than zeroed (`score_calculator.py:119-144`).
13. **No range clamp:** malformed judge scores outside 0–10 can enter calculations (`score_calculator.py:69-89`).
14. **Failed RACE tasks are excluded from averages:** only successful results are averaged (`deepresearch_bench_race.py:490-505`). Different failure sets can make runs non-comparable.
15. **FACT support is permissive:** partial presence qualifies as supported and rounding is accepted (`validate.py:39-42`).
16. **FACT unknowns are ignored by code precision:** unreachable/invalid pages normally do not lower `valid_rate`; they reduce count opportunity (`scrape.py:22-35`; `validate.py:39-41`; `stat.py:23-30`).
17. **FACT’s executable formula differs from the paper:** micro non-unknown precision and citation-bearing-task denominator versus paper macro all-task accuracy/effective count (§B.5).
18. **FACT extraction and validation are LLM-mediated:** missed citations, malformed extraction, semantic dedup errors, and support-classification errors alter the metric. The original paper reports Gemini-2.5-Flash agreement of 96% on human “support” and 92% on “not support” for a 100-pair sample (`drbench.tex:514-519`); this does not establish GPT-5.4-mini’s error rate, which is **unknown from available official artifacts**.
19. **FACT does not measure source credibility, factual truth independent of the cited page, citation recall, or uncited hallucinations.** It measures source-text support for extracted cited statements (`validate.py:39-64`; `stat.py:20-40`).
20. **Leaderboard FACT columns may be pending under GPT-5.5 regime.** The checked GPT-5.5 CSV has `-` for FACT for all ten displayed models (`data_gpt55/leaderboard.csv:1-11`), while the UI says re-evaluation is being populated (`tabs/leaderboard_tab_gpt55.py:184-220`). As of 2026-07-23, do not infer new-judge FACT standings from legacy FACT values.

---

# E. Highest-leverage implications for later fix mapping

For task 72 specifically, the largest direct pre-normalization coefficients are the two Insight surfaces **mechanistic restructuring analysis** and **critical cross-industry synthesis** at 0.0800 each, followed by **breadth of restructuring dimensions** and **industry scope** at 0.0725 each, then **emergent theoretical themes** at 0.0640 (`criteria.jsonl:72`). The next tier is focused instruction compliance and 4IR/implication depth (0.0375–0.0500). Across all 100 tasks, Insight has the highest mean dimension weight (0.352), Comprehensiveness second (0.292), Instruction third (0.2147), and Readability fourth (0.1413), but exact task weights range widely (`criteria.jsonl:1-100`). FACT is orthogonal: the only direct levers are extractable inline claim–URL mappings, successful retrieval, textual support, uniqueness, and supported-pair volume (`extract.py:39-65`; `deduplicate.py:21-29`; `validate.py:39-64`; `stat.py:20-40`).

## EXECUTIVE SUMMARY

The highest-leverage scoreable surfaces are: **(1)** task-specific Insight—causal/mechanistic analysis, cross-source synthesis, logical integration, uncertainty, and novel implications—because Insight averages 35.2% of RACE weight and reaches 42%; **(2)** Comprehensiveness—complete coverage of every requested dimension/entity/industry/time scope with representative evidence—because it averages 29.2%; **(3)** exact Instruction Following, especially source/type/language/output constraints, because omissions receive separate criteria and can carry up to 45% within that dimension; **(4)** clear structure and synthesis-oriented readability, usually lower-weight but as high as 25% for audience/data-presentation-heavy tasks; and **(5)** FACT’s independent supported-pair surface: inline, extractable, reachable citations attached to atomic claims, with more unique supported statement–URL pairs raising effective citations and unsupported pairs lowering code precision. For task 72, the four largest coefficients are mechanistic labor-market analysis (0.0800), critical cross-industry synthesis (0.0800), restructuring-dimension breadth (0.0725), and industry breadth (0.0725), so fixes that deepen mechanisms and synthesis while closing missing sector/effect coverage have the largest grounded RACE headroom (`criteria.jsonl:72`); citation-count work cannot substitute for those RACE surfaces because FACT is calculated separately (`run_benchmark.sh:35-95`).
