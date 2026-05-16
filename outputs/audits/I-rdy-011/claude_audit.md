# Claude architect audit — I-rdy-011 (#507): implement cancellation/resume

**Issue:** GH #507 — implement the disabled UI cancel path and the xfailed
backend resume behaviour. Acceptance: a run can be cancelled in under 5s and
resumed from checkpoint.

**Commits (off `polaris` @ `9185035e`):** `eccfe85d` (APPROVE'd brief),
`5d1df254` (code), `43511151` (diff-iter-1 P1 fixes), `4e56489b` (diff-iter-2
P1 fix). Canonical-diff-sha256
`728c4c674d395bc608f57d0c6cb1b26107d1e8cb59ebb0a37755575ea483641d`.

## Scope (Codex brief-iter-1 APPROVE'd, scope_ruling = option-A)

#507 names cancel + resume. Resume-from-checkpoint is infrastructure-blocked:
pipeline-A's `run_one_query` has no checkpoint protocol, and the resume
acceptance scenarios (`test_dramatiq_acceptance.py` 4/5) are xfailed pending
the Vast.ai real-Redis multi-worker cluster (#85-91, hardware-gated). Codex
APPROVE'd shipping the **cancel path** now (queued T1 + cooperative
in-progress T2 + UI) and **carving** T3 (hard-kill mid-LLM, needs
`Worker.send_signal` + real broker) + resume-from-checkpoint.

## Acceptance check (cancel)

- **Queued run cancelled instantly (T1):** `request_cancel` flips a `queued`
  row to terminal `cancelled` in one atomic UPDATE — well under 5s.
- **In-progress run cancelled cooperatively (T2):** `request_cancel` sets the
  `cancel_requested` flag; the run aborts at the next `_abort_if_cancelled`
  checkpoint (three: pre-retrieval, pre-generation, post-generation/
  pre-evaluator), AND the actor's post-`run_one_query` backstop catches a
  cancel that lands in the final stage past the last checkpoint. The cancel
  request is recorded + surfaced (`RunStatusResponse.cancel_requested`) in
  <5s; the run reaches terminal `cancelled`, never `completed`.
- **UI:** the run page's "Cancel run" button is enabled + wired, disabled
  once the run is terminal.

## Codex review trail — converged at diff-iter 3

- Brief: APPROVE iter-1.
- Diff iter-1 REQUEST_CHANGES → fixed P1-1 (the actor false-cancelled a
  retry of a `failed` run by inferring cancel from the `mark_in_progress`
  CAS-False — now detects cancel ONLY via `is_cancel_requested`) + P1-2
  (added the post-generation/pre-evaluator checkpoint).
- Diff iter-2 REQUEST_CHANGES → fixed P1 (a cancel during the final
  evaluator/judge stage was lost — added the actor-side post-`run_one_query`
  `is_cancel_requested` backstop that overrides a success manifest).
- Diff iter-3 **APPROVE** — zero P0/P1, `accept_remaining`.

## Codex P2 guardrails (brief-iter-1) — all four implemented

P2-1 SSE: `run_events._check_lifecycle_terminal` treats `cancelled` as
terminal. P2-2 CAS: `mark_in_progress` is a compare-and-swap. P2-3:
`RunStatusResponse.cancel_requested` surfaced. P2-4: cancel polls only at
major `run_one_query` stage boundaries.

## Tests

`tests/v6/test_cancellation.py` — 17 tests, all pass offline: run_store
cancel methods + CAS + the retry-not-false-cancelled regression + the
late-cancel-overrides-success regression; `cancel_run` route 404 /
terminal-noop / queued-cancel; the actor honors a pre-pickup cancel;
`_abort_if_cancelled`. `test_actors.py` 8/8 + `test_dramatiq_acceptance.py`
scenario 1 pass — no regression. Import smoke clean. `web/`: `typecheck` +
`eslint` clean.

`test_dramatiq_acceptance.py` scenario 3 (`cancel_mid_execution`) stays xfail
— its xfail reason is `Worker.send_signal` (the carved T3 hard-kill path).
`test_cancellation.py` is the T1+T2 coverage.

## Residual / follow-up

- **Carved (infra-gated follow-up):** T3 hard-kill-mid-LLM (needs
  `Worker.send_signal` + a real Redis multi-worker broker) + resume-from-
  checkpoint (needs new pipeline-A checkpoint infrastructure + the Vast.ai
  cluster).
- **Accepted residual (Codex diff-iter-3 P2, non-blocking):** a queued-cancel
  emits no Redis terminal event, so a stream-only SSE consumer closes via the
  `stream_lost` grace path rather than a direct `cancelled` payload — the
  brief-P2-1-sanctioned OR-branch (terminal detection includes `cancelled`);
  the status API is correct.
- A full live in-progress cancel (real pipeline run, cancel mid-flight) needs
  network + the generator API — CI/e2e, not the autonomous loop.

## Verdict

The diff implements the APPROVE'd brief (Option A), the cancel path is
correct across all three difficulty tiers in scope (T1 instant, T2
cooperative with an airtight actor backstop), all four Codex P2 guardrails
are in, and Codex diff review converged to APPROVE at iter 3.
