# Codex M-58 audit

**Verdict**: CONDITIONAL-blockers

## Answers

1. Structured-first vs prose-first (rev #1): Mostly yes. `parse_slot_fill_response` builds `SlotFillPayload`/`SlotFieldFill` before `render_slot_prose`, and each field carries `(field_name, status, value, bound_ev_id, source_span)`. The only nuance is that `bound_ev_id` is host-derived from `frame_row`, not model-emitted; that is safer, not worse.
2. Anti-fabrication guard: Not sufficient. The current check proves only that `source_span` exists in `direct_quote`; it does not prove that `value` is supported by that span. A response with `value="1880"` and `source_span="N=1879"` passes today. Add a parser check that extracted `value` is a verbatim substring of `source_span` (optionally after a small normalization rule) or reject.
3. Gap-row handling: `build_slot_fill_prompt` raising on a gap row is the right failure mode. Returning an empty prompt would hide routing bugs and make accidental LLM calls harder to detect. I would also make `compose_gap_payload` raise on non-gap rows so the gap path fails symmetrically.
3a. M-60 gap template: M-58 should own the structured gap payload; M-60 should own the exact prose template if M-60 is the manifest/report surface layer. The current sentence is acceptable as a stopgap, but it couples rendering policy to the slot-fill layer.
4. min_fields_for_completion check placement: Yes. Exposing `payload.completion_count()` in M-58 and comparing against contract minima in M-59 is the cleaner layering.
5. Strict response parser: The biggest missed failure mode is extracted `value` not being supported by `source_span`. I would also add tests for `status=not_extractable` with non-null `source_span`, extracted numeric/non-string values, empty/missing `field_name`, and possibly unexpected top-level/per-field keys if "schema exactly" is meant literally.
6. Prompt contract over/under-constraint: Slightly under-constrained on evidence binding and slightly over-constrained on formatting. Under: it never states "value must be verbatim inside source_span", and the parser does not enforce that. Over: numeric facts must be JSON strings, which JSON-mode models often violate. Rule 5 about "cite only bound ev_id" is also odd because the schema has no citation field.
7. Entity-type-agnostic: Yes for unit scope. The code has no `entity_type` branching, and the statute/DFT tests are enough to show behavior is quote/field-driven rather than type-driven.
8. No-LLM inside M-58: Yes. Keeping M-58 pure and pushing the actual LLM call into the integration layer is the right separation.
9. Determinism framing: Partly correct. M-58 is deterministic for a fixed prompt inputs + parseable JSON response, and prose is deterministic for a fixed payload. That does not make repeated end-to-end generations stable unless the payload/LLM response is persisted.
10. Test coverage: Warranted, not overkill. Parser failures are contract-critical and many are plausible real LLM failures. The one high-value real case still missing is a fabricated `value` paired with a real `source_span`.

## Findings

- Blocker: `parse_slot_fill_response` accepts fabricated extracted values as long as the model supplies any real substring for `source_span`. The parser checks `source_span in direct_quote` but never checks that `value` is supported by that span, so `value="1880"` with `source_span="N=1879"` passes and later renders false prose. Add a hard check that extracted `value` is a verbatim substring of `source_span` (or `direct_quote` under a defined normalization) and add a failure test for that case. `src/polaris_graph/generator/slot_fill.py:315` `tests/polaris_graph/test_m58_slot_fill.py:312`
- Medium: `compose_gap_payload` has no guard that `frame_row.provenance_class` is actually `FRAME_GAP_UNRECOVERABLE`. A misrouted non-gap row would be silently converted into all-`gap_unrecoverable`, which is worse than failing fast because it erases retrievable evidence. Mirror the prompt-builder guard here. `src/polaris_graph/generator/slot_fill.py:366` `tests/polaris_graph/test_m58_slot_fill.py:373`
- Nit: The exact gap prose sentence is embedded in M-58 even though the module comments position M-60 as the layer that consumes the gap state for manifest rendering. If M-60 owns report surface policy, move the template there and keep M-58 focused on payload production plus generic deterministic rendering. `src/polaris_graph/generator/slot_fill.py:31` `src/polaris_graph/generator/slot_fill.py:401`

## Next

After the blocker above is fixed, Claude can proceed to M-59 (slot-completion validator) with the current layering: M-59 should consume `SlotFillPayload`, enforce `min_fields_for_completion`, and validate bound-evidence invariants.
