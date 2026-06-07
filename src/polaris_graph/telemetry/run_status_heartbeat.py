"""Live run-status heartbeat (I-obs-001 #1141 AC1) — a single tailable JSON file.

PURELY ADDITIVE observability. This module writes a per-run heartbeat that a human can
``tail`` to see which query/stage a Gate-B run is on, the running cost, and coarse
progress — refreshed at every stage transition and on every terminal/abort path of
``run_one_query``. It NEVER raises into the caller: a heartbeat IO error must not be able
to convert a success/abort into an error or perturb a verdict (faithfulness invariants —
strict_verify / 4-role D8 / provenance / two-family — are untouched by anything here).

Stdlib-only, and a sibling of ``tool_tracer.py`` under ``src/`` (NOT ``scripts/``) so
``sweep_integration`` and other ``src`` modules may reference its constants without
importing ``scripts`` (LAW VII).

Kill-switch: ``PG_RUN_STATUS_HEARTBEAT`` (default ON; OFF iff value in
{0,false,no,off}). When OFF, ``write_heartbeat`` returns at its first line and no file is
written — the only added cost is one env read on the hot path, so faithfulness artifacts
are byte-identical.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

RUN_STATUS_FILENAME = "run_status.json"
HEARTBEAT_ENABLED_ENV = "PG_RUN_STATUS_HEARTBEAT"
RUN_STATUS_PATH_ENV = "PG_RUN_STATUS_PATH"
_DEFAULT_MIRROR_PATH = "state/run_status.json"
_DISABLED_VALUES = {"0", "false", "no", "off"}


def heartbeat_enabled() -> bool:
    """True unless ``PG_RUN_STATUS_HEARTBEAT`` is set to a disable value (default ON)."""
    return os.environ.get(HEARTBEAT_ENABLED_ENV, "").strip().lower() not in _DISABLED_VALUES


def heartbeat_paths(run_dir: Path | str) -> list[Path]:
    """The two heartbeat targets: the per-run file + the stable cross-query mirror.

    The mirror lets a human tail ONE file across all 5 sequential Gate-B queries; its
    location is env-overridable via ``PG_RUN_STATUS_PATH`` (LAW VI).
    """
    return [
        Path(run_dir) / RUN_STATUS_FILENAME,
        Path(os.environ.get(RUN_STATUS_PATH_ENV, _DEFAULT_MIRROR_PATH)),
    ]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as JSON to ``path`` atomically (temp + ``os.replace``).

    A UNIQUE temp name (pid + thread-ident + uuid) is REQUIRED: the parent coroutine AND
    the seam worker thread both write concurrently, and a fixed temp name would let one
    writer clobber the other's temp. ``os.replace`` is atomic on POSIX and on Windows
    (same filesystem), so a tailer always reads a complete object. Best-effort: any
    exception is swallowed after cleaning up the temp.
    """
    import json

    tmp = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — heartbeat IO must never raise into the run
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def write_heartbeat(
    *,
    run_dir: Path | str,
    run_id: str,
    slug: str,
    query_index: int | None,
    query_total: int | None,
    stage: str,
    started_monotonic: float,
    running_cost_usd: float | None,
    budget_cap_usd: float | None,
    sources_kept: int | None = None,
    sections_done: int | None = None,
    sections_total: int | None = None,
    claims_verified: int | None = None,
    claims_total: int | None = None,
) -> None:
    """Write the run-status heartbeat to both targets (best-effort, never raises).

    ``elapsed_s`` is derived from ``started_monotonic`` (a dedicated entry timestamp the
    caller captures at ``run_one_query`` entry — NOT the late-set ``t0``). The whole body
    is guarded so a heartbeat failure can never change the run outcome.
    """
    if not heartbeat_enabled():
        return
    try:
        import time

        payload: dict[str, Any] = {
            "run_id": run_id,
            "slug": slug,
            "query_index": query_index,
            "query_total": query_total,
            "stage": stage,
            "elapsed_s": round(time.monotonic() - started_monotonic, 1),
            "running_cost_usd": running_cost_usd,
            "budget_cap_usd": budget_cap_usd,
            "sources_kept": sources_kept,
            "sections_done": sections_done,
            "sections_total": sections_total,
            "claims_verified": claims_verified,
            "claims_total": claims_total,
            "last_update_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        for target in heartbeat_paths(run_dir):
            _atomic_write_json(target, payload)
    except Exception:  # noqa: BLE001 — observability must never perturb the run
        _LOG.debug("run-status heartbeat write failed (stage=%s)", stage, exc_info=True)
