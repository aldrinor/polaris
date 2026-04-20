"""
BUG-M-203 regression tests: outline validation + deterministic fallback.

Pre-fix, `_parse_outline()` silently accepted 1-6 sections (even though
the prompt required 3-5), accepted duplicate titles, accepted
overlapping ev_ids across sections, and accepted unknown ev_ids. On
fully-invalid planner output, the generator collapsed to a single
generic "Efficacy" section with no signal to downstream.

Post-fix (deep-dive R4): `_parse_outline()` returns an
`OutlineParseResult` with reason codes. `_call_outline()` retries once
with a tighter prompt. If retry fails, a deterministic 3-section
fallback is built from the evidence pool and
`outline_fallback_used=True` is propagated to `MultiSectionResult` +
the manifest emits `status=partial_outline_fallback`.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    OutlineParseResult,
    _ALLOWED_SECTIONS,
    _build_deterministic_fallback_outline,
    _parse_outline,
)


# ─────────────────────────────────────────────────────────────────
# Test 1: parser rejects section count < 3
# ─────────────────────────────────────────────────────────────────

def test_m203_parser_rejects_section_count_below_min() -> None:
    """Only two valid sections should fail validation with reason
    section_count_below_min."""
    raw = json.dumps({
        "sections": [
            {"title": "Efficacy", "focus": "...", "ev_ids": ["ev_001", "ev_002"]},
            {"title": "Safety",   "focus": "...", "ev_ids": ["ev_003", "ev_004"]},
        ]
    })
    result = _parse_outline(raw)
    assert isinstance(result, OutlineParseResult)
    assert result.ok is False
    assert "section_count_below_min" in result.reason_codes
    # Plans are still returned (caller decides: fallback or abort)
    assert len(result.plans) == 2


# ─────────────────────────────────────────────────────────────────
# Test 2: M-24 — parser ALLOWS overlap across sections
# A single primary study often legitimately supports multiple sections
# (a SURPASS RCT contributes to both Efficacy and Safety). The old
# "no overlap" rule starved downstream sections of citations; M-24
# removes it. Overlap is now reported as info telemetry, not failure.
# ─────────────────────────────────────────────────────────────────

def test_m24_parser_allows_overlapping_ev_ids() -> None:
    raw = json.dumps({
        "sections": [
            {"title": "Efficacy", "focus": "...", "ev_ids": ["ev_001", "ev_002"]},
            {"title": "Safety",   "focus": "...", "ev_ids": ["ev_002", "ev_003"]},  # ev_002 shared
            {"title": "Comparative", "focus": "...", "ev_ids": ["ev_004", "ev_005"]},
        ]
    })
    result = _parse_outline(raw)
    # M-24: overlap is legitimate, plan stays valid
    assert result.ok is True
    # Informational reason code is still recorded for telemetry
    assert any(
        c.startswith("info_overlap:") for c in result.reason_codes
    ), f"Expected info_overlap telemetry, got {result.reason_codes}"
    # All 3 sections survive with their (possibly shared) ev_ids intact
    titles = [p.title for p in result.plans]
    assert "Efficacy" in titles and "Safety" in titles
    # ev_002 appears in BOTH Efficacy and Safety
    eff = next(p for p in result.plans if p.title == "Efficacy")
    safety = next(p for p in result.plans if p.title == "Safety")
    assert "ev_002" in eff.ev_ids
    assert "ev_002" in safety.ev_ids


# ─────────────────────────────────────────────────────────────────
# Test 3: parser deduplicates within-section ids before counting
# ─────────────────────────────────────────────────────────────────

def test_m203_parser_dedupes_within_section_ev_ids() -> None:
    """["ev_001", "ev_001"] is effectively 1 unique id; section is dropped."""
    raw = json.dumps({
        "sections": [
            {"title": "Efficacy", "focus": "...", "ev_ids": ["ev_001", "ev_001"]},  # dedup → 1
            {"title": "Safety",   "focus": "...", "ev_ids": ["ev_002", "ev_003"]},
            {"title": "Comparative Effectiveness", "focus": "...", "ev_ids": ["ev_004", "ev_005"]},
        ]
    })
    result = _parse_outline(raw)
    # The Efficacy section dropped, so only 2 plans survive
    titles = [p.title for p in result.plans]
    assert "Efficacy" not in titles
    assert "Safety" in titles
    # <3 plans → section_count_below_min
    assert "section_count_below_min" in result.reason_codes


# ─────────────────────────────────────────────────────────────────
# Test 4: parser rejects unknown ev_ids when pool is supplied
# ─────────────────────────────────────────────────────────────────

def test_m203_parser_rejects_unknown_ev_ids() -> None:
    raw = json.dumps({
        "sections": [
            {"title": "Efficacy", "focus": "...", "ev_ids": ["ev_001", "ev_002"]},
            {"title": "Safety",   "focus": "...", "ev_ids": ["ev_999", "ev_003"]},  # ev_999 unknown
            {"title": "Comparative Effectiveness", "focus": "...", "ev_ids": ["ev_004", "ev_005"]},
        ]
    })
    allowed = {"ev_001", "ev_002", "ev_003", "ev_004", "ev_005"}
    result = _parse_outline(raw, allowed_ev_ids=allowed)
    assert result.ok is False
    assert any("unknown_ev_ids" in c for c in result.reason_codes)
    # The Safety section should be dropped
    titles = [p.title for p in result.plans]
    assert "Safety" not in titles


# ─────────────────────────────────────────────────────────────────
# Test 5: deterministic fallback builder produces 3 non-overlapping sections
# ─────────────────────────────────────────────────────────────────

def test_m203_deterministic_fallback_builds_3_balanced_sections() -> None:
    evidence = [
        {"evidence_id": f"ev_{i:03d}", "statement": f"fact {i}"}
        for i in range(1, 10)  # 9 evidence ids → 3 per section round-robin
    ]
    plans = _build_deterministic_fallback_outline(evidence)
    assert len(plans) == 3
    # Every section has >=2 unique ev_ids
    for plan in plans:
        assert len(set(plan.ev_ids)) >= 2
    # No overlap across sections
    all_ev = [e for plan in plans for e in plan.ev_ids]
    assert len(all_ev) == len(set(all_ev)), "deterministic fallback must not overlap"


def test_m203_deterministic_fallback_returns_empty_on_insufficient_evidence() -> None:
    """Fewer than 6 evidence ids → cannot build 3 sections of >=2 each."""
    evidence = [
        {"evidence_id": f"ev_{i:03d}", "statement": ""}
        for i in range(1, 6)  # only 5 ids
    ]
    plans = _build_deterministic_fallback_outline(evidence)
    assert plans == []


# ─────────────────────────────────────────────────────────────────
# Test 6: MultiSectionResult carries outline telemetry
# ─────────────────────────────────────────────────────────────────

def test_m203_multisection_result_has_outline_telemetry_fields() -> None:
    from src.polaris_graph.generator.multi_section_generator import MultiSectionResult
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(MultiSectionResult)}
    for expected in (
        "outline_ok",
        "outline_retry_attempted",
        "outline_fallback_used",
        "outline_reason_codes",
    ):
        assert expected in field_names, (
            f"MultiSectionResult missing field {expected!r} required by M-203"
        )


# ─────────────────────────────────────────────────────────────────
# Test 7: orchestrator maps outline_fallback_used → manifest status
# ─────────────────────────────────────────────────────────────────

def test_m203_orchestrator_status_precedence_includes_outline_fallback() -> None:
    """The orchestrator's status-computation block must check
    outline_fallback_used BEFORE the generic ok branches, so a run
    with outline fallback emits partial_outline_fallback, not ok."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    # The outline_fallback check must appear in the status precedence
    assert 'outline_fallback_used' in source, (
        "Orchestrator status block must check outline_fallback_used"
    )
    assert '"ok_outline_fallback"' in source, (
        "Orchestrator must emit summary status ok_outline_fallback"
    )


def test_m203_ok_outline_fallback_maps_to_partial_outline_fallback() -> None:
    from scripts.run_honest_sweep_r3 import to_unified_status
    assert to_unified_status("ok_outline_fallback") == "partial_outline_fallback"
