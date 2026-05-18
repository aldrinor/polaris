# Codex BRIEF review — GH #509 (I-rdy-013): 1-concurrent-session enforcement + queue/rejection UX

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
exists on the branch. Confirm the recut is faithful, the #509↔#505/#506/#507
layering is correct, and the scope is honest. The diff gets a separate Codex
diff review next.

## 1. Why this is a recut (front-loaded so you VERIFY)

#509 was implemented as PR #541 (`bot/I-rdy-013-concurrent-session-limit`).
That PR earned **Codex brief APPROVE iter-3 AND Codex diff APPROVE iter-2**.
PR #541 is now unmergeable:

1. **44 commits stale** behind `polaris`.
2. **Verdict-only-rule violation** — `.codex/I-rdy-013/` committed
   `codex_brief_verdict.txt` (1.2 MB) + `codex_diff_audit.txt` (2.4 MB) +
   `_iter_*` duplicates — raw Codex transcripts, not the ~130-byte slim YAML
   verdict (CLAUDE.md §8.3; the raw-transcript secret-exposure surface is
   #535).

Decision (same as the #506/#507/#508 recuts, Codex-advisor-confirmed):
**recut** onto a clean `bot/I-rdy-013` off current `polaris` HEAD
`7b504cc2`, re-applying #541's APPROVE'd #509 source with proper slim
verdict artifacts. PR #541 is closed.

### 1.1 Recut fidelity — the #505/#506/#507 layering

`polaris`'s 44 commits touched 4 of the 6 #541 source files — all 4
diverged because issues that merged THIS session modified them:

- **2 re-applied verbatim** (`git checkout` — polaris did not touch them):
  `tests/v6/conftest.py`, `tests/v6/test_concurrency.py`.
- **`run_store.py`** — #507 (I-rdy-011) already added `_RUN_COLUMNS`
  (16-col, incl. `cancel_requested`) + `_row_to_response` (16-field) + the
  CAS `mark_in_progress`. #541's delta ALSO adds `_RUN_COLUMNS` /
  `_row_to_response` (its 15-col pre-#507 versions). The recut applies ONLY
  #509's net-new pieces — `_ACTIVE_STATUSES`, `_INIT_LOCK`, `import
  threading`, `_connect` `busy_timeout` PRAGMA, `init_db` `_INIT_LOCK`
  wrap, `insert_run` docstring, `insert_run_if_idle`, `get_active_run` —
  and KEEPS #507's 16-col `_RUN_COLUMNS` / `_row_to_response`.
  `insert_run_if_idle` / `get_active_run` SELECT `{_RUN_COLUMNS}` (the
  16-col version) and call `_row_to_response` — consistent.
- **`api/runs.py`** — #506 prepended `_resolve_uploaded_documents` +
  `actor_payload["uploaded_documents"]`; #507 appended `cancel_run`. #509's
  `create_run` change (swap `insert_run`→`insert_run_if_idle`; 409 on a
  non-None active; wrap `enqueue` in try/except) is layered onto #506's
  `create_run` — the `enqueue` try/except wraps #506's
  `enqueue_research_run.send(run_id, actor_payload)`.
- **`web/lib/api.ts`** — #507 added `cancelRun` + `cancel_requested`; #509's
  `ConcurrentRunError` + the `createRun` 409-unwrap are re-anchored.
- **`web/app/dashboard/page.tsx`** — #505 wired the DisambiguationModal;
  #509's `concurrentRun` state + the `ConcurrentRunError` catch + the
  callout are re-anchored onto #505's heavily-modified `onSubmit`.

## 2. Issue + acceptance

#509 (I-rdy-013, Phase 3.10): "Enforce the locked 1-concurrent-session
constraint; a second concurrent request is queued or cleanly rejected with
UX. Acceptance: a second concurrent request is handled gracefully (no crash,
clear UX); Codex APPROVE." Depends on I-rdy-007 (#503, CLOSED).

## 3. The change (6 files, +517/-32)

- **`run_store.py`** — `insert_run_if_idle`: atomic check-and-insert inside
  ONE `BEGIN IMMEDIATE` transaction; `conn.isolation_level = None` for
  manual transaction control (the only correct way to get explicit-txn
  semantics from Python's sqlite3). Returns the blocking active
  `RunStatusResponse` when rejected, `None` when inserted. `get_active_run`
  read-side helper. `_connect` `PRAGMA busy_timeout=5000` (a concurrent
  writer waits, never SQLITE_BUSY-crashes). `init_db` `_INIT_LOCK`-serialized.
- **`api/runs.py`** — `create_run` 409s on a non-None active run with a
  structured `detail`; a failed `enqueue` marks the committed row failed
  (frees the slot) then 503s.
- **`api.ts`** / **`page.tsx`** — `ConcurrentRunError` + the dedicated
  rejection callout.
- **`conftest.py`** — autouse `_isolated_run_db` (per-test temp run DB —
  mandatory: the 1-session gate would make a leftover `queued` row from an
  earlier test 409 a later test's POST /runs).
- **`test_concurrency.py`** (NEW) — concurrency tests.

## 4. Scope boundary (Codex: confirm)

The issue says "queued OR cleanly rejected". #509 implements **cleanly
rejected** (HTTP 409 + UX) — not server-side queueing. A real
multi-run queue is larger scope; the 1-concurrent-session constraint is
"locked" per the issue, so rejection (not queueing) is the honest minimal
satisfaction of "handled gracefully (no crash, clear UX)". #552 (excluded)
is a SEPARATE asyncio-teardown concurrency bug, not this. Codex: confirm
rejection-not-queue is acceptable for #509's acceptance.

## 5. Smoke

`ast.parse` 4/4. `PYTHONPATH='src;.' pytest tests/v6/` — **499 passed, 4
skipped, 7 xfailed** (the whole v6 directory, because the new autouse
`conftest._isolated_run_db` fixture changes the run-DB contract for every
v6 test — no regression, the fixture composes with
`test_runs_db_integration.py`'s own `isolated_db`). Web: prettier, `npm run
lint` (0 errors, 3 pre-existing warnings), `tsc --noEmit` clean, `npm run
build` succeeded.

## 6. Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/actors.py` — `mark_in_progress` CAS (#507) is
  unchanged; the actor still transitions queued→in_progress; NOT modified.
- `src/polaris_v6/schemas/run_status.py` — `RunStatusResponse`; consumed
  as-is; NOT modified.
- `tests/v6/acceptance/test_runs_db_integration.py` — has its own
  `isolated_db` fixture; composes with the new autouse `_isolated_run_db`
  (both point `POLARIS_V6_RUN_DB` at a tmp path); runs green; NOT modified.

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
