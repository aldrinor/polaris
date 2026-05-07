# Claude Architect Audit — I-f3-009 (8-input adversarial)

**Branch:** bot/I-f3-009 / **Diff SHA256:** `11be1a42564661b10b3491836af456a94e5f69e0b94c77cc365d5473b6adf164`
**LOC:** 91 net (well under 200-cap)
**Tests:** 8/8 PASS

## Files

```
tests/polaris_v6/api/test_upload_adversarial.py   NEW +91
```

## Coverage

| # | Input | Outcome | Test |
|---|---|---|---|
| 1 | 100MB | 413 | test_100mb_rejected_413 |
| 2 | 0-byte | 422 | test_empty_file_rejected_422 |
| 3 | malformed PDF | 201 queued | test_malformed_pdf_returns_queued |
| 4 | password PDF | 201 queued | test_password_pdf_returns_queued |
| 5 | image-only PDF | 201 queued | test_image_only_pdf_filename_returns_queued |
| 6 | DOCX | 201 queued | test_docx_returns_queued |
| 7 | TXT | 201 completed | test_txt_returns_completed |
| 8 | EPUB | 415 | test_epub_rejected_415 |

## Architecture review

1. **Hermetic app-build** via `polaris_v6.api.app.create_app()`. Fixture clears env vars (SERPER, OPENROUTER, GPG, OTEL, S2) BEFORE construction so external-service initialization is deterministic.
2. **Tests CURRENT behavior, not aspirational.** Per brief HONEST framing — backend bytes-level validation hardening (PDF magic-byte check, password detection) is a follow-up, not this Issue.
3. **Iter-1 P2 (50MB+1 byte ≠ trigger 413):** `bytes(101 * 1024 * 1024)` confirmed in test #1.
4. **§9.4 compliance:** No `unittest.mock`. FastAPI TestClient + real route.

## Verdict

APPROVE for Codex diff review.
