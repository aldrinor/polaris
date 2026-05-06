# Codex Brief Review — I-f3-001 (ITER 3 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-001 — Backend: wire document_ids into graph_v4 evidence pool
**Phase:** 1 / **Feature:** F3 (document upload + grounding)
**LOC budget:** 200 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-history resolution

**Iter 1 → Iter 2 P1s ADDRESSED:** Pivoted from `_UPLOAD_TABLE` to `DocumentIngester.get_document()`; consolidated import path on `from src.polaris_graph.document_ingester import DocumentIngester`.

**Iter 2 → Iter 3 P1s ADDRESSED:**

- **P1 #1 (stale `_UPLOAD_TABLE` references):** This iter-3 brief is rewritten from scratch with NO `_UPLOAD_TABLE` mention anywhere. Single canonical substrate: `DocumentIngester.get_document()`.
- **P1 #2 (path-traversal on `DOCUMENT_STORAGE_DIR / doc_id`):** Helper validates each `doc_id` matches `re.fullmatch(r"[a-f0-9]{16}", doc_id)` BEFORE filesystem lookup. DocumentIngester uses `hashlib.sha256(file_bytes).hexdigest()[:16]` (16 hex chars) per `document_ingester.py:162`. Invalid IDs are rejected with a logged warning + skipped (treated as "missing").

**Iter 2 P2s ADDRESSED:**

- **P2 #1 (stubbed run_one_query test for q-dict threading):** Added Test 6 — patches `scripts.run_honest_sweep_r3.run_one_query` with a stub that captures the `q` dict; asserts `q["uploaded_documents"]` is the list of chunks emitted by `_load_uploaded_documents`.
- **P2 #2 (filename fallback chain):** Helper uses `metadata.get("original_filename") or metadata.get("filename") or doc_id`.
- **P2 #3 (`chunk_index` not `chunk_idx`):** Field renamed to `chunk_index` to match existing `UploadedChunk.chunk_index` substrate naming.

## Mission

Wire the existing `document_ids: Optional[list[str]]` parameter at `src/polaris_graph/graph_v4.py:149` into the pipeline-A `q` dict so uploaded document chunks become part of the evidence pool. Per breakdown's "v6.2 §F3 CRITICAL GAP."

## Substrate (HONEST)

- `src/polaris_graph/graph_v4.py:139-265` — `build_and_run_v4(...)` already accepts `document_ids: Optional[list[str]] = None`. Currently unused.
- `src/polaris_graph/document_ingester.py:1084-1115` — `DocumentIngester.get_document(doc_id) -> Optional[dict]`. Returns `{content, html, metadata, pages, doc_id}` from filesystem at `DOCUMENT_STORAGE_DIR / doc_id`. `content` is the parsed text (PDF/MD/TXT/etc).
- `src/polaris_graph/document_ingester.py:162` — `doc_id = hashlib.sha256(file_bytes).hexdigest()[:16]` — 16-hex-char format. Validation regex: `r"[a-f0-9]{16}"`.
- `scripts/live_server.py:3446-3491` — `/api/documents/upload` calls `_document_ingester.ingest(tmp_path)` and writes to filesystem.
- `scripts/live_server.py:1838` — `build_and_run_v4(...)` invoked with `document_ids=req.document_ids` from `/api/research`. Same-process; filesystem-backed.

## Scope clarification

This Issue scopes to the **v4-layer wiring** (`document_ids` → `q["uploaded_documents"]`). Pipeline-A consumption of `q["uploaded_documents"]` (i.e. merging into the evidence pool used by `strict_verify`) is the deeper integration deferred to:
- **I-f3-001b — Backend: pipeline-A consumes uploaded_documents.** Reads `q["uploaded_documents"]` in `scripts/run_honest_sweep_r3.py`'s evidence-pool builder; emits document chunks as evidence items the strict_verify gate cites.

PDF chunking deferred to:
- **I-f3-001c — Backend: PDF chunk pre-segmentation.** Currently `DocumentIngester` returns one long `content` string; production may need finer chunking (semantic boundaries, page-aware) — that's a separate concern.

## Acceptance criteria (binding)

1. **`src/polaris_graph/graph_v4.py`** (EDIT): add helper `_load_uploaded_documents(document_ids: list[str], ingester=None, chunk_size: int = 1500) -> list[dict]`.
   - Lazy-imports `from src.polaris_graph.document_ingester import DocumentIngester`; `ingester = ingester or DocumentIngester()`.
   - Module-level constant `_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")`.
   - For each `doc_id` in `document_ids`:
     - If `not _DOC_ID_RE.fullmatch(doc_id)` → log warning ("invalid doc_id format"), skip.
     - `doc = ingester.get_document(doc_id)`. If `None` → log warning, skip.
     - Extract `content = doc.get("content", "")`. If empty → log warning, skip.
     - Filename: `name = doc.get("metadata", {}).get("original_filename") or doc.get("metadata", {}).get("filename") or doc_id`.
     - Chunk `content` via fixed `chunk_size` window: `[content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]`.
     - For each chunk, emit `{"document_id": doc_id, "filename": name, "chunk_index": i, "text": chunk_text}`.
   - Return aggregated list.
   - If `document_ids` non-empty AND aggregated list is empty → raise RuntimeError (LAW II — every requested id failed; user must see this).
   - LOC: ~40.

