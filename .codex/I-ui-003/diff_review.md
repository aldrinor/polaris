# Codex DIFF review — I-ui-003 (#542) follow-up answer UI

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings. P0/P1 for real execution risks only. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. Touches web/ only.

Canonical-diff-sha256: `510eb648d760deb2065b1a667d9d1d6981fcacd4ed96ad2643f0a4789693ed54`. 3 files, 206+/8-.

## EMPIRICAL: typecheck clean, lint 0 errors, npm build SUCCEEDS. (e2e pending #720.)

## Implements the brief you APPROVE'd (iter 1) + all 4 iter-1 P2 folded in. Diff: .codex/I-ui-003/codex_diff.patch.
- web/lib/api.ts — FollowUpAnswer type + askFollowup(runId, question) via authFetch POST + asJsonOrThrow.
- web/app/runs/[runId]/components/followup_panel.tsx (NEW) — form (textarea 4–2000, trimmed, submit) → askFollowup; renders 4 statuses; rationale always; provenance chips; error mapping.
- web/app/runs/[runId]/page.tsx — replaced disabled "Ask follow-up" button; <FollowupPanel/> shown full-width only when status==completed.

## P2s from brief iter-1, all applied:
1. maxLength={2000} + trimmed submit (over-2000 → won't misreport).
2. 422 mapping: Array.isArray(body.detail) → validation copy; else → no-shippable-evidence.
3. Full-width panel block (not a cramped button peer).
4. rationale shown for answered too (always present).

## Review focus
1. askFollowup auth/error (authFetch + asJsonOrThrow → ApiError {status, body}) correct?
2. completed-only gating (status==completed) — failed/cancelled/in-progress correctly hidden; lifecycle-completed-but-pipeline-abort run → endpoint 422 → no-evidence branch. Sound?
3. 4-status rendering: answer_text only on answered; rationale always; needs_new_run hint; provenance chips.
4. error mapping 404/validation-422/no-evidence-422/generic correct + friendly?
5. Any NOVEL P0/P1.

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
