"""Pin replay route — I-cd-017 (#627).

GET /runs/{run_id}/pins → list of PinSnapshot synthesized from all
completed runs sharing the same query_slug (chronological by finished_at).

GET /runs/{run_id}/pins/{date} → single PinSnapshot for the exact
(run_id, finished_at[:10]) pair.

Synthesis sources (iter-2 P1 fixes):
- Pipeline status: `RunStatusResponse.pipeline_status` from run_store
  (NOT raw manifest field — actors.py:219 translates `manifest.status` →
  `pipeline_status`).
- Quality fields: `manifest.json` `generator` block. Handles BOTH shape
  variants:
    * success path → `sections_kept`, `sentences_dropped`,
      `outline_sections`, `sentences_verified`.
    * abort_no_verified_sections path → `sections_total`,
      `sections_dropped`, `sentences_verified` (NO `sections_kept`, NO
      `sentences_dropped` — confirmed at
      scripts/run_honest_sweep_r3.py:2468-2473).

Auth: protected via app-level `dependencies=[Depends(_require_auth)]`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException

from polaris_v6.queue import run_store
from polaris_v6.schemas.pin_snapshot import PinSnapshot
from polaris_v6.schemas.run_status import RunStatusResponse

router = APIRouter(prefix="/runs", tags=["pins"])

_QUALIFYING_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "success",
        "partial_outline_fallback",
        # Codex diff iter-2 P1: partial_qwen_advisory is a real terminal
        # PipelineStatus (run_status.py) — pipeline-A maps ok_qwen_advisory
        # to it (scripts/run_honest_sweep_r3.py:198), and the actor stores
        # the run as completed. Excluding it would 404 a real completed run.
        "partial_qwen_advisory",
        "partial_evaluator_advisory",
        "partial_thin_corpus",
        "partial_incomplete_corpus",
        "partial_rule_check_warnings",
        "abort_no_verified_sections",
    }
)


def _collapsed_verdict(pipeline_status: str) -> str:
    if pipeline_status == "abort_no_verified_sections":
        return "abort_no_verified_sections"
    return "success"


def _synthesize_pin_from_manifest(
    run: RunStatusResponse,
    manifest: dict,
) -> PinSnapshot:
    """Build a PinSnapshot from a completed-run RunStatusResponse + manifest.

    Defensive against the two generator-block shape variants (iter-2 P1.2):
    success-path manifests carry `sections_kept` + `sentences_dropped`;
    abort_no_verified_sections manifests carry `sections_total` +
    `sections_dropped` and lack `sentences_dropped`.
    """
    generator = manifest.get("generator") or {}
    sections_kept = generator.get("sections_kept")
    sections_dropped_in_generator = generator.get("sections_dropped")
    sections_total = generator.get("sections_total")
    outline_len = len(generator.get("outline_sections") or [])

    if sections_kept is None and sections_total is not None:
        sections_kept = max(0, sections_total - (sections_dropped_in_generator or 0))
    if sections_kept is None:
        sections_kept = 0

    if sections_dropped_in_generator is not None:
        section_count_dropped = sections_dropped_in_generator
    elif outline_len > 0:
        section_count_dropped = max(0, outline_len - sections_kept)
    else:
        section_count_dropped = 0

    verified = max(0, int(generator.get("sentences_verified") or 0))
    dropped_sentences = max(0, int(generator.get("sentences_dropped") or 0))
    denominator = verified + dropped_sentences
    pass_rate = verified / denominator if denominator > 0 else 0.0
    pass_rate = min(1.0, max(0.0, pass_rate))

    finished_at = run.finished_at or ""
    pin_date = finished_at[:10] if finished_at else "1970-01-01"

    return PinSnapshot(
        run_id=run.run_id,
        pin_date=pin_date,
        query=run.question,
        verdict=_collapsed_verdict(run.pipeline_status or "error_unexpected"),
        section_count_kept=max(0, sections_kept),
        section_count_dropped=max(0, section_count_dropped),
        verified_sentence_count=verified,
        pass_rate=pass_rate,
        retracted_source_ids=None,
    )


def _load_manifest(artifact_dir: str | None) -> dict | None:
    if not artifact_dir:
        return None
    path = Path(artifact_dir) / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _qualifies(run: RunStatusResponse) -> bool:
    if run.lifecycle_status != "completed":
        return False
    pipeline_status = run.pipeline_status or ""
    return pipeline_status in _QUALIFYING_STATUSES


@router.get("/{run_id}/pins", response_model=list[PinSnapshot])
def list_pins(run_id: str) -> list[PinSnapshot]:
    anchor = run_store.get_run(run_id)
    if anchor is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found.")
    query_slug = anchor.query_slug
    if not query_slug:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id!r} has no query_slug (run not yet completed by pipeline).",
        )
    siblings = run_store.list_completed_runs_by_query_slug(query_slug)
    snapshots: list[PinSnapshot] = []
    for run in siblings:
        if not _qualifies(run):
            continue
        manifest = _load_manifest(run.artifact_dir)
        if manifest is None:
            continue
        snapshots.append(_synthesize_pin_from_manifest(run, manifest))
    return snapshots


@router.get("/{run_id}/pins/{date}", response_model=PinSnapshot)
def get_pin_by_date(
    run_id: str,
    date: str,
) -> PinSnapshot:
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    run = run_store.get_run(run_id)
    if run is None or not _qualifies(run):
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not pin-eligible.")
    finished_at = run.finished_at or ""
    if finished_at[:10] != date:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id!r} finished on {finished_at[:10]!r}, not {date!r}.",
        )
    manifest = _load_manifest(run.artifact_dir)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest missing for run {run_id!r}.")
    return _synthesize_pin_from_manifest(run, manifest)
