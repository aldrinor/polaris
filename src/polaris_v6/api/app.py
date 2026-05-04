"""FastAPI app factory for POLARIS v6.

Composes routers, wires OpenTelemetry instrumentation when configured,
and exposes the ASGI app via `app = create_app()` for uvicorn.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polaris_v6 import __version__
from polaris_v6.api.ambiguity import router as ambiguity_router
from polaris_v6.api.bundle import router as bundle_router
from polaris_v6.api.charts import router as charts_router
from polaris_v6.api.compare import router as compare_router
from polaris_v6.api.followup import router as followup_router
from polaris_v6.api.health import router as health_router
from polaris_v6.api.memory import router as memory_router
from polaris_v6.api.runs import router as runs_router
from polaris_v6.api.scope import router as scope_router
from polaris_v6.api.stream import router as stream_router
from polaris_v6.api.templates import router as templates_router
from polaris_v6.api.upload import router as upload_router

# Slice 001 (clinical scope discovery + ambiguity) and slice 002 (clinical
# retrieval). Each lives in polaris_graph.api per slice spec; we mount them
# under /api alongside the v6 routers so the frontend at /intake + /retrieval
# can call them without a separate origin.
from polaris_graph.api.intake_route import router as slice001_intake_router
from polaris_graph.api.retrieval_route import (
    get_fetch_fn as slice002_get_fetch_fn,
    router as slice002_retrieval_router,
)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN"):
        from polaris_v6.observability.otel_init import init_otel

        init_otel()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="POLARIS",
        version=__version__,
        description="Sovereign Canadian deep research AI",
        lifespan=_lifespan,
    )
    cors_origins = os.environ.get(
        "POLARIS_V6_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3737,http://localhost:3738,http://127.0.0.1:3000,http://127.0.0.1:3737,http://127.0.0.1:3738",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins if o.strip()],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(runs_router)
    app.include_router(stream_router)
    app.include_router(ambiguity_router)
    app.include_router(bundle_router)
    app.include_router(scope_router)
    app.include_router(upload_router)
    app.include_router(charts_router)
    app.include_router(followup_router)
    app.include_router(compare_router)
    app.include_router(memory_router)
    app.include_router(templates_router)

    # Slice 001 — POST /api/intake + GET /api/intake/health
    app.include_router(slice001_intake_router, prefix="/api")

    # Slice 002 — POST /api/retrieval + GET /api/retrieval/health.
    # Inject the real Serper + Semantic-Scholar fetcher when keys are
    # present; otherwise leave the dependency at the sentinel default
    # (returns 400 fetch_backend_unavailable, never silently degrades).
    if os.environ.get("SERPER_API_KEY", "").strip():
        from polaris_graph.retrieval2.real_fetcher import build_real_fetcher

        # Build once at startup; fetcher reuses httpx connections per call.
        _real_fetcher = build_real_fetcher()

        def _inject_real_fetcher():
            return _real_fetcher

        app.dependency_overrides[slice002_get_fetch_fn] = _inject_real_fetcher
    app.include_router(slice002_retrieval_router, prefix="/api")

    return app


app = create_app()
