# SCORING_SPEC — RACE + FACT — LOSSLESS consolidation of Sol + Fable (Phase 1)
Opus read BOTH full verdicts line-by-line. This preserves EVERY distinct point from each; literal duplicates
merged; every anchor/number/verbatim quote kept. [S]=Sol only, [F]=Fable only, [S+F]=both, [O]=Opus-verified vs source.
Checkout 469cce54 (2026-05-11); paper arXiv 2506.11763 (drbench.tex). Root third_party/deep_research_bench/.
Source verdicts (also committed): phase1_sol_verdict.md (462 ln), phase1_fable_verdict.md (473 ln).

===================== PART I — RACE =====================

## I.0 Source/version distinction [S+F]
- [S] Executable code is authority for what a local run computes. main branch: RACE judge default
  `openai/gpt-5.5`, FACT `openai/gpt-5.4-mini` (OpenRouter or OpenAI backend) (utils/api.py:40-75).
- [S] Paper describes LEGACY regime: Gemini-2.5-Pro RACE, Gemini-2.5-Flash FACT, Gemini-2.5-Pro DR references
  (§3.3; drbench.tex:243-248). Legacy branch pins gemini-2.5-pro-preview-06-05 / flash-preview-05-20.
- [S] TWO official leaderboards: HF main tab "GPT-5.5(race)+GPT-5.4-mini(fact)" + separate "Gemini-2.5" tab;
  comparable WITHIN not ACROSS regimes (README:24-29; create_leaderboard.py:81-98).
- [S] Paper≠code for FACT (see II). [S] The model that generated the frozen criteria.jsonl is NOT recorded in
  the file → unknown from the artifact; scorer loads it, never regenerates (deepresearch_bench_race.py:28-30,245-248).
- [F] Migration date **11 May 2026** (README:16-29); 3 candidate judges benchmarked on human-annotated subset;
  **human inter-annotator agreement baseline 68.78%**; GPT-5.5 won Overall/PAR/FAS. Dual-acceptance until
  **31 May 2026**, GPT-5.5-only after **1 June 2026**; legacy on `Gemini-2.5` branch.
- [S] Empirical GPT5.5−Gemini Overall deltas (5 shared models): cellcog-max −0.89, Gemini DR +0.27, OpenAI DR
  +1.39, Perplexity +2.59, Grok +3.00. Not one-constant transformable.

## I.1 Call mechanics [S+F]
- Production scorer imports `generate_merged_score_prompt` (comparative, reference-based) — NOT static/
  point_wise/vanilla (deepresearch_bench_race.py:14-17,95-104; [F] :16 import, :99-104 format).
- ONE judge call/task; retries only on error/invalid JSON, MAX_RETRIES=10 exp-backoff (:31,106-149).
- [F] Sampling params intentionally UNSET ("gpt-5.x reasoning models reject non-default values", api.py:24-25);
  reasoning_effort clean=low/score=medium/fact=low (:84-88); max_completion_tokens=64000 (:81); no seed; no
  multi-sample averaging at scoring (5-sample averaging only at criteria-generation).
- 50 en + 50 zh tasks; en/zh score+criteria prompts are translations of one algorithm (score_prompt_zh.py;
  query.jsonl:1-100; lang select deepresearch_bench_race.py:232-240).

## I.2 Judge inputs [S+F, O]
1 task_prompt · 2 article_1 = CLEANED TARGET (ours) · 3 article_2 = CLEANED REFERENCE (Gemini DR) · 4 criteria
NAMES+EXPLANATIONS only. Weights STRIPPED before prompting ("without weight information",
deepresearch_bench_race.py:33-56) → judge can't steer by weight. [F] Target ALWAYS article_1, NO position swap →
any bias = constant offset. Judge told to compare both per each criterion; one call covers all ~20–27 criteria.

## I.3 Score scale — VERBATIM (score_prompt_en.py:35-41) [O]
0–2 "Very poor, almost completely fails" · 2–4 "Poor, minimally meets, significant deficiencies" · 4–6 "Average,
basically meets, neither good nor bad" · 6–8 "Good, largely meets, notable strengths" · 8–10 "Excellent, fully
meets or exceeds." Continuous 0–10 per criterion per article. [S+F] ONLY partial-credit rule — no sub-checklists/
point schedules. [S] No range clamp (score_calculator.py:69-89).

