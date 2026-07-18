# 0004. POLARIS is a Class-B verify-then-organize composition pipeline

Status: accepted

Date: 2026-07-06

## Context

Frontier composition methods split into two classes. Class-A stacks (STORM's article stage, LongWriter, OmniThink) generate freely and attach attribution afterward — generate-then-attribute. Class-B pipelines only organize and phrase content that is already verified. The governing question for any composition candidate (`composition_landscape_2026.md` §0/§1, I-comp-001): does its value survive being clamped to "organize verified spans only", or does its quality come precisely from the free generation POLARIS forbids?

The subtle landmine is cross-claim, author-summary synthesis — an abstract that asserts a NEW relation recombined from body atoms. Bag-of-atoms faithfulness checking provably cannot catch atom-recombination, so every abstractive frontier method steps on it.

## Decision

POLARIS is a Class-B pipeline. The writer may only ORGANIZE and PHRASE already-verified source spans. On strict_verify failure the text degrades to the basket's own verbatim K-span, never to empty. This structurally forbids the free generation that Class-A stacks depend on. GenerationPrograms (modular paraphrase/compress/fuse of source-grounded operations) is the top adoptable frontier method, because attribution is inherent to generation there.

Cross-claim author-summary synthesis is the deliberately-cut gap: it ships ONLY if it comes with an entailment grounding gate. Today POLARIS ships the safe verbatim-only subset.

## Consequences

- Any composition method that draws its quality from free generation is rejected on principle, because that quality is exactly what POLARIS forbids.
- The degrade-to-verbatim-K-span rule guarantees a section never collapses to empty when the gate fails; it collapses to the source's own words.
- The abstractive-synthesis gap is a known, disclosed limitation, not an oversight. Re-opening it requires a real entailment grounding gate first — do not ship an abstract that recombines atoms without one.
- This complements ADR 0003: 0003 separates the granularities; this ADR bounds what the writer is allowed to do inside a composition unit.
