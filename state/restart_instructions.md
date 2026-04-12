# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 6 Complete, Ready for Unit 7

**Branch:** `PL`
**Last commits (local, not pushed):**
- `3a3c514` — Wiki Mesh Unit 1 — single-db schema + store + 43 tests
- `68e177e` — file_directory register for Unit 1 files (§2.1 bookkeeping)
- `860210a` — Wiki Mesh Unit 2 of 10 — ingest + claim_extract (foundation for Unit 3)
- `65875dd` — Wiki Mesh Unit 3 of 10 — entity canonicalization (FIX D2)
- `9f90a2f` — Wiki Mesh Unit 4 of 10 — edge discovery + snowball (FIX S4)
- `f1e95de` — restart_instructions doc fix
- `292a12f` — Wiki Mesh Unit 5 of 10 — lethal retrieval + gap classify (FIX D3, S5, S8)
- **Unit 6 commit pending** — compose/composer.py + compose/artifact_directives.py + tests (26 new tests)

**Status:** 6 of 10 wiki mesh units complete. Complete pipeline: ingest → extract → canonicalize → discover edges → retrieve → compose. 234/234 tests passing.

**Honest scope:** Unit 6 completes the core pipeline (question in → cited answer out). Q&A layer (Unit 7), CLI (Unit 8), API (Unit 9), and integration tests (Unit 10) are still ahead. The mesh can compose answers but doesn't yet have multi-turn threads or a user interface.

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue. User will resolve when back from their trip.

---

## What was just done

### Unit 6 — Compose + artifact directives (FIX S7)

**`src/polaris_graph/wiki/mesh/compose/composer.py` (~200 lines)**
- Fresh implementation (NOT adapted from wiki_composer.py — that's coupled to WikiResult/section-based reports)
- Single-answer composition from RetrievalResult: hydrates claims, builds inline bibliography (by first source appearance, dedupes URLs), formats numbered claims for LLM, post-processes (CoT scrub → [REF:N]→[N] → artifact rendering)
- `_ComposeClient` protocol for LLM (same pattern as Units 2-3). Tests inject mock, production passes OpenRouterClient
- Simpler Q&A-style `MESH_COMPOSE_SYSTEM` prompt (8 rules vs wiki_composer's 13)
- Empty retrieval returns "No relevant claims" without LLM call
- `ComposeResult` holds answer_text, bibliography, claim_ids_used, artifact_paths

**`src/polaris_graph/wiki/mesh/compose/artifact_directives.py` (~120 lines)**
- FIX S7 validation framework: validates claim_ids exist before rendering, strips invalid blocks with logged warning
- TABLE renderer: inline markdown from claims with keyword-based row extraction, MIN_TABLE_ROWS=2 guard
- CHART/FLOW/DECK/FLASHCARDS: stub entries returning "_(artifact deferred: {kind})_" — FIX S7 validation still runs
- `_parse_payload` handles "claim_ids=a,b;x_label=Year" → dict

**`tests/unit/test_mesh_compose.py` — 26 tests**
- TestScrubCoT (3), TestNormalizeRefs (3), TestFormatClaims (1), TestFormatBibliography (1): helpers
- TestHydrateClaims (3): hydration + bib building, same-source dedup, missing claim skipped
- TestComposeAnswer (4): end-to-end mock LLM, empty retrieval, CoT scrubbed, REF normalized
- TestParsePayload (3), TestRenderArtifacts (6), TestArtifactPattern (2): artifact directives

---

## NEXT SESSION — Start Unit 7: Q&A layer + multi-turn threads

Unit 7 wraps the retrieve → compose pipeline in a conversational Q&A layer with multi-turn thread support and stage 0 coreference resolution.

### What Unit 7 delivers

- `qa/thread.py` — Thread model (thread_id, workspace_id, list of Q&A turns), persistence in the mesh store
- `qa/ask.py` — `ask(store, workspace_id, question, thread_id)` → orchestrates retrieve → compose → store answer, handles coreference via thread history
- Stage 0 coreference wiring — prepend last 3 Q&A pairs to the question before retrieval
- NEARBY auto-expansion trigger — when gap_classify returns NEARBY and budget allows, auto-expand search
- Tests for thread persistence, coreference resolution, ask orchestration

### Files to read first in next session

1. `docs/wiki_mesh_design.md` §7 stage 0 (coreference), §10 (failure modes)
2. `src/polaris_graph/wiki/mesh/retrieve/lethal.py` — `resolved_question` param ready for wiring
3. `src/polaris_graph/wiki/mesh/compose/composer.py` — `compose_answer` is the downstream call
4. `src/polaris_graph/wiki/mesh/retrieve/gap_classify.py` — NEARBY budget for auto-expansion
5. `src/polaris_graph/wiki/mesh/store.py` — check if thread/answer tables exist in schema

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
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py tests/unit/test_mesh_edge_discovery.py tests/unit/test_mesh_snowball.py tests/unit/test_mesh_lethal_retrieve.py tests/unit/test_mesh_compose.py -v
```

Expected: **234 passed** in ~108s (the embedding model loads once for the integration tests).

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
