"""Tests for polaris_graph.generator2.verified_report schemas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from polaris_graph.generator2.verified_report import (
    FrameCoverage,
    FrameGap,
    GenerationError,
    Section,
    VerifiedReport,
    VerifiedSentence,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- VerifiedSentence ----------

def test_verified_sentence_pass_minimal():
    s = VerifiedSentence(
        section_id="sec_population",
        sentence_text="Adults aged 65+ were enrolled.",
        provenance_tokens=["[#ev:abc-123:100-150]"],
        verifier_pass=True,
    )
    assert s.verifier_pass
    assert s.drop_reason is None


def test_verified_sentence_fail_requires_drop_reason():
    with pytest.raises(ValidationError, match="drop_reason is required"):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="Bogus sentence.",
            verifier_pass=False,
        )


def test_verified_sentence_pass_rejects_drop_reason():
    with pytest.raises(ValidationError, match="must be None when verifier_pass=True"):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="Good sentence.",
            verifier_pass=True,
            drop_reason="numeric_mismatch",
        )


def test_verified_sentence_drop_with_reason():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="Numeric claim 23%.",
        provenance_tokens=["[#ev:abc:0-100]"],
        verifier_pass=False,
        drop_reason="numeric_mismatch",
    )
    assert s.drop_reason == "numeric_mismatch"


def test_verified_sentence_evaluator_agrees_default_none():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="x.",
        provenance_tokens=["[#ev:e:0-1]"],
        verifier_pass=True,
    )
    assert s.evaluator_agrees is None


def test_verified_sentence_evaluator_agrees_true_with_pass_true_ok():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="x.",
        provenance_tokens=["[#ev:e:0-1]"],
        verifier_pass=True,
        evaluator_agrees=True,
    )
    assert s.evaluator_agrees is True


def test_verified_sentence_evaluator_agrees_false_with_pass_true_ok():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="x.",
        provenance_tokens=["[#ev:e:0-1]"],
        verifier_pass=True,
        evaluator_agrees=False,
    )
    assert s.evaluator_agrees is False


def test_verified_sentence_evaluator_agrees_true_with_pass_false_forbidden():
    with pytest.raises(ValidationError, match="evaluator_agrees=True is forbidden"):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="x.",
            verifier_pass=False,
            drop_reason="numeric_mismatch",
            evaluator_agrees=True,
        )


def test_frame_coverage_minimal_no_gaps():
    fc = FrameCoverage(covered_entity_count=15, total_entity_count=15)
    assert fc.gaps == []


def test_frame_coverage_with_gaps_passes():
    fc = FrameCoverage(
        covered_entity_count=14,
        total_entity_count=15,
        gaps=[
            FrameGap(
                entity_name="Pediatric",
                reason="no_oa",
                reason_detail="no open-access version of Cochrane review",
            )
        ],
    )
    assert len(fc.gaps) == 1
    assert fc.gaps[0].reason == "no_oa"


def test_frame_gap_accepts_all_9_enum_values():
    for r in (
        "paywalled",
        "no_oa",
        "source_tier_ineligible",
        "language_unavailable",
        "retracted_only",
        "jurisdiction_outside",
        "not_indexed",
        "embargoed",
        "other",
    ):
        g = FrameGap(entity_name="x", reason=r)
        assert g.reason == r


def test_frame_gap_rejects_bogus_reason():
    with pytest.raises(ValidationError):
        FrameGap(entity_name="x", reason="bogus_value")  # type: ignore[arg-type]


def test_frame_gap_reason_detail_optional_and_bounded():
    g = FrameGap(entity_name="x", reason="other")
    assert g.reason_detail is None
    g2 = FrameGap(entity_name="x", reason="other", reason_detail="abc")
    assert g2.reason_detail == "abc"
    with pytest.raises(ValidationError):
        FrameGap(entity_name="x", reason="other", reason_detail="x" * 600)


def test_frame_coverage_count_mismatch_rejected():
    with pytest.raises(ValidationError, match="must equal total_entity_count"):
        FrameCoverage(
            covered_entity_count=14,
            total_entity_count=15,
            gaps=[],  # 14 + 0 != 15
        )


def test_frame_coverage_covered_exceeds_total_rejected():
    with pytest.raises(ValidationError, match="cannot exceed"):
        FrameCoverage(covered_entity_count=16, total_entity_count=15)


def test_verified_sentence_assertion_surface_default_prose():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="x.",
        provenance_tokens=["[#ev:e:0-1]"],
        verifier_pass=True,
    )
    assert s.assertion_surface == "prose"


def test_verified_sentence_assertion_surface_accepts_six_values():
    for surface in ("prose", "table", "summary_bullet", "limitation", "caption", "heading"):
        s = VerifiedSentence(
            section_id="sec_x",
            sentence_text="x.",
            provenance_tokens=["[#ev:e:0-1]"],
            verifier_pass=True,
            assertion_surface=surface,
        )
        assert s.assertion_surface == surface


def test_verified_sentence_assertion_surface_rejects_bogus():
    with pytest.raises(ValidationError):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="x.",
            provenance_tokens=["[#ev:e:0-1]"],
            verifier_pass=True,
            assertion_surface="bogus_surface",  # type: ignore[arg-type]
        )


def test_verified_sentence_synthesis_claim_allows_empty_tokens():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="These trials together suggest moderate effect.",
        provenance_tokens=[],
        verifier_pass=True,
        is_synthesis_claim=True,
    )
    assert s.is_synthesis_claim is True
    assert s.provenance_tokens == []


def test_verified_sentence_synthesis_claim_with_tokens_forbidden():
    with pytest.raises(ValidationError, match="provenance_tokens=\\[\\]"):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="Synthesis with token.",
            provenance_tokens=["[#ev:e:0-3]"],
            verifier_pass=True,
            is_synthesis_claim=True,
        )


def test_verified_sentence_synthesis_claim_with_pass_false_forbidden():
    with pytest.raises(ValidationError, match="verifier_pass=True"):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="Bad synthesis.",
            provenance_tokens=[],
            verifier_pass=False,
            drop_reason="no_provenance_token",
            is_synthesis_claim=True,
        )


def test_verified_sentence_kept_non_synthesis_must_have_tokens():
    with pytest.raises(ValidationError, match="≥1 provenance token"):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="Kept claim with no tokens.",
            provenance_tokens=[],
            verifier_pass=True,
            is_synthesis_claim=False,
        )


def test_verified_sentence_invalid_drop_reason():
    with pytest.raises(ValidationError):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="x",
            verifier_pass=False,
            drop_reason="bogus_reason",  # type: ignore[arg-type]
        )


def test_verified_sentence_no_token_drop():
    s = VerifiedSentence(
        section_id="sec_x",
        sentence_text="Sentence with no token.",
        provenance_tokens=[],
        verifier_pass=False,
        drop_reason="no_provenance_token",
    )
    assert s.provenance_tokens == []


def test_verified_sentence_blank_text_rejected():
    with pytest.raises(ValidationError):
        VerifiedSentence(
            section_id="sec_x",
            sentence_text="",
            verifier_pass=True,
        )


# ---------- Section ----------

def _kept(text: str = "kept sentence") -> VerifiedSentence:
    return VerifiedSentence(
        section_id="sec_x",
        sentence_text=text,
        provenance_tokens=["[#ev:abc:0-100]"],
        verifier_pass=True,
    )


def _dropped(reason: str = "numeric_mismatch") -> VerifiedSentence:
    return VerifiedSentence(
        section_id="sec_x",
        sentence_text="dropped sentence",
        verifier_pass=False,
        drop_reason=reason,  # type: ignore[arg-type]
    )


def test_section_minimal():
    s = Section(
        section_id="sec_population",
        section_title="Population",
        verified_sentences=[_kept(), _kept(), _dropped()],
        section_verify_pass_rate=0.667,
        section_status="verified",
    )
    assert len(s.verified_sentences) == 3


def test_section_kept_sentences_filters():
    s = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[_kept(), _dropped(), _kept()],
        section_verify_pass_rate=0.667,
        section_status="verified",
    )
    assert len(s.kept_sentences()) == 2
    assert all(k.verifier_pass for k in s.kept_sentences())


def test_section_pass_rate_must_be_0_to_1():
    with pytest.raises(ValidationError):
        Section(
            section_id="sec_x",
            section_title="X",
            section_verify_pass_rate=1.5,
            section_status="verified",
        )


def test_section_invalid_status_rejected():
    with pytest.raises(ValidationError):
        Section(
            section_id="sec_x",
            section_title="X",
            section_verify_pass_rate=0.5,
            section_status="weird",  # type: ignore[arg-type]
        )


def test_section_dropped_status_allowed():
    s = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[_dropped(), _dropped()],
        section_verify_pass_rate=0.0,
        section_status="dropped",
    )
    assert s.section_status == "dropped"


# ---------- VerifiedReport ----------

def _success_report(**overrides) -> VerifiedReport:
    started = _now()
    finished = started + timedelta(seconds=10)
    base = dict(
        pool_id="pool-1",
        decision_id="dec-1",
        sections=[
            Section(
                section_id="sec_population",
                section_title="Population",
                verified_sentences=[_kept(), _kept()],
                section_verify_pass_rate=1.0,
                section_status="verified",
            )
        ],
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="deepseek-v4-flash",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=started,
        finished_at_utc=finished,
        latency_ms=10000,
        cost_usd=0.05,
    )
    base.update(overrides)
    return VerifiedReport(**base)  # type: ignore[arg-type]


def test_verified_report_success_minimal():
    r = _success_report()
    assert r.report_id  # uuid
    assert r.pipeline_verdict == "success"
    assert len(r.sections) == 1


def test_verified_report_success_requires_at_least_one_kept_section():
    with pytest.raises(ValidationError, match="at least one non-dropped section"):
        _success_report(
            sections=[
                Section(
                    section_id="sec_x",
                    section_title="X",
                    section_verify_pass_rate=0.0,
                    section_status="dropped",
                )
            ]
        )


def test_verified_report_abort_requires_all_dropped():
    with pytest.raises(ValidationError, match="all sections .* to be dropped"):
        _success_report(
            pipeline_verdict="abort_no_verified_sections",
            sections=[
                Section(
                    section_id="sec_x",
                    section_title="X",
                    verified_sentences=[_kept()],
                    section_verify_pass_rate=1.0,
                    section_status="verified",
                )
            ],
        )


def test_verified_report_abort_with_all_dropped_passes():
    r = _success_report(
        pipeline_verdict="abort_no_verified_sections",
        sections=[
            Section(
                section_id="sec_x",
                section_title="X",
                verified_sentences=[_dropped()],
                section_verify_pass_rate=0.0,
                section_status="dropped",
            )
        ],
        overall_verify_pass_rate=0.0,
    )
    assert r.pipeline_verdict == "abort_no_verified_sections"


def test_verified_report_abort_with_no_sections_passes():
    """Empty sections list is allowed for abort verdict."""
    r = _success_report(
        pipeline_verdict="abort_no_verified_sections",
        sections=[],
        overall_verify_pass_rate=0.0,
    )
    assert r.sections == []


def test_verified_report_finished_before_started_rejected():
    started = _now()
    with pytest.raises(ValidationError, match="finished_at_utc must be"):
        _success_report(
            started_at_utc=started,
            finished_at_utc=started - timedelta(seconds=1),
        )


def test_verified_report_negative_latency_rejected():
    with pytest.raises(ValidationError):
        _success_report(latency_ms=-1)


def test_verified_report_negative_cost_rejected():
    with pytest.raises(ValidationError):
        _success_report(cost_usd=-0.01)


def test_verified_report_invalid_threshold_rejected():
    with pytest.raises(ValidationError):
        _success_report(verifier_pass_threshold=1.5)


def test_verified_report_kept_sections_filters_dropped():
    r = _success_report(
        sections=[
            Section(
                section_id="sec_a",
                section_title="A",
                verified_sentences=[_kept()],
                section_verify_pass_rate=1.0,
                section_status="verified",
            ),
            Section(
                section_id="sec_b",
                section_title="B",
                verified_sentences=[_dropped()],
                section_verify_pass_rate=0.0,
                section_status="dropped",
            ),
        ],
        overall_verify_pass_rate=0.5,
    )
    kept = r.kept_sections()
    assert len(kept) == 1
    assert kept[0].section_id == "sec_a"


def test_verified_report_round_trip_json():
    r = _success_report()
    payload = r.model_dump(mode="json")
    rehydrated = VerifiedReport.model_validate(payload)
    assert rehydrated.report_id == r.report_id
    assert rehydrated.pipeline_verdict == "success"


# ---------- GenerationError ----------

def test_generation_error_minimal():
    err = GenerationError(
        code="inadequate_pool",
        message="Pool adequacy is_adequate=False; cannot generate",
    )
    assert err.error is True
    assert err.code == "inadequate_pool"


def test_generation_error_with_pool_and_decision_ids():
    err = GenerationError(
        code="completion_backend_unavailable",
        message="LLM endpoint refused connection",
        pool_id="p-1",
        decision_id="d-1",
    )
    assert err.pool_id == "p-1"
    assert err.decision_id == "d-1"
