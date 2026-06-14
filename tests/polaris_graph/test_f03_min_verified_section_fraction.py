"""F03 (A3) regression: the success gate must abort a MOSTLY-gap-stubbed report,
not just a totally-empty one.

Pre-fix: ``run_one_query`` aborted (``abort_no_verified_sections``) only when ZERO
sections survived strict_verify. A report where N-2 of N sections are gap stubs
(only a couple verify) shipped as ``ok``/``success`` — a mostly-gap clinical
report going GREEN.

Post-fix: ``PG_MIN_VERIFIED_SECTION_FRACTION`` (float, default 0.0 = inert) adds a
verified-section-fraction floor. Below it, the run aborts with the NON-``partial``
status ``abort_excessive_gap`` and a verdict report body. The policy lives in the
pure helpers ``min_verified_section_fraction`` / ``is_excessive_gap`` /
``build_excessive_gap_abort_body`` so it is unit-testable without the async
orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class _FakeSection:
    title: str
    verified_text: str
    dropped_due_to_failure: bool
    sentences_verified: int = 0
    sentences_dropped: int = 0
    regen_attempted: bool = False
    is_gap_stub: bool = False
    error: str | None = None


# ── pure predicate: is_excessive_gap ─────────────────────────────────────────

def test_is_excessive_gap_inert_when_floor_explicitly_zero() -> None:
    """An EXPLICIT 0.0 floor ⇒ never fires (only reachable via deliberate operator
    override, no longer the default)."""
    from scripts.run_honest_sweep_r3 import is_excessive_gap
    assert is_excessive_gap(verified_count=1, total_sections=8, min_fraction=0.0) is False


def test_is_excessive_gap_fires_below_floor() -> None:
    """N-2 of N gap-stubbed (2 of 8 verify = 25%) is below a 0.5 floor ⇒ excessive."""
    from scripts.run_honest_sweep_r3 import is_excessive_gap
    assert is_excessive_gap(verified_count=2, total_sections=8, min_fraction=0.5) is True


def test_is_excessive_gap_passes_at_or_above_floor() -> None:
    from scripts.run_honest_sweep_r3 import is_excessive_gap
    # exactly at floor is NOT excessive (>= floor passes)
    assert is_excessive_gap(verified_count=4, total_sections=8, min_fraction=0.5) is False
    assert is_excessive_gap(verified_count=6, total_sections=8, min_fraction=0.5) is False


def test_is_excessive_gap_no_sections_is_safe() -> None:
    from scripts.run_honest_sweep_r3 import is_excessive_gap
    assert is_excessive_gap(verified_count=0, total_sections=0, min_fraction=0.5) is False


# ── env reader: min_verified_section_fraction ────────────────────────────────

def test_min_verified_section_fraction_default_is_strict(monkeypatch) -> None:
    """Codex P0: unset MUST enforce the strict floor (0.5), NOT 0.0 (fail-open)."""
    from scripts.run_honest_sweep_r3 import (
        DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
        min_verified_section_fraction,
    )
    monkeypatch.delenv("PG_MIN_VERIFIED_SECTION_FRACTION", raising=False)
    assert min_verified_section_fraction() == DEFAULT_MIN_VERIFIED_SECTION_FRACTION
    assert DEFAULT_MIN_VERIFIED_SECTION_FRACTION == 0.5


def test_min_verified_section_fraction_blank_is_strict(monkeypatch) -> None:
    """An empty/whitespace value is treated as unset ⇒ strict default, never 0.0."""
    from scripts.run_honest_sweep_r3 import (
        DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
        min_verified_section_fraction,
    )
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "   ")
    assert min_verified_section_fraction() == DEFAULT_MIN_VERIFIED_SECTION_FRACTION


def test_strict_default_aborts_mostly_gap_report(monkeypatch) -> None:
    """End-to-end policy with NO env opt-in: the strict default flags a 1-of-3
    gap-stubbed report (33% < 50%) as excessive gap (Codex P0 + P2 behavioral proof)."""
    from scripts.run_honest_sweep_r3 import (
        is_excessive_gap,
        min_verified_section_fraction,
    )
    monkeypatch.delenv("PG_MIN_VERIFIED_SECTION_FRACTION", raising=False)
    floor = min_verified_section_fraction()
    assert is_excessive_gap(verified_count=1, total_sections=3, min_fraction=floor) is True
    assert is_excessive_gap(verified_count=2, total_sections=3, min_fraction=floor) is False


def test_min_verified_section_fraction_reads_env(monkeypatch) -> None:
    from scripts.run_honest_sweep_r3 import min_verified_section_fraction
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0.7")
    assert min_verified_section_fraction() == pytest.approx(0.7)


def test_min_verified_section_fraction_clamps_and_falls_back(monkeypatch) -> None:
    from scripts.run_honest_sweep_r3 import (
        DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
        min_verified_section_fraction,
    )
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "1.5")
    assert min_verified_section_fraction() == 1.0
    # An EXPLICIT negative is the deliberate operator disable → 0.0.
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "-0.2")
    assert min_verified_section_fraction() == 0.0
    # Garbage is NOT a disable — it falls back to the STRICT default (never fail-open).
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "garbage")
    assert min_verified_section_fraction() == DEFAULT_MIN_VERIFIED_SECTION_FRACTION


# ── verdict body builder ─────────────────────────────────────────────────────

def test_excessive_gap_body_is_verdict_not_content() -> None:
    from scripts.run_honest_sweep_r3 import build_excessive_gap_abort_body
    sections = [
        _FakeSection("Efficacy", "## Efficacy\n\nReal.", False, sentences_verified=4),
        _FakeSection("Safety", "(gap)", False, sentences_verified=0, is_gap_stub=True),
        _FakeSection("Contraindications", "(gap)", False, sentences_verified=0,
                     is_gap_stub=True),
        _FakeSection("Dosing", "(gap)", False, sentences_verified=0, is_gap_stub=True),
    ]
    body = build_excessive_gap_abort_body(
        "What is the efficacy and safety of drug X?", sections,
        verified_count=1, min_fraction=0.5,
    )
    assert "Pipeline verdict" in body
    assert "below the required floor" in body
    # Per-section verdict surfaces the gap-stub flag so an operator can triage.
    assert "Contraindications" in body
    assert "gap_stub=True" in body
    # Must NOT look like a complete findings report.
    assert "## Methods" not in body
    assert "## Bibliography" not in body


# ── status registration (couples to the manifest contract) ───────────────────

def test_abort_excessive_gap_is_registered_status() -> None:
    from scripts.run_honest_sweep_r3 import (
        UNIFIED_STATUS_VALUES,
        to_unified_status,
    )
    assert "abort_excessive_gap" in UNIFIED_STATUS_VALUES
    # maps to itself (already an abort_ unified name), not error_unexpected
    assert to_unified_status("abort_excessive_gap") == "abort_excessive_gap"


def test_abort_excessive_gap_is_not_a_partial() -> None:
    """Critical for F03 part 2: the status must NOT start with 'partial' or Gate-B
    would treat the mostly-gap report as a PASS (rc=0)."""
    assert not "abort_excessive_gap".startswith("partial")


# ── source-anchor: the floor is wired into the orchestrator branch ───────────

def test_orchestrator_wires_the_floor() -> None:
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    src = inspect.getsource(sweep.run_one_query)
    assert "min_verified_section_fraction()" in src
    assert "is_excessive_gap(" in src
    assert 'summary["status"] = _abort_status' in src
    assert "abort_excessive_gap" in src
