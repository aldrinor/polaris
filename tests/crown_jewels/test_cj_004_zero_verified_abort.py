"""Crown Jewel I-cj-004 — Zero-verified abort invariant.

Per CLAUDE.md §9.1.4: if every section fails strict_verify, the report
verdict MUST be 'abort_no_verified_sections' (not a pseudo-success
report). Conversely, a 'success' verdict requires >=1 non-dropped
section.

Bound by VerifiedReport._verdict_consistency (model_validator).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.polaris_graph.clinical_generator.verified_report import (
    Section,
    VerifiedReport,
    VerifiedSentence,
)


def _dropped_section(sid: str = "sec_x") -> Section:
    return Section(
        section_id=sid,
        section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id=sid,
                sentence_text="bad claim",
                provenance_tokens=[],
                verifier_pass=False,
                drop_reason="no_provenance_token",
            ),
        ],
        section_verify_pass_rate=0.0,
        section_status="dropped",
    )


def _kept_section(sid: str = "sec_x") -> Section:
    return Section(
        section_id=sid,
        section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id=sid,
                sentence_text="claim [#ev:src-A:0-3].",
                provenance_tokens=["[#ev:src-A:0-3]"],
                verifier_pass=True,
                drop_reason=None,
            ),
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )


def _report_kwargs() -> dict:
    return dict(
        pool_id="p1",
        decision_id="d1",
        overall_verify_pass_rate=0.0,
        generator_model="g",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def test_cj_004_abort_with_all_dropped_sections_constructs() -> None:
    rpt = VerifiedReport(
        sections=[_dropped_section("a"), _dropped_section("b")],
        pipeline_verdict="abort_no_verified_sections",
        **_report_kwargs(),
    )
    assert rpt.pipeline_verdict == "abort_no_verified_sections"
    assert rpt.kept_sections() == []


def test_cj_004_abort_with_empty_sections_constructs() -> None:
    rpt = VerifiedReport(
        sections=[],
        pipeline_verdict="abort_no_verified_sections",
        **_report_kwargs(),
    )
    assert rpt.pipeline_verdict == "abort_no_verified_sections"


def test_cj_004_abort_with_kept_section_raises() -> None:
    with pytest.raises(ValidationError, match="requires all sections.*dropped"):
        VerifiedReport(
            sections=[_dropped_section("a"), _kept_section("b")],
            pipeline_verdict="abort_no_verified_sections",
            **_report_kwargs(),
        )


def test_cj_004_success_with_only_dropped_sections_raises() -> None:
    with pytest.raises(ValidationError, match="requires at least one non-dropped"):
        VerifiedReport(
            sections=[_dropped_section("a")],
            pipeline_verdict="success",
            **_report_kwargs(),
        )
