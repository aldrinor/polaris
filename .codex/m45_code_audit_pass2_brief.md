M-45 pass-2 audit — closes pass-1 HIGH + medium-2.

## Pass-1 verdict (commit `6b2f9c9`)

Do-not-sign-off. Two findings:
- HIGH: method reporting. `_fetch_content` discarded
  `result.access_method` before returning; diagnostic artifact
  showed `method: "none"` for all attempts, couldn't drive M-45
  targeted-fix branch (your plan required "attempted backend(s)").
- Medium #2: primary rows with thin direct_quote and no
  refetchable URL fell through the `if url:` branch without any
  diagnostic entry — invisible in `refetch_diagnostics.json`.

## Pass-2 (commit `6e85312`)

**HIGH closure**: New module-level telemetry recorder
`_M45_LAST_FETCH_TELEMETRY` dict with accessor functions
`_m45_record_fetch_telemetry(url, method, reason)` and
`_m45_pop_fetch_telemetry(url)`.

`_fetch_content` now records telemetry at every return path:
- env-opt-out (PG_DISABLE_ACCESS_BYPASS=1): method=httpx_naive,
  reason=pg_disable_access_bypass=1
- AccessBypass import failed: method=httpx_naive,
  reason=access_bypass_import_failed:...
- AccessBypass timeout: method=httpx_naive,
  reason=access_bypass_timeout_90s
- AccessBypass exception: method=httpx_naive,
  reason=access_bypass_raised_...
- AccessBypass no-result: method=httpx_naive,
  reason=access_bypass_no_result
- AccessBypass success (fetch_ok): method=<result.access_method>,
  reason=""
- AccessBypass miss (fetch_miss): method=<result.access_method>,
  reason=<result.metadata.reason or "no_content">

`refetch_for_extraction_with_diagnostics` reads telemetry after
calling `_fetch_content` and surfaces method. Timeout failure_mode
classified separately from fetch_failed.

**Medium #2 closure**: builder now appends
`{failure_mode: "missing_url"}` diagnostic for primary rows with
thin direct_quote and no refetchable URL.

## Test coverage

3 new tests:
- `test_method_surfaces_from_fetch_telemetry` — recorder/popper
- `test_diag_reads_method_from_fetch_telemetry` — integration with
  mocked `_fetch_content` that sets "jina" method
- `test_diag_reads_timeout_from_fetch_telemetry` — timeout
  classification
- `test_missing_url_creates_diagnostic_entry` — M-45 pass-2 medium
  closure

14/14 tests pass in M-45 suite. 276/276 full M-series regression.

## What to audit

1. **HIGH closure**: does pass-2 now report backends per URL? Any
   missed code path where method is still recorded as "none" or
   "unknown"?
2. **Telemetry thread safety**: module-level dict without lock.
   Acceptable for sequential-per-URL path? Any concern for future
   async refactor (R-RETRIEVE-ASYNC tracked in docs/todo_list.md)?
3. **Medium #2 closure**: does missing_url appear in sink when
   primary row has thin direct_quote AND no URL? Test verifies.
4. **Failure mode taxonomy**: empty_url / exception / fetch_failed
   / thin_content / paywall_shell / timeout / builder_exception /
   missing_url — covers every branch?
5. **Pop semantics**: `_m45_pop_fetch_telemetry` removes the entry
   so stale reads don't contaminate subsequent URLs. Acceptable?

Write verdict to
`outputs/codex_findings/m45_code_audit_pass2/findings.md`.
