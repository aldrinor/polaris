M-58 code audit — tight.

**Skip git status.** Focus only on the two files below.

## Scope

Commit `df0835c`. Two files:

1. `src/polaris_graph/generator/slot_fill.py` (~360 lines) —
   M-58 slot-bound structured-first generator. New module.
2. `tests/polaris_graph/test_m58_slot_fill.py` (~500 lines) —
   27 tests in 7 classes.

Do not re-read V30 plan or prior findings. This audit runs at
gpt-5.4 + reasoning effort xhigh (previous audits ran at
effort=none — you now have full reasoning budget).

## Your pass-1 revision to verify

Your M-58 plan verdict was `needs_revision` (structured-first
over prose-first). Revision #1 required:
  "change the slot-bound generation contract from paragraph-only
   to structured-first. Each slot should emit a machine-readable
   payload for every required field: field_name, status
   (extracted | not_extractable | gap_unrecoverable), value,
   bound_ev_id, source_span."

Verify M-58 actually ships structured-first (not prose-first).

## Questions

1. **Structured-first vs prose-first (rev #1)**: `parse_slot_fill_response`
   returns SlotFillPayload with per-field `(field_name, status,
   value, bound_ev_id, source_span)` tuples BEFORE any prose is
   rendered. `render_slot_prose` is a pure function that consumes
   the payload. Does this satisfy rev #1?
2. **Anti-fabrication guard**: `parse_slot_fill_response` raises
   when `source_span` is not a verbatim substring of
   `direct_quote`. Is that sufficient protection against LLM
   fabricating extracted values, or do you want stronger checks
   (e.g. verify the value itself appears inside source_span)?
3. **Gap-row handling (plan review #4)**: `compose_gap_payload`
   skips the LLM entirely for FRAME_GAP_UNRECOVERABLE rows and
   emits `status=gap_unrecoverable` for every field.
   `build_slot_fill_prompt` RAISES on a gap row (forbidden path)
   rather than silently returning empty — is that the right
   failure mode, or should it return an empty prompt?
3a. **M-60 gap template**: `render_slot_prose` on an all-gap
   payload emits: "{subsection}: Primary publication was not
   retrievable from open-access, abstract, or metadata sources.
   All required fields are unavailable for this entity. [ev_id]"
   Is this the right prose surface for M-60, or should M-60
   own the template?
4. **min_fields_for_completion check placement**: M-58 exposes
   `payload.completion_count()` but does NOT compare against
   the contract's min_fields. That comparison lives at M-59.
   Correct layering?
5. **Strict response parser**: missing required field / extra
   field / invalid status / duplicate / empty-value-on-extracted
   / non-null-value-on-not-extractable / non-substring source_span
   all raise SlotFillParseError. 10 failure tests in
   `TestParseFailures`. Are there parser failure modes I missed?
6. **Prompt contract**: system prompt + context + bound evidence
   + required fields bullet list + JSON schema example +
   6 explicit rules (every field appears once; status vocab; span
   must be verbatim; no extra fields; cite only bound ev_id;
   no inference). Does it over- or under-constrain the LLM?
7. **Entity-type-agnostic (rev #7)**: no `entity_type` branching.
   Tests include statute and dft_primary fills. Sufficient?
8. **No-LLM inside M-58**: all four public functions are pure
   (no httpx, no os.environ, no wall-clock). LLM call happens
   in the integration layer. Is this the right separation, or
   should M-58 own the call?
9. **Determinism**: `build_slot_fill_prompt` + `render_slot_prose`
   are byte-deterministic. `parse_slot_fill_response` is
   deterministic given parseable JSON. The LLM response itself
   is not deterministic, but M-58 captures it as a payload
   and renders deterministically — so downstream layers see
   stable prose. Correct framing?
10. **Test coverage parity with V30 plan**: plan asked for 6
    tests; shipped 27. Overkill or warranted? Particularly —
    are all the parser-failure tests real failure modes that
    could happen with a real LLM, or are some hypothetical?

## Output

Write to `outputs/codex_findings/m58_code_audit/findings.md`.

Format:
```markdown
# Codex M-58 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Structured-first vs prose-first (rev #1): ...
2. Anti-fabrication guard: ...
3. Gap-row handling: ...
3a. M-60 gap template: ...
4. min_fields_for_completion check placement: ...
5. Strict response parser: ...
6. Prompt contract over/under-constraint: ...
7. Entity-type-agnostic: ...
8. No-LLM inside M-58: ...
9. Determinism framing: ...
10. Test coverage: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-59
(slot-completion validator — consumes SlotFillPayload, checks
against contract's min_fields_for_completion and bound_ev_id
rules).
```

Keep findings.md under 150 lines. Use your full xhigh reasoning
budget — surface anything a weaker pass would have missed.
