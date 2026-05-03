# Phase 1 End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `1.8` per `docs/task_acceptance_matrix.yaml`
**Substrate-prep:** `1.8_prep_briefing_pack` (orchestrator-completed 2026-05-02)
**Walkthrough deadline:** 2026-06-04 (latest, per Plan v13 §G #7)
**Scope:** Phase 1 BPEI spine + Evidence Contract Gate (features F1, F2, F3, F15)

> **Phase-1-PARTIAL bar (post halt-condition #4 resolution path 3 — 2026-05-02).**
> The walkthrough exercises Phase-1 substrate that has already shipped to HEAD
> + uses stub LLM responses where the cluster is not yet online (§G #3 pending).
> Specifically, F4 (live audit with reasoning visibility) is **out of scope**
> for this walkthrough — F4 is a Phase 2A feature (`docs/carney_delivery_plan_v6_2.md` §F4)
> and is exercised in `2A.7_prep_briefing_pack`. Items below the line "Phase 1
> known gaps" mark anything that requires the cluster.

## What you'll be evaluating

4 features that landed in Phase 1 substrate:

| Feature | What it does | What to test |
|---|---|---|
| **F1 Scope discovery** | Dashboard surfaces 8 templates with in-scope examples; live template suggestion as user types | Type "tirzepatide" → expect Clinical drug audit suggestion within 200ms |
| **F2 BPEI ambiguity** | When a query has multiple plausible meanings, modal asks which entity user means | Type "What is BPEI?" → expect modal with at least 3 candidate meanings (syndrome/institute/chemical) |
| **F3a/F3b Document upload** | Drag-and-drop PDF; backend `/upload` accepts the file and returns a `document_id` (endpoint contract). Full parser + chunk + tier-assignment + cite-uploaded-doc loop is **Phase 1+** (see known-gaps below). | Drop a PDF, see upload progress + document_id returned. Citing the uploaded doc in a query is **out of scope** for this walkthrough — observe behavior if surfaced, do not fail. |
| **F15 Audit bundle export** | `GET /runs/{run_id}/bundle` returns the **EvidenceContract v1.0 JSON** for that run; frontend's "Export bundle" button calls `downloadBundleAsJson` and saves a single `.json` file. Phase 1 substrate at `src/polaris_v6/api/bundle.py` serves this from the golden-fixture suite. | Click export → single JSON file downloads; open it in any text editor and verify `contract_version: "1.0"`, `evidence_pool`, `verified_sentences`, and `family_segregation_passed` fields are present. |

## Prerequisites

What the orchestrator pre-stages (in repo, ready to use):
- 17-input adversarial test corpus in `docs/walkthroughs/1.8/test_inputs.md`
- Recording template at `docs/walkthroughs/1.8/recording_template.md`

What the evaluator brings (Phase-1-PARTIAL — fixture authoring deferred):
- Fresh browser session (no cached state)
- **One small text-PDF (≤ 5 MB)** of your choice for Block C input #11. Any
  ordinary text PDF works (a paper, a press release, a policy brief). Image-
  only PDFs are tested separately in input #13. **No fixture PDF is
  committed in `tests/v6/fixtures/walkthrough/`** — Phase 1 walkthrough is
  evaluator-supplied for upload content, by design.

What the build operator pre-stages (must be online before walkthrough):
- POLARIS backend reachable (locally OR on dev cluster — task 0.3 gate)

## Phase 1 known gaps (in scope to observe, out of scope to ship in this walkthrough)

These are deferred-with-explicit-disclosure per Plan v13 §F (no SILENT fallback):

- **Live LLM cluster**: §G #3 pending. Backend may run with stub LLM responses
  for Block A (template suggestion) and Block B (BPEI ambiguity); the LLM-
  augmented disambiguation is fully exercised only after cluster online.
- **F3 upload-as-evidence loop** (parser → chunking → tier T7 assignment →
  cite uploaded doc in next query): Phase-1-END behavior, **not** Phase-1-PARTIAL.
  HEAD substrate provides the `/upload` endpoint contract (returns `document_id`)
  but the parse + chunk + cite-back loop requires §G #3 cluster + Phase 1+
  parser wiring. Walkthrough Block C exercises endpoint contract only; do not
  fail on missing chunk listing or missing T7-tagged citation in subsequent
  query.
- **Walkthrough fixture PDFs** (`tests/v6/fixtures/walkthrough/1.8_*.pdf`):
  not committed; evaluator brings their own per the prereq above. A future
  task may freeze a small fixture set for repeatable replay.
- **OCR for image-only PDFs** (input #13): may emit "OCR pending"; this is
  Phase 1+ work and acceptable to flag rather than fail.
- **Audit bundle redaction for paywalled spans** (input #17): IP counsel
  opinion pending per blockers.md §5. Bundle may emit `[REDACTED — counsel
  review pending]` placeholder; observe it, not fail it.

## What I (the evaluator) need to do

1. **Open the recording app** of your choice (Loom, OBS, QuickTime, etc.)
2. **Open `docs/walkthroughs/1.8/test_inputs.md`** — your 17-input script
3. **Start recording** (full screen + audio narration if you can)
4. **Walk through every input** in the script, narrate observations
5. **Stop recording** and save the file
6. **Save the recording to `.private/walkthroughs/1.8_<your_initials>_<YYYY-MM-DD>.mp4`** (gitignored — your machine only)
7. **Generate a GPG-signed attestation file** (the autoloop will guide you through this) at `outputs/audits/attestations/1.8_<your_name>.md.asc`
8. **Optional**: attach short notes to `outputs/audits/walkthroughs/1.8_findings.md` if anything stuck out

## What POLARIS is supposed to do (so you know when something's broken)

- F1 template browse: <200ms suggestion latency
- F2 BPEI ambiguity: modal appears within 1s of submit; offers 2-5 candidate meanings; refusing to disambiguate is not allowed (POLARIS must ask, not silently guess)
- F3 upload (endpoint contract only — Phase-1-PARTIAL): PDF up to **25 MB** accepts (`src/polaris_v6/api/upload.py` `MAX_BYTES = 25 * 1024 * 1024`); successful upload returns **HTTP 201 Created** with an `UploadResponse` body containing `document_id`, `filename`, `bytes`, `sha256`, `classification`, `parse_status`, `chunk_preview`. Parser + full chunk listing + tier-T7 assignment + cite-uploaded-doc-in-next-query are **Phase-1-END**, deferred per known-gaps. (HEAD ships only the endpoint contract; `parse_status` may be `"queued"` and `chunk_preview` may be empty.)
- F15 export: JSON downloads within 5s; the file is a single `EvidenceContract v1.0` artifact served by `GET /runs/{run_id}/bundle` (see `src/polaris_v6/api/bundle.py`, `response_model=EvidenceContract`). All 15 required top-level fields per `src/polaris_v6/schemas/evidence_contract.py` lines 86-105 must be present: `contract_version` (literal `"1.0"`), `run_id`, `template`, `question`, `queued_at`, `finished_at`, `pipeline_status`, `evidence_pool`, `verified_sentences`, `frame_coverage`, `contradictions`, `cost_usd`, `generator_model`, `verifier_model`, `family_segregation_passed`. **No ZIP / no `report.md` / no `evidence/` folder** — those are Phase-1-END artifacts not yet shipped.

## What to specifically NOT trust

- The phrase "[#ev:...]" appearing in body text but not clickable → broken citation
- Any silent fallback (e.g., "I couldn't disambiguate so here's a generic answer") → BPEI failure
- Any answer that reads like ChatGPT (no citations, no tier markers) → missing strict_verify gate
- Any error message that's just a stack trace (vs. user-friendly explanation) → UX gap

## How long it'll take

~25-35 min for one full pass of the 17-input corpus. Budget 45 min.

## Compensation (per Plan v13 §G #7)

If you're a paid evaluator: $300/session. If you're a friend: thank-you note.

## Questions during walkthrough

If something doesn't work as described → that's a finding, write it down. If something is unclear about WHAT to test → ping the user (`msn`); they'll iterate the briefing.

## Success criterion

Walkthrough is "passed" when:
1. Recording saved
2. GPG-signed attestation written
3. No P0 findings (broken core feature)

P1/P2/P3 findings are acceptable; orchestrator will land fixes in Phase 2 buffer.
