# SCORING_SPEC — EXHAUSTIVE per-scoring-point map of RACE + FACT (Phase 1, self-contained)
Grounded line-by-line by Sol + Fable (agree on every mechanic); RACE judge prompt + score bands verified
verbatim by Opus from source. Benchmark checkout commit 469cce54 (2026-05-11), paper arXiv 2506.11763
(drbench.tex). Nothing here points elsewhere; every scoring point is stated in full.

================================================================================
PART I — RACE (report-quality board)
================================================================================

## I.0 Judge identity & call mechanics
- Production judge model: **openai/gpt-5.5** (utils/api.py:43-55). Legacy/paper: Gemini-2.5-Pro. Two
  leaderboards, comparable only WITHIN a judge regime (README.md:15-31,24-29).
- ONE judge call per task (retries only on error/invalid-JSON, ≤10) → no averaging, run-to-run variance
  NOT cancelled (deepresearch_bench_race.py:106-149). No temperature/top_p/seed set; provider default
  sampling governs (utils/api.py:22-25). This is the source of the observed ±0.027 noise.
- Production scorer imports `generate_merged_score_prompt` — the COMPARATIVE, reference-based variant
  (deepresearch_bench_race.py:14-17,95-104). (static/point_wise/vanilla prompts exist but are NOT used.)

## I.1 What the judge is given (exact inputs; score_prompt_en.py:2-27)
1. `task_prompt` — the original task text.
2. `article_1` — the CLEANED TARGET report (ours).
3. `article_2` — the CLEANED REFERENCE report (the frozen Gemini-2.5-Pro Deep-Research report we must beat).
4. `criteria_list` — the task's criterion NAMES + EXPLANATIONS only. **Criterion WEIGHTS are stripped
   before prompting** (deepresearch_bench_race.py:33-54) — the judge cannot steer effort by weight.
The judge is told to compare the two articles criterion-by-criterion and score EACH article 0–10 per
criterion (score_prompt_en.py:28-41).

## I.2 The score scale — VERBATIM (score_prompt_en.py:35-41). Continuous 0–10, five bands:
- 0–2: Very poor. Almost completely fails to meet the criterion.
- 2–4: Poor. Minimally meets, significant deficiencies.
- 4–6: Average. Basically meets, neither good nor bad.
- 6–8: Good. Largely meets, notable strengths.
- 8–10: Excellent. Fully meets or exceeds.
No criterion-specific point schedule exists; meaning of full/partial/zero for a criterion = its
explanation text × these bands. Scores are NOT range-clamped (score_calculator.py:69-89).

## I.3 The four dimensions — VERBATIM definitions (criteria_prompt_en.py:101-106)
- **Comprehensiveness:** "The breadth, depth, and relevance of information coverage."
- **Insight:** "The depth, originality, logic, and value of the analysis and conclusions."
- **Instruction Following:** "Whether the report accurately and completely responds to all requirements
  and constraints of the task."
- **Readability:** "Clarity of structure, fluency of language, effectiveness of data presentation, and
  overall ease of understanding."

## I.4 Dynamic DIMENSION weighting (per task; 4 weights sum to 1.0)
### I.4a The rule the weight-LLM is given (criteria_prompt_en.py:29-33)
Analyze the task's content/implicit goals/difficulties/core value; allocate 4 decimal weights summing to
1.0; ADJUST FLEXIBLY to the task (no fixed weights); justify each weight against the task. There is NO
keyword/formula rule (e.g. no "finance→readability 0.15"); it is semantic. Two worked examples:
EV-feasibility → Ins0.35/Comp0.30/Inst0.20/Read0.15; renewable-stock-decade → Comp0.40/Read0.25/Inst0.20/
Ins0.15 (readability up because heavy comparative DATA presentation is a key success factor) (:41-82).
### I.4b Mechanics (generate_criteria.py)
5 weight samples/task; keep samples that parse and sum to 1.0±1e-6; average dims present in every kept
sample; renormalize to 1; round to 2 decimals; **the rounding residual is added to READABILITY**
(:30-104,129-180). So the stored readability weight silently absorbs rounding.
### I.4c ACTUAL distribution over all 100 tasks (criteria.jsonl:1-100; computed identically by Sol+Fable)
| Dimension | Mean | Median | Min (task) | Max (task) | Modes |
|---|---|---|---|---|---|
| Insight | **0.352** | 0.36 | 0.11 (t91) | 0.42 (t34) | 0.35×12, 0.38×11, 0.39×11, 0.40×10 |
| Comprehensiveness | 0.292 | 0.30 | 0.20 (t4,t30) | 0.37 (t91) | 0.30×25, 0.29×18 |
| Instruction | 0.215 | 0.20 | 0.13 (t43) | 0.35 (t48) | 0.19×16, 0.20×12 |
| Readability | 0.141 | 0.14 | 0.10 (t32,t54) | 0.25 (t73) | 0.15×24, 0.13×19, 0.14×14 |
Lang means (CN vs EN): Comp .287/.297, Ins .354/.350, Inst .220/.209, Read .139/.144.
=> INSIGHT is the biggest lever on ~every task. Readability smallest + narrowest.

