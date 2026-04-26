"""Tests for src/polaris_graph/audit_ir/registry.py — run discovery."""

from __future__ import annotations

from pathlib import Path

from src.polaris_graph.audit_ir.registry import (
    CANONICAL_DEMO_DIR,
    CANONICAL_DEMO_SLUG,
    OUTPUTS_DIR,
    RunSummary,
    find_run_by_slug,
    list_available_runs,
)


def test_canonical_demo_path_exists() -> None:
    """Phase A canonical demo (V30 run-14) must be discoverable."""
    assert CANONICAL_DEMO_DIR.is_dir()
    assert (CANONICAL_DEMO_DIR / "manifest.json").exists()
    assert (CANONICAL_DEMO_DIR / "report.md").exists()


def test_outputs_dir_resolves() -> None:
    assert OUTPUTS_DIR.exists()
    assert OUTPUTS_DIR.is_dir()


def test_list_available_runs_includes_canonical_demo() -> None:
    runs = list_available_runs()
    slugs = [r.slug for r in runs]
    assert CANONICAL_DEMO_SLUG in slugs


def test_run_summary_canonical_fields() -> None:
    runs = list_available_runs()
    canonical = next(r for r in runs if r.slug == CANONICAL_DEMO_SLUG)
    assert isinstance(canonical, RunSummary)
    assert canonical.run_id == "SWEEP_clinical_clinical_tirzepatide_t2dm_1777170058"
    assert canonical.contradictions_found == 14
    assert canonical.cost_usd > 0.0
    assert canonical.word_count > 0
    assert canonical.created_at_iso is not None
    assert canonical.release_allowed is True


def test_find_run_by_slug_returns_canonical() -> None:
    summary = find_run_by_slug(CANONICAL_DEMO_SLUG)
    assert summary is not None
    assert summary.slug == CANONICAL_DEMO_SLUG


def test_find_run_by_slug_unknown_returns_none() -> None:
    assert find_run_by_slug("does_not_exist") is None
    assert find_run_by_slug("") is None


def test_run_summaries_sorted_newest_first() -> None:
    runs = list_available_runs()
    if len(runs) >= 2:
        # Sort key is created_at_iso descending, then slug
        for a, b in zip(runs, runs[1:]):
            assert (a.created_at_iso or "") >= (b.created_at_iso or "")
