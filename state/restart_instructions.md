# Restart Instructions

## Current State (2026-04-11) — Wiki Mesh Unit 1 Complete

**Branch:** `PL`
**Last commit:** `efdaeb9` (compose-side work — synthesis section augmentation)
**Uncommitted:** Wiki Mesh Unit 1 — design doc + schema.py + store.py + 39-test suite (not yet committed; pending user decision whether to commit Unit 1 as one block or wait until more units land)
**Status:** Option A adopted — mesh design locked with all 10 advisor fixes integrated; Unit 1 code + tests green; ready for Unit 2 (ingest + claim extraction).

---

## What was just done

The user asked for a full review of the persistent wiki mesh architectural plan I'd drawn up. The advisor's deep review identified **10 structural bugs**, three deadly:
- **D1** Dual-store (ChromaDB + SQLite) consistency race
- **D2** Entity canonicalization permanently poisoning the mesh
- **D3** Snowball becoming a popularity trap

The user chose **Option A**: adopt the fixes, update the design doc, then build the spine. Here's what shipped in this session:

### Design doc (`docs/wiki_mesh_design.md`)
Complete 20-section plan with all 10 fixes integrated inline. Replaces the ephemeral "plan mode" file at `plans/vivid-waddling-riddle.md`. This is the durable reference for future sessions.

