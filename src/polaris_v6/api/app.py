"""FastAPI app factory for POLARIS v6.

Composes routers, wires OpenTelemetry instrumentation when configured,
and exposes the ASGI app via `app = create_app()` for uvicorn.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from polaris_v6 import __version__
from polaris_v6.api.health import router as health_router
from polaris_v6.api.runs import router as runs_router


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
    app.include_router(health_router)
    app.include_router(runs_router)
    return app


app = create_app()
