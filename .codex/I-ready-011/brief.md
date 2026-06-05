# Codex BRIEF review — I-ready-011 (#1077): deep OCR / graphic-doc ingestion

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Decide the scope question in §3 and judge the acceptance criteria; return the YAML verdict block ONLY. Claude authors the diff after APPROVE.**

---

## 0. What this is

Brief gate for I-ready-011 (#1077), F11 P1 (ocr_graphics), an INDEP readiness issue. Branch will be `bot/I-ready-011-doc-ingest-backend` off `bot/I-ready-013`. Full finding: `.codex/I-ready-000/findings/ocr_graphics.md`. **This brief routes a real scope decision to you (§3) — the honest fix needs heavy GPU-class deps that §8.4 forbids loading in the autonomous loop, so I need your call on what ships tonight vs what defers to operator-gated activation.**

## 1. The gap (grounded)

Two disconnected realities:
- A capable ingester EXISTS (`src/polaris_graph/document_ingester.py`): PyMuPDF text + pytesseract OCR fallback for scanned/vector PDFs, image OCR, Whisper audio. `requirements.txt` HAS `PyMuPDF==1.27.2.3`, `python-docx==1.2.0`, `pytesseract==0.3.13` (verified) — so basic PDF/DOCX parsing needs NO new deps.
- BUT the v6 HTTP upload path `src/polaris_v6/api/upload.py:121-132` only decodes `.md`/`.txt` (`else: chunks=[]`), and `runs.py:60-69` then raises HTTP 400 "pdf/docx parsing is not yet available" for PDF/DOCX. So a clinician dropping a trial PDF into the v6 UI gets zero evidence.

**Important context (already shipped):** #1073 (I-ready-010, merged into this stack as a sibling PR) wired `DocumentIngester` (PyMuPDF + Tesseract OCR fallback) into the **benchmark** path (`run_gate_b --upload-file`). So the beat-both Gate-B path can ALREADY ingest + OCR a scanned PDF. The remaining F11 gap is therefore: (a) the v6 **UI** upload path still 400s on PDF/DOCX; (b) figure/chart/table semantic understanding (Tesseract reads pixels, not forest-plot/Kaplan-Meier semantics) — the 2026 SOTA is VLM-OCR (DeepSeek-OCR-2 / Docling+Surya) emitting structure-preserving Markdown, which are NEW heavy open-weight deps (sovereign-deployable but GPU-class).

## 2. §8.4 constraint

I cannot load Docling/Surya/DeepSeek-OCR-2 (GB-scale models) in the autonomous loop, and adding those deps + license clearance is operator-gated. So the VLM-OCR upgrade itself defers to operator activation. The question is what real, faithfulness-safe value ships tonight using EXISTING deps + inert plumbing for the heavy backend.

## 3. SCOPE DECISION (route to you)

**Option A — wire existing DocumentIngester into the v6 upload path + flag-gated VLM stub.** Add `PG_DOC_INGEST_BACKEND={legacy|local|vlm}`:
- `legacy` (DEFAULT) — current `.md`/`.txt`-only behavior, byte-identical (PDF/DOCX still 400). 
- `local` — route PDF/DOCX through the EXISTING `DocumentIngester` (PyMuPDF + Tesseract, no new deps) so they produce chunks instead of 400. Keeps the fail-loud-on-empty contract in `runs.py`.
- `vlm`/`docling` — an INERT, fail-LOUD stub: raises a clear "VLM-OCR backend requires operator-installed deps (docling/surya/deepseek-ocr-2) + sign-off; not enabled" — NO model load.
- **Open faithfulness question for you:** the v6 upload path is pipeline-B (UI/worker), not pipeline-A (the strict_verify + 4-role benchmark). I have NOT audited whether uploaded-doc text on the pipeline-B path is subject to per-sentence provenance verification before it can be cited. If pipeline-B lets uploaded text be cited WITHOUT verification, then enabling `local` PDF parsing there widens an un-verified-evidence surface — in which case `local` should NOT be wired tonight (or only behind the same sovereignty/verification gate). Please weigh: is Option A's `local` wiring faithfulness-safe on pipeline-B, or must it stay inert pending a pipeline-B verification audit?

**Option B — inert plumbing only.** Ship ONLY the `PG_DOC_INGEST_BACKEND` flag scaffold (default `legacy` byte-identical) + the fail-loud `vlm` stub + a regression-marker test locking the current 400-on-PDF behavior; defer ALL real parsing wiring (both `local` and `vlm`) to an operator-gated follow-up. Lowest risk, lowest value.

**My lean:** Option A IF you judge pipeline-B upload evidence is already verification-gated (so `local` is faithfulness-safe); else Option B. Either way the `vlm` backend is an inert operator-gated stub tonight. Your call decides which the diff implements.

## 4. Acceptance criteria (GREEN)

- `PG_DOC_INGEST_BACKEND` default `legacy` → byte-identical (PDF/DOCX still 400; `.md`/`.txt` unchanged). Test-pinned.
- (Option A only) `local` → a tiny text-PDF/DOCX fixture produces non-empty chunks via DocumentIngester (offline, no OCR model — a born-digital text PDF uses PyMuPDF text extraction, no Tesseract); fail-loud-on-empty preserved.
- `vlm`/`docling` → fail-loud stub (clear operator-deps message), NO heavy model import.
- Faithfulness: no path lets uploaded text bypass whatever verification pipeline-B already enforces (per your §3 ruling).
- Sovereignty: any future VLM weights are open-weight, Canada/EU-deployable (documented; not activated tonight).
- Offline smoke green (no GPU, no VLM model, §8.4-clean); flag-OFF/`legacy` byte-identical.

## 5. Files I have ALSO checked and they're clean (adjacent-file scan)

- `src/polaris_v6/api/upload.py:40` (allowed ext `{.pdf,.docx,.md,.txt}`), `:121-132` (the `.md`/`.txt`-only branch — the edit site), `:66-82` `chunk_text`, `:85-91` `get_upload_record`.
- `src/polaris_v6/api/runs.py:40-78` `_resolve_uploaded_documents` (fail-loud-on-empty 400 — keep).
- `src/polaris_graph/document_ingester.py` — `ingest` (async, PyMuPDF text + Tesseract OCR fallback only when text<threshold), `PARSERS`, `DOCUMENT_STORAGE_DIR` (env-redirectable for hermetic test). The reusable parser.
- `src/polaris_graph/tools/pdf_table_extractor.py` — pdfplumber tables-to-markdown, ZERO production caller (finding-confirmed) — candidate for the table path but out of tonight's scope unless you fold it in.
- `requirements.txt` — PyMuPDF/python-docx/pytesseract present; docling/surya/deepseek-ocr NOT present (the heavy deps).
- `scripts/dr_benchmark/run_gate_b.py` (#1073 `_resolve_benchmark_upload`) — the benchmark path already uses DocumentIngester; this issue does NOT touch it.

## 6. Smoke plan (offline, no GPU, no VLM — §8.4-clean)

`tests/polaris_v6/test_doc_ingest_backend_iready011.py`: (a) `legacy` default → PDF bytes → `chunks=[]` / 400 (regression marker, byte-identical); (b) [Option A] `local` → a born-digital text-PDF fixture → non-empty chunks (PyMuPDF text path, no Tesseract); (c) `vlm` → fail-loud stub, asserts no docling/surya import; (d) `.md`/`.txt` unchanged across all backends.

## 7. Output schema (return EXACTLY this; loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
scope: option_a_wire_local | option_b_inert_only | other
local_wiring_faithfulness_safe: yes | no | needs_pipelineB_audit
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
