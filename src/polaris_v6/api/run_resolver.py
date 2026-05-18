"""Shared completed-run resolver for the v6 rich-surface read routes.

I-rdy-008 (#504) slice 8: `resolve_completed_artifact_dir` was first added
in slice 7a inside `inspector.py` (as `_resolve_completed_artifact_dir`).
The charts route (slice 8) needs the identical `run_store -> artifact_dir`
resolution, so it is extracted here as the single shared implementation —
behavior is unchanged: same status codes, same detail strings.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from polaris_v6.queue import run_store


def resolve_completed_artifact_dir(run_id: str) -> Path:
    """Resolve a completed run to its on-disk artifact_dir, or raise.

    The shared run-resolution for every completed-run read route (inspector
    slices 1 + 7a, charts slice 8):

    - unknown run -> 404
    - run not completed -> 409
    - abort_* / error_* run -> 422 (no AuditIR-loadable artifacts)
    - missing / absent artifact_dir -> 404
    """
    record = run_store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    if record.lifecycle_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id} is not completed "
                f"(lifecycle_status={record.lifecycle_status!r})"
            ),
        )

    status = record.pipeline_status or ""
    if status.startswith("abort_") or status.startswith("error_"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"run {run_id} produced no AuditIR-loadable artifacts "
                f"(pipeline_status={status!r}); it is a pipeline-verdict "
                f"artifact, not a renderable run"
            ),
        )

    if not record.artifact_dir:
        raise HTTPException(
            status_code=404,
            detail=f"run {run_id} has no artifact_dir recorded",
        )
    artifact_dir = Path(record.artifact_dir)
    if not artifact_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"artifact_dir does not exist on disk: {artifact_dir}",
        )
    return artifact_dir
