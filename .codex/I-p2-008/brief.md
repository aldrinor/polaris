# Codex BRIEF review — I-p2-008 (#747): run-progress checklist + Thinking-Toggle

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
Add a **Thinking-Toggle** to the live run-progress checklist (make the run's DEPTH visible-but-collapsible — a frontier-DR affordance).

## Verified current state (grounded — REUSE, no churn)
- `web/app/runs/[runId]/components/run_progress.tsx` (#707/#725, Codex-reviewed) ALREADY IS the dynamic 4-stage checklist (Scope/Retrieval/Generation/Verification) driven by the #706 SSE events, with counters + per-stage StageBody detail feeds + honest stage states (pending/active/done/skipped/degraded) + #742 --primary tokens. Do NOT rebuild it (churn).
- NO live "reasoning"/"thinking" SSE event exists (events: scope_decision/retrieval_progress/evidence_id/verifier_verdict/section_complete/run_complete). So "thinking"/DEPTH = the existing per-stage StageBody detail (sources read, sections drafted, verifications). Do NOT invent a reasoning stream.

## Acceptance criteria (diff implements; brief reviews the plan)
1. Add a Thinking-Toggle control to run_progress.tsx: a button that shows/hides the per-stage StageBody DETAIL (the depth). When OFF → compact checklist (stage chip + label + a one-line status only); when ON → the full per-stage feeds (current behavior).
2. Default ON (depth visible — the differentiator), with a clear "Hide details / Show details" toggle. Persist within the session is optional (not required).
3. a11y: the toggle is a button with `aria-expanded` + `aria-controls` pointing at the detail region; keyboard + focus-visible; the collapsed state still shows each stage's state honestly (chip + one-line).
4. NO behavior change to the honest stage-state logic (#725) or counters. Frontier-Minimal; Canada-red toggle accent only if it's the primary affordance (else neutral).

## Files I have ALSO checked and they're clean
- web/app/runs/[runId]/components/run_progress.tsx (the existing checklist — the ONLY file #747 edits), web/app/runs/[runId]/page.tsx (parent passes events+status — unchanged), web/components/inspector/reasoning_trace_timeline.tsx (post-run reasoning, NOT the live run — out of scope).

## Review focus
1. Is "thinking = collapsible per-stage detail" the right read given there's no live reasoning SSE, or is there a real reasoning stream I missed? (If I missed one, that's a P1.)
2. Toggle a11y (aria-expanded/controls) + the collapsed state still honest (each stage's state visible)?
3. No regression to the #725 honest stage-state logic / counters. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```
