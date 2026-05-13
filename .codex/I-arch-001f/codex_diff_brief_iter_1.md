HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001f diff iter 1 — e2e test pinning POST → stream → resume → bundle

Brief APPROVE iter 3 of 5. This is the diff implementation.

## Diff: `.codex/I-arch-001f/codex_diff.patch` (~280 LOC, 1 NEW test file)

## File added (1)

**NEW `tests/v6/test_end_to_end_arch_001f.py`** (~280 LOC, 1 test):

`test_e2e_post_run_through_stream_resume_and_bundle` exercises the full I-arch-001a..001e chain:

1. POST `/runs` → 202 + uuid + `lifecycle_status="queued"`
2. Simulate pipeline-A side-effects: `_write_synthetic_artifact_dir(tmp_path)` (reused from I-arch-001d), patch manifest.json to thread `external_run_id`/`scope.decision_id`, then `run_store.mark_in_progress` + `run_store.set_pipeline_meta(**kwargs)` + `emit_event("scope_gate.completed")` + `emit_terminal_event("success")` + `run_store.mark_completed`
3. GET `/runs/{uuid}` → 200 + `lifecycle_status="completed"` + `pipeline_status="success"`
4. GET `/stream/{uuid}` (with monkeypatched `read_events` feeding fakeredis) → SSE: `scope_decision` + `run_complete` (translated from pipeline-A naming)
5. GET `/stream/{uuid}` with `Last-Event-ID: <first_event_id>` → only `run_complete` (resume semantics)
6. GET `/runs/{uuid}/bundle.tar.gz` with `dependency_overrides[get_sign_fn] = _stub_sign_fn` → not-503 (P1-001 regression check from I-arch-001d)
7. Open tar via `tarfile` + `BytesIO`; parse `audit_<id>/manifest.yaml` (yaml.safe_load) + `audit_<id>/verified_report.json`. Assert:
   - `bundle_manifest.report_id == bundle_report.report_id`
   - `bundle_manifest.decision_id == bundle_report.decision_id == f"dec-{posted_run_id}"`
   - `bundle_manifest.pool_id == bundle_report.pool_id` (if present)
   - Source `artifact_dir/manifest.json.external_run_id == posted_run_id`
   - `run_store.get_run(uuid).run_id == posted_run_id`

## P1 resolutions verified in code

- **P1-001 fixture run_id consistency:** lines 154-162 patch source manifest.json with posted UUID + decision_id + slug; `build_slice_chain` reads these into the slice chain.
- **P1-002 POLARIS_V6_RUN_DB isolation + StubBroker flush:** `isolated_runs_db` fixture (lines 47-53) uses `monkeypatch.setenv` + `run_store.init_db(tmp_path/...)`. `flush_stub_broker` autouse fixture (lines 57-68) calls `broker.flush_all()` before + after yield with `hasattr` guard.
- **P1-003 Last-Event-ID resume assertion:** lines 207-213 issue a SECOND GET with `Last-Event-ID: <first_event_id>` header, assert only `run_complete` returned.
- **P1-004 keyword-only set_pipeline_meta:** lines 168-175 call with all kwargs (query_slug, artifact_dir, manifest_run_id, decision_id, path).
- **P1-005 broker.flush_all (not flush_queue):** line 60-61 + 65-66 use `hasattr(broker, "flush_all")` guard then `broker.flush_all()`.
- **P1-006 manifest.yaml + verified_report.json:** lines 230-242 open tar, extract those two members, `yaml.safe_load` the manifest, assert FK chain. External_run_id asserted ONLY against source manifest.json + run_store record (lines 257-260), NOT against bundle manifest.

## Files I have ALSO checked clean (§-1.2 #2)

- `tests/v6/conftest.py` — autouse StubBroker installer fires for this file (sibling under `tests/v6/`)
- `tests/polaris_v6/api/test_artifact_to_slice_chain.py` — `_write_synthetic_artifact_dir` import path resolves correctly via `from tests.polaris_v6.api.test_artifact_to_slice_chain import _write_synthetic_artifact_dir`
- `src/polaris_v6/queue/run_store.py:set_pipeline_meta` — verified keyword-only signature against HEAD
- `src/polaris_graph/api/audit_bundle_route.py:get_sign_fn` — same import path used by I-arch-001d test_bundle_endpoint_targz.py for dependency_overrides
- `requirements-v6.txt` — yaml available transitively; the bundle endpoint also imports yaml elsewhere

## Test results

```
$ python -m pytest tests/v6/test_end_to_end_arch_001f.py -x
1 passed in 1.33s
```

Test passes on the first run with all 6 P1 resolutions verified.

## Direct questions iter 1

1. Test passes hermetically in 1.33s with all 6 P1 resolutions from brief iter 2 + 3 — APPROVE'd?
2. PyYAML dependency: test imports `yaml` directly; available transitively in v6 CI per Codex iter-3 P2 nudge. Acceptable, or want a direct pin added to `requirements-v6.txt` in this PR?
3. Anything else blocking iter-1 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
