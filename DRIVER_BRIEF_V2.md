# DRIVER BRIEF V2 — READ THIS INSTEAD OF THE OLD RESUME_NOW.md
## The old brief is RETIRED. Everything it told you to optimise has been MEASURED AND REFUTED.

You are the POLARIS flywheel driver. Chat history is gone every restart; ONLY these files are truth.

## THE ONE THING YOU MUST INTERNALISE
We spent an entire night optimising **proxies** — words, verified sentences, distinct works, density,
bibliography tier-compliance — and then, for the first time, ran the ACTUAL SCORER. **The proxies did not move the score.**

| arm | lever it tried | words | RACE |
|---|---|---|---|
| baseline | — | 3,343 | 0.4052 |
| Rank7 | longer sections | 7,615 | 0.4041 |
| Rank8 | writer menu cap | 4,226 | 0.3957 |
| Rank9 | both stacked | 7,937 | 0.4155 |
| Rank10 | + theme floor (no-op) | 9,194 | **0.4313** |
| Rank11 | cross-section repetition guard | 7,178 | 0.4133 |
| Rank12 | source-eligibility firewall | 7,829 | 0.4276 |

**Ranks 9-12 are ONE INDISTINGUISHABLE CLUSTER (noise ~±0.016). Four levers, four theories, one flat line.**
The whole 2.7x depth push bought **~one noise-width**. SOTA = **0.5265** (ADORE). We are at **~0.42**.

## WHY EVERY LEVER FAILED — THE MECHANISM (verified, do not re-litigate)
**RACE DELETES THE BIBLIOGRAPHY AND EVERY `[n]` CITATION MARKER BEFORE THE JUDGE READS A WORD.**
(`third_party/deep_research_bench/utils/clean_article.py` — an LLM pass: *"remove all citation links, citation
marks, reference lists, footnotes"*.) Verified by diffing submitted vs judge-read:
`9,300 words -> 7,692 | [n] markers 345 -> 0 | 105-entry bibliography -> DELETED | "(also mirrored)" 25 -> 0 | "(tier T6)" 105 -> 0.`

Consequences, all of them expensive:
- **ALL bibliography-side work scores ZERO.** The Rank12 firewall drove tier-compliance 43.3% -> 72.8% and
  instruction-following on the scorecard went **DOWN** (0.4409 -> 0.4280, within noise). The lever aimed at the
  dimension did not move the dimension. Source quality can ONLY be reached by **naming venues in the running prose**.
- **The readability defects we blamed for months are GHOSTS** — the `(also mirrored)` markers and tier labels are
  stripped by the cleaner. They never touched the score.
- **Length is CLOSED.** The human reference body is 9,029 words; our judge-read body is 7,692. More words cannot help.

## WHAT THE JUDGE ACTUALLY SEES (post-cleaner) — THE REAL GAP
| | OURS (0.4313) | REFERENCE (0.5000) |
|---|---|---|
| body paragraphs | **12** | **59** |
| avg paragraph | **633 words** | **142 words** |
| H3 subsections | 0 | 24 |
| tables | 0 | 10 |
| bullets | 0 | 91 |

**Our report is twelve walls of text. The reference is a navigable argument.**
Two independent reviewers (Codex 5.6 max-thinking, Fable — each reading both full reports line-by-line, blind to
each other) converged on ONE diagnosis:

> **The reference converts evidence into an ARGUMENT. POLARIS converts retrieved passages into SENTENCES.**

**This is ARCHITECTURAL, not a tuning gap.** `strict_verify` requires every sentence to be span-grounded in ONE
source. That STRUCTURALLY FORBIDS the sentence that earns insight — the cross-source inference
(*"this discrepancy may reflect implementation lags inherent to general-purpose technologies"*). **We did not fail
to write synthesis. We built a machine that cannot.** Insight is **0.32 — the heaviest dimension, and our worst.**
Our report literally ships, inside the section graded for critical synthesis:
*"No contradictions were detected by the pipeline."* We are telling the judge we did none.

## DIMENSION WEIGHTS (task 72) — where points actually live
**INSIGHT 0.32 | COMPREHENSIVENESS 0.29 | INSTRUCTION-FOLLOWING 0.25 | READABILITY 0.14**
Free points on the floor: **"Scope of Industry-Specific Analysis" = 0.25 of comprehensiveness, and we have ZERO
industry-organised content.** The reference has a whole sectoral section.

## THE RULES YOU NOW RUN UNDER
1. **THE SCORE IS THE ONLY METRIC.** Run `scripts/score_report_race.py`. Words, verified sentences, distinct works,
   density and tier-compliance are **GATES, NOT OBJECTIVES**. Never again claim a win from an internal counter.
2. **NEVER n=1.** Judge noise is ~±0.016 and every lever is worth ~+0.010. Score **k=5, paired, interleaved**
   (`scripts/noise_floor_k5.sh`). A single-run delta under ~0.02 is UNINTERPRETABLE.
3. **FAITHFULNESS IS NOT FOR SALE.** The two-tier claim system must NOT open a hallucination hole. An INFERENCE
   sentence is legal only if **every premise it rests on is span-grounded** and it is phrased as interpretation.
   If an ungrounded assertion can reach the page, the design is UNSHIPPABLE. This is our moat; the frontier
   products do not have it.
4. **CHEAP TEST BEFORE EXPENSIVE COMPOSE.** Prove the mechanism FIRED (a counter, a diff, a rendered fragment)
   before paying for a ~65-minute compose + score.
5. **DEFAULT-OFF, ENV-GATED** for every change. And **CHECK THAT IT ACTUALLY BITES** — Rank11 taught us a flag can
   fire and consolidate ZERO ("the wins are switched off" is only half the lesson).
6. **SPLIT BODY FROM `## References` BEFORE COUNTING ANYTHING.** A whole-file regex re-reads the bibliography as
   prose. This has produced **three** false findings already.
7. **GATE / DEEP THINKING = FABLE.** Codex 5.6 Sol may be used ONLY detached + read-only + hard timeout, never inline.
8. **APPEND ONE HONEST LINE TO `FLYWHEEL_PROGRESS.md` AFTER EVERY STEP.** Report refutations of your own claims as
   loudly as wins. The operator has explicitly asked to be told when we are wrong.

## THE MISSION
Build the architecture that lets the writer REASON ACROSS SOURCES, then fix -> test -> score -> read the prose
line-by-line -> fix again, until we beat **0.5265**. The build plan is in `SOTA_BUILD_PLAN.md`.
**If the thesis dies, SAY SO and stop — do not build on a corpse for weeks.**
