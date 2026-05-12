HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — brief iter 4 (P1 fixes from iter 3)

Iter 3 status: AGREED on V30 AuditIR source, schema, drop unverified sentences, drop self-contradiction, frame_coverage.entries field name confirmed. 2 P1 + 1 P2-status-enum left.

## P1 fixes

### P1-3.1 — Dangling edge endpoints on canonical V30 run

Codex finding: V30 canonical data has token `evidence_id`s and contradiction-claim `evidence_id`s that are NOT in `bibliography`. Building cites/contradicts edges with `target=src:<missing_evidence_id>` produces dangling edges.

**Resolution: fallback source nodes for every referenced evidence_id.**

Strategy: collect the set of evidence_ids referenced by (a) sentence tokens, (b) contradiction-claim evidence_ids. For any evidence_id NOT in `bibliography`, create a stub source node:

```python
def _build_source_nodes(ir: AuditIR) -> tuple[list[ClaimNode], set[str]]:
    """Returns (source nodes, set of all source_ids in graph)."""
    in_bib_ids: set[str] = set()
    nodes: list[ClaimNode] = []
    for entry in ir.bibliography:
        in_bib_ids.add(entry.evidence_id)
        tier = entry.tier if entry.tier in {"T1","T2","T3","T4","T5","T6","T7"} else None
        nodes.append(ClaimNode(data=NodeData(
            id=f"src:{entry.evidence_id}",
            type="source",
            label=(entry.statement or entry.evidence_id)[:200],
            tier=tier,
            source_url=entry.url or None,
            classes=None,
        )))
    # collect all referenced evidence_ids
    referenced: set[str] = set()
    for section in ir.verified_report.sections:
        for sent in section.sentences:
            if sent.is_verified:
                for tok in sent.tokens:
                    referenced.add(tok.evidence_id)
    for cluster in ir.contradictions:
        for claim in cluster.claims:
            referenced.add(claim.evidence_id)
    # fallback stubs for any referenced but not in bibliography
    missing = referenced - in_bib_ids
    for eid in sorted(missing):
        nodes.append(ClaimNode(data=NodeData(
            id=f"src:{eid}",
            type="source",
            label=eid,                # use evidence_id as label fallback
            tier=None,
            source_url=None,
            classes="bibliography_missing",   # CSS hook for grey/dashed rendering
        )))
    return nodes, in_bib_ids | missing
```

The set `in_bib_ids | missing` is then used to validate every cites/contradicts edge endpoint exists before emission. If an edge endpoint still doesn't resolve (impossible given construction above, but defensive), emit `dropped_edges_count` in `GraphPayload.diagnostics`:

```python
class GraphDiagnostics(BaseModel):
    bibliography_count: int
    fallback_source_count: int          # how many bibliography_missing stubs we created
    dropped_edges_count: int = 0        # always 0 with current logic; defensive
    referenced_unknown_evidence_ids: list[str] = Field(default_factory=list)

class GraphPayload(BaseModel):
    elements: GraphElements
    run_id: str
    elements_hash: str
    diagnostics: GraphDiagnostics
    schema_version: Literal["1.0"] = "1.0"
```

This surfaces the data anomaly via API (consumers can warn "98 sources referenced but not in bibliography") and the UI renders stubs greyed out so a Carney-grade reviewer sees them as "missing-from-bibliography" not "phantom citations."

**ADD** to `NodeData`:
```python
class NodeData(BaseModel):
    # ... existing fields ...
    classes: str | None = None     # cytoscape CSS class hook
```

### P1-3.2 — Mount router in serving app

Per Codex: `src/polaris_v6/api/app.py` is where slice routers are mounted (audit_bundle, intake, retrieval, generation, etc.).

**Resolution:** the diff adds one import + one mount line to `app.py`:

```python
# src/polaris_v6/api/app.py — appended near other slice mounts
from src.polaris_graph.api.graph_route import router as graph_router
app.include_router(graph_router, prefix="/api")
```

(I'll verify the existing mount conventions for prefix when writing the diff; if existing routes use `prefix=""` and the route file already has `/runs/...` etc., I'll match the surrounding pattern.)

## P2 fix

### P2-3.1 — FrameStatus enum widened

V30 canonical has `fail_min_fields` (not just `fail`). Two options:
- (chosen) **Map `fail_*` → `fail` in API enum**: simplest, UI doesn't care about sub-types in v1.
- Widen enum: `Literal["pass", "partial", "fail", "fail_min_fields", "fail_no_evidence", ...]` — exposes V30's exact taxonomy.

Going with map-to-fail for v1 simplicity:

```python
def _normalize_frame_status(raw: str) -> Literal["pass", "partial", "fail"] | None:
    if raw == "pass":
        return "pass"
    if raw == "partial":
        return "partial"
    if raw.startswith("fail"):
        return "fail"
    return None
```

If UI later wants the sub-type, add `frame_status_detail: str | None` (= raw V30 status) as a separate field.

## Final implementation file structure (no LOC changes; same as iter 3 + the additions above)

```
src/polaris_graph/api/graph_route.py        # NEW ~210 LOC (router + builder + helpers)
src/polaris_v6/api/app.py                   # MODIFIED +2 lines (import + include_router)
tests/polaris_graph/api/test_graph_route.py # NEW ~150 LOC (fixture + 8 cases)
tests/polaris_graph/api/conftest.py         # NEW ~40 LOC (V30 canonical AuditIR fixture)
```

Per-file LOC all ≤200. Total ≈ 402 LOC across 4 files.

## Test cases (concrete)

1. `test_404_for_missing_run` — non-existent run_id → 404
2. `test_422_on_audit_ir_load_failure` — exception from load_audit_ir → 422
3. `test_canonical_run_returns_payload_with_diagnostics` — clinical_tirzepatide_t2dm fixture → payload with non-zero bibliography_count + fallback_source_count matching the 98 referenced-not-in-bib evidence_ids Codex flagged
4. `test_no_dangling_edges_canonical` — every cites/contradicts edge endpoint resolves to a source node (in_bib OR fallback)
5. `test_deterministic_byte_equal` — two consecutive `build_graph_payload(ir)` produce identical `elements_hash`
6. `test_section_member_edges_match_kept_sentences` — every verified sentence has exactly one section_member edge to its parent section
7. `test_self_contradiction_skipped` — V30 fixture with cluster having single-evidence_id claims emits zero contradicts edges
8. `test_frame_status_normalization` — `fail_min_fields` → `fail` in normalized output

## Files I have ALSO checked and they're clean (re-verified iter 4)

- `src/polaris_graph/audit_ir/loader.py:163-188` (FrameCoverageEntry, status field is string)
- `src/polaris_graph/audit_ir/registry.py:44-58` (RunSummary), `:179` (find_run_by_id)
- `src/polaris_v6/api/app.py` (mount point for new router — actual file read happens in diff stage)
- `src/polaris_graph/api/audit_bundle_route.py` (router-mount precedent)

## Direct questions for Codex iter 4

1. **Fallback source node strategy** — is "bibliography_missing" classes hook + GraphDiagnostics counter the right way to handle V30 dangling-evidence-ids? Or do you want a different approach (e.g., drop the offending edges entirely with a counter)?
2. **Router mount location** — `src/polaris_v6/api/app.py` with `prefix="/api"` — confirm this matches existing slice-router precedent?
3. **FrameStatus map-to-fail** — acceptable for v1, or do you require widened enum from the start?
4. **Anything else genuinely blocking?**

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
