M-59 code audit — xhigh reasoning.

**Skip git status.** Two files only.

## Scope

Commit `44810bf` (post-M-58 pass-6 APPROVED). Files:

1. `src/polaris_graph/generator/slot_validator.py` (~330 lines) —
   M-59 validator. New module.
2. `tests/polaris_graph/test_m59_slot_validator.py` (~420 lines)
   — 18 tests in 12 classes.

Skip V30 plan + prior audit findings. Codex at gpt-5.4 + xhigh
(default in ~/.codex/config.toml).

## Your pass-1 plan verdict to verify

M-59 plan verdict was `needs_revision`. Your revision #3:
  "Validator should validate slot existence, bound evidence, and
   per-field completion status from structured output, not prose
   heuristics. Validator should emit a slot coverage object
   consumable by M-60 manifest rendering."

Verify M-59 consumes M-58 SlotFillPayload (structured) and emits
per-entity + per-slot verdicts, NOT prose heuristics.

## Questions

1. **Structured consumption (rev #3)**: `validate_slot_completion`
   takes `payloads_by_entity_id: dict[str, SlotFillPayload]` as
   input. Per-entity checks read `payload.completion_count()` +
   `payload.provenance_class` + `payload.slot_id` + `payload.entity_id`.
   Only TWO prose-substring checks remain: `[entity_id]` citation
   and `_GAP_MARKER in prose`. Are those acceptable prose
   touchpoints, or should citation-checking also be structured?
2. **Per-entity verdicts**: each entity gets its own
   EntityValidation with explicit verdict + reason. SlotAggregateVerdict
   takes the first failing entity's verdict. Sufficient for M-60
   manifest rendering? Or do you want aggregate richer semantics
   (e.g. "partial fail — 3 of 5 entities passed")?
3. **Gap-slot requirements**: gap entity passes iff prose contains
   _GAP_MARKER="was not retrievable" AND `[entity_id]`. Agree with
   both requirements? Is the marker check too coupled to M-58's
   current template?
4. **Min-fields resolution**: validator reads
   `entity.min_fields_for_completion` from ReportContract (source of
   truth), not from ContractOutline (which doesn't carry the
   threshold). Right layer?
5. **Check order**: per-entity checks are
   missing-payload → slot_id/entity_id mismatch → gap-path OR
   non-gap path (citation → min_fields). Short-circuits on first
   failure. Agree, or want all failures enumerated?
6. **Payload mismatch fail mode**: if M-58 produced a payload
   with wrong slot_id/entity_id (pipeline crossed wires), M-59
   emits FAIL_PAYLOAD_MISMATCH. Correct defensive layer?
7. **Defensive "slot in contract but not in outline iteration"**
   path in validate_slot_completion — is it reachable given
   M-57's invariants, or dead code? If dead, should be removed.
8. **Entity-type-agnostic (Codex rev #7)**: no branching on
   entity_type. statute + dft_primary tests pass identically.
   Sufficient?
9. **Determinism**: pure function, deterministic iteration
   (outline.sections nested loop). `test_same_inputs_yield_same_report`
   asserts `r1 == r2`. Enough?
10. **Anti-fabrication from M-58 upstream**: M-58 already rejects
    fabricated values via value==source_span enforcement. M-59
    therefore doesn't re-check value authenticity. Is that the
    right division of concerns, or should M-59 independently
    verify the payload is consistent with the frame_row used to
    build it?

## Output

Write to `outputs/codex_findings/m59_code_audit/findings.md`.

Format:
```markdown
# Codex M-59 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Structured consumption: ...
2. Per-entity verdict granularity: ...
3. Gap-slot requirements: ...
4. Min-fields resolution layer: ...
5. Check order: ...
6. Payload mismatch fail mode: ...
7. Defensive dead code: ...
8. Entity-type-agnostic: ...
9. Determinism: ...
10. Anti-fabrication division of concerns: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-60.
```

Keep under 130 lines. Full xhigh reasoning budget.
