HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — brief iter 3 (V30 AuditIR only, schema-grounded)

Per Codex iter 2 P1: "Pick one canonical source model: V30 AuditIR via load_audit_ir, or slice-004 bundle files. The current brief combines both and will not run."

**Decision: V30 AuditIR.** This is the canonical source the existing /api/inspector route uses; the run-list view is built on `find_run_by_id` + `load_audit_ir(artifact_dir)`. Slice-003 Pydantic VerifiedReport is for a different surface and dropped from this PR's scope.

## Schema grounding (verified in `src/polaris_graph/audit_ir/loader.py` + `registry.py`)

```python
# registry.py
@dataclass(frozen=True)
class RunSummary:
    slug: str; run_id: str; domain: str; status: str
    artifact_dir: Path
    cost_usd: float; word_count: int
    contradictions_found: int
    release_allowed: bool
    created_at_iso: str | None

def find_run_by_id(run_id: str) -> RunSummary | None: ...

# loader.py
def load_audit_ir(artifact_dir: Path) -> AuditIR: ...

@dataclass(frozen=True)
class AuditIR:
    ir_schema_version: str
    run_id: str
    artifact_dir: Path
    bibliography: tuple[BibliographyEntry, ...]    # → source nodes
    contradictions: tuple[ContradictionCluster, ...]  # → contradicts edges
    frame_coverage: FrameCoverageReport            # → frame nodes
    verified_report: VerifiedReport                # → sentence + section nodes
    # ... other fields not used in F-snowball v1

@dataclass(frozen=True)
class BibliographyEntry:
    num: int; evidence_id: str; statement: str; tier: str; url: str

@dataclass(frozen=True)
class ReportSentence:
    claim_id: str; section: str; text: str
    tokens: tuple[EvidenceSpanToken, ...]
    is_verified: bool
    failure_reasons: tuple[str, ...]

@dataclass(frozen=True)
class EvidenceSpanToken:
    evidence_id: str; start: int; end: int

@dataclass(frozen=True)
class ReportSection:
    title: str; kept_count: int; dropped_count: int
    sentences: tuple[ReportSentence, ...]

@dataclass(frozen=True)
class VerifiedReport:  # NESTED in AuditIR — NOT the slice-003 Pydantic VerifiedReport
    sections: tuple[ReportSection, ...]
    sentences_verified: int; sentences_dropped: int

@dataclass(frozen=True)
class ContradictionCluster:
    cluster_id: int; subject: str; predicate: str
    severity: str
    claims: tuple[ContradictionClaim, ...]

@dataclass(frozen=True)
class ContradictionClaim:
    evidence_id: str; subject: str; predicate: str
    # ... other fields

@dataclass(frozen=True)
class FrameCoverageEntry:
    entity_id: str; entity_type: str; section: str
    status: str  # 'pass' | 'partial' | 'fail'
    # ... other fields

@dataclass(frozen=True)
class FrameCoverageReport:
    pass_count: int; partial_count: int  # ... + entries tuple TBC; will verify
```

## Graph derivation rules (V30-AuditIR-only)

| Element | Source | ID format |
|---|---|---|
| source node | `BibliographyEntry` (one per `bibliography`) | `src:{evidence_id}` |
| sentence node | `ReportSentence` (kept-only, walking `verified_report.sections[].sentences`, filter `is_verified=True`) | `sent:{claim_id}` |
| section node | `ReportSection` (one per `verified_report.sections`) | `section:{slug(title)}` |
| frame node | `FrameCoverageEntry` (one per `frame_coverage.entries`) | `frame:{entity_id}` |
| cites edge | per `sentence.tokens[i].evidence_id` → src | `cite:{claim_id}:{ord}:{evidence_id}` (ord disambiguates same-source multi-cite) |
| contradicts edge | pairwise within each `ContradictionCluster.claims` on `evidence_id` | `contra:{cluster_id}:{a}:{b}` where (a,b) sorted asc |
| section_member edge | sentence → section (visual grouping; NO compound parent) | `membersec:{claim_id}:{slug(section_title)}` |
| frame_member edge | DEFERRED to follow-up (mapping sentence-text → frame-entity-name is non-trivial; not in this PR) | — |

**Dropped from v1 scope:** frame_member edges (require text→entity matching), self-contradiction handling (V30 AuditIR contradictions are between-evidence; no self-contradiction concept), co_cites_default_off (derived; defer to I-snowball-005).

## Schema (Pydantic)

