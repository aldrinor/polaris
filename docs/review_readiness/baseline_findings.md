# Baseline findings (Phase 0-A) — honest ground-truth

Captured by exercising the pipeline read-only at commit `d76a0ea`. These are the real issues the
baseline surfaced *before* any refactor — they become prerequisites and work items.

## Config inventory (Phase 1 / S1 seed)
- Runtime config source: `/workspace/POLARIS/.env` — **694 variables, 352 `PG_*` flags, 56 secret-shaped**
  (values never recorded in plaintext; secrets stored as digests in the git-ignored baseline).
- This is the exact key set that Phase 1 config governance must classify + own before migration.

## Test suite (see `baseline_test_state.md`)
- **16,501 tests**, **23 collection errors**, deterministic (not flaky). Root cause: `registry.py`
  filesystem validation **at import time** that raises when historical output dirs are absent.

## Acceptance harness — NOT a trustworthy oracle yet (verified by codex)
Ran the two live scenarios; the run exposed three real issues **and** a strategic gap.

1. **Portability crash** — the harness writes to a hardcoded `/workspace/outline_agent_wt/` path that
   does not exist here → `FileNotFoundError`, exit 1. Also: exit status is tied to the result-file
   write, not to the semantic assertions.
2. **Playwright browser not installed** — every crawl4ai browser fetch failed; circuit breaker opened;
   pipeline degraded gracefully (fell back, still retrieved evidence).
3. **Positive control FAILED** — the THIN scenario is designed so a known coverage gap (long-term CV
   safety, uncovered by an efficacy-only seed) is detected and fires a `search_more_evidence` call.
   Instead the checklist returned "no grounded deficiencies" and fired **0 searches**. The negative
   control (SATURATED) recorded 0 searches too — which, given the positive control also reads 0, may be
   **vacuous** (a globally-disabled/unreachable search path or broken instrumentation would produce the
   same 0/0). Cause is currently indeterminate (real gap-detection bug vs. instrumentation vs. test
   premise vs. browserless degradation).

### Strategic gap (codex, on the plan itself)
A **live web+model harness cannot be the arbiter of a "byte-identical" refactor** — live retrieval and
generation are mutable. It is a smoke/acceptance test only. A **deterministic regression oracle**
(frozen inputs/responses, pinned model/tool/browser versions, byte-level artifact diff) is required
before Phase 1 config changes can be verified as behavior-preserving. This updates plan v4.

## Immediate work items (before Phase 1)
1. Diagnose the search-not-firing: instrumentation/counter, THIN seed premise, gap-detection logic,
   and any env flag that globally gates `search_more_evidence`.
2. Make harness output-path portable + decouple exit status from the result-file write.
3. Install the Playwright-matched Chromium; re-run repeatedly to expose nondeterminism.
4. Build the deterministic regression oracle.