2. **`src/polaris_graph/graph_v4.py`** (EDIT): in `build_and_run_v4`, after the `q` dict synthesis at line 192:
   ```python
   if document_ids:  # truthy: handles None and []
       q["uploaded_documents"] = _load_uploaded_documents(document_ids)
   ```
   LOC: +2.

3. **`tests/polaris_graph/test_graph_v4_documents.py`** (NEW): 6 unit tests using a `StubIngester` regular class (no `unittest.mock` per CLAUDE.md §9.4).
   - `test_empty_or_none_returns_empty`: `_load_uploaded_documents([])` returns `[]`.
   - `test_invalid_doc_id_format_skipped_with_warning`: id `"../etc/passwd"` (path-traversal) → skipped + warning logged. id `"abc"` (too short) → skipped. The single valid id's chunks DO appear.
   - `test_loads_chunks_from_documents`: 2 valid 16-hex docs with content "abcde..." → returns chunks with `document_id`/`filename`/`chunk_index`/`text`. Filename uses `original_filename` from metadata.
   - `test_missing_document_id_skipped_with_warning`: 1 doc resolves, 1 returns None → only existing doc's chunks; warning logged.
   - `test_all_invalid_or_missing_raises`: every id either invalid format OR returns None → RuntimeError.
   - `test_chunk_size_respected`: doc content of length 4500 with `chunk_size=1500` → 3 chunks with lengths 1500/1500/1500.
   - LOC: ~110.

4. **`tests/polaris_graph/test_graph_v4_documents.py`** continued: ALSO add a 7th test `test_q_dict_threading_with_stubbed_run_one_query` (Codex iter-2 P2 #1):
   - Patches `scripts.run_honest_sweep_r3.run_one_query` with a stub that captures the `q` dict argument and returns a minimal valid summary.
   - Patches `DocumentIngester` instantiation in graph_v4 with a stub returning 2 docs of 1500 chars each.
   - Calls `await build_and_run_v4(vector_id="t", query="Q", document_ids=["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])`.
   - Asserts `captured_q["uploaded_documents"]` has 2 entries with the expected `chunk_index=0` per doc.
   - LOC: ~30.

## Planned diff shape

```
src/polaris_graph/graph_v4.py                          EDIT  +42
tests/polaris_graph/test_graph_v4_documents.py         NEW   +140
```

LOC: +182 net pre-Prettier. Under CHARTER §1 200-cap by 18.

## Out of scope

- Pipeline-A consumption → I-f3-001b.
- PDF semantic chunking → I-f3-001c.
- End-to-end `upload PDF → strict_verify cites span` integration test → blocked by I-f3-001b.

## Risks for Codex Red-Team

1. **Path-traversal mitigation.** `_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")` rejects everything except 16-hex strings. `re.fullmatch` ensures no partial match (e.g. "abc/../etc" → None). Test `test_invalid_doc_id_format_skipped_with_warning` covers `"../etc/passwd"`, `"abc"`, mixed-case, non-hex.

2. **Filename fallback chain.** `original_filename or filename or doc_id`. Test asserts each rung: doc with `original_filename` set → uses that. Doc with only `filename` → uses that. Doc with neither → uses doc_id (defensive).

3. **`chunk_index` field name.** Aligned with `UploadedChunk.chunk_index` per Codex iter-2 P2 #3.

4. **Empty-content skip.** Documents whose `content` is empty (e.g., DocumentIngester ingestion failed but metadata.json exists) are skipped to avoid emitting empty chunks. Test `test_loads_chunks_from_documents` uses non-empty content; the empty-content branch is documented but not separately tested (implicit via the all-invalid-or-missing test which covers similar fail-loud).

5. **`asyncio` semantics.** `_load_uploaded_documents` is sync; called from async `build_and_run_v4`. No `await` needed since `DocumentIngester.get_document` is sync (filesystem read).

6. **Stubbed run_one_query test (test #7).** Uses `monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", stub)`. The stub is an `async def` returning a minimal summary dict. Test asserts the captured `q["uploaded_documents"]` shape.

7. **CHARTER §1 LOC cap.** 182 net. Under 200 by 18. Prettier reflow margin sufficient.

8. **No new package.json / requirements.txt dep.**

9. **Test isolation via `monkeypatch`.** No global state mutation; cleanup automatic.

10. **Fail-loud on all-invalid-or-missing.** Per LAW II. Test covers explicitly. User receives RuntimeError instead of silently empty pool.

11. **`document_ids` truthy check (`if document_ids:`).** Handles both `None` and `[]` correctly; only when at least 1 id is present do we invoke the loader.

12. **Live `tests/polaris_graph/test_graph_v4*` patterns.** The test file path matches existing test directory conventions.

13. **`from src.polaris_graph.document_ingester` import.** Matches `live_server.py:108` and `graph_v4.py:172` (`PipelineTracer`). Stable across same-process invocations.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