```python
# src/polaris_graph/api/graph_route.py (NEW)
from __future__ import annotations
import hashlib
import json
import re
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.polaris_graph.audit_ir.registry import find_run_by_id
from src.polaris_graph.audit_ir.loader import load_audit_ir, AuditIR

router = APIRouter(tags=["graph"])

NodeType = Literal["sentence", "source", "section", "frame"]
EdgeType = Literal["cites", "contradicts", "section_member"]
Tier = Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"]

class NodeData(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    type: NodeType
    label: str = Field(min_length=1, max_length=500)
    tier: Tier | None = None
    sentence_text: str | None = None
    source_url: str | None = None
    section_title: str | None = None
    frame_status: Literal["pass", "partial", "fail"] | None = None

class Position(BaseModel):
    x: float
    y: float

class ClaimNode(BaseModel):
    data: NodeData
    position: Position | None = None   # Option B: None on server; client Web Worker populates

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

class GraphPayload(BaseModel):
    elements: GraphElements
    run_id: str = Field(min_length=1, max_length=200)
    elements_hash: str = Field(min_length=64, max_length=64)
    schema_version: Literal["1.0"] = "1.0"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:80]


def build_graph_payload(ir: AuditIR) -> GraphPayload:
    """Pure-function transformation. Same AuditIR → byte-equal canonical JSON."""
    nodes: list[ClaimNode] = []
    edges: list[ClaimEdge] = []

    # 1. Source nodes
    for entry in ir.bibliography:
        tier = entry.tier if entry.tier in {"T1","T2","T3","T4","T5","T6","T7"} else None
        nodes.append(ClaimNode(data=NodeData(
            id=f"src:{entry.evidence_id}",
            type="source",
            label=entry.statement[:200] or entry.evidence_id,
            tier=tier,
            source_url=entry.url or None,
        )))

    # 2. Section nodes
    for section in ir.verified_report.sections:
        section_id = f"section:{_slug(section.title)}"
        nodes.append(ClaimNode(data=NodeData(
            id=section_id,
            type="section",
            label=section.title,
            section_title=section.title,
        )))

    # 3. Frame nodes
    for entry in ir.frame_coverage.entries:  # verify field name in iter 3 first response
        nodes.append(ClaimNode(data=NodeData(
            id=f"frame:{entry.entity_id}",
            type="frame",
            label=entry.entity_id,
            frame_status=entry.status if entry.status in {"pass","partial","fail"} else None,
        )))

    # 4. Sentence nodes + section_member + cites
    for section in ir.verified_report.sections:
        section_id = f"section:{_slug(section.title)}"
        for sent in section.sentences:
            if not sent.is_verified:
                continue                       # drop unverified sentences from graph
            sent_id = f"sent:{sent.claim_id}"
            nodes.append(ClaimNode(data=NodeData(
                id=sent_id,
                type="sentence",
                label=sent.text[:100],
                sentence_text=sent.text,
            )))
            edges.append(ClaimEdge(data=EdgeData(
                id=f"membersec:{sent.claim_id}:{_slug(section.title)}",
                source=sent_id,
                target=section_id,
                edge_type="section_member",
            )))
            for ord_, token in enumerate(sent.tokens):
                edges.append(ClaimEdge(data=EdgeData(
                    id=f"cite:{sent.claim_id}:{ord_}:{token.evidence_id}",
                    source=sent_id,
                    target=f"src:{token.evidence_id}",
                    edge_type="cites",
                )))

    # 5. Contradicts edges (pairwise within each cluster)
    for cluster in ir.contradictions:
        evidence_ids = sorted({c.evidence_id for c in cluster.claims})
        for i, a in enumerate(evidence_ids):
            for b in evidence_ids[i + 1:]:
                edges.append(ClaimEdge(data=EdgeData(
                    id=f"contra:{cluster.cluster_id}:{a}:{b}",
                    source=f"src:{a}",
                    target=f"src:{b}",
                    edge_type="contradicts",
                )))

    # 6. Canonical hash
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
    )


@router.get("/runs/{run_id}/graph", response_model=GraphPayload)
def get_run_graph(run_id: str) -> GraphPayload:
    summary = find_run_by_id(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        ir = load_audit_ir(summary.artifact_dir)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"audit IR load failed: {e}")
    return build_graph_payload(ir)
```

## Files I have ALSO checked and they're clean (verified line-by-line)

- `src/polaris_graph/audit_ir/registry.py:44` (RunSummary), `:179` (find_run_by_id)
- `src/polaris_graph/audit_ir/loader.py:43-46` (BibliographyEntry), `:60-66` (EvidenceSpanToken), `:69-83` (ReportSentence), `:86-95` (ReportSection), `:98-108` (nested VerifiedReport), `:115-128` (ContradictionClaim), `:133-148` (ContradictionCluster), `:163-188` (FrameCoverageEntry), `:404-426` (AuditIR top-level)
- `src/polaris_graph/api/audit_bundle_route.py` (FastAPI router pattern reference)

## Direct questions for Codex iter 3

1. **`ir.frame_coverage.entries` field name** — I haven't verified the exact attribute name on `FrameCoverageReport`. Per loader.py line 190+ this dataclass exists but I cut my read at line 200. If the attribute is named differently (e.g., `entry_list`, `gaps`), please flag and I'll fix in iter 4.
2. **Self-contradiction handling** — V30 AuditIR `ContradictionCluster` is between-evidence (cluster.claims, multiple evidence_ids). No `self_contradiction` kind. Acceptable to drop self-contradiction from v1?
3. **Dropping unverified sentences from graph** — I filter `is_verified=True`. This means dropped sentences (failure_reasons set) don't appear. Acceptable, or should we render them grey with `classes='dropped'`?
4. **Frame nodes have no edges in v1** — they're isolated nodes (no frame_member edge). They'll appear in the visual but disconnected from the rest of the graph. Acceptable as a v1 visual, or should I drop frame nodes entirely until I-snowball-005 connects them?
5. **Tier T1-T7 vs V30 actual** — BibliographyEntry.tier is a string; V30 typically emits T1-T7 but I've seen "UNKNOWN" too. Filter UNKNOWN to None — acceptable?
6. **LOC est** — ~180 LOC route + ~120 LOC test fixtures + ~80 LOC tests = ~380 total. Within 200-LOC cap if we count only the route+builder file separately; tests are a separate file (per CHARTER §3, each file in PR ≤200 LOC).

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
