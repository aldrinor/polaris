M-60 code audit pass 2 — verify blocker+medium fixes.

**Skip git status.** Two files only.

## Context

Pass-1 verdict: CONDITIONAL-blockers. Commit `3efa0d5` addresses:

- Blocker: compose_human_completion_tasks() now emits
  required_fields, min_fields_for_completion, entity_type, and a
  failure-specific `needs` string via _compose_task_needs.
- Medium: defensive missing-FrameRow path is now classified as
  `pipeline_fault` (distinct from frame_gap_unrecoverable), with
  is_pipeline_fault=True, human_completion_eligible=False,
  pipeline-diagnosis leading the failure_reason, and a separate
  aggregate pipeline_fault_count surfaced in Methods disclosure.
- Nit 1: dead `slot.is_partial` branch removed.
- Nit 2: TestPartialOnlyDisclosure added.

Total tests: M-54 54 + M-55 41 + M-56 35 + M-57 20 + M-58 44 +
M-59 20 + M-60 19 = 233/233 pass.

## What to verify

Files (commit `3efa0d5`):

1. `src/polaris_graph/generator/frame_manifest.py`
2. `tests/polaris_graph/test_m60_frame_manifest.py`

Check:

1. **Blocker resolution** — compose_human_completion_tasks() now
   emits required_fields + min_fields_for_completion + failure-
   specific needs guidance per status. Is the `_compose_task_needs`
   taxonomy (RETRIEVAL/EXTRACTION/CITATION/GAP-LANGUAGE/VALIDATION)
   appropriate, or did I miss a status?
2. **Medium resolution** — pipeline-fault path is now distinct:
   provenance_class="pipeline_fault", is_pipeline_fault=True,
   human_completion_eligible=False, pipeline_fault_count
   aggregated, Methods disclosure surfaces the count separately.
   Sufficient, or any residual concerns?
3. **Nit fixes** — dead is_partial branch gone; partial-only
   disclosure test added.
4. **New adversarial attempts** — use your full xhigh budget.
   Specifically:
   - Can a pipeline-fault entry still end up human-routed by
     any code path?
   - Is the pipeline_fault provenance class consistently
     distinct from frame_gap_unrecoverable everywhere?
   - Does the failure-specific needs guidance correctly route
     CITATION/GAP-LANGUAGE gaps to engineers rather than
     curators?
   - Any JSON-serialization issue with the new fields
     (required_fields is list, min_fields is int — both fine,
     but verify)?
5. **Regression** — 233/233 pass in the scoped V30 suite.

## Output

Write to
`outputs/codex_findings/m60_code_audit/pass2_findings.md`.

Format:
```markdown
# Codex M-60 audit — pass 2

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Blocker — M-61 task payload
<resolution verified / still open>

## Medium — pipeline-fault path
<resolution verified / still open>

## Nits
<resolution verified>

## New adversarial attempts
<list each input, parser/composer behavior>

## Residual concerns
<anything>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-61.
```

Keep under 100 lines.
