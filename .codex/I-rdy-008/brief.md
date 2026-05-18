# Codex BRIEF review — I-rdy-008 / GH #504 slice 1: v6 live-inspector AuditIR resolver

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 This is slice 1 of #504, Option A (operator-delegated, Codex-decided)

#504 (I-rdy-008, Phase 3.5) wires all 7 rich UI surfaces from golden-fixture-
bound to live-run-backed. The operator delegated the architecture choice to
Codex; the Codex consult (`.codex/I-rdy-008/arch_decision_verdict.txt`)
returned **verdict A**: move #504 onto the canonical `run_id → artifact_dir →
load_audit_ir() → AuditIR` path (preserves real tier labels, range-keyed
evidence spans, etc. — vs Option B which keeps the too-narrow `EvidenceContract`).

The consult's **stale correction**, honored here: do NOT wholesale-mount the
existing `src/polaris_graph/audit_ir/inspector_router.py` — in current HEAD it
is far larger than a clean read surface (jobs, workspaces, reviews, operator
dashboards, metrics — non-demo). Slice 1 is a **demo-scoped v6 facade route**
exposing only the completed-run AuditIR read.

The consult's **slice 1** verbatim: "shared backend plumbing — add a v6
live-inspector resolver that accepts UUID `run_id`, reads `run_store`, requires
`lifecycle_status=completed`, rejects abort/error/non-loadable statuses before
`load_audit_ir()`, validates `artifact_dir`, and exposes `GET
/api/inspector/runs/{run_id}` as AuditIR JSON ... keep under 200 LOC by not
touching the 805-line frontend yet." This brief implements exactly that.

## 0.2 Iter-1 findings folded in

- **P1** — the loadable-run test must NOT depend on `outputs/honest_sweep_r3/...`:
  `outputs/*` is gitignored, so `verification_details.json` etc. are absent on
  a clean CI checkout. Fixed: the test builds a complete minimal artifact_dir
  under `tmp_path` (§4).
- **P2** — the route's path parameter is `run_id: str` passed verbatim to
  `run_store.get_run()` (NO `UUID` typing — `create_run` stores `uuid4().hex`,
  unhyphenated; a `UUID`-typed param + `str()` would mismatch the stored key).
- **P2** — the route tests set the run-store DB env var to the seeded temp DB
  before constructing the `TestClient` (else the route reads the real
  `state/v6_runs.sqlite`).
- **P2** — `json.JSONDecodeError` is added to the caught loader-error set →
  422 (malformed artifact JSON must fail loud, not 500-escape).

## 1. Grounded state (verified, current `polaris` HEAD)

- `src/polaris_v6/queue/run_store.py` `get_run(run_id) -> RunStatusResponse |
  None` (line 230) — `RunStatusResponse` carries `lifecycle_status`,
  `pipeline_status`, `artifact_dir`.
- `src/polaris_graph/audit_ir/loader.py` `load_audit_ir(artifact_dir) ->
  AuditIR` — raises `NotADirectoryError` / `FileNotFoundError` /
  `AuditIRSchemaError`. Per `docs/live_run_artifact_contract.md` §2.3 (the
  #503 contract), abort_*/error_* runs are NOT AuditIR-loadable.
- `src/polaris_graph/audit_ir/serializer.py` `to_json_dict(ir_object) -> Any`
  — already serializes `AuditIR` (frozen dataclasses + MappingProxyType +
  Path) to a JSON-safe dict.
- `src/polaris_v6/api/app.py` mounts 21 routers via `app.include_router(...)`.
- The 14-value `pipeline_status` set: `PipelineStatus` in
  `src/polaris_v6/schemas/run_status.py` — `abort_*` (6) + `error_unexpected`
  are the non-loadable statuses; `success` + `partial_*` (6) are loadable.

## 2. The plan — slice 1 (backend only)

**Two files.**

