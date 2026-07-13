# BRIEF V3 — THE CELLCOG PROFILE. Design POLARIS's path to the TOP of the board (0.5578).
# READ THE DEBIASING SECTION FIRST. Your previous plan was tunnel-visioned and the operator caught it.

## 0. WHAT YOU GOT WRONG LAST TIME (both designers, independently — do not repeat it)
1. **YOU BOTH ANCHORED ON "REWRITE THE BANKED REPORT".** Both plans took `outputs/rank10_sections_compose/report.md`
   as the substrate and designed a report->report retrofit. That framing CAPPED both plans at ~0.48-0.51 and both of
   you then reported "we cannot reach 0.54" as if it were a fact about the world. **It was a fact about your framing.**
2. **YOU BOTH ACCEPTED A TRADE-OFF YOU NEVER MEASURED: "sources vs thinking" / "breadth vs depth".** Fable capped
   length and proposed DELETING words to raise density. Sol proposed shrinking to 5-7k words. **The #1 system does the
   opposite of both: it has 98 sources (we have 97), writes 13,580 body words, AND is mostly analysis.** There is no
   trade-off. The operator spotted this; neither of you did.
3. **YOU BOTH MISSED THE SINGLE CHEAPEST LEVER ON THE BOARD** (see §2). It was sitting in the artifacts you both read.
4. Fable additionally mis-measured cellcog's citation rate (called it "92% uncited" — it is not uncited, it is
   cited IN PROSE) and built a whole argument on it. **Verify your own measurements against the raw text.**

**METHOD RULE FOR THIS ROUND:** every claim you make must be re-derived from the artifacts at
`/home/polaris/polaris_project/drb_corpus/gpt55_board/` or the grader source. Do not inherit a premise from this brief
or from your last plan without checking it. If you find THIS brief is wrong, say so — that is the most valuable thing
you can do.

