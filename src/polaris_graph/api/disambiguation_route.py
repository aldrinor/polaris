"""F2 disambiguation route (I-f2-003): cluster + label candidate snippets."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from polaris_graph.clinical_generator.real_completion import OPENROUTER_ENDPOINT, _extract_text
from polaris_graph.intake.cluster_labeler import ClusterLabelClient, label_clusters
from polaris_graph.intake.disambiguation_clusterer import cluster_candidates

router = APIRouter(tags=["disambiguation"])


class CandidateSnippet(BaseModel):
    text: str = Field(min_length=1)
    embedding: list[float] = Field(min_length=1)


class DisambiguationRequest(BaseModel):
    candidates: list[CandidateSnippet] = Field(min_length=1)
    min_cluster_size: int = Field(default=2, ge=2)
    max_snippets_per_cluster: int = Field(default=3, ge=1)


class ClusterPayload(BaseModel):
    cluster_id: int
    label: str
    sample_snippets: list[str]


class DisambiguationResponse(BaseModel):
    is_ambiguous: bool
    num_clusters: int
    clusters: list[ClusterPayload]
    server_time_utc: str


class _OpenRouterLabelClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key, self.model = api_key, model

    def complete(self, prompt: str, *, max_tokens: int = 50) -> str:
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                   "HTTP-Referer": "https://polaris-canada.local",
                   "X-Title": "POLARIS F2 Disambiguation"}
        with httpx.Client() as client:
            r = client.post(OPENROUTER_ENDPOINT, json=body, headers=headers, timeout=30.0)
            r.raise_for_status()
        text = _extract_text(r.json())
        if not text.strip():
            raise RuntimeError("OpenRouter returned empty disambiguation label")
        return text


def _make_openrouter_label_client() -> ClusterLabelClient | None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("OPENROUTER_DEFAULT_MODEL", "").strip() or "deepseek/deepseek-v4-pro"
    return _OpenRouterLabelClient(api_key=key, model=model)


def get_label_client() -> ClusterLabelClient | None: return _make_openrouter_label_client()


@router.post("/disambiguation", response_model=None)
def post_disambiguation(req: DisambiguationRequest,
        client: ClusterLabelClient | None = Depends(get_label_client)) -> DisambiguationResponse:
    dim = len(req.candidates[0].embedding)
    if any(len(c.embedding) != dim for c in req.candidates):
        raise HTTPException(status_code=400, detail={"error": True,
            "code": "embedding_dim_mismatch",
            "message": f"All candidate embeddings must have dim={dim}."})
    embeddings = np.array([c.embedding for c in req.candidates], dtype=np.float64)
    cr = cluster_candidates(embeddings, min_cluster_size=req.min_cluster_size)
    now_z = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if cr.num_clusters in (0, 1):
        return DisambiguationResponse(is_ambiguous=False, num_clusters=cr.num_clusters,
            clusters=[], server_time_utc=now_z)
    if client is None:
        raise HTTPException(status_code=503, detail={"error": True,
            "code": "label_client_unavailable",
            "message": "OPENROUTER_API_KEY is unset; cannot label clusters."})
    labeled = label_clusters(cr, [c.text for c in req.candidates], client,
        max_snippets_per_cluster=req.max_snippets_per_cluster)
    return DisambiguationResponse(is_ambiguous=True, num_clusters=cr.num_clusters,
        clusters=[ClusterPayload(cluster_id=lc.cluster_id, label=lc.label,
            sample_snippets=lc.sample_snippets) for lc in labeled],
        server_time_utc=now_z)


@router.get("/disambiguation/health")
def get_disambiguation_health() -> dict[str, Any]:
    return {"status": "ok", "stages": ["cluster_candidates", "label_clusters"],
            "label_client": "openrouter" if get_label_client() is not None else "sentinel"}
