# SCORING_SPEC — the definitive RACE + FACT scoring map (Phase 1 consolidation)
Opus consolidation of 2 independent grounded investigations (Sol + Fable); they AGREE on every major
mechanic below (high confidence). K3 verdict pending (Moonshot throttle) — will be folded if it adds anything.
Every claim is grounded in benchmark code file:line or the paper (arXiv 2506.11763 / drbench.tex). Local
benchmark checkout commit 469cce54 (2026-05-11). Full detail: investigators/phase1_{sol,fable}_verdict.md.

## 0. VERSION / JUDGE (critical framing)
- Current `main` judge: **RACE = openai/gpt-5.5**, **FACT = openai/gpt-5.4-mini** (utils/api.py:43-75; README:15-31).
  Paper/legacy = Gemini-2.5-Pro (RACE) / Gemini-2.5-Flash (FACT). TWO leaderboards, scores comparable only
  WITHIN a judge regime (empirical GPT5.5−Gemini deltas span −0.89..+3.00; README:24-29). Our tonight's judge
  = the gpt-5.5 regime. NEVER compare across judges (this is why tonight's 0.49 ≠ historical 0.5084).

## 1. RACE — HOW IT SCORES
### 1a. The formula chain (RACE is RELATIVE, not absolute)
- Per criterion k in dimension d, judge gives target & reference each a **0–10** score (5 bands, score_prompt_en.py:35-41).
- Dimension raw: `D_R,d = Σ_k(s·w_dk)/Σ_k w_dk` (score_calculator.py:53-64).
- Intermediate report: `I_R = Σ_d(W_d · D_R,d)` (score_calculator.py:146-158).
- **Overall = I_target / (I_target + I_reference)** (deepresearch_bench_race.py:151-160). Published per-dimension
  numbers are ALSO relative shares `D_t/(D_t+D_ref)` (:162-175). => 0.5 = tie with the reference.
- **CONSEQUENCE:** you don't score absolute quality — you score by **beating a frozen Gemini-2.5-Pro Deep-Research
  reference report, criterion by criterion** (drbench.tex:246-248). A criterion's leverage depends on target
  improvement AND the reference's score there. Compressed ~0.5; focus on rankings not absolutes (drbench.tex:345).

### 1b. Dynamic dimension weighting (no formula — semantic)
- Weights are LLM-generated per task, sum to 1.0, "adjust flexibly to task characteristics" (criteria_prompt_en.py:29-33).
  NOT keyword/formula-driven. Residual from 2-decimal rounding is dumped into **readability** (generate_criteria.py:88-104,177-180).
- **Actual distribution across all 100 tasks** (criteria.jsonl, computed by both investigators, identical):
  Insight mean **0.352** (max 0.42) · Comprehensiveness **0.292** · Instruction **0.215** · Readability **0.141** (min 0.10, max 0.25).
  => **Insight is the biggest lever, everywhere.** Readability is smallest + narrowest.

### 1c. Sub-criteria (the real scoreboard: ~23–27 judged items/task, 2517 total across 100 tasks)
- Each dimension → LLM-generated sub-criteria, sub-weights sum to 1.0 (generate_criteria.py). Judge sees criterion
  names+explanations but **NOT the weights** (deepresearch_bench_race.py:33-54). Counts/task: Comp ~6.4, Insight ~5.6,
  Instruction ~5.7, Readability ~7.5.
- **TASK-72 full rubric** (effective coeff = dim_weight × sub_weight; the real per-cell value):
  - INSIGHT (0.32): mechanisms of restructuring **0.0800** · critical cross-industry synthesis **0.0800** ·
    emergent themes/linkages 0.0640 · 4IR integration 0.0480 · implications/future agenda 0.0480. ← BIGGEST CELLS
  - COMPREHENSIVENESS (0.29): breadth of restructuring dimensions 0.0725 · industry-specific scope 0.0725 ·
    disruptive scale 0.0435 · literature representativeness 0.0435 · 4IR grounding 0.0290 · balanced impacts 0.0290.
  - INSTRUCTION (0.25): on-topic focus 0.0500 · 4IR-driver theme 0.0375 · significant-disruption 0.0375 ·
    various-industries 0.0375 · journal-only 0.0375 · lit-review form 0.0250 · English-only 0.0250.
  - READABILITY (0.14): language clarity/precision 0.0280 · structure+roadmap 0.0280 · paragraph cohesion 0.0210 ·
    synthesis-clarity (penalizes serial paper-summaries) 0.0210 · data clarity/tables 0.0140 · formatting 0.0140 · audience/term-defs 0.0140.
- Score bands: 0–2 fails · 2–4 minimal · 4–6 basic · 6–8 largely meets · 8–10 fully/exceeds (score_prompt_en.py:35-41).
  No criterion-specific point schedule; meaning comes from the criterion explanation + bands.

### 1d. What the judge SEES (cleaning contract)
- Before RACE, an LLM cleaner strips citations/markers/reference-lists/footnotes and "retains every other element"
  (clean_prompt.py:21-37). **Headings, paragraphs, bold, bullets, TABLES are SUPPOSED to survive** (not guaranteed —
  it's an LLM rewrite, not a parser; only validity test = ≥100 chars). => **citations/faithfulness buy 0 RACE points**;
  markdown structure does reach the judge. Source-type/language constraints (task-72 journal/English) are Instruction
  criteria BUT the bibliography is stripped, so compliance must be visible **in the prose**, verification is run-dependent.

### 1e. Scoring edge cases (gaming-relevant)
- Missing sub-criteria are NOT zeroed — remaining weights renormalize (score_calculator.py:119-144).
- Criterion-name matching: exact → case-insensitive → substring; NO match → assigns **average dimension weight**
  (score_calculator.py:91-118). No 0–10 range clamp (:69-89). Permissive JSON regex fallback (json_extractor.py).

## 2. FACT — HOW IT SCORES (fully independent of RACE)
- Separate pipeline on the RAW report; does NOT enter RACE Overall (run_benchmark.sh:35-95; score_calculator.py:146-158).
- Two metrics: **Citation Accuracy** (supported/judged) and **Effective Citations/task** (supported unique pairs). NO recall metric.
- Pipeline: extract inline (fact,url) pairs → dedup by URL (exact-semantic) → fetch via Jina Reader → judge support.
- HARD MECHANICS:
  - **In-text citation markers MANDATORY**: bibliography-only → empty extraction → 0 (extract.py:47-51).
  - **Support is LENIENT**: "entirely OR PARTIALLY" present + rounded-number agreement = `supported` (validate.py:39-42).
  - `unknown` (unfetchable page) excluded from BOTH numerator+denominator (stat.py:23-30) → broken URLs don't lower accuracy, just waste a slot.
  - No credibility/prestige/recency/recall scoring — only source-text support (validate.py:39-64).
  - Levers: more unique supported inline pairs on ATOMIC claims; multiple URLs per fact each count; avoid unsupported attach.
- **Code≠paper**: shipped stat.py = micro precision over non-unknown + skips zero-citation tasks; paper = macro over ALL tasks
  (stat.py:13-40 vs drbench.tex:555-590). Use CODE formula to reproduce leaderboard.

## 3. CAVEATS (measurement reliability)
- No temperature/seed control; **one judge call/task** (retry only on error) → run-to-run variance NOT averaged (api.py:22-25;
  deepresearch_bench_race.py:106-149). This is the source of our ±0.027 noise. Weights hidden from judge.
- Reference contamination: reports stylistically close to the Gemini reference benefit from pairwise comparison.
- FACT columns currently "-" under the gpt-5.5 leaderboard (re-eval pending) — don't infer new-judge FACT standings.

## 4. SCOREABLE-SURFACE INVENTORY (52 items — from Sol, corroborated)
Full enumerated list in investigators/phase1_sol_verdict.md §C (items 1–52), each tagged dimension+weight+file:line.
Grouped: RACE items 1–39 (coverage/breadth/scope/constraints → Comp+Instruction; mechanisms/synthesis/themes/
implications/logic → Insight; structure/paragraphs/data-clarity/tables/formatting/audience → Readability;
#39 = preserve non-citation structure through cleaning). FACT items 40–52 (inline extractable reachable supported
atomic unique pairs; NOT prestige, NOT recall, NOT uncited abundance, NOT citations-for-RACE).

## 5. STRATEGIC IMPLICATIONS (for Phases 2–4)
1. **Insight is the game** (0.352 mean; task-72's two 0.0800 cells = mechanisms + cross-industry synthesis are the
   largest single coefficients). Insight = causal mechanisms, cross-source synthesis (NOT serial summaries), logical
   integration, uncertainty/consensus, emergent themes, novel implications. This is WRITER REASONING — pre-gen.
2. **Comprehensiveness is a pre-enumerable checklist** — criteria.jsonl explanations name the exact aspects to cover;
   we can read the coverage targets BEFORE writing (per task).
3. **Instruction-following is cheap full credit** — literal task restatements; source/type/language constraints must be
   visible in PROSE (bibliography stripped). Easy points if we don't miss a constraint.
4. **Readability is smallest (0.141) + narrow band** — tables/formatting = only ~0.028 of task-72. Real readability
   sub-levers are structure/roadmap + paragraph cohesion + synthesis-clarity (prose), not tables. Low ceiling.
5. **FACT is orthogonal** — improving it never helps RACE; both matter for the leaderboard but need separate fixes.
6. **RACE is relative to a Gemini reference** — the target is to BEAT that reference per criterion; Phase 2 must read the
   actual high-scoring reports to see HOW they beat it (esp. on the Insight cells).
7. **Measurement**: single-call, no-seed, ±0.027 noise → every fix must be tested with a same-judge baseline + replication.
