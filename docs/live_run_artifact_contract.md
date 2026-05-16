# Live-run artifact contract

**Issue:** I-rdy-007 (#503) — Phase 3.4 of `state/carney_demo_execution_plan_2026_05_15.md`.
**Status:** specification. **Implementation:** I-rdy-008 (#504).
**Depends on:** I-rdy-003 (`docs/polaris_locked_scope.md`).

---

## 1. Purpose & scope

The POLARIS v6 rich product surfaces — the report **inspector**, **charts**,
**follow-up**, **compare**, **pin replay**, **memory**, and **bundle** — were each
built against *golden test fixtures*. Per the readiness gap register
(`state/carney_readiness_gaps_2026_05_15.md`, P0 #3) and the I-rdy-002 verification
(`.codex/I-rdy-002/verification_findings.md`), four of these endpoints resolve a run
through the hard-coded `_GOLDEN_RUN_INDEX` dict in
`src/polaris_v6/api/bundle.py` — so a **real completed run ID always returns 404**.

This document is the **contract** that maps the artifacts a completed run produces
to what each surface consumes. It is the specification I-rdy-008 (#504) implements.

**This is a specification only.** It changes no endpoint code. The executable
`artifact_dir → EvidenceContract` adapter and the endpoint rewiring are I-rdy-008's
scope (execution plan Phase 3.5: "Live-run → rich UI"). Codex brief review
(`.codex/I-rdy-007/codex_brief_verdict.txt`) ratified this spec/wiring split.

---

## 2. The resolution chain

Every run-keyed surface resolves a `run_id` to artifacts through one chain:

```
run_id
  │
  ▼
run_store.get_run(run_id)            src/polaris_v6/queue/run_store.py
  │   → RunStatusResponse | None
  ▼
RunStatusResponse.artifact_dir       absolute path to the pipeline-A artifact dir
  │
  ▼
load_audit_ir(artifact_dir)          src/polaris_graph/audit_ir/loader.py
  │   → AuditIR  (canonical IR)
  ▼
adapter: artifact_dir → EvidenceContract     ← NEW component, built by I-rdy-008
```

`run_store` is a SQLite table (`state/v6_runs.sqlite`, override `POLARIS_V6_RUN_DB`).
`get_run(run_id)` returns a `RunStatusResponse` (`src/polaris_v6/schemas/run_status.py`)
or `None`. The fields that matter to this contract:

| Field | Role in the contract |
|---|---|
| `run_id` | the v6 API-facing run identifier (the path parameter) |
| `lifecycle_status` | `queued` \| `in_progress` \| `completed` \| `failed` — gates resolution |
| `pipeline_status` | `success` \| `abort_*` \| `error_*` — pipeline-A verdict (CLAUDE.md §9.3) |
| `artifact_dir` | absolute path to the canonical artifact directory; nullable |
| `manifest_run_id` | pipeline-A's internal run id (distinct from the API `run_id`) |
| `cost_usd`, `queued_at`, `finished_at`, `template`, `question`, `decision_id` | passthrough metadata |

**Structural fact.** There is no `artifact_dir → EvidenceContract` converter today.
`src/polaris_v6/api/artifact_to_slice_chain.py:build_slice_chain()` produces the
slice-chain triple `(ScopeDecision, EvidencePool, VerifiedReport)` — used by the
already-wired `bundle.tar.gz` path — **not** an `EvidenceContract`. The fixture-bound
endpoints obtain an `EvidenceContract` only via
`EvidenceContract.model_validate(<golden fixture JSON>)`. The contract therefore has
two parts: the **resolver** (§2, above — already exists) and the **adapter** (§4 —
new, built by I-rdy-008).

---

## 3. Canonical `artifact_dir` file set

`load_audit_ir()` (`src/polaris_graph/audit_ir/loader.py`) reads:

| File | Required | Feeds |
|---|---|---|
| `manifest.json` | yes | run metadata, `evaluator_gate`, `release_allowed`, `corpus`, `frame_coverage_report`, `retrieval` |
| `report.md` | yes | rendered markdown report (`AuditIR.report_md`) |
| `bibliography.json` | yes | `[N] → evidence_id → {tier, url, statement}` mapping |
| `contradictions.json` | yes | tier-labeled disagreement clusters |
| `verification_details.json` | yes | per-section kept/dropped sentences + `[#ev:…]` span tokens |
| `evidence_pool.json` | **yes for this contract** | source bodies — **required** to extract `SourceSpan.span_text` (see §4). `build_slice_chain` treats it as optional for tarball assembly, but the `EvidenceContract` adapter cannot populate verbatim span text without it. |
| `evaluator_rule_checks.json` | optional | `generator_model`, `evaluator_model`, rule-check trail |
| `qwen_judge_output.json` | optional | judge model + token counts |
| `protocol.json` | optional | research-question protocol, expected tier bands |
| `corpus_approval.json` | optional | corpus approval gate decision |

`load_audit_ir()` fails loud (`FileNotFoundError` / `AuditIRSchemaError`) on a
missing or malformed *required* file. `evaluator_rule_checks.json` +
`qwen_judge_output.json` must be present together or both absent.

---

## 4. The adapter — `artifact_dir → EvidenceContract`

I-rdy-008 builds a function (proposed `live_run_to_evidence_contract(run_id) ->
EvidenceContract`, or `artifact_dir`-keyed) reusing `load_audit_ir()` and the
bibliography/token shaping `build_slice_chain()` already demonstrates.

Target type: `EvidenceContract` v1.0 (`src/polaris_v6/schemas/evidence_contract.py`).
Field-by-field source map:

| `EvidenceContract` field | Source |
|---|---|
| `contract_version` | constant `"1.0"` |
| `run_id` | `RunStatusResponse.run_id` (the API run id) |
| `template` | `RunStatusResponse.template` |
| `question` | `RunStatusResponse.question` (≡ `AuditIR.manifest.question`) |
| `queued_at` | `RunStatusResponse.queued_at` |
| `finished_at` | `RunStatusResponse.finished_at` |
| `pipeline_status` | `RunStatusResponse.pipeline_status` |
| `cost_usd` | `RunStatusResponse.cost_usd` ?? `AuditIR.manifest.cost_usd` |
| `generator_model` | `AuditIR.model_provenance.generator_model` |
| `verifier_model` | `AuditIR.model_provenance.evaluator_model` |
| `family_segregation_passed` | derived: `model_provenance.generator_family != model_provenance.evaluator_family` |
| `verified_sentences[]` | `AuditIR.verified_report.sections[].sentences[]` (one `VerifiedSentence` each) |
| → `section_id` | `_slugify(ReportSentence.section)` |
| → `sentence_text` | `ReportSentence.text` |
| → `provenance_tokens` | `[f"[#ev:{t.evidence_id}:{t.start}-{t.end}]" for t in ReportSentence.tokens]` |
| → `verifier_local_pass`, `verifier_global_pass` | **adapter decision (see below)** — `AuditIR.ReportSentence` exposes a single `is_verified`; `EvidenceContract.VerifiedSentence` splits local/global |
| → `drop_reason` | `ReportSentence.failure_reasons[0]` normalized; `None` when `is_verified` |
| `evidence_pool[]` (`SourceSpan`) | one per distinct cited `EvidenceSpanToken` across all sentences |
| → `evidence_id`, `span_start`, `span_end` | the `EvidenceSpanToken` |
| → `source_url`, `source_tier` | `AuditIR.get_bibliography_by_evidence_id(evidence_id)` → `.url`, `.tier` |
| → `span_text` | the source body in `evidence_pool.json` for `evidence_id`, sliced `[span_start:span_end]` |
| `frame_coverage[]` (`FrameCoverage`) | **adapter decision** — `AuditIR.frame_coverage.entries` are per-*entity* (`FrameCoverageEntry`); `EvidenceContract.FrameCoverage` is per-*frame*. The adapter aggregates entries by frame/section into `{frame_id, frame_name, sources_assigned, coverage_percent}` |
| `contradictions[]` (`ContradictionRecord`) | `AuditIR.contradictions` clusters → `{contradiction_id, section_id, claim_a, claim_b, evidence_a, evidence_b, resolution}` |

**Two adapter decisions I-rdy-008 must resolve and test (flagged here, not pre-decided):**

1. **local/global verifier split.** `AuditIR` has one `is_verified` bool;
   `EvidenceContract.VerifiedSentence` wants `verifier_local_pass` +
   `verifier_global_pass`. Either set both to `is_verified`, or read
   `verification_details.json` raw for the finer Local/Global split if the
   pipeline-A artifact records it. I-rdy-008 picks one and documents it.
2. **frame-coverage aggregation.** `FrameCoverageEntry` (per entity, with `status`)
   must roll up to `FrameCoverage` (per frame, with `coverage_percent`). I-rdy-008
   defines the rollup (group by `section`/`slot_id`; `coverage_percent` from the
   pass/partial/gap counts).

`tier` normalization: pipeline-A tiers above T3 / `UNKNOWN` collapse to `T3`
(consistent with `artifact_to_slice_chain._normalize_tier`); `SourceSpan.source_tier`
is the `Literal["T1","T2","T3"]`.

---

## 5. Per-surface consumption — three patterns

The seven surfaces named in the issue are **three** distinct integration patterns.

### Pattern A — `EvidenceContract` consumers, currently fixture-bound (the bug)

| Surface | Endpoint | Consumes | I-rdy-008 fix |
|---|---|---|---|
| **bundle (JSON)** / **inspector** | `GET /runs/{run_id}/bundle` | the whole `EvidenceContract` (the inspector UI is the frontend consumer of this JSON — there is no separate inspector endpoint) | replace `_GOLDEN_RUN_INDEX.get()` + fixture load with the §4 adapter |
| **charts** | `GET /runs/{run_id}/charts/{chart_type}` | `EvidenceContract` → `chart_from_bundle()` | same |
| **follow-up** | `POST /runs/{run_id}/followup` | `EvidenceContract` → `answer_followup(parent=…)` | same |
| **compare** | `GET /runs/{left}/compare/{right}` | two `EvidenceContract`s → `compare_reports()` | same, for both run IDs |

All four import `_GOLDEN_RUN_INDEX` / `_FIXTURE_DIR` from `bundle.py` and 404 on any
non-golden `run_id`. After I-rdy-008 each calls the §2 resolver + §4 adapter; the
golden fixtures remain valid as *test* inputs only.

### Pattern B — already live-wired (reference implementation)

`GET /runs/{run_id}/bundle.tar.gz` (`bundle.py:68-152`, shipped by I-arch-001d)
already resolves a live run: `run_store.get_run()` → gates → `build_slice_chain()` →
`post_audit_bundle()`. Pattern A's rewiring mirrors this control flow and **reuses
its error-state matrix verbatim** (§6). Pattern B needs no change.

### Pattern C — not artifact-symmetric

- **memory** (`/workspaces/{workspace_id}/memory*`, `src/polaris_v6/api/memory.py`)
  is **workspace-keyed, not run-keyed**. It stores `MemoryEntry` records in an
  in-memory `WorkspaceMemoryStore`; runs appear only as `derived_from_run_ids`
  provenance pointers. Memory does **not** consume run artifacts the way Pattern A
  does. Its real gap — the in-memory store is non-durable and not workspace-isolated
  with cited recall — is a **separate issue, I-rdy-012 (#508)**. This contract only
  requires that `derived_from_run_ids` reference real `run_store` run IDs.
- **pin replay** has **no v6 backend route**. `web/app/pin_replay/` renders a
  frontend `DEMO_PIN_REGISTRY`; the typed pin source that exists today is the
  pipeline-side `ModelPin` (`src/polaris_graph/audit_ir/model_pin.py`) and the
  frontend `PinSnapshot`. This contract specifies the *intended* resolution —
  `run_id → run_store → pin records` — but the `GET /runs/{run_id}/pins/{date}`
  route and its response schema do not exist and are **owned by I-rdy-008**.

---

## 6. Error-state matrix

I-rdy-008 applies the matrix `bundle.tar.gz` already enforces (`bundle.py:89-152`)
to every Pattern-A surface. The contract fixes these as the canonical responses:

| Condition | Status | Body |
|---|---|---|
| `run_store.get_run()` → `None` | **404** | `run not found` |
| `lifecycle_status != "completed"` | **404** | `run not completed: lifecycle_status=<…>` |
| `pipeline_status` starts with `abort_` | **422** | `run aborted: pipeline_status=<…>`, `bundleable: false` |
| `manifest.release_allowed` is `false` | **422** | `run release-blocked`, `release_allowed: false` |
| sovereignty cascade empties the report (`SovereigntyFilterEmptiedReportError`) | **422** | the exception message |
| `artifact_dir` null, or not a directory on disk | **404** | `run has no artifact_dir recorded` / `artifact_dir does not exist` |
| `artifact_dir` missing a required canonical file | **404** | `artifact_dir incomplete: <file>` |
| GPG signer unset (`bundle.tar.gz` only) | **503** | `signer not configured` |

A surface that does not itself need the bundle (charts/follow-up/compare/inspector)
still applies rows 1-7; only `bundle.tar.gz` has the 503 signer row.

### `abort_*` / `partial_*` / release-blocked

- **`abort_*`** (`abort_scope_rejected`, `abort_corpus_inadequate`,
  `abort_corpus_approval_denied`, `abort_no_verified_sections`): the run completed
  operationally but a pipeline-A gate halted it. No shippable `EvidenceContract` —
  **422** with the typed `pipeline_status`.
- **`partial_*`** (e.g. `partial_qwen_advisory`): the pipeline produced kept content
  but a degradation is recorded. `build_slice_chain` collapses `partial_*` to verdict
  `success`; the gate that actually blocks shipping is **`manifest.release_allowed`**.
  A `partial_*` run with `release_allowed: true` is serviceable (the
  `EvidenceContract.pipeline_status` carries the `partial_*` string so the UI can
  badge it); a `partial_*` run with `release_allowed: false` is **422**.
- **`error_*`**: operational failure — **404**/**422** as the matrix dictates; never
  a synthetic empty `EvidenceContract`.

No surface ever returns a fabricated or empty `EvidenceContract` for a non-shippable
run (CLAUDE.md LAW II — fail loud, no silent fallback).

---

## 7. Schema surface

The contract's formal typed surface is the set of **existing** Pydantic / dataclass
schemas — no new schema file is introduced (Codex brief review ruled
`pin-existing-ok`):

- `RunStatusResponse` — `src/polaris_v6/schemas/run_status.py`
- `AuditIR` (+ `BibliographyEntry`, `ReportSentence`, `EvidenceSpanToken`,
  `ContradictionCluster`, `FrameCoverageReport`, `RunManifest`, `ModelProvenance`) —
  `src/polaris_graph/audit_ir/loader.py`
- `EvidenceContract` (+ `SourceSpan`, `VerifiedSentence`, `FrameCoverage`,
  `ContradictionRecord`) — `src/polaris_v6/schemas/evidence_contract.py`

I-rdy-008's adapter is bound by these. If I-rdy-008 finds a new typed
resolver-result model genuinely reduces ambiguity, it may add one small file under
`src/polaris_v6/schemas/` — but the contract does not require it.

---

## 8. Acceptance for I-rdy-008 (#504)

When I-rdy-008 implements this contract:

1. `GET /runs/{id}/bundle`, `/charts/{type}`, `/followup`, `/compare/{r}` all accept
   a real completed `run_id` and return data derived from its `artifact_dir`.
2. The error-state matrix (§6) holds on every surface.
3. The golden fixtures remain valid test inputs (the contract does not delete them).
4. `bundle.tar.gz` (Pattern B) and memory (Pattern C) behavior is unchanged.
5. The two §4 adapter decisions are made, documented, and tested against a real run.
