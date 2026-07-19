"""Health endpoint for liveness + readiness probes."""

from fastapi import APIRouter
from pydantic import BaseModel

from polaris_v6 import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health-probe payload: liveness `status` plus the running package `version`."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness/readiness probe returning `status: ok` and the package version."""
    return HealthResponse(status="ok", version=__version__)
