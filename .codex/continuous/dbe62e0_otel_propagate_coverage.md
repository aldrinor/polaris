# Per-commit Codex brief — `dbe62e0`

**Commit:** `dbe62e0 PL: v6.2 backend coverage — OtelPropagateMiddleware (7 tests)`
**Format:** v2 minimal
**Files changed (1):** `tests/v6/test_otel_propagate_middleware.py` (new, 134 lines, 7 tests)

## What this commit does

`src/polaris_v6/queue/middleware/otel_propagate.py` was uncovered. This is bespoke substrate (no upstream `opentelemetry-instrumentation-dramatiq` package exists on PyPI per Phase 0 verification) that keeps OpenTelemetry trace context across Dramatiq enqueue → execute boundary.

Adds 7 tests:
1. `before_enqueue` injects non-empty W3C-style carrier when span active.
2. `before_enqueue` no-op (or empty carrier) when no span active.
3. `before_process_message` attaches a context token under `_otel_token`.
4. `before_process_message` no-op when no carrier present.
5. `after_process_message` detaches the token (cleanup invariant).
6. `after_process_message` no-op when no token present.
7. Full round-trip preserves the carrier dict identity through extract.

**Critical fixture detail**: `autouse` fixture installs a real `TracerProvider`. Without it, OpenTelemetry's NoOp tracer means `propagate.inject` writes nothing, and 4 of the 7 tests fail with empty-carrier KeyError. Fixed during initial run.

`pytest.importorskip` guards: dramatiq, opentelemetry, opentelemetry.sdk.

All 7 PASS in 1.61s. Brings v6 test count from 221 to 228.

## Acceptance criteria

1. **Real OTEL invocation** (not mocked) — `propagate.inject` and `propagate.extract` are called inside an actual span context, exercising the production code path.
2. **TracerProvider fixture is autouse** so subsequent tests in the file can rely on context propagation. Documented in fixture docstring.
3. **No assertion on carrier contents** beyond "non-empty dict" — keeps tests stable across W3C TraceContext format changes.
4. **Token leakage prevented** — every test that creates a token explicitly calls `after_process_message` to detach. Test 5 asserts the cleanup deterministically.
5. **No double-propagator setup** — uses the global tracer provider, doesn't shim it per-test.

## Codex focus

- **P1:** The autouse fixture installs a TracerProvider GLOBALLY for the test session. This could pollute other test files in `tests/v6/` if they assume the NoOp default. Verify by running `pytest tests/v6/` after this lands and checking nothing flakes.
- **P1:** Test 7 (round-trip) only verifies the carrier dict survives — does NOT verify the context object identity (parent-child span IDs). Should we extract the trace_id from both sides and assert match?
- **P2:** No test for the EXCEPTION case where opentelemetry IS installed but `propagate.inject` raises. The middleware silently catches `ImportError` only, not other exceptions; if `inject` raises a runtime error, the whole queue could fail. Should we test that path?

## Cross-review

Lands at `outputs/audits/continuous/dbe62e0/cross_review.md`. Counter at **4/5** in the new batch — pausing substrate until cycle-2 adversarial subagent (still running on the prior 5-commit batch) returns. Will resume after processing that audit + cross-review.
