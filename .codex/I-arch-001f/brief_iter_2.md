HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001f iter 2 — P1 resolutions

## P1-001 resolution — fixture run_id consistency

`_write_synthetic_artifact_dir` will be extended (in-test patch, not promoted to conftest per iter-1 P2 guidance) to accept `manifest_overrides: dict[str, Any] = None` that lets the test inject the POST `/runs` UUID into `manifest.run_id`, `manifest.scope.decision_id`, `manifest.slug` consistently. After `_write_synthetic_artifact_dir(...)`, the test re-reads `manifest.json`, applies overrides, writes back:

```python
manifest_path = artifact_dir / "manifest.json"
m = json.loads(manifest_path.read_text())
m["run_id"] = f"SWEEP_{posted_run_id[:8]}"  # pipeline-A's internal name
m["external_run_id"] = posted_run_id        # threads through augment_v6_manifest
m["scope"]["decision_id"] = f"dec-{posted_run_id}"
m["slug"] = "synthetic_e2e"
manifest_path.write_text(json.dumps(m, sort_keys=True))
```

Then assert: `bundle_response.manifest.external_run_id == posted_run_id`, `bundle.report.decision_id == f"dec-{posted_run_id}"`, AND per iter-1 P2 nudge: `bundle.manifest.report_id == bundle.report.report_id` + `bundle.manifest.decision_id == bundle.report.decision_id`.

## P1-002 resolution — isolate POLARIS_V6_RUN_DB + flush StubBroker

Fixture chain:
```python
@pytest.fixture
def isolated_runs_db(tmp_path, monkeypatch):
    db_path = tmp_path / "e2e_v6_runs.sqlite"
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(db_path))
    run_store.init_db(str(db_path))
    yield db_path

@pytest.fixture(autouse=True)
def flush_stub_broker():
    """Per Codex iter-1 P1-2: enqueue_research_run.send leaves a message on
    the session-shared StubBroker; flush before and after to prevent bleed."""
    import dramatiq
    broker = dramatiq.get_broker()
    for q in list(broker.queues.keys()):
        broker.flush_queue(q)
    yield
    for q in list(broker.queues.keys()):
        broker.flush_queue(q)
```

The POLARIS_V6_RUN_DB env var is read by `run_store._resolve_path()` so all `run_store.*` calls inside the test (POST /runs invokes the queue actor + endpoints invoke run_store directly) land on the isolated sqlite file.

## P1-003 resolution — Last-Event-ID resume assertion

After step 4 (initial /stream GET that consumes scope_decision + run_complete), test issues a SECOND GET with `Last-Event-ID: <first_event_stream_id>` header. Verify the response only contains events AFTER that stream_id (i.e., `run_complete` but NOT `scope_decision`). Reuses the monkeypatched `read_events` reader from I-arch-001e test pattern.

## P1-004 resolution — set_pipeline_meta keyword-only args

Verified against HEAD `src/polaris_v6/queue/run_store.py`:

```python
def set_pipeline_meta(
    run_id: str,
    *,
    query_slug: str | None = None,
    artifact_dir: str | None = None,
    manifest_run_id: str | None = None,
    decision_id: str | None = None,
    path: str | None = None,
) -> None:
```

All call-sites in the test will use keyword args:
```python
run_store.set_pipeline_meta(
    posted_run_id,
    query_slug="synthetic_e2e",
    artifact_dir=str(artifact_dir),
    manifest_run_id=f"SWEEP_{posted_run_id[:8]}",
    decision_id=f"dec-{posted_run_id}",
    path=str(isolated_runs_db),
)
```

## P2 — iter-1 nudges accepted

- Single capstone test, no split.
- fakeredis CI; real Redis is a separate post-deploy smoke (out of scope for I-arch-001f).
- Fixture extended in-place via overrides; conftest promotion deferred.
- Bundle manifest.report_id == report.report_id + decision_id chain assertion ADDED per iter-1 P2 nudge.

## Updated test outline

```python
def test_e2e_post_run_through_bundle_stream_compare(
    app_with_v6_routers, isolated_runs_db, fake_server, sync_fake, async_fake,
    tmp_path, monkeypatch,
):
    # Step 1: POST /runs → 202 + uuid
    # Step 2: simulate pipeline-A:
    #   - write artifact dir w/ manifest patched to POST uuid
    #   - run_store.mark_in_progress / set_pipeline_meta(kwargs) / emit_event /
    #     emit_terminal_event / mark_completed
    # Step 3: GET /runs/{uuid} → 200 completed/success
    # Step 4: GET /stream/{uuid} → scope_decision + run_complete; capture
    #         first_event_stream_id from `id:` SSE line
    # Step 5: GET /stream/{uuid} headers={"Last-Event-ID": first_event_stream_id}
    #         → only run_complete (resume semantics)
    # Step 6: GET /runs/{uuid}/bundle.tar.gz with stub sign_fn override → !=503
    # Step 7: extract bundle.tar.gz; verify manifest.external_run_id == uuid +
    #         report.decision_id == f"dec-{uuid}" + manifest.report_id == report.report_id
```

## Direct questions iter 2

1. The 4 P1 resolutions as described — APPROVE'd?
2. Bundle response is `application/gzip`; extraction in test uses `tarfile.open(fileobj=BytesIO(resp.content), mode="r:gz")` and reads `manifest.json` + `verified_report.json` inside the tar. Acceptable, or want a `bundleable=true` JSON-only response check instead?
3. Anything else blocking iter-2 APPROVE?

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
