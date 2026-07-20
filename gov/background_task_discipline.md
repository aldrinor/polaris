# Background-task discipline (govkit operating rule)

The operator watches a "running tasks" panel. Loose or piled-up background tasks read as runaway
work and erode trust. Two real failures produced this rule:
1. **24 resume-orphans** — long codex/`while`-loop tasks launched with `run_in_background` that never
   exited; a session resume dropped the task-manager handle, so they became permanent panel ghosts.
2. **~11 watchdog pile-up** — a chain of one-shot `sleep N; check` background tasks spawned to poll
   long jobs. Each self-terminated (letter of the rule kept) but their finished entries cluttered the
   panel (spirit broken).

## Rules — apply every time, no exceptions
1. **Wait for the automatic completion notification; do NOT poll.** Every harness-tracked background
   task (Bash `run_in_background`, `Workflow`, async agents) sends a `<task-notification>` when it
   finishes. That IS the signal. Waiting is free and correct.
2. **NO watchdog chains.** Never spawn a series of `sleep N; <check>` background tasks to monitor
   progress. That is the exact pattern that piled up 11 entries. One long job → wait for its one
   notification.
3. **At most ONE `Monitor`, and only with a real exit condition** (a log line, a status flip), if you
   genuinely need streamed progress. Never an unbounded poll loop.
4. **Every background task must be self-terminating** — an `until`/`grep -q` guard that exits on the
   condition, never a bare `while true` / `tail -f` / bare `sleep` left armed.
5. **Prefer foreground** for anything that finishes quickly (blocks, returns, done — no panel entry lingers).
6. **`TaskStop` anything still live the moment its purpose is served,** and never end a session with
   background tasks open. Sweep first.
7. **Target: near-zero background tasks alive or lingering at any time.**

## Honest limit
There is no CLI to wrap for a hard machine-block on harness background spawns (unlike the `gh` and
`opmsg` guards). Enforcement is this version-controlled discipline plus the auto-loaded memory
[[background-task-lifecycle-rule]]. The discipline is the guard here — follow it by default.
