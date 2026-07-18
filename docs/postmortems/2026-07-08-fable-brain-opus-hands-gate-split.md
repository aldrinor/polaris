# Postmortem: Wrong division of labor — a 2.3M-token fan-out that produced nothing

- **Date:** 2026-07-08
- **Theme:** review-process / workflow
- **Severity:** high (a weekly token budget was exhausted with no deliverable)
- **Evidence:** `feedback_claude_codex_fable_workflow_fable_investigates_opus_builds_2026_07_08.md` (operator-locked 2026-07-08)

## What happened

Two Fable fan-outs were run to investigate and build across several issues. They
burned about 2.3M tokens and hit the weekly limit while producing nothing — all
of the agents died mid-flight. The pattern behind the waste was a build agent
repeatedly settling on a wrong root cause and fixing the wrong thing, which had
kept progress stalled across an extended period.

## Root cause

Diagnosis and building were not separated. The build agent was confident but
unreliable on root cause, so it chose the wrong fix, and the deep-think capacity
was spent on token-heavy mechanical build work instead of on thinking. That split
both produced wrong fixes and drove the token blowup, because expensive
investigation agents were doing expansive work rather than tight, read-only
diagnosis.

## Contributing factors

- The same agent both decided the root cause and built the fix, so a wrong
  diagnosis flowed straight into wrong code with no gate in between.
- The scarce deep-think budget was spent on mechanical build, so it ran out
  before a correct diagnosis was reached.
- The investigation agents had write access, which let them expand into
  token-heavy exploration instead of staying cheap and read-only.

## Lessons (promoted to)

- Split the roles. The deep-think investigator (Fable) finds the true root cause
  and specifies exactly what to build, test, and run — the file, the exact
  change, and the proving test — and consolidates the multi-fix plan across
  issues. The builder (Opus) builds, tests, and runs exactly that and does not
  decide the root cause or choose the fix. The build then goes to Fable AND Codex
  to gate.
- Keep investigators read-only (no worktree, no diff) so they stay cheap; spend
  the scarce deep-think budget only on thinking, never on the token-heavy
  mechanical build.
- Promoted to memory:
  `feedback_claude_codex_fable_workflow_fable_investigates_opus_builds_2026_07_08.md`
  (operator-locked 2026-07-08).
