"""Shared run_store + AuditIR-artifact_dir fixtures for tests/v6 route tests.

I-rdy-008 (#504) slice 8 (Codex brief iter-2 P2 6.5): the seeded-run_store +
`load_audit_ir()`-loadable artifact_dir helpers are factored here so the
charts route tests build live completed runs without a brittle
cross-test-module import. `write_audit_ir_artifact_dir` writes exactly the
5 files `polaris_graph.audit_ir.loader.load_audit_ir()` requires; callers
pass real `bibliography` / `contradictions` / `sections` rows to exercise
the chart derivations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from polaris_v6.queue import run_store

QUESTION = "What does the latest evidence show on this topic?"


def write_audit_ir_artifact_dir(
    d: Path,
    *,
    bibliography: list[dict[str, Any]] | None = None,
    contradictions: list[dict[str, Any]] | None = None,
    sections: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a complete `load_audit_ir()`-loadable artifact_dir under ``d``.

    ``bibliography`` / ``contradictions`` / ``sections`` default to empty;
    pass real rows to exercise the chart derivations. ``sections`` are
    written verbatim into ``verification_details.json["sections"]`` — each
    is ``{"title", "kept": [...], "dropped": [...], "total_in"?: int}``.
    """
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "manifest_run_1",
                "slug": "charts_test_slug",
                "status": "success",
                "question": QUESTION,
                "protocol_sha256": "0" * 64,
                "completeness": {"covered_fraction": 1.0},
                "evaluator_gate": {
                    "gate_class": "release",
                    "release_allowed": True,
                },
                "corpus": {"count": 1, "tier_fractions": {"T1": 1.0}},
                "frame_coverage_report": {"entries": [], "by_status": {}},
            }
        ),
        encoding="utf-8",
    )
    (d / "report.md").write_text(
        "# Research report\n\nMinimal.\n", encoding="utf-8"
    )
    (d / "bibliography.json").write_text(
        json.dumps(bibliography or []), encoding="utf-8"
    )
    (d / "contradictions.json").write_text(
        json.dumps(contradictions or []), encoding="utf-8"
    )
    (d / "verification_details.json").write_text(
        json.dumps({"sections": sections or [], "totals": {}}),
        encoding="utf-8",
    )
    return d


def seed_completed_run(run_id: str, artifact_dir: Path) -> None:
    """Seed run_store with a completed run pointing at ``artifact_dir``."""
    run_store.insert_run(run_id, "clinical", QUESTION)
    run_store.set_pipeline_meta(run_id, artifact_dir=str(artifact_dir))
    run_store.mark_completed(run_id, {}, pipeline_status="success")
