# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 7 Complete, Ready for Unit 8

**Branch:** `PL`
**Last commits (local, not pushed):**
- `3a3c514` — Wiki Mesh Unit 1 — single-db schema + store + 43 tests
- `68e177e` — file_directory register for Unit 1 files (§2.1 bookkeeping)
- `860210a` — Wiki Mesh Unit 2 of 10 — ingest + claim_extract (foundation for Unit 3)
- `65875dd` — Wiki Mesh Unit 3 of 10 — entity canonicalization (FIX D2)
- `9f90a2f` — Wiki Mesh Unit 4 of 10 — edge discovery + snowball (FIX S4)
- `f1e95de` — restart_instructions doc fix
- `292a12f` — Wiki Mesh Unit 5 of 10 — lethal retrieval + gap classify
- `5aa2b42` — Wiki Mesh Unit 6 of 10 — compose + artifact directives (FIX S7)
- **Unit 7 commit pending** — qa/ask.py + store.py Q&A CRUD + tests (16 new tests)

**Status:** 7 of 10 wiki mesh units complete. Full Q&A path: ask → retrieve → compose → answer with bibliography + multi-turn threads. 250/250 tests passing.

**Honest scope:** Unit 7 completes the conversational Q&A layer. CLI (Unit 8), API (Unit 9), and integration tests (Unit 10) are still ahead. The mesh can answer questions with cited responses and maintain multi-turn threads, but has no user interface yet.

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue. User will resolve when back from their trip.

---

## What was just done

### Unit 7 — Q&A layer + multi-turn threads (FIX S8)

**`src/polaris_graph/wiki/mesh/qa/ask.py` (~160 lines)**
- `ask()` orchestrator: 6 steps — insert question → build thread context → retrieve → check NEARBY budget → compose → insert answer → return AskResult
- Coreference via simple concatenation of last 3 Q&A pairs (no LLM in v1). Embedding of "Q: ... A: ... Q: What about the cost?" naturally resolves pronouns
- NEARBY budget awareness: `AskResult.nearby_budget_available` set when gap=NEARBY and budget allows, for Unit 8 CLI to act on
- Empty workspace: returns ORTHOGONAL gap + "no claims" but persists question row (we track what was asked even with no results)

**Store additions (~100 lines in store.py)**
- `insert_question(workspace_id, text, parent_id, asked_by) -> str`
- `get_question(question_id) -> dict | None`
- `insert_answer(question_id, text, retrieved_claims, cited_claims, artifact_paths, model) -> str`
- `get_answer_for_question(question_id) -> dict | None`
- `get_thread_history(question_id, last_n=3) -> list[dict]` — walks parent_id chain backward, reverses to chronological order, pops current question, limits to last_n

**`tests/unit/test_mesh_qa.py` — 16 tests**
- TestInsertQuestion (4): basic, parent, empty raises, missing returns None
- TestInsertAnswer (2): basic, no answer returns None
- TestThreadHistory (4): no history, 2-question, 3-question chronological, last_n limits
- TestBuildResolvedQuestion (2): no history → raw, with history → concatenated Q/A format
- TestAskOrchestration (4): E2E single question, follow-up with parent_id, empty ORTHOGONAL, unknown workspace raises

---

## NEXT SESSION — Start Unit 8: Workspace management + CLI

Unit 8 provides the user interface layer: a CLI tool for interacting with the mesh (ask questions, ingest files, manage workspaces, review quarantined entities).

### What Unit 8 delivers

- `cli/main.py` — Click-based CLI entry point: `polaris mesh ask`, `polaris mesh ingest`, `polaris mesh stats`, `polaris mesh entities review`
- `cli/workspace.py` — Workspace CRUD commands: create, list, switch, delete
- Snapshot support with zstd compression for mesh.db backup/restore
- Tests for CLI argument parsing + workspace management

### Files to read first in next session

1. `docs/wiki_mesh_design.md` §12 (CLI commands reference)
2. `src/polaris_graph/wiki/mesh/qa/ask.py` — the ask() function the CLI calls
3. `src/polaris_graph/wiki/mesh/ingest.py` — ingest_file/ingest_web_content the CLI calls
4. `src/polaris_graph/wiki/mesh/store.py` — workspace CRUD, stats, quarantined entities

---

## Key invariants to preserve across Unit 4 and beyond

