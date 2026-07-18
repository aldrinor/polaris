# Postmortem: The 4-hour autonomous freeze — a delete guard blocked every loop wake on line one

- **Date:** 2026-07-05
- **Theme:** autonomy
- **Severity:** high (~4 hours of autonomous time lost; a finished build sat un-committed)
- **Evidence:** `feedback_never_ask_permission_when_authorized_no_long_heartbeat_stall_2026_07_05.md` (operator-flagged 2026-07-05)

## What happened

During an unattended autonomous run, every loop wake began with
`rm -rf "$SC"/*_wt` to clean worktrees. Claude Code's dangerous-rm safety guard
intercepts `rm -rf` with a variable path and prompts for approval even when Bash
is allow-listed. With no one present to answer, the prompt sat unanswered and
froze each wake on its first line. The loop woke on schedule but blocked
immediately every time, for about four hours. A finished build (B1) sat
un-committed from 04:45 to 08:49 because the workflow that would have processed
it never got past the delete.

## Root cause

An approval-requiring command was placed at the very start of an unattended loop
wake. The dangerous-rm guard fires on `rm -rf` with a variable path regardless of
the Bash allow-list, so the wake could never advance past line one without a
human. The design also let a completed workflow sit unprocessed: completion did
not equal committed, so a finished build had no path to durability while the wake
was blocked.

## Contributing factors

- The guard-tripping delete was the first command of the wake, so a single
  unanswerable prompt blocked the entire wake rather than a later, skippable step.
- The build+gate workflow did not self-commit at the end, so a finished build
  depended on later steps that never ran.
- The heartbeat was long enough that a blocked wake could sit for hours before
  anything noticed.

## Lessons (promoted to)

- Never put `rm -rf` with a variable path — or any approval-requiring,
  guard-tripping command — at the start of an autonomous loop wake or anywhere
  unattended. Put only safe, allow-listed commands at a wake's start. Use
  `git worktree remove --force` + prune for worktree cleanup, never a manual
  `rm`.
- Make each build+gate workflow SELF-COMMIT at the end so completion equals
  committed, and keep a tight heartbeat (<= 300s) as a backstop. A finished
  workflow must never sit unprocessed, and a wake must never block on a delete
  guard.
- Promoted to memory:
  `feedback_never_ask_permission_when_authorized_no_long_heartbeat_stall_2026_07_05.md`.
