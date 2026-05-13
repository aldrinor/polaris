HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank for iter 6.
- Surface ALL findings now; do not hold back.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001f — e2e test with pinned AuditIR fixture (POST → graph → bundle → compare)

GH#468. Critical-path day 10. The capstone test that pins the I-arch-001a → I-arch-001e seam end-to-end so any future drift on run_store / actors / pipeline-A / bundle / stream / SSE-translation breaks one obvious assertion.

## Files I have ALSO checked clean (§-1.2 #2)

- `tests/polaris_v6/api/test_artifact_to_slice_chain.py` — has `_write_synthetic_artifact_dir(tmp_path, ...)` building a loader-valid AuditIR fixture with all 5 required JSON files (manifest, verification_details, bibliography, contradictions, report). Reusable.
- `tests/polaris_v6/api/test_bundle_endpoint_targz.py` (I-arch-001d) — already exercises the bundle endpoint with synthetic artifact + signer override + 404/422 paths. Has the pattern for `app.dependency_overrides[get_sign_fn] = _stub_sign_fn`.
- `tests/v6/test_api_stream.py` (I-arch-001e) — has the fakeredis monkeypatch pattern for `stream_module.read_events`.
- `src/polaris_v6/api/app.py` — `create_app()` wires `/runs` + `/stream` + `/bundle` (need to confirm bundle router is included).
- `src/polaris_v6/api/runs.py:23-40` — POST /runs creates uuid → `run_store.insert_run` → `enqueue_research_run.send` → returns RunStatusResponse with lifecycle_status='queued'.
- `src/polaris_v6/queue/actors.py` — `enqueue_research_run.fn(run_id, payload)` is the Phase-0 stub returning `{"run_id": ..., "status": "completed", "echo": payload}` — does NOT call pipeline-A.
- `src/polaris_v6/queue/run_store.py` — `insert_run`, `mark_in_progress`, `set_pipeline_meta(query_slug, artifact_dir, manifest_run_id, decision_id)`, `mark_completed(run_id, result_json, pipeline_status, cost_usd)`, `get_run`.
- `src/polaris_v6/api/bundle.py` — `GET /runs/{run_id}/bundle.tar.gz` reads run_store record, requires lifecycle_status='completed' + release_allowed=True, calls `build_slice_chain(artifact_dir)`, dispatches to `post_audit_bundle` with `Depends(get_sign_fn)`.
- `src/polaris_v6/queue/run_events.py` (I-arch-001e) — `emit_event` + `emit_terminal_event` + `read_events` + `translate`.

## Scope

Single test file `tests/v6/test_end_to_end_arch_001f.py` (~250 LOC) that hits:

1. **POST /runs** with `{template: "clinical", question: "..."}` → 202 + `RunStatusResponse(run_id=uuid, lifecycle_status="queued")`.
2. **Simulate pipeline-A side-effects** (the actor is a Phase-0 stub, so the test manually invokes the side-effects pipeline-A would produce):
   - `_write_synthetic_artifact_dir(tmp_path / run_id)` builds the AuditIR-shape directory.
   - `run_store.mark_in_progress(run_id)`.
   - `run_store.set_pipeline_meta(run_id, query_slug, artifact_dir, decision_id)`.
   - `run_events.emit_event(run_id, "scope_gate.completed", {...}, redis_client=sync_fake)` — stage event.
   - `run_events.emit_terminal_event(run_id, "success", redis_client=sync_fake)`.
   - `run_store.mark_completed(run_id, result_json, pipeline_status="success", cost_usd=0.42)`.
3. **GET /runs/{run_id}** → 200 + lifecycle_status="completed" + pipeline_status="success".
4. **GET /stream/{run_id}** → SSE response with `scope_decision` + `run_complete` v6 events (translated from pipeline-A naming via `run_events.translate`).
5. **GET /runs/{run_id}/bundle.tar.gz** with `dependency_overrides[get_sign_fn] = _stub_sign_fn` → 200 application/gzip (or 503 gpg_unavailable if no override; assert NOT 503 with override).
6. **Compare assertions**: the bundle response carries `bundle_id` + a manifest with the same `run_id` UUID. The SSE stream's `run_complete.status` == manifest.status. The bundle's slice_chain.report.pipeline_verdict == "success".

## Acceptance criteria

1. Single hermetic e2e test using `fakeredis.FakeServer()` + `_write_synthetic_artifact_dir` (no real Redis, no real LLM, no real network).
2. Test passes against the polaris HEAD (post-I-arch-001e merge).
3. Test fails LOUDLY if any of:
   - `run_store.mark_completed` schema regression
   - `bundle.py` Depends() callable-identity regression (per I-arch-001d P1-001)
   - `stream.py` Last-Event-ID header semantics regression
   - `run_events.translate` mapping regression
   - `artifact_to_slice_chain` ScopeDecision / EvidencePool / VerifiedReport schema regression
4. Test runs in <5s wall-clock.
5. No mocking of `run_store` or `artifact_to_slice_chain` — those are exercised against the real implementations to catch real drift.

## Direct questions iter 1

1. Single e2e test (~250 LOC) covering 6 steps as the I-arch-001a-e capstone — APPROVE'd? Or want it split into 2 tests (one for POST→stream, one for POST→bundle)?
2. Synthetic AuditIR fixture reused from `tests/polaris_v6/api/test_artifact_to_slice_chain.py::_write_synthetic_artifact_dir` rather than promoted to a shared conftest — APPROVE'd, or want it promoted in this same PR?
3. fakeredis-backed SSE rather than real-Redis integration test — APPROVE'd for I-arch-001f (hermetic CI bar), with real-Redis e2e captured as a separate post-deploy smoke test?
4. Test file path `tests/v6/test_end_to_end_arch_001f.py` — APPROVE'd? Or prefer `tests/v6/test_e2e_pipeline_a_seam.py`?
5. Anything else blocking iter-1 APPROVE?

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
