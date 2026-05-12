HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — Backend `/api/runs/{id}/graph` endpoint + GraphPayload schema

GH#448. Branch: `bot/I-snowball-002-graph-endpoint`. First of 8 issues in F-snowball workstream.

## Scope (per `.codex/I-snowball-001/DECISION.md`)

- `GET /api/runs/{run_id}/graph` returns `GraphPayload` JSON (cytoscape element format).
- Build the payload deterministically from `(ScopeDecision, EvidencePool, VerifiedReport)` triple (same inputs F15 audit bundle takes).
- Nodes: sentences (small), evidence sources (larger), frame manifest entries.
- Edges: sentence→source (from provenance tokens `[#ev:source_id:start-end]`), source↔source contradiction (from contradictions.json / F8), section_member compound-membership.
- LOC ≤200.

## Design question for Codex (this is where I want your input)

**Server-side layout pre-computation:** the DECISION.md proposed running fcose server-side (Python → Node subprocess → cytoscape-fcose) to ship preset positions in `GraphPayload`. After deeper look, this has three options:

**Option A (server-side Node subprocess):**
- Python backend spawns `node` subprocess with a small wrapper script
- Wrapper installs cytoscape@3.30 + cytoscape-fcose@2.2, reads elements from stdin, runs fcose with `randomize:false, quality:'proof'`, writes positions to stdout
- Backend caches positions keyed on hash(elements) so re-requests are O(1)
- COST: adds Node.js runtime dependency to backend; subprocess complexity; ~80 LOC of Python wrapper + Node JS wrapper
- BENEFIT: first paint at client is pure preset render (zero layout solver cost), best determinism

**Option B (Web Worker client-side first-load):**
- Backend returns elements ONLY, no positions
- Client spawns a Web Worker that loads cytoscape + fcose, runs layout, caches positions in localStorage keyed on hash(elements)
- Subsequent visits use cached positions
- COST: first-EVER load shows loading spinner during layout; localStorage cache invalidates if user clears site data
- BENEFIT: no Node backend dependency; pure browser-side

**Option C (Python networkx alternative):**
- Backend uses `networkx.spring_layout` (deterministic with seed=42)
- Approximates fcose force-directed look but lacks compound-aware clustering
- Pure-Python, no Node dependency
- COST: aesthetic doesn't match fcose / Connected Papers / Litmaps look (compound nodes don't cluster as cleanly)
- BENEFIT: simplest, fully reproducible

**My provisional recommendation:** **Option B (Web Worker client-side)** — keeps backend pure Python (matches POLARIS LAW VII CLI Isolation), avoids Node dependency, accepts a one-time "computing layout..." spinner on first visit per run (acceptable per Carney demo flow because reviewer typically views a report once or twice). Subsequent re-visits + audit-bundle PNG export use cached positions.

If Codex disagrees: which option AND why?

## Files I have ALSO checked and they're clean:

