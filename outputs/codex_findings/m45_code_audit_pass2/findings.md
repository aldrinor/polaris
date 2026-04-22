# M-45 Pass-2 Code Audit Findings

Verdict: SIGN OFF.

No HIGH or Medium findings remain for the two pass-1 blockers.

## Audit Results

1. HIGH closure: closed. `_fetch_content` now records method telemetry on the observed return paths, and `refetch_for_extraction_with_diagnostics()` pops that telemetry into the diagnostic entry. Successful and miss paths preserve `result.access_method`; fallback paths report `httpx_naive`; timeout is separately classified as `failure_mode: "timeout"` instead of being collapsed to `fetch_failed`.

2. Method `"none"` / `"unknown"` exposure: acceptable. `"none"` remains the default for no-attempt cases (`empty_url`, `missing_url`) and for builder-level exceptions that happen before a diagnostic fetch can report a backend. `"unknown"` is only used if an AccessBypass result lacks `access_method`, which is a defensive fallback rather than the pass-1 regression.

3. Telemetry thread safety: acceptable for the current sequential-per-URL path. The module-level dict is not safe for concurrent refetches of the same URL because record/pop is keyed only by URL and has no lock or request id. That is not a current blocker, but R-RETRIEVE-ASYNC should replace this with per-call returned telemetry, a request-scoped object, or a locked/request-id keyed recorder before concurrent refetching is introduced.

4. Medium #2 closure: closed. In `build_trial_summary_and_timeline_from_evidence()`, primary rows with `direct_quote` shorter than 100 chars and no `source_url`/`url` now append a diagnostic entry with `attempted: false` and `failure_mode: "missing_url"`.

5. Failure-mode taxonomy: covers the current diagnostic branches: `empty_url`, `exception`, `fetch_failed`, `thin_content`, `paywall_shell`, `timeout`, `builder_exception`, and `missing_url`. Eligible rows clear failure mode except the timeout-fallback case can still carry `timeout` if AccessBypass timed out before naive fallback produced usable content; that is diagnostically defensible, but downstream consumers should prefer `eligible` for eligibility decisions.

6. Pop semantics: acceptable. `_m45_pop_fetch_telemetry()` removes the consumed entry and prevents stale method reads across sequential diagnostic calls.

## Verification

Ran:

```powershell
python -m pytest tests\polaris_graph\test_m45_refetch_diagnostics.py -q
```

Result: 15 passed. Pytest emitted a cache warning because `.pytest_cache` was not writable, but the tests passed.
