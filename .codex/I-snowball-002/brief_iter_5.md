HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — brief iter 5 (final under cap; 2 nitpick P1 fixes)

Iter 4 status: AGREED on fallback strategy, router mount location/prefix, fail_* normalization, the data.classes placement, smoke-test add. 2 nitpick P1s left.

## P1 fixes (iter 4 → iter 5)

### P1-4.1 — Counts: 97 unique stubs / 98 occurrences

Codex iter 4 recomputed on canonical V30 (clinical_tirzepatide_t2dm):
- `bibliography = 26 entries`
- `referenced unique = 121 evidence_ids`
- `missing unique = 97 evidence_ids`
- `missing occurrences = 98` (because `ev_162` appears twice in references)

**Final GraphDiagnostics schema:**

```python
class GraphDiagnostics(BaseModel):
    bibliography_count: int
    fallback_source_count: int                       # unique stubs (=97 on canonical)
    missing_reference_occurrence_count: int          # total refs to absent IDs (=98 on canonical, includes duplicates)
    referenced_unknown_evidence_ids: list[str] = Field(default_factory=list)  # sorted set
```

**Test assertion update:**

```python
def test_canonical_fallback_counts():
    payload = build_graph_payload(load_audit_ir(CANONICAL_FIXTURE_DIR))
    assert payload.diagnostics.bibliography_count == 26
    assert payload.diagnostics.fallback_source_count == 97
    assert payload.diagnostics.missing_reference_occurrence_count == 98
    assert len(payload.diagnostics.referenced_unknown_evidence_ids) == 97
```

The duplicate (`ev_162` appearing in 2 referencing locations) is the count gap. Both fields exposed so UI can show "97 sources missing from bibliography (98 citations affected)" — distinct semantics, both useful.

### P1-4.2 — Bare import in app.py

Use bare `polaris_graph` import, no `src.` prefix:

```python
# src/polaris_v6/api/app.py — append near existing slice-router mounts
from polaris_graph.api.graph_route import router as graph_router
app.include_router(graph_router, prefix="/api")
```

Matches the convention used by other slice routers (audit_bundle_route, intake_route, generation_route, retrieval_route, benchmark_route, disambiguation_route).

Also fix the `graph_route.py` internal imports to use bare prefix:
```python
from polaris_graph.audit_ir.registry import find_run_by_id
from polaris_graph.audit_ir.loader import load_audit_ir, AuditIR
```

(Not `from src.polaris_graph...` as shown in iter 3.)

## P2 — `create_app` mount smoke test (iter 4 P2 add)

Add to `tests/polaris_graph/api/test_graph_route.py`:

```python
def test_graph_route_mounted_in_create_app(monkeypatch):
    """Prevents P1-3.2 regression — graph route must be mounted in the serving FastAPI app."""
    from polaris_v6.api.app import create_app
    from fastapi.testclient import TestClient
    app = create_app()
    routes = [(getattr(r, "path", None) or getattr(r, "path_regex", "")) for r in app.routes]
    assert any("/runs/{run_id}/graph" in str(p) for p in routes), \
        f"graph route not mounted; routes: {routes}"
    client = TestClient(app)
    response = client.get("/api/runs/nonexistent_run/graph")
    assert response.status_code == 404
```

## Final test count: 9 cases

1. `test_404_for_missing_run`
2. `test_422_on_audit_ir_load_failure`
3. `test_canonical_run_returns_payload_with_diagnostics` — verifies counts 26 / 97 / 98
4. `test_no_dangling_edges_canonical`
5. `test_deterministic_byte_equal`
6. `test_section_member_edges_match_kept_sentences`
7. `test_self_contradiction_skipped`
8. `test_frame_status_normalization`
9. `test_graph_route_mounted_in_create_app` — NEW from iter 4 P2

## Final file plan (unchanged from iter 4)

```
src/polaris_graph/api/graph_route.py        # NEW ~210 LOC
src/polaris_v6/api/app.py                   # MODIFIED +2 lines
tests/polaris_graph/api/test_graph_route.py # NEW ~170 LOC (9 cases now)
tests/polaris_graph/api/conftest.py         # NEW ~40 LOC
```

Per-file ≤200 LOC.

## Direct question for Codex iter 5

This is the iter-5 cap shot. Anything genuinely blocking I should fix before the diff phase begins, OR is the brief APPROVE-able now? Per §8.3.1: iter 5 REQUEST_CHANGES → I force-APPROVE and proceed to diff phase, capturing residual concerns as follow-up Issues.

## Output schema (terse)

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
