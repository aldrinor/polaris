# BRIEF V2 — EVERYTHING WE NOW KNOW. Design the plan that takes POLARIS to the top of the board.
# (Every number here is MEASURED from primary artifacts on disk or read from the grader's own source code.)

## 1. THE BOARD (task 72, OUR evaluator = GPT-5.5, per-task scores from the benchmark's own raw_results)
| system | OVERALL | compreh | INSIGHT | instr-follow | readability | words | H3 | med-para | bullets |
|---|---|---|---|---|---|---|---|---|---|
| **bodhi** (task-72 winner) | **0.5441** | 0.5441 | 0.5457 | 0.5559 | 0.5199 | **4,361** | 40 | 59w | 14 |
| lunon | 0.5406 | 0.5437 | 0.5594 | 0.5323 | 0.5037 | 11,476 | 50 | 71w | 11 |
| WhaleCloud | 0.5396 | 0.5417 | 0.5429 | 0.5393 | 0.5284 | 7,892 | 33 | 63w | 26 |
| dalpha | 0.5252 | 0.5213 | 0.5200 | 0.5350 | 0.5284 | 4,039 | 0 | 38w | 0 |
| sourcery | 0.5205 | 0.5211 | 0.5397 | 0.5033 | 0.5035 | 9,849 | 38 | 66w | 106 |
| **gemini-2.5-pro-DR = THE REFERENCE** | 0.5102 | 0.5111 | 0.5035 | 0.5187 | 0.5100 | 7,907 | 0 | 131w | 61 |
| openai-DR | 0.4743 | 0.4789 | 0.4475 | 0.4982 | 0.4859 | 8,513 | 0 | 170w | 13 |
| **POLARIS (rank10)** | **0.4382** | 0.4549 | 0.4238 | 0.4409 | **0.3774** | 7,742 | **0** | **677w** | 0 |
| grok | 0.4316 | 0.4292 | 0.3873 | 0.4670 | 0.4706 | 1,060 | 0 | 72w | 0 |
| perplexity | 0.4241 | 0.4228 | 0.4015 | 0.4391 | 0.4507 | 1,510 | 0 | 58w | 0 |
(cellcog-max = 0.5578 corpus-wide #1; it publishes no per-task breakdown. Its task-72 artifact: 16,334w, 31 H3, 75w paras, 0 bullets.)
**"ADORE 52.65" IS FICTION** — absent from the backing data of both boards. Do not plan against it.

## 2. THE GAP, DECOMPOSED (us -> bodhi)
| dim | gap | weight | overall |
|---|---|---|---|
| INSIGHT | +0.122 | 0.32 | **+0.039** |
| instruction-following | +0.115 | 0.25 | +0.029 |
| comprehensiveness | +0.089 | 0.29 | +0.026 |
| readability | **+0.143** | 0.14 | +0.020 |
| | | | **= +0.114 -> 0.552** |
**OUR READABILITY (0.3774) IS THE WORST SCORE ON THE ENTIRE BOARD** — below grok and perplexity, the two systems we beat.

## 3. HOW THE GRADER WORKS (read from its source, not inferred)
- **ONE LLM call scores BOTH reports SIDE BY SIDE.** Ours = article_1, reference = article_2, always. (race.py:99-104)
- **0-10 per criterion**, ~25 criteria. Bands: 4-6 "Average", **6-8 "Good"**, **8-10 "Excellent"**.
  We are being read at ~6.6; the reference reads ~9.0. **To beat parity a criterion must cross from "Good" into "Excellent". There is no credit for being a better 7.**
- **Overall = ours/(ours+reference)** — COMPRESSIVE. +1.0 raw point on EVERY criterion = only **+0.036 overall**.
- **THE JUDGE WRITES A COMPARATIVE ANALYSIS BEFORE IT SCORES** (forced chain-of-thought, prompt lines 47-75), and
  **ALL ~25 CRITERIA ACROSS ALL 4 DIMENSIONS ARE SCORED IN ONE CALL, ONE CONTEXT.** Nothing firewalls the dimensions.
  **=> CROSS-DIMENSION BLEED IS REAL AND UNINSTRUCTED.** The narrative it writes about our 677-word walls is still in
  context when it scores our insight. Our readability disaster is taxing the other 86% of the score.
- **Dimension weights (100-task mean): insight 0.352 | comprehensiveness 0.292 | instruction-following 0.215 | readability 0.141.**
  Insight + comprehensiveness = **64% of the score**.
- **LENGTH IS NEVER MENTIONED IN THE SCORING PROMPT.** No criterion rewards it. Padding is penalised at only ~0.7% of
  overall, while substance-bearing expansion pays into 64%. => "longer but DENSER" wins; "longer and thinner" is pointless.
- **EXECUTIVE SUMMARIES ARE NOT REWARDED.** Proof: the reference ships an EMPTY PLACEHOLDER exec summary
  ("this section will be written after the report body is complete") and still beats every system on every task.
- **HEDGING IS NOT REWARDED.** No criterion anywhere pays for softness or uncertainty-as-stance. What IS rewarded (51
  criteria, inside the 64%-weight dimensions) is **CRITICAL SCRUTINY**: "Critical Evaluation of Evidence and Synthesis of
  Competing Theories", "Critical Scrutiny of Limitations". **The judge does not want us to sound uncertain. It wants us to ADJUDICATE.**
- INSIGHT rubric, verbatim: "deep analysis and original insights rather than simply repeating known information";
  "clear logical reasoning and effectively explains causal relationships behind phenomena"; "identifies key issues ...
  provides insightful solutions"; "forward-looking thinking, can anticipate trends".
- COMPREHENSIVENESS rubric: breadth AND depth AND **evidence** AND "multiple perspectives and balance" — NOT "more sections".
- Structure: "Overall Article Structure and Logical Flow" is the largest readability criterion and explicitly names
  "distinct heading levels" / "effective headings and subheadings". Tables/charts: max ~2.8% of overall. Worth having, not worth optimising hard.
- **RACE STRIPS EVERY CITATION MARKER AND THE ENTIRE BIBLIOGRAPHY BEFORE JUDGING** (utils/clean_article.py, an LLM
  cleaner). VERIFIED: our 9,300 words -> 7,692 read; 345 [n] markers -> 0; 105-entry bibliography -> DELETED.
  **=> ALL bibliography/citation-quality work scores ZERO. Source quality can ONLY be signalled by NAMING VENUES/AUTHORS
  IN THE RUNNING PROSE.** (The 0.5102 reference ships ZERO inline citations.)

## 4. WHAT THE WINNERS DO (measured from their task-72 artifacts)
- **5 of the 6 systems above the reference have 31-50 H3 subsections. Every system at/below the reference has ZERO.**
  (dalpha is the lone exception: 0 H3, but 38-word paragraphs.) **We have 0 H3 and 677-word paragraphs.**
- Winners' median paragraph: **59-75 words**. Reference: 131. OpenAI: 170. **Us: 677 — a different regime entirely.**
- **LENGTH IS DEAD AS A LEVER: bodhi WINS TASK 72 ON 4,361 WORDS — 44% SHORTER THAN OURS.** dalpha scores 0.5252 on 4,039.
- Bullets are NOT the lever (sourcery ships 106 and beats the reference; cellcog ships 0). Tables are NOT the lever (0-5).
- cellcog's synthesis pattern (measured in its prose): grounded finding A (named study + number) -> grounded finding B
  (a CONFLICTING named study) -> a reconciliation sentence carrying NO new facts -> enumerated candidate explanations ->
  an explicit statement of what the evidence CANNOT yet resolve. Plus a dedicated "Critical Synthesis" section
  (convergence / outstanding tensions / limitations / future research).
- Winners ADAPT SHAPE TO GENRE (bullet-density varies 3-10x between applied and scholarly tasks); losers apply one template.

## 5. WHAT POLARIS IS (the constraint you must design around)
- An extraction-grounded FACT CONVEYOR. `verify_sentence_provenance` (provenance_generator.py:2098) admits a sentence
  only if `len(failures)==0`; the entailment judge's NEUTRAL clause (entailment_judge.py:588) kills any sentence that
  "introduces a fact, entity, **MECHANISM** ... NOT present in the SPAN".
- **A cross-source inference is, BY DEFINITION, a mechanism not present in either span. Our own gate deletes exactly the
  sentence type that earns INSIGHT (0.32 — the heaviest weight, and our worst dimension).**
- Boundary, precisely: a CONJUNCTION of two sources ("X found 2.1% [a] while Y found 0.4% [b]") PASSES. Add one
  interpretive clause ("a gap that may reflect slower adoption") and it is KILLED.
- **FAITHFULNESS IS THE MOAT AND IS NOT FOR SALE.** No fabricated fact, number, quote or attribution may ever ship. Any
  design that can leak one is unshippable, whatever it scores. We have a working deterministic contract
  (scripts/reflow_report.py): FACT (span-verified, byte-identical) / STRUCTURE (assembled from sidecar data) /
  INTERPRETATION (no digits, no new proper nouns, no citations, must sit beside >=2 facts from >=2 sources,
  contradiction-screened fail-closed). **NOTE: it was built around HEDGING — and the rubric does not reward hedging.
  It rewards ADJUDICATION. That contract needs rethinking, not just retuning.**

## 6. MEASUREMENT (fixed tonight — use it, never score n=1 again)
- Judge noise: **SD = 0.0074** (byte-identical artifact scored 6x). Baseline is tighter (SD 0.0020).
- k=5 paired => SE(diff) = 0.0047 => **smallest resolvable effect = +0.0094 at 2 sigma.**
- Generation noise (re-composing the same config) is LARGER (~0.016) and applies ONLY to arms needing a new compose.
  A report->report transform of a BANKED artifact has ZERO generation noise — cheap AND sensitive. Prefer it.
- Our own history: baseline 0.4062 -> rank10 0.4382 = **+0.032, z=10** (real). The depth levers DID work, modestly.
  But every subsequent lever (padding removal, source firewall) scored FLAT. And ALL of it was aimed at proxies.

## 7. YOUR TASK
Design the plan that takes POLARIS from **0.4382** to **the top of this board (0.54-0.56)**.
- Ground every lever in the rubric text or a measured artifact. NO PROXIES — we lost a night to them.
- State, for each lever: the criterion it moves, the expected points, how it FAILS, and the cheap test that proves the
  mechanism fired BEFORE we pay for a 65-minute compose.
- Respect the faithfulness moat absolutely. If a lever needs ungrounded prose, say so explicitly and justify the exact
  containment.
- Be honest about the ceiling. If your plan does not reach 0.54, SAY SO and name the residual.
- Where you are UNCERTAIN, SEARCH (papers, GitHub, the artifacts on disk at
  /home/polaris/polaris_project/drb_corpus/gpt55_board/). Do not guess.