- **Single database file.** Never introduce a second store for vectors — FIX D1 depends on this.
- **Over-fetch KNN.** Any new vector search path must use the `k × 3 → filter → LIMIT k` pattern from `search_claims_by_vector`.
- **Entity quarantine is not optional.** Any code path that inserts an entity with `confidence < 0.8` must NOT let it participate in retrieval expansion until user-confirmed.
- **usage_boost is bounded.** Anything that modifies edge weights must go through `bump_edge_usage_boost()` or respect the schema CHECK constraint (≤ 0.2, FIX S4).
- **Header-strip before char-span.** Any downstream code that reads an ingested source file MUST use `ingest.read_source_text()`, not raw `Path.read_text()`.
- **Reuse MESH_SYSTEM and analyzer.py untouched.** Any new mesh-side prompt must wrap `ANALYSIS_SYSTEM`, not modify it.
- **Fail loudly.** LAW II. No silent fallbacks, no partial inserts, no default-value substitutions.
- **L2 → cosine.** `cos = 1 - 0.5 * d²` for unit vectors. sqlite-vec vec0 reports L2 distance for float vectors; the production `embed_texts` returns unit-length vectors (all-MiniLM-L6-v2 default).
- **v1 contradiction edges are candidates.** Cosine-based (0.80-0.85 zone from different sources), NOT NLI-confirmed. The ×0.7 penalty applies immediately but user review resolves false positives. NLI-based typing deferred to v2.
- **Mapping table column name.** All 4 vec0 mapping tables use `entity_id` as the column name (not `claim_id` etc.) — generic schema pattern from Unit 1.

---

## Running the tests

```
cd C:/POLARIS
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py tests/unit/test_mesh_edge_discovery.py tests/unit/test_mesh_snowball.py tests/unit/test_mesh_lethal_retrieve.py tests/unit/test_mesh_compose.py tests/unit/test_mesh_qa.py -v
```

Expected: **250 passed** in ~102s (the embedding model loads once for the integration tests).

---

## Long-term backlog (carried across units)

- `vacuum_orphan_vectors()` for post-delete cleanup (Unit 1)
- Schema migration tool for future SCHEMA_VERSION bumps (Unit 1)
- Exception-string fragility in `_insert_vector` (Unit 1)
- `_row_id_to_int` 63-bit hash collision warning (Unit 1, documented in code)
- Decouple `ANALYSIS_SYSTEM` from `agents/analyzer.py` into standalone prompt file (Unit 2 CP-D)
- Real OpenRouter E2E test for `extract_claims_from_source` (Unit 2 CP-D — awaiting credit restoration)
- Normalized alias table at scale — `_find_by_alias` is O(n) linear scan; once a workspace has > few thousand entities, move aliases to a separate indexed table (Unit 3 CP-B note)
- NLI-based edge typing for v2 — current v1 uses cosine-only thresholds. Contradiction edges are candidates, not NLI-confirmed. (Unit 4 CP-A design note.)
- `elaborates` edge kind — deferred to v2, requires NLI infra. (Unit 4 CP-A design note.)
- Word-boundary entity matching — `_extract_question_entities` uses bare substring `in`. At scale, switch to `re.search(r'\b...\b')`. (Unit 5 CP-C advisor note.)
- Stage 0 coreference — accepts `resolved_question` param, deferred to Unit 7. (Unit 5.)
- NEARBY auto-expansion trigger — gap_classify returns category, actual search deferred to Unit 7+. (Unit 5.)
- Multi-user auth (v2 scope)
- 768-/1024-/4096-dim embedding support (currently pinned at 384-dim via sqlite-vec DDL)

---

## GitHub push backlog

- Remote `origin` = `https://github.com/aldrinor/polaris` (configured but auth blocked)
- Git Credential Manager is authenticated as `sotaleung-wec` (different account from `aldrinor`)
- User logged out `sotaleung-wec` via GitHub web but GCM cache still held the token; cleared via `git credential-manager erase`
- Subsequent push hangs because GCM tries to open a browser window to re-auth as `aldrinor`, but the headless shell can't receive the popup
- **User to resolve when back home** by running `!git push -u origin PL` in their own Claude Code prompt — any browser popup will reach their display
- All local commits (Unit 1 + Unit 2 + Unit 3 + subsequent units) will ship in one push when the auth is resolved
