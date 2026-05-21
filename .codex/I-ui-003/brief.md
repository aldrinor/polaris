# Codex BRIEF review — I-ui-003 (#542) follow-up answer UI

HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — P3/P2/cosmetic for non-blockers; P0/P1 only for real execution risks.
- If iter 5 returns REQUEST_CHANGES, Claude force-APPROVE's on remaining-non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Design-spec review (brief IS the work for UI) — confirm sound BEFORE implementing.

## Goal (#542 / I-rdy-014a)
From a COMPLETED run, an operator submits a follow-up question scoped to that run's evidence; the FollowUpAnswer renders. Backend exists + is real-run-wired (#680).

## Scope
**IN:** (a) api.ts — `FollowUpAnswer` type + `askFollowup(runId, question)` client (authFetch POST); (b) new `followup_panel.tsx`; (c) runs page — replace the disabled "Ask follow-up" button (line ~212) with the panel, shown only for completed runs. cyan-consistent with #704.
**OUT:** run-compare (#543).

## Verified facts (grounded)
1. Endpoint: `POST /api/v6/runs/{run_id}/followup` body `{question}` (min 4 / max 2000 chars per FollowUpHttpRequest Field) → FollowUpAnswer. Real-run wired via load_evidence_contract_for_run (#680): golden fixtures + real completed runs; **422** for abort_*/release-blocked, **404** for unknown id.
2. FollowUpAnswer schema (src/polaris_v6/followup/schema.py): `{parent_run_id, question, status, answer_text|null, used_evidence_ids[], provenance_tokens[], rationale}`. status ∈ {`answered`, `out_of_scope`, `needs_new_run`, `evidence_insufficient`}. answer_text is null unless status==answered. rationale always present.
3. Auth: the run page (/runs/[runId]) is behind app auth; the user IS signed in. Use `authFetch` (api.ts:30 — adds bearer; redirects to /sign-in on 401, acceptable on this gated page, unlike the public home). createRun/cancelRun use this pattern (api.ts:129-176).
4. Run page (web/app/runs/[runId]/page.tsx): `status.status`, TERMINAL_STATUSES=[completed,failed,cancelled], isTerminal (line 71), disabled "Ask follow-up" button (line ~212), Affordances section (~159).
5. Visual identity (#704, live): cyan accent oklch(0.50 0.20 200) via --primary/--ring; Card/Button/Input shadcn.

## Design
**api.ts:** `export interface FollowUpAnswer {...}` (mirror the schema) + `export async function askFollowup(runId: string, question: string): Promise<FollowUpAnswer>` → authFetch POST `${BACKEND_URL}/runs/${runId}/followup` with `{ method:"POST", headers:{"content-type":"application/json"}, body: JSON.stringify({question}) }`; throw ApiError on !ok (mirror createRun's error handling).

**followup_panel.tsx (new client component, props `{ runId }`):**
- A `<form>`: a textarea (label "Ask a follow-up scoped to this run", placeholder, value/onChange), submit Button (cyan primary, disabled while submitting or question.trim().length < 4 — matches backend min_length).
- States: `idle` | `submitting` | `{answer: FollowUpAnswer}` | `{error: string}`.
- On submit: askFollowup → set answer; catch → friendly error (404 → "run not found"; 422 → "This run has no shippable evidence to follow up on (it was aborted or release-blocked)."; else "Couldn't get a follow-up answer right now.").
- Render answer by status:
  - `answered` → answer_text (prose), then provenance: used_evidence_ids + provenance_tokens as small mono chips; a "scoped to this run's verified evidence" caption.
  - `out_of_scope` / `needs_new_run` / `evidence_insufficient` → a status badge + the `rationale` text (no answer_text); for needs_new_run, a hint to start a new run.
- Allow asking again (reset to idle / keep history is OUT — single Q/A is enough for #542).

**runs page:** replace the disabled "Ask follow-up" Button with `{status?.status === "completed" && <FollowupPanel runId={runId} />}`. Only `completed` (not failed/cancelled/in-progress) — those have no answerable report; the panel simply doesn't render for them. Keep the other affordances (inspector/bundle/cancel) intact.

## Review focus
1. Show-only-on-completed gating correct? (failed/cancelled/in-progress → no panel.) Should abort-but-"completed" lifecycle runs be handled (they're lifecycle=completed but pipeline abort_* → endpoint 422)? → the 422 error branch covers that case gracefully.
2. The 4 FollowUpStatus rendered correctly (answer_text only on answered; rationale always)?
3. Error mapping (404/422/network) friendly + correct?
4. authFetch (redirect-on-401) acceptable here (gated page) vs the home's authHeader choice?
5. Input min-4-char matches backend; max 2000.
6. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
