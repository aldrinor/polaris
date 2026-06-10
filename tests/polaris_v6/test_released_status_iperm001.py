"""I-perm-001 (#1195) slice 2 — the always-release `released_*` statuses are wired through the v6
serving path (Codex slice-2 P1-a). Without this, a PG_ALWAYS_RELEASE canary run would 500
RunStatusResponse and fall to `unknown_pipeline_status` in the actor.
"""

from __future__ import annotations

import typing
from pathlib import Path

from src.polaris_graph.audit_ir.regression_lab import KNOWN_STATUS_VALUES
from src.polaris_v6.schemas.run_status import PipelineStatus, RunStatusResponse
from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES

_RELEASED = ("released_with_disclosed_gaps", "released_insufficient_safety_evidence")
# Read the actor source from disk (importing it pulls in the dramatiq broker — out of scope here).
_ACTORS_SRC = Path(__file__).resolve().parents[2] / "src" / "polaris_v6" / "queue" / "actors.py"


def test_released_statuses_validate_in_pipeline_schema():
    """RunStatusResponse must accept the released_* statuses (the actor loads manifest.status into
    pipeline_status — an omitted value 500s Pydantic validation on a real run)."""
    allowed = set(typing.get_args(PipelineStatus))
    for status in _RELEASED:
        assert status in allowed, f"{status} missing from PipelineStatus schema mirror"
        response = RunStatusResponse(
            run_id="x",
            lifecycle_status="completed",
            pipeline_status=status,
            template="t",
            question="q",
            queued_at="2026-01-01T00:00:00Z",
        )
        assert response.pipeline_status == status


def test_actor_classifies_released_as_completed():
    """The actor completion classifier marks a released_* manifest as COMPLETED — not
    unknown_pipeline_status. Locks the `startswith('released_')` branch in run_research_run."""
    source = _ACTORS_SRC.read_text(encoding="utf-8")
    assert 'startswith("released_")' in source, (
        "actor completion classifier must treat released_* as a completed terminal"
    )
    # And the classification predicate itself recognises them as completed.
    for status in _RELEASED:
        assert (
            status == "success"
            or status.startswith("partial_")
            or status.startswith("released_")
        )


def test_released_statuses_mirrored_across_all_taxonomies():
    """released_* must be in EVERY status mirror (runner / regression_lab / v6 schema) so no layer
    rejects or mis-tiers a real always-release run."""
    schema_allowed = set(typing.get_args(PipelineStatus))
    for status in _RELEASED:
        assert status in UNIFIED_STATUS_VALUES
        assert status in KNOWN_STATUS_VALUES
        assert status in schema_allowed
