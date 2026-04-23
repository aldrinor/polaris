# Codex M-54 audit

**Verdict**: CONDITIONAL-no-blockers

## Answers

1. Entity-type-agnostic: YES. The three `TestEntityTypeAgnostic` cases, combined with the loader's implementation, do prove arbitrary non-empty type strings are accepted without code changes. The loader only enforces `type` is a non-empty string and does no vocabulary check (`src/polaris_graph/nodes/report_contract.py:260-264`; `tests/polaris_graph/test_m54_contract_schema.py:271-307`).
2. Path-precise errors: Mostly yes, but not uniformly. Sample paths like `...required_entities[0].rendering_slot` and `...rendering_slots.s1.section` are precise and achievable for most failures. One hole: the referential-integrity error reports `required_entities[{e.id}].rendering_slot`, not the YAML list index, so the path is informative but not strictly path-precise (`src/polaris_graph/nodes/report_contract.py:393-395`).
3. Referential integrity: Agree with both. Rejecting `rendering_slot -> unknown_slot` is correct. Allowing declared-but-unreferenced slots is useful for future growth and is explicitly tested. Allowing multiple entities to share one slot also matches the runtime helper semantics (`entities_by_slot`) and is reasonable for composite/table-style rendering.
4. Forward-compat schema_version: Agree. Accepting unknown version strings in M-54 and deferring warning behavior to M-55 is the right boundary for a shape loader. Tests cover acceptance of future versions.
5. Domain-inheritance descoped: Yes. M-54 is correctly implemented as a flat per-slug map; deferring `extends:` or composition logic to M-55 matches the loader/compiler split stated in the module docstring.
6. Clinical contract content: No blocking gaps in the declared M-54 scope. The contract has the expected 15 required entities and 15 rendering slots: 8 pivotal efficacy trials, 1 mechanism paper, 6 regulatory artifacts. Primary publications carry DOI/PMID metadata where relevant; regulatory items appropriately use `url_pattern`. Minor note only: `surpass_cvot_primary` has DOI but `pmid: null`, which is acceptable at M-54 because PMID is optional/pass-through.

## Findings

- Medium: Unknown-slot `ContractSchemaError.path` is not truly YAML-path-precise. It uses entity id inside list brackets (`required_entities[{e.id}]`) instead of the numeric list index, so callers cannot map the error back to an exact YAML node by path alone. File: `src/polaris_graph/nodes/report_contract.py:393`
- Nit: The test for unknown-slot referential integrity only asserts `"rendering_slot"` appears in `exc.value.path`, so it would not catch the path-format regression above. File: `tests/polaris_graph/test_m54_contract_schema.py:375`

## Next

Claude proceeds to M-55.
