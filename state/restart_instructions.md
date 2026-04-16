# Restart Instructions

## Current State (2026-04-15) — PG_LOOPBACK_MIN AUDIT + 3 DEFECT FIXES

**Branch:** `PL`

**Uncommitted changes (from this session + prior uncommitted W3.9 work):**
- `src/polaris_graph/wiki/wiki_builder.py` — **D3 FIX (production-critical)**: `build_wiki()` now canonicalizes `claim.source_url` via `_canonicalize_url` before the `url_to_ref` lookup at line ~451. Without this, every claim whose URL had trailing-slash or www. variation vs the canonical bibliography URL got `ref_num=0` and was silently dropped by wiki_composer → zero-citation reports. Also fixed fragile `url_to_evidence_ids.get(url, ...)` → `.get(canonical, ...)` at line ~800.
- `src/polaris_graph/wiki/wiki_composer.py` — Defense-in-depth: `_format_claims_for_prompt` now logs a WARNING when dropping ref_num=0 or empty-statement claims (was silent).
- `src/polaris_graph/llm/loopback_client.py` — **D1 FIX**: added `reason()` method matching OpenRouterClient signature; **D2 FIX**: catches `PermissionError`/`OSError` on response-file read (Windows file-lock race) and retries rename-to-done 5x with 0.2s backoff.
- Plus prior uncommitted work: Tier 3.5 env fixes, load_dotenv override=False in src/__init__.py and src/agents/search_agent.py, hardcoded timeouts → env-controlled in analyzer/section_writer/synthesizer/wiki_composer/wiki_builder.

**Last committed HEAD: `3b17932`** — PL: S6 (audit field alignment) + E4 empirical confirmation

**Session deliverables:**
- Audit report: 9/9 pipeline nodes fired, W3.1/W3.4/W3.11 gates fired, 3 real defects fixed (D1, D2, D3), 1 retracted (D4 budget mismatch was a cross-session false positive), 2 observability findings unfixed (D5 misleading faithfulness metric, D6 synthesize/wiki llm_call trace gap)
- Smoke test: 3 fixes verified — LoopbackLLMClient has reason/generate/generate_structured/validate_reasoning; _format_claims_for_prompt warns on ref_num=0; D3 simulation maps PMC trailing-slash + www.mdpi URLs correctly to ref_num 1 and 2 (was 0 and 0 pre-fix)

## NEXT SESSION — Verify D3 fix end-to-end

**Primary task:** Re-run the pipeline (loopback OR real) and confirm `quality_metrics.total_citations > 0` and `zero_cite_sections == 0`.

**Recommended sequence:**
1. Check that the 3 audit artifacts haven't been clobbered: `logs/pg_trace_PG_LOOPBACK_MIN.jsonl`, `logs/pg_loopback_minimal_stdout.log`, `outputs/polaris_graph/PG_LOOPBACK_MIN.json`
2. Rerun PG_LOOPBACK_MIN via `python scripts/pg_loopback_minimal.py` — should now produce non-zero citations
3. If loopback pass, run a real production test (a single vector, budget $5, no loopback) to confirm D3 fix works in the committed path
4. Commit the fixes once both passes

**What to watch for:**
- New `[wiki] N claims failed URL→ref_num lookup` warning — should NOT appear; if it does, D3 fix is incomplete
- `[wiki-compose] _format_claims_for_prompt dropped N claims` — should NOT appear; defense-in-depth log
- `quality_gate_result` — should be "passed" or "failed: words=...<2000" but NOT "citations=0<5"

---

## Current State (2026-04-12) — Wiki Mesh ALL 10 UNITS COMPLETE

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
- `67deb31` — Wiki Mesh Unit 8 of 10 — CLI presentation layer
- `6a0fa09` — Wiki Mesh Unit 9 of 10 — REST API server (FastAPI)
- **Unit 10 commit pending** — snapshot.py + integration tests + CLI snapshot commands (10 new tests)

**Status:** ALL 10 of 10 wiki mesh units COMPLETE. 283/283 tests passing.

**What was built:** A persistent, self-growing research expert system with: single-db SQLite+vec storage, PDF/HTML/markdown ingestion, LLM claim extraction, 5-step entity canonicalization with quarantine, cosine edge discovery, 6-stage lethal retrieval with bounded snowball re-rank, cited answer composition with artifact validation, multi-turn Q&A threads, CLI + REST API interfaces, and zstd snapshot backup/restore. All 8 advisor design fixes (D1-D3, S4-S8) implemented. 283 tests across 13 test files.

**GitHub push:** still blocked. Commits are local only. The `aldrinor/polaris` remote is configured but GCM has a credential issue. User will resolve when back from their trip.

---

## What was just done

### Unit 9 — REST API server

**`src/polaris_graph/wiki/mesh/api/server.py` (~260 lines)**
- Standalone FastAPI app with 7 routes mirroring CLI: POST/GET /workspaces, POST /workspaces/{id}/ask (LLM), POST /workspaces/{id}/ask/dry-run (retrieval only), POST /workspaces/{id}/ingest (file upload), GET /workspaces/{id}/stats, GET /workspaces/{id}/entities/quarantined
- Lifespan manages store lifecycle with `check_same_thread=False` (required for ASGI thread pool)
- Pydantic response models enforce output shape (WorkspaceResponse, AskResponse, DryRunResponse, StatsResponse)
- File upload: UploadFile → temp file → ingest_file → cleanup in finally block
- CORS allow_origins=["*"] for local dev. No auth for v1.
- `_make_llm_client` fails loudly → HTTP 503

**`store.py` addition**
- `MeshStore.open` extended with `check_same_thread: bool = True` parameter (backward-compatible)

**`tests/unit/test_mesh_api.py` — 12 tests**
- TestCreateWorkspace (2), TestListWorkspaces (2), TestDryRun (3 inc. empty + invalid), TestStats (2), TestQuarantinedEntities (3 inc. shows quarantined)

**Bugs caught:** (1) check_same_thread — SQLite cross-thread error with FastAPI TestClient. (2) sqlite3.Row.get() — Row doesn't support .get(), fixed to direct access.

---

## NEXT SESSION — Start Unit 10: Integration tests + snapshots

Unit 10 closes the 10-unit series with end-to-end integration tests and optional snapshot/restore.

### What Unit 10 delivers

- `tests/integration/test_mesh_e2e.py` — full pipeline integration tests: ingest file → extract claims → canonicalize entities → discover edges → retrieve → compose → Q&A thread
- `mesh/snapshot.py` — zstd-compressed db backup/restore (if zstandard available)
- Snapshot CLI/API commands wired

### Files to read first in next session

1. All mesh source files in `src/polaris_graph/wiki/mesh/` — verify the full vertical slice works
2. `requirements.txt` — check if zstandard is available
3. `tests/unit/test_mesh_*.py` — understand existing test patterns to avoid duplication

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
python -m pytest tests/unit/test_mesh_store.py tests/unit/test_mesh_ingest.py tests/unit/test_mesh_claim_extract.py tests/unit/test_mesh_entity.py tests/unit/test_mesh_edge_discovery.py tests/unit/test_mesh_snowball.py tests/unit/test_mesh_lethal_retrieve.py tests/unit/test_mesh_compose.py tests/unit/test_mesh_qa.py tests/unit/test_mesh_cli.py tests/unit/test_mesh_api.py tests/unit/test_mesh_snapshot.py tests/integration/test_mesh_e2e.py -v
```

Expected: **283 passed** in ~119s (the embedding model loads once for the integration tests).

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
