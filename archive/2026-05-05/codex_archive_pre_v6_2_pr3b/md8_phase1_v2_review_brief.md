# Codex round 2 — M-D8 phase 1 v2

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md8_phase1_parallel_fetch.py`
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/parallel_fetch.py`
  - `tests/polaris_graph/test_md8_phase1_parallel_fetch.py`
  - `docs/md8_phase1_threat_model.md`
- DO NOT run Python verification scripts that print Unicode

## Round-1 findings to verify closed

You returned PARTIAL on v1 with 4 findings:

**[HIGH]** ThreadPoolExecutor `with` block waited for workers
on __exit__, defeating boundary 3's caller-latency promise.
Manual probe: 0.5s fetch with 0.05s timeout returned in 0.5s.

**v2 fix**: manage executor manually with try/finally; call
`shutdown(wait=False, cancel_futures=True)` so caller gets
control back at timeout. New test
`test_timeout_actually_returns_fast_not_just_relabels` asserts
elapsed < 0.30s.

**[MEDIUM]** Per-task deadlines anchored to shared submit_now;
under contention a task can timeout before fetcher.fetch runs.

**v2 fix**: documented in boundary 3 as intentional ("timeout
reflects operator's overall responsiveness budget, not fetch
wire time"). Operators tune max_workers + per_backend_max_concurrent
to avoid contention if they want different semantic.

**[MEDIUM]** FetcherProtocolError didn't propagate promptly
due to same executor shutdown wait.

**v2 fix**: explicit `shutdown(wait=False, cancel_futures=True)`
in the protocol-error branch before raising.

**[LOW]** Cross-backend wall-clock test flaky (0.1229s vs 0.12 cutoff).

**v2 fix**: tightened CI floor from 0.12 to 0.20.

## What v2 changed (concrete diff)

```python
# v2: manual executor management (closes HIGH)
executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=max_workers,
)
try:
    # ... existing wait+collect logic
    if protocol_error_to_raise is not None:
        for other_fut in remaining:
            other_fut.cancel()
        executor.shutdown(wait=False, cancel_futures=True)  # closes MEDIUM
        raise protocol_error_to_raise
finally:
    executor.shutdown(wait=False, cancel_futures=True)  # closes HIGH
```

## Convergence note

If round 2 finds another edge in the timeout path or
executor lifecycle, that's still convergence — fix it.

If round 2 reaches for an entirely new probe surface, flag.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-1 fix integration
- [x/ ] HIGH executor.shutdown(wait=False) returns fast at timeout
- [x/ ] MEDIUM submit-anchored deadline documented in boundary 3
- [x/ ] MEDIUM FetcherProtocolError propagates promptly
- [x/ ] LOW timing test threshold loosened

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
