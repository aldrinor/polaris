# Claude architect audit — I-p2-057 (#861): Run progress page S-audit

## Goal
Final leg of the Plan→Run→Compare journey: /runs/[runId] (cred-gated live-run surface; depth-visible
4-stage progress consuming the #706 SSE sub-task events). Audited by rendering locally (seeded
session + a mocked EventSource emitting canned scope/evidence/section/verifier/run_complete events +
route-mocked getRun) so both the LIVE mid-run state and the terminal state could be seen. Fixture is
visual-audit-only — never shipped.

## What looking-at-it found
The run_progress component was already exemplary (honest stream-loss handling, the "never
green-check an unobserved stage" rule, the Thinking-Toggle, honest "—" elapsed when not watched
live). Gaps:
- The "done" stage chip + the retrieval source ✓ were brand-RED — a red done-checkmark reads as an
  alarm in the product's verdict language (done/verified = green).
- The stage cards, counters, and the page's actions card were flat (no elevation).
- The page's actions card used UX jargon ("Affordances during this run") and a hardcoded heading
  that said "While this run works" even on a completed run.

## What changed (page + component + tracker)
- done stage chip + retrieval ✓ → `--verified` green (matches the Compare-page flag fix).
- `shadow-card` + `rounded-xl` on the stage cards, the counters, and the actions card.
- Actions card heading de-jargoned + branched by verdict.

## The honest-framing fix Codex caught (diff iter-3, §9.1)
My first copy branch gated the "verified result" wording on lifecycle `status === "completed"`.
Codex correctly flagged that `mark_aborted()` persists lifecycle 'completed' for abort_* runs too —
so an `abort_no_verified_sections` run (lifecycle completed, pipeline aborted) would claim a
"verified result" AND render the follow-up panel despite having NO verified result. That is exactly
the lethal-in-clinical-context overclaim. Fixed: `hasVerifiedResult` is derived from the PIPELINE
verdict (completed AND pipeline_status not abort_*/error_*; a null pipeline_status on a completed run
is trusted as success, matching RunProgress's own fallback). BOTH the "verified result" copy AND the
FollowupPanel now gate on `hasVerifiedResult` — an aborted run shows "Open or export what this run
produced:" with no follow-up. This corrects a latent bug in pre-existing code, not just my copy.

## Preserved
The stage-state machine (the "never green-check unobserved" rule, stream-loss/synthetic-
run_complete handling), the getRun/subscribeToRun(SSE)/cancelRun flow, the tick/elapsed logic, the
Thinking-Toggle, and testids (runs-runid-page, run-progress, stage-*).

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-2 (live desktop A / live mobile A / done desktop A). Code
  diff APPROVE iter-4 (after the §9.1 pipeline-status honesty fix).

## Honest verification state
LIVE end-to-end run verification on polarisresearch.ca is DEFERRED — it needs auth + a real backend
run; the live + terminal states verified against a mocked EventSource + route-mocked getRun (visual
audit only). The abort-run branch is logic-gated (not separately screenshotted) but follows the same
pipeline-verdict rule the component itself documents.

## Constraints honored
Brand `#c8102e` (New-run + Ask + active spinner + nav active); done = verified-green; tokens only;
the stage-state machine + SSE flow + testids preserved; no fabricated SHIPPED data; no test
relaxation. The pipeline-status honesty fix strengthens §9.1 adherence.

canonical-diff-sha256: b21755dd226a93ffc06b04d715308703e9491f28277ce8d5fb38832b26335133
