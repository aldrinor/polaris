# BRIEF: get POLARIS to SOTA on DeepResearch Bench (RACE), task 72

## What RACE actually is (read this first — most of our past reasoning got it wrong)
RACE is REFERENCE-BASED. An LLM judge scores BOTH our report and a human REFERENCE report
against per-task weighted criteria, then:  **Overall = target / (target + reference)**.
- **0.500 = TIED with the human reference.**  Below 0.5 = worse than the reference.
- Judge noise measured on this box: **±0.016** (two identical-config runs scored 0.4155 and 0.4313).
- EVALUATOR: the benchmark switched judges in 2026 (Gemini-2.5-Pro deprecated -> **GPT-5.5**). Our sweep
  used `openai/gpt-5.5`, i.e. the CURRENT evaluator. Our numbers are on the right scale.

## THE TARGET: 0.5265 (SOTA). WE ARE AT 0.4313. THE GAP IS 9.5 POINTS.
| System | Overall |
|---|---|
| **ADORE (rank 1, SOTA)** | **0.5265** |
| Tavily Research | 0.5244 |
| (human reference = parity) | 0.5000 |
| Gemini-2.5-Pro DR (the ORIGINAL paper's number — now STALE) | 0.4888 |
| **POLARIS Rank10 (us, best)** | **0.4313** |
| POLARIS baseline | 0.4052 |
**The top systems have BEATEN the human reference (>0.50).** Beating the reference is NOT enough for SOTA
any more — we must beat it by ~2.7 points. Do NOT plan to 0.4888; that target is a year out of date.
CAVEAT the plan must respect: leaderboard scores are averaged over ALL 100 benchmark tasks; ours is ONE
task (#72). A plan that overfits to task 72 wins nothing. Prefer levers that generalise across tasks.

## The scoreboard (measured tonight, official harness, task 72)
| Arm | Words | Overall | Comprehens. | Insight | Instr-Follow | Readability |
|---|---|---|---|---|---|---|
| CTRL baseline | 3,343 | 0.4052 | 0.4310 | 0.3839 | 0.4032 | 0.4008 |
| Rank7 (long sections) | 7,615 | 0.4041 | 0.4326 | 0.4070 | 0.3996 | 0.3379 |
| Rank8 (menu cap only) | 4,226 | 0.3957 | 0.4197 | 0.3903 | 0.3907 | 0.3634 |
| Rank9 (both levers) | 7,937 | 0.4155 | 0.4372 | 0.4122 | 0.4241 | 0.3588 |
| **Rank10 (best)** | **9,194** | **0.4313** | 0.4549 | 0.4238 | 0.4409 | 0.3774 |
Rank9 and Rank10 are the SAME effective config (the theme floor was a no-op) => their 0.0158 gap IS the noise floor.

## DIMENSION WEIGHTS FOR TASK 72 (this is where points live)
**Insight 0.32 | Comprehensiveness 0.29 | Instruction-Following 0.25 | Readability 0.14**
Insight is the single biggest lever. Readability is the only dimension we made WORSE, but it is the
LIGHTEST weight — do not over-invest there.

## THE LENGTH QUESTION IS CLOSED
The human REFERENCE report is **9,029 words**. Rank10 is **9,194 words**. We are already AT reference
length. More words cannot help. Anything that trades insight-per-word for length is now strictly harmful.

## THE TASK PROMPT (verbatim — every instruction here is graded)
"Please write a literature review on the restructuring impact of Artificial Intelligence (AI) on the
labor market. Focus on how AI, as a key driver of the Fourth Industrial Revolution, is causing
significant disruptions and affecting various industries. Ensure the review only cites high-quality,
English-language journal articles."

## KNOWN, UNFIXED DEFECTS (found by Fable's prose gate, all still shipping)
1. **4IR framing is SHALLOW, not absent.** (CORRECTED — verify claims like this yourself, do not trust this brief.)
   The earlier "zero mentions" finding was about RANK7 and is now STALE. Measured in the RANK10 BODY:
   "Fourth Industrial Revolution" x4 in 7,742 body words, "4IR" x0. (A naive whole-file grep says x8 — the
   other 4 are in the BIBLIOGRAPHY. This body-vs-references trap already fooled our own density instrument
   once tonight. Split the body from the `## References` section before counting ANYTHING.)
   All 4 body mentions are NAME-DROPS — 4IR appears as scenery, never as an organising frame. The criteria
   (instruction-following w=0.15 "Integration of AI as a Key Driver of the 4IR"; comprehensiveness w=0.10
   "Grounding in the 4IR Context") demand the review DISCUSS AI *within* that context. So the fix is
   INTEGRATION, not insertion. Compare against how the REFERENCE report frames 4IR — it opens with it.
2. **We cite non-journal sources.** Instruction-following criterion w=0.15 demands "all cited sources are
   academic, peer-reviewed journal articles ... books, conference proceedings, news articles, blogs,
   non-peer-reviewed reports are NOT cited." We ship Google Scholar PROFILE PAGES, mirror URLs, and reports.
   NOTE: the driver KILLED the source-eligibility firewall because it did not improve RELEVANCE — but RACE
   grades source type as INSTRUCTION-FOLLOWING (0.25 weight), not relevance. It was judged against the wrong yardstick.
3. **Readability regressions that literally ship:** 27 stray `(also mirrored)` markers leak into prose; TWO
   sections begin MID-WORD ("ings in the last two years.[85]"); the fact_dedup pass writes its own internal
   cross-references into the report body ("...is detailed under Productivity Gains from Generative AI at Work.").
4. **~30-35% of the added words are padding**: verbatim cross-section duplicate facts; the SAME fact cited to
   two different sources (invisible to every dedup we have); and VACUOUS metadata-as-content sentences that pass
   strict_verify because it checks GROUNDING, not INFORMATIVENESS — e.g. "The study received 239 Scopus
   citations.[22]", "This dataset was published in the Strategic Management Journal, volume 42, issue 12."
5. **Rule #9 (15 distinct sources per section) is UNSATISFIABLE and silently ignored** — met in 1 of 10 sections.
   When a prompt rule is unsatisfiable the model does not fail loudly, it PADS by restating what it has.
   One section spends 28 sentences on 8 refs, TEN of them citing [1] alone.
6. **Insight is our LOWEST-scoring dimension and the HIGHEST-weighted (0.32).** strict_verify guarantees every
   sentence is GROUNDED but nothing in the pipeline rewards SYNTHESIS across sources, contrast of competing
   findings, or a thesis. The reference report synthesises; we serially summarise.

## YOUR JOB
Read the FULL Rank11 report **LINE BY LINE, END TO END — every line, no sampling, no skimming, no
"representative excerpts"**. Then read the FULL human REFERENCE report the same way. The reference is the
thing we are scored against: the single most valuable output you can produce is a precise account of what
the reference DOES that we DO NOT.
Then produce a CONCRETE, ORDERED plan to reach **SOTA = 0.5265** from our 0.4313 — a 9.5-point climb.
For EVERY proposed change state: (a) which DIMENSION and which WEIGHTED CRITERION it targets, (b) the
expected point gain and your reasoning, (c) how it could FAIL or backfire, (d) how we would MEASURE it
against a ±0.016 noise floor. Rank by points-per-unit-effort. Be brutally honest: if a lever is exhausted,
say so. We have optimised proxies (words, verified sentences, density) all night that turned out NOT to
move the score — do not hand us another proxy.
