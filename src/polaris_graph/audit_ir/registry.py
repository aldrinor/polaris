"""Discover available V30 Phase-2 audit artifacts under outputs/.

The Evidence Inspector needs a small registry to list runs the user can
inspect. Phase A scope: scan known canonical demo paths. Phase C will
replace this with a per-workspace database-backed registry.
"""

from __future__ import annotations

import json
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


def _load_run_summary(artifact_dir: Path) -> RunSummary | None:
    """Read just manifest.json + protocol.json for the lightweight summary."""
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


def list_available_runs() -> list[RunSummary]:
    """Return every V30 Phase-2 audit artifact discoverable under outputs/.

    A directory is considered an artifact if it contains both manifest.json
    and report.md.
    """
    runs: list[RunSummary] = []
    if not OUTPUTS_DIR.exists():
        return runs

    for candidate in OUTPUTS_DIR.glob("**/manifest.json"):
        artifact_dir = candidate.parent
        if not (artifact_dir / "report.md").exists():
            continue
        summary = _load_run_summary(artifact_dir)
        if summary is not None:
            runs.append(summary)

    runs.sort(key=lambda r: (r.created_at_iso or "", r.slug), reverse=True)
    return runs


def find_run_by_slug(slug: str) -> RunSummary | None:
    """Find a run by its slug. Used by the inspector router for direct lookup."""
    if not slug:
        return None
    for run in list_available_runs():
        if run.slug == slug:
            return run
    return None
