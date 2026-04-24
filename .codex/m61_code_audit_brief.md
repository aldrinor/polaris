M-61 code audit — xhigh reasoning.

**Skip git status.** Two files only.

## Scope

Commit `7da7b18`. Files:

1. `src/polaris_graph/retrieval/human_gap_completion.py`
   (~370 lines) — Path B completion interface.
2. `tests/polaris_graph/test_m61_human_completion.py`
   (~370 lines, 26 tests in 8 classes).

Codex at gpt-5.4 + xhigh (default). Skip V30 plan + prior audits.

## Your pass-1 plan verdict to verify

M-61 plan verdict was `needs_revision`. Revision #6:
  "replace free-text-only `consent_proof` with a structured
   provenance object. Minimum fields: curator_id, source_type,
   source_locator, acquired_at, artifact_sha256,
   artifact_retention_path, quote_page_range, attestation.
   Human-curated rows should remain permanently flagged in
   evidence, manifest, and rendered Methods disclosure."

Revision #7 (verification scope): "`strict_verify` may verify
quote-to-row consistency, but it cannot verify quote-to-original-
source authenticity for human-curated content. The plan should
state that explicitly and treat provenance assurance as
audit-log + retained-artifact based, not as solved by
`strict_verify`."

Verify M-61 ships structured provenance (all 8 fields required,
no free-text consent_proof acceptance) AND the human_curated
flag is permanent.

## Questions

1. **Structured provenance (rev #6)**: all 8 required fields
   enumerated in StructuredProvenance dataclass and enforced in
   `_parse_provenance`. Missing any → CompletionSchemaError.
   Sufficient? Or any field you'd add/remove?
2. **source_type allowlist**: 5 values (institutional /
   personal subscription / author communication / legally-
   accessed preprint / other). `other` is a pressure valve.
   Acceptable, or should `other` require justification?
3. **artifact_sha256 validation**: 64 lowercase hex enforced by
   regex. Normalized to lowercase before storage. Independently
   recomputable via `compute_artifact_sha256(bytes)`. Sufficient
   for audit replay?
4. **acquired_at validation**: requires timezone-aware ISO-8601.
   Naive datetimes rejected. 'Z' suffix accepted via replace.
   Other formats rejected. Agree with the strictness?
5. **DOI substitution attack**: `validate_against_tasks` rejects
   entity_id-match + DOI-mismatch combinations. Operator can't
   swap one paper for another. Sufficient fraud defense?
6. **Unmatched entity_id**: completions for entities NOT on the
   M-60 task list are rejected with explicit reason. Prevents
   operator from supplying content for a PASS or
   engineer-owned entry. Correct?
7. **Human-curated permanent flag (rev #6)**: FrameRow emits
   quote_source=HUMAN_CURATED_PROVENANCE ("human_curated").
   Passing this through M-57 slots + M-58 rendering + M-60
   manifest — does it stay visible everywhere, or can it be
   lost in a handoff?
8. **Provenance object not in FrameRow**: the StructuredProvenance
   is not serialized into FrameRow (would require extending
   frame_fetcher schema). Caller keeps an in-memory map keyed
   by entity_id. Is that the right boundary, or should
   FrameRow gain a `provenance: StructuredProvenance | None`
   field?
9. **strict_verify division of concerns (rev #7)**: M-58
   value==source_span still enforced for human-curated content
   (via the SlotFillPayload path), but that can't verify
   authenticity. structured provenance + retained artifact +
   audit log is the authenticity defense. Is this separation
   documented clearly enough?
10. **Methods disclosure**: compose_methods_disclosure_human_curated()
    produces "N retrieved + M human-curated from licensed sources".
    V30 plan wanted tier disclosure; this matches. Any missing
    element (e.g. list of curator_ids)?
11. **Entity-type-agnostic (rev #7)**: no branching on
    entity_type. DOI=null accepted for entities without DOI
    (statute, URL-only regulatory). Tests include statute + dft.
    Sufficient?
12. **Determinism**: parse_completion, validate_against_tasks,
    to_frame_rows are pure (no I/O). load_completions reads
    file. Determinism claim scoped correctly?

## Output

Write to `outputs/codex_findings/m61_code_audit/findings.md`.

Format:
```markdown
# Codex M-61 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Structured provenance (rev #6): ...
2. source_type allowlist: ...
3. artifact_sha256 validation: ...
4. acquired_at validation: ...
5. DOI substitution attack: ...
6. Unmatched entity_id: ...
7. Human-curated permanent flag: ...
8. Provenance object not in FrameRow: ...
9. strict_verify division: ...
10. Methods disclosure: ...
11. Entity-type-agnostic: ...
12. Determinism: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-62
(non-clinical generalization guard — V30's final layer).
```

Keep under 150 lines. Full xhigh reasoning budget. Specifically
look for fraud/fabrication paths the schema still permits.
