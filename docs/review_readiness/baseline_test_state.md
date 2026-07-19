# Baseline — test suite state (Phase 0-A, read-only)

**Commit:** d76a0ea (branch gate-inversion) · **Python:** 3.11.10 · **pytest:** 8.4.1

## Collection
- **16,501 tests collected** (corrects the audit's "1,082" — that was a file/subset count).
- **23 modules FAIL to collect.**

### Root cause of collection failures
`src/polaris_graph/audit_ir/registry.py:132` runs `_RUNS = _build_runs()` **at import time**, which
validates that historical run-output directories exist and raises `RegistryError` when they don't
(e.g. `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm`, absent in a clean
checkout). Any module importing `registry`/`live_server` then fails to import.
→ **Import-time filesystem validation that raises = non-portability anti-pattern.** Fix: make the
registry lazy (build on first use, not at import) and fail soft. (Work item, Phase 0/1.)
Plus 1 playwright "browser not installed" error (test-infra: needs `playwright install`).

## Execution — clean subset (`tests/unit`, `-m "not slow and not api and not live"`, continue-on-collection-errors)
| Run | passed | failed | errors | wall |
|-----|--------|--------|--------|------|
| 1   | 1343   | 104    | 103    | 226.8s |
| 2   | 1343   | 104    | 103    | 226.1s |

- **DETERMINISTIC** — identical across both runs → **not flaky**; failures are real, reproducible debt.
- Pass rate on this subset ≈ **86.6%** (1343 / 1550).
- `errors` (103) are mostly environment/import (playwright browser, registry chain) — setup-fixable.
- `failures` (104) are assertion mismatches — real test/code drift, needs triage.

## Honest implication for Telus
The suite is **NOT green out-of-the-box**. Presenting "16,501 tests" without saying they don't all
pass would fail the first `pytest`. The fix path is clear (deterministic, not flaky): (1) make
`registry` import lazy, (2) `playwright install` in CI, (3) triage the 104 assertion failures.
This is why the plan runs the baseline before claiming anything.
