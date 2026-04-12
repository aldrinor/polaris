# Restart Instructions

## Current State (2026-04-12) — Wiki Mesh Unit 8 Complete, Ready for Unit 9

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
- `f9de5aa` — Wiki Mesh Unit 7 of 10 — Q&A layer + multi-turn threads (FIX S8)
- **Unit 8 commit pending** — cli/main.py + tests (11 new tests)

**Status:** 8 of 10 wiki mesh units complete. Full pipeline with CLI: ingest → extract → canonicalize → edge discovery → retrieve → compose → Q&A with threads → CLI interface. 261/261 tests passing.

**Honest scope:** Unit 8 provides the user-facing CLI. API (Unit 9) and integration tests + snapshots (Unit 10) remain. The mesh is functionally usable from the command line (with --dry-run for testing without LLM).

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue. User will resolve when back from their trip.

---

## What was just done

### Unit 8 — CLI presentation layer

**`src/polaris_graph/wiki/mesh/cli/main.py` (~210 lines)**
- argparse-based CLI with 6 subcommands: workspace-create, workspace-list, ask (with --dry-run), ingest, stats, entities-review
- Each handler is thin: open store, call mesh function, print result, close store. Zero business logic
- `--dry-run` on ask calls `lethal_retrieve` directly without LLM — testable without network
- `asyncio.run()` bridges the sync CLI to async `ask()` orchestrator
- `_make_llm_client()` fails loudly per LAW II if OpenRouterClient unavailable (suggests --dry-run)
- Design doc estimated ~830 lines but snapshots + confirm/reject/merge + config layer intentionally deferred

**`tests/unit/test_mesh_cli.py` — 11 tests**
- TestWorkspaceCreate (2): basic, with seed question
- TestWorkspaceList (2): empty db, lists existing
- TestAskDryRun (2): retrieval result displayed, empty workspace
- TestStats (1): full workspace stats output
- TestEntitiesReview (2): no quarantined, shows quarantined with type/confidence/aliases
- TestErrorHandling (2): no command → help, invalid workspace → error

---

## NEXT SESSION — Start Unit 9: REST API server

Unit 9 exposes the mesh operations as a REST API (FastAPI).

### What Unit 9 delivers

- `api/server.py` — FastAPI app with routes for workspace CRUD, ask, ingest, stats, entities
- `api/schemas.py` — Pydantic request/response models for API endpoints
- Tests for API routes using FastAPI's TestClient

### Files to read first in next session

1. `docs/wiki_mesh_design.md` (API section if exists)
2. `src/polaris_graph/wiki/mesh/cli/main.py` — the CLI handlers show which mesh functions to expose
3. `requirements.txt` — verify fastapi + uvicorn already in deps
4. `src/polaris_graph/wiki/mesh/qa/ask.py` — async ask() maps naturally to async FastAPI routes

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
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py tests/unit/test_mesh_edge_discovery.py tests/unit/test_mesh_snowball.py tests/unit/test_mesh_lethal_retrieve.py tests/unit/test_mesh_compose.py tests/unit/test_mesh_qa.py tests/unit/test_mesh_cli.py -v
```

Expected: **261 passed** in ~109s (the embedding model loads once for the integration tests).

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
