# Claude architect audit — I-rdy-012 (#508): durable workspace-scoped memory

**Issue:** GH #508 — F14 real durability + workspace isolation + cited recall +
migration from the in-memory demo store. Acceptance: memory survives restart,
is workspace-scoped, cited recall surfaces which past run contributed.

**Commits (off `polaris` @ `9185035e`):** `<brief>` + the code commit
(4 files, +436/-7). Canonical-diff-sha256
`292b34f43907d5bf4576fd6fdca66f57b14b138a90998e829a5ad00be44a43d1`.

## Scope (Codex brief-iter-1 APPROVE'd, backend_ruling = option-B-sqlite)

#508 had two built backends: the in-memory `WorkspaceMemoryStore` (demo, not
durable) and `ChromaWorkspaceMemoryStore` (durable, but needs an embed_fn
whose real impl is the deferred I-f14-001b; a hash embedder would *regress*
recall vs the current keyword-cosine). Codex ruled **option-B**: a
SQLite-backed store that keeps the keyword-cosine recall — durable without an
embedder / chromadb / heavy-ML dependency. `ChromaWorkspaceMemoryStore` stays
untouched as the future semantic upgrade.

## Acceptance check

- **Survives restart:** `SqliteWorkspaceMemoryStore` persists to a SQLite DB
  (`state/v6_workspace_memory.sqlite`, WAL). `test_durability_survives_new_store_instance`
  proves a brand-new store object on the same DB recalls a prior entry.
- **Workspace-scoped:** every method normalizes `workspace_id` identically and
  filters on it (`WHERE workspace_id=?`). Tests cover recall / list /
  cross-workspace-forget isolation + write/read normalization.
- **Cited recall:** `derived_from_run_ids` is a JSON column;
  `test_cited_recall_round_trips_run_ids` proves a recalled entry surfaces the
  contributing run ids `["run_aaa","run_bbb"]` after a store reopen.
- **Migration off the demo store:** `api/memory.py` swaps `_store` to
  `SqliteWorkspaceMemoryStore`; the HTTP contract is unchanged.

## Design

`SqliteWorkspaceMemoryStore` is a drop-in replacement — identical
`remember` / `recall` / `forget` / `list_workspace` signatures, same return
types — so the route swap is one line. Storage mirrors `queue/run_store.py`
(WAL, `_connect`, idempotent additive `_migrate_schema`). `recall` keeps the
exact keyword-cosine scoring of `store.py` (fetch the workspace's rows, score
in Python, top-k, then persist `use_count`/`last_used_at`). The keyword-cosine
helpers are duplicated (≈15 lines of frozen utility) rather than imported, so
`sqlite_store.py` is self-contained.

`store.py` (in-memory) + `chroma_store.py` are left untouched —
`store_disposition = alongside` (the in-memory store remains a fast test
double for `test_workspace_memory.py`).

## Codex P2 (brief-iter-1) — addressed

P2: API tests against the module-global `_store` with the default DB path
would accumulate fixed-workspace rows across runs. Fixed:
`test_api_memory.py`'s `client` fixture now `monkeypatch.setattr`s
`memory_mod._store` to a fresh `tmp_path`-backed `SqliteWorkspaceMemoryStore`
per test.

## Tests

`tests/v6/test_sqlite_workspace_memory.py` — 10 tests, all pass offline:
durability across a fresh store instance; workspace isolation on recall /
list / cross-workspace forget; workspace-id normalization; cited-recall
run-id round-trip; keyword-cosine ranking; durable `use_count` increment;
`kinds` filter; forget-missing. `test_workspace_memory.py` 8/8 unregressed
(`store.py` untouched). Import smoke clean on `sqlite_store.py` +
`api/memory.py`.

`test_api_memory.py` exercises the route end-to-end; on this host its
`create_app()` errors on the absent `gpg` binary (pre-existing — identical to
`test_api_bundle.py`); it runs in CI. The fixture change isolates it per the
P2.

## Residual / follow-up

- Semantic recall (Chroma + a real sentence-transformers embedder) remains a
  separately-tracked future issue (the embedder is the already-deferred
  I-f14-001b). `ChromaWorkspaceMemoryStore` is unchanged and ready for that
  wiring.
- Auto-population of `prior_run_summary` entries by the pipeline (so cited
  recall has data without an explicit `remember` call) is a separate pipeline
  feature — Codex `cited_recall_ruling = derived-run-ids-roundtrip-ok`
  confirmed it is not in #508 scope.

## Verdict

The diff implements the APPROVE'd brief (option-B-sqlite), meets all three
acceptance criteria, preserves recall quality, adds no heavy-ML/embedder/
chromadb dependency, and is covered by 10 offline tests. Ready for Codex diff
review.