## I.5 SUB-criteria generation (the real scoreboard: 2,517 items across 100 tasks)
Each dimension → a separate LLM call AFTER weights fixed; list accepted only if sub-weights sum to 1.0±1e-6;
model picks the count (generate_criteria.py:182-224). Per-dimension GENERATION instruction (what earns a
criterion) — criteria_prompt_en.py:
- Comp (:112-125): identify all key info areas/perspectives/depths; maximize coverage, minimize overlap/omission.
- Insight (:213-226): identify areas needing deep analysis/deduction/synthesis/value-judgment; reward
  analytical depth, logical consistency, originality, conclusion value; EXCLUDE mere information listing.
- Instruction (:314-327): decompose explicit questions/required outputs/scope limits (geography/time/subject)/
  objectives; score directness, completeness, on-topic, strict constraint adherence.
- Readability (:409-432): cover language clarity, structure, information density, data/visualization,
  formatting/layout, audience adaptation; sub-weights may adapt to task.
Corpus counts/task: Comp 6.4 (640), Insight 5.6 (557), Instruction 5.7 (571), Readability 7.5 (749).
Sub-weight ranges: Comp .05–.30, Insight .05–.35, Instruction .05–.45, Readability .03–.30.

## I.6 THE COMPLETE TASK-72 RUBRIC — all 25 scoring points
Task-72 = literature review on AI-driven labor-market restructuring; AI as a 4IR driver; disruptions
across industries; ONLY high-quality English-language journal articles (query.jsonl:72). Dimension weights:
Insight 0.32 / Comprehensiveness 0.29 / Instruction 0.25 / Readability 0.14 (criteria.jsonl:72).
"Effective" = dim_weight × sub_weight (its coefficient in the pre-normalization raw score).

COMPREHENSIVENESS (0.29):
1. 4IR grounding — sub .10, eff .0290. Full: defines AI in 4IR + explains driver role; partial: mentions/
   weakly links; zero: omits/misframes.
2. Breadth of restructuring dimensions — .25, eff **.0725**. Surface: job creation, displacement,
   transformation, skills, wages, productivity.
3. Industry-specific scope — .25, eff **.0725**. Diverse industries + common & sector-specific patterns.
4. Disruptive character & scale — .15, eff .0435. Magnitude, speed, transformative potential.
5. Literature depth/representativeness — .15, eff .0435. Broad/current/high-quality lit; themes, findings, debates.
6. Balanced impacts — .10, eff .0290. Challenges (displacement/skills/inequality) AND opportunities (jobs/
   productivity/quality).
INSIGHT (0.32):
7. Mechanisms of restructuring — .25, eff **.0800**. Task automation, augmentation, creation/destruction
   dynamics, org adaptation, effects on roles/skills/structures. ← largest cell
8. Critical cross-industry synthesis — .25, eff **.0800**. Patterns, sector variation, consensus, debate,
   uncertainty — NOT a catalog. ← largest cell
9. 4IR integration (insightful) — .15, eff .0480. 4IR framework explains nature/scale/interconnectedness.
10. Emergent themes / theoretical linkages / novel perspectives — .20, eff .0640. Higher-order synthesis.
11. Implications & future research agendas — .15, eff .0480. Policy/education/workforce; gaps; future agenda.
INSTRUCTION FOLLOWING (0.25):
12. Literature-review form — .10, eff .0250. Synthesize published research, not original empirical/opinion.
13. On-topic focus (AI labor restructuring) — .20, eff .0500. Digressions lose credit.
14. AI-as-4IR-driver theme present — .15, eff .0375.
15. Significant-disruption treatment — .15, eff .0375.
16. Various-industries coverage — .15, eff .0375.
17. ONLY high-quality journal articles — .15, eff .0375. Books/proceedings/news/blogs violate.
18. ONLY English-language articles — .10, eff .0250.
READABILITY (0.14):
19. Language clarity/precision/academic tone — .20, eff .0280.
20. Overall structure + logical org (scope-setting intro, thematic headings, logical sequence, synthesizing
    conclusion) — .20, eff .0280.
