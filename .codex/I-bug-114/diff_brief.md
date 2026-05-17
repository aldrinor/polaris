# Codex diff review — I-bug-114 (#551): hard wall-clock bound on the concurrent fetch fan-out

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (return THIS, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

You are reviewing the **diff** for issue #551 against the APPROVE'd brief
(`.codex/I-bug-114/brief.md`, brief verdict APPROVE iter 3).

## What to review

Canonical diff `.codex/I-bug-114/codex_diff.patch`
(sha256 trailer `# canonical-diff-sha256: 2462e7fa0ba3e8bb859833e84d618eb910ae756fb1ab41afee5a6ef07ee503d4`).
2 files, +224/-4:

- `src/tools/access_bypass.py` (+110/-4) — `_DETACHED_BACKEND_TASKS` set,
  `_backend_fetch_timeout`, `_backend_cleanup_grace`, `_drain_detached`,
  `_backend_failure`, `_bounded_backend` (all module-level, inserted before
  `class AccessBypass`); the 4 `concurrent_tasks.append(...)` calls in
  `fetch_with_bypass` wrapped in `_bounded_backend`.
- `tests/polaris_graph/test_access_bypass_backend_timeout.py` (NEW, 114
  lines) — 4 tests.

## Brief (APPROVE'd iter 3) — the agreed design + scope

- The fix bounds the **in-flight** concurrent fetch fan-out. `_bounded_backend`
  uses `asyncio.wait` (returns after its timeout unconditionally) — never
  `asyncio.wait_for` (which awaits the cancelled coroutine's cleanup) — so it
  returns within `PG_BACKEND_FETCH_TIMEOUT + PG_BACKEND_CLEANUP_GRACE`
  (60s + 10s) regardless of backend state.
- On timeout: `task.cancel()`, a bounded grace `asyncio.wait`, then either
  log-cancelled (task finished within grace) or detach (ref-kept +
  exception-drained via `_drain_detached`) — returns a failure `AccessResult`.
- **Explicitly out of scope** (brief §"OUT of scope", APPROVE'd): the
  `asyncio.run`-teardown residual — a detached backend awaited by
  `_cancel_all_tasks` at loop teardown after artifacts are written — is
  filed as **#552**. This PR does not claim a process-level guaranteed
  abandon; it claims the in-flight fetch is hard-bounded.

## Implementation notes for the review

- The post-`gather` result loop in `fetch_with_bypass` is unchanged:
  `_bounded_backend` always returns an `AccessResult`, so a timed-out
  backend is a non-winning candidate; the quality-scored winner selection
  and the direct-HTTP fallback are untouched.
- The two `except Exception: pass` sites are exception-retrieval drains on
  already-finished tasks (suppress asyncio "exception never retrieved"
  noise), each commented — not silent failure of real work (§9.4).
- Both timeouts are env-driven with code defaults (LAW VI).

## Test coverage

`tests/polaris_graph/test_access_bypass_backend_timeout.py`:
- `test_bounded_backend_returns_within_timeout_plus_grace` — a backend that
  hangs *during cancellation cleanup* (the class `wait_for` cannot escape)
  is bounded within `timeout + grace`.
- `test_gather_survives_one_hung_backend` — `asyncio.gather` over
  `_bounded_backend`-wrapped backends (the exact pattern `fetch_with_bypass`
  uses): one hung backend does not stall it; the fast backend's result
  survives.
- `test_bounded_backend_passes_through_a_fast_success` — happy path
  untouched.
- `test_bounded_backend_converts_a_raising_backend_to_failure` — a fast
  backend that raises → failure `AccessResult`, not a propagated exception.

Note on test 2: it exercises the bounded-`gather` pattern directly rather
than driving the full `fetch_with_bypass` (whose pre-concurrent preamble
does live network I/O — direct fetch / PDF / unpaywall — and is not
unit-testable without broad network mocking). It proves the identical
property the bug needs: a hung backend cannot freeze the concurrent
fan-out.

## Verification done

- `pytest tests/polaris_graph/test_access_bypass_backend_timeout.py` — 4 passed.
- `pytest tests/polaris_graph/test_m23_access_bypass_fixes.py` — 20 passed
  (adjacent access_bypass test, no regression).

## Files I have ALSO checked and they're clean

- `fetch_with_bypass`'s post-`gather` result loop (`isinstance(r,
  AccessResult)` filter + quality-scored winner) — unchanged, compatible
  with `_bounded_backend` always returning an `AccessResult`.
- Callers of `fetch_with_bypass` (`live_retriever.py:864`, `agents/*`,
  `frame_fetcher.py`, `orchestration/graph.py`) — all consume an
  `AccessResult`; unchanged.
- `_try_crawl4ai` / `_safe_close_crawler` — unchanged; the hard bound is
  applied at the wrapper, not inside the backend (per the APPROVE'd brief
  scope; inner-await guards are deliberately not added).

## Acceptance criteria

1. Every backend in `fetch_with_bypass`'s concurrent fan-out wrapped by
   `_bounded_backend`; hard-bounded at `PG_BACKEND_FETCH_TIMEOUT +
   PG_BACKEND_CLEANUP_GRACE` regardless of backend state.
2. A regression test proves a backend hanging during cancellation cleanup
   is bounded, and `gather` survives one hung backend.
3. `pytest` for the access_bypass tests passes; no regression.

Return the YAML verdict block only.
