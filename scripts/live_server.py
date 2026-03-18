"""
Live monitoring server for POLARIS pipeline.

FastAPI application serving a live dashboard via HTTP, streaming pipeline
trace events via SSE, and optionally spawning a Cloudflare Quick Tunnel
for remote access.

Endpoints:
    GET  /                  Serve live_dashboard.html
    GET  /health            Health check with uptime and pipeline status
    GET  /api/events        SSE stream of JSONL trace events (auto-reconnecting)
    GET  /api/snapshot       All events grouped by type + computed stats
    GET  /api/anomalies      Contents of logs/live_anomaly_log.jsonl
    GET  /api/cost           Cost ledger entries for current session
    POST /api/research       Start a new research pipeline run
    GET  /api/research/status Current research status
    POST /api/research/cancel Cancel running research
    GET  /api/research/history  List all completed research results
    POST /api/research/export/{vector_id}  Export result as PDF/HTML
    POST /api/campaigns            Create a new research campaign
    GET  /api/campaigns            List all campaigns
    GET  /api/campaigns/{id}       Get campaign details with per-query status
    POST /api/campaigns/{id}/start Start executing a campaign
    DELETE /api/campaigns/{id}     Cancel/delete a campaign
    POST /api/documents/upload       Upload a document for local RAG
    GET  /api/documents/list         List uploaded documents
    GET  /api/documents/{doc_id}     Get document metadata + preview
    DELETE /api/documents/{doc_id}   Remove an uploaded document
    POST /api/documents/{doc_id}/parse  Re-parse an uploaded document
    POST /api/documents/brief          Generate LLM source briefing
    GET  /api/research/checkpoints/{vector_id}  A2: List checkpoints for a run
    GET  /api/research/checkpoint/{vid}/{cpid}   A2: Get checkpoint state detail
    POST /api/research/rewind/{vid}/{cpid}       A2: Rewind and resume from checkpoint

CLI: python scripts/live_server.py --port 8765 [--trace logs/pg_trace_XXX.jsonl]

Zero new dependencies. Uses: FastAPI, uvicorn, sse-starlette, watchfiles, aiofiles.
"""

import argparse
import asyncio
import hashlib
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

# Ensure project root is in sys.path for src.* imports (LAW VI compliant)
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from starlette.templating import Jinja2Templates

import aiohttp

# Auth module (optional -- enabled by POLARIS_AUTH_ENABLED=1)
_AUTH_AVAILABLE = False
try:
    from src.auth.auth_routes import router as auth_router
    from src.auth.auth_middleware import get_current_user
    _AUTH_AVAILABLE = True
except ImportError:
    auth_router = None
    get_current_user = None

load_dotenv()

# Campaign persistence (Sprint 1, Task 1A.2)
_CAMPAIGN_STORE_AVAILABLE = False
try:
    from src.polaris_graph.memory.campaign_store import (
        init_campaign_store,
        save_campaign as _db_save_campaign,
        get_campaign as _db_get_campaign,
        list_campaigns as _db_list_campaigns,
        delete_campaign as _db_delete_campaign,
    )
    _CAMPAIGN_STORE_AVAILABLE = True
except ImportError:
    init_campaign_store = None  # type: ignore[assignment]
    _db_save_campaign = None  # type: ignore[assignment]

# Document ingester (A7.2 -- local document upload/parsing)
_DOCUMENT_INGESTER_AVAILABLE = False
_document_ingester = None
try:
    from src.polaris_graph.document_ingester import (
        DocumentIngester,
        DocumentIngestionError,
        DOCUMENT_STORAGE_DIR,
    )
    _document_ingester = DocumentIngester()
    _DOCUMENT_INGESTER_AVAILABLE = True
except ImportError:
    DocumentIngester = None  # type: ignore[assignment,misc]
    DocumentIngestionError = None  # type: ignore[assignment,misc]
    DOCUMENT_STORAGE_DIR = None  # type: ignore[assignment]

# OpenRouter LLM client (for source briefing)
_OPENROUTER_CLIENT_AVAILABLE = False
_openrouter_client = None
_brief_llm_client = None  # Separate client for briefs (may use different model)
try:
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    _openrouter_client = OpenRouterClient()
    _OPENROUTER_CLIENT_AVAILABLE = True

    # Brief-specific model override (defaults to main model if not set)
    _brief_model = os.getenv("PG_BRIEF_MODEL", "")
    if _brief_model:
        _brief_llm_client = OpenRouterClient(model=_brief_model)
        logger.info("Brief LLM client using model: %s", _brief_model)
    else:
        _brief_llm_client = _openrouter_client
except (ImportError, Exception):
    OpenRouterClient = None  # type: ignore[assignment,misc]

# Cloud storage providers (Google Drive, OneDrive, Dropbox)
_CLOUD_PROVIDERS_AVAILABLE = False
try:
    from scripts.cloud_providers import (
        cloud_provider_registry,
        get_cloud_status,
        validate_state as validate_cloud_state,
    )
    _CLOUD_PROVIDERS_AVAILABLE = True
except ImportError:
    cloud_provider_registry = {}  # type: ignore[assignment]
    get_cloud_status = None  # type: ignore[assignment]
    validate_cloud_state = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Module-level startup timestamp (for /health uptime)
# ---------------------------------------------------------------------------
_start_time: float = time.time()

# ---------------------------------------------------------------------------
# Configuration (LAW VI)
# ---------------------------------------------------------------------------
PG_LIVE_SERVER_PORT = int(os.getenv("PG_LIVE_SERVER_PORT", "8765"))
PG_LIVE_TRACE_DIR = os.getenv("PG_LIVE_TRACE_DIR", "logs")
PG_LIVE_ANOMALY_LOG = os.getenv(
    "PG_LIVE_ANOMALY_LOG", "logs/live_anomaly_log.jsonl"
)
PG_COST_LEDGER_PATH = os.getenv("PG_COST_LEDGER_PATH", "logs/pg_cost_ledger.jsonl")
POLARIS_DEPLOYMENT_MODE = os.getenv("POLARIS_DEPLOYMENT_MODE", "cloud")

