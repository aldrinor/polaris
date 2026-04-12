"""
Mesh REST API — FastAPI server exposing mesh operations.

v1 design (CP-A lock):

  7 endpoints mirroring the CLI's 6 commands + a dry-run ask:
    POST /workspaces                          — create workspace
    GET  /workspaces                          — list workspaces
    POST /workspaces/{ws_id}/ask              — ask question (LLM compose)
    POST /workspaces/{ws_id}/ask/dry-run      — retrieve only, no LLM
    POST /workspaces/{ws_id}/ingest           — file upload
    GET  /workspaces/{ws_id}/stats            — workspace statistics
    GET  /workspaces/{ws_id}/entities/quarantined — FIX D2 quarantine queue

  Standalone FastAPI app. Store opened on startup via lifespan,
  shared via app.state.store. No auth for v1 (local tool).
  CORS allow_origins=["*"] for local development.

  Run:
    uvicorn src.polaris_graph.wiki.mesh.api.server:app --port 8100
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..store import MeshStore, MeshStoreError

DB_PATH = os.getenv("PG_MESH_DB", "mesh.db")


# ───── lifespan ─────

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = MeshStore.open(Path(DB_PATH), check_same_thread=False)
    yield
    app.state.store.close()


app = FastAPI(
    title="POLARIS Mesh API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _store() -> MeshStore:
    return app.state.store


# ───── request/response models ─────

class WorkspaceCreateRequest(BaseModel):
    name: str
    seed_question: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    source_count: int = 0
    claim_count: int = 0
    created_at: str = ""


class AskRequest(BaseModel):
    question: str
    parent_question_id: Optional[str] = None


class AskResponse(BaseModel):
    question_id: str
    answer_id: str
    answer_text: str
    gap_category: str
    bibliography: list[dict] = Field(default_factory=list)
    claim_ids_used: list[str] = Field(default_factory=list)


class DryRunResponse(BaseModel):
    gap_category: str
    seed_count: int
    entity_expansion_count: int
    walked_count: int
    exploration_count: int
    total_claims: int
    top_claims: list[dict] = Field(default_factory=list)


class StatsResponse(BaseModel):
    workspace_id: str
    name: str
    source_count: int
    claim_count: int
    gold_claims: int
    silver_claims: int
    bronze_claims: int
    flagged_claims: int
    quarantined_entities: int
    edge_count: int


# ───── routes ─────

@app.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(req: WorkspaceCreateRequest):
    try:
        ws_id = _store().create_workspace(
            name=req.name,
            root_question=req.seed_question,
        )
    except MeshStoreError as exc:
        raise HTTPException(400, str(exc))
    ws = _store().get_workspace(ws_id)
    return WorkspaceResponse(
        id=ws["id"],
        name=ws["name"],
        source_count=ws["source_count"],
        claim_count=ws["claim_count"],
        created_at=ws.get("created_at", ""),
    )


@app.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces():
    rows = _store()._conn.execute(
        "SELECT id, name, source_count, claim_count, created_at "
        "FROM workspaces ORDER BY created_at DESC"
    ).fetchall()
    return [
        WorkspaceResponse(
            id=r["id"], name=r["name"],
            source_count=r["source_count"],
            claim_count=r["claim_count"],
            created_at=r["created_at"] or "",
        )
        for r in rows
    ]


@app.post("/workspaces/{ws_id}/ask", response_model=AskResponse)
async def ask_question(ws_id: str, req: AskRequest):
    from ..qa.ask import ask

    try:
        client = _make_llm_client()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    try:
        result = await ask(
            client, _store(),
            workspace_id=ws_id,
            question_text=req.question,
            parent_question_id=req.parent_question_id,
        )
    except MeshStoreError as exc:
        raise HTTPException(400, str(exc))

    return AskResponse(
        question_id=result.question_id,
        answer_id=result.answer_id,
        answer_text=result.answer_text,
        gap_category=result.gap_category,
        bibliography=result.bibliography,
        claim_ids_used=result.claim_ids_used,
    )


@app.post("/workspaces/{ws_id}/ask/dry-run", response_model=DryRunResponse)
async def ask_dry_run(ws_id: str, req: AskRequest):
    from ..retrieve.lethal import lethal_retrieve

    try:
        result = lethal_retrieve(
            _store(),
            workspace_id=ws_id,
            question_text=req.question,
        )
    except MeshStoreError as exc:
        raise HTTPException(400, str(exc))

    top = []
    for cid, score in result.scored_claims[:10]:
        claim = _store().get_claim(cid)
        top.append({
            "claim_id": cid,
            "score": round(score, 4),
            "statement": claim["statement"][:120] if claim else "",
            "tier": claim["tier"] if claim else "",
        })

    return DryRunResponse(
        gap_category=result.gap_category,
        seed_count=result.seed_count,
        entity_expansion_count=result.entity_expansion_count,
        walked_count=result.walked_count,
        exploration_count=result.exploration_count,
        total_claims=len(result.scored_claims),
        top_claims=top,
    )


@app.post("/workspaces/{ws_id}/ingest")
async def ingest_file_upload(ws_id: str, file: UploadFile):
    from ..ingest import ingest_file

    suffix = Path(file.filename or "upload.txt").suffix
    with tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False, dir=tempfile.gettempdir(),
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        src_id, was_new = ingest_file(
            store=_store(),
            workspace_id=ws_id,
            file_path=tmp_path,
            kind="upload",
        )
    except MeshStoreError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "source_id": src_id,
        "was_new": was_new,
        "filename": file.filename,
    }


@app.get("/workspaces/{ws_id}/stats", response_model=StatsResponse)
async def get_stats(ws_id: str):
    try:
        stats = _store().workspace_stats(ws_id)
    except MeshStoreError as exc:
        raise HTTPException(404, str(exc))

    return StatsResponse(
        workspace_id=stats["id"],
        name=stats["name"],
        source_count=stats["source_count"],
        claim_count=stats["claim_count"],
        gold_claims=stats["gold_claims"],
        silver_claims=stats["silver_claims"],
        bronze_claims=stats["bronze_claims"],
        flagged_claims=stats["flagged_claims"],
        quarantined_entities=stats["quarantined_entities"],
        edge_count=stats["edge_count"],
    )


@app.get("/workspaces/{ws_id}/entities/quarantined")
async def get_quarantined_entities(ws_id: str):
    ws = _store().get_workspace(ws_id)
    if ws is None:
        raise HTTPException(404, f"Workspace not found: {ws_id}")

    entities = _store().get_quarantined_entities(ws_id)
    result = []
    for ent in entities:
        aliases_raw = ent.get("aliases", "[]")
        try:
            aliases = json.loads(aliases_raw) if aliases_raw else []
        except (ValueError, TypeError):
            aliases = []
        result.append({
            "id": ent["id"],
            "canonical_name": ent["canonical_name"],
            "entity_type": ent["entity_type"],
            "confidence": ent["confidence"],
            "times_referenced": ent.get("times_referenced", 0),
            "aliases": aliases,
        })
    return {"quarantined": result, "count": len(result)}


# ───── LLM client factory ─────

def _make_llm_client():
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        return OpenRouterClient()
    except ImportError:
        raise RuntimeError(
            "OpenRouterClient not available. Use the /dry-run endpoint "
            "for retrieval-only mode."
        )
