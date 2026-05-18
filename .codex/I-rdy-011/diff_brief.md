# Codex DIFF review — GH #507 (I-rdy-011): implement run cancellation/resume

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #507 (I-rdy-011) — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-011/` and `outputs/audits/I-rdy-011/` (canonical
diff in `.codex/I-rdy-011/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-011/brief.md` (brief APPROVE iter 1; 0
P0/P1, 1 non-blocking P2). **10 files, +589/-35.**

## 2. Recut provenance (front-loaded so you VERIFY)

This is a **recut** of PR #538 (`bot/I-rdy-011-cancellation-resume`), which
earned Codex brief APPROVE iter-1 + **diff APPROVE across 3 iters** for this
exact #507 implementation:
- #538 diff-iter-1 P1: false-cancel on retry — fixed (the actor detects
  cancellation ONLY via `is_cancel_requested`, never the `mark_in_progress`
  CAS return).
- #538 diff-iter-2 P1: late-stage cancel — fixed (an actor-side backstop
  after `run_one_query`).
- #538 diff-iter-3: APPROVE.

PR #538 became unmergeable (42 commits stale; its `.codex/` committed ~65k
lines of raw Codex transcripts — a verdict-only-rule violation). The recut
re-applies #538's APPROVE'd source onto current `polaris` HEAD `fbcfb630`.
This is the same code Codex already diff-APPROVE'd on #538 (both P1 fixes
included); your job is to confirm the re-application is faithful and
introduced no NEW P0/P1 — paying attention to the #506-overlap layering.

### 2.1 Re-application detail

`polaris`'s 42 commits touched 5 of 9 #538 source files; 3 of them
(`runs.py`, `actors.py`, `run_honest_sweep_r3.py`) diverged because **#506
(I-rdy-010) merged this session and modified them**. #507's cancellation
deltas were layered on #506's document-grounding changes:
- `runs.py` — `cancel_run` endpoint appended after #506's `create_run`;
  module docstring carries both I-rdy-010 + I-rdy-011 paragraphs.
- `actors.py` — the pre-start cancel checks bracket the `mark_in_progress`
  call (before #506's sovereignty block); the backstop is in the
  manifest-dispatch section (after #506's region). Distinct regions.
- `run_honest_sweep_r3.py` — the before-generator checkpoint sits right
  AFTER #506's upload-evidence block, before `multi = await
  generate_multi_section_report(`. Distinct region.
- 4 files (`run_events.py`, `run_store.py`, `test_cancellation.py`,
  `web/app/runs/[runId]/page.tsx`) re-applied verbatim from #538.
- 1 NEW file vs #538 — `tests/v6/acceptance/test_runs_db_integration.py`:
  `test_init_db_creates_schema` needed `cancel_requested` in its expected
  column set. #538 missed it (its `pytest tests/v6/` CI skips via the
  pip-dry-run `needs:` dependency, #494); this recut's offline smoke
  caught it.

## 3. The change

`POST /runs/{id}/cancel` + a cooperative-cancel contract — see brief §3.
Key invariants:
- `run_store.mark_in_progress` is a compare-and-swap (`WHERE
  lifecycle_status='queued' AND cancel_requested=0`).
- `request_cancel`: queued → terminal `cancelled` atomically; in_progress →
  flag set.
- The actor detects cancellation via `is_cancel_requested` ONLY (never the
  CAS return) + an after-`run_one_query` backstop.
- `_abort_if_cancelled` — v6-only, best-effort, at 3 stage boundaries.

## 4. Verify

1. **Cancel <5s.** A queued cancel is one atomic UPDATE → terminal; an
   in_progress cancel sets the flag immediately (surfaced in the response).
2. **No queued-cancel race.** The `mark_in_progress` CAS — confirm a queued
   cancel that flipped the row to `cancelled` cannot be resurrected.
3. **False-cancel-on-retry guarded (#538 P1).** Confirm the actor never
   infers cancellation from the `mark_in_progress` CAS return — a retry of
   an already-`failed`/`completed` run must NOT become `cancelled`.
4. **Late-stage backstop (#538 P1).** Confirm a cancel at the late
   evaluator stage (past the last `_abort_if_cancelled` checkpoint) still
   wins over a success/abort manifest via the actor's post-run re-check.
5. **Cooperative abort safety.** `_abort_if_cancelled` is best-effort (a
   run_store hiccup never aborts a healthy run) and v6-gated.
6. **SSE terminal.** `cancelled` is terminal in `_check_lifecycle_terminal`
   — a queued-cancel (no Redis terminal event) does not hang the consumer.
7. **Recut fidelity / #506 overlap.** Confirm the 5 re-anchored files layer
   #507's deltas onto #506's regions without altering #506's behavior, and
   the 10-file diff matches #538's APPROVE'd #507 implementation.
8. **Scope.** The "resume from checkpoint" + mid-stage hard-kill are #539
   (infra-gated), out of #507 — confirm not a P0/P1 that must block.

## 5. Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/broker.py`, `schemas/run_request.py`,
  `api/upload.py`, `adapters/upload_evidence.py` — consumed/adjacent, NOT
  modified.
- `tests/v6/test_actors.py`, `test_api_health_and_runs.py`,
  `test_document_grounding.py` — adjacent suites; run green; NOT modified.

## 6. Smoke state

`ast.parse` 7/7. `pytest tests/v6/test_cancellation.py` 17/17 +
`test_runs_db_integration.py` 4/4 + 55 adjacent v6 tests green. Web
prettier / lint (0 err) / tsc / build green.

## 7. Required output schema (§8.3.9)

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
