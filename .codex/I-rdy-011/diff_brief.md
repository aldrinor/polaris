# Codex DIFF review — I-rdy-011 (#507): implement cancellation

**Type:** DIFF review (code correctness against the APPROVE'd brief). **iter 3 of 5.**

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §0.5 Changes since prior diff iters

**diff-iter 2 → 3 (REQUEST_CHANGES — P1 fixed, commit `4e56489b`):** Codex
diff-iter-2 found that a cancel requested during run_one_query's *final*
stage (evaluator / Qwen judge / terminal manifest assembly — past the last
cooperative checkpoint) was recorded in the DB but then overwritten by
`mark_completed` when the actor mapped the success manifest. **Fixed:** the
actor now checks `is_cancel_requested` AFTER `run_one_query` returns, before
the manifest-status dispatch — a cancel requested at ANY point during the run
wins over a success/partial/abort manifest → `mark_cancelled`. This
actor-side backstop guarantees the cooperative-cancel contract regardless of
which stage the cancel landed in; the three in-pipeline checkpoints remain as
the early-abort optimization. New test
`test_actor_late_cancel_overrides_success_manifest`.

**diff-iter 1 → 2 (REQUEST_CHANGES — both P1s fixed, commit `43511151`):**

- **P1-1 — false-cancel on retry.** The actor inferred "cancelled" from
  `not run_store.mark_in_progress(...)`, but that CAS returns False for ANY
  non-`queued` row — including a Dramatiq retry of an already-`failed` run,
  which the old code would then rewrite to `cancelled`. **Fixed**
  (`actors.py`): cancellation is now detected ONLY via `is_cancel_requested`
  — two checks bracketing `mark_in_progress` (one before, to honor a
  pre-pickup cancel; one after, to catch a cancel that raced the CAS window).
  The `mark_in_progress` CAS return is no longer interpreted at all (the CAS
  still does its job — it won't resurrect a cancelled row). A retry of a
  failed run now correctly falls through and re-runs the pipeline. New test
  `test_actor_retry_of_failed_run_not_marked_cancelled` proves a failed-row
  retry reaches `completed`, not `cancelled`.
- **P1-2 — cancel during the final stage silently lost.** The last cooperative
  checkpoint was pre-generation, so a cancel requested during/after generation
  was recorded in the DB but never observed; `run_one_query` finished and the
  actor marked the run completed. **Fixed** (`run_honest_sweep_r3.py`): a
  third `_abort_if_cancelled` checkpoint after generation, before
  `run_external_evaluation` (the late long-running evaluator step).

The diff-iter-1 P2 (a queued cancel produces no Redis terminal event; SSE
closes via `stream_lost` rather than a `cancelled` payload) is the
brief-P2-1-sanctioned OR-branch — terminal detection includes `cancelled`
(`run_events.py`), the status API is correct. Left as the accepted residual
Codex itself classified non-blocking; a `cancelled` SSE payload from the
endpoint would add Redis coupling to the API process.

## §1. What to review

The diff for #507 against the brief APPROVE'd at brief-iter 1
(`.codex/I-rdy-011/codex_brief_verdict.txt`). Canonical diff:
`.codex/I-rdy-011/codex_diff.patch`, trailer
`# canonical-diff-sha256: 728c4c674d395bc608f57d0c6cb1b26107d1e8cb59ebb0a37755575ea483641d`
= sha256 of `git diff origin/polaris...HEAD -- ':(exclude).codex/I-rdy-011/'
':(exclude)outputs/audits/I-rdy-011/'`.

9 code files (commits `5d1df254` + `43511151`; `eccfe85d` = the APPROVE'd
brief, excluded from the canonical diff). Scope (brief-APPROVE'd): cancel
only — queued T1 + cooperative in-progress T2 + UI. T3 + resume carved.

## §2. Implementation map

**`run_store.py`** — `cancel_requested` column (additive migration);
`request_cancel` (queued→cancelled atomic / in_progress→flag);
`is_cancel_requested`; `mark_cancelled`; `mark_in_progress` is a CAS
(`WHERE lifecycle_status='queued' AND cancel_requested=0`, returns bool —
P2-2). `get_run` + `_row_to_response` carry `cancel_requested`.
`TERMINAL_STATUSES` public.

**`run_status.py`** — `RunStatusResponse.cancel_requested: bool` (P2-3).

**`api/runs.py`** — `POST /runs/{id}/cancel`: 404 / terminal-noop / else
`request_cancel`.

**`actors.py`** — cancel detected via `is_cancel_requested` (two checks
bracketing `mark_in_progress`; CAS return NOT interpreted — diff-iter-1 P1-1).
Manifest `status == "cancelled"` → `mark_cancelled` (actor-special-case).

**`run_honest_sweep_r3.py`** — `_abort_if_cancelled` helper + **three**
cooperative checkpoints: pre-retrieval, pre-generation, and post-generation/
pre-evaluator (the third added for diff-iter-1 P1-2). Writes a terminal
`cancelled` manifest + emits `run.completed(status=cancelled)`.

**`run_events.py`** — `_check_lifecycle_terminal` includes `cancelled` (P2-1).

**`web/lib/api.ts`** — `cancelRun`; `RunStatusResponse.cancel_requested?`.
**`web/app/runs/[runId]/page.tsx`** — Cancel button enabled + wired,
disabled when terminal.

**`tests/v6/test_cancellation.py`** (new) — 16 tests.

## §3. Test evidence

`tests/v6/test_cancellation.py` — **16/16 pass** offline (the 15 from
diff-iter-1 + `test_actor_retry_of_failed_run_not_marked_cancelled`).
`test_actors.py` 8/8; `test_dramatiq_acceptance.py` scenario 1 pass, 7 xfail
unchanged — no regression. Import smoke clean on the touched backend modules.
`web/`: `typecheck` + `eslint` clean (verified diff-iter-1; no frontend change
since).

A full live in-progress cancel (real pipeline, cancel mid-flight) needs
network + the generator API — CI/e2e, not the autonomous loop.

## §4. Points to scrutinise

1. **P1-1 fix** — the actor now never interprets the `mark_in_progress` CAS
   return; cancellation is `is_cancel_requested`-only, checked before AND
   after `mark_in_progress`. Confirm a retry of a `failed` / `completed` run
   can no longer be rewritten to `cancelled`.
2. **P1-2 fix** — three checkpoints now (pre-retrieval, pre-generation,
   post-generation/pre-evaluator). Confirm a cancel during the generation
   stage is observed at the third checkpoint.
3. **No-cancel regression** — `_abort_if_cancelled` False at all three
   checkpoints; `mark_in_progress` CAS True for a normal queued run; the
   actor's two `is_cancel_requested` checks both False → pipeline runs
   normally. (test_actors 8/8 + dramatiq scenario-1 pass.)
4. Any remaining P0/P1 execution risk.

## §5. Adjacent-file scan — checked, clean

`tests/v6/acceptance/test_dramatiq_acceptance.py` (scenario 3/4/5 xfail —
carved), `src/polaris_v6/api/app.py` (runs router mounted), `src/polaris_v6/
api/stream.py` (SSE — unchanged), `web/app/runs/[runId]/graph/page.tsx`
(separate graph view — untouched).

## §6. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
