M-60 code audit — xhigh reasoning.

**Skip git status.** Two files only.

## Scope

Commit `6cb6963`. Files:

1. `src/polaris_graph/generator/frame_manifest.py` (~310 lines).
2. `tests/polaris_graph/test_m60_frame_manifest.py` (~540 lines,
   14 tests in 10 classes).

Codex at gpt-5.4 + xhigh (default). Skip V30 plan / prior audits.

## Your pass-1 plan verdict to verify

M-60 plan verdict was `needs_revision`. Your revision #4:
  "Manifest output must carry structured failure metadata and
   retrieval-attempt details, not just a human sentence.
   Machine-readable metadata for every incomplete slot:
   slot_id, entity_id, status, failure_reason,
   retrieval_attempt_log, available_artifacts,
   human_completion_eligible."

And revision #5 (M-60 report language):
  "keep the explicit clinician-facing sentence, but avoid
   overfitting it to one publication string. Template it from
   structured metadata so the report is explicit and consistent."

Verify SlotCoverageEntry carries all 7 required fields + the
Methods disclosure is template-driven (no hardcoded trial name).

## Questions

1. **Structured metadata (rev #4)**: SlotCoverageEntry fields are
   slot_id, entity_id, section, subsection_title, status,
   provenance_class, failure_reason, retrieval_attempt_log,
   available_artifacts, human_completion_eligible, doi, pmid.
   All seven Codex-required fields present plus four echo fields
   for M-61 consumption. Sufficient for M-60 manifest + M-61
   downstream?
2. **retrieval_attempt_log passthrough**: M-56 emits one
   RetrievalAttempt per HTTP request (Blocker 2 fix). M-60
   flattens each into a dict with source/url/attempt_index/
   http_status/outcome. Full retry chain visible. Agree that's
   the right manifest shape?
3. **Methods disclosure (rev #5)**: compose_methods_disclosure()
   produces deterministic prose from the structured coverage —
   NO hardcoded trial names. Three shapes: all-pass (single
   line), partial-only (enumerates counts), gaps-present (adds
   Unretrievable line + manifest pointer). Does that meet the
   "template from structured metadata" requirement?
4. **human_completion_eligible logic**: True when gap row OR
   validator verdict != PASS. Catches both retrieval failures
   AND extraction failures (min_fields below threshold / unbound
   citation). Correct boundary for M-61 task generation?
5. **M-61 task composition**: compose_human_completion_tasks()
   filters coverage.entries by human_completion_eligible=True.
   Each task echoes doi/pmid/failure_reason/retrieval_attempt_log/
   available_artifacts + a `needs` string. JSON-serializable.
   Sufficient to hand off to the operator?
6. **Partial-count semantics**: partial_count counts non-gap rows
   with non-PASS verdicts (content exists but didn't pass
   validation). Distinct from frame_gap_count (retrieval
   failure). Correct taxonomy?
7. **Aggregate by_status**: by_status[verdict_str] → int. Ships
   in manifest so downstream dashboards can aggregate without
   iterating entries. Reasonable?
8. **Determinism**: pure function, deterministic iteration
   through outline.sections. `test_same_inputs_yield_same_coverage`
   asserts `c1 == c2`. Full `FrameCoverageReport` equality
   sufficient?
9. **to_manifest_dict JSON round-trip**: test_coverage_dict_round_trips_through_json
   does `json.dumps(d); json.loads(j)`. Proves serializability.
   Any JSON-incompatible type slipping through?
10. **Defensive fallback**: when FrameRow is missing for a
    contracted entity, emits "FrameRow missing" failure_reason
    ONLY if validator also has no reason; otherwise validator
    reason wins. Reasonable preference, or should the "missing
    row" message always dominate?
11. **No M-60 surface-language constants leak**: M-60 does NOT
    define the gap prose template — M-58 owns GAP_PROSE_MARKER
    and M-59 imports it. Correct layering?
12. **Entity-type-agnostic (rev #7)**: no branching on
    entity_type. statute + dft_primary compose identically.
    Sufficient?

## Output

Write to `outputs/codex_findings/m60_code_audit/findings.md`.

Format:
```markdown
# Codex M-60 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Structured metadata (rev #4): ...
2. retrieval_attempt_log passthrough: ...
3. Methods disclosure (rev #5): ...
4. human_completion_eligible logic: ...
5. M-61 task composition: ...
6. Partial-count semantics: ...
7. Aggregate by_status: ...
8. Determinism: ...
9. JSON round-trip: ...
10. Defensive fallback preference: ...
11. No surface-language leak: ...
12. Entity-type-agnostic: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-61
(hybrid human/licensed completion — Path B).
```

Keep under 150 lines. Full xhigh reasoning budget.
