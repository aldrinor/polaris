# Codex BRIEF review — I-ui-002 (#707) /runs/[runId] staged-progress UI

HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — P3/P2/cosmetic for non-blockers; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, Claude force-APPROVE's on remaining-non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Design-spec (brief IS the work for UI) review — confirm sound + safe BEFORE implementing.

## Operator context
The most-watched demo moment is the 5-15 min run. Today /runs/[runId] dumps raw SSE events as JSON cards ("Live events (N)"). #707: replace with a Perplexity-style 4-stage progress UI consuming the #706 SSE events. Carney-visible. warm-editorial cyan consistent with the just-merged #704.

## Scope
**IN:** (a) new staged-progress component `run_progress.tsx` replacing the raw "Live events" JSON dump (lines ~232-261 of web/app/runs/[runId]/page.tsx); (b) **web/lib/api.ts — register `evidence_id` in the subscribeToRun EventSource listener list** (iter-1 P1: it's currently NOT listened for, so the source feed/counter is dead without it); keep the existing header/status/affordances (cancel/inspector/bundle) + error handling.
**OUT:** the home (#704, merged); follow-up UI (#542); compare UI (#543).

## Verified facts (grounded)
1. The page (web/app/runs/[runId]/page.tsx, "use client") ALREADY subscribes via `subscribeToRun(runId, onEvent)` and accumulates `events: StreamEvent[]` (StreamEvent = {event: string; data: Record<string,unknown>}). The data is already flowing — #707 is pure rendering of `events` + `status`.
2. Event names (web/lib/api.ts subscribeToRun + #706 translator) + payloads:
   - `scope_decision` {verdict, reason}
   - `retrieval_progress` {sources_found, tier_breakdown}
   - `evidence_id` {evidence_id, source_url}
   - `verifier_verdict` {section, local_pass, global_pass}
   - `section_complete` {section, verified_sentences, dropped}
   - `run_complete` {status, ...}  (terminal)
3. RunStatusResponse (frontend type) = {run_id, status, template, question, queued_at, started_at?, finished_at?, cancel_requested?}. NO cost_usd field. So "spend" is NOT available frontend-side; the issue's #707 counters are word-count / elapsed / sources-read (NOT spend).
4. Visual identity (just merged #704): cyan accent oklch(0.50 0.20 200) via --primary/--ring; zinc-50 bg; Card/Button/Badge shadcn components.

## Design — 4-stage progress
A new client component `run_progress.tsx` (props: `events: StreamEvent[]`, `status: RunStatusResponse | null`) rendered in place of the raw events dump. Maps events → 4 ordered stages:

| Stage | Driving events | Resolves (observation-based) |
|---|---|---|
| Scope | scope_decision | when scope_decision observed |
| Retrieval | retrieval_progress, evidence_id | on its own observed events; terminal run_complete |
| Generation | section_complete | on its own observed events; terminal run_complete |
| Verification | verifier_verdict | on its own observed events; terminal run_complete |

(iter-3 P2: superseding any earlier "Retrieval done on first section_complete" / "on run_complete all stages → done" wording — replaced by the observation-based rule + exhaustive terminal taxonomy below.)

**Stage status — ONE unambiguous rule (iter-4 P1 resolves the prior contradiction).** Per stage, computed independently (NOT a linear cursor — the producer emits verifier_verdict before section_complete):
- **While the run is NOT terminal:** a stage is `done` iff its own event(s) were observed; `active` iff its own events are arriving and no later-stage event has been observed; otherwise `pending`. Never infer a stage from a later stage's events.
- **On terminal `run_complete{status: success}`:** ALL 4 stages → `done`. A success terminal PROVES the full pipeline ran end-to-end, so green-checking every stage is truthful even if a late-joining viewer missed early events. (This is the ONLY case where an unobserved stage is marked done — and it is justified because success ⇒ it provably ran.)
- **On any NON-success terminal** (abort_* / partial_* / error_* / unknown / stream_lost / stream_unavailable): stages with observed events → `done`; stages WITHOUT observed events → neutral `did not run / not observed` (NEVER a green check — they may genuinely not have run). No stage stays `active`/spinning.

**run_complete handling — EXHAUSTIVE terminal taxonomy (iter-2 NOVEL P1 + iter-3 P1).** UNIVERSAL RULE: ANY `run_complete` (any status, AND any unrecognized/unknown status) is TERMINAL → immediately freeze elapsed, stop the timer, and no stage may keep spinning. The `data.status` value ONLY drives the banner + how unreached stages render. Never auto-green-check a stage whose events were not observed.
- `success` → success banner; ALL 4 stages → done (success proves the pipeline ran end-to-end; per the stage rule above this is the only case unobserved stages are marked done).
- `partial_*` (e.g. partial_evaluator_advisory) → terminal "report produced with caveats" warning banner; observed stages done; unobserved stages neutral "did not run / not observed" (NOT a green check).
- `abort_*` (abort_scope_rejected / abort_corpus_inadequate / abort_corpus_approval_denied / abort_no_verified_sections) → terminal "run halted at gate" banner; observed stages done; unobserved stages neutral "did not run / not observed" (NOT a green check). No spinner.
- `error_*` / `error_unexpected` / any UNKNOWN status → terminal "run failed" banner; observed stages observed; unreached neutral. (Default branch catches unknown so the UI never hangs.)
- `stream_lost` / `stream_unavailable` (synthetic terminal from the #706 STREAM_LOST_GRACE backstop in run_events.py) → **terminal-DEGRADED**: "live connection lost — run may still be progressing" banner; DO NOT checkmark any unobserved stage. A dropped stream must not masquerade as a completed run.

Terminal detection sources (iter-3 P2): (a) a `run_complete` EVENT (read data.status as above) — primary; (b) fallback `status.status` ∈ {`completed`,`failed`,`cancelled`} (LIFECYCLE terminal values — NOT pipeline abort_*/partial_*, which arrive only in run_complete.data.status). Either path freezes elapsed + stops the timer.

Per stage: a status chip (pending = muted dot; active = cyan pulsing spinner; done = cyan check) + a sub-task feed:
- Scope: the verdict + reason line.
- Retrieval: a running list of evidence sources (each evidence_id → one row with source_url + check), + "N sources read" from the evidence_id count (fallback to retrieval_progress.sources_found).
- Generation: one row per section_complete (section name + "{verified_sentences} verified, {dropped} dropped").
- Verification: one row per verifier_verdict (section + local/global pass badges).

## Counters (top strip)
- **Elapsed**: tick every 1s = now − (started_at ?? queued_at). iter-1 P1: status is fetched ONCE and `status.finished_at` stays null after run_complete, so DO NOT depend on it — latch a LOCAL terminal timestamp when the `run_complete` EVENT arrives (or when status.status is terminal), freeze elapsed at that latched value, and clear the setInterval from the run_complete event handler. Interval also cleared on unmount.
- **Sources read**: count of distinct evidence_id events (fallback retrieval_progress.sources_found).
- **Sentences verified**: sum of section_complete.verified_sentences. (iter-2 P2 CONFIRMED: live SSE has NO word-count payload; counter is labelled "Sentences verified", not "word count".)
Degrade gracefully + defensive parsing (iter-2 P2): filter blank/missing evidence_id before counting; coerce numeric payload fields with Number()/?? 0 safely; any counter with no data shows "—", never NaN/undefined.

## Review focus
1. Stage-derivation logic from event presence — sound? Any event ordering edge case (e.g. run_complete with no sections = abort run → show stages as done-with-zero, not stuck-active)?
2. Counter data availability: elapsed (timestamps), sources (evidence_id count), sentences (section_complete sum). Is "word count" genuinely unavailable from SSE (→ relabel to sentences-verified)?
3. Terminal/abort handling: run_complete{status: abort_*} — stages should resolve, not spin forever.
4. setInterval cleanup (no leak; stop on terminal/unmount).
5. Keep the existing cancel/inspector/bundle affordances + error handling intact?
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

---
## iter-2 changelog (addressing iter-1 REQUEST_CHANGES)
- P1 evidence_id: scope now includes web/lib/api.ts to register `evidence_id` in the subscribeToRun EventSource listener list (without it the source feed/counter is dead). Will add a test/mock for it.
- P1 elapsed: latch a LOCAL terminal timestamp from the `run_complete` event (not status.finished_at, which stays null); freeze elapsed + clear interval from that handler.
- P2 generation terminal: run_complete is the ONLY authoritative generation/verification done; partial section/verifier rows shown as incremental feed (no total-section count assumed).
- P2 out-of-order: stage status derived independently per stage (verifier_verdict-before-section_complete safe); abort run (run_complete, zero sections) resolves all stages done.

---
## iter-3 changelog (addressing iter-2 REQUEST_CHANGES)
- NOVEL P1 stream_lost: run_complete handling now branches on data.status — success → resolve observed stages done; abort_* → done/did-not-run (no green check on unreached); stream_lost/stream_unavailable → terminal-DEGRADED (freeze elapsed, stop timer, "connection lost" banner, NO checkmark on unobserved stages). Stage checkmarks are observation-based, never assumed.
- P2 generation/verification: resolve on OWN observed events + real run_complete only (not generic later-stage rule).
- P2 defensive parsing: filter blank evidence_id, safe numeric coercion, "—" not NaN.
- P2 label: "Sentences verified" (confirmed no word-count in SSE).

---
## iter-4 changelog (addressing iter-3 REQUEST_CHANGES)
- P1 taxonomy: run_complete handling is now EXHAUSTIVE — success / partial_* / abort_* / error_*/error_unexpected / UNKNOWN (default branch) / stream_lost / stream_unavailable. UNIVERSAL rule: ANY run_complete (incl unknown) is terminal → freeze elapsed + stop timer; no stage spins forever. Status drives banner + unreached-stage rendering only.
- P2 stale wording removed: deleted "Retrieval done on first section_complete" + "On run_complete all stages → done"; superseded by observation-based rule.
- P2 fallback: status.status terminal fallback uses LIFECYCLE values {completed, failed, cancelled} (not pipeline abort_*/partial_*, which arrive in run_complete.data.status).

---
## iter-5 changelog (addressing iter-4 REQUEST_CHANGES)
- P1 contradiction resolved with ONE rule: non-terminal → stage done iff own events observed; terminal success → ALL stages done (success proves full pipeline ran — the only case unobserved=done, justified); any non-success terminal → observed done, unobserved neutral "did not run / not observed" (never green-check, never spin).
- P2 abort wording aligned to "observed done; unobserved neutral did-not-run; no spinner" (no "done-with-zero" ambiguity).
