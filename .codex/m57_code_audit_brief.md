M-57 code audit — tight.

**Skip git status.** Focus only on the two files below.

## Scope

Commit `d039940`. Two files:

1. `src/polaris_graph/nodes/contract_outline.py` (~260 lines) —
   M-57 contract-driven outline composer. New module, standalone
   (no generator/ imports).
2. `tests/polaris_graph/test_m57_contract_outline.py` (~420 lines)
   — 19 tests in 11 classes.

Do not re-read V30 plan or prior findings.

## Your pass-1 revision to verify

Your M-57 verdict was `root_cause_approved`. You said:
"Correctly moves outline authority from LLM emergence to contract
instantiation."

Verify M-57 actually does that — outline structure comes from
contract, not LLM.

## Questions

1. **Contract-determined vs LLM-emergent**: `compose_outline_from_contract`
   is a pure function (no LLM, no network). Sections come from
   `contract.section_order`; slots from `rendering_slots` sorted
   by `ordering`; entity_ids from `entities_by_slot()`. Is outline
   authority fully transferred to the contract?
2. **Gap-slot preservation (Codex plan review #4)**: slots whose
   frame rows are ALL FRAME_GAP_UNRECOVERABLE still appear with
   `is_gap=True` + `provenance_classes=("frame_gap_unrecoverable",)`.
   Is that sufficient for M-60 to render explicit gap content
   deterministically? If not, what other per-slot structured
   metadata should travel?
3. **Partial slot semantics**: multi-entity slot with mixed
   gap/non-gap rows is `is_partial=True` with `is_gap=False`.
   Agree with this boundary, or should partial be treated as
   gap?
4. **Determinism**: pure function, no wall-clock, explicit sort
   on sections + slots + entity_ids within a slot. Proven by
   `TestDeterminism::test_same_inputs_yield_same_outline` which
   asserts `o1 == o2`. Sufficient?
5. **Parallel-validation of frame_rows**: length/order checks
   raise ValueError. Is that the right layer to enforce the
   M-56 ordering contract?
6. **Entity-type-agnostic (Codex rev #7)**: statute +
   dft_primary + unknown_xyz_2099 compose together in the same
   outline. `TestEntityTypeAgnostic::test_statute_dft_novel_types_compose`.
   Sufficient?
7. **Section-order policy duplication**: both M-55
   `_ordered_entities` and M-57 `_resolve_section_order`
   implement the same "section_order wins / alphabetic fallback"
   policy. Comment flags the duplication; real-yaml integration
   test covers both. Is leaving the duplication acceptable, or
   should it be factored into a shared helper?
8. **Standalone vs integrated**: M-57 does NOT touch
   `multi_section_generator.py`. `ContractOutline.to_section_plan_dicts()`
   gives the legacy shape for any caller that wants it. Actual
   integration happens at M-58 (slot-bound prompts). Agree with
   deferring integration?
9. **Focus string**: deterministic one-line summary
   (e.g. "8 subsections: SURPASS-1, SURPASS-2, ..., +2 more").
   Entity-type-agnostic. Suitable for section-level prompt
   header use, or should it carry more structured info?
10. **Real clinical.yaml integration test**: produces 3 sections
    in explicit section_order with 8/1/6 slot distribution;
    SURPASS-1..6 + CVOT + SURMOUNT-2 titles all present.
    Sufficient integration proof, or do you want another slug
    exercised?

## Output

Write to `outputs/codex_findings/m57_code_audit/findings.md`.

Format:
```markdown
# Codex M-57 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Contract-determined vs LLM-emergent: ...
2. Gap-slot preservation: ...
3. Partial slot semantics: ...
4. Determinism: ...
5. Parallel-validation: ...
6. Entity-type-agnostic: ...
7. Section-order policy duplication: ...
8. Standalone vs integrated: ...
9. Focus string: ...
10. Real clinical.yaml integration: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-58
(slot-bound generator prompts, V30 Layer 4 begins).
```

Keep findings.md under 130 lines.
