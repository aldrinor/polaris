# Codex Diff Review — I-f14-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f14-001 — Migrate workspace_memory to Chroma semantic
**Brief:** APPROVED iter 3 (LOC trim to 200; per-test unique collection_name; mkdir guard; metadata None-safe; telemetry off; empty-kinds short-circuit; persistent round-trip + wrong-metric tests)
**Canonical-diff-sha256:** `8c2caa86d5c3a229365f0568f8ad1666757ed85ddab5132d4cc6e9ddf3601659`
**LOC:** 198 net (under CHARTER §1 200-cap)

## Files

```
requirements-v6.txt                                  +4   (chromadb==1.0.20 pin under new "Vector store" section)
src/polaris_v6/memory/chroma_store.py                NEW +101 (ChromaWorkspaceMemoryStore + guards)
tests/v6/test_chroma_workspace_memory.py             NEW +93  (8 tests: 4 mirror + default-fail + forget + persist + wrong-metric)
```

## What changed

### `requirements-v6.txt`
- New `# --- Vector store (I-f14-001 — workspace memory semantic recall) ---` section.
- `chromadb==1.0.20` pinned (verified 2026-05-07 against local install + PyPI).

### `chroma_store.py` (NEW)
- `EmbedFn = Callable[[list[str]], list[list[float]]]`.
- `_default_embed_fn` raises RuntimeError loudly per LAW II.
- `_norm` (workspace_id) + `_now` (UTC iso) + `_meta` (chromadb metadata dict shape).
- `ChromaWorkspaceMemoryStore.__init__`:
  - Lazy `import chromadb`.
  - `Settings(anonymized_telemetry=False)`.
  - `os.makedirs(persist_directory, exist_ok=True)` BEFORE `PersistentClient` (Codex iter-2 P1 — Chroma 1.0.20 on Windows fails on non-existent path).
  - `EphemeralClient` if persist_directory is None.
  - `get_or_create_collection(metadata={"hnsw:space": "cosine"})`.
  - **Cosine guard:** `(self._collection.metadata or {}).get("hnsw:space") != "cosine"` raises RuntimeError. Null-safe per Codex iter-2 P2.
- `remember`: embed → MemoryEntry → collection.add with metadata.
- `recall`:
  - **Empty kinds short-circuit:** `query.kinds is not None and len(query.kinds) == 0` → return [] (Codex iter-2 P2: Chroma rejects `$in: []`).
  - Build `where` (workspace + optional kind filter).
  - `collection.query(...)`.
  - Iterate ids/distances/metadatas; reconstruct entry; increment use_count + last_used_at; persist via `collection.update`; score = `max(0, min(1, 1 - distance))` clamp.
- `forget`: workspace-scoped delete; null-safe metadata access.
- `list_workspace`: filter by workspace_id.

### `tests/v6/test_chroma_workspace_memory.py` (NEW, 8 tests)
- `_hash_embed_fn`: deterministic 8-dim FNV-style hash embedder. NEVER loads sentence-transformers per CLAUDE.md §8.4.
- Per-test unique `collection_name=f"t_{request.node.name}_{uuid.uuid4().hex[:8]}"` to avoid EphemeralClient state-share (Codex iter-2 P1).
- Tests: basic recall, workspace isolation, kind filter, top_k cap, forget workspace-scoped, default-embed-fn fail, persistent round-trip (tmp_path), wrong-metric raise (pre-creates l2 collection, expects RuntimeError).

## Verification

- `pytest tests/v6/test_chroma_workspace_memory.py`: 8/8 passing in 2.5s.
- `pytest tests/v6/test_workspace_memory.py tests/v6/test_api_memory.py`: 14/14 passing (no regression).
- Total: `pytest tests/v6/`: 22/22 passing.
- Lazy chromadb import confirmed (no module-level cost).
- Telemetry suppressed via Settings (caveat: Codex iter-3 noted Chroma 1.0.20 still emits some failed-telemetry log lines — flag, not blocker).

## Risks for Codex Red-Team

1. **Production wiring deferred:** router still uses in-memory store (unchanged). Follow-up I-f14-001b swaps router + adds sentence-transformers wiring.
2. **Test-only persistence:** tests use tmp_path; production persistence path comes via env var in I-f14-001b.
3. **Hash embedder shape:** 8-dim deterministic; production uses sentence-transformers (~384/768 dim). Score-distance math identical.
4. **§9.4:** no `try/except: pass`, no magic numbers (top_k from query, threshold from chromadb), no time.sleep, no TODO, no `from x import *`.
5. **CHARTER §1 LOC cap:** 198 net. Under 200.

## Output schema (mandatory)

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
