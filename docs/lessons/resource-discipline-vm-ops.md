# Lessons: Resource discipline, VM ops & infrastructure

Canonical home: CLAUDE.md §8.4; memory `feedback_resource_discipline_2026_05_06.md`, `project_vm_github_backup_and_login_2026_07_15.md`, `fact_polaris_core_single_stable_vm_2026_07_10.md`, `feedback_preflight_and_all_heavy_runs_on_vm_not_local_2026_06_25.md`.

Local CPU/GPU/RAM stewardship (one codex exec at a time, kill orphaned processes between iters, no heavy ML/CUDA in autonomous loops, notify on >80% RAM / >90% CPU), running ALL heavy runs incl. offline preflight on the VM (polaris-core), persistent headless login, the 24-worktree layout, and the continuous GitHub backup daemon all live canonically in CLAUDE.md §8.4 and the pointed memory files. This hub adds the mined Windows-fetch gotcha.

## On Windows, run each Crawl4AI/Playwright fetch in its own daemon thread with an isolated asyncio.run() and a join timeout

To call an async browser fetch from both sync and async contexts on Windows, give each fetch a dedicated daemon thread that calls `asyncio.run()`, and bound it with `worker.join(timeout)`. A fresh event loop is a SelectorEventLoop (Playwright/Crawl4AI need ProactorEventLoop), and `asyncio.run()` fails inside an already-running loop.

Why: The loop-type and running-loop constraints are silent on Windows and cost real debugging time; the threaded-isolation pattern is the only one that works from every calling context.

Evidence: Session 58 BUG-FETCH-R8d (2026-04-18): `asyncio.new_event_loop()` left the coroutine un-awaited (Selector vs Proactor); `asyncio.run()` from a running loop raised because Crawl4AI leaves background tasks. Daemon-thread-per-URL + `join(timeout=PG_FETCH_DEADLINE_SECONDS)` fixed a 90% fetch-failure rate, validated at 75% and 95% on two domains.

Recurrence: One concrete, hard-won Windows gotcha.