21. Paragraph cohesion & transitions — .15, eff .0210.
22. Clarity & synthesis of sourced info (penalizes SERIAL paper-summaries, density, redundancy) — .15, eff .0210.
23. Data/evidence clarity (incl. summary tables/figures if used) — .10, eff .0140.
24. Formatting/layout/visual consistency — .10, eff .0140.
25. Audience adaptation + term explanation — .10, eff .0140.
(Note items 17/18: the bibliography is stripped by cleaning, so journal/English compliance must be visible
in the PROSE for the judge to credit it — verification is limited/run-dependent.)

## I.7 AGGREGATION — every formula (score_calculator.py, deepresearch_bench_race.py)
- Dimension raw: `D_R,d = Σ_k(s_R,dk·w_dk) / Σ_k(w_dk)` (score_calculator.py:53-64). Missing/unmatched
  sub-criteria drop from BOTH numerator+denominator → remaining renormalize (NOT zeroed) (:119-144).
- Criterion matching: exact → case-insensitive → substring; NO match ⇒ assign the dimension's AVERAGE
  criterion weight (:91-118).
- Intermediate report score: `I_R = Σ_d(W_d·D_R,d)` (:146-158).
- **Overall (target) = I_target / (I_target + I_reference)** (deepresearch_bench_race.py:151-160). 0.5 = tie.
- Published per-dimension = `D_t,d/(D_t,d + D_ref,d)` — ALSO relative (:162-175).
- Dataset leaderboard = arithmetic mean of successful tasks' published values ×100; failed tasks excluded
  (:478-514; rank_leaderboard.py:16-37).
- Overall is NOT Σ W_d·PublishedDim_d — the ratio is applied AFTER weighting raw target/reference.
- A criterion's leverage depends on target improvement AND the reference's score there (relative frame).

## I.8 CLEANING contract — what the judge actually sees (clean_prompt.py:21-37; clean_article.py)
LLM cleaner instructed to: remove all citation links, citation MARKS ([1],[2],1,2,…), reference lists,
footnotes; RETAIN every other original element; keep text inside citation markers, drop the marker; return
EMPTY for a chunk that is only bibliography/footnotes; invent nothing (clean_prompt.py:28-37).
⇒ **Citations/refs/footnotes are DELETED (faithfulness buys 0 RACE points). Headings, paragraphs, bold,
bullets, TABLES are SUPPOSED to survive** (it's an LLM rewrite, not a parser → not guaranteed; only code
test = ≥100 non-whitespace chars, clean_article.py:31-33). Long reports chunked on newlines, cleaned in
parallel, concatenated with NO delimiter → formatting can shift at chunk boundaries; cleaned output cached
by ID (clean_article.py:95-223,327-370).

