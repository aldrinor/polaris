# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 4 Complete, Ready for Unit 5

**Branch:** `PL`
**Last commits (local, not pushed):**
- `3a3c514` — Wiki Mesh Unit 1 — single-db schema + store + 43 tests
- `68e177e` — file_directory register for Unit 1 files (§2.1 bookkeeping)
- `860210a` — Wiki Mesh Unit 2 of 10 — ingest + claim_extract (foundation for Unit 3)
- `65875dd` — Wiki Mesh Unit 3 of 10 — entity canonicalization (FIX D2)
- **Unit 4 commit pending** — edge_discovery.py + snowball.py + tests (45 new tests)

**Status:** 4 of 10 wiki mesh units complete. L1 sources + L2 claims + L3 entities + L4 edges + snowball formulas all working. 183/183 tests passing. Build is advisor-monitored with checkpoints per unit.

**Honest scope:** Unit 4 completes the foundation layers (ingest through edge discovery). The snowball formulas are proven by tests but triggers are deferred until Units 5-7. Units 5-10 still ahead: lethal retrieval, compose+artifacts, Q&A, CLI, API, integration tests. The wiki mesh is NOT a shippable product yet.

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue. User will resolve when back from their trip.

---

## What was just done

### Unit 4 — Edge discovery + snowball formulas

