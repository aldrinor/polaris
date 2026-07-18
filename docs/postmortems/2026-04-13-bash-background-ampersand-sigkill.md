# Postmortem: Backgrounding a long run with `&` orphaned it and it was SIGKILLed

- **Date:** 2026-04-13
- **Theme:** resource / VM-ops
- **Severity:** high (~10 hours lost across two dead runs)
- **Evidence:** `logs/bug_log.md` BUG-BASH-BACKGROUND (2026-04-13)

## What happened

A long-running job was launched as `python ... &` inside a Bash tool call. The
shell backgrounded the process, the shell task itself exited 0, and Python was
left orphaned. The orphan was later SIGKILLed with no traceback — the log simply
stopped mid-work. This happened twice, with the run dying at 00:13 both times.
About 10 hours were lost across the two dead runs.

The same command run in the FOREGROUND, with `run_in_background=true` set on the
Bash tool itself, ran cleanly for 7h48m to completion.

## Root cause

`&` disowns the process from the shell. The Bash tool's task lifecycle is what
keeps a subprocess alive across the turn; a process backgrounded with `&` is
outside that lifecycle, so when the shell task returns, the subprocess has no
owner and is reaped. The failure is a property of how the tool manages process
lifecycle, not of any POLARIS code — which is why it is durable and worth
codifying.

## Contributing factors

- The shell task exiting 0 looked like success, so the launch appeared to have
  worked while the real work was already dead.
- The death was silent: no traceback, just a log that stopped, so it was only
  visible by noticing the missing completion, not by an error.
- The first dead run did not immediately surface the pattern, so a second run
  was lost the same way before the cause was understood.

## Lessons (promoted to)

- Never background a long run with `&` inside a Bash tool call. Run the command
  in the FOREGROUND and set `run_in_background=true` on the Bash tool itself; the
  tool's task lifecycle keeps the subprocess alive, whereas `&` disowns it.
- Promoted to `logs/bug_log.md` BUG-BASH-BACKGROUND (2026-04-13) as a standing
  operational rule: the foreground + `run_in_background` pattern is the only
  supported way to run a long job across a turn.
