# Codex DIFF review — I-ready-011 (#1077): PG_DOC_INGEST_BACKEND — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Return the YAML verdict block ONLY. Claude authored the diff (commits a2c17ada + the P2 fixup on bot/I-ready-011-doc-ingest-backend).**

---

## 0. Your iter-1 verdict: APPROVE (0 P0/P1, default_backend_correct=yes, 2 P2). Both folded in.

- **P2-1 (blank local extraction → deferred /runs 400):** the `local` branch now FAILS LOUD at upload (HTTP 422) when `_extract_text_local` returns blank/whitespace (DocumentIngester can return "" without raising — scanned/figure-only PDF), with an actionable "enable the VLM-OCR backend" message — consistent with the parse-error 422 branch.
- **P2-2 (unknown backend silently → legacy):** an unrecognised `PG_DOC_INGEST_BACKEND` value now FAILS LOUD (HTTP 400) via `_KNOWN_BACKENDS` validation at the top of the dispatch, instead of silently behaving as legacy. LAW II — no silent config degradation. (legacy/unset is still in `_KNOWN_BACKENDS` → byte-identical.)

These two guards are the only change since iter-1.

## 1. Verify this iter

- Both new fail-loud guards are correct; `legacy`/unset is still byte-identical (legacy ∈ _KNOWN_BACKENDS; a blank guard only fires under the `local` branch); no new regression to the iter-1-APPROVE'd behavior.
- No NEW P0/P1.

## 2. Verification done (offline, no spend, no OCR model)

11 behavioral tests pass (added unknown-backend→400 + blank-local→422) + 8 adversarial upload regression green.

## 3. Output schema (return EXACTLY this; loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

## 4. The full committed diff (`git diff bot/I-ready-013-analyst-synthesis-verified..HEAD`)

