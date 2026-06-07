"""FastAPI route for F-snowball claim-graph endpoint.

`GET /api/runs/{run_id}/graph` returns a cytoscape-format `GraphPayload`
built from the V30 AuditIR for one run. Server returns elements + a
canonical content hash; the client computes layout positions in a Web
Worker (DECISION.md Option B; positions are not populated server-side).

Per I-snowball-002 brief APPROVE'd by Codex iter 5 (2026-05-12).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from polaris_graph.audit_ir.loader import AuditIR

router = APIRouter(tags=["graph"])

# Lazy imports for audit_ir.{registry,loader} live inside `get_run_graph`
# (Codex diff iter 1 P1): module-level imports trigger src/__init__.py →
# .env load → optional real-backend wiring, which makes app startup +
# this module's import non-hermetic. Keep graph_route import cheap.

# ---------------------------------------------------------------------------
# Type literals
# ---------------------------------------------------------------------------

NodeType = Literal["sentence", "source", "section", "frame"]
EdgeType = Literal["cites", "contradicts", "section_member"]
Tier = Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
FrameStatus = Literal["pass", "partial", "fail"]

_VALID_TIERS = {"T1", "T2", "T3", "T4", "T5", "T6", "T7"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NodeData(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    type: NodeType
    label: str = Field(min_length=1, max_length=500)
    tier: Tier | None = None
    sentence_text: str | None = None
    source_url: str | None = None
    section_title: str | None = None
    frame_status: FrameStatus | None = None
    classes: str | None = None


class Position(BaseModel):
    x: float
    y: float


class ClaimNode(BaseModel):
    data: NodeData
    position: Position | None = None  # Option B: None server-side; client populates


class EdgeData(BaseModel):
    id: str = Field(min_length=1, max_length=400)
    source: str
    target: str
    edge_type: EdgeType


class ClaimEdge(BaseModel):
    data: EdgeData


class GraphElements(BaseModel):
    nodes: list[ClaimNode]
    edges: list[ClaimEdge]


class GraphDiagnostics(BaseModel):
    bibliography_count: int
    fallback_source_count: int  # unique evidence_ids referenced but absent from bibliography
    missing_reference_occurrence_count: int  # total references (with duplicates)
    referenced_unknown_evidence_ids: list[str] = Field(default_factory=list)


class GraphPayload(BaseModel):
    elements: GraphElements
    run_id: str = Field(min_length=1, max_length=200)
    elements_hash: str = Field(min_length=64, max_length=64)
    diagnostics: GraphDiagnostics
    schema_version: Literal["1.0"] = "1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:80] or "section"


def _normalize_frame_status(raw: str) -> FrameStatus | None:
    if raw == "pass":
        return "pass"
    if raw == "partial":
        return "partial"
    if raw.startswith("fail"):
        return "fail"
    # I-ready-017 FX-07b leg-2 (#1111) — Codex diff-gate iter-1 P2: the
    # frame_coverage honesty override emits status="generation_failed" for a
    # contract slot whose drafted prose was fully dropped by strict_verify
    # (a pipeline fault — zero verified content for that frame). Map it to
    # "fail" so the graph inspector renders the frame node as a failed slot
    # instead of leaving frame_status null (uncolored). is_pipeline_fault on
    # the manifest still carries the finer-grained classification.
    if raw == "generation_failed":
        return "fail"
    # I-ready-017 FX-07b leg-2 (#1111) root-cause design: a validated entity that
    # produced zero substantive verified prose (curator must supply licensed
    # full-text). Renders as a failed frame in the inspector; human_completion_
    # eligible / is_pipeline_fault on the manifest carry the curator-vs-engineer
    # routing.
    if raw == "curator_gap_no_substantive_content":
        return "fail"
    return None


# ---------------------------------------------------------------------------
# Builder (pure function — easy to test)
# ---------------------------------------------------------------------------

def build_graph_payload(ir: "AuditIR") -> GraphPayload:
    """Transform AuditIR into cytoscape-format GraphPayload (deterministic)."""
    # 1. Bibliography source nodes
    bib_ids: set[str] = set()
    nodes: list[ClaimNode] = []
    for entry in ir.bibliography:
        bib_ids.add(entry.evidence_id)
        tier = entry.tier if entry.tier in _VALID_TIERS else None
        label = (entry.statement or entry.evidence_id)[:200]
        nodes.append(ClaimNode(data=NodeData(
            id=f"src:{entry.evidence_id}", type="source", label=label,
            tier=tier, source_url=entry.url or None,
        )))

    # 2. Collect all referenced evidence_ids from sentence tokens + contradictions
    referenced_occurrences: list[str] = []
    for section in ir.verified_report.sections:
        for sent in section.sentences:
            if sent.is_verified:
                for tok in sent.tokens:
                    referenced_occurrences.append(tok.evidence_id)
    for cluster in ir.contradictions:
        for claim in cluster.claims:
            referenced_occurrences.append(claim.evidence_id)
    referenced_unique = set(referenced_occurrences)

    # 3. Fallback source nodes for referenced-but-missing-from-bibliography
    missing_unique = sorted(referenced_unique - bib_ids)
    for eid in missing_unique:
        nodes.append(ClaimNode(data=NodeData(
            id=f"src:{eid}", type="source", label=eid, classes="bibliography_missing",
        )))
    valid_source_ids = bib_ids | set(missing_unique)

    # 4. Section nodes
    for section in ir.verified_report.sections:
        nodes.append(ClaimNode(data=NodeData(
            id=f"section:{_slug(section.title)}", type="section",
            label=section.title, section_title=section.title,
        )))

    # 5. Frame nodes (FrameCoverageReport.entries per AuditIR schema)
    for entry in ir.frame_coverage.entries:
        nodes.append(ClaimNode(data=NodeData(
            id=f"frame:{entry.entity_id}", type="frame", label=entry.entity_id,
            frame_status=_normalize_frame_status(entry.status),
        )))

    # 6. Sentence nodes + section_member + cites edges
    edges: list[ClaimEdge] = []
    for section in ir.verified_report.sections:
        sec_id = f"section:{_slug(section.title)}"
        for sent in section.sentences:
            if not sent.is_verified:
                continue
            sent_id = f"sent:{sent.claim_id}"
            nodes.append(ClaimNode(data=NodeData(
                id=sent_id, type="sentence",
                label=sent.text[:100], sentence_text=sent.text,
            )))
            edges.append(ClaimEdge(data=EdgeData(
                id=f"membersec:{sent.claim_id}:{_slug(section.title)}",
                source=sent_id, target=sec_id, edge_type="section_member",
            )))
            for ord_, tok in enumerate(sent.tokens):
                if tok.evidence_id not in valid_source_ids:
                    continue  # defensive — should not happen given fallback creation
                edges.append(ClaimEdge(data=EdgeData(
                    id=f"cite:{sent.claim_id}:{ord_}:{tok.evidence_id}",
                    source=sent_id, target=f"src:{tok.evidence_id}", edge_type="cites",
                )))

    # 7. Contradicts edges (pairwise within each cluster; skip self-contradictions)
    for cluster in ir.contradictions:
        evidence_ids = sorted({c.evidence_id for c in cluster.claims if c.evidence_id in valid_source_ids})
        for i, a in enumerate(evidence_ids):
            for b in evidence_ids[i + 1:]:
                edges.append(ClaimEdge(data=EdgeData(
                    id=f"contra:{cluster.cluster_id}:{a}:{b}",
                    source=f"src:{a}", target=f"src:{b}", edge_type="contradicts",
                )))

    # 8. Canonical content hash (position-stripped, sorted by id)
    elements_dict = GraphElements(nodes=nodes, edges=edges).model_dump(mode="json")
    elements_dict["nodes"].sort(key=lambda n: n["data"]["id"])
    elements_dict["edges"].sort(key=lambda e: e["data"]["id"])
    for n in elements_dict["nodes"]:
        n.pop("position", None)
    canonical = json.dumps(elements_dict, sort_keys=True, separators=(",", ":"))
    elements_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return GraphPayload(
        elements=GraphElements(nodes=nodes, edges=edges),
        run_id=ir.run_id,
        elements_hash=elements_hash,
        diagnostics=GraphDiagnostics(
            bibliography_count=len(bib_ids),
            fallback_source_count=len(missing_unique),
            missing_reference_occurrence_count=sum(
                1 for eid in referenced_occurrences if eid not in bib_ids
            ),
            referenced_unknown_evidence_ids=missing_unique,
        ),
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/graph", response_model=GraphPayload)
def get_run_graph(run_id: str) -> GraphPayload:
    """Return cytoscape-format graph payload for a completed run."""
    # Lazy import (Codex diff iter 1 P1): avoid loading audit_ir + .env at
    # module load / app startup time.
    from polaris_graph.audit_ir.loader import load_audit_ir
    from polaris_graph.audit_ir.registry import find_run_by_id

    summary = find_run_by_id(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        ir = load_audit_ir(summary.artifact_dir)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=422, detail=f"audit IR load failed: {exc}")
    return build_graph_payload(ir)
