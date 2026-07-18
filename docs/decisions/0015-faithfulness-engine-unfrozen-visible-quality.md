# 0015. The faithfulness engine is unfrozen: visible quality outranks invisible faithfulness

Status: accepted

Date: 2026-07-10

## Context

The faithfulness engine (strict_verify / NLI / D8 4-role / provenance) had been locked as the ONE untouchable hard gate and explicitly frozen on 2026-06-25. Over time that lock backfired. We over-invested in an invisible property the reader never sees, while depth, coverage, chrome, and readability — the visible things that decide garbage-versus-gold — got starved. The specific backfire: the engine SILENTLY DROPS unproven sentences, thinning the report into a shallow quote-dump. Operator reversal (2026-07-10).

## Decision

The faithfulness engine is no longer the untouchable only-hard-gate in the "never modify it" sense. It is touchable and tunable: delete or fix the piece that backfires. Rewire the silent DROP of unproven sentences into LABEL+REPAIR — keep the claim, show its confidence, repair the weak ones. Do not re-freeze the engine in a future session.

Visible quality now outranks invisible faithfulness in priority. This reprioritizes; it does not abolish grounding — every claim still ties to a source span.

## Consequences

- The past-self lesson: over-locking one property so hard that it starves the qualities that actually win is itself the bug. A frozen gate that produces shallow output has failed its purpose.
- "Unfrozen" is not "unimportant." Grounding is still mandatory per claim; what changed is that the engine may be tuned to serve visible quality instead of being preserved as-is.
- Silent DROP is banned as a behavior; the replacement is LABEL+REPAIR, which aligns with the always-release policy (ADR 0012).
- A future session that re-freezes the engine, or reinstates a silent drop, is repeating the exact mistake this decision reverses.
