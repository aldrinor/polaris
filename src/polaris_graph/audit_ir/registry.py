"""Discover available V30 Phase-2 audit artifacts.

Phase A scope discipline (per Codex M-2 review): the registry exposes
ONLY a curated allowlist of canonical artifacts that successfully load
through the strict AuditIR loader. The previous broad `outputs/**/manifest.json`
scan picked up 90 directories with 9 slug collisions and 75 of them
failed `load_audit_ir()`'s strict schema. Phase A returns exactly the
curated set; Phase B/C will replace this with a per-workspace database-
backed registry.

Each registered run is identified by both:
  - `run_id`: the canonical unique identifier (used for routing)
  - `slug`: a friendly slug derived from artifact_dir (URL-safe label)

`run_id` is the unique key. `slug` may collide if Phase B operators
load multiple runs with the same template; the registry detects this
at startup and raises.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUTS_DIR = REPO_ROOT / "outputs"

# Canonical Phase A demo: V30 Phase-2 run-14 (PHASE2_CHECKPOINT ship).
CANONICAL_DEMO_SLUG = "clinical_tirzepatide_t2dm"
CANONICAL_DEMO_DIR = (
    OUTPUTS_DIR
    / "full_scale_v30_phase2_run14"
    / "clinical"
    / "clinical_tirzepatide_t2dm"
)

# Phase A curated allowlist. Each entry is an absolute artifact directory.
# Phase B replaces this with a database-backed per-workspace registry.
_PHASE_A_ALLOWLIST: tuple[Path, ...] = (CANONICAL_DEMO_DIR,)


@dataclass(frozen=True)
class RunSummary:
    """Lightweight summary used by the run-list view (no full IR load)."""

    slug: str
    run_id: str
    domain: str
    status: str
    artifact_dir: Path
    cost_usd: float
    word_count: int
    contradictions_found: int
    release_allowed: bool
    created_at_iso: str | None


class RegistryError(RuntimeError):
    """Raised when the curated allowlist contains a malformed or duplicate run."""


def _load_run_summary(artifact_dir: Path) -> RunSummary | None:
    """Read just manifest.json + protocol.json for the lightweight summary.

    Returns None if the directory cannot be summarized — but for a curated
    allowlist this should never happen (and the caller raises).
    """
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    created_at = None
    protocol_path = artifact_dir / "protocol.json"
    if protocol_path.exists():
        try:
            with protocol_path.open("r", encoding="utf-8") as f:
                protocol = json.load(f)
            created_at = protocol.get("created_at_iso")
        except (OSError, json.JSONDecodeError):
            created_at = None

    generator = manifest.get("generator", {}) or {}
    slug = str(manifest.get("slug") or artifact_dir.name)
    domain = artifact_dir.parent.name if artifact_dir.parent != OUTPUTS_DIR else ""
    return RunSummary(
        slug=slug,
        run_id=str(manifest.get("run_id", "")),
        domain=domain,
        status=str(manifest.get("status", "")),
        artifact_dir=artifact_dir,
        cost_usd=float(manifest.get("cost_usd", 0.0)),
        word_count=int(generator.get("words", 0)),
        contradictions_found=int(manifest.get("contradictions_found", 0)),
        release_allowed=bool(manifest.get("release_allowed", False)),
        created_at_iso=created_at,
    )


def _validate_loadable(artifact_dir: Path) -> None:
    """Verify the artifact loads through the strict AuditIR loader.

    Raises RegistryError if loading fails. Done at registry init time
    so the inspector router never lists a run it can't actually serve.
    Imported lazily to avoid a circular import with loader.py.
    """
    from src.polaris_graph.audit_ir.loader import (
        AuditIRSchemaError,
        load_audit_ir,
    )
    try:
        load_audit_ir(artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError, NotADirectoryError) as exc:
        raise RegistryError(
            f"Allowlisted artifact failed strict load: {artifact_dir}: {exc}"
        ) from exc


def _build_runs() -> tuple[RunSummary, ...]:
    """Build the registry by validating each allowlisted artifact."""
    summaries: list[RunSummary] = []
    seen_slugs: dict[str, str] = {}
    seen_run_ids: set[str] = set()

    for artifact_dir in _PHASE_A_ALLOWLIST:
        if not artifact_dir.is_dir():
            raise RegistryError(
                f"Allowlisted artifact directory missing: {artifact_dir}"
            )
        _validate_loadable(artifact_dir)
        summary = _load_run_summary(artifact_dir)
        if summary is None:
            raise RegistryError(
                f"Allowlisted artifact failed lightweight summary: {artifact_dir}"
            )
        if summary.run_id in seen_run_ids:
            raise RegistryError(
                f"Duplicate run_id in allowlist: {summary.run_id}"
            )
        if summary.slug in seen_slugs and seen_slugs[summary.slug] != summary.run_id:
            raise RegistryError(
                f"Duplicate slug across distinct run_ids: {summary.slug} "
                f"({seen_slugs[summary.slug]} vs {summary.run_id})"
            )
        seen_slugs[summary.slug] = summary.run_id
        seen_run_ids.add(summary.run_id)
        summaries.append(summary)

    summaries.sort(key=lambda r: (r.created_at_iso or "", r.slug), reverse=True)
    return tuple(summaries)


# Built lazily on first access (not at import). Rationale: an eager module-level
# build raised at IMPORT time whenever the curated allowlist artifacts were absent
# (e.g. a clean checkout / CI), which broke test collection for every module that
# merely imports this one. Deferring to first use keeps the fail-loud guarantee —
# the inspector route still raises when actually used with a malformed allowlist —
# without coupling importability to the presence of run artifacts.
#
# Semantics match the original eager build EXACTLY except for timing:
#   - built exactly ONCE (double-checked lock; concurrent first callers cannot
#     run _build_runs() more than once),
#   - fail ONCE and stay failed (a failed build is cached and re-raised on every
#     later call — the original import-time failure was likewise permanent; we do
#     NOT retry),
#   - thread-safe.
# The one intended change is *when* validation fires: at first registry access
# rather than at import (that deferral is the entire point of this fix).
_RUNS_CACHE: tuple[RunSummary, ...] | None = None
_RUNS_ERROR: Exception | None = None
_RUNS_BUILT: bool = False
_RUNS_LOCK = threading.Lock()


def _runs() -> tuple[RunSummary, ...]:
    """Return the validated registry, building (and caching) it once on first access."""
    global _RUNS_CACHE, _RUNS_ERROR, _RUNS_BUILT
    if not _RUNS_BUILT:
        with _RUNS_LOCK:
            if not _RUNS_BUILT:
                try:
                    _RUNS_CACHE = _build_runs()
                except BaseException as exc:  # noqa: BLE001 — cache & re-raise; never leave a half-built None state
                    _RUNS_ERROR = exc
                    _RUNS_BUILT = True
                    raise
                _RUNS_BUILT = True  # only marked built AFTER success (or a cached failure above)
    if _RUNS_ERROR is not None:
        raise _RUNS_ERROR
    return _RUNS_CACHE  # type: ignore[return-value]


def list_available_runs() -> list[RunSummary]:
    """Return every Phase-A-allowlisted V30 audit artifact (already validated)."""
    return list(_runs())


def find_run_by_slug(slug: str) -> RunSummary | None:
    """Find a run by slug. Slugs are guaranteed unique within the registry."""
    runs = _runs()  # always initialize (validate) first — even for a falsy slug
    if not slug:
        return None
    for run in runs:
        if run.slug == slug:
            return run
    return None


def find_run_by_id(run_id: str) -> RunSummary | None:
    """Find a run by its canonical unique run_id."""
    runs = _runs()  # always initialize (validate) first — even for a falsy id
    if not run_id:
        return None
    for run in runs:
        if run.run_id == run_id:
            return run
    return None
