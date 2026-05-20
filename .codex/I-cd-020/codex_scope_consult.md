# I-cd-020 (#630) — scope consult (rescope candidate)

## Operator directive 2026-05-20

"For all decision, ask Codex to decide based on highest quality impact."

## Reality discovered while drafting the brief

The acceptance of #630/#544 says "real run → EvidenceContract JSON conforming to I-A-02b schema → renders in /inspector/[runId]." Grep into actual pipeline-A artifacts reveals **data-shape gaps** between what pipeline-A produces today and what `EvidenceContract` (v1.0) requires.

### What pipeline-A actually writes

For a completed real run at `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/`:

- `evidence_pool.json` is a `list[dict]` with keys: `direct_quote`, `evidence_id`, `full_content_length`, `source`, `source_url`, `statement`, `tier` (T1-T7).
- `verification_details.json` has `{drop_reason_counts, sections, totals}` — sections carry `total_kept`, `total_dropped` **counters only** (NO `sentence_text`, NO `provenance_tokens`, NO per-sentence pass/fail).
- `manifest.json` carries `generator.{outline_sections, sections_kept, sentences_verified, sentences_dropped}` and `frame_coverage_report` but no per-evidence-span offsets.

### What `EvidenceContract` v1.0 (`src/polaris_v6/schemas/evidence_contract.py`) requires

- `SourceSpan` REQUIRES: `evidence_id`, `source_url`, `source_tier in {T1, T2, T3}`, `span_start: int`, `span_end: int`, `span_text: str` (min_length=1).
- `VerifiedSentence` REQUIRES: `section_id`, `sentence_text`, `provenance_tokens: list[str]`, `verifier_local_pass: bool`, `verifier_global_pass: bool`.

### The gap

| EvidenceContract field | Available in pipeline-A artifact? |
|---|---|
| `SourceSpan.evidence_id` | YES (`evidence_id`) |
| `SourceSpan.source_url` | YES |
| `SourceSpan.source_tier` | PARTIAL — pipeline-A writes T1-T7; SourceSpan accepts only T1/T2/T3 (mapping needed) |
| `SourceSpan.span_start` / `span_end` | **NO** — pipeline-A does not record char offsets into source body |
| `SourceSpan.span_text` | YES (`direct_quote`) |
| `VerifiedSentence.section_id` | PARTIAL — section title exists but no `section_id` |
| `VerifiedSentence.sentence_text` | **NO** — verification_details.json only has counters |
| `VerifiedSentence.provenance_tokens` | **NO** — counters only |
| `VerifiedSentence.verifier_local_pass` / `verifier_global_pass` | **NO** — counters only |
| `frame_coverage` | YES (`manifest.frame_coverage_report.entries`) |
| `pipeline_status`, `run_id`, `question`, etc. | YES (from manifest + run_store) |

Pipeline-A's `verification_details.json` writes section-level counts, not sentence-level records. The sentence-level data (text + provenance tokens + per-sentence pass/fail) lives in pipeline-A's `report.md` (in-line `[#ev:...]` tokens) but is NOT exported as JSON.

### Companion data path that DOES work for real runs

`GET /runs/{run_id}/bundle.tar.gz` is already wired via `build_slice_chain` (I-arch-001d, in production). It produces:

- `manifest.yaml` (BundleManifest v1.0 — locked I-cd-012)
- `scope_decision.json` (ScopeDecision)
- `evidence_pool.json` (slice-chain `EvidencePool`)
- `verified_report.json` (slice-chain `SliceChainVerifiedReport`)
- `reasoning_trace.jsonl`
- `metadata.json`
- `sources/` directory
- `manifest.yaml.asc` (GPG signature)

These are **different Pydantic shapes** from EvidenceContract — they are the v1.0 SCHEMA the I-A-02b fixture froze and the Inspector frontend (`inspector_bundle_loader.ts`) consumes today. They populate from real-run artifact-dir data without needing span offsets.

## Four paths

### Option A — implement EvidenceContract for real runs WITH a pipeline-A capability extension

Extend pipeline-A to write per-sentence provenance + per-evidence-span offsets into JSON artifacts. Then `evidence_contract_builder.py` reads them and produces a full EvidenceContract.

