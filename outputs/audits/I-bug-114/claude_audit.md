# Claude architect audit — I-bug-114 (#551)

**Issue:** pipeline-A retrieval hangs when a fetch backend never returns.
**Branch:** `bot/I-bug-114-retrieval-timeout` off `polaris`.
**Canonical diff sha256:** `2462e7fa0ba3e8bb859833e84d618eb910ae756fb1ab41afee5a6ef07ee503d4`

## What shipped

| File | Change |
|---|---|
| `src/tools/access_bypass.py` | +110/-4 — `_bounded_backend` + 3 helpers; the 4 concurrent backends wrapped |
| `tests/polaris_graph/test_access_bypass_backend_timeout.py` | NEW — 4 tests |

## Root cause → fix

`AccessBypass.fetch_with_bypass` ran the per-backend coroutines under
`asyncio.gather` with **no per-backend wall-clock**. One backend wedged in a
Playwright op (the #514 rehearsal's `policy` run hit `federalregister.gov` →
`unblock.federalregister.gov` and stalled ~30 min) froze the whole `gather`.

`_bounded_backend(label, coro, url)` wraps each backend:
- It uses **`asyncio.wait({task}, timeout=T)`** — which returns after `T`
  **unconditionally** — not `asyncio.wait_for`, which awaits the cancelled
  coroutine's cleanup and therefore cannot escape a hung `__aexit__`.
- On timeout it `task.cancel()`s, then allows a **bounded** cleanup grace
  via a second `asyncio.wait`; if cleanup also exceeds the grace it detaches
  the task (strong ref kept in `_DETACHED_BACKEND_TASKS`, exception drained
  by the `_drain_detached` done-callback) and returns a failure
  `AccessResult`.
- Net: `_bounded_backend` returns within `PG_BACKEND_FETCH_TIMEOUT +
  PG_BACKEND_CLEANUP_GRACE` (60s + 10s defaults) regardless of backend state.

The post-`gather` result loop is unchanged: `_bounded_backend` always
returns an `AccessResult`, so a timed-out backend is simply a non-winning
candidate; the quality-scored winner selection and the direct-HTTP fallback
are untouched.

## Codex iteration trail (brief)

- iter 1: `wait_for` awaits cancellation cleanup → no hard abandon. Accepted
  → switched to `asyncio.wait`.
- iter 2: a detached task on the retrieval loop is still awaited by
  `asyncio.run`'s `_cancel_all_tasks` at teardown. Accepted → brief scoped
  explicitly to the **in-flight** fetch; the teardown residual filed as #552.
- iter 3: **APPROVE** (zero P0/P1/P2).

## Scope honesty

This PR bounds the **in-flight** concurrent fetch — the demo-fatal symptom
(retrieval freezing mid-run, the pipeline never reaching a verdict). A
backend whose cancellation cleanup itself wedges is detached; in the
theoretical worst case that delays `asyncio.run` *teardown* **after** all
artifacts are written. That residual is honestly out of scope here and
tracked as **#552** (it needs daemon-thread / subprocess isolation — a
concurrency-model redesign). The brief and the code comments state this
plainly; nothing overclaims "process-level guaranteed abandon".

## Invariant / hygiene check

- LAW VI: both timeouts come from env (`PG_BACKEND_FETCH_TIMEOUT`,
  `PG_BACKEND_CLEANUP_GRACE`) with code defaults — no magic numbers.
- §9.4: the two `except Exception: pass` sites are exception-*retrieval*
  drains on already-finished tasks (best-effort, to suppress asyncio's
  "exception never retrieved" noise) — not silent failure of real work;
  each is commented.
- No existing code path's behaviour changed for the happy path — a fast
  backend is passed through untouched (`test_..._passes_through_a_fast_success`).

## Verification

`pytest tests/polaris_graph/test_access_bypass_backend_timeout.py` — 4
passed (hard bound incl. hang-during-cancellation; gather survives one hung
backend; fast pass-through; raising backend → failure result).
`pytest tests/polaris_graph/test_m23_access_bypass_fixes.py` — 20 passed
(adjacent regression check, clean).

## Verdict

Ready for Codex diff review. The in-flight retrieval hang is closed by a
hard `asyncio.wait`-based bound, proven by a test that models the exact
cancellation-cleanup-hang class.
