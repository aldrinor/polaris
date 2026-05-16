# Codex BRIEF review — I-rdy-011 (#507): implement cancellation/resume

**Type:** BRIEF review (acceptance-criteria + scope correctness). Phase 3.8 of the
Carney demo execution plan. iter 1 of 5.

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

This brief carries a **scope decision** (§3) — #507 names two features and one of
them (resume) is genuinely infrastructure-blocked. Please rule `scope_ruling`.

## §1. Issue + acceptance

GH #507 (I-rdy-011, Phase 3.8): "Implement the disabled UI cancel path and the
xfailed backend resume behaviour. **Acceptance: a run can be cancelled in under
5s and resumed from checkpoint; Codex APPROVE.**" Depends on I-rdy-003 (done).

## §2. Grounded current state (all files read)

**Cancel surfaces — nothing is wired:**
- `web/app/runs/[runId]/page.tsx:166-173` — a `<Button disabled
  title="Phase 1: cancel a queued or in-progress run">Cancel run</Button>`.
  The "disabled UI cancel path."
- `src/polaris_v6/api/runs.py` — only `POST /runs` + `GET /runs/{id}`. **No
  `/runs/{id}/cancel`.**
- `src/polaris_v6/queue/run_store.py` — `insert_run` / `mark_in_progress` /
  `set_pipeline_meta` / `mark_completed` / `mark_aborted` / `mark_failed` /
  `get_run`. **No cancel method, no cancel column.** `_migrate_schema` is
  idempotent-additive (the `ADD COLUMN for each missing` loop) — a
  `cancel_requested` column is a clean additive migration.
- `src/polaris_v6/schemas/run_status.py` — `LifecycleStatus` **already
  includes `"cancelled"`** (unused today).
- `src/polaris_v6/queue/actors.py:214` — `cancel_research_run` actor is a
  **stub**: returns `{"status": "cancel_requested"}`, docstring says "real
  cancellation is via Worker.send_signal on the target message_id". The
  `enqueue_research_run` actor (`:71`) does NOT check any cancel flag.

