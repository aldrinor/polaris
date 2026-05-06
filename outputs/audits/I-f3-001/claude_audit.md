# Claude Architect Audit — I-f3-001

**Branch:** bot/I-f3-001 / **Diff SHA256:** `140b8e9e8572f2156d171a04bdf5e61893bfc24da0110d46613dd5f7b360d96c`
**LOC:** 166 net (under CHARTER §1 200-cap by 34)
**Tests:** 7/7 PASS via `PYTHONPATH=src python -m pytest tests/polaris_graph/test_graph_v4_documents.py -v`.

## Files

```
src/polaris_graph/graph_v4.py                          EDIT  +50
tests/polaris_graph/test_graph_v4_documents.py         NEW   +116
```

## Iter-3 brief P2 advisories — addressed in implementation

- **P2 #1 (Test 7 patch target ambiguous):** `monkeypatch.setattr("src.polaris_graph.document_ingester.DocumentIngester", lambda: StubIngester(docs))` — patches the class at its source module so the lazy import inside `_load_uploaded_documents` resolves to the stub. Verified via 7/7 PASS.
- **P2 #2 (`chunk_index` is ordinal not byte offset):** Implementation uses `enumerate(chunks)` → `idx` is 0, 1, 2 ordinal. Test asserts `[c["chunk_index"] for c in out] == [0, 1, 2]` for a 4500-char doc with chunk_size=1500.
- **P2 #3 (`None` vs `list[str]` signature mismatch):** Helper accepts `list[str]` per signature; the `if not document_ids: return []` truthy-check inside graph_v4 handles `None` BEFORE calling the helper. Test name `test_empty_or_none_returns_empty` retained as accurate (covers `[]` directly; `None` is filtered out by the calling site).

## Architecture review

1. **Path-traversal mitigation (Codex iter-2 P1 #2 fix).** `_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")` rejects `"../etc/passwd"`, `"abc"`, `"X"*16` (non-hex), `"g"*16` (out-of-range hex). `re.fullmatch` requires the entire string match. Test asserts the path-traversal id is skipped + warning logged.

2. **Filename fallback chain.** `meta.get("original_filename") or meta.get("filename") or doc_id`. Test exercises all three rungs.

3. **Empty-content skip.** Documents with `content == ""` (e.g. ingestion produced metadata.json but no extracted.txt) are skipped to avoid emitting empty chunks. Logged warning.

4. **Fail-loud on all-failed.** RuntimeError raised when every requested id fails. Per LAW II — user receives error instead of silently empty pool.

5. **Lazy DocumentIngester import.** `from src.polaris_graph.document_ingester import DocumentIngester` happens inside `_load_uploaded_documents` only — keeps graph_v4 import cheap (mirrors existing lazy-import pattern at graph_v4.py:163 `from scripts.run_honest_sweep_r3 import run_one_query`).

6. **`_load_uploaded_documents` references `logger`.** `logger = logging.getLogger(__name__)` is defined at module-level (graph_v4.py:89). Python resolves `logger` at function-call time (not import time), so the forward reference is safe.

7. **q-dict threading.** Helper output appended to `q["uploaded_documents"]` ONLY when `document_ids` is truthy (handles None and []). Pipeline-A consumption is the next Issue (I-f3-001b).

## LAW + invariant checks

- **LAW II:** Path-traversal rejected; missing/empty docs skipped with warning; all-failed raises RuntimeError. ✓
- **LAW V:** snake_case file naming; module-level `logger`; constant `_DOC_ID_RE`. ✓
- **LAW VI:** No magic numbers (chunk_size=1500 is a default parameter, overridable). ✓
- **§9.4:** No `unittest.mock`; tests use `StubIngester` regular class + `monkeypatch.setattr`. ✓
- **§8.4:** No real network/ML in tests. ✓
- **CHARTER §1 200-cap:** 166 net. ✓

## Test plan coverage

7 tests:
1. `test_empty_or_none_returns_empty` — empty list.
2. `test_invalid_doc_id_format_skipped_with_warning` — path-traversal + various invalid formats; valid id passes through.
3. `test_loads_chunks_from_documents` — 2 docs with `original_filename` and `filename` metadata; chunk_size=10.
4. `test_missing_document_id_skipped_with_warning` — DocumentIngester returns None for one id.
5. `test_all_invalid_or_missing_raises` — every id fails → RuntimeError.
6. `test_chunk_size_respected` — 4500-char doc, chunk_size=1500, asserts 3 chunks at lengths 1500/1500/1500 with chunk_index 0/1/2.
7. `test_q_dict_threading_with_stubbed_run_one_query` — full async path: monkeypatch DocumentIngester source module + run_one_query; assert captured `q["uploaded_documents"]` shape.

## Out of scope (deferred per scope clarification)

- **Pipeline-A consumption** of `q["uploaded_documents"]` → **I-f3-001b** follow-up Issue.
- **PDF semantic chunking** → **I-f3-001c** follow-up.
- **End-to-end** "upload PDF → strict_verify cites span" integration test → blocked on I-f3-001b + I-f3-001c.

## Verdict

APPROVE for Codex diff review.