- `src/polaris_graph/api/audit_bundle_route.py` — FastAPI router pattern (APIRouter + Pydantic models + Depends)
- `src/polaris_graph/audit_bundle/bundle_schema.py` — Pydantic schema pattern (ContentType, BundleManifest, FileEntry with field_validator)
- `src/polaris_graph/retrieval2/evidence_pool.py` — `EvidencePool` model (source of evidence node data)
- `src/polaris_graph/generator2/verified_report.py` — `VerifiedReport` model (source of sentence node data)
- `src/polaris_graph/scope/scope_decision.py` — `ScopeDecision` model (source of frame manifest data)
- `src/polaris_graph/generator/provenance_generator.py` + `src/polaris_graph/generator2/strict_verify.py` — `[#ev:source_id:start-end]` token format used by sentence→source edge derivation
- `src/polaris_v6/api/app.py` — central FastAPI app that mounts slice routers (we'll add `graph_router` here)
- `web/package.json` — confirmed no graph viz libs installed; new deps come in I-snowball-003a not 002

## Proposed schema (Pydantic)

```python
# src/polaris_graph/api/graph_route.py (NEW)
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from polaris_graph.scope.scope_decision import ScopeDecision
from polaris_graph.retrieval2.evidence_pool import EvidencePool
from polaris_graph.generator2.verified_report import VerifiedReport

router = APIRouter(tags=["graph"])

# ----- payload models -----

NodeType = Literal["sentence", "source", "frame"]
EdgeType = Literal["cites", "co_cites_default_off", "contradicts", "section_member", "frame_member"]
Tier = Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"]

class NodeData(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    type: NodeType
    label: str = Field(min_length=1, max_length=500)
    tier: Tier | None = None
    parent: str | None = None              # compound-node membership
    sentence_text: str | None = None
    source_url: str | None = None
    section_name: str | None = None

class Position(BaseModel):
    x: float
    y: float

class ClaimNode(BaseModel):
    data: NodeData
    # Per Option B: position is OPTIONAL in v1 payload — client computes via Web Worker.
    # If we adopt Option A/C later, server populates this field.
    position: Position | None = None

class EdgeData(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    source: str
    target: str
    edge_type: EdgeType

class ClaimEdge(BaseModel):
    data: EdgeData

class GraphElements(BaseModel):
    nodes: list[ClaimNode]
    edges: list[ClaimEdge]

class GraphPayload(BaseModel):
    elements: GraphElements
    run_id: str = Field(min_length=1, max_length=200)
    elements_hash: str = Field(min_length=64, max_length=64, description="SHA256 hex of canonicalized elements JSON; client uses as layout cache key")
    layout_meta: dict | None = None        # populated when positions present; None for Option B
    schema_version: Literal["1.0"] = "1.0"

# ----- builder (pure function, easy to test) -----

def build_graph_payload(
    run_id: str,
    decision: ScopeDecision,
    pool: EvidencePool,
    report: VerifiedReport,
) -> GraphPayload:
    """Pure-function transformation. Deterministic — test asserts byte-equal output for same input."""
    # 1. sentence nodes (one per VerifiedReport sentence; parent=section_id)
    # 2. source nodes (one per EvidencePool source; tier from source.tier)
    # 3. frame nodes (one per decision.frame_manifest entry)
    # 4. cites edges (parse provenance tokens in each sentence; one edge per (sentence, source))
    # 5. contradicts edges (parse contradictions.json from report; one edge per pair)
    # 6. section_member edges (sentence → section compound parent; visual only)
    # 7. compute SHA256 of canonical (sort_keys=True) JSON for elements_hash
    raise NotImplementedError("Implementation in diff")

# ----- route -----

@router.get("/runs/{run_id}/graph", response_model=GraphPayload)
def get_run_graph(run_id: str) -> GraphPayload:
    """Return cytoscape-format graph payload for a completed run.

    Looks up the run by `run_id` from storage (TBD how — there's existing
    run lookup substrate; pattern matches `/api/inspector/runs/{slug}/...`).
    Returns 404 if run not found. Returns 422 if run is still in_progress.
    """
    raise NotImplementedError
```

## Provisional test plan (smoke + unit + integration)

```python
# tests/polaris_graph/api/test_graph_route.py
def test_build_graph_payload_deterministic_byte_equal():
    """Same (decision, pool, report) → byte-identical GraphPayload JSON across runs."""
    payload_1 = build_graph_payload(run_id, decision, pool, report).model_dump_json(sort_keys=True)
    payload_2 = build_graph_payload(run_id, decision, pool, report).model_dump_json(sort_keys=True)
    assert payload_1 == payload_2

def test_provenance_tokens_become_cites_edges():
    """A sentence with [#ev:src_42:10-25] gets one cites edge from sentence → src_42."""

def test_contradictions_become_contradicts_edges():
    """Pairs in contradictions.json → contradicts edges (red layer)."""

def test_compound_parent_uses_top_level_position_field():
    """Per DECISION.md P1-3.1: compound parent uses element top-level position field, NOT data.position."""

def test_elements_hash_is_sha256_canonical():
    """elements_hash is SHA256(sorted-keys JSON of elements), deterministic across reruns."""

def test_route_404_for_missing_run():
def test_route_422_for_in_progress_run():
def test_route_200_for_completed_run_includes_all_node_types():
```

## Direct questions for Codex iter 1

1. **Server-side layout architecture (Option A/B/C)?** This is the key design question. Without your input I'd go Option B. Open to changing.
2. **Schema correctness?** Pydantic models above — anything wrong with NodeData / Position / ClaimNode (top-level `position`) given DECISION.md iter-3 fix?
3. **Builder approach.** Pure-function `build_graph_payload(decision, pool, report)` separated from HTTP route — testability OK, or should the route do the assembly inline?
4. **`elements_hash` as SHA256 of sorted-keys JSON** — is this the right cache key for the client-side layout cache? Any edge case I'm missing (e.g. float serialization variance)?
5. **Run storage lookup.** How does the route find the (decision, pool, report) triple for a given run_id? Existing patterns: `/api/inspector/runs/{slug}/...` uses a filesystem-based audit_ir lookup. Should `graph_route` follow that, or use a different storage path?
6. **LOC budget.** Estimate ~150 LOC if Option B (no layout solver), ~230 LOC if Option A (Node subprocess wrapper). Acceptable, or split further?

## Output schema (terse)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
layout_option_pick: A | B | C
acceptable_loc_estimate: <int>
remaining_blockers: [...]
```
