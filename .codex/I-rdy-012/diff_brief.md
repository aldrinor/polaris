# Codex DIFF review — I-rdy-012 (#508): durable workspace-scoped memory

**Type:** DIFF review (code correctness against the APPROVE'd brief). iter 1 of 5.

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

## §1. What to review

The diff for #508 against the brief APPROVE'd at brief-iter 1
(`.codex/I-rdy-012/codex_brief_verdict.txt`). Canonical diff:
`.codex/I-rdy-012/codex_diff.patch`, trailer
`# canonical-diff-sha256: 292b34f43907d5bf4576fd6fdca66f57b14b138a90998e829a5ad00be44a43d1`
= sha256 of `git diff origin/polaris...HEAD -- ':(exclude).codex/I-rdy-012/'
':(exclude)outputs/audits/I-rdy-012/'`.

4 files, +436/-7. Scope (brief-APPROVE'd, `backend_ruling = option-B-sqlite`):
SQLite-backed durable store, keyword-cosine recall preserved, no
embedder/chromadb/heavy-ML dependency.

## §2. Implementation map

**`src/polaris_v6/memory/sqlite_store.py` (new, ~250 LOC)** —
`SqliteWorkspaceMemoryStore`: drop-in replacement for the in-memory
`WorkspaceMemoryStore`, identical `remember` / `recall` / `forget` /
`list_workspace` signatures + return types. SQLite storage mirrors
`queue/run_store.py` (`_connect`, WAL, idempotent additive `_migrate_schema`).
Table `memory_entries` (entry_id PK, workspace_id, kind, content, created_at,
last_used_at, use_count, derived_from_run_ids JSON, embedding_vector JSON
NULL) + `idx_memory_workspace`. DB path env `POLARIS_V6_MEMORY_DB`, default
`state/v6_workspace_memory.sqlite`. `recall` reproduces the in-memory store's
keyword-cosine scoring verbatim (the `_tokens`/`_cosine` helpers are
duplicated — ~15 lines of frozen utility — keeping the module self-contained),
then persists `use_count`/`last_used_at` for the returned top-k.
`workspace_id` normalized identically on write + read (P0 governance).

**`src/polaris_v6/api/memory.py` (mod)** — `_store` swapped from
`WorkspaceMemoryStore()` to `SqliteWorkspaceMemoryStore()`; docstring updated.
The HTTP contract (request/response models, routes) is unchanged.

**`tests/v6/test_sqlite_workspace_memory.py` (new)** — 10 tests (see §3).

**`tests/v6/test_api_memory.py` (mod)** — the `client` fixture now
`monkeypatch.setattr`s `memory._store` to a per-test `tmp_path`-backed store
(Codex brief-iter-1 P2 — API tests must not accumulate fixed-workspace rows in
the default DB).

`store.py` (in-memory) + `chroma_store.py` are untouched.

## §3. Test evidence

`tests/v6/test_sqlite_workspace_memory.py` — **10/10 pass** offline:
durability (a fresh store object on the same DB recalls a prior entry);
workspace isolation on recall / list / cross-workspace forget; workspace-id
write/read normalization; cited recall (`derived_from_run_ids` round-trips a
store reopen); keyword-cosine ranking; durable `use_count` increment; `kinds`
filter; forget-missing. `test_workspace_memory.py` **8/8** — `store.py`
untouched, no regression. Import smoke clean on `sqlite_store.py` +
`api/memory.py`.

`test_api_memory.py` exercises the routes via `TestClient(create_app())`; on
this dev host `create_app()` errors on the absent `gpg` binary (pre-existing —
identical to `test_api_bundle.py` / `test_api_ambiguity.py`); it runs in CI.
The fixture change isolates it per the P2.

## §4. Points to scrutinise

1. **Durability** — `SqliteWorkspaceMemoryStore.__init__` runs `_init_db`
   (WAL + additive migration); a new instance on the same path sees prior
   rows. Confirm the migration is idempotent and the round-trip
   (`derived_from_run_ids`, `embedding_vector` as JSON columns) is lossless.
2. **Workspace isolation** — every method normalizes `workspace_id` and
   filters `WHERE workspace_id=?`; `forget` is workspace-scoped so a
   cross-workspace `forget` returns False without deleting. Any leak path?
3. **Behavioural parity with `WorkspaceMemoryStore`** — same interface, same
   keyword-cosine recall, same `use_count`/`last_used_at` mutation semantics
   — so the unchanged `api/memory.py` HTTP contract holds.
4. **`recall` connection handling** — two `_connect` blocks (SELECT, then the
   use_count UPDATE); each `try/finally`-closed. Acceptable, or fold into one?
5. Any P0/P1 execution risk.

## §5. Adjacent-file scan — checked, clean

`src/polaris_v6/memory/store.py` (in-memory store — untouched; remains a fast
test double, `test_workspace_memory.py` still green), `src/polaris_v6/memory/
chroma_store.py` (the future semantic-recall store — untouched),
`src/polaris_v6/memory/schema.py` (`MemoryEntry`/`MemoryQuery`/
`MemoryRecallResult` — unchanged; reused), `src/polaris_v6/api/app.py:102`
(memory router mounted — unchanged), `src/polaris_v6/queue/run_store.py` (the
SQLite pattern mirrored).

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
