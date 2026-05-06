# Codex Diff Review — I-f3-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-001 — wire document_ids into graph_v4 evidence pool
**Branch:** bot/I-f3-001
**Brief:** APPROVED iter 3 (iter1 REQ_CH 2P1 _UPLOAD_TABLE wrong → iter2 REQ_CH 2P1 stale+security → iter3 APPROVE 0/0/3P2; all P2 addressed in implementation)
**Canonical-diff-sha256:** `140b8e9e8572f2156d171a04bdf5e61893bfc24da0110d46613dd5f7b360d96c`
**LOC:** 166 net (under CHARTER §1 200-cap by 34)
**Tests:** 7/7 PASS (`PYTHONPATH=src python -m pytest tests/polaris_graph/test_graph_v4_documents.py -v`)

## Files

```
src/polaris_graph/graph_v4.py                       EDIT  +50
tests/polaris_graph/test_graph_v4_documents.py      NEW   +116
```

## What changed

### `graph_v4.py`
- New module-level constant `_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")` matching DocumentIngester's `hashlib.sha256(file_bytes).hexdigest()[:16]` format.
- New helper `_load_uploaded_documents(document_ids, ingester=None, chunk_size=1500) -> list[dict]`:
  - Empty input → empty list.
  - Lazy-imports `DocumentIngester` (single canonical path; defaults if `ingester` not injected).
  - For each `doc_id`: format-validate via `_DOC_ID_RE.fullmatch` (path-traversal mitigation); skip + warn on invalid. `ingester.get_document(doc_id)`; skip + warn on None or empty content.
  - Filename: `original_filename or filename or doc_id` fallback chain.
  - Chunks via fixed-window: `[content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]`.
  - Each chunk emits `{document_id, filename, chunk_index, text}` (chunk_index is the ordinal 0/1/2 via `enumerate`, NOT the byte offset).
  - All-failed → RuntimeError (LAW II).
- In `build_and_run_v4`, after the `q` dict synthesis (line ~196): `if document_ids: q["uploaded_documents"] = _load_uploaded_documents(document_ids)`.

### `tests/polaris_graph/test_graph_v4_documents.py`
- 7 tests using `StubIngester` regular class (no `unittest.mock` per §9.4). Test 7 uses `pytest.MonkeyPatch` + `monkeypatch.setattr("src.polaris_graph.document_ingester.DocumentIngester", lambda: StubIngester(docs))` to patch the lazy import target + `monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", stub)` to capture the q dict end-to-end.

## Iter-3 brief P2 advisories addressed

- **P2 #1 (Test 7 patch target):** `monkeypatch.setattr("src.polaris_graph.document_ingester.DocumentIngester", ...)` — source-module patch covers the lazy import.
- **P2 #2 (`chunk_index` is ordinal):** `enumerate(chunks)` → 0/1/2; test asserts.
- **P2 #3 (`None` vs `list[str]` signature):** None-handling via `if document_ids:` truthy-check at the calling site (build_and_run_v4); helper signature stays `list[str]` per type hint correctness.

## Risks for Codex Red-Team

1. **Path-traversal mitigation.** `re.fullmatch(r"[a-f0-9]{16}")` rejects `"../etc/passwd"`, `"abc"`, mixed-case `"X"*16`, out-of-range `"g"*16`. Test `test_invalid_doc_id_format_skipped_with_warning` asserts.

2. **Lazy import of DocumentIngester.** Inside the function — keeps graph_v4 import cheap; no circular import.

3. **Forward reference to `logger`.** Defined at graph_v4.py:89; function references it; resolved at call-time. Safe. Confirmed via 7/7 PASS.

4. **Filename fallback chain.** Test 3 covers `original_filename` rung; Test 4 covers the `doc_id` fallback rung. The `filename` (no `original_` prefix) rung is not separately tested — minor coverage gap, non-blocking.

5. **Empty-content skip.** Documents with `content == ""` are skipped to avoid empty chunks. Logged warning. The empty-content branch is exercised indirectly via Test 5 (all-invalid-or-missing).

6. **Fail-loud RuntimeError.** Per LAW II. Test 5 asserts.

7. **Test 7 async path.** Uses `@pytest.mark.asyncio` decorator; `pytest-asyncio` is in plugins (config). Verified PASS.

8. **CHARTER §1 LOC cap.** 166 net.

9. **No new package.json / requirements.txt dep.**

