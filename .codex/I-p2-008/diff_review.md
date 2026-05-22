# Codex DESIGN+DIFF review — I-p2-008 (#747): run-progress Thinking-Toggle

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1 (code + design rubric). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `99cabd9cffe186ca661bee191664b0a5f45ef50e29904cc86898cd70de988945`. web/ only.

## Design-audit note
Additive toggle on the existing #707/#725 Codex-reviewed checklist (already screenshot-verified). The toggle is the only new affordance; full page screenshot at #755 (Run progress page). Audit code + a11y here.

## Diff (single file: run_progress.tsx)
- showThinking state (default ON). Toggle button: aria-expanded={showThinking} + aria-controls="run-progress-stages", focus-visible /70, "Hide/Show details".
- <ol id="run-progress-stages">; per stage: showThinking ? <StageBody/> (full feed) : <p>{compactStatus(state)}</p> (honest 1-line from the SAME StageState source-of-truth as the chip).
- compactStatus(): active→In progress, done→Done, skipped→Did not run, degraded→Not observed (stream lost), pending→Pending.
- NO change to stageState/#725 honest-state logic or counters.

## Review focus
1. Collapsed state still HONEST: each stage's state visible (chip + compactStatus matches the chip's state)? No active-sounding copy on a skipped/degraded stage?
2. Toggle a11y: aria-expanded/aria-controls correct + keyboard + focus-visible?
3. No regression to #725 stage-state logic / counters / stream-loss handling. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
