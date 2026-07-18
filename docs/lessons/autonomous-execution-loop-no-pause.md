# Lessons: Autonomous execution loop & no-pause discipline

Canonical home: CLAUDE.md §8.3.10 (+ §8.1/§8.2 zero-prose-between-merge); memory `project_overnight_beatboth_loop_2026_07_03.md`, `feedback_dont_pause_keep_executing_2026_05_07.md`, `feedback_resume_from_closest_checkpoint_ground_rule_2026_07_01.md`.

The overnight beat-both loop (8-step; if not #1, re-investigate and re-run), the rule that stops are Codex's/halt-condition's/user's call and never a projected "natural cadence," resume-from-closest-checkpoint, and quota discipline all live canonically in the pointed files. This hub adds the mined don't-hold rule.

## Once a bug is TRACED and the fix is faithfulness-neutral, fix → test → gate → relaunch immediately — don't hold and ask

Once a bug is traced to a concrete fix that does not touch the faithfulness engine (strict_verify / D8 / span-grounding / corpus drop-keep): fix it, write a behavioral replay test, run it, Codex-gate the diff (in parallel with the relaunch), and relaunch from the closest checkpoint. Immediately. Hold for the operator ONLY when the only path forward is overriding an operator LOCK, or the change would alter faithfulness — those are the genuine decision points.

Why: Over-applying caution wasted a whole night: after tracing a one-field carry-through fix (faithfulness-neutral), the agent stopped and wrote a long "fix vs bypass — operator decide" note and waited, when the fix took ~30 min once just done. There was nothing to decide. "Quick fix, quick test, quick relaunch from checkpoints, don't fuck around" is the standing instruction. (An advisor call is what counseled the overcautious hold — another reason not to use it.)

Evidence: `feedback_dont_hold_just_fix_relaunch_when_traced_2026_06_30.md` (operator flagged hard 2026-06-30, "you waste whole night").

Recurrence: Operator flagged hard; a repeat over-caution pattern.