**Resume surfaces — infrastructure-blocked:**
- `tests/v6/acceptance/test_dramatiq_acceptance.py` — scenarios 2-8 are
  `@pytest.mark.xfail` stubs that `raise NotImplementedError`. The resume/cancel
  ones: scenario 3 `test_scenario_3_cancel_mid_execution` (xfail: "requires
  Worker.send_signal against real broker — Task 0.3"); scenario 4
  `test_scenario_4_worker_kill_resume` (xfail: "requires SIGKILL fixture +
  idempotency key store — Task 0.3"); scenario 5
  `test_scenario_5_resume_after_broker_restart` (xfail: "requires
  ConnectionMiddleware + broker restart fixture — Task 0.3"). The file header:
  scenarios 2-8 are "xfail until the Vast.ai dev cluster (Task 0.3) is live
  with real Redis + multi-worker Dramatiq."
- **Pipeline-A has no checkpoint mechanism.** `grep -rn "checkpoint"
  scripts/run_honest_sweep_r3.py src/polaris_v6/` → zero hits. `run_one_query`
  is a linear ~1500-line async function; it cannot be resumed from a partial
  state. Resume-from-checkpoint is not a wiring task — it is a major new
  pipeline-A capability.

**Conclusion:** the cancel half is buildable now without real infra
(cooperative cancellation — a DB flag, not `Worker.send_signal`). The resume
half (scenarios 4/5) needs BOTH (a) a pipeline-A checkpoint capability that does
not exist AND (b) the Vast.ai real-Redis multi-worker cluster — the hardware
track (#85-91) the demo execution plan defers. It cannot land in #507's PR.

## §3. The scope decision — Codex please rule `scope_ruling`

The cancel path has three tiers of difficulty:

| Tier | What | Feasible without Vast.ai cluster? |
|---|---|---|
| **T1** queued-run cancel | a not-yet-started run cancels **instantly** | Yes — DB flag + actor checks it at pickup |
| **T2** in-progress cooperative abort | `run_one_query` polls the cancel flag at stage boundaries, aborts at the next one | Yes — cooperative poll, StubBroker-testable |
| **T3** hard-kill mid-LLM-call | interrupt a run *inside* a 30s external LLM call, <5s | **No** — needs `Worker.send_signal` + real broker (xfail scenario 3) |
| **Resume** from checkpoint | resume a partial run after worker kill / broker restart | **No** — needs pipeline-A checkpoint infra (absent) + real Redis cluster (xfail 4/5) |

- **Option A (recommended).** #507 ships **T1 + T2 + the UI** — a real,
  demoable cancel: queued runs cancel instantly; an in-progress run's cancel
  request is recorded in <5s and the run aborts at the next pipeline stage
  boundary; the UI "Cancel run" button is enabled and wired. The cooperative
  cancel path is testable on StubBroker (un-xfail scenario 3 *for the
  cooperative mechanism*, or add a dedicated test). **T3 (hard-kill mid-LLM)
  and Resume-from-checkpoint are carved into a follow-up issue** explicitly
  dependent on the Vast.ai real-Redis cluster (#85-91 track) + new pipeline-A
  checkpoint infrastructure. #507's acceptance is met as "cancel in <5s"
  (instant for queued, request-registered + cooperative-abort for in-progress);
  "resumed from checkpoint" moves to the carved issue.
- **Option B.** Attempt cancel + resume in #507. Rejected: resume needs
  infrastructure that does not exist and is hardware-gated — it cannot be
  delivered or even tested in this PR. Forcing it would mean shipping an
  xfail-still-xfail no-op, which is dishonest against the acceptance.
- **Option C.** Codex's call.

**Recommendation: A.** It delivers a genuine, demo-usable cancel feature now,
and is honest that resume-from-checkpoint is a separate infra-gated build
rather than pretending a no-op satisfies the acceptance.

## §4. Implementation plan — Option A (if Codex rules A)

1. **`run_store.py`** — additive `cancel_requested INTEGER DEFAULT 0` column via
   `_migrate_schema`; `request_cancel(run_id)` (sets the flag; if the run is
   still `queued`, also sets `lifecycle_status='cancelled'` + `finished_at` —
   instant T1 cancel); `is_cancel_requested(run_id) -> bool`;
   `mark_cancelled(run_id)` (terminal `cancelled` + `finished_at`).
2. **`POST /runs/{run_id}/cancel`** (`runs.py`) — 404 if unknown; idempotent
   no-op (200, current record) if already terminal; else `request_cancel` →
   return the updated record. Status 200.
3. **`enqueue_research_run`** — before `mark_in_progress`/the pipeline, check
   `is_cancel_requested`; if set, `mark_cancelled` and return without running
   pipeline-A (closes the queued→cancel-before-pickup race — T1).
4. **`run_one_query` cooperative abort (T2)** — at existing stage boundaries
   (post scope-gate, post-retrieval, post-corpus-gate, per-section), when
   `q.get("v6_mode")` and `q.get("external_run_id")`, poll
   `run_store.is_cancel_requested`; on cancel write a terminal manifest
   (`status: "cancelled"`) and return early. The actor maps a `cancelled`
   manifest status → `mark_cancelled`. ~4-6 poll points; bounded.
5. **Frontend** — `web/lib/api.ts` `cancelRun(runId)`; `runs/[runId]/page.tsx`
   enable the "Cancel run" button (shown only for non-terminal status),
   `onClick` → `cancelRun` → refresh status. Disable/hide once terminal.
6. **Tests** (`tests/v6/`) — `run_store` cancel methods; `POST /runs/{id}/cancel`
   404 / terminal-noop / queued→cancelled; the actor honors a pre-set cancel
   flag (queued→cancelled, pipeline not run); a `run_one_query`-level
   cooperative-abort unit test if feasible offline (stub the stage). Convert /
   replace the xfail scenario-3 stub for the cooperative mechanism. Frontend
   typecheck + lint.

LOC estimate: ~200-260 (run_store + endpoint + actor + run_one_query poll +
frontend + tests). May need a cap-exemption — flagged for Codex.

## §5. Adjacent-file scan — files I have ALSO checked and they're clean

`src/polaris_v6/queue/actors.py` (`cancel_research_run` stub + `enqueue_research_run`),
`src/polaris_v6/schemas/run_status.py` (`cancelled` lifecycle value exists),
`src/polaris_v6/queue/run_store.py` (`_migrate_schema` additive pattern),
`tests/v6/acceptance/test_dramatiq_acceptance.py` (xfail scenario matrix),
`web/app/runs/[runId]/page.tsx` (disabled cancel button), `web/lib/api.ts`
(no `cancelRun` yet). The SSE terminal-event path (`run_events.py`) +
`run_one_query` exact stage boundaries will be read at implement time.

## §6. Questions for Codex

1. **`scope_ruling`** — A (cancel T1+T2 now, carve T3+resume), B, or C?
   (Recommendation: A.)
2. Is T2 (in-progress cooperative abort — poll points inside `run_one_query`)
   in #507 scope, or should #507 ship only T1 (queued cancel) + the UI and
   carve T2 as well? (Recommendation: T1+T2 — T2 is a bounded ~4-6-poll-point
   change and without it "cancel an in-progress run" is unmet.)
3. For the cooperative-cancel manifest: a new `PipelineStatus` value
   (`cancelled`) vs the actor special-casing a `cancelled` manifest `status`
   without a schema change — preference?
4. `loc_disposition` — single PR with cap-exemption if ~250 LOC, or carve?
5. Any P0/P1 execution risk.

## §7. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
scope_ruling: <option-A | option-B | option-C + reasoning>
t2_ruling: <t2-in-scope | t2-carve + reasoning>
cancelled_status_ruling: <new-pipelinestatus | actor-special-case>
loc_disposition: <single-pr-cap-exemption | carve + reasoning>
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
