# Per-commit Codex brief — `3bac322` (BACKFILL)

**Commit:** `3bac322 PL: v6.2 backend coverage — queue.actors (8 tests, Phase 0 stub contract)`
**Format:** v2 minimal
**Files changed (1):** `tests/v6/test_actors.py` (new, 80 lines, 8 tests)
**Brief filed:** retroactively on 2026-05-01 — closes cycle-4 P2.2 + cycle-5 P3.3 (chain break).

## What this commit did

`src/polaris_v6/queue/actors.py` was uncovered. Pinned the Phase 0 contract of the 2 dramatiq actors (`enqueue_research_run`, `cancel_research_run`) so the Phase 1 bridge (when `adapters/retrieval_bridge.py` replaces the noop) cannot silently change the public interface.

8 tests covered:
- `enqueue` echoes payload + reports `status='completed'`
- `enqueue` handles empty payload
- `ENQUEUE_MAX_RETRIES == 3`
- `@dramatiq.actor` decoration carries `max_retries=3` + `time_limit=30 * 60 * 1000`
- `cancel` returns `status='cancel_requested'`
- `cancel` actor `max_retries=0` (fire-and-forget)
- Both actors have dramatiq primitives (`.send` + `.fn`)
- Constants match documented values

## What this brief MISSED at the time (and what cycle-4 caught)

**The module-level `get_broker(use_stub=True)` call shipped in this commit was a STATE-LEAK BUG.** It decorated the dramatiq `@actor` decorators against a StubBroker that the `acceptance/test_dramatiq_acceptance.py` fixture's separate StubBroker couldn't reach → `QueueNotFound: default` regression. My local "8/8 PASS in isolation" verification missed it. Cycle-4 audit (subagent ID `a2faf9ed60ad4b097`) reproduced it with the full suite + caught it.

Fix landed as F-13 in commit `15622b2` (3 layers: new `tests/v6/conftest.py` does module-level broker setup; `test_actors.py` drops its module-level call; acceptance fixture uses `dramatiq.get_broker()` instead of creating a new broker; `test_broker.py` autouse save+restore).

## Lessons documented in memory

- `feedback_run_full_test_suite_not_just_new_file.md` — verify with `pytest <suite>/`, not `pytest <new-file>` in isolation.

## Cross-review

This brief is BACKFILL. The original commit shipped without one because the autoloop wasn't yet enforcing per-commit briefs at this point in the session. Cycle-4 P2.2 + cycle-5 P3.3 both flagged the absence; this file closes the chain break. No cross-review needed for the original commit — it was superseded by F-13's correction commit.
