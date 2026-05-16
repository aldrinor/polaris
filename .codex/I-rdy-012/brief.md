# Codex BRIEF review — I-rdy-012 (#508): durable workspace-scoped memory with cited recall

**Type:** BRIEF review (acceptance-criteria + scope correctness). Phase 3.9 of the
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

This brief carries a **scope decision** (§3) — the substrate has two built
storage backends and the choice between them is a real fork. Please rule
`backend_ruling`.

## §1. Issue + acceptance

GH #508 (I-rdy-012, Phase 3.9): "F14 real durability + workspace isolation +
cited recall + migration from the in-memory demo store. **Acceptance: memory
survives restart, is workspace-scoped, cited recall surfaces which past run
contributed; Codex APPROVE.**" Depends on I-rdy-007 (done).

## §2. Grounded current state (all files read)

- **`src/polaris_v6/api/memory.py`** — the F14 HTTP endpoints
  (`POST /workspaces/{id}/memory`, `/memory/recall`, `DELETE
  /memory/{entry_id}`, `GET /memory`). Module-level `_store =
  WorkspaceMemoryStore()` — **the in-memory store**. Mounted at `app.py:102`.
- **`src/polaris_v6/memory/store.py`** — `WorkspaceMemoryStore`: an in-memory
  `dict[str, MemoryEntry]`. Recall = token-frequency **keyword cosine**
  (`_tokens` + `_cosine`). Workspace-scoped (`_normalize_workspace_id` on
  read+write, filtered in `recall`/`forget`/`list_workspace`). Module
  docstring: "Phase 2B production swap: replace with Chroma." **NOT durable —
  the dict is lost on process restart.** This is the "in-memory demo store"
  #508 names.
- **`src/polaris_v6/memory/chroma_store.py`** — `ChromaWorkspaceMemoryStore`:
  **already built + tested** (`test_chroma_workspace_memory.py`). Durable via
  `chromadb.PersistentClient(path=persist_directory)` (embedded chromadb —
  `chromadb 1.0.20` is installed; no external service). Same interface as
  `WorkspaceMemoryStore` (`remember`/`recall`/`forget`/`list_workspace`),
  workspace-scoped (`where` filters). **BUT** it requires an injected
  `embed_fn`; its `_default_embed_fn` *raises* `RuntimeError("inject embed_fn
  (sentence-transformers); deferred to I-f14-001b")`. The real
  sentence-transformers embedder is an explicitly-deferred separate issue
  (I-f14-001b); `test_chroma_workspace_memory.py` injects an 8-dim
  character-hash embedder as a stopgap.