## I.9 RACE edge cases / gaming mechanics (all)
(a) Missing returned sub-criteria renormalize, not zero (score_calculator.py:119-144). (b) Fuzzy name match
→ average-weight fallback (:91-118). (c) No 0–10 clamp (:69-89). (d) Permissive JSON regex reconstruction
(json_extractor.py:95-149). (e) Only top-level 4 dimension keys required; per-sub-criterion presence not
enforced (deepresearch_bench_race.py:118-132). (f) Reference contamination: a target stylistically close to
the Gemini reference benefits from pairwise comparison. (g) Weights hidden from judge (can't steer by weight).
(h) Edge: if the LAST reference item lacks a score, that whole reference dimension can read 0 (:136-140).

================================================================================
PART II — FACT (citation board; FULLY INDEPENDENT of RACE)
================================================================================

## II.0 Independence
Separate pipeline on the RAW (un-cleaned) report, run after RACE; writes fact_result.txt; does NOT enter
RACE Overall (run_benchmark.sh:35-95; score_calculator.py:146-158). Judge = openai/gpt-5.4-mini (api.py:72-75).

## II.1 The two metrics (no recall metric exists)
- **Citation Accuracy (C.Acc)** = supported / judged pairs.
- **Effective Citations/task (E.Cit)** = supported unique pairs per task.
CODE (stat.py:20-40): valid_rate = total_valid/total (micro over non-unknown); E.Cit = N_supported /
N_tasks_with_nonempty_citations. PAPER (drbench.tex:566-590): Acc_t = N_s,t/N_u,t (0 if none), C.Acc =
mean over ALL tasks (macro); E.Cit = ΣN_s,t / |T|. **Code≠paper**: code is micro, skips zero-citation tasks,
drops `unknown`/error pairs from the denominator. Use CODE to reproduce leaderboard artifacts.

## II.2 Pipeline stages (each rule)
1. **Extract** (extract.py:39-65): judge finds ALL in-text citations in 4 forms (trailing numeric,
   bracket numbers, line-annotated brackets, markdown links); outputs (fact, ref_idx, url) with enough
   surrounding context to be self-contained. One fact citing N refs → N pairs (:47-50). **Bibliography-only,
   no in-text marker → EMPTY (0)** (:51). Markdown links in fact text reduced to [title] (:84-88). Path-based
   openai special-case strips #:~:text= fragments (:68-81). Parse retries reuse the same response (:124-149).
2. **Dedup** (deduplicate.py): group by exact URL; multi-fact URLs judged — two statements are duplicates
   ONLY if they express exactly the same thing (:21-29,73-110). Dedup failure → keep ALL facts (never delete).
3. **Retrieve** (api.py:202-233; scrape.py): fetch each unique URL via Jina Reader r.jina.ai, 60s timeout,
   ≤3 retries; success = title+description+content; failure = literal "scrape failed: …".
4. **Support judge** (validate.py:39-64): per URL, all its facts judged together; label each:
   `supported` if the statement's facts/data are found **entirely OR PARTIALLY**, rounded numbers accepted;
   `unsupported` if none found; `unknown` if page invalid/not-found. ≤3 retries, result count must equal
   fact count (:116-140). ⇒ SUPPORT IS LENIENT (partial + rounding qualifies).
5. **Stat** (stat.py:20-40): supported→+1/+1; unsupported→+1 total, +0 valid; unknown & validate-error →
   EXCLUDED from both. Zero-citation tasks skipped from denominators.

## II.3 FACT edge cases / levers
- Broken/unreadable URL → unknown → excluded (doesn't lower accuracy, just wastes a slot; scrape.py:22-35).
- Partial support of a compound statement still = supported → atomic claims reduce ambiguity (validate.py:39-42).
- Same claim+URL counts once; same claim + multiple URLs = multiple pairs each countable; multiple distinct
  facts from one URL each count (extract/dedup).
- NO credibility/prestige/recency/recall/uncited-hallucination scoring — only source-text support (validate.py:39-64).
- Uncited factual abundance is INVISIBLE to FACT (extract.py:47-51). Bibliography-only sourcing = 0 pairs.

================================================================================
PART III — COMPLETE SCOREABLE-SURFACE CHECKLIST (every distinct point; 52 items)
================================================================================
RACE (task-specific coefficients; representative proofs):
1 Cover every named topic/sub-question (Comp+Inst). 2 Cover requested breadth of entities/sectors/populations
(Comp/Inst). 3 Respect geography (Inst). 4 Respect time period/cutoff (Inst,Comp). 5 Use required deliverable
form (Inst+Read). 6 Give every requested output field per item (Inst/Comp). 7 Provide requested number of
options/recs (Inst). 8 Stay on central topic; no digressions (Inst). 9 Define key concepts/context (Comp).
10 Breadth+depth not a surface list (Comp). 11 Sufficient concrete data/cases/evidence (Comp+Read). 12 Represent
current literature broadly & fairly (Comp). 13 Multiple perspectives; balance benefits vs risks (Comp+Ins).
14 Compare entities systematically not independently (Comp+Ins). 15 Analyze CAUSAL MECHANISMS (Ins). 16 Explain
relative importance/interaction of drivers (Ins). 17 SYNTHESIZE across sources, don't serially summarize
(Ins+Read). 18 Identify consensus/disagreement/uncertainty/limits/gaps (Ins). 19 Develop emergent themes/
conceptual linkages/novel perspectives (Ins). 20 Logically consistent evidence→conclusion (Ins). 21 Use
scenarios/forecasting when asked (Ins+Inst). 22 Prioritize alternatives & justify rankings (Ins). 23 Actionable
recs tied to analysis (Ins+Inst). 24 Discuss stakeholder implications (Ins). 25 Use only allowed source classes
(Inst). 26 Use only allowed source languages (Inst). 27 Match intended audience (Read). 28 Clear grammatical
fluent language (Read). 29 Accurate terminology + explain terms (Read). 30 Appropriate tone/genre (Read/Inst).
31 Clear macro-structure: intro/sections/synthesis/conclusion (Read). 32 Informative headings, navigable
hierarchy (Read). 33 Focused paragraphs + explicit transitions (Read). 34 Control density/redundancy (Read).
35 Present quantitative evidence clearly + interpret it (Read). 36 Tables/charts/visual aids where they help
comparison, clearly labelled (Read). 37 Highlight key findings/summaries w/ formatting/bullets (Read). 38
Professional consistent formatting/layout (Read). 39 Preserve useful non-citation structure through cleaning
(all RACE, indirect).
FACT: 40 Attach citations at exact claim locations (inline, not bibliography-only). 41 Use extractable citation
forms + real URLs. 42 Make each cited claim complete/understandable. 43 Use reachable fetchable URLs. 44 Ensure
source text supports ≥ part of the exact statement. 45 Avoid attaching sources with none of the facts. 46
Increase unique SUPPORTED statement–URL pairs. 47 Avoid exact duplicate same-URL claims. 48 Multiple independent
URLs per fact each count. 49 Multiple distinct facts per URL each count. 50 Don't rely on uncited abundance. 51
Prestige doesn't help FACT. 52 Citations don't help RACE (cleaned) — don't optimize RACE via citations.

================================================================================
PART IV — MEASUREMENT CAVEATS (all)
================================================================================
1 Current gpt-5.5/gpt-5.4-mini vs legacy Gemini — two non-comparable scales (empirical deltas −0.89..+3.00).
2 RACE reference-relative, compressed ~0.5; use rankings not absolutes (drbench.tex:345). 3 One judge call/
task, no temp/seed → variance not averaged (±0.027 observed). 4 max_completion_tokens=64000; reasoning effort
low/medium/low for clean/score/fact (api.py). 5 Criteria weights averaged over 5 samples but criteria LISTS
from 1 accepted call; then frozen. 6 Reference contamination (Gemini DR report). 7 Weights hidden from judge.
8 Cleaner nondeterminism can drop source-class/language visibility. 9 Long-report chunk boundary effects
(≥100-char min). 10 Permissive parser; missing sub-criteria renormalize; no clamp. 11 Failed RACE tasks
excluded from averages → different failure sets non-comparable. 12 FACT support permissive (partial+rounding).
13 FACT unknowns ignored by code precision. 14 FACT code≠paper (micro vs macro). 15 FACT extraction/validation
LLM-mediated (paper cites 96%/92% Gemini-Flash human agreement; gpt-5.4-mini error rate unknown). 16 FACT
measures support only — not truth/credibility/recall/uncited-hallucination. 17 gpt-5.5 leaderboard FACT column
currently "-" (re-eval pending) — don't infer new-judge FACT standings.

================================================================================
PART V — STRATEGIC IMPLICATIONS (for Phases 2–4)
================================================================================
1 Insight (0.352 mean; task-72 cells #7,#8 = .0800 each) is the dominant lever — causal mechanisms + cross-
source synthesis + logical integration + uncertainty + emergent themes + novel implications = WRITER REASONING,
pre-generation. 2 Comprehensiveness = pre-enumerable per-task checklist (read criteria.jsonl before writing).
3 Instruction = cheap full credit but source-class/language must be visible in PROSE (bibliography stripped).
4 Readability = smallest/narrowest; structure/roadmap + paragraph cohesion + synthesis-clarity (prose) >
tables (.014). 5 FACT orthogonal to RACE — separate fix track (inline atomic supported unique pairs). 6 RACE
is RELATIVE to the local Gemini reference (reference.jsonl) — Phase 2 must dissect THAT report + top scorers to
see HOW they beat it, esp. on the Insight cells. 7 Every fix needs a same-judge baseline + replication (±0.027).
