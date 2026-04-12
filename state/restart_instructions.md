# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 3 Complete, Ready for Unit 4

**Branch:** `PL`
**Last commits (local, not pushed):**
- `3a3c514` — Wiki Mesh Unit 1 — single-db schema + store + 43 tests
- `68e177e` — file_directory register for Unit 1 files (§2.1 bookkeeping)
- `860210a` — Wiki Mesh Unit 2 of 10 — ingest + claim_extract (foundation for Unit 3)
- **Unit 3 commit pending** — entity.py + schemas.py extension + claim_extract.py integration + test_mesh_entity.py (46 new tests)

**Status:** 3 of 10 wiki mesh units complete. L1 (sources) + L2 (claims) + L3 (entities) all working end-to-end with atomicity preserved in a single transaction. 138/138 tests passing. Build is advisor-monitored with 4+ checkpoints per unit.

**Honest scope:** Unit 3 delivers a working L3 entity canonicalization pipeline tightly integrated into the L2 claim-extract path, BUT units 4-10 still ahead: edge discovery, lethal retrieval, compose+artifacts, Q&A, CLI, API, integration tests. The wiki mesh is NOT a shippable product yet.

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

## NEXT SESSION — Start Unit 4: Edge discovery + snowball

Unit 4 turns isolated claims + entities into a knowledge graph with typed edges between claims. Design is in `docs/wiki_mesh_design.md` §7.

### What Unit 4 delivers

- `mesh/edge_discovery.py` (~350 lines) — candidate edges via vec KNN over claims, edge type via NLI (corroborates / contradicts / elaborates), evidence_weight derived from cosine × NLI confidence
- `mesh/snowball.py` (~120 lines) — bounded feedback formulas from FIX S4: age-decayed retrieval bonus, corroboration count reinforcement capped at 0.2, upload gravity for user-promoted sources
- Tests: edge type classification, usage_boost clamp at 0.2, snowball bounds
- Integration into `extract_claims_from_source`: after claim insert + entity canonicalize, run edge discovery to find relationships between the new claim and existing claims (same workspace, shared entities prioritized, KNN fallback)

### Advisor checkpoints to run

- **CP-A pre-code (MOST IMPORTANT):** show advisor `mesh/edge_discovery.py` plan alongside `store.insert_edge` + `store.bump_edge_usage_boost` + `store.get_edges_from`. Ask: (1) what NLI model to use for edge typing (is flan-t5-large from production acceptable, or do we need something lighter)? (2) Should edge discovery run inside the same transaction as claim insert, or as a background pass? (3) What's the dedup policy — do we find new edges on EVERY claim insert, or only periodically? (4) How do we handle the combinatorial explosion (N claims → N² candidate edges)? (5) What test coverage for edge-type classification accuracy?
- **CP-B mid:** after `edge_discovery.py` is written but before `snowball.py` / integration — catch any architectural drift
- **CP-C post-code + tests:** full review with mocked NLI cases
- **CP-D robustness:** end-to-end run with a realistic claim graph (use the Unit 3 integration test's 5-entity corpus as a seed)

### Files to read first in next session

1. `docs/wiki_mesh_design.md` §7 (the Unit 4 edge discovery design)
2. `src/polaris_graph/wiki/mesh/store.py` — `insert_edge`, `bump_edge_usage_boost`, `get_edges_from`, `get_edges_from_kind` are already in place from Unit 1
3. `src/polaris_graph/wiki/mesh/claim_extract.py` — `extract_claims_from_source` orchestrator, which Unit 4 will extend with an edge discovery pass
4. `src/polaris_graph/wiki/mesh/entity.py` — understand how Unit 3 hooked in so Unit 4 can follow the same pattern
5. `tests/unit/test_mesh_store.py::TestEdge` — existing store-level edge tests

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

---

## Running the tests

```
cd C:/POLARIS
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py -v
```

Expected: **138 passed** in ~75-80s (the embedding model loads once for the integration tests).

---

## Long-term backlog (carried across units)

- `vacuum_orphan_vectors()` for post-delete cleanup (Unit 1)
- Schema migration tool for future SCHEMA_VERSION bumps (Unit 1)
- Exception-string fragility in `_insert_vector` (Unit 1)
- `_row_id_to_int` 63-bit hash collision warning (Unit 1, documented in code)
- Decouple `ANALYSIS_SYSTEM` from `agents/analyzer.py` into standalone prompt file (Unit 2 CP-D)
- Real OpenRouter E2E test for `extract_claims_from_source` (Unit 2 CP-D — awaiting credit restoration)
- Normalized alias table at scale — `_find_by_alias` is O(n) linear scan; once a workspace has > few thousand entities, move aliases to a separate indexed table (Unit 3 CP-B note)
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
