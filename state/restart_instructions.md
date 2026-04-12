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

### Unit 3 — Entity canonicalization

**`src/polaris_graph/wiki/mesh/entity.py` (~600 lines)**
- 5-step FIX D2 canonicalization pipeline:
  1. Exact canonical_name match → confidence 1.0
  2. Alias match case-insensitive → confidence 0.95
  3. Cosine ≥ COSINE_MERGE_THRESHOLD (0.92) → merge, confidence = cosine, new surface added as alias
  4. Cosine in [0.80, 0.92) → optional LLM disambig:
     - YES → confidence 0.70 (DISAMBIG_YES_CONFIDENCE), still quarantined
     - NO / missing client / exception → fall through to step 5
  5. Insert new entity with confidence 0.5 (NEW_ENTITY_CONFIDENCE), user_confirmed=False → quarantined (FIX D2 gate = 0.8)
- `classify_entity_type()` heuristic: compound | method | organization | person | metric | concept
- Person regex requires honorific prefix (Dr./Prof./Mr./Mrs./Ms./Sr./Jr.) OR explicit middle-initial dot (`John A. Smith`) — fixed mid-Unit-3 because the original 3+ token heuristic mis-classified "Water Research Foundation" as person
- Cross-type filter in step 3 — prevents a 0.98-cosine collision between a compound named "PFOS" and an organization named "PFOS Consulting" from merging
- `canonicalize_entity(store, workspace_id, surface_form, embedding, disambig_client, entity_type)` is the single-entity entry point
- `canonicalize_entities_for_claim(store, workspace_id, claim_id, surface_forms, disambig_client, embeddings)` is the bulk helper — dedups surfaces, drops over-long (>80 chars) surfaces, takes an optional precomputed embedding dict so the orchestrator can batch-embed all unique surfaces in one `embed_texts` call instead of one model forward-pass per surface
- L2 distance → cosine conversion: `cos = 1 - 0.5 * d²` for unit vectors (empirically verified against sqlite-vec vec0 at CP-B)
- `_find_by_alias` is an O(n) linear scan over the workspace's entity rows (aliases are stored as JSON); at ≤ a few thousand entities per workspace this is fine, normalize into a separate table if the workspace grows past that

**`src/polaris_graph/schemas.py` — AtomicFact extension**
- New field `entities: list[str] = Field(default_factory=list)` with a description that tells the LLM to emit 1-5 short canonical entity names per fact
- `normalize_field_names` validator extended to handle the backward-compat path:
  - Missing key → `[]`
  - `None` → `[]`
  - Alternative keys (`entity_mentions`, `named_entities`, `mentions`) → rename
  - Comma-separated string → split on `,` and strip
  - List with mixed types → coerce each to str and strip
  - Garbage → `[]`

**`src/polaris_graph/wiki/mesh/claim_extract.py` — integration**
- New `MESH_SYSTEM` constant — wraps the imported `ANALYSIS_SYSTEM` with a suffix asking the LLM to populate `entities` (keeps `agents/analyzer.py` UNTOUCHED per CP-A lock c2)
- Parser `_parse_batch_to_claims` now emits `"entities": list[str]` in each claim dict (sanitized: stripped, empty dropped, over-long dropped)
- Orchestrator `extract_claims_from_source`:
  - New optional `disambig_client: DisambigClient | None = None` parameter
  - After parsing, collects the SORTED UNIQUE set of surface forms across all claims and embeds them once via `embed_texts` (amortizes the ~1-2s model forward-pass across all entities in the source)
  - Inside the transaction, after each `store.insert_claim(...)`, calls `await canonicalize_entities_for_claim(...)` with the precomputed embedding dict so claim + vector + entities + claim_entities links all land (or roll back) atomically

**`tests/unit/test_mesh_entity.py` — 46 tests**
- TestClassifyEntityType (7) — compound / method / organization / person / metric / concept, inc. regressions for "Water Research Foundation" + "Dr. Jane Smith"
- TestFindByCanonical (3), TestFindByAlias (3), TestVecNeighbours (4) — helper coverage including cosine formula verification
- TestCanonicalizeEntityFivePaths (11) — paths 1-5 + 3 path-4 sub-branches (disambig YES / NO / no-client / exception) + `test_path_3_cosine_just_above_threshold` (uses 0.93 not 0.92 because float32 quantization lands at 0.9199) + `test_type_filter_prevents_merge_with_high_cosine`
- TestCanonicalizeEntityValidation (2) — empty surface + unknown workspace
- TestCrossTypeFilter (1) — the compound-vs-organization collision case
- TestCanonicalizeEntitiesForClaim (6) — empty list short-circuit, multi-entity (uses orthogonal vectors to prevent accidental cosine merge), dedup, over-long skip, idempotent re-link, precomputed embedding pathway
- TestLLMDisambiguate (3) — YES / NO / exception (defensive default to NO)
- TestQuarantineSemantics (4) — FIX D2 new-entity-in-quarantine, confirm-removes-from-quarantine, exact-match-doesn't-requarantine, disambig-YES-still-quarantined
- **TestClaimExtractEntityIntegration (3)** — the Unit 2 → Unit 3 bridge: full `extract_claims_from_source` with mock LLM, one test populates 5 entities across 2 claims and verifies every entity + link landed (inc. classifier type assignment), one test exercises the legacy backward-compat path (no `entities` key in fact dict), one test verifies a duplicate entity across two claims produces 1 entity row + 2 claim_entities rows + `times_referenced=2`

### Unit 3 design corrections that happened during the build

1. **Person regex bug (caught during tests):** Original regex `^[A-Z][a-z]+(?:\s+[A-Z]\.?[a-z]*){2,}$` required 3+ title-cased tokens, which matched BOTH "John Michael Smith" (person) AND "Water Research Foundation" (organization). Tightened to require an explicit disambiguating signal: honorific prefix OR middle-initial dot.

2. **Float32 cosine quantization at boundary:** `_unit_vec(0.92)` stored as float32 and fed through sqlite-vec's L2 distance + formula back-conversion lands at ~0.9199, which is < 0.92, so the strict `>=` comparison falls to the disambig zone. Test uses 0.93 with a comment explaining the quantization.

3. **Orthogonal vs near-collinear test vectors:** `_unit_vec(0.2)` and `_unit_vec(0.3)` both live in the e₀-e₁ plane so their mutual cosine is ~0.995 — they LOOK different but are actually near-collinear. Added a `_orthogonal_vec(axis)` helper that produces basis-direction unit vectors (cosine 0 between distinct axes) for tests that need well-separated vectors.

4. **`"PFOSA"` not `"pfos acid"` for compound-type merge test:** `"pfos acid"` classifies as `concept` (starts lowercase, has a space, matches no specific rule), while the target is `compound`. The cross-type filter in step 3 blocks the merge. Switched to `"PFOSA"` which classifies as `compound` so the merge actually tests what it claims to test.

5. **Prompt integration strategy (CP-A lock c2):** Unit 3 does NOT touch `agents/analyzer.py`. Instead, `claim_extract.py` defines a `MESH_SYSTEM` constant that wraps `ANALYSIS_SYSTEM` with an entity-extraction suffix. This way the 40+ production runs that import `ANALYSIS_SYSTEM` directly from analyzer.py are completely unaffected.

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
