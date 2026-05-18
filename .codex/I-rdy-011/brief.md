# Codex BRIEF review — GH #507 (I-rdy-011): implement run cancellation/resume

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Review-stage **brief** — reviewing the *plan + recut rationale*. This is a
**recut** of an already-Codex-APPROVE'd implementation (see §1); the code
already exists on the branch. You are confirming the recut is faithful, the
polaris-HEAD divergence (incl. the #506 overlap) was handled correctly, and
the scope is honest. The diff gets a separate Codex diff review next.

## 1. Why this is a recut (front-loaded so you VERIFY)

#507 was implemented as PR #538 (`bot/I-rdy-011-cancellation-resume`). That
PR earned **Codex brief APPROVE iter-1 AND Codex diff APPROVE** — its diff
review ran THREE iterations (iter-1 P1 false-cancel-on-retry fix; iter-2 P1
late-stage-cancel backstop fix; iter-3 APPROVE). PR #538 is now unmergeable:

1. **42 commits stale** behind `polaris`.
2. **Verdict-only-rule violation** — `.codex/I-rdy-011/` committed
   `codex_brief_verdict.txt` (6937 lines) + `codex_diff_audit{,_iter_1,_iter_2,
   _iter_3}.txt` (12k–14k lines each) — ~65k lines of RAW Codex transcripts,
   not the ~7-line slim YAML verdict. Raw transcripts must never reach
   `polaris` (CLAUDE.md §8.3; the raw-transcript secret-exposure surface is
   #535).

Decision (same as #506's recut, Codex-advisor-confirmed): **recut** onto a
clean `bot/I-rdy-011` off current `polaris` HEAD `fbcfb630`, re-applying
#538's APPROVE'd #507 source with proper slim verdict artifacts. PR #538 is
closed.

### 1.1 Recut fidelity — how the 10 files were re-applied

`polaris`'s 42 commits touched 5 of the 9 #538 source files. **Note: 3 of
those 5 (`runs.py`, `actors.py`, `run_honest_sweep_r3.py`) diverged because
#506 (I-rdy-010, merged THIS session as PR #601) modified them** — so #507's
cancellation deltas had to be layered ON TOP of #506's document-grounding
changes.

- **4 re-applied verbatim** (`git checkout` from #538 — polaris did not
  touch them): `queue/run_events.py`, `queue/run_store.py`,
  `tests/v6/test_cancellation.py` (new), `web/app/runs/[runId]/page.tsx`.
- **5 re-anchored manually** onto current HEAD: `schemas/run_status.py`
  (1 hunk — `cancel_requested` field), `web/lib/api.ts` (2 hunks —
  `cancel_requested` field + `cancelRun`), `api/runs.py` (docstring + the
  `cancel_run` endpoint appended AFTER #506's `create_run` changes),
  `queue/actors.py` (3 hunks — the cancel checks bracket #506's
  sovereignty-partition block, distinct regions), `run_honest_sweep_r3.py`
  (`_abort_if_cancelled` def + 3 stage-boundary checkpoints — the
  before-generator checkpoint sits right after #506's upload-evidence
  block, distinct region). Every hunk anchor verified against current HEAD.
- **1 NEW file vs #538** — `tests/v6/acceptance/test_runs_db_integration.py`:
  `test_init_db_creates_schema` asserts the `runs` column set; #507 adds
  the `cancel_requested` column, so the expected set needed it.
  **#538 missed this** — #538's `pytest tests/v6/` CI skips (via the
  pip-dry-run `needs:` dependency, #494), so it never ran the schema test.
  This recut's OFFLINE smoke caught it. The fix is one line added to the
  expected set.

## 2. Issue + acceptance

#507 (I-rdy-011, Phase 3.8): "Implement the disabled UI cancel path and the
xfailed backend resume behaviour. Acceptance: a run can be cancelled in
under 5s and resumed from checkpoint; Codex APPROVE." Depends on I-rdy-007
(#503, CLOSED).

## 3. The change (10 files, +589/-35)

`POST /runs/{id}/cancel` + a cooperative-cancel contract through the v6
worker + pipeline-A:

- **`run_store.py`** — new `cancel_requested` column; `request_cancel`
  (queued → terminal `cancelled` atomically T1; in_progress → set the flag
  T2); `mark_in_progress` is now a **compare-and-swap** (`WHERE
  lifecycle_status='queued' AND cancel_requested=0`) so a queued cancel
  cannot be overwritten by a worker pickup; `is_cancel_requested` /
  `mark_cancelled`; `TERMINAL_STATUSES` exported.
- **`api/runs.py`** — `POST /runs/{id}/cancel`: unknown→404,
  terminal→idempotent no-op (200), queued→instant, in_progress→cooperative.
- **`actors.py`** — `enqueue_research_run` honors a pre-start cancel (the
  pre- and post-`mark_in_progress` checks, detected ONLY via
  `is_cancel_requested` — NEVER the CAS return, which is also False for a
  retry of an already-terminal run: Codex diff-iter-1 P1); plus an
  actor-side **backstop** after `run_one_query` so a cancel at ANY stage
  (incl. the late evaluator stage past the last checkpoint) wins over a
  success/abort manifest (Codex diff-iter-2 P1); maps a pipeline-A
  `cancelled` manifest → `mark_cancelled`.
- **`run_honest_sweep_r3.py`** — `_abort_if_cancelled` cooperative
  checkpoint at 3 stage boundaries (before retrieval / generator /
  evaluator); writes a terminal `cancelled` manifest + emits the SSE
  terminal event; best-effort (a run_store hiccup never aborts a healthy
  run); v6-only (`v6_mode` + `external_run_id` gate).
- **`run_events.py`** — `cancelled` is terminal for the SSE consumer
  (a queued-cancel writes no Redis terminal event).
- **`run_status.py` / `api.ts`** — `cancel_requested` surfaced so the UI
  shows a cancel in-flight in <5s; `cancelRun` client + run-page button.
- **`test_cancellation.py`** (new, 17 tests) + the
  `test_runs_db_integration.py` schema-assertion fix.

## 4. Scope boundary — #507 vs #539 (Codex: confirm)

#507 is **in-process cooperative cancellation** (queued instant + 3
stage-boundary checkpoints + actor backstop). The "resumed from checkpoint"
half of the acceptance and a true mid-stage **hard-kill** are carved to
**#539** (I-rdy-011-followup, "hard-kill mid-execution +
resume-from-checkpoint, infra-gated") — #539 is infra-gated and out of
#507. #507 delivers: cancel <5s for a queued run (instant) and for an
in-progress run at the next stage boundary; the cooperative contract is the
shippable core. Codex: confirm this boundary is honest and #507 is not
under-scoped for "cancellation/resume".

## 5. Smoke

`ast.parse` 7/7 clean. `PYTHONPATH='src;.' pytest
tests/v6/test_cancellation.py` 17/17; `test_runs_db_integration.py` 4/4;
55 adjacent v6 tests (test_actors, test_api_health_and_runs, …) green. Web:
prettier, `npm run lint` (0 errors, 3 pre-existing warnings), `tsc
--noEmit` clean, `npm run build` succeeded.

## 6. Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/broker.py` — broker init; unchanged.
- `src/polaris_v6/api/upload.py`, `adapters/upload_evidence.py` — #506
  surface; the #507 actor/runs deltas layer onto #506's regions without
  touching them; NOT modified.
- `src/polaris_v6/schemas/run_request.py` — unchanged.
- `tests/v6/test_actors.py`, `test_api_health_and_runs.py`,
  `test_document_grounding.py` — adjacent suites; run green; NOT modified.

## 7. Output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
