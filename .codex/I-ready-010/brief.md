# Codex BRIEF review — I-ready-010 (#1073): wire uploaded-document grounding into the Gate-B benchmark path

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Read the repo, judge this brief's acceptance criteria, and return the YAML verdict block (schema at the end) ONLY. Do NOT write or edit code; Claude authors the diff after this brief is APPROVE'd.**

---

## 0. What this brief is

This is the **brief gate** (acceptance-criteria correctness) for I-ready-010 (#1073), one of the 15 readiness-audit issues (#1070–#1084) gating the live beat-both run. It does NOT contain a diff yet — judge whether the PLAN + acceptance criteria below are correct and complete. After APPROVE, Claude writes the diff and submits it to a separate diff gate.

Branch: `bot/I-ready-010-doc-upload-wiring`, based off `bot/I-ready-013-analyst-synthesis-verified` (HEAD `07617c08`). **Why this base, not `polaris`:** the entire Gate-B benchmark launcher (`scripts/dr_benchmark/run_gate_b.py`) lives ONLY on the unmerged readiness stack (it was introduced by I-cap-005 / I-meta-008, not yet merged to `polaris`). The whole readiness audit is one stacked branch chain; an issue that touches Gate-B infra MUST stack on it.

## 1. The finding (F10 P1), restated

Full finding: `.codex/I-ready-000/findings/doc_ingestion.md` (line-by-line §-1.1 evidence audit included there).

POLARIS has a complete uploaded-document → citable-evidence capability **on the pipeline-B UI/worker path**: `src/polaris_v6/api/upload.py` (upload + chunk), `src/polaris_v6/api/runs.py::_resolve_uploaded_documents` (resolve ids → `{document_id, classification, filename, chunks}`), `src/polaris_v6/adapters/upload_evidence.py` (`partition_uploads_by_sovereignty` + `build_upload_evidence_rows` → `ev_upload_*` rows), and the sweep injection at `scripts/run_honest_sweep_r3.py:3458` (`_upload_docs = q.get("uploaded_documents") or []` → prepends rows onto `evidence_for_gen` → flows into generator + strict_verify + `evidence_pool.json` + bibliography).

**The gap:** the Gate-B benchmark launcher cannot attach a document. `scripts/dr_benchmark/run_gate_b.py::load_locked_questions` filters the static `SWEEP_QUERIES` registry; smoke-verified all 5 locked questions carry only `{amplified, domain, question, slug}` — no `uploaded_documents` key — and `main`'s argparse exposes only `--only/--all/--list`. So on the exact beat-both shipping path, `_upload_docs` is always `[]` and the injection at :3458 is dead. The headline differentiator — "upload your clinical PDF, get a cited report grounded in it" — is structurally untestable against ChatGPT/Gemini.

## 2. Proposed scope — PART 1 ONLY this issue (ROUTING A DECISION TO YOU)

The finding names two deltas:
- **PART 1 — WIRING (P1, primary):** add a CLI flag to attach a document to the benchmark questions, populating `q["uploaded_documents"]`. Pure Python; makes the feature live + measurable on the beat-both path.
- **PART 2 — QUALITY:** replace flat-text extraction (`PyMuPDF get_text("text")`) with a structure-preserving **markdown** backend (Docling/TableFormer or MarkItDown), flag-gated `PG_DOC_INGEST_BACKEND={legacy|docling|markitdown}`, for table fidelity (dose/endpoint grids the §-1.1 clinical standard depends on).

**Claude's proposed split: do PART 1 in #1073; DEFER PART 2 to #1077 (I-ready-011, the OCR/Docling/Surya deps issue).** Rationale:
1. **One-responsibility (LAW V):** PART 2 adds heavy new dependencies (Docling pulls torch/transformers; Marker pulls Surya). #1077 is *the* issue that owns adding + license-clearing those deps (operator-gated). Adding them here duplicates that work and couples two issues.
2. **§8.4 resource discipline:** Docling/Surya load GB-scale models; I cannot heavy-smoke them in the autonomous loop. PART 1 smokes offline with a tiny `.md` fixture (no model).
3. **Flag-OFF byte-identical + 200-LOC cap:** PART 1 keeps #1073 a small additive producer-side change. PART 2's converter swap is a larger ingestion-layer change better reviewed on its own.
4. **The P1 severity is the WIRING gap** (capability absent from the benchmark), not the flat-text quality gap (which is a within-UI-path fidelity concern). PART 1 closes the P1.

**Question for Codex:** is PART-1-only the right scope for #1073, deferring the markdown backend to #1077? Or do you judge the flat-text→markdown fidelity gap severe enough to require it in the same PR? (My lean: defer. If you disagree, say so with the quality-impact reasoning and I'll fold PART 2's flag-gated plumbing in — though the heavy-model smoke would have to be operator-run.)

## 3. PART 1 design (what the diff will do)

All changes in `scripts/dr_benchmark/run_gate_b.py` only (the producer). Additive; flag-OFF byte-identical.

**3a. Two new CLI args on `main`'s argparse (not in the mutually-exclusive selection group):**
- `--upload-file PATH` (default `None`): a local file to ingest and attach as grounding evidence to every benchmark question in this run.
- `--upload-classification {PUBLIC_SYNTHETIC,CAN_REAL,PRIVATE,CLIENT,UNKNOWN}` (default `UNKNOWN`): the sovereignty classification, mirroring `upload.py`'s conservative `UNKNOWN` default.

**3b. New module-level resolver helper** (NO spend / NO network at import — all imports lazy inside, only runs when `--upload-file` is passed):
```
def _resolve_benchmark_upload(path, classification) -> tuple[list[dict], int]:
    # lazy imports: DocumentIngester, chunk_text, partition_uploads_by_sovereignty
    # 1. ingest the file via DocumentIngester().ingest(Path(path))  [.md/.txt = lightweight _parse_text]
    # 2. content = (result["content"] or "").strip(); FAIL LOUD (ValueError) if empty  [mirrors runs.py:61]
    # 3. chunks = chunk_text(content)  [the canonical chunker — no divergence from the UI path]
    # 4. doc = {document_id: result["doc_id"], classification, filename: path.name, chunks}
    # 5. allowed, blocked = partition_uploads_by_sovereignty([doc])  [belt-and-suspenders sovereignty gate]
    # 6. return allowed, len(blocked)
```

**3c. In `main`, AFTER `load_locked_questions`, BEFORE the per-question loop:**
- if `--upload-file` given: call the resolver; if `allowed` is empty (doc blocked by sovereignty), `parser.error(...)` — FAIL LOUD that a non-PUBLIC_SYNTHETIC doc can never ground the external-generator benchmark (rather than silently run zero-upload). Print a one-line confirmation of the attached doc + chunk count for the blind operator.

**3d. In the per-question loop — attach to a COPY of `q`, never the shared registry entry:**
```
for q in questions:
    if _attach_uploads:
        q = dict(q)                                  # COPY — load_locked_questions returns the live SWEEP_QUERIES dict
        q["uploaded_documents"] = _attach_uploads
        q["uploaded_documents_blocked_count"] = _blocked_count
    summary = asyncio.run(run_gate_b_query(q, out_root))
```

**Why a copy:** `load_locked_questions` does `resolved.append(entry)` where `entry` IS the `SWEEP_QUERIES` registry dict (run_gate_b.py:886,893). Mutating it in place would leak `uploaded_documents` into the global registry — poisoning the routing tests and any later run in the same process. `dict(q)` is a shallow copy; `uploaded_documents` is a fresh key, read-only-consumed by `run_one_query` → `build_upload_evidence_rows`.

## 4. Acceptance criteria (what GREEN means for #1073)

1. `run_gate_b --upload-file <fixture.md> --upload-classification PUBLIC_SYNTHETIC --only <slug>` resolves the fixture into a `{document_id, classification, filename, chunks}` dict and sets it on `q["uploaded_documents"]` before `run_gate_b_query` — verified by a behavioral test that asserts the resolved `q` carries the upload and `build_upload_evidence_rows` produces an `ev_upload_*` row whose `direct_quote` contains the fixture's fact.
2. **Flag-OFF byte-identical:** without `--upload-file`, every resolved `q` is byte-identical to `load_locked_questions` output (no `uploaded_documents` key); the attach loop is a no-op.
3. **Sovereignty fail-loud:** a doc classified `CAN_REAL`/`PRIVATE`/`CLIENT`/`UNKNOWN` is blocked by `partition_uploads_by_sovereignty` (allowed empty, blocked=1) and `main` `parser.error`s rather than running a zero-upload benchmark.
4. **Registry isolation:** attaching `uploaded_documents` to the `q` copy does NOT mutate the shared `SWEEP_QUERIES` entry (the registry stays clean for the next question / other tests).
5. **Empty-extraction fail-loud:** an empty/whitespace-only file raises `ValueError` (LAW II — no silent zero-evidence run).
6. No-spend/no-network at import preserved: importing `run_gate_b` still opens no socket and pulls no `document_ingester`/`fastapi` (all upload imports are lazy inside the resolver).
7. Faithfulness invariants untouched: uploaded rows flow through the SAME `build_upload_evidence_rows` → prepend → strict_verify → 4-role path as the UI; no bypass of provenance/strict_verify; sovereignty partition enforced (only PUBLIC_SYNTHETIC reaches the external generator).
8. Offline smoke (no spend, no model) green; production diff < 200 LOC.

## 5. Files I have ALSO checked and they're clean (adjacent-file scan)

- `scripts/run_honest_sweep_r3.py:3458-3473` — the ONLY consumer of `q["uploaded_documents"]` + `q["uploaded_documents_blocked_count"]` in the sweep/benchmark path. Read-only: reads the list, builds rows, prepends, records counts in `summary`. My change feeds it; no edit needed there.
- `src/polaris_v6/adapters/upload_evidence.py` — `partition_uploads_by_sovereignty` (:38) + `build_upload_evidence_rows` (:51). I reuse both unchanged. `build_upload_evidence_rows` RAISES `UploadSovereigntyError` on non-PUBLIC_SYNTHETIC — my resolver pre-filters via `partition_uploads_by_sovereignty` so only allowed docs ever reach it (the actor path does the same).
- `src/polaris_v6/api/upload.py` — `chunk_text` (:66, size=280/max=40) + `get_upload_record` (:85). I reuse `chunk_text` (lazy import) for identical chunking. `_UPLOAD_TABLE` is an in-process dict (:63) — this is WHY a `--document-id` flag is unusable from the CLI (a fresh process can't read HTTP-uploaded docs), so `--upload-file` (ingest in-process) is the correct design.
- `src/polaris_v6/api/runs.py::_resolve_uploaded_documents` (:40-78) — the production worker's resolver. My CLI resolver mirrors its exact shape (`{document_id, classification, filename, chunks}` via `chunk_text`) and its fail-loud-on-empty (:61). No divergence.
- `src/polaris_graph/document_ingester.py` — `DocumentIngester.ingest` (:127, async), `PARSERS` map (:97; `.md`/`.txt`→`_parse_text`, lightweight), `get_document` (:1084). No heavy init in the class; fitz/pytesseract/whisper are lazy inside their own `_parse_*`. My `.md` smoke loads no model (§8.4).
- The 13 other `uploaded_documents` consumers (`state.py`, `actors.py`, `run_store.py`, `graph.py`, `analyzer.py`, `planner.py`, `pipeline_a_ui_adapter.py`, and tests under `v6/`, `integration/`, `polaris_graph/`) — all pipeline-B UI/worker/graph path. UNTOUCHED. My change is additive on the Gate-B producer only.
- `scripts/dr_benchmark/run_gate_b.py` itself: `run_gate_b_query(q,...)` (:703) passes `q` straight to `run_one_query`; `apply_full_capability_benchmark_slate` (:565) + `preflight_full_capability` (:787) are unaffected (upload attach happens on the per-q dict, after the slate, orthogonal to the cap floor).

## 6. Smoke plan (offline, no spend, no model — §8.4-clean)

New test file `tests/dr_benchmark/test_benchmark_upload_wiring_iready010.py`:
1. Wiring proof: ingest a tiny PUBLIC_SYNTHETIC `.md` fixture (a synthetic citable fact) → resolver returns the doc dict → `build_upload_evidence_rows(allowed)` yields an `ev_upload_*` row whose `direct_quote` contains the fact.
2. Flag-OFF byte-identical: questions without `--upload-file` carry no `uploaded_documents` key.
3. Sovereignty fail-loud: `CAN_REAL` doc → `allowed` empty, `blocked`=1.
4. Registry isolation: the shared `SWEEP_QUERIES` entry is unmutated after attaching to a `q` copy.
5. Empty-extraction fail-loud: empty `.md` → `ValueError`.
6. Import-cleanliness: importing `run_gate_b` does not import `document_ingester`/`fastapi` (assert via `sys.modules` after a fresh import) — confirms lazy-import invariant.

## 7. Output schema (return EXACTLY this; loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
scope_decision: part1_only_correct | require_part2 | other   # your call on §2
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
