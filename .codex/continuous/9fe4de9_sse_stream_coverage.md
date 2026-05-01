# Per-commit Codex brief — `9fe4de9`

**Commit:** `9fe4de9 PL: v6.2 backend coverage — SSE /stream endpoint (6 tests)`
**Format:** v2 minimal
**Files changed (1):** `tests/v6/test_api_stream.py` (new, 104 lines, 6 tests)

## What this commit does

`src/polaris_v6/api/stream.py` was a Phase 0 stub (5 hardcoded SSE events) with NO test coverage. This commit pins the contract until pipeline-A bridge replaces the stub in Phase 1:

- **Order assertion** — exactly 5 events in the documented sequence: `scope_decision → retrieval_progress → verifier_verdict → section_complete → run_complete`.
- **run_id propagation** — every event payload carries the run_id passed in the URL (no leakage between concurrent requests; uses a special-character runId to expose any naive string substitution).
- **Per-event payload shape** — scope_decision has verdict + reason; retrieval_progress has sources_found + tier_breakdown {T1,T2,T3}; verifier_verdict has section + local_pass + global_pass; run_complete has status="completed".

Wire-format helper `_parse_sse_events` normalizes `\r\n` → `\n` because `sse_starlette.EventSourceResponse` emits CRLF line endings. Probed live then fixed parser when test/raw output mismatched.

All 6 PASS in 3.23s. v6 test count: 203 → 209.

## Acceptance criteria

1. **Tests use real FastAPI app**, not a hand-rolled mock. `from polaris_v6.api.app import create_app` + `TestClient(create_app())` — same pattern as the other 27 v6 API tests.
2. **No mock of sse_starlette.** The endpoint's SSE serialization is exercised end-to-end; if sse_starlette ever changes wire format, tests detect it.
3. **Wire-format parser handles real CRLF.** Initial assertion failed because parser split on `\n\n` while server emits `\r\n\r\n`; fix preserves robustness for either line ending.
4. **No flaky timing assertions.** The endpoint sleeps 0.05s between events; tests don't assert on timing — only on order + content. CI hardware variance can't flake.
5. **Pins contract for Phase 1 swap.** When pipeline-A bridge replaces the stub, these tests will fail unless the new implementation maintains the same event names + payload shapes — explicit by construction.

## Codex focus

- **P1:** Should we test the case where the run_id contains URL-unsafe characters that need encoding? Currently we test underscores + dashes; not slashes or `?`. Possibly out of scope for stub-stage tests.
- **P2:** No test asserts that the response stream CLOSES after the 5th event. SSE clients sometimes hang on missing close. Worth adding `assert response.is_closed` or similar.
- **P3:** The `_parse_sse_events` helper could become a fixture if reused elsewhere; for now it lives inline.

## Cross-review

Lands at `outputs/audits/continuous/9fe4de9/cross_review.md`. Counter at **1/5** (new batch since 909eb4c trigger; cycle-2 subagent currently running).
