# Claude architect audit — I-ready-010 (#1073): Gate-B uploaded-document wiring

Reviewer: Claude (architect). Scope: the END RESULT of the #1073 diff (commits `f1b176c8` + `177f263c` on `bot/I-ready-010-doc-upload-wiring`, off `bot/I-ready-013`). Method: §-1.1 line-by-line — each claim verified against the actually-changed code + the existing consumer it feeds, not against the brief's prose.

## 1. The gap closed (verified against the running code)

- **Producer gap, confirmed:** `scripts/dr_benchmark/run_gate_b.py::load_locked_questions` filters `SWEEP_QUERIES`; the 5 locked questions carry only `{amplified, domain, question, slug}` (smoke-confirmed in the finding). The CLI `main` exposed only `--only/--all/--list`. So `q["uploaded_documents"]` was never set on the benchmark path and the consumer at `run_honest_sweep_r3.py:3458` (`_upload_docs = q.get("uploaded_documents") or []`) was dead. VERIFIED by reading both files.
- **Consumer unchanged + real:** `run_honest_sweep_r3.py:3458-3473` reads `q["uploaded_documents"]`, calls `build_upload_evidence_rows`, prepends rows onto `evidence_for_gen`, records `summary["uploaded_documents_used"/"_blocked"]`. The diff does NOT touch this — it only feeds it. VERIFIED.

## 2. Faithfulness invariants — line-by-line (the clinical-safety bar)

- **No provenance/strict_verify bypass.** Uploaded chunks become evidence rows ONLY via `build_upload_evidence_rows` (`upload_evidence.py:51`), which emits `{evidence_id: ev_upload_*, direct_quote: <chunk text>, tier: T2, ...}`. These rows are prepended onto `evidence_for_gen` and flow through the SAME generator → `strict_verify` → 4-role D8 path as every other evidence row. There is NO code path in the diff where an uploaded chunk becomes a verified claim without the `[#ev:...]` provenance token + numeric-match + ≥2 content-word-overlap checks. VERIFIED: the diff adds only the producer (`q["uploaded_documents"]`); it adds nothing to the generator or verifier. Invariant 9.1.2/9.1.3 intact.
- **Two-family + zero-verified abort untouched.** No change to evaluator family segregation or the abort taxonomy. VERIFIED (diff is confined to `run_gate_b.py` + a test).
- **Sovereignty enforced twice (belt-and-suspenders).** `_resolve_benchmark_upload` routes the doc through `partition_uploads_by_sovereignty` and returns ONLY the egress-cleared (`PUBLIC_SYNTHETIC`) partition. `build_upload_evidence_rows` independently RAISES `UploadSovereigntyError` on any non-PUBLIC_SYNTHETIC doc. A non-PUBLIC_SYNTHETIC `--upload-classification` ⇒ `allowed` empty ⇒ `main` `parser.error` (rc2) BEFORE any token spend. VERIFIED against `upload_evidence.py:38-99` + the rc2 test. No path lets `CAN_REAL`/`PRIVATE`/`CLIENT`/`UNKNOWN` reach the external generator.

## 3. Safety / honesty properties

- **Flag-OFF byte-identical.** With no `--upload-file`, `_attach_uploads` stays `[]`; the per-q `if _attach_uploads:` guard is False ⇒ no copy, no attach ⇒ the question handed to `run_gate_b_query` IS the registry entry (`q is registry_entry`, test-pinned). The feature is fully inert by default. VERIFIED.
- **Registry isolation.** `load_locked_questions` returns the live `SWEEP_QUERIES` dict; the diff attaches uploads to a `dict(q)` shallow COPY (fresh top-level `uploaded_documents` key; no nested registry structure mutated). The shared registry stays clean for the next question / sibling tests (test-pinned: `"uploaded_documents" not in registry_entry` after a run). VERIFIED.
- **Fail-loud (LAW II), no silent zero-evidence.** Missing file → FileNotFoundError; empty/whitespace extraction → ValueError; no grounding chunks → ValueError; unsupported ext / oversized / missing parser dep → DocumentIngestionError re-raised as ValueError (iter-1 P2 fix). All converge on `main`'s `except (FileNotFoundError, ValueError): parser.error(...)` → clean pre-spend rc2. A doc that can't ground a run never silently produces a zero-upload benchmark. VERIFIED.
- **NO-SPEND/NO-NETWORK-at-import invariant preserved.** Every upload import (`DocumentIngester`, `DocumentIngestionError`, `chunk_text`, `partition_uploads_by_sovereignty`) is INSIDE `_resolve_benchmark_upload`; nothing was added at module top. `import run_gate_b` still pulls neither `document_ingester` nor `fastapi`. Source-pinned by `test_upload_imports_are_lazy_inside_the_resolver`. VERIFIED.
- **`--list` / `--dry-run` unaffected.** The resolve sits in the real-run path AFTER the `--list` early `return 0`; `--upload-file --list` ingests nothing and leaves env byte-identical (the existing env-restore test still passes). VERIFIED.
- **No-divergence from the UI path.** The CLI resolver mirrors the production worker (`runs.py::_resolve_uploaded_documents`): same `chunk_text` chunker, same `{document_id, classification, filename, chunks}` shape, same fail-loud-on-empty. The benchmark consumes uploads identically to the UI. VERIFIED.

## 4. Scope discipline

- **PART-1 wiring only** (Codex brief-gate APPROVE, `scope_decision=part1_only_correct`). The PART-2 markdown-backend table-fidelity gap (Docling/MarkItDown, flat-text→markdown for clinical dose/endpoint tables) is DEFERRED to #1077 (the OCR/Docling/Surya deps issue) — it needs new heavy deps that #1077 owns and cannot be heavy-smoked in the autonomous loop (§8.4). This issue stays pure-Python, additive, flag-OFF byte-identical, 130 LOC (< 200-LOC cap). HONEST RESIDUAL: a benchmark run that attaches a table-heavy PDF still gets de-structured table text through `PyMuPDF get_text("text")` — that fidelity improvement lands in #1077, not here.

## 5. Verdict

Faithfulness-safe, sovereignty-enforced, flag-OFF byte-identical, fail-loud, in-scope. The wiring makes the upload→citable-evidence capability live + measurable on the exact beat-both shipping path it was previously absent from. 14 offline upload tests + 17 existing CLI tests green; no regression. Codex diff-gate: APPROVE iter-1 (0 P0/P1, 1 cosmetic P2 now folded in); iter-2 confirms the P2 fix.

**Architect verdict: APPROVE.** Residual (table-fidelity markdown backend) tracked in #1077, not a blocker for this wiring.
