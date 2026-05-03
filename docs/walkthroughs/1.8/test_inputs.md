# Phase 1 Walkthrough — 17-Input Adversarial Corpus (Phase-1-PARTIAL bar)

> **Scope (post halt-condition #4 resolution path 3 — 2026-05-02):** F1 (scope
> discovery, 5 inputs) + F2 (BPEI ambiguity, 5 inputs) + F3 (document upload
> endpoint contract, 4 inputs) + F15 (audit bundle export, 3 inputs) = **17
> inputs**. Crown-jewel surface checks (Inspector, frame coverage,
> contradictions, two-family disagreement) are Phase 2A-B features
> exercised in `2A.7_prep_briefing_pack` / `2B.7_prep_briefing_pack` —
> deliberately **out of scope** for this walkthrough.

Use this script in order. For each input: paste, observe, narrate.

---

## Block A — F1 Scope discovery (5 inputs)

1. **Drug name (clinical scope)**: type `tirzepatide` → expect Clinical drug audit template suggested within 200ms; click it; verify it loads scope examples.
2. **Trade query**: type `softwood lumber dispute` → expect Trade audit template; verify in-scope examples include CUSMA + WTO.
3. **Out-of-scope nonsense**: type `purple monkey dishwasher` → expect either (a) no template suggested with helpful empty-state, or (b) suggestion of "general scope" that visibly says no specialized template applies. NOT acceptable: silent default to clinical or first template.
4. **Multi-word ambiguous**: type `quantum computing impact` → expect at least 2 templates (defense / AI sovereignty / climate) suggested; user picks.
5. **French language**: type `bois d'œuvre canadien` → expect either Trade template suggested, or refusal with "supported language: English" message. NOT acceptable: silent acceptance of mangled-French response.

## Block B — F2 BPEI ambiguity (5 inputs)

6. **Classic BPEI test**: type `What is BPEI?` → expect modal with at least 3 candidate meanings (e.g., Beth Israel Deaconess, biopsychosocial, business process, etc.). NOT acceptable: silent answer.
7. **Acronym with one strong meaning**: type `What is FDA?` → expect single-candidate flow (no modal, FDA is unambiguous).
8. **Acronym in context**: type `Has the FDA approved tirzepatide for weight loss?` → no modal; query proceeds (context disambiguates).
9. **Truly ambiguous**: type `python` → modal with at least 2 candidates (snake / programming language); user picks; query proceeds with disambiguation tag.
10. **Disambiguate then refine**: in modal from #9, click "programming language" → expect query to update with disambiguation visible.

## Block C — F3 Document upload (4 inputs, **endpoint-contract-only**)

> Phase-1-PARTIAL: These inputs verify the `POST /upload` endpoint contract
> shipped at `src/polaris_v6/api/upload.py`. They DO NOT verify parser output,
> chunk listings, tier assignment, or cite-uploaded-doc-in-next-query. Those
> behaviors are Phase-1-END (see briefing.md known-gaps). If they appear to
> work, observe + record; if they do not, **do not fail** — that is expected.

11. **Drop a small text-PDF (≤ 5 MB)**: drag a PDF onto the dropzone → expect HTTP 201 Created (`src/polaris_v6/api/upload.py:50` declares `status_code=201`) + an `UploadResponse` body containing `document_id`, `filename`, `bytes`, `sha256`, `classification`, `parse_status`, `chunk_preview`. Visible UX: upload progress bar reaches 100%. **Out of scope to verify**: parse_status value beyond what HEAD returns, chunk_preview content, parse-completion latency.
12. **Drop a PDF approaching 25 MB limit**: try a ~20-24 MB PDF → expect HTTP 201 Created + `UploadResponse` body. Then try a >25 MB PDF → expect HTTP 4xx with `"File exceeds 25 MB limit"` message (`MAX_BYTES = 25 * 1024 * 1024` per `src/polaris_v6/api/upload.py:34`). NOT acceptable: silent acceptance of >25 MB upload, or 5xx without size message.
13. **Drop an image-only PDF (scanned doc)**: endpoint-contract-only means we accept the upload (HTTP 201 Created + `UploadResponse` body); OCR triggering is Phase-1-END. Acceptable Phase-1-PARTIAL behaviors: (a) HTTP 201 returned silently, (b) HTTP 201 returned + a "Phase 1 OCR pending" warning surfaced. NOT acceptable: 5xx without explanation.
14. **Reference uploaded doc in query (out-of-scope check, observational only)**: with PDF uploaded, type a question that *might* be answerable from the doc. Expected Phase-1-PARTIAL behavior: query proceeds against backend evidence pool only (uploaded doc may not appear cited; this is OK). Observe whether the backend ever produces a `[#ev:user_doc_*]` citation — if yes, log as bonus Phase-1-END behavior detected; if no, **do not fail** — that is expected per known-gaps.

