# Codex DIFF review — GH #509 (I-rdy-013): 1-concurrent-session enforcement + queue/rejection UX

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #509 (I-rdy-013) — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-013/` and `outputs/audits/I-rdy-013/` (canonical
diff in `.codex/I-rdy-013/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-013/brief.md` (brief APPROVE iter 1; 0
P0/P1/P2). **6 files, +517/-32.**

## 2. Recut provenance (front-loaded so you VERIFY)

Recut of PR #541 (`bot/I-rdy-013-concurrent-session-limit`), which earned
Codex brief APPROVE iter-3 + **diff APPROVE iter-2** for this exact #509
implementation. PR #541 became unmergeable (44 commits stale; its `.codex/`
committed 1.2 MB / 2.4 MB raw Codex transcripts — verdict-only-rule
violation). The recut re-applies #541's APPROVE'd source onto current
`polaris` HEAD `7b504cc2`.

### 2.1 The #505/#506/#507 layering (the verification focus)

All 4 polaris-touched source files diverged because issues that merged THIS
session modified them:
- **`run_store.py`** — #507 (I-rdy-011) already added `_RUN_COLUMNS`
  (16-col, incl. `cancel_requested`) + `_row_to_response` (16-field). #541's
  delta also added them (15-col pre-#507). The recut applied ONLY #509's
  net-new pieces (`_ACTIVE_STATUSES`, `_INIT_LOCK`, `import threading`,
  `_connect` `busy_timeout`, `init_db` `_INIT_LOCK` wrap, `insert_run`
  docstring, `insert_run_if_idle`, `get_active_run`) and KEPT #507's
  16-col `_RUN_COLUMNS` / `_row_to_response`. **Verify**: `insert_run_if_idle`
  and `get_active_run` SELECT `{_RUN_COLUMNS}` (16-col) and pass the row to
  `_row_to_response` (16-field, reads `cancel_requested`) — consistent, no
  duplicate definition.
- **`api/runs.py`** — #509's `create_run` change layered onto #506's
  `create_run` (which prepends `_resolve_uploaded_documents` + builds
  `actor_payload` with `uploaded_documents`). The `enqueue` try/except
  wraps #506's `enqueue_research_run.send(run_id, actor_payload)`.
- **`api.ts`** layered on #507 (`cancelRun`); **`page.tsx`** layered on
  #505 (DisambiguationModal `onSubmit`).
- 2 test files re-applied verbatim.

## 3. The change

- **`run_store.py`** — `insert_run_if_idle` (atomic `BEGIN IMMEDIATE`
  check-and-insert; `conn.isolation_level = None` for manual txn control);
  `get_active_run`; `_connect` `PRAGMA busy_timeout=5000`; `init_db`
  `_INIT_LOCK`-serialized. `insert_run` kept as the unconditional primitive.
- **`api/runs.py`** — `create_run` 409s on a non-None active run with a
  structured `detail`; failed `enqueue` → `mark_failed` (frees the slot) +
  503.
- **`api.ts`** — `ConcurrentRunError` + `createRun` 409-unwrap.
- **`page.tsx`** — `ConcurrentRunError` catch + rejection callout.
- **`conftest.py`** — autouse `_isolated_run_db`; **`test_concurrency.py`**
  (new).

## 4. Verify

1. **Atomic gate.** `insert_run_if_idle` — the active-run SELECT and the
   INSERT are inside ONE `BEGIN IMMEDIATE`; two concurrent `POST /runs`
   cannot both pass (the 2nd blocks on the write lock, then sees the row).
   Confirm `conn.isolation_level = None` + manual `BEGIN/COMMIT/ROLLBACK` is
   correct (it is — Python sqlite3 autocommit cannot express explicit-txn
   semantics; `BEGIN IMMEDIATE` is per SQLite docs).
2. **No crash.** `busy_timeout=5000` — a concurrent writer waits, never
   `SQLITE_BUSY`-crashes. `init_db` `_INIT_LOCK`-serialized.
3. **Clean UX.** 409 structured `detail` → `ConcurrentRunError` →
   dedicated callout with a link to the active run.
4. **Enqueue-failure frees the slot (#541 diff P1-001).** A failed
   `enqueue` `mark_failed`s the committed row (terminal) then 503s.
   Confirm the 409 branch does NOT `mark_failed` (no row was inserted —
   `insert_run_if_idle` rolled back, returned the existing active record).
5. **run_store.py overlap.** No duplicate `_RUN_COLUMNS` / `_row_to_response`;
   #507's 16-col versions are intact; the new helpers are consistent with
   them.
6. **conftest autouse fixture.** `_isolated_run_db` per-test temp DB —
   confirm it composes (no double-monkeypatch breakage) with
   `test_runs_db_integration.py`'s `isolated_db`.
7. **Recut fidelity.** The 6-file diff matches #541's APPROVE'd #509
   implementation.

## 5. Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/actors.py` — `mark_in_progress` CAS (#507); the
  actor still works against the new `insert_run_if_idle`-gated rows; NOT
  modified.
- `src/polaris_v6/schemas/run_status.py` — NOT modified.
- `tests/v6/acceptance/test_runs_db_integration.py` — composes with the new
  autouse fixture; runs green; NOT modified.

## 6. Smoke state

`ast.parse` 4/4. `pytest tests/v6/` — 499 passed, 4 skipped, 7 xfailed
(whole dir). Web prettier / lint (0 err) / tsc / build green.

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
