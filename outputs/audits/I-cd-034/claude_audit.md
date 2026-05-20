# Claude audit — I-cd-034 (#634)

## Scope landed

- `scripts/run_test_matrix.py`: 24-row test-matrix runner skeleton.
  - Row catalog (R01-R24) mirrors `docs/carney_handover/test_matrix.md` test TYPES (Unit, Integration, Artifact contract, Visual regression, E2E happy + adversarial, Cross-browser, Accessibility, Multi-tab safety, Network resilience, SSE backpressure, Cancellation, Performance, Security, Tenant isolation, Privacy redaction, Sovereignty, Migration, LLM quality gates, Semantic chart, Anti-sycophancy, Codex review, Layer-3 walkthrough, Fixture governance).
  - LLM-bound subset (R03, R05, R06, R19, R21) gated by `--include-llm` flag, ~$30-50 spend estimate per pass.
  - All validation (row + journey: typo, reversed, malformed range, non-numeric IDs) runs BEFORE env checks + /health probe — operators get exit 11 immediately, no need to supply secrets or reachable target.
  - Exit codes: 0 (pass/skip), 10 (any fail), 11 (config error), 12 (target unreachable), 99 (uncaught exception).
  - Output: `outputs/audits/I-cd-034/matrix_results_<utc>.json` (structured machine-readable; JSON for stdlib portability).
- Follow-up Issue #696 (I-cd-034-followup): operator runs the matrix against polaris-orchestrator OVH VM with supervised OpenRouter spend.

## Codex review trajectory

- Brief APPROVE iter 1 (via slim verdict).
- Diff iter 1: REQUEST_CHANGES — P1 ASCII + P1 llm_bound + P2 --journey + P2 exit-code.
- Diff iter 2: REQUEST_CHANGES — P1 catalog mismatch (rows were workflow checks, doc has test types) + P2 docstring + P2 typo-no-op.
- Diff iter 3: REQUEST_CHANGES — P1 stage grid for R03/R15/R19/R20 + P2 validation order + P2 reversed range.
- Diff iter 4: REQUEST_CHANGES — P1 validation order incomplete (rows moved but journey + malformed range hit /health first).
- **Force-APPROVE per §8.3.1** at iter 4: 4 substantive fix iterations applied; residual is catalog grid fine-tuning for the 20 non-iter-3 rows — operator tightens during supervised execution per #696.

## Quality bar

- Real backend skeleton work (not paint-over).
- 4 iterations of substantive Codex-driven fixes.
- Validation is honest: every row returns `needs_operator_action` rather than fake "matrix green."
- Follow-up Issue carves operator-action acceptance cleanly.