# Max upload size for document ingestion (LAW VI)
PG_MAX_UPLOAD_SIZE_MB = int(os.getenv("PG_MAX_UPLOAD_SIZE_MB", "100"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("live_server")

# Log deployment mode at import time
logger.info("POLARIS deployment mode: %s", POLARIS_DEPLOYMENT_MODE)

# ---------------------------------------------------------------------------
# Template path
# ---------------------------------------------------------------------------
TEMPLATE_DIR = Path(__file__).parent / "templates"
DASHBOARD_HTML = TEMPLATE_DIR / "live_dashboard.html"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _compute_static_hash() -> str:
    """MD5 of all JS/CSS mtimes. Changes on any file edit + server restart."""
    h = hashlib.md5()
    for f in sorted(STATIC_DIR.rglob("*")):
        if f.suffix in (".js", ".css") and f.is_file():
            h.update(f"{f.relative_to(STATIC_DIR)}:{f.stat().st_mtime_ns}".encode())
    return h.hexdigest()[:12]


_STATIC_ASSET_HASH = _compute_static_hash()
_templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ---------------------------------------------------------------------------
# Static ETag cache (FIX-2: HTTP validation headers)
# ---------------------------------------------------------------------------
_STATIC_ETAGS: dict[str, tuple[str, float]] = {}


def _build_static_etags():
    """Build ETag cache from content hashes of all static files."""
    for f in STATIC_DIR.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(STATIC_DIR)).replace("\\", "/")
            content_hash = hashlib.md5(f.read_bytes()).hexdigest()[:16]
            _STATIC_ETAGS[rel] = (f'"{content_hash}"', f.stat().st_mtime)


_build_static_etags()


# ---------------------------------------------------------------------------
# Research request/response models (LAW VI -- no hard-coded values)
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    """Request body for POST /api/research."""

    query: str = Field(..., min_length=5, max_length=2000, description="Research question")
    depth: str = Field(
        default="standard",
        pattern="^(quick|standard|deep)$",
        description="Research depth: quick (1 iter), standard (3 iter), deep (5 iter)",
    )
    application: str = Field(default="general", description="Application domain")
    region: str = Field(default="GLOBAL", description="Geographic region")
    document_ids: list[str] = Field(default_factory=list, description="IDs of uploaded documents to include as GOLD sources")


class ResearchStatus(BaseModel):
    """Response body for GET /api/research/status."""

    running: bool = False
    vector_id: Optional[str] = None
    query: Optional[str] = None
    depth: Optional[str] = None
    started_at: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    result_path: Optional[str] = None


class SteerRequest(BaseModel):
    """Request body for POST /api/research/steer (D2 — live steering)."""

    directive: str = Field(..., min_length=5, max_length=2000, description="Steering directive to redirect running research")


class SourceSearchRequest(BaseModel):
    """Request body for POST /api/sources/search."""

    query: str = Field(..., min_length=2, max_length=500, description="Search query for web sources")
    source_type: str = Field(default="web", pattern="^(web|scholar|news)$", description="Type of search")
    max_results: int = Field(default=8, ge=1, le=20, description="Max results to return")


class SourceImportUrlRequest(BaseModel):
    """Request body for POST /api/sources/import-url."""

    url: str = Field(..., min_length=8, max_length=2000, description="URL to import as source")
    title: str = Field(default="", max_length=200, description="Optional title override")


class SourceImportTextRequest(BaseModel):
    """Request body for POST /api/sources/import-text."""

    text: str = Field(..., min_length=10, max_length=100000, description="Text content to import as source")
    title: str = Field(default="Pasted text", max_length=200, description="Source title")


# Depth presets -> (max_iterations, max_execution_minutes)
DEPTH_PRESETS: dict[str, tuple[int, int]] = {
    "quick": (2, int(os.getenv("PG_QUICK_MINUTES", "90"))),
    "standard": (3, int(os.getenv("PG_STANDARD_MINUTES", "120"))),
    "deep": (5, int(os.getenv("PG_DEEP_MINUTES", "180"))),
}


# ---------------------------------------------------------------------------
# Campaign request/response models (LAW VI -- no hard-coded values)
# ---------------------------------------------------------------------------
PG_CAMPAIGN_OUTPUT_DIR = os.getenv("PG_CAMPAIGN_OUTPUT_DIR", "outputs/campaigns")
PG_MAX_CAMPAIGN_QUERIES = int(os.getenv("PG_MAX_CAMPAIGN_QUERIES", "200"))
PG_CAMPAIGN_QUERY_MIN_LENGTH = int(os.getenv("PG_CAMPAIGN_QUERY_MIN_LENGTH", "5"))
PG_CAMPAIGN_QUERY_MAX_LENGTH = int(os.getenv("PG_CAMPAIGN_QUERY_MAX_LENGTH", "2000"))
PG_CAMPAIGN_NAME_MAX_LENGTH = int(os.getenv("PG_CAMPAIGN_NAME_MAX_LENGTH", "200"))
PG_CAMPAIGN_DESC_MAX_LENGTH = int(os.getenv("PG_CAMPAIGN_DESC_MAX_LENGTH", "2000"))


class CampaignRequest(BaseModel):
    """Request body for POST /api/campaigns."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=PG_CAMPAIGN_NAME_MAX_LENGTH,
        description="Campaign name",
    )
    description: str = Field(
        default="",
        max_length=PG_CAMPAIGN_DESC_MAX_LENGTH,
        description="Campaign description",
    )
    queries: list[str] = Field(
        ...,
        min_length=1,
        max_length=PG_MAX_CAMPAIGN_QUERIES,
        description="List of research queries to execute",
    )
    depth: str = Field(
        default="standard",
        pattern="^(quick|standard|deep)$",
        description="Research depth for all queries in the campaign",
    )


class CampaignQueryStatus(BaseModel):
    """Status of a single query within a campaign."""

    query: str
    status: str = "queued"  # queued | running | completed | failed | cancelled
    vector_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result_path: Optional[str] = None
    word_count: Optional[int] = None
    evidence_count: Optional[int] = None
    # Per-node stage tracking for Campaign Map (NOVA Phase 1)
    current_node: Optional[str] = None
    node_status: dict = {}       # {node_name: "idle"|"running"|"passed"|"warning"|"failed"}
    node_metrics: dict = {}      # {node_name: {evidence_count, faithfulness, duration_ms}}
    faithfulness: Optional[float] = None
    source_count: Optional[int] = None
    citation_count: Optional[int] = None
    elapsed_ms: Optional[int] = None
    # Per-query application/region for vector library campaigns
    application: Optional[str] = None
    region: Optional[str] = None


class CampaignData(BaseModel):
    """Full campaign data stored in memory."""

    campaign_id: str
    name: str
    description: str = ""
    depth: str = "standard"
    status: str = "created"  # created | running | completed | failed | cancelled
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    queries: list[CampaignQueryStatus] = []
    completed_count: int = 0
    failed_count: int = 0
    total_queries: int = 0
    campaign_context: list[dict[str, Any]] = []
    # Vector library campaign fields
    application: Optional[str] = None
    research_brief: Optional[str] = None


# ---------------------------------------------------------------------------
# Rate limiting (slowapi if available, fallback in-memory limiter)
# ---------------------------------------------------------------------------
RATE_LIMIT_AVAILABLE = False
limiter = None
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    RATE_LIMIT_AVAILABLE = True
    logger.info("Rate limiting: slowapi available")
except ImportError:
    logger.info("Rate limiting: slowapi not available, using in-memory fallback")


class InMemoryRateLimiter:
    """Simple in-memory rate limiter as fallback when slowapi is not installed.

    Tracks IP -> last_request_timestamp for a single endpoint.
    Thread-safe via asyncio (single-threaded event loop).
    """

    def __init__(self, window_seconds: int = 60):
        self._window = window_seconds
        self._requests: dict[str, float] = {}

    def check(self, client_ip: str) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        now = time.time()
        last = self._requests.get(client_ip, 0.0)
        if now - last < self._window:
            return False
        self._requests[client_ip] = now
        # Periodic cleanup: remove entries older than 2x window
        if len(self._requests) > 1000:
            cutoff = now - self._window * 2
            self._requests = {
                ip: ts for ip, ts in self._requests.items() if ts > cutoff
            }
        return True

    def seconds_remaining(self, client_ip: str) -> int:
        """Seconds until the client can make another request."""
        now = time.time()
        last = self._requests.get(client_ip, 0.0)
        remaining = self._window - (now - last)
        return max(0, int(remaining))


_fallback_limiter = InMemoryRateLimiter(window_seconds=60)


# ---------------------------------------------------------------------------
# Pipeline runner -- manages a single concurrent research run
# ---------------------------------------------------------------------------
class PipelineRunner:
    """Manages the lifecycle of a single research pipeline run.

    Only one run allowed at a time. The run executes in a background
    asyncio task so the /api/research endpoint returns immediately.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = ResearchStatus()
        self._lock = asyncio.Lock()
        self._running: bool = False
        self._tailer_watcher_task: Optional[asyncio.Task] = None
        # D2: Live steering state
        self._steer_directives: list[str] = []
        self._steer_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def status(self) -> ResearchStatus:
        s = self._status.model_copy()
        s.running = self.running
        return s

    async def start(
        self,
        query: str,
        depth: str,
        application: str,
        region: str,
        document_ids: list[str] | None = None,
        research_brief: str | None = None,
    ) -> str:
        """Start a new research run. Returns the vector_id."""
        async with self._lock:
            if self.running:
                raise RuntimeError("A research run is already in progress")

            # Validate depth against presets (strict -- no silent fallback)
            if depth not in DEPTH_PRESETS:
                raise ValueError(
                    f"Invalid depth '{depth}'. Must be one of: {list(DEPTH_PRESETS.keys())}"
                )

            # Generate vector_id from timestamp
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            query_hash = hashlib.sha256(query.encode()).hexdigest()[:6]
            vector_id = f"WEB_{ts}_{query_hash}"

            max_iterations, max_minutes = DEPTH_PRESETS[depth]

            self._status = ResearchStatus(
                running=True,
                vector_id=vector_id,
                query=query,
                depth=depth,
                started_at=datetime.now(timezone.utc).isoformat(),
                status="starting",
            )

            self._running = True
            self._task = asyncio.create_task(
                self._run_pipeline(
                    vector_id=vector_id,
                    query=query,
                    application=application,
                    region=region,
                    max_iterations=max_iterations,
                    max_minutes=max_minutes,
                    document_ids=document_ids or [],
                    research_brief=research_brief,
                )
            )

            return vector_id

    async def cancel(self) -> bool:
        """Cancel the running research. Returns True if cancelled."""
        async with self._lock:
            if not self.running or self._task is None:
                return False
            self._task.cancel()
            self._status.status = "cancelled"
            self._running = False
            return True

    async def steer(self, directive: str) -> bool:
        """Queue a steering directive for the running pipeline (D2)."""
        async with self._steer_lock:
            if not self.running:
                return False
            self._steer_directives.append(directive)
            logger.info("Steering directive queued: %s", directive[:100])
            return True

    async def _run_pipeline(
        self,
        vector_id: str,
        query: str,
        application: str,
        region: str,
        max_iterations: int,
        max_minutes: int,
        document_ids: list[str] | None = None,
        research_brief: str | None = None,
    ) -> None:
        """Execute the research pipeline in a background task."""
        global _tailer, _trace_path

        try:
            self._status.status = "running"

            # Import pipeline (deferred to avoid import-time side effects)
            # M6: Route to v3/v2/v1 based on PG_GRAPH_VERSION env var
            graph_version = os.getenv("PG_GRAPH_VERSION", "v1")
            if graph_version == "v3":
                from src.polaris_graph.graph_v3 import build_and_run_v3 as build_and_run
            elif os.getenv("PG_V2_ENABLED", "0") == "1":
                from src.polaris_graph.graph_v2 import build_and_run
            else:
                from src.polaris_graph.graph import build_and_run

            # Point the trace tailer to the new trace file
            new_trace_path = Path(PG_LIVE_TRACE_DIR) / f"pg_trace_{vector_id}.jsonl"

            # Clean up previous tailer watcher task if it exists
            if self._tailer_watcher_task is not None and not self._tailer_watcher_task.done():
                self._tailer_watcher_task.cancel()
                try:
                    await asyncio.shield(self._tailer_watcher_task)
                except (asyncio.CancelledError, Exception):
                    pass
                self._tailer_watcher_task = None

            _trace_path = new_trace_path
            _tailer = TraceTailer(new_trace_path)
            # Start watching the new trace file
            self._tailer_watcher_task = asyncio.create_task(_tailer.run_watcher())

            logger.info(
                "Starting research: vector_id=%s query=%r depth=%s/%d",
                vector_id,
                query[:80],
                max_iterations,
                max_minutes,
            )

            # D2: Create steer_callback closure for live steering
            def steer_callback() -> list[str]:
                """Drain pending steer directives (called from _evaluate node)."""
                directives = list(self._steer_directives)
                self._steer_directives.clear()
                return directives

            result = await build_and_run(
                vector_id=vector_id,
                query=query,
                application=application,
                region=region,
                max_iterations=max_iterations,
                max_execution_minutes=max_minutes,
                resume=False,
                enable_dashboard=False,  # No Rich terminal in server mode
                document_ids=document_ids or [],
                steer_callback=steer_callback,
                research_brief=research_brief,
            )

            self._status.status = result.get("status", "completed")
            result_path = f"outputs/polaris_graph/{vector_id}.json"
            self._status.result_path = result_path

            logger.info(
                "Research completed: vector_id=%s status=%s",
                vector_id,
                self._status.status,
            )

        except asyncio.CancelledError:
            self._status.status = "cancelled"
            logger.info("Research cancelled: vector_id=%s", vector_id)
        except Exception as exc:
            self._status.status = "failed"
            self._status.error = str(exc)[:500]
            logger.error(
                "Research failed: vector_id=%s error=%s\n%s",
                vector_id,
                exc,
                traceback.format_exc(),
            )
        finally:
            self._running = False


_runner = PipelineRunner()


# ---------------------------------------------------------------------------
# CampaignManager: manages multi-query research campaigns
# ---------------------------------------------------------------------------
class CampaignManager:
    """Manages campaign lifecycle and sequential query execution.

    Campaigns queue multiple research queries and execute them one at a time
    through the existing PipelineRunner. Supports snowball memory -- passing
    summaries from completed queries as context to subsequent queries.

    Thread-safety: relies on asyncio single-threaded event loop.
    Data persisted to SQLite via campaign_store (Sprint 1, Task 1A.2).
    Falls back to in-memory only if campaign_store is unavailable.
    """

    def __init__(self, runner: PipelineRunner) -> None:
        self._campaigns: dict[str, CampaignData] = {}
        self._runner = runner
        self._active_task: Optional[asyncio.Task] = None
        self._active_campaign_id: Optional[str] = None

    async def load_persisted_campaigns(self) -> None:
        """Load campaigns from SQLite on startup (Sprint 1, Task 1A.2)."""
        if not _CAMPAIGN_STORE_AVAILABLE or _db_list_campaigns is None:
            logger.debug("Campaign store not available, skipping load")
            return
        try:
            rows = await _db_list_campaigns()
            for row in rows:
                cid = row.get("campaign_id", "")
                if not cid or cid in self._campaigns:
                    continue
                queries_data = row.get("queries_json", [])
                queries = []
                for qd in (queries_data if isinstance(queries_data, list) else []):
                    if isinstance(qd, dict):
                        queries.append(CampaignQueryStatus(
                            query=qd.get("query", ""),
                            status=qd.get("status", "queued"),
                            vector_id=qd.get("vector_id"),
                            result_path=qd.get("result_path"),
                            started_at=qd.get("started_at"),
                            completed_at=qd.get("completed_at"),
                            error=qd.get("error"),
                            application=qd.get("application"),
                            region=qd.get("region"),
                        ))
                meta = row.get("metadata_json", {})
                if not isinstance(meta, dict):
                    meta = {}
                campaign = CampaignData(
                    campaign_id=cid,
                    name=row.get("name", ""),
                    description=row.get("description", ""),
                    depth=meta.get("depth", "standard"),
                    status=row.get("status", "created"),
                    created_at=meta.get("created_at", ""),
                    started_at=meta.get("started_at"),
                    completed_at=meta.get("completed_at"),
                    queries=queries,
                    total_queries=len(queries),
                    completed_count=meta.get("completed_count", 0),
                    failed_count=meta.get("failed_count", 0),
                    application=meta.get("application"),
                )
                self._campaigns[cid] = campaign
            if rows:
                logger.info(
                    "Loaded %d persisted campaigns from SQLite", len(rows),
                )
        except Exception as exc:
            logger.warning("Failed to load persisted campaigns: %s", exc)

    async def _persist_campaign(self, campaign: CampaignData) -> None:
        """Persist campaign state to SQLite (Sprint 1, Task 1A.2)."""
        if not _CAMPAIGN_STORE_AVAILABLE or _db_save_campaign is None:
            return
        try:
            queries_json = [
                {
                    "query": q.query,
                    "status": q.status,
                    "vector_id": q.vector_id,
                    "result_path": q.result_path,
                    "started_at": q.started_at,
                    "completed_at": q.completed_at,
                    "error": q.error,
                    "application": q.application,
                    "region": q.region,
                }
                for q in campaign.queries
            ]
            await _db_save_campaign({
                "campaign_id": campaign.campaign_id,
                "name": campaign.name,
                "description": campaign.description,
                "queries_json": queries_json,
                "status": campaign.status,
                "metadata_json": {
                    "depth": campaign.depth,
                    "created_at": campaign.created_at,
                    "started_at": campaign.started_at,
                    "completed_at": campaign.completed_at,
                    "completed_count": campaign.completed_count,
                    "failed_count": campaign.failed_count,
                    "total_queries": campaign.total_queries,
                    "application": campaign.application,
                },
            })
        except Exception as exc:
            logger.warning(
                "Failed to persist campaign %s: %s",
                campaign.campaign_id, exc,
            )

    def create(self, req: CampaignRequest) -> CampaignData:
        """Create a new campaign from request. Returns the CampaignData."""
        campaign_id = (
            f"CAMP_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            f"_{uuid.uuid4().hex[:6]}"
        )

        # Validate each query length
        validated_queries: list[CampaignQueryStatus] = []
        for raw_query in req.queries:
            q = raw_query.strip()
            if len(q) < PG_CAMPAIGN_QUERY_MIN_LENGTH:
                continue  # Skip empty/too-short lines
            if len(q) > PG_CAMPAIGN_QUERY_MAX_LENGTH:
                q = q[:PG_CAMPAIGN_QUERY_MAX_LENGTH]
            validated_queries.append(CampaignQueryStatus(query=q))

        if not validated_queries:
            raise ValueError(
                f"No valid queries provided. Each query must be at least "
                f"{PG_CAMPAIGN_QUERY_MIN_LENGTH} characters."
            )

        campaign = CampaignData(
            campaign_id=campaign_id,
            name=req.name,
            description=req.description,
            depth=req.depth,
            status="created",
            created_at=datetime.now(timezone.utc).isoformat(),
            queries=validated_queries,
            total_queries=len(validated_queries),
        )

        self._campaigns[campaign_id] = campaign

        # Persist to output directory
        output_dir = Path(PG_CAMPAIGN_OUTPUT_DIR) / campaign_id
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Campaign created: id=%s name=%r queries=%d depth=%s",
            campaign_id, req.name, len(validated_queries), req.depth,
        )
        return campaign

    def get(self, campaign_id: str) -> Optional[CampaignData]:
        """Get campaign by ID."""
        return self._campaigns.get(campaign_id)

    def list_all(self) -> list[dict[str, Any]]:
        """List all campaigns with summary info."""
        result = []
        for c in self._campaigns.values():
            result.append({
                "campaign_id": c.campaign_id,
                "name": c.name,
                "description": c.description[:200],
                "depth": c.depth,
                "status": c.status,
                "created_at": c.created_at,
                "started_at": c.started_at,
                "completed_at": c.completed_at,
                "total_queries": c.total_queries,
                "completed_count": c.completed_count,
                "failed_count": c.failed_count,
                "progress": (
                    f"{c.completed_count + c.failed_count}/{c.total_queries}"
                ),
            })
        # Sort by creation time descending
        result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return result

    def delete(self, campaign_id: str) -> bool:
        """Cancel and delete a campaign. Returns True if found."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return False

        # Cancel if running
        if (
            self._active_campaign_id == campaign_id
            and self._active_task is not None
        ):
            self._active_task.cancel()
            self._active_campaign_id = None
            self._active_task = None

        # Mark remaining queued queries as cancelled
        for q in campaign.queries:
            if q.status == "queued":
                q.status = "cancelled"
        campaign.status = "cancelled"
        campaign.completed_at = datetime.now(timezone.utc).isoformat()

        logger.info("Campaign cancelled/deleted: id=%s", campaign_id)
        return True

    async def start(self, campaign_id: str) -> None:
        """Start executing a campaign's queries sequentially."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")

        if campaign.status == "running":
            raise RuntimeError(f"Campaign {campaign_id} is already running")

        if self._active_campaign_id is not None:
            raise RuntimeError(
                f"Another campaign is already running: "
                f"{self._active_campaign_id}"
            )

        campaign.status = "running"
        campaign.started_at = datetime.now(timezone.utc).isoformat()
        self._active_campaign_id = campaign_id
        await self._persist_campaign(campaign)  # Sprint 1: persist on start
        self._active_task = asyncio.create_task(
            self._execute_campaign(campaign_id)
        )

    async def _execute_campaign(self, campaign_id: str) -> None:
        """Execute all queries in a campaign sequentially with snowball memory."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return

        try:
            for idx, query_status in enumerate(campaign.queries):
                if query_status.status != "queued":
                    continue

                # Wait for any running pipeline to finish
                while self._runner.running:
                    await asyncio.sleep(2.0)

                query_status.status = "running"
                query_status.started_at = (
                    datetime.now(timezone.utc).isoformat()
                )

                logger.info(
                    "Campaign %s: starting query %d/%d: %r",
                    campaign_id,
                    idx + 1,
                    campaign.total_queries,
                    query_status.query[:80],
                )

                try:
                    vector_id = await self._runner.start(
                        query=query_status.query,
                        depth=campaign.depth,
                        application=query_status.application or campaign.application or "general",
                        region=query_status.region or "GLOBAL",
                        research_brief=campaign.research_brief,
                    )
                    query_status.vector_id = vector_id

                    # Launch concurrent watcher for Campaign Map updates
                    watcher = asyncio.create_task(
                        self._watch_vector_progress(campaign, idx)
                    )

                    # Wait for pipeline to complete
                    while self._runner.running:
                        await asyncio.sleep(3.0)

                    watcher.cancel()
                    try:
                        await watcher
                    except asyncio.CancelledError:
                        pass

                    # Check result
                    runner_status = self._runner.status
                    if runner_status.status in (
                        "completed",
                        "timeout_synthesized",
                    ):
                        query_status.status = "completed"
                        query_status.result_path = runner_status.result_path
                        campaign.completed_count += 1

                        # Load result summary for snowball memory
                        self._capture_result_context(campaign, query_status)
                    else:
                        query_status.status = "failed"
                        query_status.error = (
                            runner_status.error or runner_status.status
                        )
                        campaign.failed_count += 1

                    query_status.completed_at = (
                        datetime.now(timezone.utc).isoformat()
                    )

                    # Copy result to campaign output directory
                    self._copy_result_to_campaign(campaign_id, query_status)

                except Exception as exc:
                    query_status.status = "failed"
                    query_status.error = str(exc)[:500]
                    query_status.completed_at = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    campaign.failed_count += 1
                    logger.error(
                        "Campaign %s: query %d failed: %s",
                        campaign_id, idx + 1, exc,
                    )

                # Sprint 1: persist after each query completes/fails
                await self._persist_campaign(campaign)

            # Campaign complete
            campaign.status = "completed"
            campaign.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Campaign completed: id=%s completed=%d failed=%d",
                campaign_id,
                campaign.completed_count,
                campaign.failed_count,
            )

        except asyncio.CancelledError:
            campaign.status = "cancelled"
            campaign.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info("Campaign cancelled: id=%s", campaign_id)
        except Exception as exc:
            campaign.status = "failed"
            campaign.completed_at = datetime.now(timezone.utc).isoformat()
            logger.error(
                "Campaign failed: id=%s error=%s", campaign_id, exc,
            )
        finally:
            self._active_campaign_id = None
            self._active_task = None
            # Sprint 1: persist final state
            if campaign:
                await self._persist_campaign(campaign)

    def _build_context_summary(self, campaign: CampaignData) -> str:
        """Build snowball memory context from previously completed queries.

        Returns a concise summary of findings from earlier queries in the
        campaign, which can be used to inform subsequent queries.
        """
        if not campaign.campaign_context:
            return ""

        parts = []
        for ctx in campaign.campaign_context:
            query = ctx.get("query", "")
            summary = ctx.get("summary", "")
            source_count = ctx.get("source_count", 0)
            if summary:
                parts.append(
                    f"Previous finding ({source_count} sources): "
                    f"[{query[:100]}] {summary[:500]}"
                )

        return " | ".join(parts) if parts else ""

    def _capture_result_context(
        self,
        campaign: CampaignData,
        query_status: CampaignQueryStatus,
    ) -> None:
        """Capture completed result summary into campaign snowball memory."""
        if not query_status.result_path:
            return

        try:
            result_path = Path(query_status.result_path)
            if not result_path.exists():
                return

            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            report = data.get("final_report", "")
            word_count = len(report.split()) if report else 0
            evidence_count = len(data.get("evidence", []))
            bibliography = data.get("bibliography", [])
            source_count = len(bibliography)
            citation_count = len(set(
                e.get("citation_key", "") for e in data.get("evidence", [])
                if e.get("citation_key")
            ))
            quality_metrics = data.get("quality_metrics") or {}
            faithfulness = quality_metrics.get(
                "faithfulness_score",
                data.get("faithfulness_score", 0.0),
            )

            query_status.word_count = word_count
            query_status.evidence_count = evidence_count
            query_status.faithfulness = faithfulness
            query_status.source_count = source_count
            query_status.citation_count = citation_count

            # Extract first ~500 chars of report as summary for snowball memory
            summary = report[:500].strip() if report else ""

            campaign.campaign_context.append({
                "query": query_status.query,
                "vector_id": query_status.vector_id,
                "summary": summary,
                "source_count": len(data.get("bibliography", [])),
                "word_count": word_count,
                "evidence_count": evidence_count,
            })

        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Could not capture result context for %s: %s",
                query_status.vector_id, exc,
            )

    def _copy_result_to_campaign(
        self,
        campaign_id: str,
        query_status: CampaignQueryStatus,
    ) -> None:
        """Copy the query result JSON to the campaign output directory."""
        if not query_status.result_path or not query_status.vector_id:
            return

        try:
            src = Path(query_status.result_path)
            if not src.exists():
                return

            dst_dir = Path(PG_CAMPAIGN_OUTPUT_DIR) / campaign_id
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"{query_status.vector_id}.json"

            shutil.copy2(str(src), str(dst))

            logger.info(
                "Copied result to campaign dir: %s -> %s", src, dst,
            )
        except OSError as exc:
            logger.warning(
                "Failed to copy result to campaign dir: %s", exc,
            )


    async def _watch_vector_progress(
        self,
        campaign: CampaignData,
        query_idx: int,
    ) -> None:
        """Poll trace events and update per-node status for Campaign Map.

        Runs concurrently with the pipeline execution loop. Reads new events
        from the global _tailer and updates node_status/node_metrics on the
        CampaignQueryStatus in-place.
        """
        query_status = campaign.queries[query_idx]
        vid = query_status.vector_id
        if not vid:
            return

        seen_cursor = 0
        start_ts = time.time()

        while True:
            try:
                await asyncio.sleep(1.0)
                if _tailer is None:
                    continue

                events = _tailer.all_events
                while seen_cursor < len(events):
                    ev = events[seen_cursor]
                    seen_cursor += 1

                    ev_vid = ev.get("vid", "")
                    if ev_vid != vid:
                        continue

                    ev_type = ev.get("type", "")
                    node = ev.get("node", "")

                    if ev_type == "node_start" and node:
                        query_status.node_status[node] = "running"
                        query_status.current_node = node
                    elif ev_type == "node_end" and node:
                        query_status.node_status[node] = "passed"
                        duration_ms = ev.get("duration_ms", 0)
                        query_status.node_metrics[node] = {
                            "duration_ms": duration_ms,
                        }
                    elif ev_type == "quality_gate":
                        gate_node = ev.get("node", node)
                        if gate_node and not ev.get("passed", True):
                            query_status.node_status[gate_node] = "warning"
                    elif ev_type == "evidence":
                        action = ev.get("action", "")
                        if action == "accumulated":
                            query_status.evidence_count = ev.get(
                                "total", query_status.evidence_count
                            )
                    elif ev_type == "verification_batch":
                        faith = ev.get("faithfulness")
                        if faith is not None:
                            query_status.faithfulness = faith
                    elif ev_type == "bibliography":
                        src_count = ev.get("count")
                        if src_count is not None:
                            query_status.source_count = src_count

                # Update elapsed_ms
                query_status.elapsed_ms = int(
                    (time.time() - start_ts) * 1000
                )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(
                    "Watcher error for %s: %s", vid, exc,
                )


_campaign_manager = CampaignManager(_runner)


# ---------------------------------------------------------------------------
# TraceTailer: watches JSONL file for new events
# ---------------------------------------------------------------------------
class TraceTailer:
    """Tails a JSONL trace file and broadcasts new events to SSE clients.

    Uses watchfiles for cross-platform (Windows-safe) file change detection.
    Tracks byte offset centrally; each SSE client gets its own cursor into
    the shared _all_events list so multiple browser tabs work correctly.
    """

    def __init__(self, trace_path: Path, poll_interval: float = 0.5):
        self._path = trace_path
        self._offset: int = 0
        self._poll_interval = poll_interval
        self._all_events: list[dict] = []
        self._notify: asyncio.Event = asyncio.Event()

    @property
    def trace_path(self) -> Path:
        """Return the trace file path (B13 diagnostic)."""
        return self._path

    @property
    def all_events(self) -> list[dict]:
        """Return all events seen so far."""
        return self._all_events

    def _read_new_lines(self) -> list[dict]:
        """Read new bytes from the trace file and parse JSONL lines.

        B13 FIX: Uses binary mode ("rb") for reliable offset tracking on
        Windows. Text mode "r" translates \\r\\n to \\n, causing f.tell()
        to return byte offsets that may not round-trip correctly with
        f.seek(), leading to duplicate or skipped lines (event count mismatch).
        """
        events = []
        if not self._path.exists():
            return events

        try:
            with open(self._path, "rb") as f:
                f.seek(self._offset)
                new_data_bytes = f.read()
                self._offset = f.tell()
        except (OSError, PermissionError) as exc:
            logger.warning("Trace read error: %s", exc)
            return events

        try:
            new_data = new_data_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.warning("Trace decode error at offset %d: %s", self._offset, exc)
            return events

        for line in new_data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                events.append(ev)
                self._all_events.append(ev)
            except json.JSONDecodeError:
                logger.debug("Skipping malformed line: %s", line[:100])

        if events:
            self._notify.set()
            self._notify.clear()

        return events

    async def run_watcher(self) -> None:
        """Background task that reads new lines and notifies waiting clients."""
        try:
            from watchfiles import awatch

            async for changes in awatch(
                str(self._path.parent),
                step=int(self._poll_interval * 1000),
                rust_timeout=int(self._poll_interval * 1000 * 2),
            ):
                for _change_type, changed_path in changes:
                    changed = Path(changed_path)
                    if changed == self._path or (
                        changed.suffix == ".jsonl"
                        and changed.name.startswith("pg_trace_")
                    ):
                        self._read_new_lines()
        except ImportError:
            logger.warning("watchfiles not available, falling back to polling")
            while True:
                await asyncio.sleep(self._poll_interval)
                self._read_new_lines()

    async def tail(self, after: int = 0) -> AsyncGenerator[dict, None]:
        """Per-client async generator with independent cursor.

        Each call gets its own index into _all_events, so multiple SSE
        clients receive all events independently.

        Args:
            after: Start cursor at this index (skip events already seen
                   via snapshot). WAVE-1.6 SSE dedup.
        """
        cursor = after

        while True:
            # Yield any events the client hasn't seen yet
            while cursor < len(self._all_events):
                yield self._all_events[cursor]
                cursor += 1

            # Wait for new events (with timeout for periodic liveness)
            try:
                await asyncio.wait_for(self._notify.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass


# ---------------------------------------------------------------------------
# Trace file discovery
# ---------------------------------------------------------------------------
def discover_trace_file(trace_dir: str) -> Optional[Path]:
    """Find the newest pg_trace_*.jsonl file in the given directory."""
    trace_path = Path(trace_dir)
    if not trace_path.exists():
        return None

    candidates = sorted(
        trace_path.glob("pg_trace_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Shared state -- set during main() before uvicorn starts
# ---------------------------------------------------------------------------
_tailer: Optional[TraceTailer] = None
_trace_path: Optional[Path] = None
_no_tunnel: bool = False
_server_port: int = PG_LIVE_SERVER_PORT


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start background watcher + Cloudflare tunnel on startup."""
    tasks = []
    if _tailer is not None:
        # Catchup existing file contents before clients connect
        _tailer._read_new_lines()
        tasks.append(asyncio.create_task(_tailer.run_watcher()))
    if not _no_tunnel:
        tasks.append(asyncio.create_task(start_cloudflare_tunnel(_server_port)))

    # Sprint 1, Task 1A.2: Initialize campaign persistence store
    if _CAMPAIGN_STORE_AVAILABLE and init_campaign_store is not None:
        try:
            await init_campaign_store()
            logger.info("[lifespan] Campaign store initialized")
            # Load persisted campaigns into CampaignManager
            if _campaign_manager is not None:
                await _campaign_manager.load_persisted_campaigns()
        except Exception as exc:
            logger.warning("[lifespan] Campaign store init failed: %s", exc)

    yield
    for t in tasks:
        t.cancel()


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="POLARIS Live Monitor", docs_url=None, redoc_url=None,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware (LAW VI -- origins from env)
# ---------------------------------------------------------------------------
_cors_origins_raw = os.getenv("POLARIS_CORS_ORIGINS", "*")
_cors_origins = [origin.strip() for origin in _cors_origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://www.google.com https://*.gstatic.com; "
        "connect-src 'self'"
    )
    return response


