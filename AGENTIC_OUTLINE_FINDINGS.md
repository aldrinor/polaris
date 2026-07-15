# AGENTIC OUTLINE — CONSOLIDATED FINDINGS (foundation for the codex deep-think)
Grounded in real data / logs / code (file:line). Goal: beat ChatGPT + Gemini + FS-Researcher on
DeepResearch-Bench RACE (task 72 = "literature review on AI restructuring of the labor market;
ONLY high-quality English-language JOURNAL articles"). Worktree: /home/polaris/wt/outline_agent.

## 0. MODELS (verified live + §9.1.8 lock)
- COGNITION (ReAct decide/gap-analysis/plan) = z-ai/glm-5.2  — outline_agent.py:104,156
- code-EXEC (execute_python calculator) = deepseek/deepseek-v4-pro — outline_agent.py:105,162
- generator (writing) = z-ai/glm-5.2
- Deep-think GATE mind (NEW, replaces Fable) = openai/gpt-5.6-sol via OpenRouter (validated; helper
  /home/polaris/polaris_project/sol_think.py). Once codex CLI+OAuth up, route through user's plan.

## 1. THE FUNNEL (measured; the core problem)
Corpus (cp4_corpus_s3gear_329.corrected.json): 995 rows / ~840 distinct works / 329 baskets.
Tier mix: T1 5.5% T2 8.4% T3 18.7% T4 20.8% | T5 2.5% T6(blog) 21% T7 8.6% UNKNOWN 14.5% (~44% low-tier).
  -> agentic outline SELECTS only ~39 ev_ids (8 sections x 4-10)      [95% dropped HERE]
  -> strict_verify keeps 97 sentences (34 dropped)
  -> 25 sources cited in the report (~3% of works).
Depth-vs-RACE is an INVERTED-U: 22src=0.406, 25=0.4245, 37(champion)=0.4447 PEAK, 40=0.4225,
54=0.398, 64=0.396. Champion's 37 SYNTHESIZED sources beat both lean(25) and bloat(54-64).
RACE judge noise ~0.016 (step3 re-scored 0.4447->0.4291). Champion reproducible ~0.43. SOTA top-3 ~0.45-0.50.

## 2. WHY THE OUTLINE SELECTS SO FEW (ranked mechanisms, file:line)
1. SOFT/primary — the planner SEES the full corpus but the prompt says "NEVER pad a section...to reach a
   count" with NO floor (>=8 only in a code comment; FACET floors at 2). glm-5.2 picks ~4-10/section.
   multi_section_generator.py:1516/1557/1596/1628 (prompts), :3001 (_call_outline). Fix = prompt floor +
   reward genuine density; not a constant edit.
2. HARD switch — PG_ROUTE_ALL_BASKETS. Default ON in the compose script (compose_agentic_report_s3gear329.py:190)
   but the wheel's "lean win" DISABLED it. OFF => ~600 orphan baskets stranded. ON => sections balloon to
   52-103 rows (the BLOAT that lowers RACE). verified_compose.py:3725 (enabled?), :3789 (router), gen :10615.
   NOTE: route_all only works if the credibility pass builds baskets (gov_suffixes threaded, script :231-246);
   else it's INERT and the report renders only the writer's directly-cited sources (the 25-source lean outcome).
3. HARD bound — section writers compose ONLY from their section's ev_ids; NO path into the ~800-work
   validated pool. verified_compose.py:3289 (_section_baskets_for_compose). Outline thinness propagates.
NOT the neck: top-24 writer cap (downstream), PG_OUTLINE_MAX_EV=150 (dissolved by default), PG_MAX_EV_PER_SECTION=30
 (above observed), 24-turn loop (fetches NEW web rows, never rescues the unselected pool).

## 3. COGNITION READ (glm-5.2 reasoning, from the actual decision log)
+ FULL gap-fill loop WORKS: 5 search_more_evidence -> live-fetch (147 cands) -> topic-gate -> select/weight
  -> route. It genuinely finds holes and triggers new query/search/fetch/select/weight/corpus.
+ 4/5 queries on-topic; one explicitly sought "quantitative estimates of jobs" (quant instinct present).
- WEAKNESS 1: generic gap query "methodological restriction to high-quality English-language" fetched 104
  OFF-TOPIC medical papers (sports med/nephrology/child psych); topic_gate DEMOTED(kept,disclosed) but 106
  ev_ids still auto-routed into "Introduction". (Irony: that query was TRYING to satisfy the prompt's
  "high-quality English journal" instruction — right intent, wrong execution.) topic_relevance_gate.py.
- WEAKNESS 2 (biggest; = direction #4 UNMET): it SEEKS numbers but runs NO deep math/stat synthesis
  ([#calc]/execute_python meta-analysis absent). Consolidates+routes but never quantitatively aggregates.

## 4. FAITHFULNESS (HARD gate — never relax)
strict_verify + NLI entailment per sentence; computed numbers render ONLY via verified [#calc:] lane,
NEVER as [CITE:ev_xxx]. §-1.3 weight-and-consolidate, never filter (junk is demoted+disclosed, not deleted).

## 5. INSTRUMENTATION ALREADY LANDED
- PG_DUMP_ROUTED_OUTLINE (default-OFF): dumps each section's evidence resolved to tier/title/url/quote
  BEFORE compose, for the qualitative read-gate. multi_section_generator.py ~:10621 (committed f003fef).
- PG_OUTLINE_THEME_FLOOR (default-OFF): corpus-derived theme-coverage floor; variance-safe (no-op on rich
  seed, recovers dropped themes on thin). Wheel commits 644e447/72c20eb/df4118a.

## 6. sol's DEEP INPUT (gpt-5.6-sol pressure-test of the fix plan) — design gold
A. Highest leverage = QUALITY-SELECTIVE coverage (RACE rewards authoritative non-redundant synthesis, not
   utilization). Off-topic routing is mandatory HYGIENE (block first). Broad MATH synthesis is a TRAP
   (heterogeneous labor studies rarely pool validly). Read-gate must PRUNE/REPLAN, not just score a finished outline.
B. Math synthesis faithful design: typed manifest per number {ev_id, verbatim numeric span, locator, population,
   design, outcome def, unit, direction, horizon, estimate, uncertainty, N, dependence/weight}; calc runs only on an
   explicit eligibility set + declared formula + versioned deterministic code; [#calc:hash] binds statistic to the
   manifest+output; any input/code/rule/rounding change invalidates. Silent failure = SEMANTIC INCOMPATIBILITY /
   dependence (pooling % with pp, unlike outcomes/horizons, reversed signs, duplicate samples) -> perfect arithmetic,
   plausible-but-FALSE number. => only aggregate WITHIN a compatible eligibility set; declare it.
C. Push >37 sources only if a source fills an uncovered high-priority claim, materially triangulates one, or adds a
   consequential contradiction — and REPLACE weaker evidence before appending. Metric "synthesis density" = analytical
   claims supported by >=2 independent sources per 1000 words; also marginal claim coverage/added source, redundancy
   rate, unsupported-claim rate. Require >37 to beat 37 on these under same word budget + survive source ablation.
D. MISSING SOTA lever (likely): judge-aligned CLAIM ARCHITECTURE + iterative revision — decompose RQ into
   reference-answer concepts -> assign evidence-backed claims -> draft -> critique for omissions/redundancy -> rewrite.
   We measure source count/tiers but NOT reference-concept recall, marginal citation utility, claim centrality,
   contradiction resolution, evidence-to-word efficiency. Build a claim-evidence graph + ablations to learn what
   actually moves RACE. Separate RETRIEVAL ceiling from SYNTHESIS ceiling (oracle-curated evidence set test).

## 7. OPEN DESIGN QUESTIONS FOR THE CODEX DEEP-THINK
- Quality-selective route: keep T1-T4 in the writer menu, T5-T7/UNKNOWN disclosed-but-not-composed — where/how (verified_compose.py:3289 + router)?
- Gap-query domain anchoring + auto-assign refusing demoted-off-topic rows — exact insertion (outline_agent.py search_more_evidence + topic_relevance_gate).
- Claim-architecture layer (sol's #D): is it worth building; where does it slot vs the existing outline?
- Math/stat synthesis: narrow, compatible-set-only, manifest-bound [#calc:] — build or defer (sol says trap if broad)?
- Real-time cognition monitor: stream glm-5.2 reasoning beat + sol-assess each turn; kill/replan on off-topic fetch.
- Flywheel: outline-only cheap gate (dump+kill before compose) for fast iterate; full compose+RACE only when outline read-gate passes.

## 8. HARNESS GUARDRAIL (anti-"too dumb")
Every loop decision MUST cite a real observed line (log/data/code), not a count or assumption. The near-miss last
night: the "lean win" (0.4245) looked like progress but was corpus-abandonment — caught only by READING the funnel.
Read fundamentals FIRST, every iteration.

## USER DECISION (07-12): Math/stat synthesis (#4) = CORE GENERAL capability, NOT deferred
Build it as a GENERAL quantitative-synthesis capability for ALL future questions (high chance of need).
Reconcile sol's "trap": aggregate ONLY within a declared compatible ELIGIBILITY SET (same outcome/unit/
direction/horizon/independent samples) via typed manifest -> render via verified [#calc:] lane only.
The eligibility gate = both the GENERALITY (fires wherever compatible numbers exist) AND the FAITHFULNESS
(never pools incompatible numbers). Costs nothing where it shouldn't fire; wins where it should. Rank = core.

## CODEX 5.6 SOL MAX DESIGN (07-12, codex_design_FINAL.md) — key corrections to v1
- My "keep T1-T4 in writer menu" is WRONG: task needs JOURNAL articles; T3=gov docs, T4=conference proceedings
  are NOT journals. Need a task-eligibility ALLOWLIST (relevant+English+journal+peer-reviewed+quality), tier=prior only.
- "95% dropped at outline" mixes units (rows vs works vs citations); need clean work_id funnel.
- Planner sees TITLES only (ev_id/tier/title), not statements, unless basket digest on => "title-starved".
- route_all is a recall-audit tool, NOT the candidate path. Replace with marginal-utility selector.
- Claim-architecture (claims before outline) = likely SOTA unlock. Verify via 2x2 selection-vs-synthesis test.
