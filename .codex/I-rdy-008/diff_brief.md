# Codex DIFF review — I-rdy-008 / GH #504 slice 1: v6 live-inspector AuditIR resolver

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 slice 1 — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 2).
**3 files, +213:**

- `src/polaris_v6/api/inspector.py` (new) — `GET /api/inspector/runs/{run_id}`.
- `src/polaris_v6/api/app.py` — import + `include_router`.
- `tests/v6/test_inspector_route.py` (new) — 5 tests.

This is **slice 1 of ~12** for #504 (Option A, per the Codex arch-decision
consult `.codex/I-rdy-008/arch_decision_verdict.txt`). Backend only. Do NOT
flag "the frontend / the other 6 surfaces are still fixture-bound" — those are
later slices; #504 closes when the last lands.

## 2. The change

`GET /api/inspector/runs/{run_id}` resolves a v6 UUID `run_id` →
`run_store.get_run` → completed-gate (409) → abort/error reject (422) →
`artifact_dir` validation (404) → `load_audit_ir()` → `to_json_dict()` →
faithful AuditIR JSON. Loader exceptions → 422 (fail loud).

## 3. Verify

1. **Fail-loud, no silent fallback.** Every non-success path raises an
   `HTTPException` with a clear status + reason; no path returns a partial /
   zero-filled body. Confirm the `abort_*`/`error_*` 422 matches
   `docs/live_run_artifact_contract.md` §2.3 (abort/error runs are not
   AuditIR-loadable).
2. **Loader error set.** `except (FileNotFoundError, NotADirectoryError,
   ValueError, TypeError)` — `AuditIRSchemaError` and `json.JSONDecodeError`
   are `ValueError` subclasses (confirm); plain `ValueError`/`TypeError` catch
   malformed numeric fields (Codex brief iter-2 P2). Nothing should 500-escape.
3. **It does NOT mount `polaris_graph/audit_ir/inspector_router.py`.**
   `inspector.py` imports only `load_audit_ir`, `to_json_dict`, `run_store`.
   `app.py`'s new `inspector_router` is the local `polaris_v6.api.inspector`
   symbol — confirm no import of the 1400-line router (consult stale-correction).
4. **`run_id` is `str`** (no `UUID` path typing) — passed verbatim to
   `run_store.get_run`.
5. **Test is clean-checkout reproducible** — the loadable case builds a
   synthetic `artifact_dir` under `tmp_path`; no dependency on the gitignored
   `outputs/`. `POLARIS_V6_RUN_DB` set before `create_app()`.
6. **No regression** — `app.py` only adds one import + one `include_router`;
   route order/precedence unaffected.

## 4. Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/loader.py` (`load_audit_ir`) + `serializer.py`
  (`to_json_dict`) — reused as-is; NOT modified.
- `src/polaris_v6/queue/run_store.py` (`get_run` line 230, `mark_aborted`,
  `set_pipeline_meta`, `mark_completed`) — used by route + test; NOT modified.
- `src/polaris_v6/api/health.py` — the router pattern mirrored; NOT modified.
- `tests/v6/test_api_health_and_runs.py` — the `TestClient(create_app())`
  pattern; ran alongside the new test → 6/6 still pass.
- `src/polaris_graph/audit_ir/inspector_router.py` — deliberately NOT
  imported / NOT mounted (consult stale-correction); NOT modified.

## 5. Smoke state

`ast.parse` 3/3. `PYTHONPATH='src;.' pytest tests/v6/test_inspector_route.py
tests/v6/test_api_health_and_runs.py` → **11 passed** (5 new + 6 regression).

## 6. Required output schema (§8.3.9)

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