**`src/polaris_graph/wiki/mesh/edge_discovery.py` (~230 lines)**
- Cosine-only v1 edge typing (no NLI) — avoids flan-t5-large 512-token context limit and "NLI too strict for niche domains" failure mode (memory note #19)
- Non-overlapping thresholds:
  - `corroborates`: cosine ≥ 0.85 (any source pair). evidence_weight = max(0.7, cosine)
  - `contradicts`: cosine ∈ [0.80, 0.85) from DIFFERENT sources only. evidence_weight = cosine. v1 limitation: these are cosine-based candidates, not NLI-confirmed. The ×0.7 retrieval penalty applies immediately; user review resolves false positives.
  - `elaborates`: deferred to v2 with NLI infrastructure
- `discover_edges_for_claims(store, workspace_id, new_claim_ids, embeddings)` — runs OUTSIDE the claim-insert transaction (separate pass). One KNN search per new claim (top-20 candidates), O(k) not O(N)
- `_read_claim_embedding` reads back from vec0 via the mapping table. Column is `entity_id` (generic name across all 4 mapping tables, found during test)
- `_distance_to_cosine` uses the verified `cos = 1 - 0.5 * d²` formula for unit vectors
- Idempotent via store.insert_edge (same claim pair + kind → same edge returned)
- `EdgeDiscoveryResult` tracks edge_ids, corroboration_count, contradiction_count, skipped

**`src/polaris_graph/wiki/mesh/snowball.py` (~110 lines)**
- Pure bounded formulas from design doc §8 (FIX D3, FIX S4):
  - M1 `usage_bonus(times_used, age_days)`: `1 + log(1+uses) * 0.1 * exp(-age/365)`. Max ~1.46 at 100 uses fresh, decays to ~1.0 at 2yr. Always ≥ 1.0.
  - M2 `corroboration_factor(count)`: `1 + 0.3 * sqrt(count)`. Practical max ~1.95 at count=10. Always ≥ 1.0.
  - M3 `contradiction_penalty(has_contradiction)`: fixed ×0.7 or ×1.0.
  - M4 `upload_gravity_boost(is_upload)`: fixed ×1.3 or ×1.0.
  - `lethal_snowball_score()`: multiplicative composition of all 4 for Unit 5's lethal re-rank.
- Triggers deferred to Units 5-7 (retrieval / compose / Q&A). Unit 4 deliverable is: formulas exist, bounds proven by tests, ready for Unit 5+ to call.

**`tests/unit/test_mesh_edge_discovery.py` — 20 tests**
- TestDistanceToCosine (4): identical/orthogonal/opposite/clamping
- TestReadClaimEmbedding (2): round-trip via vec0 mapping + missing claim
- TestDiscoverEdgesCorroboration (3): high cosine → edge, same-source still allowed, evidence_weight clamped
- TestDiscoverEdgesContradiction (2): medium cosine different source → edge, same source → no edge
- TestDiscoverEdgesNoEdge (1): low cosine → no edge
- TestDiscoverEdgesSelfExclusion (1): single claim → no self-edge
- TestDiscoverEdgesIdempotent (1): re-run → same edges, 1 row in store
- TestDiscoverEdgesValidation (4): empty list, missing claim, wrong workspace, unknown workspace
- TestDiscoverEdgesPrecomputedEmbedding (1): optional embeddings dict used
- TestDiscoverEdgesMultipleClaims (1): batch of new claims

**`tests/unit/test_mesh_snowball.py` — 25 tests**
- TestUsageBonus (8): zero/negative → 1.0, always ≥ 1.0 across 20 combos, design doc bounds (100 uses fresh ≈ 1.46, 100 uses 2yr ≈ 1.06), decay monotonicity, use monotonicity
- TestCorroborationFactor (7): zero/negative → 1.0, always ≥ 1.0, exact sqrt at 1/4/9, practical max at 10, theoretical max at 100, sublinear growth
- TestContradictionPenalty (2): False → 1.0, True → 0.7
- TestUploadGravityBoost (2): False → 1.0, True → 1.3
- TestLethalSnowballScore (6): baseline only, all factors combined, contradiction reduces, upload boosts, zero base stays zero, worst-case max bounded <10x

### Unit 4 bugs caught during build

1. **`entity_id` not `claim_id` in mapping table:** `vec_claims_mapping` (and all 4 mapping tables) use `entity_id` as a generic column name. `_read_claim_embedding` initially used `claim_id` which doesn't exist → `sqlite3.OperationalError`. Fixed to `entity_id`.

2. **Negative L2 distance clamping test:** L2 distances are always ≥ 0, so testing `_distance_to_cosine(-1.0)` is unrealistic. Replaced with an oversized distance (3.0) → clamped to -1.0.

---

## NEXT SESSION — Start Unit 5: Lethal retrieval

Unit 5 implements the 6-stage retrieval algorithm that surfaces the most relevant claims from the mesh for a given query. Design is in `docs/wiki_mesh_design.md` §7.

### What Unit 5 delivers

- `retrieve/lethal.py` (~400 lines) — 6-stage retrieval algorithm: (0) coreference resolution, (1) vec KNN seed, (2) entity cosine filter, (3) corroboration walk (1 hop), (4) contradiction surface (always include), (5) elaboration follow, (6) lethal re-rank with snowball factors + 10% exploration reservation
- `retrieve/gap_classify.py` (~150 lines) — IN_SCOPE/NEARBY/ADJACENT/ORTHOGONAL classifier + NEARBY daily budget (FIX S6)
- Tests for each retrieval stage + the composite re-ranking + the exploration reservation
- Integration: wire snowball formulas from Unit 4's snowball.py into the lethal re-rank

### Advisor checkpoints to run

- **CP-A pre-code:** show advisor the lethal.py plan alongside the snowball formulas + store.search_claims_by_vector + store.get_edges_from. Key questions: (1) how many KNN candidates for the seed stage? (2) should exploration reservation be deterministic or random? (3) what's the gap classification strategy when there are no claims at all? (4) does the age-decayed bonus need claim.last_used_at (currently unused column)?
- **CP-B mid:** after lethal.py seed+corroboration stages written — catch re-rank issues
- **CP-C post-code + tests:** full review
- **CP-D robustness:** end-to-end retrieval on a realistic claim graph

### Files to read first in next session

1. `docs/wiki_mesh_design.md` §7 (the lethal retrieval algorithm)
2. `src/polaris_graph/wiki/mesh/snowball.py` — the 4 bounded formulas Unit 5 will call during re-rank
3. `src/polaris_graph/wiki/mesh/edge_discovery.py` — understand the edge types available for walk stages
4. `src/polaris_graph/wiki/mesh/store.py` — `search_claims_by_vector`, `get_edges_from`, `get_claim`
5. `tests/unit/test_mesh_store.py::TestVectorSearch` — existing KNN tests

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
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py tests/unit/test_mesh_edge_discovery.py tests/unit/test_mesh_snowball.py -v
```

Expected: **183 passed** in ~85-90s (the embedding model loads once for the integration tests).

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
