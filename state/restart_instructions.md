# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 5 Complete, Ready for Unit 6

**Branch:** `PL`
**Last commits (local, not pushed):**
- `3a3c514` — Wiki Mesh Unit 1 — single-db schema + store + 43 tests
- `68e177e` — file_directory register for Unit 1 files (§2.1 bookkeeping)
- `860210a` — Wiki Mesh Unit 2 of 10 — ingest + claim_extract (foundation for Unit 3)
- `65875dd` — Wiki Mesh Unit 3 of 10 — entity canonicalization (FIX D2)
- `9f90a2f` — Wiki Mesh Unit 4 of 10 — edge discovery + snowball (FIX S4)
- `f1e95de` — restart_instructions doc fix
- **Unit 5 commit pending** — retrieve/lethal.py + retrieve/gap_classify.py + tests (25 new tests)

**Status:** 5 of 10 wiki mesh units complete. Complete read+write path: ingest → extract → canonicalize → discover edges → retrieve. 208/208 tests passing.

**Honest scope:** Unit 5 delivers the first user-facing feature — lethal retrieval that surfaces the most relevant claims from the mesh. But compose (Unit 6), Q&A (Unit 7), CLI (Unit 8), API (Unit 9), and integration tests (Unit 10) are still ahead. The mesh can retrieve but can't yet compose answers from the retrieved claims.

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue. User will resolve when back from their trip.

---

## What was just done

### Unit 5 — Lethal retrieval + gap classification

**`src/polaris_graph/wiki/mesh/retrieve/lethal.py` (~310 lines)**
- 6-stage lethal retrieval algorithm implementing FIX D3, S5, S8:
  - Stage 0 (coreference): skipped for v1, accepts optional `resolved_question` for Unit 7
  - Stage 1 (semantic seed): KNN over ALL tiers (GOLD/SILVER/BRONZE, k=80). BRONZE included because graph edges can promote them (pre-flagged at Unit 4 audit)
  - Stage 2 (entity expansion): simple string matching against entity canonical_name + aliases (no LLM). FIX D2 quarantine gate (confidence ≥ 0.8 OR user_confirmed). FIX S5 cosine filter (≥ 0.5)
  - Stage 3 (corroboration walk): 1-hop walk via corroboration edges, decay 0.7, limit 5, min_weight 0.6
  - Stage 4 (contradiction surface): always include contradicting claims at score 0.3
  - Stage 5 (elaboration follow): structurally present, no-op until v2 creates elaborates edges
  - Stage 6 (lethal re-rank): 8-factor multiplicative score using snowball.py formulas + source authority + entity match fraction + recency. 10% exploration reservation for unseen GOLD claims (FIX D3)
- `RetrievalResult` tracks scored_claims, gap_category, per-stage counts

**`src/polaris_graph/wiki/mesh/retrieve/gap_classify.py` (~90 lines)**
- 4-category gap classifier: IN_SCOPE (≥5 claims + max ≥ 0.3), NEARBY (≥1 claim), ADJACENT (entity only), ORTHOGONAL (nothing)
- FIX S6 NEARBY budget: `check_nearby_budget` resets daily counter, `increment_nearby_budget` tracks usage
- Auto-expansion trigger deferred to Unit 7+

**`tests/unit/test_mesh_lethal_retrieve.py` — 25 tests**
- TestRecencyFactor (4) + TestDistanceToCosine (1): helper functions
- TestLethalRetrieveBasic (4): empty workspace → ORTHOGONAL, single claim found, BRONZE included, unknown workspace raises
- TestLethalRetrieveCorroborationWalk (1): edge walks neighbor into pool
- TestLethalRetrieveContradiction (1): both original + contradicting claim surface
- TestLethalRetrieveReRank (1): upload source ranked higher than web
- TestLethalRetrieveExploration (1): reservation fills with unseen claims
- TestGapClassify (5): all 4 categories tested
- TestNearbyBudget (3): fresh budget, depletion, nonexistent workspace
- TestEntityMatchFraction (4): full/partial/no overlap, empty question entities

---

## NEXT SESSION — Start Unit 6: Compose + artifact renderers

Unit 6 takes retrieved claims and composes them into structured answers with artifact directives. Design is in `docs/wiki_mesh_design.md` §9.

### What Unit 6 delivers

- `compose/composer.py` — adapted from existing `src/polaris_graph/wiki/wiki_composer.py` (already built and validated in Phase 0B). Takes retrieved claims from Unit 5's `lethal_retrieve`, composes structured answers with inline citations.
- `compose/artifact_directives.py` — prompt fragments for TABLE/CHART/FLOW/DECK artifacts with FIX S7 validation (claim_ids + data type checks, strip invalid blocks)
- Tests for composition + artifact validation

### Advisor checkpoints to run

- **CP-A pre-code:** review the existing wiki_composer.py, decide what to adapt vs rewrite. Key: does Unit 6 compose from RetrievalResult.scored_claims, or does it need a different interface?
- **CP-B mid:** after composer adapted, before artifact validation
- **CP-C post-code + tests:** full review

### Files to read first in next session

1. `docs/wiki_mesh_design.md` §9 (artifact generation with FIX S7 validation)
2. `src/polaris_graph/wiki/wiki_composer.py` — existing compose path (Phase 0B, already validated)
3. `src/polaris_graph/wiki/mesh/retrieve/lethal.py` — `RetrievalResult` is the input to compose
4. `src/polaris_graph/wiki/mesh/store.py` — `get_claim`, `get_source` for claim hydration

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
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py tests/unit/test_mesh_edge_discovery.py tests/unit/test_mesh_snowball.py tests/unit/test_mesh_lethal_retrieve.py -v
```

Expected: **208 passed** in ~110s (the embedding model loads once for the integration tests).

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