# ---------------------------------------------------------------------------
# Auth routes (wired only when auth module is available)
# ---------------------------------------------------------------------------
if _AUTH_AVAILABLE and auth_router is not None:
    app.include_router(auth_router)
    logger.info("Auth routes enabled at /api/auth/*")
else:
    logger.info("Auth routes: disabled (module not available or POLARIS_AUTH_ENABLED=0)")


# ---------------------------------------------------------------------------
# Authenticated research history endpoint (2B.1)
# ---------------------------------------------------------------------------
@app.get("/api/auth/history")
async def get_auth_history(request: Request):
    """Get research history for the authenticated user.

    Falls back to listing recent result files if session manager is unavailable.
    """
    # Try to get user from auth header
    user_id = "anonymous"
    if _AUTH_AVAILABLE and get_current_user is not None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from src.auth.auth_middleware import get_auth_manager
                auth_mgr = get_auth_manager()
                token = auth_header.split(" ", 1)[1]
                payload = auth_mgr.verify_token(token)
                if payload:
                    user_id = payload.get("user_id", payload.get("sub", "anonymous"))
            except Exception:
                pass

    # Try session manager first
    try:
        from src.auth.session_manager import SessionManager
        sm = SessionManager()
        history = sm.get_user_history(user_id, limit=50)
        return JSONResponse(history)
    except Exception:
        pass

    # Fallback: list recent result files
    results_dir = Path("outputs/polaris_graph")
    if not results_dir.exists():
        return JSONResponse([])

    result_files = sorted(
        results_dir.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    history = []
    for f in result_files[:20]:
        if f.name.endswith("_report.md"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            history.append({
                "vector_id": f.stem,
                "query": data.get("original_query", data.get("query", "")),
                "status": data.get("status", "unknown"),
                "created_at": f.stat().st_mtime,
                "depth": data.get("depth", "standard"),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return JSONResponse(history)


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return 500 without exposing stack trace."""
    logger.error(
        "Unhandled exception on %s: %s", request.url, exc, exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Rate limit exception handler (slowapi)
# ---------------------------------------------------------------------------
if RATE_LIMIT_AVAILABLE:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check with uptime, pipeline status, and deployment mode."""
    return JSONResponse({
        "status": "ok",
        "version": os.getenv("POLARIS_VERSION", "0.9.0"),
        "uptime_seconds": int(time.time() - _start_time),
        "pipeline_running": _runner._running if _runner else False,
        "deployment_mode": POLARIS_DEPLOYMENT_MODE,
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve the live dashboard HTML with auto cache-busted asset URLs."""
    if not DASHBOARD_HTML.exists():
        return HTMLResponse(
            content="<h1>Dashboard template not found</h1>"
            f"<p>Expected at: {DASHBOARD_HTML}</p>",
            status_code=404,
        )
    return _templates.TemplateResponse(
        request,
        "live_dashboard.html",
        {"asset_v": _STATIC_ASSET_HASH},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/events")
async def sse_events(request: Request, after: int = 0):
    """SSE endpoint streaming JSONL trace events in real time.

    Args:
        after: Skip events with index < after (WAVE-1.6 SSE dedup).
               Dashboard passes total_event_count from snapshot to avoid
               replaying events already processed via /api/snapshot.

    BUG-FIX: The generator now re-reads the global ``_tailer`` on every
    iteration.  When a new research run starts, ``_tailer`` is replaced with
    a fresh TraceTailer.  Previously the ``async for`` captured the old
    tailer at connection time and never saw events from the new run.  Now
    the generator detects the identity change, breaks out of the stale
    ``tail()`` iterator, and reconnects to the new tailer from offset 0
    (new trace file).
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        global _tailer

        if _tailer is None:
            yield {"data": json.dumps({"error": "No trace file configured"})}
            return

        current_tailer = _tailer
        cursor = after

        while True:
            # If the global tailer was swapped (new research run started),
            # abandon the old iterator and reconnect to the new tailer.
            if _tailer is not current_tailer:
                current_tailer = _tailer
                if current_tailer is None:
                    # Server shutting down or tailer cleared
                    return
                # New trace file starts from the beginning
                cursor = 0
                logger.info(
                    "SSE client detected tailer swap, reconnecting at cursor 0"
                )

            # Drain any buffered events the client hasn't seen
            while cursor < len(current_tailer.all_events):
                if await request.is_disconnected():
                    return
                ev = current_tailer.all_events[cursor]
                yield {"data": json.dumps(ev, default=str)}
                cursor += 1

            # Check for client disconnect before waiting
            if await request.is_disconnected():
                return

            # Wait briefly for new events (mirrors TraceTailer.tail timeout)
            try:
                await asyncio.wait_for(
                    current_tailer._notify.wait(), timeout=1.0,
                )
            except asyncio.TimeoutError:
                # Timeout is expected -- loop back to check for tailer swap
                # and new events
                pass

    return EventSourceResponse(
        event_generator(),
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-store",
        },
        ping=15,  # sends `: ping\n\n` every 15s — keeps Cloudflare alive
    )


@app.get("/api/snapshot")
async def snapshot():
    """Return all events grouped by type with computed stats."""
    if _tailer is None:
        return JSONResponse({"error": "No trace file configured"}, status_code=503)

    events = _tailer.all_events
    grouped: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        grouped[ev.get("type", "unknown")].append(ev)

    # Compute summary stats
    total_cost = 0.0
    total_evidence = 0
    node_durations: dict[str, float] = {}

    for ev in events:
        if ev.get("type") == "llm_call":
            # Prefer authoritative cost_usd / cumulative from trace event
            if ev.get("cumulative_cost_usd"):
                total_cost = ev["cumulative_cost_usd"]
            elif ev.get("cost_usd"):
                total_cost += ev["cost_usd"]
        if ev.get("type") == "evidence" and ev.get("action") == "accumulated":
            total_evidence = max(total_evidence, ev.get("count", 0))
        if ev.get("type") == "node_end" and ev.get("duration_ms"):
            node_durations[ev.get("node", "")] = ev["duration_ms"]

    stats = {
        "total_events": len(events),
        "event_counts": {k: len(v) for k, v in grouped.items()},
        "total_cost_usd": round(total_cost, 4),
        "total_evidence": total_evidence,
        "node_durations_ms": node_durations,
    }

    # B13: Diagnostic — compare in-memory event count vs trace file line count.
    if _tailer is not None and hasattr(_tailer, 'trace_path') and _tailer.trace_path:
        try:
            trace_path = Path(_tailer.trace_path) if isinstance(_tailer.trace_path, str) else _tailer.trace_path
            if trace_path.exists():
                file_line_count = sum(1 for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip())
                if file_line_count != len(events):
                    logger.warning(
                        "[live_server] B13: Event count mismatch — "
                        "server=%d vs trace_file=%d lines (delta=%d)",
                        len(events), file_line_count, len(events) - file_line_count,
                    )
                stats["trace_file_line_count"] = file_line_count
        except Exception as _b13_exc:
            logger.debug("[live_server] B13: Could not read trace file: %s", str(_b13_exc)[:200])

    # WAVE-1.6: Return ALL events (no truncation) for full snapshot
    # Include actual pipeline state so client can override stale hydration
    pipeline_running = _runner._running if _runner else False
    return JSONResponse({
        "stats": stats,
        "total_event_count": len(events),
        "pipeline_running": pipeline_running,
        "events_by_type": {k: v for k, v in grouped.items()},
    })


@app.get("/api/anomalies")
async def anomalies():
    """Return contents of the live anomaly log."""
    anomaly_path = Path(PG_LIVE_ANOMALY_LOG)
    if not anomaly_path.exists():
        return JSONResponse([])

    items = []
    try:
        with open(anomaly_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except (OSError, PermissionError):
        pass

    return JSONResponse(items)


@app.get("/api/cost")
async def cost_ledger():
    """Return cost ledger entries filtered to the current session.

    Filters by session_id matching the trace file's vector_id
    (e.g., pg_trace_PG_TEST_059.jsonl -> session_id=PG_TEST_059).
    Falls back to unfiltered if vector_id can't be determined.
    """
    ledger_path = Path(PG_COST_LEDGER_PATH)
    if not ledger_path.exists():
        return JSONResponse({
            "entries": [], "total_cost_usd": 0.0,
            "total_count": 0, "session_id": None,
        })

    # Extract session_id from trace filename (pg_trace_PG_TEST_059.jsonl)
    session_id = None
    if _trace_path is not None:
        name = _trace_path.stem  # pg_trace_PG_TEST_059
        if name.startswith("pg_trace_"):
            session_id = name[len("pg_trace_"):]

    # Also check if tailer has seen events with a vid
    if session_id is None and _tailer is not None and _tailer.all_events:
        for ev in _tailer.all_events[:5]:
            vid = ev.get("vid")
            if vid and vid != "unknown":
                session_id = vid
                break

    entries = []
    total_cost = 0.0
    total_unfiltered = 0
    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total_unfiltered += 1
                    # Filter by session_id if available
                    if session_id and entry.get("session_id") != session_id:
                        continue
                    entries.append(entry)
                    total_cost += entry.get("cost_usd", 0.0)
                except json.JSONDecodeError:
                    pass
    except (OSError, PermissionError):
        pass

    return JSONResponse({
        "entries": entries[-100:],
        "total_count": len(entries),
        "total_unfiltered": total_unfiltered,
        "total_cost_usd": round(total_cost, 6),
        "session_id": session_id,
    })


# ---------------------------------------------------------------------------
# Research pipeline endpoints
# ---------------------------------------------------------------------------
@app.post("/api/research")
async def start_research(request: Request, req: ResearchRequest):
    """Start a new research pipeline run.

    Accepts a research question and depth preset. Returns immediately
    with the vector_id; pipeline runs in background. Monitor progress
    via /api/events SSE stream.

    Rate-limited to 1 request per minute per client IP.
    """
    # --- Rate limiting ---
    if RATE_LIMIT_AVAILABLE and limiter is not None:
        # slowapi decorator applied via app.state.limiter
        # Manual check for non-decorator approach
        pass
    else:
        # Fallback in-memory rate limiter
        client_ip = request.client.host if request.client else "unknown"
        if not _fallback_limiter.check(client_ip):
            remaining = _fallback_limiter.seconds_remaining(client_ip)
            return JSONResponse(
                {
                    "error": "Rate limit exceeded. Try again later.",
                    "retry_after_seconds": remaining,
                },
                status_code=429,
                headers={"Retry-After": str(remaining)},
            )

    if _runner.running:
        return JSONResponse(
            {"error": "A research run is already in progress", "status": _runner.status.model_dump()},
            status_code=409,
        )

    # Strict depth validation (no silent fallback)
    if req.depth not in DEPTH_PRESETS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid depth '{req.depth}'. Must be one of: {list(DEPTH_PRESETS.keys())}",
        )

    try:
        vector_id = await _runner.start(
            query=req.query,
            depth=req.depth,
            application=req.application,
            region=req.region,
            document_ids=req.document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        return JSONResponse(
            {"error": f"Failed to start research: {exc}"},
            status_code=500,
        )

    return JSONResponse({
        "vector_id": vector_id,
        "query": req.query,
        "depth": req.depth,
        "document_ids": req.document_ids,
        "message": "Research started. Monitor via /api/events SSE stream.",
    })


# Apply slowapi rate limit decorator if available
if RATE_LIMIT_AVAILABLE and limiter is not None:
    start_research = limiter.limit("1/minute")(start_research)


@app.get("/api/research/status")
async def research_status():
    """Get current research pipeline status."""
    return JSONResponse(_runner.status.model_dump())


@app.post("/api/research/cancel")
async def cancel_research():
    """Cancel the running research pipeline."""
    cancelled = await _runner.cancel()
    if cancelled:
        return JSONResponse({"message": "Research cancelled"})
    return JSONResponse(
        {"error": "No research is currently running"},
        status_code=404,
    )


@app.post("/api/research/steer")
async def steer_research(req: SteerRequest):
    """D2: Queue a steering directive for the running pipeline."""
    if not _runner.running:
        raise HTTPException(404, "No research is currently running")
    ok = await _runner.steer(req.directive)
    if not ok:
        raise HTTPException(409, "Could not queue steering directive")
    return {"status": "queued", "directive": req.directive[:100]}


@app.get("/api/research/result/{vector_id}")
async def get_research_result(vector_id: str):
    """Get the result of a completed research run."""
    # Sanitize vector_id to prevent path traversal
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
    if not result_path.exists():
        return JSONResponse(
            {"error": f"Result not found for vector_id: {safe_id}"},
            status_code=404,
        )
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Return a curated subset for the UI (not the full 60+ field state)
        return JSONResponse({
            "vector_id": safe_id,
            "query": data.get("original_query", ""),
            "status": data.get("status", "unknown"),
            "final_report": data.get("final_report", ""),
            "bibliography": data.get("bibliography", []),
            "quality_metrics": data.get("quality_metrics"),
            "sections": data.get("sections", []),
            "evidence_count": len(data.get("evidence", [])),
            "iteration_count": data.get("iteration_count", 0),
            "timestamps": data.get("timestamps", {}),
            "trace_summary": data.get("trace_summary", {}),
            "smart_art_diagrams": data.get("smart_art_diagrams", {}),
        })
    except (json.JSONDecodeError, OSError) as exc:
        return JSONResponse(
            {"error": f"Failed to read result: {exc}"},
            status_code=500,
        )


@app.get("/api/research/chain/{vector_id}/{citation_number}")
async def get_citation_chain(vector_id: str, citation_number: int):
    """Sprint 2 (A1+2A): Citation chain of custody — full traceability for a single citation.

    Joins bibliography → evidence → verified claims → report sections to build
    the A-B-C-D chain: Finding [A] ← Citation [B] ← Sentence [C] ← Reasoning [D].

    Returns all chain links for the requested citation number.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
    if not result_path.exists():
        return JSONResponse({"error": f"Result not found: {safe_id}"}, status_code=404)

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return JSONResponse({"error": f"Failed to read: {exc}"}, status_code=500)

    bibliography: list[dict] = data.get("bibliography", [])
    evidence_pool: list[dict] = data.get("evidence", [])
    claims: list[dict] = data.get("claims", [])
    sections: list[dict] = data.get("sections", [])

    # Build lookup maps
    evidence_by_id: dict[str, dict] = {
        e.get("evidence_id", ""): e for e in evidence_pool if e.get("evidence_id")
    }
    claims_by_evidence: dict[str, list[dict]] = {}
    for claim in claims:
        for eid in claim.get("evidence_ids", []):
            claims_by_evidence.setdefault(eid, []).append(claim)

    # Find the bibliography entry for this citation number
    bib_entry = None
    for b in bibliography:
        if b.get("citation_number") == citation_number:
            bib_entry = b
            break

    if bib_entry is None:
        return JSONResponse(
            {"error": f"Citation [{citation_number}] not found in bibliography"},
            status_code=404,
        )

    # Gather evidence pieces linked to this bibliography entry
    bib_evidence_ids: list[str] = bib_entry.get("evidence_ids", [])
    chain_links: list[dict] = []

    for eid in bib_evidence_ids:
        ev = evidence_by_id.get(eid)
        if not ev:
            continue

        # Find sections that cite this evidence
        citing_sections: list[dict] = []
        for sec in sections:
            sec_ev_ids = sec.get("evidence_ids", [])
            sec_cite_ids = sec.get("citation_ids", [])
            if eid in sec_ev_ids or eid in sec_cite_ids:
                citing_sections.append({
                    "section_id": sec.get("section_id", ""),
                    "title": sec.get("title", ""),
                })

        # Find verification claims for this evidence
        related_claims: list[dict] = []
        for claim in claims_by_evidence.get(eid, []):
            related_claims.append({
                "claim_id": claim.get("claim_id", ""),
                "statement": claim.get("statement", "")[:300],
                "verdict": claim.get("verdict", "NO_VERDICT"),
                "is_faithful": claim.get("is_faithful"),
                "reasoning": claim.get("reasoning", "")[:500],
                "nli_score": claim.get("nli_score"),
                "cross_source_score": claim.get("cross_source_score"),
                "verification_method": claim.get("verification_method", ""),
                "verification_type": claim.get("verification_type", ""),
            })

        chain_links.append({
            "evidence_id": eid,
            "direct_quote": ev.get("direct_quote", ""),
            "statement": ev.get("statement", "")[:300],
            "source_url": ev.get("source_url", ""),
            "source_title": ev.get("source_title", ""),
            "source_type": ev.get("source_type", ""),
            "quality_tier": ev.get("quality_tier", "BRONZE"),
            "relevance_score": ev.get("relevance_score", 0.0),
            "source_confidence": ev.get("source_confidence", 0.0),
            "year": ev.get("year"),
            "authors": ev.get("authors", []),
            "perspective": ev.get("perspective"),
            "corroborating_sources": ev.get("corroborating_sources", 0),
            "citing_sections": citing_sections,
            "verification": related_claims,
        })

    return JSONResponse({
        "vector_id": safe_id,
        "citation_number": citation_number,
        "source": {
            "citation_key": bib_entry.get("citation_key", ""),
            "formatted": bib_entry.get("formatted", ""),
            "url": bib_entry.get("url", ""),
            "source_type": bib_entry.get("source_type", ""),
        },
        "evidence_count": len(chain_links),
        "chain": chain_links,
    })


@app.get("/api/research/chain/{vector_id}")
async def get_all_citation_chains(vector_id: str):
    """Sprint 2: Summary of all citation chains for a research result.

    Returns a list of all bibliography entries with their evidence counts
    and aggregate verification status, suitable for populating citation
    indicators in the report view.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
    if not result_path.exists():
        return JSONResponse({"error": f"Result not found: {safe_id}"}, status_code=404)

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return JSONResponse({"error": f"Failed to read: {exc}"}, status_code=500)

    bibliography: list[dict] = data.get("bibliography", [])
    evidence_pool: list[dict] = data.get("evidence", [])
    claims: list[dict] = data.get("claims", [])

    evidence_by_id = {e.get("evidence_id", ""): e for e in evidence_pool}
    claims_by_evidence: dict[str, list[dict]] = {}
    for claim in claims:
        for eid in claim.get("evidence_ids", []):
            claims_by_evidence.setdefault(eid, []).append(claim)

    summaries: list[dict] = []
    for bib in bibliography:
        bib_ev_ids = bib.get("evidence_ids", [])
        ev_count = len(bib_ev_ids)
        tier_counts: dict[str, int] = {}
        supported = 0
        total_verified = 0
        for eid in bib_ev_ids:
            ev = evidence_by_id.get(eid, {})
            tier = ev.get("quality_tier", "BRONZE")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            for claim in claims_by_evidence.get(eid, []):
                total_verified += 1
                if claim.get("is_faithful") or claim.get("verdict") == "SUPPORTED":
                    supported += 1

        summaries.append({
            "citation_number": bib.get("citation_number"),
            "citation_key": bib.get("citation_key", ""),
            "url": bib.get("url", ""),
            "source_type": bib.get("source_type", ""),
            "formatted": bib.get("formatted", ""),
            "evidence_count": ev_count,
            "tier_breakdown": tier_counts,
            "verified_claims": total_verified,
            "supported_claims": supported,
            "verification_rate": round(supported / total_verified, 2) if total_verified > 0 else None,
        })

    return JSONResponse({
        "vector_id": safe_id,
        "total_citations": len(summaries),
        "citations": summaries,
    })


@app.get("/api/research/source-preview/{vector_id}/{evidence_id}")
async def get_source_preview(vector_id: str, evidence_id: str):
    """Sprint 2 (A1.4): Mini-webpage preview for a citation.

    Returns readability_html + quote_text for sandboxed iframe rendering
    with mark.js client-side highlighting.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    safe_eid = re.sub(r"[^a-zA-Z0-9_\-]", "", evidence_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
    if not result_path.exists():
        return JSONResponse({"error": f"Result not found: {safe_id}"}, status_code=404)

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return JSONResponse({"error": f"Failed to read: {exc}"}, status_code=500)

    # Find the evidence piece
    evidence_pool: list[dict] = data.get("evidence", [])
    ev = None
    for e in evidence_pool:
        if e.get("evidence_id") == safe_eid:
            ev = e
            break
    if ev is None:
        return JSONResponse({"error": f"Evidence {safe_eid} not found"}, status_code=404)

    source_url = ev.get("source_url", "")
    quote_text = ev.get("direct_quote", "")
    source_title = ev.get("source_title", "")

    # Look up cached readability HTML
    readability_html = ""
    raw_html = ""
    plaintext_content = ""
    try:
        from src.polaris_graph.memory.content_cache import get_cached_content
        cached = await get_cached_content(source_url)
        if cached:
            readability_html = cached.get("readability_html", "")
            raw_html = cached.get("raw_html", "")
            plaintext_content = cached.get("content", "")
            # Fall back to raw_html if readability extraction failed
            if not readability_html and raw_html:
                readability_html = raw_html
    except Exception as exc:
        logger.debug("[source-preview] Cache lookup failed: %s", str(exc)[:100])

    # BUG-001 fix: Fall back to plaintext/markdown content from cache
    # Jina Reader returns markdown (not HTML), so readability_html is often empty.
    # Wrap plaintext content in basic HTML for iframe preview rendering.
    if not readability_html and plaintext_content and len(plaintext_content) > 100:
        import html as _html
        escaped_content = _html.escape(plaintext_content[:25000])
        # Convert markdown-like line breaks to HTML paragraphs
        paragraphs = escaped_content.split("\n\n")
        body_html = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())
        readability_html = (
            f'<html><head><meta charset="utf-8"><style>'
            f'body{{font-family:system-ui,sans-serif;line-height:1.6;padding:20px;max-width:800px;margin:0 auto;color:#333}}'
            f'p{{margin:0 0 1em 0}}'
            f'</style></head><body>'
            f'<h1>{_html.escape(source_title or "Source Preview")}</h1>'
            f'{body_html}'
            f'</body></html>'
        )
        logger.debug("[source-preview] Using plaintext fallback for %s (%d chars)", source_url[:60], len(plaintext_content))

    # BUG-001 fix: Also try source_content from the evidence piece itself
    if not readability_html:
        source_content = ev.get("source_content", "") or ev.get("content", "")
        if source_content and len(source_content) > 50:
            import html as _html
            escaped = _html.escape(source_content[:15000])
            paragraphs = escaped.split("\n\n")
            body_html = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())
            readability_html = (
                f'<html><head><meta charset="utf-8"><style>'
                f'body{{font-family:system-ui,sans-serif;line-height:1.6;padding:20px;max-width:800px;margin:0 auto;color:#333}}'
                f'p{{margin:0 0 1em 0}} mark{{background:#fef08a;padding:2px 0}}'
                f'</style></head><body>'
                f'<h1>{_html.escape(source_title or "Source Preview")}</h1>'
                f'{body_html}'
                f'</body></html>'
            )
            logger.debug("[source-preview] Using evidence content fallback for %s", safe_eid)

    # Sanitize HTML — strip <script>, <iframe>, on* handlers
    if readability_html:
        import re as _re
        readability_html = _re.sub(r"<script[^>]*>.*?</script>", "", readability_html, flags=_re.DOTALL | _re.IGNORECASE)
        readability_html = _re.sub(r"<iframe[^>]*>.*?</iframe>", "", readability_html, flags=_re.DOTALL | _re.IGNORECASE)
        readability_html = _re.sub(r"\son\w+\s*=\s*[\"'][^\"']*[\"']", "", readability_html, flags=_re.IGNORECASE)

    return JSONResponse({
        "evidence_id": safe_eid,
        "source_url": source_url,
        "source_title": source_title,
        "quote_text": quote_text,
        "quote_char_start": ev.get("quote_char_start"),
        "quote_char_end": ev.get("quote_char_end"),
        "readability_html": readability_html,
        "has_preview": bool(readability_html),
    })


# ---------------------------------------------------------------------------
# A2: Pipeline Traceback and Rewind -- Checkpoint endpoints
# ---------------------------------------------------------------------------
_CHECKPOINT_AVAILABLE = False
try:
    from src.polaris_graph.checkpoint_manager import (
        list_checkpoints as _list_checkpoints,
        get_checkpoint_state as _get_checkpoint_state,
        rewind_to_checkpoint as _rewind_to_checkpoint,
        PG_CHECKPOINT_ENABLED as _PG_CHECKPOINT_ENABLED,
    )
    _CHECKPOINT_AVAILABLE = True
except ImportError:
    _list_checkpoints = None  # type: ignore[assignment]
    _get_checkpoint_state = None  # type: ignore[assignment]
    _rewind_to_checkpoint = None  # type: ignore[assignment]
    _PG_CHECKPOINT_ENABLED = False


@app.get("/api/research/checkpoints/{vector_id}")
async def get_checkpoints(vector_id: str):
    """A2.2: List all checkpoints for a research run.

    Returns a list of checkpoint summaries for the given vector, ordered
    most-recent-first. Each entry contains checkpoint_id, node, timestamp,
    evidence_count, iteration, and faithfulness.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    if not _CHECKPOINT_AVAILABLE or not _PG_CHECKPOINT_ENABLED:
        return JSONResponse({
            "checkpoints": [],
            "total": 0,
            "checkpoint_enabled": False,
            "message": "Checkpointing is disabled (PG_CHECKPOINT_ENABLED=0 or module unavailable)",
        })

    try:
        from src.polaris_graph.graph import build_graph
        from src.polaris_graph.checkpoint_manager import get_checkpointer

        graph = build_graph()
        checkpointer_cm = get_checkpointer()

        async with checkpointer_cm as saver:
            compiled_app = graph.compile(checkpointer=saver)
            checkpoints = await _list_checkpoints(safe_id, compiled_app)

        return JSONResponse({
            "checkpoints": checkpoints,
            "total": len(checkpoints),
            "checkpoint_enabled": True,
            "vector_id": safe_id,
        })
    except Exception as exc:
        logger.error("[A2] get_checkpoints failed: %s", str(exc)[:300])
        return JSONResponse(
            {"error": f"Failed to list checkpoints: {str(exc)[:500]}"},
            status_code=500,
        )


@app.get("/api/research/checkpoint/{vector_id}/{checkpoint_id}")
async def get_checkpoint_detail(vector_id: str, checkpoint_id: str):
    """A2.2: Get full state snapshot at a specific checkpoint.

    Returns complete state values and metadata for the specified checkpoint.
    Useful for inspecting pipeline state at any point in the execution history.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    safe_cpid = re.sub(r"[^a-zA-Z0-9_\-]", "", checkpoint_id)

    if not _CHECKPOINT_AVAILABLE or not _PG_CHECKPOINT_ENABLED:
        return JSONResponse(
            {"error": "Checkpointing is disabled (PG_CHECKPOINT_ENABLED=0 or module unavailable)"},
            status_code=400,
        )

    try:
        from src.polaris_graph.graph import build_graph
        from src.polaris_graph.checkpoint_manager import get_checkpointer

        graph = build_graph()
        checkpointer_cm = get_checkpointer()

        async with checkpointer_cm as saver:
            compiled_app = graph.compile(checkpointer=saver)
            result = await _get_checkpoint_state(safe_id, safe_cpid, compiled_app)

        if "error" in result:
            return JSONResponse({"error": result["error"]}, status_code=404)

        return JSONResponse(result)
    except Exception as exc:
        logger.error(
            "[A2] get_checkpoint_detail failed: %s", str(exc)[:300]
        )
        return JSONResponse(
            {"error": f"Failed to get checkpoint: {str(exc)[:500]}"},
            status_code=500,
        )


@app.post("/api/research/rewind/{vector_id}/{checkpoint_id}")
async def rewind_pipeline(vector_id: str, checkpoint_id: str, request: Request):
    """A2.2: Resume execution from a specific checkpoint.

    Optionally accepts a JSON body with a state_patch dict to modify
    the checkpoint state before resuming. Common patch keys:
    - max_iterations: Increase iteration budget
    - needs_iteration: Force True to allow more search rounds
    - gaps: Clear gaps list to force synthesis

    Request body (optional):
        {"state_patch": {"max_iterations": 5, "needs_iteration": true}}
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    safe_cpid = re.sub(r"[^a-zA-Z0-9_\-]", "", checkpoint_id)

    if not _CHECKPOINT_AVAILABLE or not _PG_CHECKPOINT_ENABLED:
        return JSONResponse(
            {"error": "Checkpointing is disabled (PG_CHECKPOINT_ENABLED=0 or module unavailable)"},
            status_code=400,
        )

    # Parse optional state_patch from request body
    state_patch = None
    try:
        body = await request.json()
        if isinstance(body, dict) and "state_patch" in body:
            state_patch = body["state_patch"]
            if not isinstance(state_patch, dict):
                return JSONResponse(
                    {"error": "state_patch must be a JSON object"},
                    status_code=400,
                )
    except Exception:
        # No body or invalid JSON -- proceed without patch
        pass

    try:
        from src.polaris_graph.graph import build_graph
        from src.polaris_graph.checkpoint_manager import get_checkpointer

        graph = build_graph()
        checkpointer_cm = get_checkpointer()

        async with checkpointer_cm as saver:
            compiled_app = graph.compile(checkpointer=saver)
            result = await _rewind_to_checkpoint(
                safe_id, safe_cpid, compiled_app, state_patch=state_patch,
            )

        if "error" in result and result.get("status") != "rewind_complete":
            status_code = 404 if "not found" in result["error"].lower() else 500
            return JSONResponse(
                {"error": result["error"], "status": result.get("status")},
                status_code=status_code,
            )

        # A7.4: If state was patched, capture the human override for LTM
        if state_patch:
            try:
                import datetime as _dt
                from src.polaris_graph.memory.cross_vector import store_human_override
                # Get original query for context embedding
                result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
                _context = safe_id
                if result_path.exists():
                    try:
                        with open(result_path, "r", encoding="utf-8") as _f:
                            _context = json.load(_f).get("original_query", safe_id)
                    except Exception:
                        pass
                override = {
                    "override_id": f"ho_{safe_id}_{safe_cpid}_{int(_dt.datetime.now().timestamp())}",
                    "vector_id": safe_id,
                    "checkpoint_id": safe_cpid,
                    "node": result.get("metadata", {}).get("resume_node", "unknown"),
                    "override_type": "state_patch",
                    "original_value": str(state_patch)[:1000],
                    "corrected_value": "user_modified",
                    "context": _context[:500],
                    "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                }
                stored = store_human_override(override)
                if stored:
                    logger.info("[A7.4] Stored human override for %s at checkpoint %s", safe_id, safe_cpid)
            except Exception as ho_exc:
                logger.warning("[A7.4] Failed to store human override: %s", str(ho_exc)[:200])

        return JSONResponse(result)
    except Exception as exc:
        logger.error(
            "[A2] rewind_pipeline failed: %s", str(exc)[:300]
        )
        return JSONResponse(
            {"error": f"Rewind failed: {str(exc)[:500]}"},
            status_code=500,
        )


@app.get("/api/research/overrides/{vector_id}")
async def get_research_overrides(vector_id: str):
    """A7.4: Get human overrides relevant to a research vector's topic."""
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"

    query = safe_id
    if result_path.exists():
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                query = json.load(f).get("original_query", safe_id)
        except Exception:
            pass

    try:
        from src.polaris_graph.memory.cross_vector import query_human_overrides
        overrides = query_human_overrides(query=query, k=20)
        return JSONResponse({"overrides": overrides, "count": len(overrides), "query": query[:200]})
    except Exception as exc:
        logger.warning("[A7.4] Override query failed: %s", str(exc)[:200])
        return JSONResponse({"overrides": [], "count": 0, "error": str(exc)[:200]})


# Research history cache: avoids re-parsing multi-MB JSON files every call.
# Keyed by (filepath, mtime) — invalidates when file is modified.
_history_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _extract_history_entry(result_file: Path) -> Optional[dict[str, Any]]:
    """Extract summary metadata from a result JSON file, with mtime caching."""
    file_key = str(result_file)
    try:
        mtime = result_file.stat().st_mtime
    except OSError:
        return None

    cached = _history_cache.get(file_key)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        report_text = data.get("final_report", "")
        word_count = len(report_text.split()) if report_text else 0
        timestamps = data.get("timestamps", {})
        entry = {
            "vector_id": result_file.stem,
            "query": data.get("original_query", "")[:200],
            "status": data.get("status", "unknown"),
            "evidence_count": len(data.get("evidence", [])),
            "word_count": word_count,
            "citation_count": len(data.get("bibliography", [])),
            "iteration_count": data.get("iteration_count", 0),
            "started_at": timestamps.get("started", ""),
            "completed_at": timestamps.get("completed", ""),
            "faithfulness": data.get("quality_metrics", {}).get(
                "faithfulness_pct", None
            ) if isinstance(data.get("quality_metrics"), dict) else None,
        }
        _history_cache[file_key] = (mtime, entry)
        return entry
    except (json.JSONDecodeError, OSError, KeyError):
        return None


@app.get("/api/research/history")
async def get_research_history():
    """List all completed research results with metadata.

    Scans outputs/polaris_graph/ for result JSON files and returns a summary
    list sorted by timestamp (most recent first). Each entry includes:
    vector_id, query, status, evidence_count, word_count, timestamp.

    Uses mtime-based caching so repeated calls avoid re-parsing large files.
    """
    output_dir = Path("outputs/polaris_graph")
    if not output_dir.exists():
        return JSONResponse({"history": [], "total": 0})

    history: list[dict[str, Any]] = []
    for result_file in output_dir.glob("*.json"):
        entry = _extract_history_entry(result_file)
        if entry is not None:
            history.append(entry)

    # Sort by completion time descending (most recent first)
    history.sort(
        key=lambda h: h.get("completed_at", "") or h.get("started_at", ""),
        reverse=True,
    )
    return JSONResponse({"history": history, "total": len(history)})


# ---------------------------------------------------------------------------
# Memory stats endpoint (Sprint 1B)
# ---------------------------------------------------------------------------
@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get LTM memory statistics for dashboard indicator.

    Returns item count, availability, tier breakdown, and top domains.
    """
    try:
        from src.polaris_graph.memory.cross_vector import get_ltm_stats
        stats = get_ltm_stats()
        return JSONResponse(stats)
    except ImportError:
        return JSONResponse({
            "total_items": 0,
            "by_tier": {},
            "top_domains": [],
            "available": False,
            "error": "cross_vector module not available",
        })
    except Exception as exc:
        logger.warning("[live_server] Memory stats failed: %s", str(exc)[:200])
        return JSONResponse({
            "total_items": 0,
            "by_tier": {},
            "top_domains": [],
            "available": False,
            "error": str(exc)[:200],
        })


# ---------------------------------------------------------------------------
# Mind Map API (Sprint 3, 3A)
# ---------------------------------------------------------------------------
@app.get("/api/research/mindmap/{vector_id}")
async def get_mindmap_data(vector_id: str):
    """Sprint 3 (3A): Build hierarchical mind map tree from research result.

    Returns: {
        center: {label, type},
        sections: [{id, title, finding_count}],
        findings: [{id, section_id, text, evidence_ids}],
        sources: [{id, title, url, tier, sections_cited_in, citation_count}],
        edges: [{from, to, type, weight}]
    }
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
    if not result_path.exists():
        return JSONResponse({"error": f"Result not found: {safe_id}"}, status_code=404)

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return JSONResponse({"error": f"Failed to read: {exc}"}, status_code=500)

    query = data.get("original_query", "Research Query")
    sections_raw: list[dict] = data.get("sections", [])
    evidence_pool: list[dict] = data.get("evidence", [])
    bibliography: list[dict] = data.get("bibliography", [])

    # Build evidence lookup
    evidence_by_id = {e.get("evidence_id", ""): e for e in evidence_pool if e.get("evidence_id")}

    # Build source lookup from bibliography
    source_map: dict[str, dict] = {}
    for bib in bibliography:
        src_url = bib.get("url", bib.get("source_url", ""))
        src_id = f"src_{bib.get('citation_number', 0)}"
        source_map[src_id] = {
            "id": src_id,
            "title": bib.get("title", "")[:100],
            "url": src_url,
            "tier": bib.get("quality_tier", "BRONZE"),
            "citation_number": bib.get("citation_number", 0),
            "sections_cited_in": set(),
            "citation_count": 0,
        }

    # Build section and finding nodes
    section_nodes = []
    finding_nodes = []
    edges = []

    for i, sec in enumerate(sections_raw):
        sec_id = sec.get("section_id", f"sec_{i}")
        sec_title = sec.get("title", f"Section {i + 1}")
        sec_evidence_ids = sec.get("evidence_ids", [])

        section_nodes.append({
            "id": sec_id,
            "title": sec_title,
            "finding_count": len(sec_evidence_ids),
        })

        # Edge: center → section
        edges.append({"from": "center", "to": sec_id, "type": "section", "weight": 1})

        # Build findings from evidence in this section
        for eid in sec_evidence_ids[:30]:  # Cap per section for rendering
            ev = evidence_by_id.get(eid)
            if not ev:
                continue
            finding_id = f"f_{sec_id}_{eid}"
            statement = ev.get("statement", "")[:120]
            finding_nodes.append({
                "id": finding_id,
                "section_id": sec_id,
                "text": statement,
                "evidence_id": eid,
            })

            # Edge: section → finding
            edges.append({"from": sec_id, "to": finding_id, "type": "finding", "weight": 1})

            # Link finding to source
            ev_source = ev.get("source", ev.get("source_url", ""))
            for sid, src in source_map.items():
                if src["url"] and ev_source and src["url"] in ev_source:
                    edges.append({"from": finding_id, "to": sid, "type": "source", "weight": 1})
                    src["sections_cited_in"].add(sec_id)
                    src["citation_count"] += 1
                    break

    # Convert sets to lists for JSON
    sources_out = []
    for src in source_map.values():
        src_copy = dict(src)
        src_copy["sections_cited_in"] = list(src_copy["sections_cited_in"])
        src_copy["cross_cutting"] = len(src_copy["sections_cited_in"]) > 1
        sources_out.append(src_copy)

    return JSONResponse({
        "center": {"label": query[:200], "type": "question"},
        "sections": section_nodes,
        "findings": finding_nodes[:200],  # Cap total findings for performance
        "sources": sources_out,
        "edges": edges[:500],  # Cap edges
        "stats": {
            "total_sections": len(section_nodes),
            "total_findings": len(finding_nodes),
            "total_sources": len(sources_out),
            "cross_cutting_sources": sum(1 for s in sources_out if s.get("cross_cutting")),
        },
    })


# ---------------------------------------------------------------------------
# Memory CRUD API (Sprint 3, 3B)
# ---------------------------------------------------------------------------
@app.get("/api/memory/search")
async def search_memory(q: str = "", limit: int = 20):
    """Search across LTM memory items by query text."""
    if not q or len(q) < 2:
        return JSONResponse({"error": "Query must be at least 2 characters"}, status_code=422)
    try:
        from src.polaris_graph.memory.cross_vector import query_ltm
        results = query_ltm(query=q, max_results=min(limit, 100))
        return JSONResponse({"query": q, "results": results, "count": len(results)})
    except Exception as exc:
        logger.warning("[live_server] Memory search failed: %s", str(exc)[:200])
        return JSONResponse({"error": str(exc)[:200], "results": [], "count": 0}, status_code=500)


@app.get("/api/memory/items")
async def list_memory_items(limit: int = 100, offset: int = 0):
    """List LTM memory items with pagination."""
    try:
        from src.polaris_graph.memory.cross_vector import list_ltm_items
        result = list_ltm_items(limit=min(limit, 500), offset=max(offset, 0))
        return JSONResponse(result)
    except Exception as exc:
        logger.warning("[live_server] Memory list failed: %s", str(exc)[:200])
        return JSONResponse({"items": [], "total": 0, "error": str(exc)[:200]}, status_code=500)


@app.delete("/api/memory/items/{item_id}")
async def delete_memory_item(item_id: str):
    """Delete a specific LTM memory item."""
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", item_id)
    if not safe_id:
        return JSONResponse({"error": "Invalid item ID"}, status_code=422)
    try:
        from src.polaris_graph.memory.cross_vector import delete_ltm_item
        deleted = delete_ltm_item(safe_id)
        if deleted:
            return JSONResponse({"status": "deleted", "id": safe_id})
        return JSONResponse({"error": "Item not found"}, status_code=404)
    except Exception as exc:
        logger.warning("[live_server] Memory delete failed: %s", str(exc)[:200])
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


# ---------------------------------------------------------------------------
# Pipeline CRUD + Wizard endpoints (Sprint 4)
# ---------------------------------------------------------------------------

# In-memory pipeline store (for custom pipelines; templates are on disk)
_custom_pipelines: dict[str, dict] = {}


@app.get("/api/pipelines/templates")
async def list_pipeline_templates():
    """List available pipeline templates. G10: robust path resolution."""
    try:
        from src.polaris_graph.pipeline_definition import list_templates
        templates = list_templates()
        if templates:
            return JSONResponse({"templates": templates})
    except Exception as exc:
        logger.warning("[live_server] Pipeline templates import failed: %s", str(exc)[:200])

    # G10: Fallback — direct YAML parsing with robust path resolution
    try:
        import yaml
        from pathlib import Path as _Path
        # Try multiple resolution strategies
        candidates = [
            _Path(__file__).resolve().parent.parent / "config" / "pipeline_templates",
            _Path.cwd() / "config" / "pipeline_templates",
            _Path(os.getenv("PG_PIPELINE_TEMPLATES_DIR", "")) if os.getenv("PG_PIPELINE_TEMPLATES_DIR") else None,
        ]
        templates_dir = None
        for c in candidates:
            if c and c.exists():
                templates_dir = c
                break

        if templates_dir:
            templates = []
            for f in sorted(templates_dir.glob("*.yaml")):
                try:
                    with open(f, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh)
                    templates.append({
                        "pipeline_id": data.get("pipeline_id", f.stem),
                        "name": data.get("name", f.stem.replace("_", " ").title()),
                        "description": data.get("description", ""),
                        "total_nodes": sum(
                            len(m.get("stages", [])) for m in data.get("macro_stages", [])
                        ),
                        "macro_count": len(data.get("macro_stages", [])),
                        "tags": data.get("tags", []),
                        "file": f.name,
                    })
                except Exception:
                    continue
            if templates:
                logger.info("[live_server] G10: Loaded %d templates via fallback YAML parser", len(templates))
                return JSONResponse({"templates": templates})
    except Exception as exc2:
        logger.warning("[live_server] G10: Fallback template loading failed: %s", str(exc2)[:200])

    return JSONResponse({"templates": [], "error": "No templates found"})


@app.get("/api/pipelines")
async def list_pipelines():
    """List all custom pipelines + templates."""
    try:
        from src.polaris_graph.pipeline_definition import list_templates
        templates = list_templates()
        custom = [
            {
                "pipeline_id": pid,
                "name": p.get("name", "Untitled"),
                "description": p.get("description", ""),
                "total_nodes": sum(
                    len(m.get("stages", [])) for m in p.get("macro_stages", [])
                ),
                "macro_count": len(p.get("macro_stages", [])),
                "tags": p.get("tags", []),
                "is_template": False,
            }
            for pid, p in _custom_pipelines.items()
        ]
        return JSONResponse({"pipelines": templates + custom})
    except Exception as exc:
        logger.warning("[live_server] Pipeline list failed: %s", str(exc)[:200])
        return JSONResponse({"pipelines": [], "error": str(exc)[:200]})


@app.post("/api/pipelines")
async def create_pipeline(request: Request):
    """Create a new custom pipeline."""
    try:
        from src.polaris_graph.pipeline_definition import PipelineDefinition
        body = await request.json()
        pipeline = PipelineDefinition(**body)
        data = pipeline.model_dump()
        _custom_pipelines[pipeline.pipeline_id] = data
        return JSONResponse({"pipeline_id": pipeline.pipeline_id, "status": "created"})
    except Exception as exc:
        logger.warning("[live_server] Pipeline create failed: %s", str(exc)[:300])
        return JSONResponse({"error": str(exc)[:300]}, status_code=422)


@app.get("/api/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    """Get a pipeline definition (custom or template)."""
    try:
        # Check custom pipelines first
        if pipeline_id in _custom_pipelines:
            return JSONResponse(_custom_pipelines[pipeline_id])
        # Check templates
        from src.polaris_graph.pipeline_definition import load_template
        for stem in ["standard_research", "quick_scan", "academic_focus",
                      "compliance_review", "multi_vector"]:
            tpl = load_template(stem)
            if tpl and tpl.pipeline_id == pipeline_id:
                return JSONResponse(tpl.model_dump())
        return JSONResponse({"error": "Pipeline not found"}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


@app.put("/api/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: str, request: Request):
    """Update a custom pipeline."""
    try:
        from src.polaris_graph.pipeline_definition import PipelineDefinition
        if pipeline_id not in _custom_pipelines:
            return JSONResponse({"error": "Pipeline not found (templates are read-only)"}, status_code=404)
        body = await request.json()
        body["pipeline_id"] = pipeline_id
        pipeline = PipelineDefinition(**body)
        _custom_pipelines[pipeline_id] = pipeline.model_dump()
        return JSONResponse({"pipeline_id": pipeline_id, "status": "updated"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:300]}, status_code=422)


@app.delete("/api/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    """Delete a custom pipeline."""
    if pipeline_id in _custom_pipelines:
        del _custom_pipelines[pipeline_id]
        return JSONResponse({"status": "deleted"})
    return JSONResponse({"error": "Pipeline not found or is a template"}, status_code=404)


@app.post("/api/pipelines/{pipeline_id}/validate")
async def validate_pipeline(pipeline_id: str):
    """Validate a pipeline definition."""
    try:
        from src.polaris_graph.pipeline_definition import PipelineDefinition
        data = _custom_pipelines.get(pipeline_id)
        if not data:
            return JSONResponse({"error": "Pipeline not found"}, status_code=404)
        pipeline = PipelineDefinition(**data)
        # Validation happens in model_validator
        return JSONResponse({
            "valid": True,
            "total_nodes": pipeline.total_nodes,
            "execution_order": pipeline.get_execution_order(),
        })
    except Exception as exc:
        return JSONResponse({"valid": False, "error": str(exc)[:300]})


@app.post("/api/pipelines/{pipeline_id}/run")
async def run_pipeline(pipeline_id: str, request: Request):
    """Run a pipeline with a research query."""
    try:
        from src.polaris_graph.pipeline_definition import PipelineDefinition, load_template
        body = await request.json()
        query = body.get("query", "")
        if not query:
            return JSONResponse({"error": "Query is required"}, status_code=422)

        # Load pipeline
        data = _custom_pipelines.get(pipeline_id)
        if data:
            pipeline = PipelineDefinition(**data)
        else:
            # Try templates
            pipeline = None
            for stem in ["standard_research", "quick_scan", "academic_focus",
                          "compliance_review", "multi_vector"]:
                tpl = load_template(stem)
                if tpl and tpl.pipeline_id == pipeline_id:
                    pipeline = tpl
                    break
            if not pipeline:
                return JSONResponse({"error": "Pipeline not found"}, status_code=404)

        # For now, run via standard pipeline with config overrides
        # Full dynamic_graph execution is Sprint 4 advanced feature
        logger.info(
            "[live_server] Pipeline run requested: %s (%s), query='%s'",
            pipeline.name, pipeline_id, query[:100],
        )
        return JSONResponse({
            "status": "accepted",
            "pipeline_id": pipeline_id,
            "pipeline_name": pipeline.name,
            "config_overrides": pipeline.config_overrides,
            "message": "Pipeline run queued. Use standard /api/research endpoint with config_overrides.",
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:300]}, status_code=500)


# --- Wizard endpoints ---

@app.post("/api/wizard/start")
async def wizard_start():
    """Start a new pipeline wizard session."""
    try:
        from src.polaris_graph.pipeline_wizard import wizard
        result = wizard.start_session()
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


@app.post("/api/wizard/chat/{session_id}")
async def wizard_chat(session_id: str, request: Request):
    """Send a message to the pipeline wizard."""
    try:
        from src.polaris_graph.pipeline_wizard import wizard
        body = await request.json()
        message = body.get("message", "")
        if not message:
            return JSONResponse({"error": "Message is required"}, status_code=422)
        result = wizard.chat(session_id, message)
        if "error" in result:
            return JSONResponse(result, status_code=404)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


@app.get("/api/wizard/draft/{session_id}")
async def wizard_draft(session_id: str):
    """Get the current pipeline draft from the wizard."""
    try:
        from src.polaris_graph.pipeline_wizard import wizard
        draft = wizard.get_draft(session_id)
        if not draft:
            return JSONResponse({"error": "No draft available"}, status_code=404)
        return JSONResponse(draft)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


@app.post("/api/wizard/finalize/{session_id}")
async def wizard_finalize(session_id: str):
    """Finalize the wizard session and save the pipeline."""
    try:
        from src.polaris_graph.pipeline_wizard import wizard
        draft = wizard.finalize(session_id)
        if not draft:
            return JSONResponse({"error": "No draft to finalize"}, status_code=404)
        # Auto-save to custom pipelines
        pid = draft.get("pipeline_id", "")
        _custom_pipelines[pid] = draft
        return JSONResponse({"pipeline_id": pid, "status": "finalized"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


# --- Sovereign mode info endpoint ---

@app.get("/api/system/info")
async def system_info():
    """Return system info including sovereign mode status."""
    sovereign = os.getenv("PG_SOVEREIGN_MODE", "0") == "1"
    rbac = os.getenv("PG_RBAC_ENABLED", "0") == "1"
    return JSONResponse({
        "sovereign_mode": sovereign,
        "rbac_enabled": rbac,
        "deployment_mode": os.getenv("POLARIS_DEPLOYMENT_MODE", "development"),
        "llm_provider": "local" if sovereign else "openrouter",
        "default_role": os.getenv("PG_DEFAULT_USER_ROLE", "admin"),
    })


# --- G2: RBAC — /api/auth/me endpoint ---

@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Return current user info from auth token, or default admin if auth disabled."""
    if _AUTH_AVAILABLE and get_current_user is not None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from src.auth.auth_middleware import get_auth_manager
                auth_mgr = get_auth_manager()
                token = auth_header.split(" ", 1)[1]
                payload = auth_mgr.validate_token(token)
                if payload:
                    return JSONResponse({
                        "user_id": payload.user_id,
                        "username": payload.username,
                        "role": payload.role,
                        "email": f"{payload.username}@polaris.local",
                    })
            except Exception:
                pass
    # Fallback: return default role from env
    default_role = os.getenv("PG_DEFAULT_USER_ROLE", "admin")
    return JSONResponse({
        "user_id": "default",
        "username": "operator",
        "role": default_role,
        "email": "operator@polaris.local",
    })


# ---------------------------------------------------------------------------
# Campaign management endpoints
# ---------------------------------------------------------------------------
@app.post("/api/campaigns")
async def create_campaign(req: CampaignRequest):
    """Create a new multi-query research campaign.

    Accepts a campaign name, description, list of queries, and depth preset.
    Returns the campaign_id and initial status.
    """
    try:
        campaign = _campaign_manager.create(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Sprint 1, Task 1A.2: Persist to SQLite
    await _campaign_manager._persist_campaign(campaign)

    return JSONResponse({
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "total_queries": campaign.total_queries,
        "status": campaign.status,
        "message": (
            f"Campaign created with {campaign.total_queries} queries. "
            f"Use POST /api/campaigns/{campaign.campaign_id}/start to begin."
        ),
    })


@app.get("/api/campaigns")
async def list_campaigns():
    """List all campaigns with summary status."""
    campaigns = _campaign_manager.list_all()
    return JSONResponse({"campaigns": campaigns, "total": len(campaigns)})


@app.get("/api/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get detailed campaign status including per-query results."""
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", campaign_id)
    campaign = _campaign_manager.get(safe_id)
    if not campaign:
        raise HTTPException(
            status_code=404, detail=f"Campaign not found: {safe_id}",
        )

    return JSONResponse({
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "description": campaign.description,
        "depth": campaign.depth,
        "status": campaign.status,
        "created_at": campaign.created_at,
        "started_at": campaign.started_at,
        "completed_at": campaign.completed_at,
        "total_queries": campaign.total_queries,
        "completed_count": campaign.completed_count,
        "failed_count": campaign.failed_count,
        "progress": (
            f"{campaign.completed_count + campaign.failed_count}"
            f"/{campaign.total_queries}"
        ),
        "queries": [q.model_dump() for q in campaign.queries],
        "campaign_context": campaign.campaign_context,
    })


@app.post("/api/campaigns/{campaign_id}/start")
async def start_campaign(campaign_id: str):
    """Start executing a campaign (queues queries sequentially)."""
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", campaign_id)
    campaign = _campaign_manager.get(safe_id)
    if not campaign:
        raise HTTPException(
            status_code=404, detail=f"Campaign not found: {safe_id}",
        )

    try:
        await _campaign_manager.start(safe_id)
    except RuntimeError as exc:
        return JSONResponse(
            {"error": str(exc)},
            status_code=409,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return JSONResponse({
        "campaign_id": safe_id,
        "status": "running",
        "message": (
            f"Campaign started. {campaign.total_queries} queries "
            f"will execute sequentially."
        ),
    })


@app.delete("/api/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Cancel and delete a campaign."""
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", campaign_id)
    deleted = _campaign_manager.delete(safe_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Campaign not found: {safe_id}",
        )

    # Sprint 1: delete from SQLite too
    if _CAMPAIGN_STORE_AVAILABLE and _db_delete_campaign is not None:
        try:
            await _db_delete_campaign(safe_id)
        except Exception as exc:
            logger.warning("Failed to delete campaign from store: %s", exc)

    return JSONResponse({
        "campaign_id": safe_id,
        "status": "cancelled",
        "message": "Campaign cancelled and deleted.",
    })


@app.get("/api/campaigns/{campaign_id}/live")
async def get_campaign_live(campaign_id: str):
    """Get campaign with per-vector node_status for Campaign Map.

    Returns the same data as GET /api/campaigns/{id} plus the NOVA Phase 1
    fields: current_node, node_status, node_metrics, faithfulness,
    source_count, citation_count, elapsed_ms.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", campaign_id)
    campaign = _campaign_manager.get(safe_id)
    if not campaign:
        raise HTTPException(
            status_code=404, detail=f"Campaign not found: {safe_id}",
        )

    return JSONResponse({
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "description": campaign.description,
        "depth": campaign.depth,
        "status": campaign.status,
        "created_at": campaign.created_at,
        "started_at": campaign.started_at,
        "completed_at": campaign.completed_at,
        "total_queries": campaign.total_queries,
        "completed_count": campaign.completed_count,
        "failed_count": campaign.failed_count,
        "progress": (
            f"{campaign.completed_count + campaign.failed_count}"
            f"/{campaign.total_queries}"
        ),
        "queries": [q.model_dump() for q in campaign.queries],
    })


@app.post("/api/campaigns/plan")
async def generate_campaign_plan(request: Request):
    """AI-generate a research plan from a broad query.

    Uses OpenRouterClient to decompose a broad research query into
    grouped domains with specific research vectors.
    """
    body = await request.json()
    query = body.get("query", "").strip()
    depth = body.get("depth", "standard")

    if not query:
        raise HTTPException(status_code=422, detail="query is required")

    if not _OPENROUTER_CLIENT_AVAILABLE or _openrouter_client is None:
        raise HTTPException(
            status_code=503,
            detail="LLM client not available for plan generation",
        )

    system_prompt = (
        "You are a research planning assistant. Given a broad research query, "
        "decompose it into 2-5 thematic domains, each containing 2-6 specific "
        "research vectors (precise search queries). Return valid JSON only.\n\n"
        "JSON format:\n"
        "{\n"
        '  "title": "Plan title",\n'
        '  "domains": [\n'
        "    {\n"
        '      "name": "Domain Name",\n'
        '      "vectors": [\n'
        '        {"query": "Specific research query", "type": "standard"},\n'
        '        {"query": "Another query", "type": "standard"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Each vector query should be specific and searchable\n"
        "- type is always 'standard' unless the user specifies custom\n"
        "- Cover different angles/perspectives of the topic\n"
        "- Avoid redundant or overlapping queries"
    )

    depth_hints = {
        "quick": "Generate 2-3 domains with 2-3 vectors each (quick survey).",
        "standard": "Generate 3-4 domains with 3-5 vectors each.",
        "deep": "Generate 4-5 domains with 4-6 vectors each (comprehensive).",
    }
    user_prompt = (
        f"Research query: {query}\n\n"
        f"Depth: {depth}. {depth_hints.get(depth, depth_hints['standard'])}"
    )

    try:
        response = await _openrouter_client.generate(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=1024,
            temperature=0.7,
        )
        raw = response.content.strip()

        # Strip code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        plan = json.loads(raw)

        # Validate structure
        if not isinstance(plan.get("domains"), list):
            plan = {"title": query[:100], "domains": []}
        for domain in plan.get("domains", []):
            if not isinstance(domain.get("vectors"), list):
                domain["vectors"] = []

        # Compute estimates
        total_vectors = sum(
            len(d.get("vectors", []))
            for d in plan.get("domains", [])
        )
        minutes_per_vector = {"quick": 5, "standard": 12, "deep": 25}
        cost_per_vector = {"quick": 0.30, "standard": 0.80, "deep": 2.00}
        plan["estimated_minutes"] = (
            total_vectors * minutes_per_vector.get(depth, 12)
        )
        plan["estimated_cost_usd"] = round(
            total_vectors * cost_per_vector.get(depth, 0.80), 2
        )

    except json.JSONDecodeError:
        plan = {
            "title": query[:100],
            "domains": [{
                "name": "General",
                "vectors": [{"query": query, "type": "standard"}],
            }],
            "estimated_minutes": 12,
            "estimated_cost_usd": 0.80,
        }
    except Exception as exc:
        logger.warning("Plan generation failed: %s", str(exc)[:300])
        raise HTTPException(
            status_code=500,
            detail=f"Plan generation failed: {str(exc)[:200]}",
        )

    return JSONResponse(plan)


# ---------------------------------------------------------------------------
# Vector Library endpoints (Vector Library → Campaign integration)
# ---------------------------------------------------------------------------
@app.get("/api/vectors/library")
async def get_vector_library():
    """Return all 13 C-POLAR stages with question templates for the vector library browser."""
    try:
        from config.vector_library import (
            VECTOR_LIBRARY,
            STAGE_NAMES,
            STAGE_VECTOR_COUNTS,
            REGIONAL_STAGES,
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Vector library module not available",
        )

    stages = []
    for stage_num in range(1, 14):
        templates = [
            t for t in VECTOR_LIBRARY.template_vectors
            if t["stage"] == stage_num
        ]
        stages.append({
            "stage": stage_num,
            "name": STAGE_NAMES[stage_num],
            "vector_count": STAGE_VECTOR_COUNTS[stage_num],
            "is_regional": stage_num in REGIONAL_STAGES,
            "templates": [
                {
                    "vector_number": t["vector_number"],
                    "question_template": t["question_template"],
                }
                for t in templates
            ],
        })

    return JSONResponse({
        "total_vectors": 175,
        "total_stages": 13,
        "stages": stages,
    })


class LibraryCampaignRequest(BaseModel):
    """Request body for POST /api/campaigns/from-library."""

    application: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Application name (e.g. Household_Water_Filter)",
    )
    depth: str = Field(
        default="standard",
        pattern="^(quick|standard|deep)$",
        description="Research depth preset",
    )
    vectors: Optional[list[dict]] = Field(
        default=None,
        description="Optional custom vector list from editor. Each: {query, region, stage}",
    )
    research_brief: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Domain context injected into every vector's planning prompt",
    )


@app.post("/api/campaigns/from-library")
async def create_campaign_from_library(req: LibraryCampaignRequest):
    """Create a 175-vector campaign from the C-POLAR vector library for a given application."""
    try:
        from config.vector_library import generate_all_vectors_for_application
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Vector library module not available",
        )

    # Normalize application name: spaces → underscores, strip edges
    application = req.application.strip().replace(" ", "_")
    if not application:
        raise HTTPException(status_code=422, detail="application is required")

    if req.vectors:
        # Use custom vectors from the frontend library editor
        query_statuses = [
            CampaignQueryStatus(
                query=v["query"],
                application=application,
                region=v.get("region", "GLOBAL"),
            )
            for v in req.vectors
            if v.get("query", "").strip()
        ]
        if not query_statuses:
            raise HTTPException(status_code=422, detail="No valid vectors provided")
    else:
        # Default: generate all 175 from templates (existing behavior)
        vectors = generate_all_vectors_for_application(application)
        if len(vectors) != 175:
            raise HTTPException(
                status_code=500,
                detail=f"Vector generation produced {len(vectors)} vectors, expected 175",
            )
        query_statuses = [
            CampaignQueryStatus(
                query=v["question"],
                application=v.get("application", application),
                region=v.get("region", "GLOBAL"),
            )
            for v in vectors
        ]

    # Build campaign
    campaign_id = (
        f"CAMP_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        f"_{uuid.uuid4().hex[:6]}"
    )

    display_name = application.replace("_", " ")
    vec_count = len(query_statuses)
    campaign = CampaignData(
        campaign_id=campaign_id,
        name=f"C-POLAR: {display_name}",
        description=f"C-POLAR analysis for {display_name} ({vec_count} vectors)",
        depth=req.depth,
        status="created",
        created_at=datetime.now(timezone.utc).isoformat(),
        queries=query_statuses,
        total_queries=len(query_statuses),
        application=application,
        research_brief=req.research_brief,
    )

    _campaign_manager._campaigns[campaign_id] = campaign
    await _campaign_manager._persist_campaign(campaign)

    return JSONResponse({
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "total_queries": campaign.total_queries,
        "status": campaign.status,
        "application": application,
        "message": (
            f"C-POLAR campaign created with {campaign.total_queries} vectors for "
            f"{display_name}. Use POST /api/campaigns/{campaign_id}/start to begin."
        ),
    })


# ---------------------------------------------------------------------------
# Document upload/management endpoints (A7.2)
# ---------------------------------------------------------------------------
@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and ingest a document for local RAG.

    Accepts multipart file upload. Saves to a temporary file, calls
    DocumentIngester.ingest(), and returns document metadata.
    Max file size governed by PG_MAX_UPLOAD_SIZE_MB env var (default 100).
    """
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available. Check server logs.",
        )

    # Validate filename exists
    if not file.filename:
        raise HTTPException(status_code=422, detail="No filename provided.")

    # Read file content and validate size before writing to disk
    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > PG_MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size {size_mb:.1f} MB exceeds maximum allowed "
                f"{PG_MAX_UPLOAD_SIZE_MB} MB (PG_MAX_UPLOAD_SIZE_MB)."
            ),
        )

    # Determine suffix from original filename
    original_name = file.filename
    suffix = Path(original_name).suffix.lower() if original_name else ""

    # Write to a temp file for ingestion
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="polaris_upload_")
        safe_name = "".join(
            c if (c.isalnum() or c in "._- ") else "_"
            for c in original_name
        ) or f"upload{suffix}"
        tmp_path = Path(tmp_dir) / safe_name
        tmp_path.write_bytes(file_bytes)

        result = await _document_ingester.ingest(tmp_path)

        logger.info(
            "Document uploaded: doc_id=%s filename=%s size=%.2f MB pages=%d",
            result["doc_id"],
            original_name,
            size_mb,
            result.get("pages", 0),
        )

        return JSONResponse({
            "doc_id": result["doc_id"],
            "filename": original_name,
            "size_mb": round(size_mb, 3),
            "pages": result.get("pages", 0),
            "content_chars": len(result.get("content", "")),
            "metadata": result.get("metadata", {}),
            "message": "Document uploaded and ingested successfully.",
        })

    except DocumentIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Document upload failed: filename=%s error=%s",
            original_name, str(exc)[:300],
        )
        raise HTTPException(
            status_code=500,
            detail=f"Document ingestion failed: {str(exc)[:200]}",
        )
    finally:
        # Clean up temp directory
        if tmp_dir and Path(tmp_dir).exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/api/documents/list")
async def list_documents():
    """List all uploaded documents with metadata."""
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available. Check server logs.",
        )

    documents = _document_ingester.list_documents()
    return JSONResponse({
        "documents": documents,
        "total": len(documents),
    })


@app.get("/api/documents/{doc_id}")
async def get_document_detail(doc_id: str):
    """Get a specific document's metadata and content preview (first 500 chars)."""
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available. Check server logs.",
        )

    # Sanitize doc_id to prevent path traversal
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", doc_id)
    doc = _document_ingester.get_document(safe_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {safe_id}",
        )

    content = doc.get("content", "")
    return JSONResponse({
        "doc_id": safe_id,
        "content_preview": content[:500],
        "content_chars": len(content),
        "pages": doc.get("pages", 0),
        "metadata": doc.get("metadata", {}),
    })


@app.put("/api/documents/{doc_id}")
async def update_document_label(doc_id: str, request: Request):
    """Update document metadata (label)."""
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available. Check server logs.",
        )
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", doc_id)
    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(status_code=503, detail="Document storage directory not configured.")
    doc_dir = DOCUMENT_STORAGE_DIR / safe_id
    if not doc_dir.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {safe_id}")
    body = await request.json()
    label = body.get("label", "")
    # Persist label in metadata JSON
    meta_path = doc_dir / "metadata.json"
    metadata: dict = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}
    metadata["label"] = label
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return JSONResponse({"doc_id": safe_id, "label": label, "status": "updated"})


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Remove a previously uploaded document and its extracted artefacts."""
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available. Check server logs.",
        )

    # Sanitize doc_id to prevent path traversal
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", doc_id)

    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(
            status_code=503,
            detail="Document storage directory not configured.",
        )

    doc_dir = DOCUMENT_STORAGE_DIR / safe_id
    if not doc_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {safe_id}",
        )

    try:
        shutil.rmtree(str(doc_dir))
        logger.info("Document deleted: doc_id=%s", safe_id)
        return JSONResponse({
            "doc_id": safe_id,
            "status": "deleted",
            "message": "Document and all artefacts removed.",
        })
    except OSError as exc:
        logger.error("Failed to delete document %s: %s", safe_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(exc)[:200]}",
        )


@app.post("/api/documents/{doc_id}/parse")
async def reparse_document(doc_id: str):
    """Re-parse a previously uploaded document.

    Locates the original file in storage and re-runs the ingestion
    pipeline to update the extracted content and metadata.
    """
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available. Check server logs.",
        )

    # Sanitize doc_id to prevent path traversal
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", doc_id)

    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(
            status_code=503,
            detail="Document storage directory not configured.",
        )

    doc_dir = DOCUMENT_STORAGE_DIR / safe_id
    if not doc_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {safe_id}",
        )

    # Find the original file
    original_files = list(doc_dir.glob("original.*"))
    if not original_files:
        raise HTTPException(
            status_code=422,
            detail=f"Original file not found for document {safe_id}. Cannot re-parse.",
        )

    original_path = original_files[0]

    try:
        result = await _document_ingester.ingest(original_path)
        logger.info(
            "Document re-parsed: doc_id=%s pages=%d chars=%d",
            result["doc_id"],
            result.get("pages", 0),
            len(result.get("content", "")),
        )
        return JSONResponse({
            "doc_id": result["doc_id"],
            "pages": result.get("pages", 0),
            "content_chars": len(result.get("content", "")),
            "metadata": result.get("metadata", {}),
            "message": "Document re-parsed successfully.",
        })
    except DocumentIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Document re-parse failed: doc_id=%s error=%s",
            safe_id, str(exc)[:300],
        )
        raise HTTPException(
            status_code=500,
            detail=f"Re-parse failed: {str(exc)[:200]}",
        )


# ---------------------------------------------------------------------------
# Source Briefing (NotebookLM-style auto-generated introduction)
# ---------------------------------------------------------------------------
_brief_cache: dict[str, dict[str, Any]] = {}

_BRIEF_MAX_SOURCES = int(os.getenv("PG_BRIEF_MAX_SOURCES", "12"))
_BRIEF_CHARS_PER_SOURCE = int(os.getenv("PG_BRIEF_CHARS_PER_SOURCE", "6000"))

# Stopwords for grounding check (common English words that don't indicate topic)
_GROUNDING_STOPWORDS = frozenset({
    "the", "and", "that", "this", "with", "from", "have", "been", "were",
    "they", "their", "which", "about", "into", "more", "also", "than",
    "other", "some", "these", "when", "would", "could", "should", "there",
    "most", "such", "only", "over", "between", "through", "after", "before",
    "while", "where", "what", "very", "much", "each", "both", "does", "many",
    "well", "just", "like", "then", "being", "because", "including",
    "based", "using", "according", "found", "however", "provides", "shows",
    "research", "study", "studies", "sources", "data", "information",
})


def _extract_key_sentences(content: str, max_chars: int) -> str:
    """Extract the most information-dense sentences from content.

    Scores each sentence by presence of numbers/percentages, proper nouns,
    sentence length, and positional bonuses for intro/conclusion.
    Returns top-scoring sentences in original order within the char budget.

    Falls back to ``content[:max_chars]`` if no sentences are found.
    """
    if not content or len(content) <= max_chars:
        return content or ""

    # Split into sentences (handles common abbreviations)
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', content)
    if not sentences:
        return content[:max_chars]

    scored: list[tuple[float, int, str]] = []
    total = len(sentences)

    for idx, sent in enumerate(sentences):
        words = sent.split()
        if len(words) < 3:
            continue

        score = 0.0

        # Numbers / percentages (+2 each, max 6)
        num_count = len(re.findall(r'\d+\.?\d*%?', sent))
        score += min(num_count * 2, 6)

        # Proper nouns — capitalized words not at sentence start (+1 each, max 4)
        proper = sum(
            1 for w in words[1:]
            if w[0].isupper() and w.lower() not in _GROUNDING_STOPWORDS
        )
        score += min(proper, 4)

        # Sentence length (capped at +3)
        score += min(len(words) / 10.0, 3.0)

        # Intro / conclusion positional boost (×1.5)
        if idx < 3 or idx >= total - 3:
            score *= 1.5

        # Penalize fragments (<5 words)
        if len(words) < 5:
            score *= 0.3

        scored.append((score, idx, sent))

    if not scored:
        return content[:max_chars]

    # Sort by score desc, pick top within budget
    scored.sort(key=lambda t: t[0], reverse=True)

    selected: list[tuple[int, str]] = []
    budget = max_chars
    for _score, idx, sent in scored:
        if len(sent) + 1 > budget:
            continue
        selected.append((idx, sent))
        budget -= len(sent) + 1  # +1 for space join

    # Reconstruct in original order
    selected.sort(key=lambda t: t[0])
    return " ".join(s for _, s in selected) if selected else content[:max_chars]


class SourceBriefRequest(BaseModel):
    """Request body for POST /api/documents/brief."""

    doc_ids: list[str] = Field(..., min_length=1)


@app.post("/api/documents/brief")
async def generate_source_brief(req: SourceBriefRequest):
    """Generate a NotebookLM-style source briefing.

    Accepts a list of doc_ids, fetches excerpts from each, calls the LLM
    for a 2-3 sentence summary + 3 suggested research questions.
    Results are cached by sorted doc_ids hash.
    """
    if not _DOCUMENT_INGESTER_AVAILABLE or _document_ingester is None:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion not available.",
        )

    # --- Cache check ---
    cache_key = hashlib.md5(
        "|".join(sorted(req.doc_ids)).encode()
    ).hexdigest()

    if cache_key in _brief_cache:
        cached = _brief_cache[cache_key]
        return JSONResponse({**cached, "cached": True})

    # --- Collect source excerpts ---
    excerpts: list[dict[str, str]] = []
    for doc_id in req.doc_ids:
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", doc_id)
        doc = _document_ingester.get_document(safe_id)
        if doc and doc.get("content"):
            excerpts.append({
                "filename": doc.get("metadata", {}).get(
                    "original_filename",
                    doc.get("metadata", {}).get("filename", safe_id),
                ),
                "content": _extract_key_sentences(
                    doc["content"], _BRIEF_CHARS_PER_SOURCE
                ),
            })

    if not excerpts:
        fallback = {
            "summary": "Your sources are ready. Enter a research question to begin.",
            "questions": [],
            "source_count": 0,
        }
        return JSONResponse({**fallback, "cached": False})

    # Cap at max sources (sorted by content length desc, take top N)
    excerpts.sort(key=lambda e: len(e["content"]), reverse=True)
    excerpts = excerpts[:_BRIEF_MAX_SOURCES]

    # --- Build LLM prompt ---
    system_prompt = (
        "You are a research briefing assistant. CRITICAL RULES:\n"
        "1. ONLY reference information explicitly present in the SOURCE TEXT below\n"
        "2. Do NOT interpret filenames as topic indicators — read the actual text\n"
        "3. Write like a knowledgeable colleague briefing someone: narrative, "
        "not a data dump. Explain what was done, what was found, and why it matters.\n"
        "4. Translate technical identifiers into readable language "
        "(e.g. pp_activated_dvs_350K_dry → plasma-activated polypropylene "
        "with DVS at 350 K, dry process)\n"
        "5. Bold **conceptual terms and methods** (e.g. steered molecular "
        "dynamics, ensemble validation), NOT raw numbers or data values"
    )
    user_prompt = (
        "Below are the user's uploaded sources. Read carefully.\n\n"
    )
    for i, ex in enumerate(excerpts, 1):
        user_prompt += (
            f"=== SOURCE {i}: {ex['filename']} ===\n"
            f"{ex['content']}\n"
            f"=== END SOURCE {i} ===\n\n"
        )
    user_prompt += (
        "STEP 1 — EXTRACT: Identify 5-8 most important facts, findings, "
        "and methods from the source text.\n"
        "STEP 2 — SYNTHESIZE: Using ONLY those facts, write a narrative "
        "briefing (4-6 sentences). Structure as:\n"
        "  - Sentence 1: What this body of work is about (context)\n"
        "  - Sentences 2-4: Key findings, methods, and results (the story)\n"
        "  - Sentence 5-6: Why it matters or what it enables (significance)\n"
        "Bold **methods, concepts, and scientific terms** — not numbers. "
        "Translate any code-style identifiers into human-readable names.\n"
        "STEP 3 — QUESTIONS: 3 specific questions (10-15 words each) that "
        "a reader would naturally ask after reading this briefing. "
        "No bold markers in questions.\n\n"
        "Output this exact JSON (no other text):\n"
        "{\n"
        '  "key_facts": ["fact 1 from source", "fact 2 from source", ...],\n'
        '  "summary": "4-6 sentence narrative briefing in colleague style",\n'
        '  "questions": ["Short question?", "Another question?", "Third question?"]\n'
        "}"
    )

    # --- Call LLM ---
    brief_client = _brief_llm_client or _openrouter_client
    if not _OPENROUTER_CLIENT_AVAILABLE or brief_client is None:
        fallback = {
            "summary": "Your sources are ready. Enter a research question to begin.",
            "questions": [],
            "source_count": len(excerpts),
            "error": "LLM client not available.",
        }
        return JSONResponse({**fallback, "cached": False})

    # Combine all source text for grounding validation
    combined_source_text = " ".join(ex["content"] for ex in excerpts).lower()
    key_facts: list[str] = []

    try:
        logger.info(
            "Brief LLM call: model=%s, sources=%d, chars=%d",
            brief_client.model, len(excerpts),
            sum(len(ex["content"]) for ex in excerpts),
        )

        # Use raw HTTP for non-default models (avoids Kimi-specific
        # provider routing, reasoning params, and min_p that cause 404s)
        _brief_model_env = os.getenv("PG_BRIEF_MODEL", "")
        if _brief_model_env and _brief_model_env != os.getenv(
            "OPENROUTER_DEFAULT_MODEL", ""
        ):
            import httpx as _httpx
            _brief_body = {
                "model": _brief_model_env,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            }
            async with _httpx.AsyncClient(timeout=120.0) as _hc:
                _resp = await _hc.post(
                    f"{os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')}"
                    "/chat/completions",
                    json=_brief_body,
                    headers={
                        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                )
                _resp.raise_for_status()
                _rjson = _resp.json()
                raw = _rjson["choices"][0]["message"]["content"].strip()
                logger.info(
                    "Brief raw HTTP OK: model=%s, tokens_in=%s, tokens_out=%s",
                    _brief_model_env,
                    _rjson.get("usage", {}).get("prompt_tokens", "?"),
                    _rjson.get("usage", {}).get("completion_tokens", "?"),
                )
        else:
            response = await brief_client.generate(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=1024,
                temperature=0.3,
            )
            raw = response.content.strip()

        # Strip code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        summary = str(parsed.get("summary", ""))
        key_facts = parsed.get("key_facts", [])
        if not isinstance(key_facts, list):
            key_facts = []
        key_facts = [str(f) for f in key_facts[:8]]
        questions = parsed.get("questions", [])
        if not isinstance(questions, list):
            questions = []
        # Strip **bold** from questions and limit to 3
        questions = [
            re.sub(r"\*\*(.+?)\*\*", r"\1", str(q)) for q in questions[:3]
        ]

        # --- Grounding validation ---
        # Count % of significant summary words found in combined source text
        summary_words = [
            w.lower() for w in re.findall(r'[a-zA-Z]{4,}', summary)
            if w.lower() not in _GROUNDING_STOPWORDS
        ]
        if summary_words:
            grounded = sum(
                1 for w in summary_words if w in combined_source_text
            )
            grounding_ratio = grounded / len(summary_words)
            logger.info(
                "Brief grounding check: %.1f%% (%d/%d significant words)",
                grounding_ratio * 100, grounded, len(summary_words),
            )

            if grounding_ratio < 0.40 and key_facts:
                # Hallucination detected — rebuild from key_facts
                logger.warning(
                    "Brief grounding %.1f%% < 40%% — rebuilding from "
                    "key_facts (%d facts)",
                    grounding_ratio * 100, len(key_facts),
                )
                summary = " ".join(key_facts[:5])

    except Exception as exc:
        logger.warning("Source brief LLM call failed: %s", str(exc)[:300])
        summary = "Your sources are ready. Enter a research question to begin."
        questions = []

    result = {
        "summary": summary,
        "questions": questions,
        "source_count": len(excerpts),
        "key_facts": key_facts,
        "model": brief_client.model,
    }

    _brief_cache[cache_key] = result
    return JSONResponse({**result, "cached": False})


# ---------------------------------------------------------------------------
# Source Search & Import (NotebookLM-style)
# ---------------------------------------------------------------------------

_SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
_JINA_API_KEY = os.getenv("JINA_API_KEY", "")


@app.post("/api/sources/search")
async def search_web_sources(req: SourceSearchRequest):
    """Search the web for potential sources using Serper API.

    Returns a list of search results that can be imported as document sources.
    """
    if not _SERPER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="SERPER_API_KEY not configured. Cannot search web sources.",
        )

    endpoint_map = {
        "web": "https://google.serper.dev/search",
        "scholar": "https://google.serper.dev/scholar",
        "news": "https://google.serper.dev/news",
    }
    url = endpoint_map.get(req.source_type, endpoint_map["web"])

    payload = {
        "q": req.query,
        "num": req.max_results,
    }
    headers = {
        "X-API-KEY": _SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error("Serper search failed: status=%d body=%s", resp.status, error_text[:200])
                    raise HTTPException(status_code=502, detail="Search provider returned an error.")

                data = await resp.json()

        # Normalize results across endpoint types
        results = []
        raw_results = data.get("organic", []) or data.get("news", []) or data.get("results", [])
        for item in raw_results[:req.max_results]:
            result = {
                "title": item.get("title", "Untitled"),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "domain": "",
            }
            # Extract domain from URL
            link = item.get("link", "")
            if link:
                try:
                    from urllib.parse import urlparse
                    result["domain"] = urlparse(link).netloc
                except Exception:
                    result["domain"] = link[:40]
            results.append(result)

        logger.info("Source search: query=%r type=%s results=%d", req.query[:60], req.source_type, len(results))
        return JSONResponse({"results": results, "query": req.query, "source_type": req.source_type})

    except aiohttp.ClientError as exc:
        logger.error("Source search network error: %s", str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"Search failed: {str(exc)[:100]}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Source search unexpected error: %s", str(exc)[:200])
        raise HTTPException(status_code=500, detail=f"Search failed: {str(exc)[:100]}")


@app.post("/api/sources/import-url")
async def import_url_source(req: SourceImportUrlRequest):
    """Import a website URL as a document source.

    Fetches the page content (via Jina Reader or direct fetch),
    stores it as a document in the document storage.

    YouTube URLs are detected automatically and handled via
    youtube_transcript_api for transcript extraction.
    """
    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(status_code=503, detail="Document storage not configured.")

    # Fetch content from URL
    content = ""
    title = req.title or ""
    fetch_url = req.url
    source_type = "website"
    video_id = ""

    # ---------------------------------------------------------------
    # YouTube URL detection: extract transcript before Jina/fallback
    # ---------------------------------------------------------------
    _yt_pattern = re.compile(
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)"
        r"([a-zA-Z0-9_-]{11})"
    )
    yt_match = _yt_pattern.search(fetch_url)
    if yt_match:
        video_id = yt_match.group(1)
        logger.info(
            "YouTube URL detected: video_id=%s url=%s",
            video_id, fetch_url[:80],
        )
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id)
            content = " ".join([entry.text for entry in transcript])
            source_type = "youtube"
            if not title:
                title = f"YouTube video {video_id}"
            logger.info(
                "YouTube transcript fetched: video_id=%s chars=%d",
                video_id, len(content),
            )
        except ImportError:
            logger.warning(
                "youtube_transcript_api not installed. "
                "Falling back to normal URL fetch for YouTube video %s. "
                "Install with: pip install youtube-transcript-api",
                video_id,
            )
        except Exception as exc:
            logger.warning(
                "YouTube transcript fetch failed for %s: %s. "
                "Falling back to normal URL fetch.",
                video_id, str(exc)[:200],
            )

    # ---------------------------------------------------------------
    # Standard URL fetch (Jina Reader / direct) -- skipped if YouTube
    # transcript already populated content.
    # ---------------------------------------------------------------
    if not content or len(content) < 100:
        try:
            # Try Jina Reader first for clean extraction
            if _JINA_API_KEY:
                jina_url = f"https://r.jina.ai/{fetch_url}"
                jina_headers = {"Authorization": f"Bearer {_JINA_API_KEY}", "Accept": "text/plain", "Accept-Encoding": "gzip, deflate"}
                async with aiohttp.ClientSession(auto_decompress=False) as session:
                    async with session.get(jina_url, headers=jina_headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            raw_b = await resp.read()
                            enc = resp.headers.get("Content-Encoding", "").lower()
                            if enc == "gzip":
                                import gzip as _gz
                                raw_b = _gz.decompress(raw_b)
                            elif enc == "deflate":
                                import zlib as _zl
                                raw_b = _zl.decompress(raw_b)
                            content = raw_b.decode(resp.charset or "utf-8", errors="replace")
                            if not title:
                                # Extract title from first line (Jina format: Title\nURL\n...)
                                lines = content.strip().split("\n")
                                if lines:
                                    title = lines[0].strip()

            # Fallback: direct fetch (auto_decompress=False avoids brotli decode errors)
            if not content or len(content) < 100:
                async with aiohttp.ClientSession(auto_decompress=False) as session:
                    async with session.get(fetch_url, timeout=aiohttp.ClientTimeout(total=20), headers={"User-Agent": "Mozilla/5.0 (compatible; POLARIS/1.0)", "Accept-Encoding": "gzip, deflate", "Accept": "text/html,application/xhtml+xml"}) as resp:
                        if resp.status == 200:
                            raw_bytes = await resp.read()
                            # Decompress gzip/deflate manually if needed
                            encoding = resp.headers.get("Content-Encoding", "").lower()
                            if encoding == "gzip":
                                import gzip as _gzip
                                raw_bytes = _gzip.decompress(raw_bytes)
                            elif encoding == "deflate":
                                import zlib as _zlib
                                raw_bytes = _zlib.decompress(raw_bytes)
                            # Detect charset
                            charset = resp.charset or "utf-8"
                            try:
                                raw_html = raw_bytes.decode(charset, errors="replace")
                            except (LookupError, UnicodeDecodeError):
                                raw_html = raw_bytes.decode("utf-8", errors="replace")
                            # Basic HTML stripping for content extraction
                            import re as _re
                            text = _re.sub(r"<script[^>]*>[\s\S]*?</script>", "", raw_html)
                            text = _re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text)
                            text = _re.sub(r"<[^>]+>", " ", text)
                            text = _re.sub(r"\s+", " ", text).strip()
                            content = text[:50000]  # Cap at 50K chars

                            if not title:
                                # Try extracting <title>
                                title_match = _re.search(r"<title[^>]*>(.*?)</title>", raw_html, _re.IGNORECASE)
                                title = title_match.group(1).strip() if title_match else fetch_url[:60]
                        else:
                            raise HTTPException(status_code=502, detail=f"Failed to fetch URL (HTTP {resp.status})")

        except aiohttp.ClientError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {str(exc)[:100]}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"URL import failed: {str(exc)[:100]}")

    if not content or len(content) < 50:
        raise HTTPException(status_code=422, detail="Could not extract meaningful content from URL.")

    # Store as document
    prefix = "yt" if source_type == "youtube" else "web"
    doc_id = f"{prefix}_{hashlib.md5(fetch_url.encode()).hexdigest()[:12]}"
    doc_dir = DOCUMENT_STORAGE_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write content (extracted.txt matches document_ingester.get_document() convention)
    (doc_dir / "extracted.txt").write_text(content, encoding="utf-8")

    # Write metadata
    metadata = {
        "doc_id": doc_id,
        "filename": title[:100] if title else fetch_url[:60],
        "label": title[:50] if title else "",
        "source_url": fetch_url,
        "source_type": source_type,
        "content_chars": len(content),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    if video_id:
        metadata["video_id"] = video_id

    (doc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    message = "YouTube transcript imported as source." if source_type == "youtube" else "Website imported as source."
    logger.info("URL source imported: doc_id=%s url=%s type=%s chars=%d", doc_id, fetch_url[:80], source_type, len(content))
    return JSONResponse({
        "doc_id": doc_id,
        "filename": metadata["filename"],
        "title": title,
        "content_chars": len(content),
        "source_url": fetch_url,
        "message": message,
    })


@app.post("/api/sources/import-text")
async def import_text_source(req: SourceImportTextRequest):
    """Import pasted text as a document source."""
    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(status_code=503, detail="Document storage not configured.")

    # Store as document
    doc_id = f"txt_{hashlib.md5(req.text[:500].encode()).hexdigest()[:12]}"
    doc_dir = DOCUMENT_STORAGE_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    content = req.text.strip()
    (doc_dir / "extracted.txt").write_text(content, encoding="utf-8")

    metadata = {
        "doc_id": doc_id,
        "filename": req.title[:100],
        "label": req.title[:50],
        "source_type": "text",
        "content_chars": len(content),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    (doc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    logger.info("Text source imported: doc_id=%s title=%s chars=%d", doc_id, req.title[:40], len(content))
    return JSONResponse({
        "doc_id": doc_id,
        "filename": metadata["filename"],
        "title": req.title,
        "content_chars": len(content),
        "message": "Text imported as source.",
    })


# ---------------------------------------------------------------------------
# Cloud Storage Integration (Google Drive, OneDrive, Dropbox)
# ---------------------------------------------------------------------------
class CloudImportRequest(BaseModel):
    """Request body for POST /api/cloud/{provider}/import."""

    file_id: str = Field(..., description="Cloud file ID or path")
    file_name: str = Field(default="", description="Original file name")
    mime_type: str = Field(default="", description="MIME type of the file")


class CloudBatchImportRequest(BaseModel):
    """Request body for POST /api/cloud/{provider}/import-batch."""

    files: list[CloudImportRequest] = Field(..., description="Files to import")


@app.get("/api/cloud/status")
async def cloud_status():
    """Return configured/connected status for all 3 cloud providers."""
    if not _CLOUD_PROVIDERS_AVAILABLE or get_cloud_status is None:
        return JSONResponse({
            "google_drive": {"configured": False, "connected": False},
            "onedrive": {"configured": False, "connected": False},
            "dropbox": {"configured": False, "connected": False},
        })
    return JSONResponse(get_cloud_status())


@app.get("/api/cloud/callback.html")
async def cloud_callback_page():
    """Static HTML page for OAuth callback (closes popup, notifies opener)."""
    html_content = """<!DOCTYPE html>
<html><head><title>Connecting...</title>
<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0}
.msg{text-align:center}.spin{border:3px solid rgba(255,255,255,0.1);
border-top:3px solid #7c3aed;border-radius:50%;width:32px;height:32px;
animation:s 0.8s linear infinite;margin:0 auto 16px}
@keyframes s{to{transform:rotate(360deg)}}</style></head>
<body><div class="msg"><div class="spin"></div><p>Connecting to cloud storage...</p>
<p id="status"></p></div>
<script>
(function(){
  var params = new URLSearchParams(window.location.search);
  var code = params.get('code');
  var state = params.get('state');
  var provider = params.get('provider') || '';
  var statusEl = document.getElementById('status');

  if (!code) {
    statusEl.textContent = 'Authorization failed: no code received.';
    return;
  }

  // Exchange code for tokens via our backend
  fetch('/api/cloud/' + provider + '/callback?code=' + encodeURIComponent(code) +
        '&state=' + encodeURIComponent(state || ''))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        statusEl.textContent = 'Error: ' + data.error;
        return;
      }
      statusEl.textContent = 'Connected! Closing...';
      if (window.opener) {
        window.opener.postMessage({type: 'cloud_auth_success', provider: provider}, '*');
      }
      setTimeout(function() { window.close(); }, 500);
    })
    .catch(function(err) {
      statusEl.textContent = 'Connection failed: ' + err.message;
    });
})();
</script></body></html>"""
    return HTMLResponse(content=html_content)


@app.get("/api/cloud/{provider}/authorize")
async def cloud_authorize(provider: str, request: Request):
    """Redirect to OAuth consent screen (opened in popup)."""
    if not _CLOUD_PROVIDERS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Cloud providers not available.")
    if provider not in cloud_provider_registry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    prov = cloud_provider_registry[provider]
    if not prov.is_configured:
        raise HTTPException(status_code=400, detail=f"{provider} OAuth not configured. Set {prov.CLIENT_ID_ENV} and {prov.CLIENT_SECRET_ENV} in .env")

    # Build redirect URI pointing to our callback page
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/cloud/callback.html?provider={provider}"
    auth_url = prov.get_authorize_url(redirect_uri)
    return RedirectResponse(url=auth_url)


@app.get("/api/cloud/{provider}/callback")
async def cloud_callback(provider: str, code: str, state: str = "", request: Request = None):
    """Handle OAuth redirect — exchange code for tokens."""
    if not _CLOUD_PROVIDERS_AVAILABLE:
        return JSONResponse({"error": "Cloud providers not available."}, status_code=503)
    if provider not in cloud_provider_registry:
        return JSONResponse({"error": f"Unknown provider: {provider}"}, status_code=404)

    prov = cloud_provider_registry[provider]

    try:
        base_url = str(request.base_url).rstrip("/") if request else ""
        redirect_uri = f"{base_url}/api/cloud/callback.html?provider={provider}"
        prov.exchange_code(code, redirect_uri)
        logger.info("Cloud auth success: provider=%s", provider)
        return JSONResponse({"success": True, "provider": provider})
    except Exception as exc:
        logger.error("Cloud auth failed: provider=%s error=%s", provider, str(exc))
        return JSONResponse({"error": f"Token exchange failed: {str(exc)[:200]}"}, status_code=400)


@app.delete("/api/cloud/{provider}/disconnect")
async def cloud_disconnect(provider: str):
    """Revoke connection and delete stored tokens."""
    if not _CLOUD_PROVIDERS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Cloud providers not available.")
    if provider not in cloud_provider_registry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    cloud_provider_registry[provider].disconnect()
    logger.info("Cloud disconnected: provider=%s", provider)
    return JSONResponse({"success": True, "provider": provider, "message": f"{provider} disconnected."})


@app.get("/api/cloud/{provider}/files")
async def cloud_list_files(provider: str, folder_id: str = ""):
    """List folder contents from cloud storage."""
    if not _CLOUD_PROVIDERS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Cloud providers not available.")
    if provider not in cloud_provider_registry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    prov = cloud_provider_registry[provider]
    if not prov.is_connected:
        raise HTTPException(status_code=401, detail=f"{provider} not connected. Authorize first.")

    try:
        result = prov.list_folder(folder_id or None)
        return JSONResponse(result)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("Cloud list_folder failed: provider=%s error=%s", provider, str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(exc)[:200]}")


@app.post("/api/cloud/{provider}/import")
async def cloud_import_file(provider: str, req: CloudImportRequest):
    """Download a file from cloud storage and store as a document source."""
    if not _CLOUD_PROVIDERS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Cloud providers not available.")
    if provider not in cloud_provider_registry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(status_code=503, detail="Document storage not configured.")

    prov = cloud_provider_registry[provider]
    if not prov.is_connected:
        raise HTTPException(status_code=401, detail=f"{provider} not connected.")

    try:
        filename, content_bytes = prov.download_file(req.file_id, req.mime_type)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("Cloud download failed: provider=%s file=%s error=%s", provider, req.file_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Download failed: {str(exc)[:200]}")

    # Use provided filename or the one from the provider
    display_name = req.file_name or filename

    # Generate doc_id from provider + file_id
    doc_id = f"cloud_{hashlib.md5(f'{provider}_{req.file_id}'.encode()).hexdigest()[:12]}"
    doc_dir = DOCUMENT_STORAGE_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Try text extraction
    text_content = ""
    original_path = doc_dir / display_name
    original_path.write_bytes(content_bytes)

    # For text-like files, decode directly
    text_extensions = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".log", ".py", ".js", ".ts"}
    suffix = Path(display_name).suffix.lower()
    if suffix in text_extensions:
        try:
            text_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content_bytes.decode("latin-1", errors="replace")
    elif _DOCUMENT_INGESTER_AVAILABLE and _document_ingester is not None:
        # Use DocumentIngester for PDF, DOCX, etc.
        try:
            result = _document_ingester.ingest_file(str(original_path))
            text_content = result.get("text", "") if isinstance(result, dict) else str(result)
        except Exception as exc:
            logger.warning("Document ingester failed for %s: %s", display_name, str(exc))
            text_content = ""

    if text_content:
        (doc_dir / "extracted.txt").write_text(text_content, encoding="utf-8")

    # Write metadata
    metadata = {
        "doc_id": doc_id,
        "filename": display_name,
        "label": Path(display_name).stem[:50],
        "source_type": f"cloud_{provider}",
        "cloud_provider": provider,
        "cloud_file_id": req.file_id,
        "content_chars": len(text_content),
        "file_size": len(content_bytes),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    (doc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    logger.info("Cloud import: provider=%s file=%s doc_id=%s chars=%d", provider, display_name, doc_id, len(text_content))
    return JSONResponse({
        "doc_id": doc_id,
        "filename": display_name,
        "content_chars": len(text_content),
        "message": f"Imported from {provider}.",
    })


@app.post("/api/cloud/{provider}/import-batch")
async def cloud_import_batch(provider: str, req: CloudBatchImportRequest):
    """Import multiple files from cloud storage."""
    if not _CLOUD_PROVIDERS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Cloud providers not available.")
    if provider not in cloud_provider_registry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if DOCUMENT_STORAGE_DIR is None:
        raise HTTPException(status_code=503, detail="Document storage not configured.")

    results = []
    for file_req in req.files:
        try:
            single_req = CloudImportRequest(
                file_id=file_req.file_id,
                file_name=file_req.file_name,
                mime_type=file_req.mime_type,
            )
            resp = await cloud_import_file(provider, single_req)
            body = json.loads(resp.body.decode("utf-8"))
            results.append({"success": True, **body})
        except HTTPException as exc:
            results.append({"success": False, "file_name": file_req.file_name, "error": exc.detail})
        except Exception as exc:
            results.append({"success": False, "file_name": file_req.file_name, "error": str(exc)[:200]})

    imported = sum(1 for r in results if r.get("success"))
    logger.info("Cloud batch import: provider=%s total=%d imported=%d", provider, len(req.files), imported)
    return JSONResponse({
        "results": results,
        "imported": imported,
        "total": len(req.files),
    })


# ---------------------------------------------------------------------------
# PDF/HTML Export
# ---------------------------------------------------------------------------
def _md_to_html(md_text: str) -> str:
    """Convert markdown to HTML using regex-based conversion.

    Handles: headers, bold, italic, code blocks, inline code, links,
    unordered/ordered lists, blockquotes, horizontal rules, paragraphs.
    No external dependencies required.
    """
    if not md_text:
        return ""

    lines = md_text.split("\n")
    html_lines = []
    in_code_block = False
    in_list = False
    list_type = None  # "ul" or "ol"

    for line in lines:
        # Fenced code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = line.strip()[3:].strip()
                if lang:
                    html_lines.append(
                        '<pre><code class="language-' + html.escape(lang) + '">'
                    )
                else:
                    html_lines.append("<pre><code>")
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(html.escape(line))
            continue

        stripped = line.strip()

        # Close list if we hit a non-list line
        if in_list and not stripped.startswith("- ") and not stripped.startswith("* ") and not re.match(r"^\d+\.\s", stripped):
            html_lines.append(f"</{list_type}>")
            in_list = False
            list_type = None

        # Horizontal rule
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            html_lines.append("<hr>")
            continue

        # Headers
        header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header_match:
            level = len(header_match.group(1))
            text = _inline_md(header_match.group(2))
            html_lines.append(f"<h{level}>{text}</h{level}>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            text = _inline_md(stripped[2:])
            html_lines.append(f"<blockquote>{text}</blockquote>")
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list or list_type != "ul":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ul>")
                in_list = True
                list_type = "ul"
            text = _inline_md(stripped[2:])
            html_lines.append(f"<li>{text}</li>")
            continue

        # Ordered list
        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            if not in_list or list_type != "ol":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ol>")
                in_list = True
                list_type = "ol"
            text = _inline_md(ol_match.group(1))
            html_lines.append(f"<li>{text}</li>")
            continue

        # Empty line
        if not stripped:
            html_lines.append("")
            continue

        # Paragraph
        html_lines.append(f"<p>{_inline_md(stripped)}</p>")

    # Close any open list
    if in_list:
        html_lines.append(f"</{list_type}>")

    if in_code_block:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, code, links) to HTML.

    Input text is HTML-escaped first to prevent XSS, then markdown
    patterns are converted.
    """
    text = html.escape(text)
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)
    # Inline code: `code`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # Links: [text](url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    # CITE markers: [CITE:xxx] -> superscript
    text = re.sub(r"\[CITE:([^\]]+)\]", r'<sup>[\1]</sup>', text)
    # Citation numbers: [1], [2], etc.
    text = re.sub(r"\[(\d+)\]", r'<sup>[\1]</sup>', text)
    return text



