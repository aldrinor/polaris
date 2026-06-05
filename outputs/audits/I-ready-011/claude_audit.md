# Claude architect audit — I-ready-011 (#1077): PG_DOC_INGEST_BACKEND (PDF/DOCX on the v6 upload path)

Reviewer: Claude (architect). Scope: the END RESULT of the #1077 diff (commits `a2c17ada` + the P2 fixup on `bot/I-ready-011-doc-ingest-backend`, off `bot/I-ready-013`). Method: §-1.1 line-by-line.

## 1. The gap closed

- `src/polaris_v6/api/upload.py` previously decoded ONLY `.md`/`.txt`; a PDF/DOCX upload yielded `chunks=[]` → `runs.py:61` raised HTTP 400 "pdf/docx parsing is not yet available." A clinician dropping a trial PDF into the v6 UI got zero evidence. VERIFIED against the pre-change `if ext in {".md",".txt"}: ... else: chunks=[]` branch.
- Now `PG_DOC_INGEST_BACKEND` dispatches: `legacy` (default, byte-identical), `local` (PDF/DOCX via the EXISTING `DocumentIngester` — PyMuPDF text + Tesseract OCR fallback, python-docx — deps already in requirements.txt), `vlm`/`docling`/`surya`/`deepseek-ocr-2`/`marker` (operator-gated 501 stub). VERIFIED.

## 2. Faithfulness invariant

- **No NEW verification bypass.** The `local` path produces `content` chunks the SAME way a `.md`/`.txt` upload already does (set `preview_text`/`chunks` from the extracted text, identical code below the dispatch); they flow into the identical downstream evidence/verification path. There is no path where a PDF-derived chunk is treated differently from a `.md`-derived chunk. Codex brief-gate explicitly ruled this faithfulness-safe (`local_wiring_faithfulness_safe=yes`). VERIFIED: the diff only changes WHICH bytes become `text`; the chunk/evidence handling is unchanged.

## 3. Safety / honesty properties

- **Flag-OFF (legacy) byte-identical.** Default `legacy` → a PDF still yields `content=""`/`chunks=[]`/`parse_status=queued` (downstream 400); `.md`/`.txt` unchanged; the `DocumentIngester`/fitz import is LAZY inside `_extract_text_local` so legacy pulls nothing new. VERIFIED (default + .md-unchanged tests).
- **Fail-loud (LAW II), no silent degradation.** A `local` parse error → 422; a `local` blank extraction (scanned/figure-only PDF where DocumentIngester returns "" without raising) → 422 at upload with an actionable "enable the VLM-OCR backend" pointer (not a deferred /runs 400); a `vlm` backend → 501 with operator-actionable detail; an UNKNOWN/typo'd backend → 400 (not a silent fallback to legacy). VERIFIED (4 fail-loud tests). The two latter guards were folded in from Codex diff-gate iter-1 P2.
- **§8.4 / no autonomous model load.** The `vlm` stub never imports docling/surya (test-pinned); the `local` path uses Tesseract ONLY when extracted text < threshold — the test fixture is a born-digital text PDF (PyMuPDF text, no OCR). The diff cannot load a GB-scale model in CI. VERIFIED.
- **Temp-file hygiene.** `_extract_text_local` unlinks the temp file in `finally`; the suffix is the validated ext (no traversal). VERIFIED.

## 4. Scope honesty

PART-1 (this issue): wire EXISTING deps (PyMuPDF/Tesseract/python-docx) so PDF/DOCX produce real chunks instead of HTTP 400. The 2026-SOTA VLM-OCR figure/chart/table understanding (Docling/Surya/DeepSeek-OCR-2 → structure-preserving Markdown) is NEW heavy open-weight GPU-class deps + license clearance → DEFERRED to operator-gated activation (the 501 stub names exactly what to install). HONEST RESIDUAL: a scanned/figure-heavy PDF on `local` gets Tesseract OCR (text only, no forest-plot/chart semantics) or fails loud at upload; the VLM upgrade lands when the operator installs the deps.

## 5. Verdict

Faithfulness-safe (no new verification bypass — equivalent to the existing .md/.txt path, Codex-confirmed), flag-OFF byte-identical, fail-loud on every degraded path (parse error / blank / unknown backend / operator-gated VLM), §8.4-clean (no autonomous model load). 11 behavioral + 22 existing upload/grounding regression green.

**Architect verdict: APPROVE.** Residual (VLM-OCR figure understanding) is operator-gated deps, documented in the 501 stub.