## I.4 Four dimensions — definitions
- [O] criteria/score prompt (criteria_prompt_en.py:101-106): COMP "The breadth, depth, and relevance of
  information coverage"; INSIGHT "The depth, originality, logic, and value of the analysis and conclusions";
  INST "Whether the report accurately and completely responds to all requirements and constraints of the task";
  READ "Clarity of structure, fluency of language, effectiveness of data presentation, and overall ease of
  understanding."
- [F] Paper App.B Table 4 alt wording: COMP "covers key areas... does not omit important parts"; DEPTH "deeply
  analyzes causes, impacts, and trends, providing valuable insights"; INST "closely follows the research topic
  and directly answers questions"; READ "clear structure, fluent language, and is easy to understand."
- [F] At scoring the judge only sees the "four dimensions" line (score_prompt_en.py:7); operative meaning =
  per-task criteria texts.

## I.5 Dynamic dimension weighting
- [S+F] Rule (criteria_prompt_en.py:27-33): Total = Σ dim·weight, sum EXACTLY 1.0; "flexibly adjusted according
  to task characteristics, not fixed" (:31); justify each vs task (:32). NO keyword/formula rule. [F] "learn the
  thinking logic... rather than simply imitating... weight values" (:38).
- [S+F] Examples (:41-85): EV-feasibility → Ins.35/Comp.30/Inst.20/Read.15 (readability "secondary to depth and
  breadth"); renewable-stock-decade → Comp.40/Read.25/Inst.20/Ins.15 (readability high: "presenting a large
  volume of ... data clearly ... is a major challenge and key success factor").
- [F] Derived rule: read↑ data-heavy overview/compilation; insight↑ feasibility/analysis/strategy; comp↑ breadth
  ("different X","over a decade").
- [S+F] Mechanics (generate_criteria.py): 5 samples/task (:35); keep those summing 1.0±1e-6 (:70-86); average
  dims present in every kept sample (:160-170); renormalize to 1 (:172-175); round 2dp; **residual added to
  READABILITY** (:88-104 line102). [S+F] criteria.jsonl FROZEN, loaded directly, never regenerated (:29,246).
- [S+F] 100-task distribution: Insight mean **0.352** (median .36, min .11 t91, max .42 t34; modes .35×12/.38×11/
  .39×11/.40×10); Comp 0.292 (med .30, min .20 t4/t30, max .37 t91; .30×25/.29×18); Instruction 0.215 (med .20,
  min .13 t43, max .35 t48; .19×16/.20×12); Readability 0.141 (med .14, min .10 t32/t54, max .25 t73; .15×24/
  .13×19/.14×14). [S] Lang means CN/EN Comp .287/.297 · Ins .354/.350 · Inst .220/.209 · Read .139/.144.
- [S] Illustrative tasks: t4 (gold+mind-map) .20/.38/.26/.16, mind-map format=0.30 within INST; t30 (4 mandatory
  lenses) .20/.38/.31/.11; t73 (novice EFL teachers) .23/.30/.22/**.25**; t91 (Saint Seiya inventory) **.37**/
  **.11**/.32/.20; t100 (AI & relationships) .29/**.40**/.16/.15. [F] t51 .15/.33/.30/.22; t52 .13/.39/.32/.16;
  t53 .15/.39/.31/.15; t72 .14/.32/.29/.25.

## I.6 Sub-criteria generation (2,517 items / 100 tasks)
- [S+F] Separate LLM call per dimension AFTER weights fixed; accepted only if sub-weights sum 1.0±1e-6; model
  picks count; task-specific + explanation each; no cross-dimension overlap (criteria_prompt_en.py:96-506,182-224).
- Per-dimension generation instruction: COMP identify all key areas/perspectives/depths, max coverage/min overlap
  (:112-125); INSIGHT areas needing deep analysis/deduction/synthesis/value-judgment, reward depth/logic/
  originality/conclusion-value, EXCLUDE listing (:213-226); INST decompose explicit questions/outputs/scope
  (geo/time/subject)/objectives, score directness/completeness/on-topic/strict-adherence (:314-327); READ cover
  language clarity/structure/density/data-viz/formatting/audience, weights may adapt (:409-432).
- [F] Readability EXCEPTION: prompt asks "relatively general" criteria (:410) from a FIXED element list (:412-418)
  → near-identical across tasks. Token freq (50 EN tasks): clarity 129, formatting 50, logical 50, layout 47,
  structure 46, precision 46, paragraph 45.
- [S+F] Counts/sub-weights: COMP 5–9 (mean 6.40, n=640, sub .05–.30 mean .156[F]/median .15[S]); INSIGHT 4–7
  (5.57, 557, .05–.35, .180/.20); INST 4–8 (5.71, 571, .05–.45, .175/.15); READ 6–10 (7.49, 749, .03–.30,
  .134/.10). [S] ~23–27 judged items/task.
- [F] INST criteria are LITERAL decompositions of task instructions/scope ("Instruction-Centric... directly
  correspond to explicit requirements, questions, limitations", :323).
- [F] VERBATIM INSIGHT gating (earns 8–10): ":256 deeply analyzes interplay and causal mechanisms, rather than a
  superficial listing"; ":261 goes beyond obvious impacts to uncover subtle or second-order effects"; ":265-267
  conclusions/recommendations derived explicitly from preceding analysis"; ":270-272 nuanced risk/trade-off where
  decisions involved"; ":275-277 novel perspectives, challenges conventional wisdom, beyond generic advice"
  ('originality' 38× in EN insight names); ":280-282 forward-looking implications + future research/strategy."
- [F] VERBATIM READABILITY templates: structure/roadmap :456-459; language/tone :461-464; paragraph cohesion/
  transitions :466-469; in-text data clarity :471-474; well-labeled tables/charts :476-479; highlight findings
  (bold/bullets/summaries) :481-484; formatting/layout :486-489; audience adaptation :491-494.

## I.7 FULL TASK-72 RUBRIC — 25 scoring points (criteria.jsonl id=72) [S+F]
weights: Ins .32/Comp .29/Inst .25/Read .14. eff=dim×sub.
COMP(.29): 1 4IR grounding .10=.0290 · 2 Breadth of restructuring dims (creation/displacement/transformation/
skills/wages/productivity) .25=**.0725** · 3 Industry-specific scope .25=**.0725** · 4 Disruptive character&scale
.15=.0435 · 5 Literature depth/representativeness .15=.0435 · 6 Balanced impacts (challenges+opportunities)
.10=.0290.
INSIGHT(.32): 7 Mechanisms of restructuring .25=**.0800** · 8 Critical cross-industry synthesis (patterns/
variation/consensus/debate/uncertainty, not a catalog) .25=**.0800** · 9 4IR integration .15=.0480 · 10 Emergent
themes/linkages/novel perspectives .20=.0640 · 11 Implications & future agendas .15=.0480.
INST(.25): 12 Lit-review form .10=.0250 · 13 On-topic focus .20=.0500 · 14 4IR-driver theme .15=.0375 · 15
Significant-disruption .15=.0375 · 16 Various-industries .15=.0375 · 17 ONLY high-quality journals .15=.0375 · 18
ONLY English-language .10=.0250.
READ(.14): 19 L1 language clarity/precision/tone .20=.0280 · 20 S1 structure+logical org (scope intro, thematic
headings, sequence, synthesizing conclusion) .20=.0280 · 21 S2 paragraph cohesion/transitions .15=.0210 · 22 P1
clarity+synthesis of sourced info (PENALIZES serial summaries/density/redundancy) .15=.0210 · 23 D1 data/evidence
clarity (incl summary tables/figures if used) .10=.0140 · 24 F1 formatting/layout/visual consistency .10=.0140 ·
25 A1 audience adaptation + term explanation .10=.0140.
[S+F] cells #7,#8 (.0800) are the LARGEST on the whole task-72 scorecard; then #2,#3 (.0725); then #10 (.0640).
[S+F] #17,#18 judged on CLEANED text (bibliography stripped) → journal/English compliance must be in-PROSE
(named-author/journal attribution); verification limited/run-dependent.

## I.8 Full/partial/zero per criterion family [F]
COMP: full=all aspects in the `explanation` covered; partial=some (bands 2–8); near-zero=omits area. INSIGHT:
gated beyond listing (mechanisms/second-order/novelty=8–10; listing=mid). INST: binary-ish wording but continuous
band; partial deviation=partial credit. READ: full=named structural artifacts (headings, focused paragraphs,
transitions, labeled tables, bolded highlights, term explanation, :456-494). ALL comparative — an "8" only helps
if the reference scores lower on the same criterion.

## I.9 AGGREGATION — every formula [S+F]
1 judge s_tgt,c, s_ref,c ∈[0,10]. 2 Dimension raw D_R,d = Σ(s·w_dk)/Σ(w_dk over MATCHED) (score_calculator.py:
53-64,119-124,136-139) — missing/unmatched drop from num+denom → remaining RENORMALIZE (not zeroed) (:119-144).
3 Criterion match: exact→case-insensitive→substring→**dimension AVERAGE weight fallback** (:91-118). 4 Intermediate
I_R=Σ_d(W_d·D_R,d) (:146-158). 5 **Overall(tgt)=I_tgt/(I_tgt+I_ref)** (deepresearch_bench_race.py:151-160);
parity⇒0.5. 6 Published per-dim = D_t,d/(D_t,d+D_ref,d) (:162-175) ALSO relative. 7 Dataset = unweighted mean of
successful tasks' published values ×100, failed excluded (:478-514; rank_leaderboard.py:16-37).
- [S] Overall ≠ Σ W_d·PublishedDim_d (ratio applied AFTER weighting raw). [S] leverage depends on target AND
  reference score. [S] edge: if the LAST reference item lacks a score the whole ref dimension can read 0 (:136-140).
- [F] Quantified: parity 5v5(0.5)→6v5(0.545) gains ≈0.045 normalized on that dim; **1 per-criterion point at
  parity ≈ +0.045 normalized per dimension point** × dim weight → task overall.

## I.10 Cleaning — what the judge sees [S+F]
Cleaner LLM (clean_prompt.py:21-38): remove all citation links/marks([1],[2],1,2…)/reference-lists/footnotes;
KEEP all other original content; keep text inside a marker, drop the marker; a chunk that is ONLY bibliography/
footnotes → EMPTY; invent nothing (:28-37). SURVIVES→headings/tables/bold/bullets/markdown/inline-data.
STRIPPED→[n]/footnotes/reference-list/citation-URLs ⇒ citation volume=0 RACE points; markdown reaches judge.
Not guaranteed (LLM rewrite, not parser; min valid=100 chars, clean_article.py:31-33). Chunked ~50k est tokens
(en=chars/3.5), parallel-cleaned, concatenated no delimiter, recursive split on truncation, cached by ID
(clean_article.py:95-223,327-370). [S] Failed/truncated chunk → recursive halving depth 3. [F] Failed clean
EXCLUDES the task (deepresearch_bench_race.py:227-229); over-aggressive clean depresses COMP. [F] REFERENCE is
pre-cleaned from reference.jsonl (both sides bibliography-free). [F] **task-72 reference = 69,284 chars**; ref =
Gemini-2.5-Pro DR "as available in April 2025" (paper §4.1).

## I.11 RACE edge cases / gaming [S+F]
missing sub-criteria renormalize not zero; fuzzy-match→avg-weight fallback (silent reweight, warn-only); no
clamp; permissive JSON regex reconstruction (json_extractor.py:95-149) can silently drop trailing criteria; only
top-level 4 dim keys required (per-sub presence not enforced); reference contamination (target close to Gemini
ref benefits); weights hidden from judge; malformed citation markers risk collateral text loss in cleaning.

===================== PART II — FACT (independent of RACE) =====================
## II.0 [S+F] Separate pipeline on RAW report, after RACE→results/fact/; NOT in RACE Overall (run_benchmark.sh:
35-95). Judge gpt-5.4-mini. [F] Only coupling: paper §4.2.2 high E.Cit correlates with Comprehensiveness.
## II.1 Metrics [S+F] Acc_t=N_s,t/N_u,t (0 if none). **C.Acc=(1/|T|)ΣAcc_t** macro (paper Eq.5). **E.Cit=ΣN_s,t/
|T|** (Eq.6). CODE (stat.py:20-40): total_citations=non-unknown/total_num; total_valid=supported/total_num
(=E.Cit); valid_rate=supported/non-unknown (MICRO). No recall metric anywhere.
## II.2 Pipeline [S+F]: (1) EXTRACT (extract.py:39-65): LLM finds ALL (fact,ref_idx,url); 4 forms (trailing
number; [n]; [n†L..]; [Title](url)); complete-with-context fact (:48); 1 fact citing k refs→k triplets (:49);
**bibliography-only/no in-text location → EMPTY list (:51)**; [title](url) in fact→[title] (:84-88); #:~:text=
stripped only for 'openai' paths (:68-81); parse retries reuse same response (:124-149). (2) DEDUP (deduplicate.py):
group by exact URL (:47-53); LLM keeps unique — dupes only if "express exactly the same thing" (:21); failure→keep
ALL (:105-106). (3) SCRAPE (scrape.py+api.py:203-241): Jina Reader r.jina.ai, 60s, ≤3 retries, success=title+
description+content, fail="scrape failed:…"; [F] JINA_API_KEY required. (4) SUPPORT (validate.py:39-64): 1 call/
URL: **supported** if facts/data "entirely OR PARTIALLY" present, **rounding accepted** (:41); **unsupported** if
ALL absent; **unknown** if page invalid; ≤3 retries, count must equal fact count (:116-140). (5) STAT: supported
+1/+1; unsupported +1total/+0valid; unknown & validate-error EXCLUDED; zero-citation tasks skipped.
## II.3 FACT levers/edges [S+F]: markers mandatory; maximize unique SUPPORTED pairs (E.Cit linear); unsupported
lowers accuracy; broken/paywalled URL→unknown→vanishes from both counts ([F] judged vs TODAY's page); atomic
claims reduce ambiguity; same claim+URL once; same claim×k URLs=k pairs; k facts/URL each count; NO credibility/
prestige/recency/recall/uncited-hallucination scoring; uncited abundance invisible.
## II.4 CODE≠PAPER [S+F]: micro vs macro; zero-cit tasks skipped (stat.py:21-22) vs paper Acc_t=0; unknown+error
excluded from denominators (:23-30) vs paper binary; E.Cit÷total_num vs paper÷|T|. Use CODE for leaderboard repro.

===================== PART III — SCOREABLE-SURFACE INVENTORY (LOSSLESS UNION) =====================
### Sol's 52 (verbatim, phase1_sol_verdict.md §C):
1 Cover every named topic/sub-question (Comp+Inst). 2 Requested breadth of entities/sectors/populations. 3
Respect geography (Inst). 4 Time period/cutoff (Inst,Comp). 5 Required deliverable form (Inst+Read). 6 Every
requested output field per item. 7 Requested number of options/recs. 8 Stay on topic, no digressions. 9 Define
key concepts/context (Comp). 10 Breadth+depth not surface list. 11 Sufficient concrete data/cases/evidence
(Comp+Read). 12 Represent literature broadly & fairly. 13 Multiple perspectives; balance benefits vs risks. 14
Compare systematically not independently. 15 Analyze causal MECHANISMS (Ins). 16 Relative importance/interaction
of drivers. 17 SYNTHESIZE across sources, not serial summary (Ins+Read). 18 Consensus/disagreement/uncertainty/
limits/gaps. 19 Emergent themes/linkages/novel perspectives. 20 Logically consistent evidence→conclusion. 21
Scenarios/forecasting when asked. 22 Prioritize alternatives & justify. 23 Actionable recs tied to analysis. 24
Stakeholder implications. 25 Only allowed source classes. 26 Only allowed source languages. 27 Match audience. 28
Clear grammatical fluent language. 29 Accurate terminology + explain terms. 30 Appropriate tone/genre. 31 Clear
macro-structure intro/sections/synthesis/conclusion. 32 Informative headings, navigable hierarchy. 33 Focused
paragraphs+explicit transitions. 34 Control density/redundancy. 35 Present quantitative evidence clearly +
interpret. 36 Tables/charts/visual aids where they help, labeled. 37 Highlight key findings/summaries w/
formatting/bullets. 38 Professional consistent formatting/layout. 39 Preserve non-citation structure through
cleaning. 40 Attach citations at exact claim locations (FACT). 41 Extractable citation forms + real URLs. 42
Each cited claim complete/understandable. 43 Reachable fetchable URLs. 44 Source supports ≥ part of the exact
statement. 45 Avoid sources with none of the facts. 46 Increase unique SUPPORTED pairs. 47 Avoid exact duplicate
same-URL claims. 48 Multiple URLs per fact each count. 49 Multiple facts per URL each count. 50 Don't rely on
uncited abundance. 51 Prestige doesn't help FACT. 52 Citations don't help RACE (cleaned).
### Fable's inventory additions (unique framing/anchors, phase1_fable_verdict.md §C):
COMP: depth of detail per area (surface→4-6 band, score_prompt_en.py:113-116); in-PROSE data density (post-
cleaning). INSIGHT verbatim anchors: mechanism-not-listing (:256), second-order (:261), logical coherence
(:265-267), originality/challenge-wisdom (:275-277, 38×), forward implications (:280-282), nuanced risk/trade-off
(:270-272). INST: source-constraint compliance VISIBLE IN PROSE (task-72 .0625 combined). READ: static analog
explicitly rewards "formatting, headings, lists, emphasis" (score_prompt_en.py:190-192). CROSS-CUT: #23 beat the
reference (+0.045/dim-pt at parity, :158-160); #24 survive cleaning (chunk that looks like a reference section
dropped entirely); #25 criterion-name echo → avg-weight fallback makes per-criterion wins noisy. FACT: #26
in-text mandatory (:51); #27 E.Cit volume linear, dupes to same URL collapsed but paraphrases survive; #28 C.Acc
precision, lenient support; #29 unscrapeable URL→unknown vanishes; #30 one fact→k sources = k pairs.

