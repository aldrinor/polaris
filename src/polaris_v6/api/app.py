"""FastAPI app factory for POLARIS v6.

Composes routers, wires OpenTelemetry instrumentation when configured,
and exposes the ASGI app via `app = create_app()` for uvicorn.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polaris_v6 import __version__
from polaris_v6.api.ambiguity import router as ambiguity_router
from polaris_v6.api.auth import (
    require_auth as _require_auth,
    router as auth_router,
    verify_app_startup as _verify_auth_startup,
)
from polaris_v6.api.bundle import router as bundle_router
from polaris_v6.api.charts import router as charts_router
from polaris_v6.api.compare import router as compare_router
from polaris_v6.api.followup import router as followup_router
from polaris_v6.api.health import router as health_router
from polaris_v6.api.inspector import router as inspector_router
from polaris_v6.api.memory import router as memory_router
from polaris_v6.api.pins import router as pins_router
from polaris_v6.api.runs import router as runs_router
from polaris_v6.api.scope import router as scope_router
from polaris_v6.api.stream import router as stream_router
from polaris_v6.api.templates import router as templates_router
from polaris_v6.api.transparency import router as transparency_router
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
from polaris_graph.api.generation_route import (
    get_completion_fn as slice003_get_completion_fn,
    router as slice003_generation_router,
)
from polaris_graph.api.audit_bundle_route import (
    get_sign_fn as slice004_get_sign_fn,
    router as slice004_audit_bundle_router,
)
from polaris_graph.api.benchmark_route import (
    get_results_root as slice005_get_results_root,
    router as slice005_benchmark_router,
)
from polaris_graph.api.disambiguation_route import router as disambiguation_router
from polaris_graph.api.graph_route import router as graph_router


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN"):
        from polaris_v6.observability.otel_init import init_otel

        init_otel()
    yield


def create_app() -> FastAPI:
    # I-carney-004 LAW II: fail-loud at app construction if auth substrate
    # is misconfigured. Skipped via POLARIS_AUTH_DISABLED=1 in tests + dev.
    _verify_auth_startup()
    app = FastAPI(
        title="POLARIS",
        version=__version__,
        description="Sovereign Canadian deep research AI",
        lifespan=_lifespan,
        dependencies=[Depends(_require_auth)],
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
    app.include_router(auth_router)
    app.include_router(runs_router)
    app.include_router(stream_router)
    app.include_router(ambiguity_router)
    app.include_router(bundle_router)
    app.include_router(pins_router)
    app.include_router(scope_router)
    app.include_router(upload_router)
    app.include_router(charts_router)
    app.include_router(followup_router)
    app.include_router(compare_router)
    app.include_router(inspector_router)
    app.include_router(memory_router)
    app.include_router(templates_router)
    app.include_router(transparency_router)

    # Slice 001 — POST /api/intake + GET /api/intake/health
    app.include_router(slice001_intake_router, prefix="/api")

    # Slice 002 — POST /api/retrieval + GET /api/retrieval/health.
    # Inject the real Serper + Semantic-Scholar fetcher when keys are
    # present; otherwise leave the dependency at the sentinel default
    # (returns 400 fetch_backend_unavailable, never silently degrades).
    if os.environ.get("SERPER_API_KEY", "").strip():
        from polaris_graph.clinical_retrieval.real_fetcher import build_real_fetcher

        # Build once at startup; fetcher reuses httpx connections per call.
        _real_fetcher = build_real_fetcher()

        def _inject_real_fetcher():
            return _real_fetcher

        app.dependency_overrides[slice002_get_fetch_fn] = _inject_real_fetcher
    app.include_router(slice002_retrieval_router, prefix="/api")

    # Slice 003 — POST /api/generation + GET /api/generation/health.
    # When OPENROUTER_API_KEY is present, inject the real OpenRouter-backed
    # completion_fn (PR 7); otherwise leave the sentinel default in place
    # which returns 400 completion_backend_unavailable per LAW II.
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        from polaris_graph.clinical_generator.real_completion import build_real_completion

        _real_completion = build_real_completion()

        def _inject_real_completion():
            return _real_completion

        app.dependency_overrides[slice003_get_completion_fn] = _inject_real_completion
    app.include_router(slice003_generation_router, prefix="/api")

    # Slice 004 — POST /api/audit-bundle + GET /api/audit-bundle/health.
    # When POLARIS_GPG_KEY_ID is set, build the real GPGSigner and inject
    # it via dep override; otherwise leave sentinel default which yields
    # HTTP 503 (LAW II fail-loud — never ship unsigned bundles).
    if os.environ.get("POLARIS_GPG_KEY_ID", "").strip():
        from polaris_graph.audit_bundle.gpg_signer import build_gpg_signer

        _real_signer = build_gpg_signer()

        def _inject_real_signer():
            return _real_signer.sign

        app.dependency_overrides[slice004_get_sign_fn] = _inject_real_signer
    app.include_router(slice004_audit_bundle_router, prefix="/api")

    # Slice 005 — GET /api/benchmark/{id}/{scoreboard,report,summary}.
    # Reads pre-computed artifacts from POLARIS_BENCHMARK_RESULTS_DIR;
    # operator runs scripts/run_benchmark.py to produce them.
    benchmark_results_dir = os.environ.get(
        "POLARIS_BENCHMARK_RESULTS_DIR", ""
    ).strip()
    if benchmark_results_dir:
        from pathlib import Path as _Path

        _benchmark_root = _Path(benchmark_results_dir)

        def _inject_benchmark_root():
            return _benchmark_root

        app.dependency_overrides[slice005_get_results_root] = (
            _inject_benchmark_root
        )
    app.include_router(slice005_benchmark_router, prefix="/api")

    app.include_router(disambiguation_router, prefix="/api")

    # F-snowball — GET /api/runs/{run_id}/graph (I-snowball-002).
    app.include_router(graph_router, prefix="/api")

    return app


app = create_app()
