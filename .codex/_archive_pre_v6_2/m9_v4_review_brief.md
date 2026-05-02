M-9 v4 — final GREEN check round 2.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-9 v3 verdict: STILL-PARTIAL on subprocess-leak.
Initial-checkpoint race fix landed, but the inner per-phase /
periodic Paused → RuntimeError conversions did not terminate the
V30 child. RuntimeError propagated past outer except blocks (no
type match), the finally only joined the drain thread, and the
child kept running while the job was marked failed.

Manual repro you performed:
- job marked failed
- child PID still alive immediately after failure
- child later exited normally and wrote completion sentinel

## What changed in v4

Centralized subprocess termination in the outer `finally` block
(before `drain_thread.join`) so EVERY exit path runs
`_terminate_subprocess`:
- Cancelled (inner re-raise → outer except → finally)
- Paused→RuntimeError (inner conversion, no outer match → finally)
- Paused (outer safety net → finally)
- Any other RuntimeError → finally
- Normal exit (proc.poll() returns rc → finally no-ops since
  proc has already exited)

`_terminate_subprocess` is idempotent (no-op if `proc.poll() is
not None`), so the success path is unchanged.

Dropped:
- `_terminate_subprocess` from outer except Cancelled / Paused
  (now redundant with finally)
- The dead `cancelled` boolean flag

Test extension:
- Stub `_write_stub_sweep` now writes its PID to
  `<out_root>/stub.pid` at startup.
- `test_pause_request_fails_loudly_for_v30_clinical` reads that
  PID, requests pause, asserts status=='failed' AND
  `psutil.pid_exists(stub_pid)` returns False within
  `cancel_grace_s + buffer` seconds.

Stability: 10/10 consecutive runs of the extended pause test
pass. 13/13 v30_runner. 144/144 Phase B (audit_ir + job_queue +
job_router + job_worker + v30_runner).

## Your job

Final verdict on M-9. GREEN / STILL-PARTIAL / DISAGREE.

Quick verification:
- Does `finally` in v30_runner.py run `_terminate_subprocess`
  before `drain_thread.join`?
- Does the extended test actually call `psutil.pid_exists` on
  the stub PID and assert False?
- Manual repro: does the child process actually die when pause
  is requested mid-sweep?
- Anything else you see?

If GREEN, M-9 is locked and Phase B can proceed to M-10 (curated
template router with confidence gating).

## Output

Write to `outputs/codex_findings/m9_v4_review/findings.md`:

```markdown
# Codex final review of M-9 v4

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Subprocess-leak fix
- [x/no] Termination centralized in finally for all exit paths
- [x/no] Manual repro: child dies on pause→fail

## Stability
10/10 + termination assertion acceptable for lock?

## Final word
GREEN to lock M-9 + proceed to M-10 / STILL-PARTIAL with edits.
```

Be terse. Under 60 lines.
