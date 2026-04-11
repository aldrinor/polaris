# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 2 Complete, Ready for Unit 3

**Branch:** `PL`
**Last commits (local, not pushed):**
- `3a3c514` — Wiki Mesh Unit 1 — single-db schema + store + 43 tests
- `68e177e` — file_directory register for Unit 1 files (§2.1 bookkeeping)
- **Unit 2 commit pending** — ingest + claim_extract + 49 more tests (will be committed after state docs are updated)

**Status:** 2 of 10 wiki mesh units complete. Foundation (L1 sources + L2 claims with embeddings) is usable standalone; no retrieval/compose/CLI yet. 92/92 tests passing. Build is advisor-monitored with 4+ checkpoints per unit.

**Honest scope:** Unit 2 delivers a usable L1→L2 data pipeline (PDF/HTML/markdown → source rows → atomic claims with tier, char-span, embedding), but it is NOT a shippable wiki mesh product. Units 3-10 still ahead: entity canonicalization, edge discovery, lethal retrieval, compose+artifacts, Q&A, CLI, API, integration tests.

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue (see `logs/session_log.md` 2026-04-11 session). User will resolve when back from their trip and push all local commits at once.

---

## What was just done

### Unit 2 — Ingest + claim extraction

**`src/polaris_graph/wiki/mesh/ingest.py` (~370 lines)**
- `ingest_file(store, workspace_id, file_path, ...)` — upload/web path for PDF/HTML/markdown/text. Content-hash dedup. Atomic temp+rename writes. Deterministic `_predicted_src_id` mirrors `store._make_id` so markdown filename matches the row id before the insert.
- `ingest_web_content(store, workspace_id, url, raw_content, ...)` — for web-fetched HTML (via trafilatura) or pre-cleaned markdown (via Jina Reader pattern).
- `read_source_text(file_path)` — **the load-bearing helper**. Strips the internal `<!-- src_id: ... -->` header before returning body. Downstream code that does char-span lookup against a claim's `direct_quote` MUST use this helper, not raw `Path.read_text()`. Without it, every char offset is shifted by ~64 characters and provenance drill-down points at the wrong paragraph.
- File-I/O-outside-transaction ordering: write file first, insert row second. Orphan file is harmless; row without a file is not.
- `_extract_text()` dispatches: `.pdf` → docling, `.html/.htm` → trafilatura, `.md/.markdown/.txt` → UTF-8 read. Raises MeshStoreError on unsupported types (LAW II, no silent fallbacks).

**`src/polaris_graph/wiki/mesh/claim_extract.py` (~420 lines)**
- REUSES (does not duplicate) production `ANALYSIS_SYSTEM` prompt from `src.polaris_graph.agents.analyzer` and `SourceAnalysisBatch` schema from `src.polaris_graph.schemas`. Those schemas have 40+ runs of Qwen field-name normalization via `@model_validator(mode="before")` — rewriting them would introduce silent parsing bugs.
- Split into two layers per advisor CP-A:
  - `_parse_batch_to_claims(parsed, source_body, source_url)` — pure function, no I/O, returns `(list[claim_dict], ExtractionResult)`. 80% of test coverage lives here.
  - `extract_claims_from_source(client, store, workspace_id, source_page_id, query)` — orchestrator, reads body via `read_source_text()`, calls LLM, embeds, inserts atomically.
- Ports these filters from `_analyze_batch` (lines 2043-2083): statement length < 10, quote word count < PG_MIN_QUOTE_WORDS=15, URL fragments, cookie/consent boilerplate. Does NOT port: fetch_method, citation_count, STORM perspective, source_content_store writes (those are production-pipeline specific).
- Char-span lookup against the BODY (not the raw file). Unverifiable quotes get sentinel `(0, 1)` + BRONZE tier instead of being dropped — the "NLI too strict for niche domains" memory lesson.
- Tier assignment — 3-signal v1 rule (advisor CP-A):
  - GOLD: `relevance ≥ 0.7 AND source_quality ≥ 0.6 AND verified`
  - SILVER: `(relevance ≥ 0.4 AND verified) OR relevance ≥ 0.5`
  - BRONZE: everything else
- has_numeric regex catches 95% CI, p-values, sample sizes, effect sizes, percentages, OR/HR/RR/SMD/WMD/MD.
- Embeddings via `src.utils.embedding_service.embed_texts` (384-dim, all-MiniLM-L6-v2-style) — generated BEFORE opening the transaction (slow CPU/GPU work) but the actual vector INSERT happens inside the same transaction as the claim row (atomicity preserved via FIX D1).

