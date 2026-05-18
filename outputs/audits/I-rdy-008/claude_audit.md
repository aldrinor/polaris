# Claude architect audit — I-rdy-008 (#504) slice 1

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 1 of ~12** (Codex arch-decision consult `arch_decision_verdict.txt`:
verdict A — migrate onto the canonical `run_id → artifact_dir →
load_audit_ir() → AuditIR` path). #504 closes when the last slice lands.
**Branch:** `bot/I-rdy-008` off `polaris` HEAD `296f75bc`.
**Commit 1:** `9082b2be` — 3 files, +213.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex APPROVE iter 2 (iter 1
REQUEST_CHANGES, 1 P1 + 3 P2 all fixed — §4).

## 1. What shipped

| File | Change |
|---|---|
| `src/polaris_v6/api/inspector.py` | NEW — `GET /api/inspector/runs/{run_id}` serving faithful AuditIR JSON for a completed run. |
| `src/polaris_v6/api/app.py` | +2 — import + `include_router(inspector_router)`. |
| `tests/v6/test_inspector_route.py` | NEW — 5 resolution-outcome tests. |

Backend only. No frontend change — the inspector frontend migration is slice 3.

## 2. Why Option A / why this slice shape

The operator delegated the A-vs-B architecture choice to Codex. The Codex
consult returned **verdict A**: route the rich UI through `AuditIR` (faithful
— preserves raw T1-T7 tiers and range-keyed evidence spans) rather than the
narrower golden `EvidenceContract` (B). The consult's **stale-correction**,
honored: do NOT wholesale-mount `polaris_graph/audit_ir/inspector_router.py`
(in HEAD it also carries non-demo surfaces — jobs, workspaces, operator
dashboards). Slice 1 is the consult's verbatim slice 1: a demo-scoped v6
facade route.

## 3. Per-finding verification

- **VERIFIED — resolution outcomes fail loud (no silent fallback):** unknown
  run → 404; `lifecycle_status != completed` → 409; `pipeline_status`
  `abort_*`/`error_*` → 422 (per `docs/live_run_artifact_contract.md` §2.3 — an
  abort/error run is a pipeline-verdict artifact, not AuditIR-loadable);
  absent / non-directory `artifact_dir` → 404; loader failure → 422 with the
  loader message. All 5 covered by `tests/v6/test_inspector_route.py`.
- **VERIFIED — faithful AuditIR, no lossy adapter:** the route returns
  `to_json_dict(load_audit_ir(artifact_dir))` — the raw canonical IR (raw
  tiers, range-keyed `[#ev:id:start-end]` tokens). This is what made A the
  Codex-chosen path over B's tier-narrowing `EvidenceContract`.
- **VERIFIED — does not mount `inspector_router.py`:** `inspector.py` imports
  only `load_audit_ir`, `to_json_dict`, `run_store` — not the 1400-line
  router. `app.py` mounts only the new demo-scoped `inspector_router` symbol
  (the local one from `polaris_v6.api.inspector`).
- **VERIFIED — clean-checkout reproducible test (Codex brief iter-1 P1):** the
  loadable-run test builds a synthetic minimal `artifact_dir` under `tmp_path`
  (the 5 `load_audit_ir`-required files) — no dependency on the gitignored
  `outputs/`. The test sets `POLARIS_V6_RUN_DB` to a temp DB before
  `create_app()` (iter-1 P2).
- **VERIFIED — `run_id` is `str`, not `UUID`-typed (iter-1 P2):** passed
  verbatim to `run_store.get_run` — no hyphen/hex mismatch with the stored
  `uuid4().hex` key.
- **VERIFIED — loader error set widened (iter-2 P2):** the `except` catches
  `(FileNotFoundError, NotADirectoryError, ValueError, TypeError)` —
  `AuditIRSchemaError` and `json.JSONDecodeError` are `ValueError` subclasses,
  and plain `ValueError`/`TypeError` catch malformed numeric fields too.

## 4. Codex iteration trail (brief)

- **iter 1 REQUEST_CHANGES** (1 P1 + 3 P2): loadable test depended on the
  gitignored `outputs/honest_sweep_r3/...`; `run_id` should be `str` not
  `UUID`; tests must seed `POLARIS_V6_RUN_DB`; map `json.JSONDecodeError` too.
  All fixed in the iter-2 brief.
- **iter 2 APPROVE** (1 non-blocking P2): also catch plain `ValueError` /
  `TypeError` from the loader — folded into the implementation.

## 5. Smoke

`ast.parse` clean on the 3 files. `PYTHONPATH='src;.' pytest
tests/v6/test_inspector_route.py tests/v6/test_api_health_and_runs.py` →
**11 passed** (5 new inspector-route + 6 health/runs — the route-mount change
is regression-free).

## 6. Scope + residuals

- Slice 1 = the backend resolver. The frontend inspector page (805 lines) +
  the other 6 surfaces are slices 3-12 of #504 (consult decomposition);
  #504 stays open until the last slice.
- The new route is unauthenticated, matching the brief and the sibling v6
  routes (`health`, `runs`); auth-gating, if wanted, is a separate concern.

## 7. Verdict

Faithful to the iter-2 APPROVE'd brief; the 5 resolution outcomes fail loud
and are tested; faithful AuditIR served; the `inspector_router.py`
wholesale-mount correctly avoided. Ready for Codex diff review.
