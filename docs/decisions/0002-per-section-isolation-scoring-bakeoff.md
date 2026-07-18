# 0002. Isolation-scoring: bake off each pipeline section on its own axis

Status: accepted

Date: 2026-06-23

## Context

Choosing among component variants (for example, several query-generation strategies) by running a full end-to-end pipeline per candidate is combinatorially expensive and mixes signals — a full run's score reflects every stage at once, so it cannot attribute an improvement to the stage you were actually testing. Operator directive I-qgen-001 (2026-06-23): "no time for full-e2e bake-off; test each section in isolation on its benchmark axis, pick highest, lock, combine, one full run." This became `docs/standard_process_pipeline_section_review.md`.

## Decision

To pick a component variant, score each pipeline section in isolation on the single axis that section drives (for example, query-generation on retrieval coverage). Pick the winner, lock it, then combine the locked winners into one final full run. Do not run a full end-to-end pipeline per candidate.

## Consequences

- Attribution is clean: the per-axis score isolates the stage's effect instead of blending it with every other stage.
- It is far cheaper and faster than a full run per candidate, which is what made the method viable under the delivery clock.
- The risk is that a locally-optimal section winner interacts badly with a downstream stage; the single combined full run at the end is the check that catches that before shipping.
- This became the standard process for all subsequent section bake-offs, so new component decisions should follow it rather than inventing an ad-hoc comparison.
