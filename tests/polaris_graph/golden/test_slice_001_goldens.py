"""Slice 001 golden-test integration runner.

Runs each test_*.json fixture from polaris-controls/golden/slice_001/
through the backend pipeline (api/intake/process_intake) and verifies
the resulting ScopeDecision matches the expected fields.

This IS the slice's fitness function. When all golden tests pass, the
slice's acceptance criteria per polaris-controls/slices/slice_001_*.md
are met (modulo the frontend, which is PR 7 — deferred to a future
focused session).

The golden test files MUST live in `<polaris-controls-checkout>/golden/
slice_001/test_*.json`. We resolve the path via env var
POLARIS_CONTROLS_PATH (preferred). Default discovery (PR-B2 2026-05-05):
nested under POLARIS at `<POLARIS>/polaris-controls/` (canonical post-
relocation), then sibling `<POLARIS>/../polaris-controls/` (pre-PR-B2
fallback for fresh-clone-elsewhere checkouts), then `~/polaris-controls/`.
CI and local dev both resolve through this chain.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from polaris_graph.api.intake import process_intake
from polaris_graph.scope.scope_decision import ScopeDecision


# ---------------------------------------------------------------------------
# Test discovery
# ---------------------------------------------------------------------------

_POLARIS_ROOT = Path(__file__).resolve().parents[3]


def _find_polaris_controls_dir() -> Path | None:
    """Locate the polaris-controls checkout; return None if unavailable."""
    # 1. Explicit env var
    env_path = os.environ.get("POLARIS_CONTROLS_PATH")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if (candidate / "golden" / "slice_001").is_dir():
            return candidate

    # 2. Nested under POLARIS root (PR-B2 canonical layout 2026-05-05)
    nested = _POLARIS_ROOT / "polaris-controls"
    if (nested / "golden" / "slice_001").is_dir():
        return nested

    # 3. Sibling directory (pre-PR-B2 layout, retained for fresh-clone fallback)
    sibling = _POLARIS_ROOT.parent / "polaris-controls"
    if (sibling / "golden" / "slice_001").is_dir():
        return sibling

    # 4. Common alternative locations
    for guess in [
        Path.home() / "polaris-controls",
    ]:
        if (guess / "golden" / "slice_001").is_dir():
            return guess

    return None


def _golden_test_files() -> list[Path]:
    pc_dir = _find_polaris_controls_dir()
    if pc_dir is None:
        return []
    golden_dir = pc_dir / "golden" / "slice_001"
    return sorted(golden_dir.glob("test_*.json"))


# ---------------------------------------------------------------------------
# Discovery report (fail-loud if no goldens found)
# ---------------------------------------------------------------------------

def test_polaris_controls_directory_resolvable():
    """First-line diagnostic: if this fails, every other test is skipped."""
    pc_dir = _find_polaris_controls_dir()
    if pc_dir is None:
        pytest.skip(
            "polaris-controls checkout not found. Either set POLARIS_CONTROLS_PATH "
            "env var, OR clone polaris-controls as nested under POLARIS at "
            "<POLARIS>/polaris-controls/ (PR-B2 canonical post-2026-05-05), "
            "OR clone as sibling at <POLARIS>/../polaris-controls/ (pre-PR-B2 "
            "fallback)."
        )
    assert (pc_dir / "golden" / "slice_001").is_dir()


def test_at_least_5_golden_test_files_exist():
    files = _golden_test_files()
    if not files:
        pytest.skip("polaris-controls checkout not found")
    assert len(files) >= 5, f"expected at least 5 golden tests, found {len(files)}"


# ---------------------------------------------------------------------------
# Per-golden execution
# ---------------------------------------------------------------------------

def _golden_id(path: Path) -> str:
    return path.stem  # e.g., "test_001_in_scope_well_formed"


@pytest.mark.parametrize(
    "golden_path",
    _golden_test_files() or [pytest.param(None, marks=pytest.mark.skip(
        reason="polaris-controls golden tests not available"
    ))],
    ids=lambda p: _golden_id(p) if p else "skipped",
)
def test_golden_passes_through_intake(golden_path: Path | None):
    if golden_path is None:
        pytest.skip("no golden tests")

    with golden_path.open("r", encoding="utf-8") as f:
        spec = json.load(f)

    question = spec["question"]
    expected = spec["expected_scope_decision"]
    max_latency_ms = spec.get("max_latency_ms", 3000)

    # Run pipeline (no LLM needed — all 5 goldens are regex-decidable;
    # if any reach LLM fallback, we'd inject a deterministic mock here)
    result = process_intake(question)

    assert isinstance(result, ScopeDecision), \
        f"{golden_path.name}: expected ScopeDecision, got IntakeError or other"

    # Status match (the most important field)
    assert result.status == expected["status"], (
        f"{golden_path.name}: status mismatch — "
        f"got {result.status!r}, expected {expected['status']!r}"
    )

    # scope_class match (None vs str)
    expected_class = expected.get("scope_class")
    if expected_class is None:
        assert result.scope_class is None, (
            f"{golden_path.name}: expected scope_class=None, got {result.scope_class!r}"
        )
    else:
        assert result.scope_class == expected_class, (
            f"{golden_path.name}: scope_class mismatch — "
            f"got {result.scope_class!r}, expected {expected_class!r}"
        )

    # Ambiguity axes count match (when applicable)
    expected_axes = expected.get("ambiguity_axes", [])
    assert len(result.ambiguity_axes) == len(expected_axes), (
        f"{golden_path.name}: ambiguity_axes count mismatch — "
        f"got {len(result.ambiguity_axes)}, expected {len(expected_axes)}"
    )

    # Per-axis needs_clarification match (the binary signal)
    for actual_axis, expected_axis in zip(result.ambiguity_axes, expected_axes):
        assert actual_axis.axis == expected_axis["axis"], (
            f"{golden_path.name}: axis label mismatch "
            f"({actual_axis.axis!r} != {expected_axis['axis']!r})"
        )
        assert actual_axis.needs_clarification == expected_axis["needs_clarification"], (
            f"{golden_path.name}: {actual_axis.axis} "
            f"needs_clarification mismatch — "
            f"got {actual_axis.needs_clarification}, "
            f"expected {expected_axis['needs_clarification']}"
        )

    # Latency under budget
    assert result.latency_ms <= max_latency_ms, (
        f"{golden_path.name}: latency {result.latency_ms}ms exceeds "
        f"budget {max_latency_ms}ms"
    )


# ---------------------------------------------------------------------------
# Aggregate health check
# ---------------------------------------------------------------------------

def test_all_5_goldens_pass_summary():
    """Single aggregate test that PASSES iff all 5 goldens pass.

    Useful for CI / dashboards that report a single number.
    """
    files = _golden_test_files()
    if not files:
        pytest.skip("polaris-controls golden tests not available")

    failures: list[str] = []
    for path in files:
        with path.open("r", encoding="utf-8") as f:
            spec = json.load(f)
        result = process_intake(spec["question"])
        if not isinstance(result, ScopeDecision):
            failures.append(f"{path.name}: not a ScopeDecision")
            continue
        if result.status != spec["expected_scope_decision"]["status"]:
            failures.append(
                f"{path.name}: status {result.status} != "
                f"{spec['expected_scope_decision']['status']}"
            )

    assert not failures, "Golden test failures:\n  " + "\n  ".join(failures)