Pros: completes the original I-A-02b contract.

Cons: pipeline-A is a ~1500-line linear async function; extending it to emit per-sentence provenance JSON is a multi-PR refactor (~600-1000 LOC). Over halt. Risk of breaking the existing strict_verify + report.md generation. Not aligned with `state/polaris_restart/issue_breakdown.md` granularity.

### Option B — implement EvidenceContract for real runs with DEGRADED fields (fabrication risk)

Synthesize `span_start=0, span_end=len(direct_quote)`. Synthesize `sentence_text=null` or extract from report.md by regex. Synthesize `verifier_local_pass = (drop_reason is None)`. Map T4-T7 → "T3" (lowest admissible tier in the contract).

Pros: ships a route that returns EvidenceContract-shaped JSON.

Cons: span offsets are not real — they're fabricated. The whole point of EvidenceContract is **verifiable provenance**. Fabricating offsets violates LAW II (no fake working). This is the clinical-safety pattern audit ban — exactly what CLAUDE.md §-1.1 forbids.

### Option C — rescope #630 to serve the slice-chain bundle JSON (NOT EvidenceContract)

`GET /runs/{run_id}/bundle` for real runs returns the slice-chain triple (ScopeDecision + EvidencePool + SliceChainVerifiedReport) wrapped as a single JSON object — the SAME shape produced by `build_slice_chain` and stored in `bundle.tar.gz`. The golden-fixture path keeps EvidenceContract for backwards-compat (or also migrates).

Pros: works against real pipeline-A artifacts today. No data fabrication. Inspector frontend (Seq 21 / #631) consumes the same shape. The "bundle conforming to the I-A-02b schema" acceptance is met because I-A-02b froze the slice-chain BundleManifest v1.0, not EvidenceContract v1.0.

Cons: deprecates / dual-mode-s the `/bundle` route's `response_model=EvidenceContract`. Two parallel typed contracts (EvidenceContract for fixtures, BundleManifest+slice-chain for real runs) creates schema confusion.

### Option D — close #630 as superseded by the existing `bundle.tar.gz` path; document the EvidenceContract gap as a follow-up Issue

The signed `bundle.tar.gz` path ALREADY satisfies "real run → signed bundle conforming to v1.0 schema → Inspector renders it" (the I-A-02b schema froze BundleManifest v1.0, not EvidenceContract). The Inspector consumes the same files. So #630 is mostly already done by I-arch-001d + I-cd-013a + I-cd-012.

The EvidenceContract data-gap (pipeline-A doesn't write per-sentence provenance JSON) is a real, separate, much-bigger work item that should be a new Issue.

Concrete delta this Issue would ship:
- Update `GET /runs/{run_id}/bundle` to redirect to `/runs/{run_id}/bundle.tar.gz` for non-golden runs (or 308/410 with documentation).
- Document the EvidenceContract data-gap as a new Issue `I-cd-020-followup`.
- Frontend Seq 21 / #631 (Offline fallback) already consumes the bundle.tar.gz path.

Pros: honest about what already works vs what doesn't. No fabrication. Minimal LOC.

Cons: the operator's "real-run bundle" expectation may have been EvidenceContract specifically; this rescope substitutes a different (but also frozen, v1.0) contract.

## Question

**Rank A vs B vs C vs D by highest quality impact, using the rubric**:

- (a) correctness / clinical-safety risk (NO fabrication of provenance fields)
- (b) PR-cap discipline (200-LOC halt)
- (c) data-honesty per CLAUDE.md §-1.1 (line-by-line audit standard) and LAW II (no fake working)
- (d) downstream-issue dependency: Seq 21 / #631 Inspector offline fallback consumes WHICH shape today?
- (e) the I-A-02b schema freeze actually locked BundleManifest v1.0 (I-cd-012), not EvidenceContract — what does "conforming to the I-A-02b schema" mean against current state?

Return picked option + 1-2 sentence rationale. If picking C, confirm the `/bundle` response_model change is acceptable. If picking D, confirm acceptance criterion is met by existing `bundle.tar.gz` + Inspector frontend wiring.
