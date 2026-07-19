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
    """One candidate snippet to disambiguate: its text and its embedding vector.

    `embedding` must be non-empty; all snippets in a request must share the same
    dimensionality (enforced by the route, not the model).
    """

    text: str = Field(min_length=1)
    embedding: list[float] = Field(min_length=1)


class DisambiguationRequest(BaseModel):
    """Request body for `POST /disambiguation`.

    Carries the candidate snippets to cluster plus clustering knobs:
    `min_cluster_size` (minimum members for a cluster to form) and
    `max_snippets_per_cluster` (how many sample snippets each labeled cluster
    surfaces). At least one candidate is required.
    """

    candidates: list[CandidateSnippet] = Field(min_length=1)
    min_cluster_size: int = Field(default=2, ge=2)
    max_snippets_per_cluster: int = Field(default=3, ge=1)


class ClusterPayload(BaseModel):
    """One labeled cluster in the response: its id, LLM-assigned label, and samples."""

    cluster_id: int
    label: str
    sample_snippets: list[str]


class DisambiguationResponse(BaseModel):
    """Response body for `POST /disambiguation`.

    `is_ambiguous` is True only when two or more clusters formed; when False
    (0 or 1 cluster) `clusters` is empty and no labeling was performed.
    `server_time_utc` is an ISO-8601 timestamp with a trailing `Z`.
    """

    is_ambiguous: bool
    num_clusters: int
    clusters: list[ClusterPayload]
    server_time_utc: str


class _OpenRouterLabelClient:
    """`ClusterLabelClient` implementation backed by the OpenRouter chat API."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key, self.model = api_key, model

    def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        """Return the model's text completion for `prompt`.

        `max_tokens` is a billing cap, not a target; it is raised to the
        reasoning-first floor (`PG_DISAMBIG_LABEL_MAX_TOKENS`, default 16384)
        when unset or below it, so reasoning-first models are not truncated
        mid-thought into empty content. Raises `RuntimeError` if OpenRouter
        returns empty text, or `httpx.HTTPStatusError` on a non-2xx response.
        """
        # I-arch-003 (#1253): self.model is reasoning-first (deepseek); the old 50-token default truncated
        # mid-reasoning -> empty content -> RuntimeError. Un-starve to the reasoning-first floor + reasoning ON
        # at max effort (env-overridable). The label output is short; max_tokens is a cap billed by usage.
        _floor = int(os.environ.get("PG_DISAMBIG_LABEL_MAX_TOKENS", "16384") or "16384")
        if max_tokens is None or max_tokens < _floor:
            max_tokens = _floor
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0, "max_tokens": max_tokens,
                "reasoning": {"effort": os.environ.get("PG_DISAMBIG_REASONING_EFFORT", "high") or "high"}}
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


def get_label_client() -> ClusterLabelClient | None:
    """FastAPI dependency yielding a cluster-label client, or None if unconfigured.

    Returns an OpenRouter-backed client when `OPENROUTER_API_KEY` is set,
    otherwise None (the route then rejects ambiguous inputs with 503).
    """
    return _make_openrouter_label_client()


@router.post("/disambiguation", response_model=None)
def post_disambiguation(req: DisambiguationRequest,
        client: ClusterLabelClient | None = Depends(get_label_client)) -> DisambiguationResponse:
    """Cluster candidate snippet embeddings and label ambiguous clusters.

    Returns a non-ambiguous response (empty `clusters`) when fewer than two
    clusters form; otherwise labels each cluster via the injected client.

    Raises:
        HTTPException 400: candidate embeddings have mismatched dimensions.
        HTTPException 503: input is ambiguous but no label client is configured.
    """
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
    """Liveness probe for the disambiguation route.

    Returns a static `status: ok` plus the pipeline stage names and whether a
    real (`openrouter`) or sentinel label client is currently configured.
    """
    return {"status": "ok", "stages": ["cluster_candidates", "label_clusters"],
            "label_client": "openrouter" if get_label_client() is not None else "sentinel"}
