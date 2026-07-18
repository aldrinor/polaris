# 0020. Generator and evaluator must be different model families

Status: accepted

Date: 2026-04-18

## Context

A judge drawn from the generator's own training family shares its blind spots and will tend to rubber-stamp its fabrications. In a clinical report a self-confirming judge can wave through a wrong dose or contraindication. Independent lineage is what makes evaluation adversarial instead of an echo. This is one of the oldest POLARIS core invariants (`CLAUDE.md` §9.1, item 1).

## Decision

The generator and the evaluator/judge must be from different training lineages. `openrouter_client.check_family_segregation` raises `RuntimeError` at construction if they match, so this is enforced in code, not by discipline.

## Consequences

- Never reuse one family for both roles to simplify config or save a model slot; a same-family judge is not a real second opinion, and the object will refuse to build.
- The check runs at construction time, so a violation fails fast and loud rather than silently degrading every downstream verdict.
- This is a standing non-negotiable invariant that never relaxes; it constrains model selection alongside the runtime lock (ADR 0021), which pins the specific generator, mirror, sentinel, and judge models.
- The cost is that the config must always source two lineages; that cost is the point, not a limitation to engineer around.
