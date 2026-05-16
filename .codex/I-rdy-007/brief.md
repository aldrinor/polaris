# Codex BRIEF review — I-rdy-007 (#503): live-run artifact contract

**Type:** BRIEF review (acceptance-criteria correctness). Phase 3.4 of the
Carney demo execution plan. iter 1 of 5.

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1. Issue + acceptance

GH #503 (I-rdy-007, Phase 3.4 of `state/carney_demo_execution_plan_2026_05_15.md`):
**define the contract that maps a completed run's artifacts to what the inspector,
charts, follow-up, compare, pin replay, memory, and bundle each consume.** Per the
gap register (`state/carney_readiness_gaps_2026_05_15.md` P0#3) + the I-rdy-002
(#498) verification, this is the **root fix** for the fixture-bound rich surfaces.

Acceptance, verbatim from the issue: **"contract documented + schema'd; Codex APPROVE."**
Depends on: I-rdy-003 (done — `docs/polaris_locked_scope.md`).

**SPEC-ONLY BOUNDARY — Codex please confirm this is the correct scope.** #503 is a
*specification* deliverable: a contract document + schema. The actual wiring (making
the rich endpoints accept a live completed run ID instead of `_GOLDEN_RUN_INDEX`) is
the *next* issue — #504 / I-rdy-008 "Live-run → rich UI" (execution plan Phase 3.5).
This brief proposes #503 changes **no endpoint code** — only docs + at most one small
schema file. If Codex judges the spec/wiring split wrong, say so now (iter 1).

## §2. Grounded current state — full inventory (all files below were read)

**Producer side — what a completed run leaves behind:**

- **`run_store`** (`src/polaris_v6/queue/run_store.py`): SQLite `runs` table at
  `state/v6_runs.sqlite`. `get_run(run_id)` → `RunStatusResponse{run_id, template,
  question, lifecycle_status ∈ [queued|in_progress|completed|failed],
  pipeline_status ∈ [success|abort_*|error_*], queued_at, started_at, finished_at,
  result_json, error_json, query_slug, manifest_run_id, artifact_dir, cost_usd,
  decision_id}`. This is the **run_id → artifact_dir resolver entry point**.
- **`artifact_dir`** — the canonical pipeline-A artifact directory. Per
  `artifact_to_slice_chain.py` docstring its file set is: `manifest.json`,
  `report.md`, `bibliography.json`, `contradictions.json`,
  `verification_details.json`, `evidence_pool.json`.
- **`load_audit_ir(artifact_dir)`** (`polaris_graph/audit_ir/loader.py`) → `AuditIR`
  — `.bibliography[]` (evidence_id, url, tier, statement), `.verified_report.sections[]`
  → `.sentences[]` (text, tokens, is_verified, failure_reasons, section), `.manifest`
  (run_id, cost_usd, status).
- **`build_slice_chain(artifact_dir)`** (`src/polaris_v6/api/artifact_to_slice_chain.py`)
  → `(ScopeDecision, EvidencePool, VerifiedReport)` slice-chain Pydantic triple;
  applies the sovereignty cascade and raises `SovereigntyFilterEmptiedReportError`
  when every section drops.

**Consumed type:** `EvidenceContract` (`src/polaris_v6/schemas/evidence_contract.py`,
`contract_version="1.0"`) — `run_id, template, question, queued_at, finished_at,
pipeline_status, evidence_pool: list[SourceSpan], verified_sentences:
list[VerifiedSentence], frame_coverage: list[FrameCoverage], contradictions:
list[ContradictionRecord], cost_usd, generator_model, verifier_model,
family_segregation_passed`.

**STRUCTURAL FINDING (the crux).** There is **no `artifact_dir → EvidenceContract`
converter today.** `build_slice_chain` yields the slice-chain *triple*, not an
`EvidenceContract`. The rich endpoints obtain an `EvidenceContract` only by
`EvidenceContract.model_validate(<golden fixture JSON>)`. So the contract must
specify **two pieces**: (1) a **resolver** `run_id → run_store.get_run() →
artifact_dir`; (2) an **adapter** `artifact_dir → EvidenceContract` — a NEW
component, which #504 builds, reusing `load_audit_ir` + the bibliography/sentence
shaping `build_slice_chain` already demonstrates.

**Consumer side — the 7 surfaces are 3 patterns, not 7 uniform:**

- **Pattern A — `EvidenceContract` consumers, fixture-bound (the bug):**
  `GET /runs/{id}/bundle` (the JSON inspector data path), `charts.py`
  (`GET /runs/{id}/charts/{type}` → `chart_from_bundle`), `followup.py`
  (`POST /runs/{id}/followup` → `answer_followup`), `compare.py`
  (`GET /runs/{l}/compare/{r}` → `compare_reports`). All four resolve the run via
  `_GOLDEN_RUN_INDEX` (defined `bundle.py:45-53`; charts/followup/compare import it)
  → load a golden fixture → `EvidenceContract.model_validate`. A real run ID always
  404s. **"Inspector" is not a separate endpoint — it is the frontend consumer of
  `/bundle` JSON.**
- **Pattern B — already live-wired (the reference implementation):**
  `GET /runs/{id}/bundle.tar.gz` (`bundle.py:68-152`, shipped by I-arch-001d) already
  does `run_store.get_run(id)` → gates → `build_slice_chain(artifact_dir)` →
  `post_audit_bundle`. The contract **cites** its error-state matrix rather than
  reinventing it: 404 run-not-found · 404 not-completed (`lifecycle_status≠completed`)
  · 422 aborted (`pipeline_status` starts `abort_`) · 422 release-blocked
  (`manifest.release_allowed` False) · 422 `SovereigntyFilterEmptiedReportError` ·
  404 `artifact_dir` missing/not-on-disk · 503 GPG signer unconfigured.
- **Pattern C — not artifact-symmetric:** `memory.py` is **workspace-keyed**
  (`/workspaces/{id}/memory`), backed by the in-memory `WorkspaceMemoryStore`; it
  references runs only as `derived_from_run_ids` provenance pointers. Its
  fixture/durability problem (in-memory, non-durable) is a **separate issue —
  #508 / I-rdy-012**, not this contract. **Pin replay** has **no v6 backend route at
  all** (`web/app/pin_replay/` uses `DEMO_PIN_REGISTRY`); the contract *specifies*
  the `run_id → pins` resolution that #504 builds. The contract must state both of
  these honestly and not pretend memory/pin-replay are symmetric with Pattern A.

## §3. The contract — proposed structure

`docs/live_run_artifact_contract.md` will contain:

1. **Resolution chain** — `run_id → run_store.get_run() → RunStatusResponse →
   artifact_dir`; the pre-conditions every consumer must check
   (`lifecycle_status == completed`; `pipeline_status`).
2. **Canonical `artifact_dir` file set** — the six files above, each with its role
   and producer.
3. **Adapter spec** — `artifact_dir → EvidenceContract`, a field-by-field mapping
   table: every `EvidenceContract` / `SourceSpan` / `VerifiedSentence` /
   `FrameCoverage` / `ContradictionRecord` field ← which artifact file / `AuditIR`
   field. (Field-exact mapping is filled at implementation time after reading
   `loader.py`.) This is the component #504 builds.
4. **Per-surface consumption table** — the 3 patterns; for each Pattern-A surface,
   which `EvidenceContract` fields it reads.
5. **Error-state matrix** — the Pattern-B (bundle.tar.gz) matrix, generalized to
   all surfaces, including explicit `abort_*` / `partial_*` / release-blocked
   behavior (mirror bundle.tar.gz: 422 + typed reason).
6. **Scope notes** — memory (#508) and pin-replay (no route yet) called out as
   asymmetric; the spec/#504-wiring boundary stated.

**"Schema'd":** the contract pins the **existing** schemas (`EvidenceContract`,
`RunStatusResponse`, `AuditIR`) as the typed interface — they already exist and are
the contract's formal surface. The brief proposes **no new schema file** unless a
small typed resolver-result model demonstrably reduces ambiguity for #504; if so it
is ≤1 small file under `src/polaris_v6/schemas/`. **Codex: rule on whether
"schema'd" is satisfied by pinning existing schemas, or demands a new artifact.**

## §4. Deliverable files

- `docs/live_run_artifact_contract.md` — the contract (§3).
- (conditional) ≤1 small schema file IF Codex rules a new typed model is required.
- No endpoint/wiring code (that is #504).

Honest size estimate: 1 markdown doc, ~200-300 lines of prose/tables; 0-1 small
schema file. Well under the 200-LOC code cap (the doc is not code; any schema file
is small).

## §5. GREEN / acceptance criteria

1. `docs/live_run_artifact_contract.md` exists and covers all of §3 (resolution
   chain, artifact file set, adapter field map, per-surface table, error matrix,
   scope notes).
2. Every artifact-file and schema reference in the doc resolves to a real
   file/field in the repo (no invented paths).
3. The 3-pattern grouping is explicit; memory + pin-replay asymmetry stated.
4. The spec-only / #504-wiring boundary is stated.
5. Any new schema file (if Codex requires one) parses (`python -c import` /
   `pydantic` validate).
6. Codex APPROVE on brief + diff.

## §6. Adjacent-file scan — files I have ALSO checked and they're clean / context-only

`src/polaris_v6/api/bundle.py`, `charts.py`, `followup.py`, `compare.py`,
`memory.py`, `runs.py`, `artifact_to_slice_chain.py`; `src/polaris_v6/queue/run_store.py`;
`src/polaris_v6/schemas/evidence_contract.py`, `run_status.py`. Execution plan +
gap register + I-rdy-002 verification_findings read. `polaris_graph/audit_ir/loader.py`
to be read at implementation time for the field-exact adapter mapping.

## §7. Questions for Codex

1. Is the **spec-only** scope correct — #503 = docs + ≤1 schema, all wiring deferred
   to #504? Or should #503 also ship the adapter function?
2. Does pinning the existing `EvidenceContract` / `RunStatusResponse` / `AuditIR`
   schemas satisfy "schema'd", or is a new artifact required?
3. Is the 3-pattern decomposition (A EvidenceContract-consumers / B already-wired
   bundle.tar.gz / C asymmetric memory+pin-replay) accurate and complete?
4. Any P0/P1 execution risk in this plan.

## §8. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
spec_scope_ruling: <spec-only-correct | adapter-belongs-in-503 + reasoning>
schema_ruling: <pin-existing-ok | new-schema-required + reasoning>
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
