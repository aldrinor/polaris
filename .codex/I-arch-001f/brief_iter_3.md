HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001f iter 3 — P1-005 + P1-006 resolutions

## P1-005 — StubBroker flush API

```python
@pytest.fixture(autouse=True)
def flush_stub_broker():
    import dramatiq
    broker = dramatiq.get_broker()
    if hasattr(broker, "flush_all"):
        broker.flush_all()
    yield
    if hasattr(broker, "flush_all"):
        broker.flush_all()
```

`hasattr` guard preserves portability when the broker is a real Redis broker (no `flush_all`) — the test environment is StubBroker-only per `tests/v6/conftest.py` so the call will fire.

## P1-006 — bundle tar shape: manifest.yaml + verified_report.json

Bundle structure (per `src/polaris_v6/api/bundle.py` + `polaris_graph.api.audit_bundle_route.post_audit_bundle`):

```
audit_<bundle_id>.tar.gz
  audit_<bundle_id>/
    manifest.yaml          # BundleManifest serialized as YAML
    verified_report.json   # VerifiedReport
    evidence_pool.json     # EvidencePool
    scope_decision.json    # ScopeDecision
    methods.json
    bibliography.json
    signature.asc          # GPG detached signature
```

BundleManifest does NOT carry `external_run_id`. The chain to validate is:
- `manifest.report_id == report.report_id`
- `manifest.decision_id == report.decision_id`
- `manifest.decision_id == f"dec-{posted_run_id}"` (the value we injected into source manifest.scope.decision_id, which `artifact_to_slice_chain.build_slice_chain` reads into the ScopeDecision)
- `manifest.evidence_pool_id == pool.pool_id`

External_run_id is asserted ONLY against the source `artifact_dir/manifest.json` AND `run_store.get_run(posted_run_id)` record, NOT against the bundle's manifest.yaml.

Test code:

```python
import io, tarfile, yaml
with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
    names = tar.getnames()
    bundle_dir = names[0].split("/")[0]  # audit_<id>
    manifest_member = tar.extractfile(f"{bundle_dir}/manifest.yaml").read()
    report_member = tar.extractfile(f"{bundle_dir}/verified_report.json").read()
bundle_manifest = yaml.safe_load(manifest_member)
report = json.loads(report_member)

assert bundle_manifest["report_id"] == report["report_id"]
assert bundle_manifest["decision_id"] == report["decision_id"] == f"dec-{posted_run_id}"

# External run_id chain — assert OUTSIDE the bundle:
src_manifest = json.loads((artifact_dir / "manifest.json").read_text())
assert src_manifest["external_run_id"] == posted_run_id
record = run_store.get_run(posted_run_id, path=str(isolated_runs_db))
assert record.run_id == posted_run_id
```

## P3 resolution — single override mechanism

Per Codex iter-2 P3: pick ONE of {fixture helper kwarg, inline JSON patch}. Going with inline JSON patch only (simpler; helper signature stays unchanged for the existing tests that reuse it).

## P2 carry-forward (already approved iter 1+2)

- Single capstone test.
- fakeredis CI; real-Redis is a post-deploy smoke (out of scope).
- `tests/v6/test_end_to_end_arch_001f.py` path APPROVE'd.
- StubBroker availability: file lives under `tests/v6/`, which has the autouse conftest installing the broker before importing runs router / actors.

## Acceptance criteria (unchanged from iter 2)

Same as iter 2.

## Direct questions iter 3

1. P1-005 fix (`flush_all` with `hasattr` guard) — APPROVE'd?
2. P1-006 fix (manifest.yaml + verified_report.json extraction via tarfile + yaml.safe_load; external_run_id asserted only on source manifest.json + run_store record) — APPROVE'd?
3. PyYAML available in test env (per `import yaml` in test)? requirements check needed?
4. Anything else blocking iter-3 APPROVE?

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
