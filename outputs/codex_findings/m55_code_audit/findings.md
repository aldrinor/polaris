# Codex M-55 audit

**Verdict**: CONDITIONAL-no-blockers

## Answers

1. Entity-type-agnostic guard: Yes, for rev #7's anti-hardcoding intent. `TestEntityTypeAgnostic` proves known, cross-domain, and novel `entity.type` values compile unchanged and pass through verbatim (`tests/polaris_graph/test_m55_frame_compiler.py:305`). Minor note: the old "slot types" wording is stale here; M-54/M-55 has no slot-type vocabulary, only slot ids/sections/orderings.
2. Identifier priority: Agree with `DOI > PMID > url_pattern > anchor` as compiled primary order (`src/polaris_graph/nodes/frame_compiler.py:141`, `:251-277`). Agree that integer `pmid=0` is a non-identifier sentinel at compile time (`:254-256`). That keeps M-56 from treating placeholder zero as retrievable evidence.
3. No-identifier rejection at compiler: Yes, correct layer. M-54 is the structural loader; M-55 is the first stage that knows retrievability is mandatory, so `FrameCompilerError` here is the right boundary (`src/polaris_graph/nodes/frame_compiler.py:245-271`; `src/polaris_graph/nodes/report_contract.py:79-85`).
4. Schema-version forward-compat: Agree. Unknown `schema_version` warning in `CompiledFrame.warnings` without abort is the right M-55 behavior for forward-compat (`src/polaris_graph/nodes/frame_compiler.py:189-200`).
5. Deterministic ordering: Within the implemented contract, yes: `(slot.section, slot.ordering, entity.id)` is deterministic (`src/polaris_graph/nodes/frame_compiler.py:221-233`). But alphabetic section order is not true template semantics; it is label-coupled. For the current clinical slug, `Efficacy < Mechanism < Regulatory` works, but that is effectively by naming convention, not by an explicit contract field.
6. Domain-inheritance descoped: Matches the architectural intent. With one shipped slug, adding `extends:` now would be speculative abstraction. Defer until a second slug creates concrete merge/override rules.
7. Schema errors propagate: Yes. `compile_frame` correctly lets M-54 `ContractSchemaError` surface unchanged rather than wrapping/swallowing it (`src/polaris_graph/nodes/frame_compiler.py:183`; `tests/polaris_graph/test_m55_frame_compiler.py:470-479`).
8. `research_question` pass-through: Agree. Empty string accepted; non-string rejected is the right structural boundary for M-55 (`src/polaris_graph/nodes/frame_compiler.py:174-181`; `tests/polaris_graph/test_m55_frame_compiler.py:415-432`). Semantic validation belongs later, if anywhere.

## Findings

Medium: Cross-section rendering order is still implicit in human-readable section labels, not encoded in the contract. `_ordered_entities()` sorts by `slot.section` alphabetically (`src/polaris_graph/nodes/frame_compiler.py:221-233`), so the current clinical order works by label choice rather than explicit schema semantics. This is not a blocker for M-55/M-56, but it is fragile if section names are renamed, localized, or if a future template wants non-alphabetic section sequencing.

Nit: The revision/test commentary still says "slot types compile without code changes," but the contract has no slot-type field. What is actually proven is arbitrary entity types plus arbitrary slot ids/sections/orderings (`tests/polaris_graph/test_m55_frame_compiler.py:305-359`).

## Next

Claude proceeds to M-56 (deterministic DOI/PMID/Unpaywall retriever).
