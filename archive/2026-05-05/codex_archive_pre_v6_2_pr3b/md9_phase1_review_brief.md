M-D9 phase 1 review (commit d672558).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D milestone M-D9 (regression lab bootstrap). Builds on
freshly-locked M-D11 phase 1 (commit 6c2f17f, model-pin v4
schema) and M-D1 (PrecisionMetrics). Phase 2 (BEAT-BOTH
dimension scoring) deferred.

This commit ships **bootstrap regression-lab**: pin diff +
induction-precision diff + manifest-flip diff, with CI exit-
code semantics (GREEN/YELLOW=0, RED=1).

## Files

`src/polaris_graph/audit_ir/regression_lab.py`:
  - RegressionInputs: ModelPin + PrecisionMetrics + optional
    pipeline manifest (dict[str, Any])
  - RegressionVerdict enum: GREEN | YELLOW | RED
  - PinDriftField: per-field config drift with severity
    "config" | "env" | "schema"
  - InductionDriftMetric: 5 metrics, direction-aware
    regression flag (drop=regression for precision/recall;
    rise=regression for silent_disagreement, operator_review)
  - ManifestDriftField: abort_status, release_allowed,
    sections_verified→0
  - diff_regression(baseline, current) -> RegressionReport
  - report_to_exit_code: RED→1, else 0
  - 4 env-overridable tolerances (LAW VI):
    PG_REGRESSION_PRECISION_TOLERANCE (default 0.02),
    PG_REGRESSION_RECALL_TOLERANCE (default 0.05),
    PG_REGRESSION_SILENT_DISAGREEMENT_TOLERANCE (default 0.02),
    PG_REGRESSION_OPERATOR_REVIEW_TOLERANCE (default 0.10)
  - Per-key env_snapshot diff (one PinDriftField per changed key)
  - pin_schema_version mismatch ALWAYS RED

`tests/polaris_graph/test_md9_regression_lab.py`: 25 tests
covering GREEN, RED, YELLOW, exit codes, env tolerance overrides,
per-key env drift, None-vs-empty propagation, manifest skip.

## Your job

GREEN / PARTIAL / DISAGREE.

1. **Verdict logic correctness**: GREEN = nothing drifted;
   YELLOW = drift but no regression; RED = induction
   regression OR manifest regression OR schema mismatch. Are
   these the right boundaries for a CI gate?

2. **Direction semantics**: precision/abstain_precision/
   abstain_recall: drop = regression. silent_disagreement /
   operator_review_load: rise = regression. Any reversed?

3. **Manifest drift logic**:
   - abort_status flip from "success" → anything else: RED
   - abort_status anything → "success": YELLOW (improvement)
   - release_allowed True → False: RED
   - sections_verified > 0 → 0: RED even if abort_status held
   Is this complete or are there other manifest signals
   (e.g. budget overshoot, gate flip in v34_runner)?

4. **YELLOW exit code = 0**: configuration drift without
   regression doesn't block CI. Right call, or should YELLOW
   block too?

5. **Per-key env drift**: env_snapshot diff emits one
   PinDriftField per changed key (severity "env"), not one
   monolithic dict diff. Will this be readable for the
   reviewer if 20+ env vars change in one PR?

6. **Tolerance defaults**: 0.02 (precision), 0.05 (recall),
   0.02 (silent disagreement), 0.10 (operator review).
   Conservative enough for a CI gate, or too tight / too loose?

7. **Coupling**: regression_lab imports model_pin and
   precision_metrics directly. Reasonable cut, or should
   inputs be a more abstract shape?

8. **Phase 2 readiness**: with phase 1 bootstrap shipping, is
   the API stable enough that BEAT-BOTH dimension scoring
   layers on cleanly later?

## Output

`outputs/codex_findings/md9_phase1_review/findings.md`:

```markdown
# Codex review of M-D9 phase 1 (commit d672558)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [verdict logic concern, if any]
- [direction-semantics concern, if any]
- [manifest-drift gap, if any]
- [YELLOW vs RED gating concern, if any]
- [tolerance default concern, if any]
- [coupling issue, if any]
- [phase-2 readiness concern, if any]

## Final word
GREEN to lock M-D9 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