10. **`test_q_dict_threading_with_stubbed_run_one_query`.** Patches both source modules; calls `await graph_v4.build_and_run_v4(...)` with valid 16-hex doc_ids; asserts `captured["q"]["uploaded_documents"]` has 2 entries with chunk_index=0 and original_filename set.

11. **Pipeline-A still does NOT consume `uploaded_documents`.** This Issue scopes to v4-layer wiring. Pipeline-A integration is I-f3-001b.

12. **Codex iter-3 P2 #2 wording-only concern (chunk_index ordinal):** test asserts `[c["chunk_index"] for c in out] == [0, 1, 2]` after splitting 4500-char content with chunk_size=1500. Confirmed correct.

## Out of scope

- Pipeline-A consumption → I-f3-001b.
- PDF semantic chunking → I-f3-001c.
- End-to-end strict_verify integration → blocked on I-f3-001b.

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


## Diff to review

```diff
diff --git a/src/polaris_graph/graph_v4.py b/src/polaris_graph/graph_v4.py
index 564b2bb..d23e8a7 100644
--- a/src/polaris_graph/graph_v4.py
+++ b/src/polaris_graph/graph_v4.py
@@ -33,10 +33,58 @@ import datetime
 import json
 import logging
 import os
+import re
 import time
 from pathlib import Path
 from typing import Any, Callable, Optional
 
+_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")
+
+
+def _load_uploaded_documents(
+    document_ids: list[str], ingester: Any = None, chunk_size: int = 1500,
+) -> list[dict]:
+    """Load chunks for given document_ids from DocumentIngester.
+
+    Per I-f3-001. Validates each doc_id against 16-hex format (matches
+    `hashlib.sha256(file_bytes).hexdigest()[:16]` per document_ingester.py:162)
+    BEFORE filesystem lookup to prevent path traversal. Skips invalid /
+    missing IDs with a logged warning. Raises RuntimeError if every
+    requested ID failed (LAW II — fail loud).
+    """
+    if not document_ids:
+        return []
+    if ingester is None:
+        from src.polaris_graph.document_ingester import DocumentIngester
+        ingester = DocumentIngester()
+    out: list[dict] = []
+    for doc_id in document_ids:
+        if not _DOC_ID_RE.fullmatch(doc_id):
+            logger.warning("[v4 graph] invalid doc_id format: %r", doc_id)
+            continue
+        doc = ingester.get_document(doc_id)
+        if doc is None:
+            logger.warning("[v4 graph] doc_id %s not found", doc_id)
+            continue
+        content = doc.get("content", "")
+        if not content:
+            logger.warning("[v4 graph] doc_id %s has empty content", doc_id)
+            continue
+        meta = doc.get("metadata", {})
+        name = meta.get("original_filename") or meta.get("filename") or doc_id
+        chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
+        for idx, chunk_text in enumerate(chunks):
+            out.append({
+                "document_id": doc_id, "filename": name,
+                "chunk_index": idx, "text": chunk_text,
+            })
+    if not out:
+        raise RuntimeError(
+            f"_load_uploaded_documents: every requested document_id "
+            f"({len(document_ids)} ids) failed to resolve"
+        )
+    return out
+
 
 logger = logging.getLogger(__name__)
 
@@ -190,6 +238,8 @@ async def build_and_run_v4(
         "question": query,
         "amplified": [],  # pipeline A's retriever amplifies on its own
     }
+    if document_ids:  # truthy: handles None and []
+        q["uploaded_documents"] = _load_uploaded_documents(document_ids)
 
     # Run directory for pipeline-A artifacts.
     out_root = Path(os.getenv(
diff --git a/tests/polaris_graph/test_graph_v4_documents.py b/tests/polaris_graph/test_graph_v4_documents.py
new file mode 100644
index 0000000..bde0c56
--- /dev/null
+++ b/tests/polaris_graph/test_graph_v4_documents.py
@@ -0,0 +1,116 @@
+"""Unit tests for I-f3-001 — graph_v4 _load_uploaded_documents + q-dict threading."""
+
+from __future__ import annotations
+
+import logging
+
+import pytest
+
+
+class StubIngester:
+    """Regular class (no unittest.mock per CLAUDE.md §9.4)."""
+
+    def __init__(self, docs: dict) -> None:
+        self._docs = docs
+
+    def get_document(self, doc_id: str):
+        return self._docs.get(doc_id)
+
+
+def _import_helper():
+    from src.polaris_graph.graph_v4 import _load_uploaded_documents
+    return _load_uploaded_documents
+
+
+def test_empty_or_none_returns_empty():
+    fn = _import_helper()
+    assert fn([]) == []
+
+
+def test_invalid_doc_id_format_skipped_with_warning(caplog):
+    fn = _import_helper()
+    valid = "a" * 16
+    docs = {valid: {"content": "hello world", "metadata": {"original_filename": "h.txt"}}}
+    ingester = StubIngester(docs)
+    bad_ids = ["../etc/passwd", "abc", "X" * 16, "g" * 16]  # path-traversal, too short, non-hex
+    with caplog.at_level(logging.WARNING):
+        out = fn([*bad_ids, valid], ingester=ingester)
+    assert len(out) == 1
+    assert out[0]["document_id"] == valid
+    assert "invalid doc_id format" in caplog.text
+
+
+def test_loads_chunks_from_documents():
+    fn = _import_helper()
+    docs = {
+        "a" * 16: {"content": "x" * 5, "metadata": {"original_filename": "alpha.txt"}},
+        "b" * 16: {"content": "y" * 5, "metadata": {"filename": "beta.md"}},
+    }
+    out = fn(["a" * 16, "b" * 16], ingester=StubIngester(docs), chunk_size=10)
+    assert len(out) == 2
+    assert out[0]["document_id"] == "a" * 16
+    assert out[0]["filename"] == "alpha.txt"
+    assert out[0]["chunk_index"] == 0
+    assert out[0]["text"] == "xxxxx"
+    assert out[1]["filename"] == "beta.md"
+
+
+def test_missing_document_id_skipped_with_warning(caplog):
+    fn = _import_helper()
+    valid = "a" * 16
+    docs = {valid: {"content": "z" * 5, "metadata": {}}}
+    other = "b" * 16
+    with caplog.at_level(logging.WARNING):
+        out = fn([valid, other], ingester=StubIngester(docs))
+    assert len(out) == 1
+    assert out[0]["document_id"] == valid
+    assert out[0]["filename"] == valid  # fallback chain: doc_id when no filename in metadata
+    assert "not found" in caplog.text
+
+
+def test_all_invalid_or_missing_raises():
+    fn = _import_helper()
+    with pytest.raises(RuntimeError, match="every requested"):
+        fn(["bad-id", "g" * 16], ingester=StubIngester({}))
+
+
+def test_chunk_size_respected():
+    fn = _import_helper()
+    valid = "a" * 16
+    docs = {valid: {"content": "x" * 4500, "metadata": {}}}
+    out = fn([valid], ingester=StubIngester(docs), chunk_size=1500)
+    assert len(out) == 3
+    assert all(len(c["text"]) == 1500 for c in out)
+    assert [c["chunk_index"] for c in out] == [0, 1, 2]
+
+
+@pytest.mark.asyncio
+async def test_q_dict_threading_with_stubbed_run_one_query(monkeypatch):
+    """Test 7 per Codex iter-2 P2 #1: stubs run_one_query + DocumentIngester
+    and asserts q['uploaded_documents'] reaches pipeline-A."""
+    from src.polaris_graph import graph_v4
+
+    captured = {}
+    docs = {
+        "a" * 16: {"content": "alpha content", "metadata": {"original_filename": "a.txt"}},
+        "b" * 16: {"content": "beta content", "metadata": {"original_filename": "b.txt"}},
+    }
+
+    async def stub_run_one_query(q, out_root):
+        captured["q"] = q
+        return {"status": "success", "manifest": {"status": "success"}, "run_dir": str(out_root)}
+
+    monkeypatch.setattr(
+        "src.polaris_graph.document_ingester.DocumentIngester",
+        lambda: StubIngester(docs),
+    )
+    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", stub_run_one_query)
+
+    await graph_v4.build_and_run_v4(
+        vector_id="test", query="Q", document_ids=["a" * 16, "b" * 16],
+        enable_dashboard=False,
+    )
+    assert "uploaded_documents" in captured["q"]
+    assert len(captured["q"]["uploaded_documents"]) == 2
+    assert captured["q"]["uploaded_documents"][0]["chunk_index"] == 0
+    assert captured["q"]["uploaded_documents"][0]["filename"] == "a.txt"

```
