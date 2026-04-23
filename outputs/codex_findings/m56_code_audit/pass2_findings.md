# Codex M-56 audit — pass 2

**Verdict**: APPROVED

## Blocker 1 — determinism
Resolution verified. `FrameRow` now separates deterministic
`retrieval_attempts` from non-deterministic `retrieval_timings`, and
`RetrievalAttempt` no longer carries `duration_ms`. That satisfies the
byte-identical payload contract: attempt logs are now equality-safe
across identical runs, while wall-clock timing remains available
outside the comparable payload. The determinism tests now prove the
intended contract directly, including
`r1.retrieval_attempts == r2.retrieval_attempts`.

## Blocker 2 — per-attempt log + URL query params
Resolution verified. `_request_with_retry` now emits one
`RetrievalAttempt` per actual HTTP request with 1-based
`attempt_index`, so retry chains are fully visible instead of being
collapsed into a source summary. Outcome naming cleanly distinguishes
intermediate retryable states from terminal errors. `_build_full_url`
also logs the concrete request URL including query params, so PubMed
attempts include `db=pubmed&id=...&retmode=xml&rettype=abstract` and
Unpaywall attempts include `email=`. This satisfies the "every HTTP
attempt visible" requirement.

## Residual concerns (if any)
None in pass-2 scope. Scoped regression check passed:
`test_m56_frame_fetcher.py` = 35/35 and
`test_m54_contract_schema.py` + `test_m55_frame_compiler.py` +
`test_m56_frame_fetcher.py` = 130/130.

## Next
Claude proceeds to M-57 (planner frame-slot integration).