## Block D — F15 Audit bundle export (3 inputs, **EvidenceContract JSON, not ZIP**)

> Phase-1 substrate at `src/polaris_v6/api/bundle.py` returns an
> EvidenceContract v1.0 JSON document for the requested `run_id` (single
> file, not a ZIP). The frontend `downloadBundleAsJson` helper saves that
> JSON to disk. ZIP packaging with `report.md`/`evidence/`/`trace.jsonl`/
> `provenance.json` is Phase-1-END / Phase-2 work; it is **out of scope**
> for this walkthrough.

15. **Run a query, then export**: load `/inspector/golden_clinical_001` (or any golden-fixture run id from `_GOLDEN_RUN_INDEX` in `src/polaris_v6/api/bundle.py`). Click "Export bundle". Expect a single `.json` file downloaded within 5s.
16. **Verify bundle contents**: open the downloaded JSON in any text editor. Expect a single object conforming to `EvidenceContract v1.0` per `src/polaris_v6/schemas/evidence_contract.py` lines 86-105. All **15 required top-level fields** must be present:
    - `contract_version: "1.0"` (literal)
    - `run_id` (string, matches the run loaded)
    - `template` (one of clinical / housing / defense / climate / ai_sovereignty / trade / canada_us / workforce)
    - `question` (string, the user's research question)
    - `queued_at` (ISO-8601 string)
    - `finished_at` (ISO-8601 string)
    - `pipeline_status` (one of `success`, `abort_scope_rejected`, `abort_corpus_inadequate`, `abort_corpus_approval_denied`, `abort_no_verified_sections`, `error_*` — see CLAUDE.md §9.3)
    - `evidence_pool` (array of source spans, ≥1 entry)
    - `verified_sentences` (array, may be empty if `pipeline_status` was an `abort_*`)
    - `frame_coverage` (array of per-frame coverage records)
    - `contradictions` (array, may be empty)
    - `cost_usd` (number ≥ 0, ≤ `PG_MAX_COST_PER_RUN` budget)
    - `generator_model` (string, e.g. `deepseek/deepseek-v4-flash`)
    - `verifier_model` (string, e.g. `google/gemma-4-31b`; MUST be different lineage from `generator_model`)
    - `family_segregation_passed: true` (CLAUDE.md §9.1 invariant 1; else flag P0)
17. **Bundle redaction posture for paywalled spans**: §G #5 IP counsel opinion is pending. Phase-1-PARTIAL acceptable behavior: bundle includes citations + DOI links for any T1-paywalled-journal sources. If verbatim spans are emitted with a placeholder like `[REDACTED — counsel review pending]`, that is also acceptable. NOT acceptable: verbatim paywalled spans appearing un-flagged (would block on legal review).

---

## End-of-walkthrough

After all 17 inputs:
- Stop recording
- Save to `.private/walkthroughs/1.8_<initials>_<YYYY-MM-DD>.mp4`
- Generate GPG-signed attestation per `briefing.md` step 7
- Add notes to `outputs/audits/walkthroughs/1.8_findings.md` if any P0/P1 surfaced