### Unit 1 code (`src/polaris_graph/wiki/mesh/`)
- `__init__.py` — package exports
- `schema.py` (~290 lines) — DDL for:
  - 11 core tables: workspaces, source_pages, claims, edges (split weight columns for S4), entities (confidence + user_confirmed for D2), claim_entities, topics, topic_claims, questions, answers, feedback
  - `mesh_meta` + `op_log`
  - 4 sqlite-vec virtual tables (`vec_claims`, `vec_sources`, `vec_entities`, `vec_questions`) at float[768]
  - 4 `vec_*_mapping` tables (string_id ↔ int rowid — advisor fix #3, DDL lives in schema not in store)
  - CHECK constraints on: edges.usage_boost ∈ [0, 0.2], entities.confidence ∈ [0, 1], enum tiers + edge kinds + source kinds
- `store.py` (~770 lines) — `MeshStore` CRUD with:
  - Transaction context that wraps SQL + vec0 atomically (FIX D1)
  - Over-fetch KNN search (k × 3, post-filter, LIMIT k) — advisor fix #1 for lossy filter defense
  - `get_quarantined_entities()` + `confirm_entity()` (FIX D2)
  - `bump_edge_usage_boost()` clamped at 0.2 via `MIN(cap, usage_boost + delta)` (FIX S4)
  - `increment_claim_usage()` + `increment_source_citation()` (FIX D3 snowball counters; re-rank decay applied in retrieve/lethal.py later)
  - Fail-loudly validation on all inputs (tier enum, kind enum, sig_authority range, char span validity, embedding dim = 768)

### Tests (`tests/unit/test_mesh_store.py`)
**39 tests, all passing.** Covers:
- Lifecycle: fresh open, reopen, version mismatch rejection, **vector persistence across close/reopen** (the load-bearing FIX D1 test — if sqlite-vec doesn't persist vectors to disk, single-store architecture is broken)
- Workspace CRUD + stats
- Source insert + hash dedup + FK cascade
- Claim insert with embedding + snowball increment + flagging
- Edge CRUD + S4 split weights + usage_boost cap (both via helper AND via direct INSERT to prove CHECK constraint enforces)
- Entity CRUD + D2 confidence quarantine + confirm + idempotent insert
- Link_claim_entity idempotent with times_referenced bump
- Vector search: closest-first ranking, tier filter, flagged exclusion, **5-claim pathological case proving over-fetch defends against lossy KNN** (advisor fix #1 validation)
- Transaction rollback: SQL + vec0 both roll back atomically (FIX D1 validation)
- Workspace delete cascade

### Empirical findings from sqlite-vec 0.1.6 on Windows
- ✓ JOIN + WHERE filters are SYNTACTICALLY valid (advisor's concern #1 was partially wrong) — but **semantically lossy** when k < filter-set size (advisor's core concern was right)
- ✓ vec0 virtual tables DO respect transactional rollback (advisor's concern #2 — verified good; FIX D1 is real)
- ✓ Mapping tables MUST be in schema.py DDL, not created on-the-fly in `_insert_vector()` (advisor's concern #3 — followed)

---

## What Unit 1 does NOT do

The mesh database can be opened, written to, and queried. But there is NO:
- File upload pipeline (Unit 2)
- LLM claim extraction (Unit 2)
- Entity canonicalization logic (Unit 3 — the CRUD plumbing is in Unit 1, the 5-step logic is Unit 3)
- Edge discovery (Unit 4)
- Retrieval (Unit 5)
- Compose + artifacts (Unit 6)
- Q&A layer (Unit 7)
- CLI (Unit 8)
- API server (Unit 9)

Those are 9 more units. Estimated ~44 working days total. See `docs/wiki_mesh_design.md` §15 for build order and `docs/todo_list.md` for the unit-by-unit plan.

---

## NEXT SESSION — Start Unit 2

Unit 2 is ingest + claim extraction:

1. **`mesh/ingest.py` (~250 lines)**
   - `ingest_upload(workspace_id, file_path)` — content hash, dedup check, docling/trafilatura extraction, `insert_source(kind='upload', sig_authority=0.95)`
   - `ingest_web_result(workspace_id, url, fetched_markdown)` — same shape for web sources, sig_authority from source_quality.py
   - Writes source markdown to `wiki/workspaces/{id}/sources/{src_id}.md`

2. **`mesh/claim_extract.py` (~500 lines — U9 correction)**
   - Port the claim extraction logic from `src/polaris_graph/agents/analyzer.py` (`_analyze_batch` function, line ~1970)
   - Must carry along: Qwen `@model_validator(mode="before")` for field normalization, `_clean_json()` for control chars / code fences, `_repair_truncated_json()` for max_tokens truncation, provider-specific reasoning_content handling
   - Input: one source_page row + content text
   - Output: list of claim dicts ready for `store.insert_claim()` — each with statement, direct_quote, char_span, tier, relevance_score, has_numeric, entity mentions (deferred to Unit 3)
   - Writes via `store.transaction()` — batch insert claims + vec embeddings atomically

3. **Tests** (`tests/unit/test_mesh_ingest.py`)
   - `test_ingest_upload_creates_source` — upload a test markdown → source row created with correct metadata
   - `test_ingest_dedup` — upload same file twice → second call returns existing src_id
   - `test_claim_extract_basic` — mock LLM returns 3 claims → all 3 inserted with vectors
   - `test_claim_extract_preserves_char_span` — direct_quote must appear at [char_start:char_end] in source content
   - `test_claim_extract_has_numeric_detection` — claims with CIs / p-values / % / n= get has_numeric=1
   - `test_claim_extract_transaction_rollback` — if one claim in a batch fails, whole batch rolls back

### Files to read first in next session
1. `docs/wiki_mesh_design.md` §5 (upload → mesh flow) + §13 (component inventory) + §20 (Unit 1 scope)
2. `src/polaris_graph/agents/analyzer.py` — `_analyze_batch` + extraction prompt + JSON repair logic (to port into claim_extract.py)
3. `src/polaris_graph/wiki/mesh/store.py` — the `insert_source` + `insert_claim` + `transaction` interfaces to build against
4. `tests/unit/test_mesh_store.py` — testing style to match

### Advisor checkpoints to run during Unit 2
1. Before writing `claim_extract.py`: show advisor the analyzer.py `_analyze_batch` function and ask what to preserve vs simplify
2. After writing extraction + ingest: show advisor the code + test output
3. Before declaring Unit 2 done: final review

---

## Key invariants to preserve

- **Single database file.** Never introduce a second store for vectors — FIX D1 depends on this.
- **Over-fetch KNN.** Any new vector search path (entities, questions) must use the same `k × 3 → filter → LIMIT k` pattern.
- **Entity quarantine is not optional.** Any code path that inserts an entity with `confidence < 0.8` must NOT make it participate in retrieval expansion until user-confirmed.
- **usage_boost is bounded.** Anything that modifies edge weights must go through `bump_edge_usage_boost()` or respect the CHECK constraint.
- **Fail loudly.** LAW II. No silent fallbacks, no partial inserts, no default-value substitutions.

---

## Files unchanged but worth knowing

- `.env` — `OPENROUTER_DEFAULT_MODEL=z-ai/glm-5`, `PG_WIKI_ENABLED=1`, `PG_WIKI_5LENS=1`, evidence caps at 300/300
- `src/polaris_graph/wiki/wiki_builder.py` + `wiki_composer.py` — the compose-side work from last session (validated, shippable, 79.1 mean G-Eval across 4 domains at gpt-4o shim)
- Validation scripts in `scripts/` — still usable for testing the compose path once OpenRouter credits are restored

---

## Running the Unit 1 tests

```
cd C:/POLARIS
python -m pytest tests/unit/test_mesh_store.py -v
```

Expected: `39 passed` in ~6 seconds, zero warnings.

---

## Long-term backlog (not Unit 2 blockers)

- `vacuum_orphan_vectors()` — `delete_workspace` cascades core tables but leaves dead rows in vec0 tables; add a vacuum pass that runs after destructive ops
- Schema migration tool — when SCHEMA_VERSION bumps, need `mesh/migrate.py` with numbered scripts
- Multi-user auth — `workspaces.owner` column exists but no auth layer (v2)
- 1024-dim / 4096-dim embedding support — vec0 tables are pinned at float[768]; switching models requires DDL migration + re-embed pass
