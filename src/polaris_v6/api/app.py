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
from polaris_v6.api.health import router as health_router
from polaris_v6.api.runs import router as runs_router
from polaris_v6.api.scope import router as scope_router
from polaris_v6.api.stream import router as stream_router
from polaris_v6.api.upload import router as upload_router


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
    return app


app = create_app()
