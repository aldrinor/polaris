# Codex DIFF review — I-ui-002 (#707) staged-progress UI

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings. P0/P1 for real execution risks only. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. Touches web/ only (NOT operator-only exclusion).

Canonical-diff-sha256: `78b82cce21ccd83e3eb304140c3519ce0490cb404942d67520bff4e5881d8818`. 3 files, 351+/34-.

## EMPIRICAL: typecheck clean, lint 0 errors, `npm run build` SUCCEEDS. (No web unit-test runner exists; e2e Playwright pending #720 jose backend-boot.)

## Implements the brief you APPROVE'd (iter 5). Diff: .codex/I-ui-002/codex_diff.patch.
- web/lib/api.ts — register `evidence_id` in subscribeToRun's EventSource listener (iter-1 P1 fix).
- web/app/runs/[runId]/components/run_progress.tsx (NEW, ~330 lines) — the 4-stage component.
- web/app/runs/[runId]/page.tsx — render <RunProgress events status/>; removed the raw "Live events" JSON dump + now-unused Card imports.

## Key logic to verify against the APPROVE'd brief
1. Stage state ONE rule: non-terminal → done iff own events observed, active = most-recent observed stage (lastObserved index), pending otherwise. Terminal success → ALL done. Terminal non-success → observed done, unobserved "skipped" (neutral), stream_lost → "degraded". (run_progress.tsx stageState())
2. EXHAUSTIVE terminal taxonomy: isTerminal = run_complete event OR status.status ∈ {completed,failed,cancelled}; ANY terminal stops the interval (elapsed freezes). isSuccess/isStreamLost branch the rendering. Unknown status → not success, not stream-lost → observed-done + unobserved-skipped (never hangs).
3. Elapsed: nowMs ticks only while non-terminal (interval cleared when isTerminal) → freezes within 1s; mountedTerminal (useState init once) → "—" for runs already terminal at mount (finished_at is null, no event timestamp). NO setState-in-effect, NO ref-read-in-render (both lint-clean).
4. Defensive: asNumber/asString coercion, blank/dup evidence_id filtered, "—" never NaN.

## LOC exemption (documented)
351+/34- (~317 net) exceeds the 200-LOC cap. The bulk is the single cohesive run_progress.tsx component (~330 lines incl 3 small presentational sub-components Counter/StageChip/StageBody). Splitting one React component across PRs is artificial + worse for review. Requesting exemption (per CLAUDE.md §3.0 cap-is-halt-unless-exempted). Confirm acceptable or advise a split.

## Review focus
1. Stage/terminal logic matches the APPROVE'd brief? Any taxonomy branch that could hang a stage or mislabel?
2. Elapsed freeze correctness (interval-stop freeze + mountedTerminal "—") — sound + lint-clean?
3. evidence_id listener + dedup + counter fallback correct?
4. Existing affordances (cancel/inspector/bundle) + error handling untouched?
5. LOC exemption reasonable?
6. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
