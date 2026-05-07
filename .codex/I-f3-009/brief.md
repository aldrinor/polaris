# Codex Brief Review — I-f3-009 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-009 — F3 adversarial: 8 input types
**Phase:** 1 / **Feature:** F3
**LOC budget:** 200 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: 8 adversarial inputs (100MB, 0-byte, malformed, password-protected, image-only, Word, txt, EPUB) — each handled per spec. Backend is the boundary that returns the right error/status; this Issue ships pytest tests against the v6 upload route, NOT frontend tests (frontend gates on size/extension; backend handles bytes-level validation).

## Substrate (HONEST)

- `src/polaris_v6/api/upload.py`: existing route. Validations:
  - filename required (400)
  - extension in `{".pdf", ".docx", ".md", ".txt"}` else 415
  - size > MAX_BYTES (50MB) → 413
  - empty → 422
- Currently NO checks for: malformed PDF bytes, password-protected PDF, image-only PDF (parses to empty content), EPUB (out of allowed extensions → 415). 
- Each of the 8 inputs maps to a discrete spec'd outcome.

## 8-input matrix (binding spec)

| # | Input | Expected backend behavior | Test name |
|---|---|---|---|
| 1 | 100MB file | HTTP 413 "exceeds limit" | test_100mb_rejected_413 |
| 2 | 0-byte file | HTTP 422 "empty file" | test_empty_file_rejected_422 |
| 3 | malformed PDF (random bytes with .pdf ext) | HTTP 201 with parse_status="queued"+chunk_preview=[] (current behavior — graceful queue; real parser failure handled async) | test_malformed_pdf_returns_queued |
| 4 | password-protected PDF (synthetic stub: bytes that look like encrypted) | HTTP 201 with parse_status="queued" (same as malformed; synchronous path doesn't decrypt) | test_password_pdf_returns_queued |
| 5 | image-only PDF (synthetic 1×1 png) | HTTP 415 (.png ext not allowed) — actually, wait: if filename is "image.pdf" but bytes are PNG, server doesn't validate magic → returns 201 queued. Test for THAT honest behavior. | test_image_only_pdf_filename_returns_queued |
| 6 | Word .docx | HTTP 201 with parse_status="queued" (no async parser yet for docx) | test_docx_returns_queued |
| 7 | .txt file | HTTP 201 with parse_status="completed", chunks > 0 | test_txt_returns_completed |
| 8 | EPUB (.epub ext) | HTTP 415 unsupported | test_epub_rejected_415 |

## Acceptance criteria (binding)

1. **`tests/v6/test_upload_adversarial.py`** (NEW): 8 pytest tests using FastAPI TestClient. Per CLAUDE.md §9.4 NO `unittest.mock`; use real FastAPI TestClient.
   - Inputs: synthetic file bytes constructed inline (e.g. `bytes(50_001_000)` for 50MB+1byte; `b""` for empty; `b"%PDF-1.0\n<malformed>"` for malformed PDF; etc.).
   - Each test: `client.post("/upload", files={"file": (filename, content, content_type)}, data={"classification": "UNKNOWN"})`.
   - Assert exact `response.status_code` + (where applicable) `response.json()["parse_status"]` or `response.json()["detail"]`.
   - LOC: ~150.

2. **`tests/v6/__init__.py`** (NEW if missing): empty package marker. LOC: 0.

## Planned diff shape

```
tests/v6/__init__.py                         NEW +0 (if missing)
tests/v6/test_upload_adversarial.py          NEW +150
```

LOC: +150 net. Under CHARTER §1 200-cap by 50; under breakdown 200 budget by 50.

## Out of scope

- Backend bytes-level validation hardening (e.g. PDF magic-byte check, password-protected PDF detection) → follow-up I-f3-009-back. This Issue tests CURRENT behavior; hardening is a separate Issue.
- Frontend adversarial coverage → already covered by I-f3-005 (`oversize`, `non-PDF .txt drop`, etc).

## Risks for Codex Red-Team

1. **TestClient covers the v6 mounted FastAPI app.** Need to construct via `from polaris_v6.api.app import create_app; app = create_app(); client = TestClient(app)` — this triggers the full app construction including OTel middleware. Deferring middleware setup or mocking heavy deps may be needed; brief author commits to verifying during impl.

2. **Synthetic file bytes.** 50MB Buffer in tests. RAM cost during test run is ~50MB; acceptable.

3. **MAX_BYTES is 50MB (post I-f3-005).** "100MB" input → use `bytes(101 * 1024 * 1024)` to test the 413.

4. **Image-only PDF with .pdf ext.** Server doesn't validate magic bytes. Test asserts 201 queued (HONEST current behavior, not aspirational).

5. **EPUB unsupported.** `.epub` extension not in `ALLOWED_EXTENSIONS` → 415. Test asserts.

6. **CHARTER §1 LOC cap.** 150 net.

7. **No new package.json / requirements.txt dep.**

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
