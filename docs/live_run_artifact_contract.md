# Live-run artifact contract

**Issue:** I-rdy-007 (#503), Phase 3.4 of the Carney readiness chain.
**Status:** definition. This document + `docs/schemas/live_run_artifact_contract.schema.json`
define the contract; **wiring** the rich surfaces to consume it is I-rdy-008
(#504). I-rdy-010 (#506) and I-rdy-012 (#508) also build on this contract.

**Purpose:** the single source of truth for *what a completed v6 run exposes*
and *what each rich UI surface consumes from it*. It is the root fix for the
fixture-bound rich surfaces — today most rich surfaces only render golden
fixtures because the run→surface contract was "the code", never written down.

This contract is **grounded in the running code**, not in older docs.
`docs/pipeline_audit_context/03_json_contracts.md` is the earlier prose
description; it is **stale** on the status taxonomy (it lists 10 values; the
code defines 14 — see §3) and is superseded by this document + the JSON schema.

---

## 1. The producer — a completed v6 run

A run is created via `POST /runs` (`src/polaris_v6/api/runs.py`) and tracked in
the v6 run store (`src/polaris_v6/queue/run_store.py`, SQLite `runs` table).
`GET /runs/{run_id}` returns `RunStatusResponse`
(`src/polaris_v6/schemas/run_status.py`):

| Field | Meaning |
|---|---|
| `run_id` | server-assigned UUID hex |
| `lifecycle_status` | operational: `queued` → `in_progress` → `completed` \| `failed` \| `cancelled` |
| `pipeline_status` | pipeline-A manifest verdict (§3); `null` until a terminal pipeline state |
| `template`, `question` | run inputs |
| `queued_at` / `started_at` / `finished_at` | ISO-8601 UTC |
| `query_slug`, `manifest_run_id` | UUID ↔ slug ↔ manifest-id mapping (I-arch-001a) |
| `artifact_dir` | filesystem path to the run's artifact directory — **the join key to everything below** |
| `cost_usd`, `decision_id`, `result_json`, `error_json` | run accounting / telemetry |
| `status` | deprecated computed alias of `lifecycle_status` (tests/v6 backcompat) |

A **completed** run (`lifecycle_status == "completed"`) has a populated
`artifact_dir`. That directory is the contract surface.

## 2. The artifact directory

`artifact_dir` holds the pipeline-A artifact set. Files split into three
classes by how `src/polaris_graph/audit_ir/loader.py` `load_audit_ir()`
treats them:

### 2.1 Required for AuditIR (fail-loud if missing)

`load_audit_ir()` raises `FileNotFoundError` / `AuditIRSchemaError` if any of
these is absent or malformed:

| File | Carries |
|---|---|
| `manifest.json` | run verdict + adequacy/corpus/generator/evaluator/frame-coverage/retrieval blocks |
| `report.md` | rendered markdown report with `[N]` inline citations (2 shapes — §4) |
| `bibliography.json` | the `[N]` → `evidence_id` → source mapping |
| `contradictions.json` | tier-labelled disagreement clusters (≥2 claims each) |
| `verification_details.json` | per-section kept/dropped sentences + `[#ev:id:start-end]` span tokens |

### 2.2 Optional provenance (loaded when present)

| File | Carries | Rule |
|---|---|---|
| `evaluator_rule_checks.json` | generator/evaluator family+model, per-rule pass/fail | **both-or-neither** with `judge_output.json` — `load_audit_ir()` raises if exactly one is present |
| `judge_output.json` | judge model, parse-ok, I/O token counts (legacy fallback name: `qwen_judge_output.json`) | pairs with the above |
| `protocol.json` | scope template — research question, `created_at`, `expected_tier_distribution` | drives Inspector View 5 expected-vs-actual tier bands |
| `corpus_approval.json` | corpus-approval gate decision + note | absent on auto-approved runs |
| `evidence_pool.json` / `live_corpus_dump.json` | per-evidence detail (id, url, tier, statement, quote) | the bridge's `EvidencePool` source |
| `reasoning_trace.jsonl` | V4-Pro chain-of-thought trace (I-gen-004) | included in the live tar.gz bundle when present |
| `run_log.txt` | human-readable `[tag]`-prefixed run log | not consumed by AuditIR |

### 2.3 Status-conditional availability (Codex brief P2-001)

The §2.1 "required" set is required **for a run that is expected to resolve
through `load_audit_ir()`** — i.e. `success` / `partial_*` runs.
**`abort_*` and `error_*` runs** legitimately lack `verification_details.json`
and `evidence_pool.json` (an abort happens before per-sentence verification, or
before generation entirely). A consumer MUST branch on `pipeline_status`
(§3) BEFORE attempting `load_audit_ir()`; an `abort_*` artifact dir is a
pipeline-verdict artifact, not an AuditIR-loadable run. The JSON schema marks
verification/evidence fields required only under non-abort status.

## 3. `manifest.status` / `pipeline_status` — the 14-value taxonomy

The authoritative set is the code: `PipelineStatus` in
`src/polaris_v6/schemas/run_status.py` and `UNIFIED_STATUS_VALUES` in
`scripts/run_honest_sweep_r3.py` (they agree). It is the **single
authoritative run verdict** — consumers classify a run by this, never by
`report.md` existence.

| Class | Values |
|---|---|
| success | `success` |
| partial — report produced, degraded signal | `partial_thin_corpus`, `partial_incomplete_corpus`, `partial_rule_check_warnings`, `partial_outline_fallback`, `partial_evaluator_advisory`, `partial_qwen_advisory` (legacy alias) |
| abort — pipeline refused to produce a report | `abort_scope_rejected`, `abort_no_sources`, `abort_corpus_inadequate`, `abort_corpus_approval_denied`, `abort_no_verified_sections`, `abort_evaluator_critical` |
| error — unhandled exception | `error_unexpected` |

`docs/pipeline_audit_context/03_json_contracts.md` lists only 10 of these and
is **stale** — it predates `partial_outline_fallback`,
`partial_evaluator_advisory`, `partial_qwen_advisory`, and
`abort_evaluator_critical`.

**Pre-taxonomy artifacts (grounding finding):** some legacy artifact dirs
(observed: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/`)
have a `manifest.json` with NO top-level `status` field at all — they predate
the unified taxonomy. These are **not contract-conformant**: `load_audit_ir()`
rejects them (`_parse_manifest` requires `status`), and the JSON schema marks
`status` required. A live v6 run always writes `status`; a consumer that
encounters a `status`-less manifest should treat the run as un-renderable, not
attempt to guess.

## 4. `report.md` — two shapes

- **`success` / `partial_*`**: an actual research report — `## <section>`
  prose with numbered `[N]` citations, then `## Limitations`, `## Methods`,
  `## Bibliography`.
- **`abort_*`**: a pipeline-verdict artifact — `## Pipeline verdict` +
  per-section verdict + suggested next steps. NOT a research report.

Consumers MUST distinguish these by `pipeline_status` (§3), never by
`report.md` existence.

## 5. The canonical IR layer — `AuditIR`

`load_audit_ir(artifact_dir)` → an immutable `AuditIR`
(`src/polaris_graph/audit_ir/loader.py`). The loader docstring states the
design rule (from FINAL_PLAN.md, Claude+Codex agreed): **"The AuditIR is the
single source of truth for the Evidence Inspector and all derivative
renderers"** — the report is a projection, not the source.

`AuditIR` (`ir_schema_version = "1.0.0"`) joins:

| `AuditIR` field | From | Used by |
|---|---|---|
| `manifest: RunManifest` | `manifest.json` | every surface (verdict, cost, counts) |
| `report_md: str` | `report.md` | inspector report pane |
| `bibliography: tuple[BibliographyEntry]` | `bibliography.json` | inspector `[N]`→source, citation hover |
| `verified_report: VerifiedReport` | `verification_details.json` | inspector click-to-inspect (claim_id → sentence → span tokens) |
| `contradictions: tuple[ContradictionCluster]` | `contradictions.json` | contradiction navigation |
| `frame_coverage: FrameCoverageReport` | `manifest.frame_coverage_report` | frame-coverage panel |
| `tier_mix: TierMix` | `manifest.corpus` | source-tier-mix view |
| `model_provenance: ModelProvenance \| None` | `evaluator_rule_checks.json` + `judge_output.json` | methods/provenance bundle, two-family signal |
| `protocol: ProtocolMetadata \| None` | `protocol.json` | expected-vs-actual tier bands |
| `adequacy: AdequacyGate \| None` | `manifest.adequacy` | adequacy-gate detail |
| `corpus_approval: CorpusApprovalGate \| None` | `corpus_approval.json` | approval-gate detail |

`AuditIR` lookup methods (`get_sentence_by_claim_id`,
`get_bibliography_by_num`/`_by_evidence_id`, `get_contradictions_for_evidence`,
`get_frame_coverage_for_entity`, `get_tier_counts`,
`get_evidence_spans_for_claim`) are the resolution API every rich surface
should use. **`claim_id` = `<section>:<kept|dropped>:<idx>`** is the stable
click-to-inspect handle a renderer overlays onto `report.md`.

## 6. Per-consumer mapping

Each rich surface, the v6 API route that serves it, the `AuditIR` it needs,
and its current state. Current-state column is the I-rdy-002 (#498)
verification recorded in `docs/polaris_locked_scope.md` §3.1.

| Surface | v6 API route | Consumes from `AuditIR` | Current state |
|---|---|---|---|
| Inspector (report click-through, F5) | `runs.py` (`GET /runs/{id}`) → `artifact_dir` → `load_audit_ir` | `report_md`, `verified_report`, `bibliography`, `manifest` | components exist; **not on the live `/runs` report** — fixture-bound |
| Citation hover (F6) | inspector data | `bibliography`, `verified_report.tokens` | harness/fixture-bound |
| Frame coverage (F7) | inspector data | `frame_coverage` | harness/fixture-bound |
| Contradiction navigation (F8) | inspector data | `contradictions` | harness/fixture-bound |
| Two-family disagreement (F9) | inspector data | `model_provenance`, `evaluator_gate` | harness/fixture-bound |
| Charts (F10 inline visuals) | `charts.py` | `verified_report`, `contradictions`, `tier_mix` | spec builder/API/tests exist; fixture-bound |
| Follow-up (F11) | `followup.py` | `report_md`, `bibliography`, `verified_report` | backend exists; **disabled on the product run page** |
| Compare (F12) | `compare.py` | two runs' `AuditIR` | backend exists; **no product route** |
| Pin replay (F13) | `pin_replay` route | run-id → pins | page exists; **demo-data-bound** |
| Memory (F14) | `memory.py` | run summary + citations | page+API exist; **in-memory demo store, not durable** |
| Bundle (F15) | `bundle.py` — **two routes** | via `artifact_to_slice_chain` → slice-chain Pydantic | see below |

**Bundle has two distinct routes — #504 must not treat "bundle" as one thing:**
- `GET /runs/{id}/bundle` — still returns golden **EvidenceContract** JSON
  (the I-ecg pre-run contract, *not* the live artifact contract). Fixture-bound.
- `GET /runs/{id}/bundle.tar.gz` — live: `artifact_dir` →
  `artifact_to_slice_chain.py` (`load_audit_ir` → slice-chain `ScopeDecision`/
  `EvidencePool`/`VerifiedReport`) → signed tar.gz. Live-capable.

## 7. The gap list — work for I-rdy-008 (#504)

Every surface above whose current state is not "live" is fixture-bound and
must be wired to a real completed run's `artifact_dir` via `load_audit_ir()`:

1. **Inspector** — render the live `/runs/{id}` report through `AuditIR`, not a
   golden fixture (F5).
2. **Citation hover / frame coverage / contradiction nav / two-family** (F6-F9)
   — same: project from the live run's `AuditIR`.
3. **Charts** (F10) — build Vega specs from the live `AuditIR`.
4. **Follow-up** (F11) — enable on the product run page.
5. **Compare** (F12) — add a product route taking two real run-ids.
6. **Pin replay** (F13) — accept a live `run_id` (also I-rdy-013 / #532).
7. **Memory** (F14) — durable store (also I-rdy-012 / #508).
8. **Bundle** (F15) — migrate `GET /runs/{id}/bundle` off the golden
   EvidenceContract JSON onto the live `artifact_dir` path.

Each consumer MUST: (a) branch on `pipeline_status` before `load_audit_ir()`
(§2.3 — abort/error dirs are not AuditIR-loadable); (b) resolve the run only
through `load_audit_ir()` + the `AuditIR` lookup methods (§5), never by
ad-hoc artifact-file reads.

## 8. Out of scope of this contract

- `web/lib/contracts.ts` — the I-ecg-003 **EvidenceContract** (a *pre-run*
  expected-claims contract). Different artifact, different lifecycle; not
  touched here.
- The SSE event contract (`web/lib/sse_events.ts`) — covers *in-progress*
  run streaming, not *completed*-run artifacts; governed separately (I-rdy-004).