## 1. THE TARGET: THE CELLCOG PROFILE (the #1 system, 0.5578)
| | cellcog-max (#1) | bodhi (task-72 winner) | **POLARIS** |
|---|---|---|---|
| overall | **0.5578** | 0.5441 | **0.4382** |
| distinct sources | **98** | 33 | **97** |
| body words | **13,580** | 4,361 | 7,742 |
| H3 subsections | 31 | 40 | **0** |
| median paragraph | 75w | 59w | **677w** |
| **authors named IN PROSE** | **133 (9.8/1k words)** | ~54 | **10 (1.3/1k)** |
| **journals named IN PROSE** | **65** | 1 | **1** |
| `[n]` citation markers | **0** | 105 | **240** |
**cellcog has OUR source count, writes 1.75x our length, and is mostly ANALYSIS. The "breadth vs depth" trade-off is FALSE.**
Two winning shapes exist (bodhi: 33 sources / 4.4k words / half analysis; cellcog: 98 sources / 13.6k words / mostly
analysis). **CELLCOG'S SHAPE IS THE ONE THAT MATCHES OUR STRENGTH — we already have the retrieval depth. We are simply
unable to REASON over what we retrieve.**

## 2. THE CHEAPEST LEVER ON THE BOARD — BOTH OF YOU WALKED PAST IT
**RACE STRIPS EVERY `[n]` MARKER AND THE ENTIRE REFERENCE LIST BEFORE THE JUDGE READS ANYTHING**
(`third_party/deep_research_bench/utils/clean_article.py` — verified: our 345 markers -> 0, our 105-entry bibliography -> deleted).
- **We put ALL our sourcing into `[n]` markers (240 of them). The judge sees NONE of it.**
- **cellcog writes `Acemoglu and Restrepo (2018), in the *American Economic Review*, show...` — that is JUST WORDS IN A
  SENTENCE. The cleaner cannot touch it. It SURVIVES.**
- => **The judge reads cellcog as a rigorously sourced scholarly review, and reads POLARIS as a report with NO SOURCES AT ALL.**
- This is on a task whose instruction is literally *"Ensure the review only cites high-quality, English-language journal
  articles."* **We cite 97 journal articles. The judge sees zero.** Our instruction-following: 0.4409. cellcog: 0.5530.
- **WE ALREADY HOLD THE DATA**: `outputs/rank10_sections_compose/bibliography.json` has `authors[]` and venue per entry.
  Converting `[n]` markers into in-prose `Author (Year, *Journal*)` attribution is a DETERMINISTIC, FABRICATION-PROOF
  transform (every injected token is a byte-substring of the sidecar record). **It is nearly free and neither of you proposed it.**

## 3. THE REAL BOTTLENECK (this is what actually caps us, not length, not sources)
`verify_sentence_provenance` (provenance_generator.py:2098) admits a sentence only if `len(failures)==0`. The entailment
judge's NEUTRAL clause (entailment_judge.py:588) kills any sentence introducing *"a fact, entity, **MECHANISM** ... NOT
present in the SPAN"*.
- A cross-source inference IS, by definition, a mechanism in neither span. **Our gate deletes exactly the sentence type
  the 0.32-weight INSIGHT dimension pays for.**
- Boundary: a CONJUNCTION of two sources passes ("X found 2.1% [a] while Y found 0.4% [b]"). Add one interpretive clause
  ("a gap that may reflect slower adoption") and it is KILLED.
- **This is why we stop at 7,742 words: a fact conveyor RUNS OUT OF THINGS TO SAY. Our length is a SYMPTOM, not a choice.**
  cellcog writes 13,580 words off the same evidence because it can REASON across it.
- **FAITHFULNESS IS THE MOAT AND IS NOT FOR SALE.** No fabricated fact, number, quote, or attribution may EVER ship.
  But note what cellcog's synthesis prose actually is — verbatim:
    *"The three frameworks are complementary rather than competitive. SBTC remains the clearest model for relative skill
    demand... The task-based framework subsumes the phenomena both describe within a more general model... A rigorous
    reading of the field therefore treats these as layered lenses to be deployed according to the question at hand."*
  **That contains NO new fact, NO number, NO new entity. It RANKS AND RELATES ideas already on the page. It is
  ADJUDICATION, and it is FULLY COMPATIBLE with a no-fabrication guarantee.** Design for THAT.

## 4. WHAT THE GRADER PAYS FOR (read from its source, not inferred)
- ONE call scores our report and the reference SIDE BY SIDE, writing a comparative analysis BEFORE the numbers, with all
  ~25 criteria in ONE context => **cross-dimension bleed is real**: our 677-word walls tax the other 86% of the score.
- **Weights: INSIGHT 0.32 | COMPREHENSIVENESS 0.29 | INSTRUCTION-FOLLOWING 0.25 | READABILITY 0.14.** Insight+compreh = 61-64%.
- Scale 0-10 per criterion. Bands: 4-6 Average, **6-8 Good**, **8-10 Excellent**. We read ~6.6; the reference ~9.0.
  **To beat parity a criterion must cross from Good into Excellent. No credit for being a better 7.**
- **Overall = ours/(ours+reference)** — COMPRESSIVE: +1.0 raw on EVERY criterion = only +0.036 overall.
- **LENGTH IS NEVER MENTIONED IN THE SCORING PROMPT.** Padding is penalised at ~0.7% of overall; substance-bearing
  expansion pays into 61-64%. **=> "longer with more FACTS" is dead (we proved it: ranks 7-12, +5,800 words, score flat).
  "longer with more ANALYSIS" is how the #1 system wins.** Do not confuse these two again.
- **HEDGING IS NOT REWARDED. ADJUDICATION IS**: "Critical Evaluation of Evidence and Synthesis of Competing Theories",
  "explains causal relationships behind phenomena", "rather than merely cataloging effects", "identifies key issues...
  provides insightful solutions", "forward-looking thinking".
- Comprehensiveness = breadth AND depth AND **evidence** AND "multiple perspectives and balance" — NOT "more sections".
- Executive summaries: NOT rewarded (the reference ships an EMPTY PLACEHOLDER one and still beats everybody).
- Bullets/tables: NOT the lever (sourcery ships 106 bullets and beats the reference; cellcog ships 0 bullets, 0 tables).

## 5. MEASUREMENT (pinned tonight — never score n=1 again)
- Judge noise SD = **0.0074** (byte-identical artifact scored 6x). k=5 paired => SE(diff) 0.0047 => **smallest resolvable
  effect = +0.0094 at 2 sigma.**
- Generation noise (re-composing the same config) ~0.016 — applies ONLY to arms needing a new compose.
- Our own real history: baseline 0.4062 -> rank10 0.4382 = **+0.032, z=10** (real). Every lever AFTER that (padding
  removal, source firewall) scored FLAT — because all of it was invisible to the judge.

## 6. YOUR TASK — DESIGN THE PATH TO THE CELLCOG PROFILE
Target: **0.5578** (or at minimum bodhi's 0.5441). We are at 0.4382.
**Design for the cellcog shape: ~98 sources (we HAVE them) + ~12-16k words + MOSTLY ANALYSIS + in-prose author/journal
attribution + 30-40 claim-first H3 + ~75-word paragraphs.**

You are NOT restricted to rewriting the banked artifact. **If reaching the cellcog profile requires changing the
COMPOSER (how prose is generated) or the RETRIEVAL (what evidence is banked), design that.** Say what must change and
where (file:line). A ~65-minute compose is an acceptable cost if the mechanism justifies it.

For every lever: the VERBATIM rubric criterion it moves, expected points, how it FAILS, and the CHEAP test that proves
the mechanism fired before a full compose. Respect the faithfulness moat absolutely — but note (§3) that cellcog's
winning synthesis prose adds NO new facts, so the moat and the target are NOT in conflict.

Be honest about the ceiling. And where you are UNCERTAIN, SEARCH (papers, GitHub, and the artifacts on disk).
**Do not hand us another proxy metric — we lost an entire night to those.**
