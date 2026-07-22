---
name: no-post-generation-fix-rule
description: "HARD RULE: no post-generation fixes EVER — they break comprehensiveness (same family as faith-ghost). All fixes go PRE-generation; constraints become smart scope contracts in the SEARCH phase."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**Operator lesson, 2026-07-22 (delivered after the 7-lever RACE degrade; explicitly "if you forget this, read back our github history").**

**THE RULE:** ANY fix that touches the report AFTER it is generated is a DEAD END. Post-generation manipulation (merging/rewriting/dropping sentences, repairing tables, filtering citations from an already-built report) BREAKS the comprehensiveness of report.md. This is the SAME family as the faithfulness-ghost that cost months (see [[no-entailment-ever-rule]]). Do not do it. Ever.

**Why:** the LLM's generated prose is more coherent than any post-hoc regex/surgery. Cutting or rewriting after the fact thins the report, corrupts sentences, and lowers Insight/Comprehensiveness/Readability — measured directly tonight (all-4-fixes = ~0.49, a degrade vs 0.5084; the two dims that fell were touched by the two POST-generation fixes — narrative consolidation mutated final text, cleaned-output guard repaired final text). See [[flat-result-diagnosis-2026-07-22]].

**WHAT TO DO INSTEAD — make PRE-generation smarter.** Every fix belongs upstream of generation:
- Shape WHAT gets written via the prompt/guidance and via the EVIDENCE given to the model — never by editing after.
- **Constraints belong in the SEARCH/RETRIEVAL phase as a smart SCOPE CONTRACT, not as a post-hoc filter on a fixed corpus.** Example (the "only journal articles" constraint): do NOT delete non-journal sources after the report exists, and do NOT even subtract them at compose-time from a pre-built corpus (that just thins 997→127 → degrade). Instead the scope contract sets the gate DURING search so it (a) pushes away the sources you don't want, AND (b) keeps searching DEEPER and DEEPER to find MORE of the sources you DO want. Result: the generation input is BOTH compliant AND comprehensive (e.g. end with 300+ wanted-type sources, not 127 survivors of a cut). Subtraction thins; a search-phase contract that excludes-and-deepens preserves/grows comprehensiveness.

**READABILITY / FORMAT / STYLE — same rule.** To improve readability, format, or style, make the COMPOSE LLM's PROMPT robust enough that the model GENERATES the format and style we want (paragraph flow, transitions, bold emphasis, non-repetition, well-formed tables) natively. Do NOT reformat/repair/consolidate after generation. If the output reads badly, the fix is a better generation prompt, not post-hoc surgery. The two allowed fix locations are: (1) the SEARCH/scope contract (what evidence enters), and (2) the GENERATION prompt (how the model writes). Nothing after the model has written.

**Concrete implication for the current effort:** RETIRE the post-generation fixes (narrative consolidation, cleaned-output guard, compose-time citation eligibility filter). REPLACE the eligibility idea with a retrieval-phase constraint-aware scope contract that filters unwanted source types at search time and drives the retriever to find more wanted-type sources. Move readability/format/de-repetition into a robust compose prompt. Keep only pre-generation shaping (e.g. coverage-obligations as outline/prompt guidance). Then target Insight+Comprehensiveness (0.61 weight) via smarter retrieval + a stronger generation prompt, never post-hoc edits.