1. **New `src/polaris_v6/api/inspector.py`** — a v6 `APIRouter` with one route:
   `GET /api/inspector/runs/{run_id}` (path param typed `str`, passed verbatim
   to `run_store.get_run` — no `UUID` coercion) →
   - `run_store.get_run(run_id)`; `None` → 404 `run not found`.
   - `lifecycle_status != "completed"` → 409 (or 404) `run not completed`.
   - `pipeline_status` is `None` or starts with `abort_` / `error_` → 422
     `run produced no AuditIR-loadable artifacts` (per #503 contract §2.3 — an
     abort/error run is a pipeline-verdict artifact, not a renderable run).
   - `artifact_dir` absent / not a directory → 404.
   - `load_audit_ir(artifact_dir)` → on `FileNotFoundError` /
     `AuditIRSchemaError` / `NotADirectoryError` / `json.JSONDecodeError` →
     422 with the loader message (fail loud — no silent zero-fill).
   - success → `to_json_dict(ir)` returned as the JSON body.
2. **`src/polaris_v6/api/app.py`** — `app.include_router(inspector_router)`
   alongside the existing mounts.

This is the demo-scoped facade: ONE completed-run read route, resolved by the
v6 UUID `run_id` (no slug bridge needed — `run_store` is keyed by `run_id`).
It does NOT import or mount `inspector_router.py`.

## 3. Scope boundary

- IN: `src/polaris_v6/api/inspector.py` (new) + the `app.py` mount + tests.
- OUT: the 805-line frontend inspector page (slice 3); frontend `api.ts`
  helpers (slice 2); the other 6 surfaces (slices 4-12); `inspector_router.py`
  (not touched — the consult's stale correction); `EvidenceContract` /
  `bundle.py` / `getBundle` (Option A migrates *off* them, later slices).
- No change to `loader.py`, `serializer.py`, `run_store.py` — all reused as-is.

## 4. Smoke test — `tests/v6/test_inspector_route.py` (new)

Per the consult's slice-1 acceptance, cover: missing run → 404; not-completed
run → 4xx; `abort_*` run → 422; completed run with missing/invalid
`artifact_dir` → 4xx; a loadable completed run → 200 + a body that round-trips
(`to_json_dict` output is JSON-serializable and carries `manifest` / `run_id`).

**Clean-checkout reproducible (iter-1 P1):** the loadable case builds a
complete minimal artifact_dir under `tmp_path` — the 5 `load_audit_ir()`-
required files written by the test (`manifest.json` with the 7 loader-required
keys + `corpus` + `frame_coverage_report`, `report.md`, `bibliography.json`,
`contradictions.json`, `verification_details.json`). NO dependency on the
gitignored `outputs/`. (If the I-arch-001f pinned AuditIR fixture is committed
under `tests/`, reuse it instead — implement step checks.)

The test seeds a temp `run_store` DB (the `_build_db` pattern from
`tests/v6/test_backup_restore.py`) and sets the run-store DB env var to it
**before** constructing the `TestClient`, so the route reads the seeded DB,
not `state/v6_runs.sqlite`. `ast.parse` + targeted `pytest`.

## 5. Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/loader.py` + `serializer.py` — the reused
  building blocks; NOT modified.
- `src/polaris_v6/queue/run_store.py` — `get_run`; NOT modified.
- `src/polaris_v6/api/bundle.py` `get_bundle()` / `compare.py` `_load()` —
  the golden-`EvidenceContract` path Option A migrates away from; NOT touched
  in slice 1 (later slices).
- `src/polaris_graph/audit_ir/inspector_router.py` — deliberately NOT mounted
  / NOT imported (consult stale correction); NOT modified.
- `.github/workflows/codex-required.yml` — the canonical-diff gate excludes
  `.codex/I-rdy-008/` + `outputs/audits/I-rdy-008/`.

## 6. Acceptance criteria for THIS PR (slice 1)

1. `src/polaris_v6/api/inspector.py` — `GET /api/inspector/runs/{run_id}`
   serving faithful AuditIR JSON for a completed loadable run.
2. The completed-gate + abort/error rejection + artifact-dir validation +
   loader-error handling all fail loud (no silent fallback).
3. Mounted in `app.py`.
4. `tests/v6/test_inspector_route.py` green (the 5 cases in §4); no regression
   in `tests/v6/`.
5. Diff ≤ ~200 LOC; backend only; no frontend change.

## 7. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