```diff
diff --git a/src/polaris_v6/api/upload.py b/src/polaris_v6/api/upload.py
index 4901acf3..91825a43 100644
--- a/src/polaris_v6/api/upload.py
+++ b/src/polaris_v6/api/upload.py
@@ -21,6 +21,7 @@ from __future__ import annotations
 
 import hashlib
 import html as _html
+import os
 import uuid
 from typing import Literal
 
@@ -47,6 +48,51 @@ MAX_BYTES = 50 * 1024 * 1024  # 50 MB per upload (I-f3-005 frontend dropzone)
 CHUNK_SIZE = 280
 MAX_GROUNDING_CHUNKS = 40
 
+# I-ready-011 (#1077): document-ingest backend selector (LAW VI). `legacy` (DEFAULT) keeps the
+# .md/.txt-only behavior byte-identical (PDF/DOCX still fail loud downstream). `local` routes
+# PDF/DOCX through the EXISTING DocumentIngester (PyMuPDF text + Tesseract OCR fallback,
+# python-docx) — deps already in requirements.txt. The VLM-OCR backends (figure/chart/table
+# understanding via docling/surya/deepseek-ocr-2) are OPERATOR-GATED heavy open-weight deps and
+# fail LOUD here until installed + signed off (never loaded in the autonomous loop, §8.4).
+_VLM_BACKENDS = frozenset({"vlm", "docling", "surya", "deepseek-ocr", "deepseek-ocr-2", "marker"})
+_LOCAL_PARSE_EXTENSIONS = frozenset({".pdf", ".docx"})
+# All recognised backend values. An unrecognised value (operator typo) FAILS LOUD rather than
+# silently falling back to legacy (Codex diff-gate P2 — no silent config degradation, LAW II).
+_KNOWN_BACKENDS = frozenset({"legacy", "local"}) | _VLM_BACKENDS
+
+
+def _doc_ingest_backend() -> str:
+    return os.environ.get("PG_DOC_INGEST_BACKEND", "legacy").strip().lower()
+
+
+async def _extract_text_local(content: bytes, ext: str) -> str:
+    """Extract text from PDF/DOCX bytes via the EXISTING DocumentIngester (PyMuPDF/python-docx +
+    Tesseract OCR fallback). I-ready-011 (#1077).
+
+    DocumentIngester.ingest takes a file PATH, so the bytes are written to a temp file with the
+    real extension (the ingester dispatches on suffix). The import is LAZY so a `legacy` upload
+    never pulls fitz/document_ingester. A born-digital text PDF uses PyMuPDF text extraction with
+    NO OCR model (Tesseract fires only when extracted text < threshold).
+    """
+    import tempfile
+    from pathlib import Path
+
+    from polaris_graph.document_ingester import DocumentIngester
+
+    tmp_path: "Path | None" = None
+    try:
+        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
+            tmp.write(content)
+            tmp_path = Path(tmp.name)
+        result = await DocumentIngester().ingest(tmp_path)
+        return str(result.get("content") or "")
+    finally:
+        if tmp_path is not None:
+            try:
+                tmp_path.unlink()
+            except OSError:
+                pass
+
 
 class UploadResponse(BaseModel):
     document_id: str
@@ -118,18 +164,70 @@ async def upload_document(
     sha = hashlib.sha256(content).hexdigest()
     document_id = uuid.uuid4().hex
 
+    backend = _doc_ingest_backend()
+    if backend not in _KNOWN_BACKENDS:
+        # Codex diff-gate P2: a typo'd backend must FAIL LOUD, not silently behave as legacy
+        # (which would unparse a PDF the operator believes they enabled). LAW II — no silent
+        # config degradation.
+        raise HTTPException(
+            status_code=400,
+            detail=(
+                f"unknown PG_DOC_INGEST_BACKEND={backend!r}; valid values: "
+                f"{sorted(_KNOWN_BACKENDS)}."
+            ),
+        )
     if ext in {".md", ".txt"}:
+        # Text formats: decode directly on EVERY backend (no parser/model needed) — unchanged.
         try:
             text = content.decode("utf-8", errors="replace")
         except Exception:
             text = ""
-        chunks = [text[i : i + 280] for i in range(0, min(len(text), 840), 280) if text]
-        preview_text = text
-        preview_html = f"<pre>{_html.escape(text)}</pre>" if text else ""
+    elif backend in _VLM_BACKENDS:
+        # I-ready-011 (#1077): VLM-OCR (figure/chart/table understanding) is operator-gated — heavy
+        # open-weight deps (docling/surya/deepseek-ocr-2) not installed + never loaded in the
+        # autonomous loop (§8.4). Fail LOUD so the operator sees exactly what to enable, never a
+        # silent empty parse.
+        raise HTTPException(
+            status_code=501,
+            detail=(
+                f"PG_DOC_INGEST_BACKEND={backend!r} (VLM-OCR) is not enabled: it requires "
+                "operator-installed open-weight OCR deps (docling / surya / deepseek-ocr-2) plus "
+                "sovereignty sign-off. Use PG_DOC_INGEST_BACKEND=local (PyMuPDF/Tesseract) or the "
+                "default 'legacy'."
+            ),
+        )
+    elif backend == "local" and ext in _LOCAL_PARSE_EXTENSIONS:
+        # I-ready-011 (#1077): parse PDF/DOCX via the EXISTING DocumentIngester (PyMuPDF text +
+        # Tesseract OCR fallback for scanned pages; python-docx). The extracted text flows through
+        # the SAME chunk_text + evidence path as a .md/.txt upload — no new verification bypass
+        # (Codex brief-gate confirmed faithfulness-safe). Fail LOUD on a parse error.
+        try:
+            text = await _extract_text_local(content, ext)
+        except Exception as exc:  # noqa: BLE001 — surface the parse failure, never silent-empty
+            raise HTTPException(
+                status_code=422,
+                detail=f"failed to parse {ext} document with the 'local' backend: {exc}",
+            ) from exc
+        if not text.strip():
+            # Codex diff-gate P2: DocumentIngester can return BLANK without raising (e.g. a
+            # scanned/figure-only PDF where text extraction yields nothing). Fail LOUD at upload
+            # time (not a deferred /runs 400) with an actionable pointer — consistent with the
+            # parse-error branch above.
+            raise HTTPException(
+                status_code=422,
+                detail=(
+                    f"the 'local' backend extracted no text from this {ext} (likely a "
+                    "scanned / figure-only document). Enable the VLM-OCR backend "
+                    "(PG_DOC_INGEST_BACKEND=vlm) once its open-weight deps are installed."
+                ),
+            )
     else:
-        chunks = []
-        preview_text = ""
-        preview_html = ""
+        # legacy (DEFAULT): non-text formats are not parsed here -> downstream fail-loud 400.
+        text = ""
+
+    chunks = [text[i : i + 280] for i in range(0, min(len(text), 840), 280) if text]
+    preview_text = text
+    preview_html = f"<pre>{_html.escape(text)}</pre>" if text else ""
 
     response = UploadResponse(
         document_id=document_id,
diff --git a/tests/polaris_v6/test_doc_ingest_backend_iready011.py b/tests/polaris_v6/test_doc_ingest_backend_iready011.py
new file mode 100644
index 00000000..ec466110
--- /dev/null
+++ b/tests/polaris_v6/test_doc_ingest_backend_iready011.py
@@ -0,0 +1,144 @@
+"""I-ready-011 (#1077) — PG_DOC_INGEST_BACKEND selector on the v6 upload path.
+
+The v6 HTTP upload path (`upload.py`) decoded only .md/.txt and returned chunks=[] for PDF/DOCX
+(→ runs.py HTTP 400 "pdf/docx parsing is not yet available"). This adds PG_DOC_INGEST_BACKEND:
+  * legacy (DEFAULT) — byte-identical (PDF/DOCX still unparsed → empty chunks);
+  * local — PDF/DOCX parsed via the EXISTING DocumentIngester (PyMuPDF + Tesseract fallback);
+  * vlm/docling/surya/... — operator-gated heavy-OCR stub that fails LOUD (501), no model load.
+
+Offline / §8.4-clean: the PDF fixture is born-digital (a text layer inserted via fitz), so the
+'local' path uses PyMuPDF text extraction with NO OCR model (Tesseract fires only when the
+extracted text is below threshold). DocumentIngester persistence is redirected to tmp.
+"""
+
+from __future__ import annotations
+
+import asyncio
+from io import BytesIO
+
+import pytest
+from fastapi import HTTPException, UploadFile
+
+import polaris_graph.document_ingester as document_ingester
+from polaris_v6.api import upload as upload_mod
+from polaris_v6.api.upload import _doc_ingest_backend, upload_document
+
+_PDF_TEXT = (
+    "Synthetic trial fixture (PUBLIC_SYNTHETIC). In the ZORBLAX-7 study the experimental compound "
+    "reduced the fictional Quibble Score by 42 percent versus placebo."
+)
+
+
+def _born_digital_pdf_bytes() -> bytes:
+    """A 1-page PDF with a real text layer (no scan) → PyMuPDF text extraction, NO Tesseract."""
+    import fitz  # PyMuPDF (in requirements.txt)
+
+    doc = fitz.open()
+    page = doc.new_page()
+    page.insert_text((72, 144), _PDF_TEXT, fontsize=11)
+    data = doc.tobytes()
+    doc.close()
+    return data
+
+
+def _uf(name: str, content: bytes) -> UploadFile:
+    return UploadFile(file=BytesIO(content), filename=name)
+
+
+@pytest.fixture()
+def _hermetic_storage(tmp_path, monkeypatch):
+    monkeypatch.setattr(document_ingester, "DOCUMENT_STORAGE_DIR", tmp_path / "doc_store")
+    return tmp_path
+
+
+@pytest.fixture(autouse=True)
+def _clear_upload_table():
+    upload_mod._UPLOAD_TABLE.clear()
+    yield
+    upload_mod._UPLOAD_TABLE.clear()
+
+
+# ── default + selector ──────────────────────────────────────────────────────
+
+def test_backend_default_is_legacy(monkeypatch):
+    monkeypatch.delenv("PG_DOC_INGEST_BACKEND", raising=False)
+    assert _doc_ingest_backend() == "legacy"
+    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "LOCAL")
+    assert _doc_ingest_backend() == "local"  # normalized lower
+
+
+# ── legacy: byte-identical (PDF unparsed) ───────────────────────────────────
+
+def test_legacy_pdf_yields_no_chunks(monkeypatch):
+    monkeypatch.delenv("PG_DOC_INGEST_BACKEND", raising=False)  # default legacy
+    resp = asyncio.run(upload_document(file=_uf("trial.pdf", b"%PDF-1.4 fake"), classification="PUBLIC_SYNTHETIC"))
+    assert resp.content == ""
+    assert resp.chunk_preview == []
+    assert resp.parse_status == "queued"  # downstream runs.py then 400s — unchanged behavior
+
+
+def test_md_unchanged_under_every_backend(monkeypatch):
+    for backend in ("legacy", "local", "vlm"):
+        monkeypatch.setenv("PG_DOC_INGEST_BACKEND", backend)
+        resp = asyncio.run(upload_document(file=_uf("note.md", b"# Title\n\nHello world."), classification="PUBLIC_SYNTHETIC"))
+        assert "Hello world." in resp.content
+        assert resp.chunk_preview  # non-empty
+        assert resp.parse_status == "completed"
+
+
+# ── local: PDF parsed via existing DocumentIngester (no OCR model) ──────────
+
+def test_local_pdf_is_parsed_to_chunks(_hermetic_storage, monkeypatch):
+    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "local")
+    resp = asyncio.run(upload_document(file=_uf("trial.pdf", _born_digital_pdf_bytes()), classification="PUBLIC_SYNTHETIC"))
+    assert "ZORBLAX-7" in resp.content
+    assert resp.chunk_preview  # non-empty → downstream runs.py will chunk + ground, no 400
+    assert resp.parse_status == "completed"
+
+
+def test_local_parse_failure_fails_loud(_hermetic_storage, monkeypatch):
+    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "local")
+    # Not a real PDF → DocumentIngester raises → 422 fail-loud (never silent-empty).
+    with pytest.raises(HTTPException) as exc:
+        asyncio.run(upload_document(file=_uf("broken.pdf", b"not a pdf at all"), classification="PUBLIC_SYNTHETIC"))
+    assert exc.value.status_code == 422
+
+
+# ── vlm: operator-gated fail-loud stub, no heavy import ─────────────────────
+
+def test_unknown_backend_fails_loud_400(monkeypatch):
+    """Codex diff-gate P2: a typo'd PG_DOC_INGEST_BACKEND must fail loud (400), not silently
+    fall back to legacy (which would unparse a PDF the operator thinks they enabled)."""
+    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "locl")  # typo
+    with pytest.raises(HTTPException) as exc:
+        asyncio.run(upload_document(file=_uf("trial.pdf", b"%PDF fake"), classification="PUBLIC_SYNTHETIC"))
+    assert exc.value.status_code == 400
+    assert "unknown" in str(exc.value.detail).lower()
+
+
+def test_local_blank_extraction_fails_loud_422(monkeypatch):
+    """Codex diff-gate P2: DocumentIngester can return blank without throwing (scanned/figure-only
+    PDF). The 'local' backend must fail loud at upload (422), not defer a confusing /runs 400."""
+    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "local")
+
+    async def _blank(content, ext):
+        return "   \n\t  "  # whitespace-only extraction
+
+    monkeypatch.setattr(upload_mod, "_extract_text_local", _blank)
+    with pytest.raises(HTTPException) as exc:
+        asyncio.run(upload_document(file=_uf("scanned.pdf", b"%PDF fake"), classification="PUBLIC_SYNTHETIC"))
+    assert exc.value.status_code == 422
+    assert "no text" in str(exc.value.detail).lower()
+
+
+@pytest.mark.parametrize("backend", ["vlm", "docling", "surya", "deepseek-ocr-2"])
+def test_vlm_backend_fails_loud_501(monkeypatch, backend):
+    import sys
+    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", backend)
+    with pytest.raises(HTTPException) as exc:
+        asyncio.run(upload_document(file=_uf("trial.pdf", _born_digital_pdf_bytes() if False else b"%PDF fake"), classification="PUBLIC_SYNTHETIC"))
+    assert exc.value.status_code == 501
+    assert "operator" in str(exc.value.detail).lower()
+    # The stub must NOT import a heavy OCR engine.
+    assert "docling" not in sys.modules
+    assert "surya" not in sys.modules

```