- **`src/polaris_v6/memory/schema.py`** — `MemoryEntry` carries
  `derived_from_run_ids: list[str]` and `MemoryKind` includes
  `prior_run_summary`. `MemoryRecallResult = {entry, score}`. So **the
  data model for cited recall already exists**: `remember` takes
  `derived_from_run_ids`, `recall` returns `MemoryRecallResult.entry` which
  carries them. Cited recall is satisfied once the store round-trips
  `derived_from_run_ids` durably. (Nothing in the pipeline auto-writes
  `prior_run_summary` entries today — the caller supplies the run ids via the
  `remember` endpoint; auto-population is out of #508 scope.)
- Tests: `test_workspace_memory.py` (in-memory store), `test_api_memory.py`
  (the HTTP endpoints, in-memory-backed), `test_chroma_workspace_memory.py`
  (the chroma store + hash embedder), `test_evidence_pool_memory.py`.

**The gap:** the route uses the non-durable in-memory store. The acceptance
needs a durable, workspace-scoped store whose recall surfaces
`derived_from_run_ids`.

## §3. The scope decision — Codex please rule `backend_ruling`

Two built backends; choosing the durable store for the route is a fork.

- **Option A — wire the existing `ChromaWorkspaceMemoryStore` into the route.**
  Reuses built+tested code; durable via embedded chromadb. **But** it needs an
  `embed_fn`. Sub-fork: (A1) inject the 8-dim **hash embedder** — works
  offline, no ML, but it is a crude character-frequency fingerprint that
  recalls *worse* than the current keyword-cosine; (A2) inject the real
  **sentence-transformers** embedder — heavy ML, a sovereignty model-lineage
  decision, and explicitly deferred (`_default_embed_fn` → I-f14-001b);
  loading it in a worker violates CLAUDE.md §8.4 (no heavy ML in autonomous
  loops). A1 *regresses* recall quality to gain durability; A2 is not
  available.
- **Option B (recommended) — make the store durable as SQLite-backed,
  keeping the keyword-cosine recall.** A new `SqliteWorkspaceMemoryStore`
  (mirroring `queue/run_store.py`: a `memory_entries` table, additive schema,
  WAL) with the **identical `remember`/`recall`/`forget`/`list_workspace`
  interface**. `recall` keeps the exact keyword-cosine scoring (fetch the
  workspace's rows, score in Python, top-k). `derived_from_run_ids` is a JSON
  column → round-trips for cited recall. The route swaps `_store` to it. This
  meets all three acceptance criteria — durable (SQLite survives restart),
  workspace-scoped (SQL `WHERE workspace_id=?`), cited recall (`MemoryEntry.
  derived_from_run_ids`) — **without degrading recall quality and with no
  embedder / chromadb / heavy-ML dependency** (sovereign + §8.4-clean).
  `ChromaWorkspaceMemoryStore` is preserved untouched as the future
  *semantic*-recall upgrade, which lands when the real embedder (I-f14-001b)
  is decided.
- **Option C** — Codex's call.

**Recommendation: B.** #508's acceptance is *durability + workspace isolation
+ cited recall* — it does NOT require semantic recall. Option B delivers all
three, preserves the current recall quality, and avoids both the recall
*regression* of A1 and the deferred/heavy-ML dependency of A2. The semantic
upgrade (chroma + real embedder) remains a clean, separately-tracked future
issue. (If Codex prefers A, A1+hash is the only offline-viable variant and
the brief's §4 plan changes to "wire chroma_store + a documented hash
embed_fn".)

## §4. Implementation plan — Option B (if Codex rules B)

1. **`src/polaris_v6/memory/sqlite_store.py`** (new) —
   `SqliteWorkspaceMemoryStore`. SQLite table `memory_entries(entry_id PK,
   workspace_id, kind, content, created_at, last_used_at, use_count,
   derived_from_run_ids TEXT JSON, embedding_vector TEXT JSON NULL)`; WAL;
   `_migrate_schema` additive (mirrors `run_store.py`). Methods identical to
   `WorkspaceMemoryStore`: `remember` (INSERT), `recall` (SELECT workspace
   rows → keyword-cosine score in Python → top-k → UPDATE use_count/
   last_used_at), `forget` (DELETE workspace-scoped), `list_workspace`
   (SELECT). `workspace_id` normalized identically on write+read (the P0
   governance invariant from `store.py`). DB path env
   `POLARIS_V6_MEMORY_DB`, default `state/v6_workspace_memory.sqlite`
   (gitignored). The keyword-cosine helpers (`_tokens`, `_cosine`) move to a
   shared spot or are duplicated minimally.
2. **`src/polaris_v6/api/memory.py`** — swap `_store = WorkspaceMemoryStore()`
   → `SqliteWorkspaceMemoryStore()`. The HTTP contract is unchanged (same
   schema in/out). This is "migration from the in-memory demo store."
3. **Tests** `tests/v6/test_sqlite_workspace_memory.py` — durability
   (remember → new store instance on the same DB path → recall returns it);
   workspace isolation (ws A entry invisible to ws B recall/list/forget);
   cited recall (`derived_from_run_ids` round-trips remember→recall);
   keyword-cosine ranking; `forget` 404-on-wrong-workspace. The route is
   exercised by importing the `memory.py` route functions directly (the
   `create_app()` TestClient errors on gpg on this host — pre-existing).

LOC estimate: ~160-200 (the SQLite store ~130, route swap ~3, tests ~100).
Within / near the 200-LOC cap — flagged for Codex if it lands over.

## §5. Adjacent-file scan — files I have ALSO checked and they're clean

`src/polaris_v6/memory/store.py` (the in-memory store — kept as-is for its
existing tests; the route stops using it), `src/polaris_v6/memory/__init__.py`,
`src/polaris_v6/api/app.py:102` (memory router mounted), `src/polaris_v6/
queue/run_store.py` (the SQLite-store pattern to mirror — additive
`_migrate_schema`, WAL, `_connect`), `tests/v6/test_api_memory.py` +
`test_workspace_memory.py` (existing memory tests — the HTTP contract is
unchanged so `test_api_memory.py` semantics hold against the SQLite backend),
`src/polaris_v6/adapters/evidence_pool_merger.py` (`MemoryDerivedSummary` —
the separate evidence-pool surfacing path, unchanged by #508).

## §6. Questions for Codex

1. **`backend_ruling`** — Option A (wire `ChromaWorkspaceMemoryStore`; A1 hash
   embedder / A2 deferred real embedder) or B (SQLite + keyword-cosine)?
   (Recommendation: B.)
2. If B: should the new SQLite store *replace* `store.py`'s
   `WorkspaceMemoryStore` (delete the in-memory one + migrate its tests) or
   sit alongside it (in-memory store kept for unit-test speed)? (Recommendation:
   alongside — the in-memory store is a fine fast test double; only the route
   migrates.)
3. Is "cited recall surfaces which past run contributed" fully satisfied by
   `MemoryRecallResult.entry.derived_from_run_ids` round-tripping durably, or
   does Codex read it as also requiring auto-population of `prior_run_summary`
   entries by the pipeline (a larger, separate scope)?
4. Any P0/P1 execution risk.

## §7. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
backend_ruling: <option-A-hash | option-A-real | option-B-sqlite | option-C + reasoning>
store_disposition_ruling: <alongside | replace>
cited_recall_ruling: <derived-run-ids-roundtrip-ok | requires-auto-population>
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