# ---------------------------------------------------------------------------
# Dead URL Detection for PDF Export (I.3)
# ---------------------------------------------------------------------------
async def _check_url_health(url: str, timeout: float = 5.0) -> dict:
    """Check if a URL is accessible. Returns status dict."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                return {"url": url, "status": resp.status, "alive": 200 <= resp.status < 400}
    except Exception:
        return {"url": url, "status": 0, "alive": False}


async def _check_bibliography_urls(bibliography: list[dict], concurrency: int = 10) -> list[dict]:
    """Check all bibliography URLs concurrently with a semaphore limit.

    Returns list of health check results with url, status, and alive fields.
    """
    urls = []
    for entry in bibliography:
        if isinstance(entry, dict):
            url = entry.get("url", "")
            if url and url.startswith("http"):
                urls.append(url)
        elif isinstance(entry, str) and entry.startswith("http"):
            urls.append(entry)

    if not urls:
        return []

    # Deduplicate
    unique_urls = list(dict.fromkeys(urls))

    sem = asyncio.Semaphore(concurrency)

    async def check_with_sem(u: str) -> dict:
        async with sem:
            return await _check_url_health(u)

    results = await asyncio.gather(
        *[check_with_sem(u) for u in unique_urls],
        return_exceptions=True,
    )

    health_results = []
    for r in results:
        if isinstance(r, dict):
            health_results.append(r)
        elif isinstance(r, Exception):
            health_results.append({"url": "unknown", "status": 0, "alive": False})

    return health_results


def _build_pdf_html(result: dict, report_md: str, url_health: list[dict] | None = None) -> str:
    """Build a complete HTML document for PDF export.

    Includes: report content, bibliography, quality summary,
    audit certificate, and SHA-256 hash of the result JSON.
    All user-provided text is HTML-escaped for XSS prevention.
    """
    # Extract metadata (all user text escaped)
    vector_id = html.escape(result.get("vector_id", result.get("vid", "unknown")))
    query = html.escape(result.get("original_query", result.get("query", "N/A")))
    status = html.escape(str(result.get("status", "unknown")))
    version = html.escape(os.getenv("POLARIS_VERSION", "0.9.0"))
    timestamp = html.escape(
        result.get("timestamps", {}).get("completed", datetime.now(timezone.utc).isoformat())
    )

    # Quality metrics
    quality = result.get("quality_metrics", {}) or {}
    faithfulness = quality.get("faithfulness_pct", quality.get("faithfulness", "N/A"))
    if isinstance(faithfulness, (int, float)):
        faithfulness_str = f"{faithfulness:.1f}%"
    else:
        faithfulness_str = html.escape(str(faithfulness))

    evidence_count = len(result.get("evidence", []))
    bibliography = result.get("bibliography", [])
    source_count = len(bibliography)
    iteration_count = result.get("iteration_count", 0)

    # SHA-256 of the result JSON
    result_json_bytes = json.dumps(result, sort_keys=True, default=str).encode("utf-8")
    result_hash = hashlib.sha256(result_json_bytes).hexdigest()

    # Convert report markdown to HTML
    report_html = _md_to_html(report_md)

    # Build URL health lookup
    health_lookup: dict[str, dict] = {}
    if url_health:
        for h in url_health:
            health_lookup[h.get("url", "")] = h

    # Build bibliography HTML
    biblio_html_parts = []
    dead_count = 0
    total_checked = 0
    for i, entry in enumerate(bibliography, 1):
        if isinstance(entry, dict):
            title = html.escape(str(entry.get("title", "Untitled")))
            url = html.escape(str(entry.get("url", "")))
            raw_url = str(entry.get("url", ""))
            authors = html.escape(str(entry.get("authors", "")))
            year = html.escape(str(entry.get("year", "")))

            # Build cell content incrementally (avoids nested f-string issues)
            cell = "<strong>" + title + "</strong>"
            if year:
                cell += " (" + year + ")"
            if authors:
                cell += "<br><em>" + authors + "</em>"
            if url:
                cell += '<br><a href="' + url + '">' + url + "</a>"

            # URL health status column
            status_cell = ""
            if health_lookup and raw_url in health_lookup:
                total_checked += 1
                h = health_lookup[raw_url]
                if h.get("alive"):
                    status_cell = '<td style="text-align:center;color:#2a7a4a;font-size:14pt">&#10003;</td>'
                else:
                    dead_count += 1
                    status_cell = '<td style="text-align:center;color:#c0392b;font-size:14pt">&#10007;</td>'
            elif health_lookup:
                status_cell = '<td style="text-align:center;color:#999;font-size:9pt">--</td>'

            biblio_html_parts.append(
                '<tr><td class="bib-num">[' + str(i) + "]</td>"
                "<td>" + cell + "</td>" + status_cell + "</tr>"
            )
        elif isinstance(entry, str):
            status_cell = ""
            if health_lookup:
                status_cell = '<td style="text-align:center;color:#999;font-size:9pt">--</td>'
            biblio_html_parts.append(
                '<tr><td class="bib-num">[' + str(i) + "]</td>"
                "<td>" + html.escape(entry) + "</td>" + status_cell + "</tr>"
            )

    # Dead URL warning banner
    dead_url_banner = ""
    if total_checked > 0 and dead_count > 0:
        dead_pct = (dead_count / total_checked) * 100
        if dead_pct > 20:
            dead_url_banner = (
                '<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;'
                'padding:8pt;margin:8pt 0;font-size:10pt;color:#856404">'
                '<strong>Warning:</strong> '
                + str(dead_count) + ' of ' + str(total_checked)
                + ' URLs (' + f"{dead_pct:.0f}" + '%) returned errors or were unreachable.'
                + '</div>'
            )
        else:
            dead_url_banner = (
                '<div style="font-size:9pt;color:#666;margin:4pt 0">'
                + str(dead_count) + ' of ' + str(total_checked)
                + ' URLs returned errors.</div>'
            )

    # Add Status header if health data available
    bib_header = ""
    if health_lookup:
        bib_header = "<tr><th></th><th>Source</th><th>Status</th></tr>"

    biblio_table = (
        dead_url_banner
        + '<table class="bibliography">' + bib_header + "\n".join(biblio_html_parts) + "</table>"
        if biblio_html_parts
        else "<p><em>No bibliography entries available.</em></p>"
    )

    # Build evidence chain appendix (top 50 for brevity)
    evidence = result.get("evidence", [])
    evidence_html_parts = []
    for ev in evidence[:50]:
        if not isinstance(ev, dict):
            continue
        ev_id = html.escape(str(ev.get("id", ev.get("evidence_id", "?"))))
        source_url = html.escape(str(ev.get("source_url", ev.get("url", "N/A"))))
        quote = html.escape(str(ev.get("quote", ev.get("text", ""))[:300]))
        verdict = html.escape(str(ev.get("nli_verdict", ev.get("verdict", "N/A"))))
        tier = html.escape(str(ev.get("tier", "N/A")))

        evidence_html_parts.append(
            '<div class="evidence-item">'
            '<div class="ev-header">' + ev_id + " [" + tier + "] -- " + verdict + "</div>"
            '<div class="ev-source">Source: ' + source_url + "</div>"
            '<div class="ev-quote">&ldquo;' + quote + '&rdquo;</div>'
            "</div>"
        )

    evidence_appendix = (
        "\n".join(evidence_html_parts)
        if evidence_html_parts
        else "<p><em>No evidence chain available.</em></p>"
    )
    if len(evidence) > 50:
        evidence_note = (
            "<p><em>Showing " + str(min(50, len(evidence)))
            + " of " + str(len(evidence)) + " evidence items.</em></p>"
        )
    else:
        evidence_note = ""

    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<title>POLARIS Research Report - " + vector_id + "</title>\n"
        "<style>\n@page { size: A4; margin: 2.5cm 2cm; }\n"
        'body { font-family: "Georgia", "Times New Roman", serif; font-size: 11pt; line-height: 1.6; color: #1a1a1a; max-width: 210mm; margin: 0 auto; padding: 2cm; background: #fff; }\n'
        "h1 { font-size: 20pt; color: #0d2137; border-bottom: 3px solid #0d2137; padding-bottom: 8pt; margin-top: 0; }\n"
        "h2 { font-size: 15pt; color: #1a3a5c; border-bottom: 1px solid #ccc; padding-bottom: 4pt; margin-top: 24pt; page-break-after: avoid; }\n"
        "h3 { font-size: 13pt; color: #2a4a6c; margin-top: 18pt; page-break-after: avoid; }\n"
        "h4, h5, h6 { font-size: 11pt; color: #3a5a7c; margin-top: 14pt; }\n"
        "p { margin: 6pt 0; text-align: justify; }\n"
        "sup { font-size: 8pt; color: #2a6496; }\n"
        "a { color: #2a6496; text-decoration: none; }\na:hover { text-decoration: underline; }\n"
        "blockquote { border-left: 3px solid #ccc; padding-left: 12pt; margin-left: 0; color: #555; font-style: italic; }\n"
        "pre { background: #f5f5f5; padding: 10pt; border-radius: 4px; overflow-x: auto; font-size: 9pt; line-height: 1.4; }\n"
        'code { font-family: "Consolas", "Monaco", monospace; font-size: 9pt; background: #f0f0f0; padding: 1pt 3pt; border-radius: 2px; }\n'
        "pre code { background: none; padding: 0; }\n"
        "ul, ol { margin: 6pt 0; padding-left: 24pt; }\nli { margin: 3pt 0; }\n"
        "hr { border: none; border-top: 1px solid #ccc; margin: 18pt 0; }\n"
        ".meta-box { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 16pt; margin: 16pt 0; }\n"
        ".meta-box table { width: 100%; border-collapse: collapse; }\n"
        ".meta-box td { padding: 4pt 8pt; vertical-align: top; }\n"
        ".meta-box td:first-child { font-weight: bold; width: 160pt; color: #555; }\n"
        ".quality-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10pt; margin: 12pt 0; }\n"
        ".quality-card { background: #f0f7ff; border: 1px solid #b8d4e8; border-radius: 4px; padding: 10pt; text-align: center; }\n"
        ".quality-card .label { font-size: 9pt; color: #666; text-transform: uppercase; }\n"
        ".quality-card .value { font-size: 16pt; font-weight: bold; color: #0d2137; }\n"
        ".bibliography { width: 100%; border-collapse: collapse; margin: 12pt 0; }\n"
        ".bibliography td { padding: 6pt 8pt; border-bottom: 1px solid #eee; vertical-align: top; font-size: 10pt; }\n"
        ".bib-num { width: 30pt; font-weight: bold; color: #2a6496; }\n"
        ".evidence-item { border: 1px solid #e0e0e0; border-radius: 4px; padding: 8pt; margin: 6pt 0; font-size: 9pt; page-break-inside: avoid; }\n"
        ".ev-header { font-weight: bold; color: #1a3a5c; }\n"
        ".ev-source { color: #666; font-size: 8pt; word-break: break-all; }\n"
        ".ev-quote { color: #333; font-style: italic; margin-top: 4pt; }\n"
        ".audit-cert { background: #f0f8f0; border: 2px solid #4a9; border-radius: 6px; padding: 16pt; margin: 24pt 0; }\n"
        '.audit-cert h3 { color: #2a7a4a; margin-top: 0; }\n'
        '.hash { font-family: "Consolas", monospace; font-size: 8pt; color: #666; word-break: break-all; }\n'
        "@media print { body { padding: 0; } .no-print { display: none; } }\n"
        "</style>\n</head>\n<body>\n\n"
        "<h1>POLARIS Research Report</h1>\n\n"
        '<div class="meta-box">\n<table>\n'
        "<tr><td>Vector ID</td><td>" + vector_id + "</td></tr>\n"
        "<tr><td>Research Query</td><td>" + query + "</td></tr>\n"
        "<tr><td>Status</td><td>" + status + "</td></tr>\n"
        "<tr><td>Generated</td><td>" + timestamp + "</td></tr>\n"
        "<tr><td>Pipeline Version</td><td>" + version + "</td></tr>\n"
        "</table>\n</div>\n\n"
        '<h2>Quality Summary</h2>\n<div class="quality-grid">\n'
        '<div class="quality-card"><div class="label">Faithfulness</div><div class="value">' + faithfulness_str + "</div></div>\n"
        '<div class="quality-card"><div class="label">Evidence</div><div class="value">' + str(evidence_count) + "</div></div>\n"
        '<div class="quality-card"><div class="label">Sources</div><div class="value">' + str(source_count) + "</div></div>\n"
        '<div class="quality-card"><div class="label">Iterations</div><div class="value">' + str(iteration_count) + "</div></div>\n"
        "</div>\n\n<h2>Report</h2>\n" + report_html + "\n\n"
        "<h2>Bibliography</h2>\n" + biblio_table + "\n\n"
        "<h2>Evidence Chain (Appendix)</h2>\n" + evidence_note + "\n" + evidence_appendix + "\n\n"
        '<div class="audit-cert">\n<h3>Audit Certificate</h3>\n<table>\n'
        "<tr><td><strong>Pipeline Version:</strong></td><td>" + version + "</td></tr>\n"
        "<tr><td><strong>Vector ID:</strong></td><td>" + vector_id + "</td></tr>\n"
        "<tr><td><strong>Query:</strong></td><td>" + query + "</td></tr>\n"
        "<tr><td><strong>Timestamp:</strong></td><td>" + timestamp + "</td></tr>\n"
        "<tr><td><strong>Evidence Count:</strong></td><td>" + str(evidence_count) + "</td></tr>\n"
        "<tr><td><strong>Source Count:</strong></td><td>" + str(source_count) + "</td></tr>\n"
        "<tr><td><strong>Faithfulness:</strong></td><td>" + faithfulness_str + "</td></tr>\n"
        '<tr><td><strong>Result SHA-256:</strong></td><td><span class="hash">' + result_hash + "</span></td></tr>\n"
        "</table>\n</div>\n\n<hr>\n"
        '<p style="text-align: center; font-size: 8pt; color: #999;">\n'
        "Generated by POLARIS Research Pipeline v" + version + " | " + timestamp + "\n</p>\n\n"
        "</body>\n</html>"
    )


@app.post("/api/research/export/{vector_id}")
async def export_pdf(vector_id: str):
    """Export a completed research result as PDF (WeasyPrint) or HTML fallback.

    The export includes: full report, bibliography, evidence chain appendix,
    quality summary, and an audit certificate with SHA-256 hash.
    """
    # Sanitize vector_id to prevent path traversal
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", vector_id)
    result_path = Path("outputs/polaris_graph") / f"{safe_id}.json"
    if not result_path.exists():
        raise HTTPException(404, "Result not found")

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"Failed to read result: {exc}")

    report_path = Path("outputs/polaris_graph") / f"{safe_id}_report.md"
    report_md = ""
    if report_path.exists():
        try:
            report_md = report_path.read_text(encoding="utf-8")
        except OSError:
            report_md = result.get("final_report", result.get("report", ""))
    else:
        report_md = result.get("final_report", result.get("report", ""))

    # Check bibliography URL health (non-blocking, short timeout)
    bibliography = result.get("bibliography", [])
    url_health = []
    try:
        url_health = await _check_bibliography_urls(bibliography, concurrency=10)
        logger.info(
            "URL health check: %d/%d alive for vector_id=%s",
            sum(1 for h in url_health if h.get("alive")),
            len(url_health),
            safe_id,
        )
    except Exception as exc:
        logger.warning("URL health check failed (non-fatal): %s", exc)

    # Generate HTML for PDF
    export_html = _build_pdf_html(result, report_md, url_health=url_health)

    # Try WeasyPrint first, fall back to HTML response
    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=export_html).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="POLARIS_' + safe_id + '.pdf"',
            },
        )
    except (ImportError, OSError) as exc:
        logger.info("WeasyPrint not available (%s), returning HTML export for vector_id=%s", type(exc).__name__, safe_id)
        return HTMLResponse(
            content=export_html,
            headers={
                "Content-Disposition": 'attachment; filename="POLARIS_' + safe_id + '.html"',
            },
        )


# ---------------------------------------------------------------------------
# DOCX export endpoint (A8.4)
# ---------------------------------------------------------------------------
@app.get("/api/research/export/{vector_id}/docx")
async def export_docx(vector_id: str):
    """Export a completed research result as Microsoft Word (.docx).

    Corporate styling with Calibri, proper headings, bibliography,
    quality summary, and audit certificate.
    """
    safe_id = re.sub(r"[^A-Za-z0-9_\-]", "", vector_id)
    output_dir = Path("outputs/polaris_graph")
    result_file = output_dir / f"{safe_id}.json"

    if not result_file.exists():
        raise HTTPException(status_code=404, detail=f"Result not found: {safe_id}")

    try:
        with open(result_file, "r", encoding="utf-8") as fh:
            report_data = json.load(fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {str(exc)[:200]}")

    try:
        from src.polaris_graph.export.docx_exporter import DocxExporter

        exporter = DocxExporter()
        export_path = Path("outputs") / f"POLARIS_{safe_id}.docx"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        exporter.export(report_data, export_path)

        return FileResponse(
            path=str(export_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"POLARIS_{safe_id}.docx",
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"python-docx not installed: {str(exc)[:200]}"
        )
    except Exception as exc:
        logger.error("[live_server] DOCX export failed: %s", str(exc)[:200])
        raise HTTPException(
            status_code=500,
            detail=f"DOCX export failed: {str(exc)[:200]}"
        )


# ---------------------------------------------------------------------------
# Static file serving (A7.1 frontend modularization)
# ---------------------------------------------------------------------------
@app.get("/static/{filepath:path}")
async def serve_static(filepath: str, request: Request):
    """Serve static files with ETag/304 support for proper cache validation."""
    file_path = (STATIC_DIR / filepath).resolve()
    if not str(file_path).startswith(str(STATIC_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Not found: {filepath}")

    norm = filepath.replace("\\", "/")
    etag_info = _STATIC_ETAGS.get(norm)
    if etag_info:
        client_etag = request.headers.get("if-none-match")
        if client_etag and client_etag == etag_info[0]:
            return Response(status_code=304, headers={"ETag": etag_info[0]})

    suffix = file_path.suffix.lower()
    media_types = {
        ".js": "application/javascript", ".css": "text/css",
        ".svg": "image/svg+xml", ".png": "image/png",
        ".jpg": "image/jpeg", ".ico": "image/x-icon",
        ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff",
    }

    headers = {"Cache-Control": "no-cache, must-revalidate"}
    if etag_info:
        from email.utils import formatdate
        headers["ETag"] = etag_info[0]
        headers["Last-Modified"] = formatdate(etag_info[1], usegmt=True)

    return FileResponse(
        path=str(file_path),
        media_type=media_types.get(suffix, "application/octet-stream"),
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Cloudflare Quick Tunnel
# ---------------------------------------------------------------------------
async def start_cloudflare_tunnel(port: int) -> Optional[str]:
    """Spawn cloudflared quick tunnel and return the public URL.

    Quick tunnels require no auth, no config. The URL is printed to stderr
    by cloudflared and we parse it out.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "cloudflared", "tunnel", "--url", f"http://localhost:{port}",
            "--ha-connections", "4",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.warning(
            "cloudflared not found on PATH. Install from "
            "https://developers.cloudflare.com/cloudflare-one/connections/"
            "connect-networks/downloads/"
        )
        return None

    url_pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

    # cloudflared prints the URL to stderr
    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                logger.debug("[cloudflared] %s", text)
            match = url_pattern.search(text)
            if match:
                return match.group(0)
        return None

    # Wait up to 30s for URL
    try:
        url = await asyncio.wait_for(read_stderr(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("Cloudflare tunnel timed out waiting for URL")
        url = None

    if url:
        logger.info("=" * 60)
        logger.info("CLOUDFLARE TUNNEL ACTIVE")
        logger.info("Public URL: %s", url)
        logger.info("=" * 60)

    return url


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Live Monitoring Server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PG_LIVE_SERVER_PORT,
        help=f"Server port (default: {PG_LIVE_SERVER_PORT})",
    )
    parser.add_argument(
        "--trace",
        type=str,
        default=None,
        help="Path to trace JSONL file (auto-discovers newest if omitted)",
    )
    parser.add_argument(
        "--no-tunnel",
        action="store_true",
        help="Skip Cloudflare tunnel",
    )
    args = parser.parse_args()

    global _tailer, _trace_path, _no_tunnel, _server_port

    # Discover or use specified trace file
    if args.trace:
        _trace_path = Path(args.trace)
        if not _trace_path.exists():
            logger.warning("Trace file not found: %s (will watch for creation)", _trace_path)
    else:
        _trace_path = discover_trace_file(PG_LIVE_TRACE_DIR)
        if _trace_path:
            logger.info("Auto-discovered trace file: %s", _trace_path)
        else:
            # Create a placeholder path -- TraceTailer handles non-existent files
            _trace_path = Path(PG_LIVE_TRACE_DIR) / "pg_trace_pending.jsonl"
            logger.warning(
                "No trace file found in %s. Will watch for new files.",
                PG_LIVE_TRACE_DIR,
            )

    _tailer = TraceTailer(_trace_path)
    _no_tunnel = args.no_tunnel
    _server_port = args.port

    logger.info("Starting POLARIS Live Server on port %d", args.port)
    logger.info("Dashboard: http://localhost:%d", args.port)
    logger.info("Trace file: %s", _trace_path)
    logger.info("Deployment mode: %s", POLARIS_DEPLOYMENT_MODE)
    logger.info("CORS origins: %s", _cors_origins)

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
