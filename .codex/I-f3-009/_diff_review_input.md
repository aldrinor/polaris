# Codex Diff Review — I-f3-009 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-009 — F3 adversarial 8-input types
**Brief:** APPROVED iter 1 (0/0/1P2 size-example fix)
**Canonical-diff-sha256:** `11be1a42564661b10b3491836af456a94e5f69e0b94c77cc365d5473b6adf164`
**LOC:** 91 net
**Tests:** 8/8 PASS

## Files

```
tests/polaris_v6/api/test_upload_adversarial.py   NEW +91
```

## What changed

Single pytest module with 8 tests covering the binding 8-input matrix from the breakdown. Hermetic v6 app build via `create_app()` after clearing external-service env vars.

## Risks for Codex Red-Team

1. **Tests current behavior, not aspirational.** Backend doesn't validate PDF magic bytes; tests assert what the route actually returns (queued for malformed/password/image PDFs).
2. **101 MiB byte-array.** ~101MB heap during test #1. Acceptable single-test cost.
3. **§9.4 compliance:** No mocks; real TestClient.
4. **Hermeticity:** env vars cleared before app build. Tests pass regardless of host env.
5. **CHARTER §1 LOC cap:** 91 net.

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
diff --git a/tests/polaris_v6/api/test_upload_adversarial.py b/tests/polaris_v6/api/test_upload_adversarial.py
new file mode 100644
index 0000000..c61778b
--- /dev/null
+++ b/tests/polaris_v6/api/test_upload_adversarial.py
@@ -0,0 +1,91 @@
+"""I-f3-009 — adversarial 8-input matrix against /upload route."""
+
+from __future__ import annotations
+
+import os
+
+import pytest
+from fastapi.testclient import TestClient
+
+
+@pytest.fixture(scope="module")
+def client(monkeypatch_module=None):
+    """Hermetic v6 app build: clear external-service env vars first."""
+    for v in (
+        "SERPER_API_KEY", "OPENROUTER_API_KEY", "POLARIS_GPG_KEY_ID",
+        "OTEL_SEMCONV_STABILITY_OPT_IN", "SEMANTIC_SCHOLAR_API_KEY",
+    ):
+        os.environ.pop(v, None)
+    from polaris_v6.api.app import create_app
+    return TestClient(create_app())
+
+
+def _post(client: TestClient, name: str, content: bytes, mime: str = "application/octet-stream"):
+    return client.post(
+        "/upload",
+        files={"file": (name, content, mime)},
+        data={"classification": "UNKNOWN"},
+    )
+
+
+def test_100mb_rejected_413(client: TestClient) -> None:
+    big = b"\x00" * (101 * 1024 * 1024)
+    r = _post(client, "huge.pdf", big, "application/pdf")
+    assert r.status_code == 413
+
+
+def test_empty_file_rejected_422(client: TestClient) -> None:
+    r = _post(client, "empty.pdf", b"", "application/pdf")
+    assert r.status_code == 422
+
+
+def test_malformed_pdf_returns_queued(client: TestClient) -> None:
+    r = _post(client, "malformed.pdf", b"%PDF-1.0\n<not a real PDF>", "application/pdf")
+    assert r.status_code == 201
+    assert r.json()["parse_status"] == "queued"
+    assert r.json()["chunk_preview"] == []
+
+
+def test_password_pdf_returns_queued(client: TestClient) -> None:
+    # Synthetic encrypted-looking PDF stub. The current synchronous route
+    # does NOT decrypt; it queues with empty chunks.
+    fake_encrypted = b"%PDF-1.4\n/Encrypt 1 0 R\n<binary blob>"
+    r = _post(client, "encrypted.pdf", fake_encrypted, "application/pdf")
+    assert r.status_code == 201
+    assert r.json()["parse_status"] == "queued"
+
+
+def test_image_only_pdf_filename_returns_queued(client: TestClient) -> None:
+    # PNG bytes with .pdf filename. The route only checks extension, not magic.
+    png = (
+        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
+        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
+    )
+    r = _post(client, "image.pdf", png, "application/pdf")
+    assert r.status_code == 201
+    assert r.json()["parse_status"] == "queued"
+
+
+def test_docx_returns_queued(client: TestClient) -> None:
+    # DOCX is allowed by extension; sync route does not parse → queued.
+    fake_docx = b"PK\x03\x04" + b"\x00" * 100
+    r = _post(client, "doc.docx", fake_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
+    assert r.status_code == 201
+    assert r.json()["parse_status"] == "queued"
+
+
+def test_txt_returns_completed(client: TestClient) -> None:
+    txt = b"Hello world\nThis is a test document for chunking.\n" * 5
+    r = _post(client, "doc.txt", txt, "text/plain")
+    assert r.status_code == 201
+    body = r.json()
+    assert body["parse_status"] == "completed"
+    assert len(body["chunk_preview"]) > 0
+    assert body["content"]
+    assert "<pre>" in body["html"]
+
+
+def test_epub_rejected_415(client: TestClient) -> None:
+    epub = b"PK\x03\x04" + b"\x00" * 100
+    r = _post(client, "book.epub", epub, "application/epub+zip")
+    assert r.status_code == 415

```
