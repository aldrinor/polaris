HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — brief iter 2 (4 P1 fixes from iter 1)

Status from iter 1: `convergence_call: continue`, `layout_option_pick: B` ✓, `acceptable_loc_estimate: 180` ✓. Library + layout architecture agreed. 4 P1 blockers all schema/input-contract issues.

## P1 fixes

### P1-1.1 — Run input source: AuditIR filesystem layout via `inspector_router.find_run_by_id`

After grepping `src/polaris_graph/audit_ir/inspector_router.py` (line 477: `list_runs()`, line 2577: `find_run_by_id(...)`):

The existing inspector router (mounted at `/api/inspector/...`) loads runs from the AuditIR filesystem (V30/audit_ir dataclass layout). Each run has `run_id` and an on-disk path with `report.md`, `verified_report.json` (Pydantic), `evidence_pool.json`, `frame_coverage.json` (inline in VerifiedReport per `FrameCoverage` model).

**Canonical input contract:**
```python
from polaris_graph.audit_ir.inspector_router import find_run_by_id
# returns a RunSummary with attributes: run_id, slug, audit_ir_path, has_verified_report, ...
summary = find_run_by_id(run_id)
if summary is None:
    raise HTTPException(404, "run not found")
verified_report = load_verified_report_json(summary.audit_ir_path)  # existing util
evidence_pool = load_evidence_pool_json(summary.audit_ir_path)      # existing util
```

`build_graph_payload(verified_report, evidence_pool)` becomes the pure-function transformation. ScopeDecision is NOT needed — `VerifiedReport` already carries `frame_coverage` and section structure.

### P1-1.2 — Frame nodes from `VerifiedReport.frame_coverage`

`VerifiedReport.frame_coverage: FrameCoverage` contains:
- `entities: list[FrameEntity]` — each with `name`, `covered: bool`, `gap: FrameGap | None`
- This IS the frame_manifest data. No separate template lookup needed.

Frame nodes: one per `frame_coverage.entities[].name`. Tier-equivalent attribute = covered/gapped status.

### P1-1.3 — Drop compound parents in v1; use membership edges only

**New NodeType taxonomy (no compound parent attribute):**

```python
NodeType = Literal["sentence", "source", "section", "frame"]
```

`section` becomes its own node type (replaces compound parent). Sentences connect to their section via `section_member` edge; sections cluster via fcose layout, no compound nesting.

**Removed from schema:** `NodeData.parent` (no longer needed; section_member edge replaces it).

### P1-1.4 — Contradiction edges from `VerifiedReport.sections[].sentences[].contradiction.sides`

`ContradictionSignal` (lines 271-319 of `verified_report.py`) has:
- `sides: list[ContradictionSide]` — each carries `source_id` + per-source detail
- `kind: "multi_source" | "self_contradiction"`

**Edge derivation:**
- For each sentence with `contradiction` set:
  - `multi_source`: pairwise contradicts edges between every pair of `sides[].source_id`
  - `self_contradiction`: single contradicts edge from source to itself (rendered as self-loop OR converted to a contradicts edge from sentence → source with classes='self_contradiction')

## P2 fixes

### P2-1.1 — Canonical JSON serialization for hash