**`tests/unit/test_mesh_ingest.py` — 21 tests**
- Full file ingest round-trip (upload creates source row + markdown file)
- Dedup without rewriting (mtime preserved)
- All error paths (missing file, unsupported ext, bad workspace, short text, out-of-range sig_authority)
- Default sig_authority rules (upload=0.95, web=0.5)
- Metadata persistence (title, authors, year, doi, venue)
- Web content via trafilatura (strips nav/footer)
- Markdown passthrough
- Dedup by content hash independent of URL
- **The key `test_strips_header` test that validates `read_source_text` prevents the char-offset corruption bug** — asserts `raw_offset - body_offset == header_length` exactly
- `_predicted_src_id` mirrors `store._make_id` byte-for-byte

**`tests/unit/test_mesh_claim_extract.py` — 28 tests**
- **The killer 5-fact integration test** (advisor's specific CP-A recommendation): one batch with GOLD/filtered-short-quote/filtered-cookie/BRONZE-unverified/has_numeric-GOLD, verifies filter counts, tier assignments, has_numeric flags, and char spans all correct in a single test covering 6 code paths.
- Individual filter tests: short statement, short quote, URL fragment, cookie text
- Wrong source_url filtering (analyses for other URLs ignored)
- Empty batch returns empty
- 4 tier branches exhaustively tested
- Char-span lookup: exact match, missing quote, empty quote, empty body
- has_numeric regex parametrized with 6 positive + 2 negative cases
- Orchestrator end-to-end with MockClient → claims inserted + vectors queryable via KNN (**closes the "invisible claims" gap the advisor caught at CP-C**)
- Missing source raises
- Wrong workspace raises
- Atomic batch insert: simulated failure mid-batch → transaction rolls back, zero claims committed

**`scripts/pg_mesh_unit2_stress.py` — stress test (not in pytest suite)**
- Ingests 3 sources + runs mock-LLM extraction on each
- Result: 3 sources, 7 claims, 7 vectors (3 filtered out as expected — short statement, short quote, cookie), 6 GOLD + 1 SILVER
- Reopen-from-disk preserves everything
- KNN lookup returns the expected claim
- Consistency: `vec_claims` count matches `workspace.claim_count` matches mapping-table count
- PASSED

### Unit 2 design corrections that happened during the build

1. **Header offset bug (CP-B):** initial `_write_source_markdown` prepended a `<!-- src_id: ... -->` comment but didn't account for it in char-span lookup. Every `char_start` would have been off by ~64 characters. Fixed by adding `read_source_text()` helper that strips the header before returning body; `claim_extract.py` uses it exclusively.

2. **Embedding integration miss (CP-C):** initial `extract_claims_from_source` inserted claims without embeddings. Unit 5's lethal retrieval opens with a KNN search → would have found zero claims. Fixed by calling `embed_texts()` on claim statements before opening the transaction, zipping embeddings into the claim dicts, passing as the `embedding=` kwarg to `store.insert_claim` (which in turn writes to `vec_claims` inside the transaction).

3. **Dimension mismatch (CP-C):** schema was pinned to `float[768]` based on an initial wrong assumption about sentence-transformers defaults. Production `embed_texts` returns **384-dim** vectors. Fixed by updating `schema.py VECTOR_DDL`, `store.EMBEDDING_DIM`, and `docs/wiki_mesh_design.md` to float[384].

4. **INSERT OR REPLACE not supported by vec0 (CP-C, surfaced in test_insert_claim_idempotent from Unit 1):** vec0 virtual tables reject `INSERT OR REPLACE` at runtime ("UNIQUE constraint failed on primary key" even for the same rowid). `_insert_vector` now does try-INSERT, catch `sqlite3.IntegrityError|OperationalError`, fall back to UPDATE with defensive re-raise on non-UNIQUE errors.

5. **SourceAnalysisBatch dict-construction gotcha (during test fixing):** the production `filter_invalid_analyses` validator runs in `mode="before"` and iterates `data["analyses"]` expecting dicts — it silently drops pre-instantiated `SourceAnalysis` objects because they don't pass `isinstance(item, dict)`. Test helper `_build_batch` goes through `SourceAnalysisBatch.model_validate({"analyses": [...]})` with dict input to satisfy the validator. Documented inline so future test writers don't hit the same trap.

---

## NEXT SESSION — Start Unit 3: Entity canonicalization

Unit 3 turns isolated claim strings into a canonical entity index. The design is in `docs/wiki_mesh_design.md` §6.

### What Unit 3 delivers
- A 5-step canonicalization pipeline (exact match → alias → cosine ≥ 0.92 → LLM disambig 0.80–0.92 → insert quarantined)
- Integration pass in `claim_extract.py` — after parsing a batch, extract entity surface forms per claim, canonicalize via `mesh/entity.py`, link via `store.link_claim_entity`
- Tests for all 5 paths + the FIX D2 quarantine semantics (entities with `confidence < 0.8 AND NOT user_confirmed` are excluded from retrieval expansion)

### Files to create
- `src/polaris_graph/wiki/mesh/entity.py` — the canonicalization pipeline (~300 lines)
- `tests/unit/test_mesh_entity.py` — the 5 paths + quarantine semantics + LLM disambig mock

### Files to modify
- `src/polaris_graph/wiki/mesh/claim_extract.py` — add post-parse entity extraction + link pass inside `extract_claims_from_source`. This is a small addition (~30 lines), NOT a rewrite. The new pass runs AFTER `_parse_batch_to_claims` and BEFORE the claim insert, so entities + claims + claim_entities links all go in the same transaction.

### Advisor checkpoints to run
- **CP-A pre-code (MOST IMPORTANT):** show advisor `mesh/entity.py` plan alongside `store.insert_entity` + `store.link_claim_entity` + `store.get_quarantined_entities`. Ask: (1) what entity types should v1 support (compound, method, organization, person, metric)? (2) How should we extract surface forms per claim — another LLM call, or piggyback on the existing extraction (`AtomicFact` schema doesn't have an entity field)? (3) How should the LLM disambiguation prompt be structured for the 0.80-0.92 cosine zone? (4) What's the test coverage for the quarantine path?
- **CP-B mid:** after `mesh/entity.py` is written but before `claim_extract.py` integration — catch any architectural drift from the plan
- **CP-C post-code + tests:** full review with mocked LLM cases
- **CP-D robustness + stress test:** end-to-end run with 5+ entities including the ambiguous "RO" / "GAC" / "PFAS" cases advisor called out in CP-A

### Files to read first in next session
1. `docs/wiki_mesh_design.md` §6 (the Unit 3 entity canonicalization design)
2. `src/polaris_graph/wiki/mesh/store.py` — `insert_entity`, `link_claim_entity`, `get_quarantined_entities`, `confirm_entity` are already in place from Unit 1
3. `src/polaris_graph/wiki/mesh/claim_extract.py` — the `extract_claims_from_source` orchestrator, which Unit 3 will extend with an entity pass
4. `src/polaris_graph/schemas.py` — `AtomicFact` schema (does it have any entity-related fields already?)
5. `tests/unit/test_mesh_store.py::TestEntity` — the existing store-level tests; Unit 3's tests will build on them

---

## Key invariants to preserve across Unit 3 and beyond

- **Single database file.** Never introduce a second store for vectors — FIX D1 depends on this.
- **Over-fetch KNN.** Any new vector search path must use the `k × 3 → filter → LIMIT k` pattern from `search_claims_by_vector`.
- **Entity quarantine is not optional.** Any code path that inserts an entity with `confidence < 0.8` must NOT let it participate in retrieval expansion until user-confirmed.
- **usage_boost is bounded.** Anything that modifies edge weights must go through `bump_edge_usage_boost()` or respect the schema CHECK constraint.
- **Header-strip before char-span.** Any downstream code that reads an ingested source file MUST use `ingest.read_source_text()`, not raw `Path.read_text()`. The inline markdown header would otherwise shift every char offset.
- **Fail loudly.** LAW II. No silent fallbacks, no partial inserts, no default-value substitutions.
- **Reuse, don't duplicate.** `ANALYSIS_SYSTEM` and `SourceAnalysisBatch` are imported from `polaris_graph.agents.analyzer` and `polaris_graph.schemas` respectively. If Unit 3 needs a similar prompt, reuse an existing one if possible.

---

## Running the tests

```
cd C:/POLARIS
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py -v
```

Expected: **92 passed** in ~60-75s (the embedding model loads in the orchestrator tests).

Optional stress test:
```
python scripts/pg_mesh_unit2_stress.py
```
Expected: `STRESS TEST PASSED` with 3 sources, 7 claims, 7 vectors, KNN lookup working after reopen.

---

## Long-term backlog (carried across units)

- `vacuum_orphan_vectors()` for post-delete cleanup (Unit 1)
- Schema migration tool for future SCHEMA_VERSION bumps (Unit 1)
- Exception-string fragility in `_insert_vector` (Unit 1)
- `_row_id_to_int` 63-bit hash collision warning (Unit 1, documented in code)
- Decouple `ANALYSIS_SYSTEM` from `agents/analyzer.py` into standalone prompt file (Unit 2 CP-D)
- Real OpenRouter E2E test for `extract_claims_from_source` (Unit 2 CP-D — awaiting credit restoration)
- Multi-user auth (v2 scope)
- 768-/1024-/4096-dim embedding support (currently pinned at 384-dim via sqlite-vec DDL)

---

## GitHub push backlog

- Remote `origin` = `https://github.com/aldrinor/polaris` (configured but auth blocked)
- Git Credential Manager is authenticated as `sotaleung-wec` (different account from `aldrinor`)
- User logged out `sotaleung-wec` via GitHub web but GCM cache still held the token; cleared via `git credential-manager erase`
- Subsequent push hangs because GCM tries to open a browser window to re-auth as `aldrinor`, but my headless shell can't receive the popup
- **User to resolve when back home** by running `!git push -u origin PL` in their own Claude Code prompt — any browser popup will reach their display
- All local commits (Unit 1 + Unit 2 + any subsequent units) will ship in one push when the auth is resolved
