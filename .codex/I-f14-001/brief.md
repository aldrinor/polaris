# Codex Brief Review — I-f14-001 (ITER 3 of 5)

## Iter 3 changes per Codex iter 2

- **P1 fix (200 LOC cap is hard, no exemption):** scope reduction.
  - Drop separate `protocol.py`; add `MemoryStore` Protocol inline in existing `store.py` (~12 LOC vs 25 in a new file).
  - Drop `test_structural_recall_orders_by_token_overlap` (was demonstrative; hash-embedder isn't real semantic anyway).
  - Tighten chroma_store.py wording, single-pass code paths.
  - Revised LOC budget: chroma_store.py ~100, store.py +12, requirements-v6.txt +3, tests/v6/test_chroma_workspace_memory.py ~80 = ~195 net. Under 200 cap.
- **P1 fix (EphemeralClient state shared across collection name):** every test fixture uses `collection_name=f"test_{request.node.name}_{uuid.uuid4().hex[:8]}"` so each test gets isolated state.
- **P1 fix (PersistentClient mkdir):** ChromaWorkspaceMemoryStore.__init__ calls `os.makedirs(persist_directory, exist_ok=True)` before `chromadb.PersistentClient(path=persist_directory)`.
- **P2 fix (metadata None):** treat `collection.metadata` being `None` OR missing `hnsw:space` key OR wrong value as the same wrong-metric failure path; single check `(collection.metadata or {}).get("hnsw:space") != "cosine"` raises RuntimeError.
- **P2 fix (telemetry disabled):** pass `chromadb.config.Settings(anonymized_telemetry=False)` to both `EphemeralClient` and `PersistentClient`.
- **P2 fix (empty kinds):** if `query.kinds == []`, return `[]` immediately (Chroma rejects `$in: []`).

## Iter 2 changes per Codex iter 1 (still in plan)

- `chromadb==1.0.20` added to `requirements-v6.txt`.
- `test_persistent_client_round_trip(tmp_path)` retained; 4 new tests narrowed to 3 (default-embed-fn fail, wrong-metric raise, persistent round-trip).
- Cosine-space metric guard with the `(metadata or {})` null-safe pattern.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Issue:** I-f14-001 — Migrate workspace_memory to Chroma semantic. Scope: keyword/Jaccard → ChromaDB embedding-based. Acceptance: semantic recall test. LOC estimate 200.
- **Substrate today:** `src/polaris_v6/memory/store.py::WorkspaceMemoryStore` is in-memory dict + Counter-based cosine similarity over lower-cased ASCII tokens (keyword/Jaccard-style). Embedding field on `MemoryEntry.embedding_vector` exists in schema but is always `None`.
- **What "Chroma semantic" means here:** add a parallel `ChromaWorkspaceMemoryStore` implementing the SAME callable surface (remember / recall / forget / list_workspace). Persists entries in chromadb's local PersistentClient (SQLite-backed; no server needed). Uses an injected `embed_fn` for vector generation — deterministic hash-based embedder in tests, sentence-transformers in production wiring (deferred until v6 dev cluster is live, per memory `feedback_substrate_is_not_product`).
- **Honest framing per CLAUDE.md §9.4:** in-memory store stays the default for the FastAPI router; ChromaWorkspaceMemoryStore lives alongside as a substrate-only addition. Production swap (router uses Chroma) is a follow-up Issue I-f14-001b once the v6 dev cluster + sentence-transformers wiring lands. Per CLAUDE.md §8.4 (RAM/CPU stewardship): tests MUST NOT instantiate sentence-transformers; tests use a deterministic hash embedder so autonomous Issue runs do not pin GB-scale RAM.
- **Why a Protocol not subclassing:** keeps the in-memory store unchanged (zero risk of regression to its 8 existing tests + HTTP integration). Both stores satisfy the Protocol; production code can switch backends behind a feature flag later.

## Plan

### Dependency

0. Add `chromadb==1.0.20` to `requirements-v6.txt` under a new `# --- Vector store ---` section. PyPI-verified and locally installed.

### Schema (`src/polaris_v6/memory/store.py`)

1. Add `MemoryStore` Protocol (typing.Protocol) inline in `store.py` (no new file) with the four methods of `WorkspaceMemoryStore`:
   - `remember(*, workspace_id, kind, content, derived_from_run_ids=None) -> MemoryEntry`
   - `recall(query: MemoryQuery) -> list[MemoryRecallResult]`
   - `forget(*, workspace_id, entry_id) -> bool`
   - `list_workspace(workspace_id) -> list[MemoryEntry]`

### `src/polaris_v6/memory/chroma_store.py` (NEW)

3. `EmbedFn = Callable[[list[str]], list[list[float]]]` type alias.
4. `_default_embed_fn(texts) -> ...`: stub raising `RuntimeError("inject embed_fn (e.g., sentence-transformers); production wiring deferred to I-f14-001b")`. Per LAW II — fail loudly, no silent fallback.
5. `ChromaWorkspaceMemoryStore`:
   - `__init__(self, *, persist_directory: str | None, embed_fn: EmbedFn | None = None, collection_name: str = "v6_workspace_memory") -> None`.
   - Lazy-import chromadb inside `__init__` (avoids module-level import overhead in callers that don't use it).
   - **mkdir guard:** if `persist_directory` is non-None, `os.makedirs(persist_directory, exist_ok=True)` BEFORE constructing PersistentClient (Codex iter 2 P1: Chroma 1.0.20 on Windows fails on non-existent path).
   - **Settings:** pass `chromadb.config.Settings(anonymized_telemetry=False)` to both client constructors.
   - Use `chromadb.PersistentClient(path=persist_directory, settings=...)` if path given, else `chromadb.EphemeralClient(settings=...)`.
   - `get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})`.
   - **After get_or_create:** read `collection.metadata`; treat `None` OR missing key OR non-`"cosine"` value as wrong-metric → raise `RuntimeError("collection {name} pre-existing with hnsw:space={...}; expected cosine")` per LAW II.
   - `embed_fn = embed_fn or _default_embed_fn`.
   - Store full `MemoryEntry` JSON in `metadatas` (workspace_id + kind for filterable query; rest as `entry_json`).
6. `remember`: generate `entry_id = uuid.uuid4().hex`, normalize `workspace_id`, embed `content`, `collection.add(ids=[entry_id], documents=[content], embeddings=[embedding], metadatas=[{workspace_id, kind, entry_json}])`. Return MemoryEntry with `embedding_vector=embedding`.
7. `recall(query)`:
   - **Empty kinds guard:** if `query.kinds is not None and len(query.kinds) == 0`, return `[]` immediately (Chroma rejects `$in: []`).
   - normalize workspace_id.
   - embed `query.query_text`.
   - Build `where = {"workspace_id": ws}` plus optional kind filter `{"$and": [{"workspace_id": ws}, {"kind": {"$in": query.kinds}}]}`.
   - `collection.query(query_embeddings=[emb], n_results=query.top_k, where=where)`.
   - Convert distance → score: chromadb cosine returns `1 - cosine_similarity` so `score = max(0.0, 1.0 - distance)`. Clamp to [0, 1].
   - Reconstruct `MemoryEntry` from `entry_json`. Increment `use_count`, set `last_used_at`. Re-write metadata via `collection.update(ids=[entry_id], metadatas=[...])`.
   - Return list of `MemoryRecallResult`.
8. `forget`: `collection.get(ids=[entry_id], include=["metadatas"])`; verify workspace_id matches; `collection.delete(ids=[entry_id])`.
9. `list_workspace`: `collection.get(where={"workspace_id": ws}, include=["metadatas"])`; reconstruct `MemoryEntry` from each entry_json.

### Tests `tests/v6/test_chroma_workspace_memory.py` (NEW)

10. Pytest fixture `chroma_store(request)`: instantiates `ChromaWorkspaceMemoryStore(persist_directory=None, embed_fn=_hash_embed_fn, collection_name=f"test_{request.node.name}_{uuid.uuid4().hex[:8]}")` — **per-test unique collection** to avoid EphemeralClient state-share (Codex iter 2 P1). `_hash_embed_fn` is a deterministic hash-based fake (FNV-1a over chars → 8-dim vector).
11. `test_remember_and_recall_basic`: write one entry, recall same content, assert score > 0.
12. `test_workspace_isolation`: write to ws_alpha + ws_beta, recall in ws_alpha, assert only alpha returned.
13. `test_workspace_id_normalization`: write WS_Carney, recall "ws_carney  ", assert hit.
14. `test_kind_filter`: kinds parameter narrows results.
15. `test_empty_kinds_returns_empty`: kinds=[] returns [] immediately.
16. `test_top_k_caps_results`: 10 entries, top_k=3 returns 3.
17. `test_recall_increments_use_count`: use_count=0 before, =1 after.
18. `test_forget_respects_workspace`: forget from wrong ws fails; correct ws succeeds.
19. `test_recall_empty_workspace_returns_empty`: empty workspace returns [].
20. `test_default_embed_fn_fails_loudly`: instantiate without embed_fn, attempt remember, assert RuntimeError mentioning "inject embed_fn".
21. `test_persistent_client_round_trip(tmp_path)`: instantiate Store(persist_directory=str(tmp_path / "chroma"), embed_fn=_hash_embed_fn, collection_name="rt_unique"); remember an entry; instantiate a SECOND store at the same path with the same collection_name; assert `list_workspace` returns the entry and `recall` finds it with score > 0. **Verifies mkdir guard, persistence, AND single-instance-per-process workflow.**
22. `test_pre_existing_collection_with_wrong_metric_raises(tmp_path)`: pre-create a chromadb collection at `tmp_path / "chroma"` with `metadata={"hnsw:space": "l2"}` (different metric); instantiate ChromaWorkspaceMemoryStore at same path; assert `RuntimeError` mentioning "hnsw:space".

### Out of scope

- Production router swap to Chroma (still uses in-memory store): follow-up I-f14-001b.
- sentence-transformers integration: follow-up I-f14-001b.
- Migration of existing in-memory entries into Chroma: follow-up if needed.

## Risks for Codex Red-Team

1. **Lazy chromadb import:** intentional to avoid module-level cost in callers that don't use it. Tests that use the new store will incur the import.
2. **Test embedding determinism:** hash-based 8-dim embedder is engineered to give meaningful scores for same/similar tokens; not a real semantic measure. Test `test_semantic_recall_with_synonyms` is structural — it documents the SHAPE of semantic recall, not real semantics.
3. **EphemeralClient vs PersistentClient:** tests use Ephemeral (in-memory chromadb); production passes a path. Both routes covered by tests via the `persist_directory=None` branch.
4. **Score-distance mapping:** chromadb cosine distance ∈ [0, 2]; we clamp `1 - distance` to [0, 1] for the schema constraint. Edge case: when distance > 1 (orthogonal-ish), score=0.
5. **Default-embed-fn loud failure:** explicit per LAW II — no silent fallback to a fake embedder in production.
6. **Resource discipline (CLAUDE.md §8.4):** chromadb itself loads, but EphemeralClient + injected hash embedder = no model loading. Test suite stays under RAM budget.
7. **CHARTER §1 LOC cap:** revised iter 3 plan = chroma_store.py ~110, store.py +12 (Protocol inline, no new file), requirements-v6.txt +3, tests/v6/test_chroma_workspace_memory.py ~75 = ~200 net. AT cap. Will tighten code if needed at write-time.
8. **§9.4 backend code hygiene:** no `try/except: pass`, no magic numbers (top_k from query, threshold from chromadb config), no `time.sleep`, no TODOs in shipped code.

## Acceptance criteria

1. `chromadb==1.0.20` added to `requirements-v6.txt`.
2. New `MemoryStore` Protocol added inline to `src/polaris_v6/memory/store.py`.
3. New `ChromaWorkspaceMemoryStore` in `src/polaris_v6/memory/chroma_store.py` with all four methods.
4. mkdir guard before PersistentClient construction.
5. Default embed_fn fails loudly per LAW II.
6. Cosine-space metric guard handles None / missing key / wrong value.
7. Empty kinds returns [] before reaching Chroma.
8. Anonymized telemetry disabled via Settings.
9. Tests in `tests/v6/test_chroma_workspace_memory.py` mirror the 8 in-memory tests + 4 new (empty-kinds; default-embed-fn fail; persistent round-trip; wrong-metric raise) = 12 tests with per-test unique collection name.
10. Existing in-memory store + 8 tests + HTTP router unchanged.
11. CHARTER §1 LOC cap respected (≤200 net).
12. CLAUDE.md §8.4: tests do NOT load sentence-transformers; deterministic hash embedder only.
13. CLAUDE.md §9.4: no forbidden patterns in shipped code.

**Forced enumeration:** before verdict, write one line per criterion 1-13.

**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
