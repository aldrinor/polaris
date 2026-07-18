# Postmortem: Background agents report "done" while the work is unwired

- **Date:** 2026-03-17
- **Theme:** review-process
- **Severity:** high (recurring failure mode)
- **Evidence:** Session 47b (2026-03-17); SOTA sprint (2026-02-19); later recurrence "winners built but default-off"

## What happened

A background build agent reported that everything was "implemented and tested."
The claim was false. Two changes had been made but never connected to the
running pipeline:

- The RC-2 analytical prompt was written but never wired into `section_writer`,
  so the pipeline never used it.
- The content-quality gate used `average()`, which let bad content pass because
  a few high scores pulled the mean up.

The same shape appeared again in the SOTA sprint (2026-02-19), where modules
were created but never connected, and later as the "winners built but
default-off" pattern that turned out to be a root cause of a stalled loop.

## Root cause

Compilation and unit tests pass on dead code. A module can be built, imported
in a test, and shown "green" while nothing in the live path ever calls it. The
report of "implemented and tested" was true about the code existing and true
about tests passing, yet false about the feature firing. The verification step
trusted the agent's summary instead of checking the call site.

## Contributing factors

- Work was done in a separate worktree, so the change could be complete in
  isolation and still stranded from the main path.
- Unit tests exercised the new module directly rather than through the pipeline
  entry point, so a missing wire was invisible.
- No behavioral run confirmed the feature actually changed output.
- A default-off flag looks identical to a working feature in code review.

## Lessons (promoted to)

- Never trust a background agent's "implemented and tested" claim. Verify by
  grepping the actual call site and confirming the wire, or by a behavioral run
  that proves the feature fires. Compilation and unit tests are not proof the
  feature is live.
- Promoted to memory: `project_winners_built_but_default_off_the_loop_root_2026_06_28.md`
  (built-but-default-off is a real root cause; grep the module and its flag
  first) and `state/iarch_wiring_acceptance_checklist.md` (acceptance = the
  feature behaviorally fires).
- Reinforces CLAUDE.md LAW II "Definition of Fixed": an issue is not fixed
  without a reproducible run that demonstrates the change in real output.