===================== PART IV — CAVEATS (union, each preserved) =====================
[S1]=current vs legacy judge (api.py:43-55,72-75). [S2]=two scales not one-constant transformable (deltas above).
[S3]=reference-relative compressed ~0.5, use rankings (drbench.tex:345). [S4/F3]=no temp/top_p/seed; max_tokens
64000; effort low/med/low; provider default sampling, effective temp UNKNOWN. [S5]=legacy Gemini 16k thinking
budget, no temp/seed. [S6/F3]=one judge call/task, variance not averaged, magnitude unknown w/o repeats. [S7]=
criteria weights averaged over 5 samples but 1 criterion list/dim, then frozen. [S8/F11]=reference is Gemini-2.5-
Pro DR (contamination benefit for close targets). [S9/F]=weights hidden from judge. [S10/F8]=cleaner nondet +
info removal (source class/lang hard to verify post-clean). [S11/F8]=long-report chunk boundary effects, min
100 chars. [S12/F7]=permissive parser, missing sub-criteria renormalize. [S13]=no 0–10 clamp. [S14]=failed RACE
tasks excluded from averages → non-comparable failure sets. [S15/F]=FACT support permissive (partial+rounding).
[S16/F]=FACT unknowns ignored by code precision. [S17/F9]=FACT code≠paper (micro vs macro; zero-cit skipped;
unknown excluded). [S18/F]=FACT extraction/validation LLM-mediated; paper Gemini-Flash agreement 96%/92% on
100-pair sample; gpt-5.4-mini error rate UNKNOWN. [S19]=FACT measures support only (not truth/credibility/recall/
uncited-hallucination). [S20/F16]=gpt-5.5 leaderboard FACT column "-" (re-eval pending) — don't infer new-judge
FACT standings. [F1]=migration/human-agreement 68.78%. [F5]=fixed position no swap (constant bias). [F6]=fuzzy-
match fallback logged warn-only. [F10]=Jina scrape fragility; time-drift (judged vs TODAY's page). [F12]=human-
consistency validated on 50 ZH tasks (filtered to 37, ICC<0 removed); **EN half NEVER human-validated in paper.**

===================== PART V — STRATEGIC IMPLICATIONS (Phases 2–4) =====================
1 INSIGHT is the game (mean 0.352; task-72 #7,#8=.0800 the two largest cells), gated on causal mechanisms/
second-order/novel synthesis/logical coherence/forward implications (verbatim I.6) = WRITER REASONING, pre-gen.
2 COMPREHENSIVENESS = pre-enumerable per-task checklist (criteria.jsonl explanations). 3 INSTRUCTION = cheap full
credit (literal restatements) but source-class/language must be in PROSE. 4 READABILITY smallest/narrowest, near-
identical criteria; structure/roadmap + paragraph cohesion + synthesis-clarity > tables (.014). 5 FACT orthogonal;
indirectly tracks Comprehensiveness; separate fix track. 6 RACE is RELATIVE to the LOCAL 69,284-char Gemini
reference — Phase 2 MUST dissect THAT report + top scorers to see HOW they beat it on the Insight cells; a win
only counts where the reference is beatable (+0.045/dim-pt at parity). 7 Every fix needs a same-judge baseline +
replication (±0.027 noise, single-call judge).
