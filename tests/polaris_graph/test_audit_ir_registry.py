"""Tests for src/polaris_graph/audit_ir/registry.py — run discovery.

Codex M-2 review (PARTIAL → fixed): Phase A registry is now a curated
allowlist that validates each artifact loads through the strict AuditIR
loader at startup time. The previous broad outputs/** scan is gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir import load_audit_ir
from src.polaris_graph.audit_ir.registry import (
    CANONICAL_DEMO_DIR,
    CANONICAL_DEMO_SLUG,
    OUTPUTS_DIR,
    RegistryError,
    RunSummary,
    find_run_by_id,
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


# ---------------------------------------------------------------------------
# Codex M-2 review fixes (high #1, #2): list/detail contract + uniqueness
# ---------------------------------------------------------------------------


def test_listed_slugs_are_unique() -> None:
    """Every listed run must have a unique slug — otherwise routes collide."""
    runs = list_available_runs()
    slugs = [r.slug for r in runs]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs in registry: {slugs}"


def test_listed_run_ids_are_unique() -> None:
    """Every listed run must have a unique run_id."""
    runs = list_available_runs()
    run_ids = [r.run_id for r in runs]
    assert len(run_ids) == len(set(run_ids))


def test_every_listed_run_loads_through_strict_loader() -> None:
    """Codex M-2 high #1: list/detail contract — every listed run must load.

    Before fix: list returned 90 runs, 75 of them failed strict load.
    """
    for run in list_available_runs():
        # Should not raise
        ir = load_audit_ir(run.artifact_dir)
        assert ir.run_id == run.run_id


def test_find_run_by_id_returns_canonical() -> None:
    runs = list_available_runs()
    assert runs
    canonical_run_id = next(r.run_id for r in runs if r.slug == CANONICAL_DEMO_SLUG)
    summary = find_run_by_id(canonical_run_id)
    assert summary is not None
    assert summary.run_id == canonical_run_id


def test_find_run_by_id_unknown_returns_none() -> None:
    assert find_run_by_id("does_not_exist") is None
    assert find_run_by_id("") is None


def test_phase_a_registry_returns_only_canonical_demo() -> None:
    """Phase A scope discipline: registry returns the curated allowlist only."""
    runs = list_available_runs()
    # Phase A allowlist is exactly one entry — the canonical demo
    assert len(runs) == 1
    assert runs[0].slug == CANONICAL_DEMO_SLUG
