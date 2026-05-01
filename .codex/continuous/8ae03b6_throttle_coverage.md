# Per-commit Codex brief — `8ae03b6`

**Commit:** `8ae03b6 PL: v6.2 backend coverage — ThrottleMiddleware (7 tests)`
**Format:** v2 minimal
**Files changed (1):** `tests/v6/test_throttle_middleware.py` (new, 104 lines, 7 tests)

## What this commit does

`src/polaris_v6/queue/middleware/throttle.py` was an uncovered file (~50 LOC). Adds 7 tests exercising the per-actor failure-ratio backoff:

1. **No backoff below threshold** — 4 ok + 1 fail (ratio 0.2) on threshold 0.5 sleeps zero.
2. **Backoff at/above threshold** — 0.5 ratio with 150ms backoff_ms produces ~150ms wall (verified ≥140ms, <250ms).
3. **Per-actor isolation** — failures on X don't throttle Y.
4. **Window roll-out** — old failures evict from the deque so recovery → no backoff.
5. **Parametric threshold sweep** — at 0.5 ratio: thresholds 0.25/0.50 backoff, 0.75 doesn't.

Uses public `after_process_message()` hook same as Dramatiq production. Synthetic Message via MagicMock — no real broker. `pytest.importorskip("dramatiq")` guards env.

All 7 PASS in 3.71s. Brings v6 test count from 209 to 216.

## Acceptance criteria

1. **Real timing measurement.** `time.monotonic()` deltas around the actual middleware invocation, not asserting on internal state.
2. **No race-prone timing.** Allowed slack: 50ms below "no backoff" threshold, 110-250ms band for the ~150ms backoff. Wide enough for CI variance, narrow enough to fail on a 2x backoff regression.
3. **Per-actor isolation actually exercised** — distinct actor_name strings; assertion on the second actor's wall-clock proves dict-keying isn't shared.
4. **Window-evict semantics** correctly modeled — push enough successes to flush the failure window, then assert recovery.
5. **No mocking of dramatiq itself** — only the `Message` and `Broker` arg types via MagicMock, since the middleware doesn't introspect them. Real Dramatiq.Middleware base class loaded from import.

## Codex focus

- **P1:** The 110-250ms band on the backoff test is timing-sensitive. On a heavily-loaded CI runner (no real-time scheduling), `time.sleep(0.15)` could overshoot to 300+ms. Should we widen to 110-400ms or use mock-time?
- **P2:** No test for thread-safety. The middleware uses `threading.Lock`; we don't assert correctness under concurrent `after_process_message` calls. Future enhancement.
- **P2:** `StickyConnectionMiddleware` (sibling file) has a `try: ... except: pass` at line 33 that violates CLAUDE.md §9.4 "no silent failure". Out of scope for this commit but worth a follow-up.

## Cross-review

Lands at `outputs/audits/continuous/8ae03b6/cross_review.md`. Counter at **2/5** (new batch since 909eb4c trigger).
