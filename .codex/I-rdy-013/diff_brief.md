# Codex DIFF review — I-rdy-013 (#509): 1-concurrent-session enforcement

## §0. HARD ITERATION CAP (verbatim, CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**This is iter 2 of 5.** This is a DIFF review (code correctness vs the
APPROVE'd brief), not a brief review.

## §0.5 Changes since diff iter 1

iter 1 = REQUEST_CHANGES, 1 P1:
- **P1-001 (orphan queued row):** if `enqueue_research_run.send()` failed
  after `insert_run_if_idle` committed the `queued` row, that run would
  never run yet would hold the session slot forever. **Fixed:** `create_run`
  now wraps the `send` call in `try/except`; on failure it calls
  `run_store.mark_failed(run_id, ...)` (terminal → frees the slot) then
  raises `HTTPException(503)`. New regression test
  `test_post_frees_slot_when_enqueue_fails` (patches `send` to raise,
  asserts 503 + `get_active_run() is None` + a subsequent POST → 202).

## §1. What to review

The diff to review is `.codex/I-rdy-013/codex_diff.patch`
(canonical-diff-sha256 trailer = `95f1948b91a38b848e223e8e9d9b4a7334ee407bb1dad1f595f64e55a19b370d`).
The APPROVE'd brief is `.codex/I-rdy-013/brief.md` (Codex APPROVE iter 3,
`.codex/I-rdy-013/codex_brief_verdict.txt`).

6 files, +517 / −32 (test file 237 LOC; non-test ≈ 165 — the LOC-cap
exemption was granted at brief iter 1).

## §2. Implementation summary (verify against the diff)

- **`run_store.py`**: `_ACTIVE_STATUSES`, `_INIT_LOCK` (serializes
  `init_db`), `_connect` busy_timeout, `_RUN_COLUMNS` + `_row_to_response`
  (dedup; `get_run` refactored to use them), `insert_run_if_idle` (atomic
  `BEGIN IMMEDIATE` check-and-insert), `get_active_run` (read-side helper).
  `insert_run` unchanged.
- **`api/runs.py`**: `create_run` → `insert_run_if_idle`; non-None return →
  `HTTPException(409, detail={code:"concurrent_run_active", active_run_id,
  active_status, message})`; `enqueue` moved after the reject branch and
  wrapped in `try/except` → `mark_failed` + 503 on send failure (P1-001).
- **`web/lib/api.ts`**: `ConcurrentRunError` + `createRun` 409 handling
  (body read once, FastAPI envelope unwrapped, non-409 untouched).
- **`web/app/dashboard/page.tsx`**: `concurrentRun` state + alert callout
  with a `<Link>` to the active run; `onSubmit` catch.
- **`tests/v6/conftest.py`**: autouse per-test run-DB isolation.
- **`tests/v6/test_concurrency.py`**: 11 tests incl. a two-thread race test.

## §3. Suggested focus (Red-Team checklist)

1. **Atomicity** — does `BEGIN IMMEDIATE` + `isolation_level=None` in
   `insert_run_if_idle` actually serialize two concurrent writers? Is the
   `ROLLBACK`/`COMMIT` explicit-statement form correct for Python 3.11+
   sqlite3 in manual-transaction mode? Any path that leaves a txn open?
2. **First-use init race** — is the `_INIT_LOCK`-guarded `init_db`
   sufficient (the iter-2 P1)? Any DDL still reachable concurrently?
3. **`get_run` refactor** — does `_row_to_response` reproduce the original
   builder field-for-field? Both `OperationalError` retry paths intact?
4. **409 detail** — `enqueue` is strictly after the reject branch (a
   rejected run must NOT be enqueued). uuid-collision 409 (str detail) vs
   concurrent 409 (dict detail) distinguishable.
5. **Frontend** — `createRun` reads the 409 body exactly once; non-409
   responses still reach `asJsonOrThrow` with an unconsumed body.
6. **Test isolation** — does the conftest autouse fixture fully prevent
   cross-test run-DB leakage? Any v6 test that depended on shared state?
7. No secret material in the diff; no `git add -A` collateral.

## §4. Evidence

- `tests/v6/test_concurrency.py` — 12 passed (incl. the P1-001 regression
  test).
- `tests/v6/` full suite — 427 passed, 7 xfailed, 0 failed, re-run after
  the P1-001 fix (conftest autouse fixture verified non-breaking).
- Backend import smoke OK; `npx eslint` clean; `npx tsc --noEmit` exit 0.

## §5. Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