Drop `model_dump_json(sort_keys=True)` (local Pydantic doesn't support it). Use:

```python
import json
elements_dict = payload.elements.model_dump(mode="json")
# Strip positions if present, sort node/edge lists by id
elements_dict["nodes"].sort(key=lambda n: n["data"]["id"])
elements_dict["edges"].sort(key=lambda e: e["data"]["id"])
for node in elements_dict["nodes"]:
    node.pop("position", None)
canonical_json = json.dumps(elements_dict, sort_keys=True, separators=(",", ":"))
elements_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
```

### P2-1.2 — Kind-prefixed node IDs to prevent collision

```
sentence node id format:  "sent:" + sentence_id
source node id format:    "src:" + source_id
section node id format:   "section:" + section_slug
frame node id format:     "frame:" + frame_name_slug
```

Prevents `src_42` (source) colliding with `sent_42` (sentence) or `frame_42` (frame entity).

### P2-1.3 — `acceptance` line in DECISION.md updated

DECISION.md iter-3 said "server-side fcose pre-layout." Iter-2 of THIS brief moves layout to client-side Web Worker (Option B). DECISION.md becomes stale. I'll patch it in this PR's first commit OR as a follow-up to I-snowball-002 — your call.

### P2-1.4 — `T1-T7` future-proof

Confirmed intentional (per Carney plan policy/regulatory tiers). Frozen as is.

## Revised schema (final for iter 2)

```python
# src/polaris_graph/api/graph_route.py (NEW)
from __future__ import annotations
import hashlib
import json
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from polaris_graph.audit_ir.inspector_router import find_run_by_id
from polaris_graph.generator2.verified_report import (
    VerifiedReport,
    ContradictionSignal,
)
from polaris_graph.retrieval2.evidence_pool import EvidencePool

router = APIRouter(tags=["graph"])

# ----- Type literals -----
NodeType = Literal["sentence", "source", "section", "frame"]
EdgeType = Literal[
    "cites",
    "co_cites_default_off",
    "contradicts",
    "section_member",
    "frame_member",
]
Tier = Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"]

# ----- Models -----
class NodeData(BaseModel):
    id: str = Field(min_length=1, max_length=300)        # kind-prefixed: "sent:42", "src:abc", "section:safety", "frame:bp"
    type: NodeType
    label: str = Field(min_length=1, max_length=500)
    tier: Tier | None = None                              # source nodes only
    sentence_text: str | None = None                      # sentence nodes only
    source_url: str | None = None                         # source nodes only
    covered: bool | None = None                           # frame nodes only

class Position(BaseModel):
    x: float
    y: float

class ClaimNode(BaseModel):
    data: NodeData
    position: Position | None = None                      # Option B: None on server; client Web Worker populates

class EdgeData(BaseModel):
    id: str = Field(min_length=1, max_length=300)
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
    elements_hash: str = Field(min_length=64, max_length=64)
    schema_version: Literal["1.0"] = "1.0"

# ----- Builder (pure function) -----
def build_graph_payload(
    run_id: str,
    verified_report: VerifiedReport,
    evidence_pool: EvidencePool,
) -> GraphPayload:
    """Deterministic builder. Same (report, pool) → byte-identical canonical JSON."""
    nodes: list[ClaimNode] = []
    edges: list[ClaimEdge] = []

    # 1. Source nodes (one per evidence_pool entry)
    for src in evidence_pool.sources:
        nodes.append(ClaimNode(data=NodeData(
            id=f"src:{src.source_id}",
            type="source",
            label=src.short_label or src.source_id,
            tier=src.tier if src.tier in {"T1","T2","T3","T4","T5","T6","T7"} else None,
            source_url=str(src.url) if src.url else None,
        )))

    # 2. Section nodes (one per VerifiedReport section)
    for section in verified_report.sections:
        nodes.append(ClaimNode(data=NodeData(
            id=f"section:{section.section_id}",
            type="section",
            label=section.title,
        )))

    # 3. Frame nodes (one per frame_coverage.entities entry)
    if verified_report.frame_coverage:
        for entity in verified_report.frame_coverage.entities:
            slug = _slugify(entity.name)
            nodes.append(ClaimNode(data=NodeData(
                id=f"frame:{slug}",
                type="frame",
                label=entity.name,
                covered=entity.covered,
            )))

    # 4. Sentence nodes + section_member edges + cites edges + contradicts edges
    for section in verified_report.sections:
        for sent in section.sentences:
            sent_id = f"sent:{sent.sentence_id}"
            nodes.append(ClaimNode(data=NodeData(
                id=sent_id,
                type="sentence",
                label=_truncate(sent.text, 100),
                sentence_text=sent.text,
            )))
            # section_member edge
            edges.append(ClaimEdge(data=EdgeData(
                id=f"membersec:{sent_id}:{section.section_id}",
                source=sent_id,
                target=f"section:{section.section_id}",
                edge_type="section_member",
            )))
            # cites edges (from provenance tokens)
            for token in _parse_provenance_tokens(sent.text):
                edges.append(ClaimEdge(data=EdgeData(
                    id=f"cite:{sent_id}:src:{token.source_id}",
                    source=sent_id,
                    target=f"src:{token.source_id}",
                    edge_type="cites",
                )))
            # contradicts edges (pairwise from ContradictionSignal.sides)
            if sent.contradiction:
                yield_contradicts_edges(sent_id, sent.contradiction, edges)

    # 5. Canonical hash (positions stripped, lists sorted by id)
    elements_dict = GraphElements(nodes=nodes, edges=edges).model_dump(mode="json")
    elements_dict["nodes"].sort(key=lambda n: n["data"]["id"])
    elements_dict["edges"].sort(key=lambda e: e["data"]["id"])
    for n in elements_dict["nodes"]:
        n.pop("position", None)
    canonical_json = json.dumps(elements_dict, sort_keys=True, separators=(",", ":"))
    elements_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return GraphPayload(
        elements=GraphElements(nodes=nodes, edges=edges),
        run_id=run_id,
        elements_hash=elements_hash,
    )

# ----- Route -----
@router.get("/runs/{run_id}/graph", response_model=GraphPayload)
def get_run_graph(run_id: str) -> GraphPayload:
    summary = find_run_by_id(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not summary.has_verified_report:
        raise HTTPException(status_code=422, detail="run is still in progress or aborted")
    verified_report = load_verified_report(summary.audit_ir_path)
    evidence_pool = load_evidence_pool(summary.audit_ir_path)
    return build_graph_payload(run_id, verified_report, evidence_pool)
```

## Files I have ALSO checked and they're clean (re-verified)

- `src/polaris_graph/audit_ir/inspector_router.py:477` (`list_runs`) + `:2577` (`find_run_by_id`)
- `src/polaris_graph/generator2/verified_report.py:271-319` (`ContradictionSignal` with `.sides` + `.kind`)
- `src/polaris_graph/generator2/verified_report.py:340-353` (`FrameGap` enum + `FrameCoverage` model)
- `src/polaris_graph/retrieval2/evidence_pool.py` (`EvidencePool.sources` with `source_id`, `tier`, `url`)
- `src/polaris_graph/audit_bundle/bundle_schema.py` (Pydantic + field_validator pattern)
- `src/polaris_v6/api/app.py` (FastAPI mounting; will add `graph_router`)

## Direct questions for Codex iter 2

1. **Input contract correctly resolved?** Using `inspector_router.find_run_by_id` + `VerifiedReport.frame_coverage` + `VerifiedReport.sections[].sentences[].contradiction.sides`. Acceptable?
2. **No compound parents — section is now an independent node type with section_member edges.** Acceptable, or do you want compound nesting back (with section being the parent and frame being a separate ungrouped node type)?
3. **Self-contradiction edges** — for `kind='self_contradiction'`, my plan is a single edge `src:X → src:X` with `classes='self_contradiction'`. Acceptable, or should it be modeled differently (e.g., 2 spans become 2 sub-source-nodes)?
4. **Schema details** — `tier: Tier | None` (only set for source nodes), `covered: bool | None` (only set for frame nodes), `sentence_text` only for sentence nodes — clean? Or would per-NodeType subclass be cleaner Pydantic?
5. **LOC estimate** — builder + route + Pydantic models ≈ 200 LOC; tests separate file ≈ 100 LOC. Within cap?

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
