# WHEEL TURN 3 — DIAGNOSE A REAL FAILURE. Everything here is MEASURED, not inferred.

## THE RESULT: turn 2 scored 0.4224. The baseline (rank10) is 0.4382. THE ARM LOST.

| dimension | rank10 | TURN 2 | delta | reference |
|---|---|---|---|---|
| insight | 6.45 | 5.87 | **-0.58** | 8.35 |
| comprehensiveness | 7.22 | **6.08** | **-1.14** | 8.13 |
| instruction-following | 6.11 | **6.74** | **+0.63** (the ONLY gain) | 7.79 |
| readability | 4.71 | 4.63 | **-0.08** (did NOT move) | 8.47 |

## WHAT CHANGED IN TURN 2 (all at once — my error)
- corpus: 97 heterogeneous sources -> 32 journal papers (via citation-graph expansion)
- median paragraph: 677w -> 106w ; H3: 0 -> 21 ; [n] markers: 240 -> 0
- journal names in prose: 0 -> 135 (format: "Writing in the <JOURNAL> in <YEAR>, <AUTHORS> show that...")
- epistemic labels: 0 -> 44 ; words: 7,742 -> 6,305
- a faithfulness gate now on the critical path (74 sentences dropped)

## THE JUDGE — ITS OWN WRITTEN CRITIQUE OF TURN 2 (this is the whole point; we no longer guess)

### THE ONE BIG WIN — the attribution lever is CONFIRMED
**"Exclusive Citation of High-Quality Journal Articles": us = 7.5, reference = 4.0.** We were at **1.5/10**.
A **+6.0 point** swing — the largest single criterion move we have ever made. Judge, verbatim:
> "Article 1 EXPLICITLY CLAIMS to rely only on peer-reviewed English-language journal articles and most
> cited sources appear to be journal articles. However, some journals are less clearly high-quality, and
> **the article lacks a formal reference list, making verification difficult.**"

### WHY READABILITY DID NOT MOVE (-4.5 on Language Clarity) — and it is OUR OWN DOING
> "Article 1 ... contains many language and editing problems: **repeated phrases such as 'Writing in,'**
> duplicated clauses, incomplete sentences, awkward constructions, missing words, and typographical
> issues. These SEVERELY REDUCE CLARITY."
**We used ONE attribution template 135 times. It reads as a machine.**
> "-4.0 [S1 Structure]: the organization breaks down due to **repetition, incomplete sections, abrupt
> endings, and sections that do not fulfill their headings.** The conclusion and implications sections
> are especially weak."

### WHY COMPREHENSIVENESS COLLAPSED (-1.14)
> "-4.0 [Grounding in 4IR]: the discussion is **thin, fragmented** ... without clearly defining 4IR or
> explaining how AI is embedded in the broader 4IR technological system."
> "-2.8 [Disruption Character and Scale]: the specific subsection on scale and speed is **extremely brief**."

### WHY INSIGHT FELL (-0.58) DESPITE 44 EPISTEMIC LABELS
> "-4.2 [Value and Foresight]: the implications section is **truncated, repetitive**, and largely confined
> to measurement gaps ... limited actionable foresight."
> "-4.1 [4IR Integration]: it does not substantially LEVERAGE the 4IR framework to explain interconnected
> digital infrastructures, cyber-physical integration, or why AI differs from prior technological waves."

## THE MEASURED CONTEXT YOU MUST RESPECT
- cellcog (#1) = 0.5603, scores 9.1-9.5 on EVERY dimension. bodhi = 0.5441. reference = 0.5102.
- **R IS NOT FIXED**: the same reference scores 8.03 vs us, 7.36 vs cellcog. A better report DRAGS IT DOWN.
  Our weak report is INFLATING our opponent. Every improvement pays twice.
- The honest bar: weighted mean 6.35 -> ~9.6/10, ABOVE cellcog. ~13 stacked levers.
- **898-article panel (verified): sections/H3 are a WELL-POWERED NULL (+0.0020/SD). Length SATURATES at
  ~8,000w and is a FLOOR (~5,000w), not a lever.** Turn 2 CONFIRMED this: paragraphs 677->106 and H3 0->21
  moved readability by **-0.08**. STRUCTURE ALONE IS WORTH NOTHING. The judge said the defect is COHESION
  ("fragmented narrative... without adequate transitions"), NOT paragraph size. We made them short and left
  them just as disconnected.

## YOUR TASK — DIAGNOSE AND DESIGN TURN 3
The attribution lever WORKS (+6.0). Everything else in turn 2 LOST. Tell me, concretely:
1. **What EXACTLY do we change for turn 3?** Ordered. Each change must name the criterion it targets.
2. Do we KEEP composing from the 32-paper journal corpus, or TRANSFORM the 97-source rank10 report
   (which has the comprehensiveness we just destroyed)? Argue it.
3. The prose is REPETITIVE, TRUNCATED and INCOMPLETE. Is that a PROMPT problem, a TOKEN-BUDGET problem,
   or an ARCHITECTURE problem? Be specific.
4. What is the CHEAPEST test that proves each fix fired BEFORE we spend a compose + judge call?
Be brutal. A failed arm that teaches is worth more than a lucky one. Do not hand me a proxy.
