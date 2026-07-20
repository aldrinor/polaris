---
name: background-task-lifecycle-rule
description: "Standing rule — never leave a background task running loose; every task I start, I track to completion and end myself"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**Standing rule (operator, 2026-07-20): stay inside the agentic infra, and NEVER leave a background task running untracked.** If I launch anything in the background, I own its full lifecycle — I watch it to completion and I stop it myself (TaskStop) the moment it is done. No fire-and-forget.

**Why:** 24 orphaned background tasks piled up in the operator's panel over Jul 18-19 (long codex runs + `while`/`until` watcher loops launched with `run_in_background` that never exited). After a session resume the task manager lost its handle to them, so neither I nor the panel could stop them — they became permanent display ghosts. That looks like runaway/drifting work to a blind operator and is exactly the mess the infra exists to prevent.

**MINIMIZE COUNT (added 2026-07-20 after a repeat):** the failure recurred not as orphans but as ~11 short "watchdog" background tasks I spawned to poll long jobs — each self-terminated (rule kept) but their finished entries piled up in the operator's panel (spirit broken). **Do NOT spawn a chain of watchdog/`sleep` polling tasks.** Harness-tracked background tasks (Bash `run_in_background`, Workflow, async agents) already send an automatic completion notification — WAIT for that, don't poll. If you genuinely must watch progress, use ONE `Monitor` with a real exit condition, never a series of one-shot `sleep N; check` tasks. Target: near-zero background tasks alive or lingering at any time.

**How to apply — every time:**
1. Prefer foreground Bash (blocks, returns, done) for anything that finishes quickly.
2. If a task MUST run in the background, it has to be self-terminating: an `until`/`grep -q` guard that exits on the condition, never an unbounded `tail -f` / `while true` / bare `sleep` loop left armed.
3. Track it — Monitor for streamed events, or the completion notification — and explicitly TaskStop it when its purpose is served. Do not move on leaving it "running".
4. Never end a session with background tasks still open. Sweep and stop them first.
5. Multi-step orchestration goes through the govkit Workflow/agent path, not a pile of loose background shells.

See [[governance-kit-operating-rule]], [[baseline-next-step]].
