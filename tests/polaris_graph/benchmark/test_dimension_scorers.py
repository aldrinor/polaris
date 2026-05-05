"""Tests for dimension_scorers — 7 BEAT-BOTH scoring functions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.benchmark.benchmark_config import BenchmarkQuestion
from polaris_graph.benchmark.dimension_scorers import (
    ALL_DIMENSIONS,
    DimensionScore,
    LATENCY_BUDGET_SECONDS,
    PROVENANCE_DENSITY_TARGET,
    score_auditability,
    score_coverage_completeness,
    score_latency,
    score_numeric_grounding,
    score_provenance_density,
    score_refusal_correctness,
    score_sourcing_tier_mix,
)
from polaris_graph.generator2.verified_report import (
    Section,
    VerifiedReport,
    VerifiedSentence,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Fixtures ----------

def _q(
    qid: str = "Q1",
    refusal_bait: bool = False,
    pico: list[str] | None = None,
    keywords: list[str] | None = None,
) -> BenchmarkQuestion:
    if pico is None:
        pico = ["population", "intervention", "outcome"]
    return BenchmarkQuestion(
        question_id=qid,
        question_text="text",
        scope_class="out_of_scope" if refusal_bait else "clinical_efficacy",
        is_refusal_bait=refusal_bait,
        expected_pico_axes=pico,
        expected_pico_keywords=keywords or [],
    )


def _src(tier: SourceTier, host: str) -> Source:
    return Source(
        url=f"https://{host}/x",
        domain=host,
        tier=tier,
        title="src",
        snippet="snippet",
        full_text="text" * 30,
        full_text_available=True,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={
                SourceTier.T1: sum(1 for s in sources if s.tier == SourceTier.T1),
                SourceTier.T2: sum(1 for s in sources if s.tier == SourceTier.T2),
                SourceTier.T3: sum(1 for s in sources if s.tier == SourceTier.T3),
            },
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _kept(text: str, tokens: list[str]) -> VerifiedSentence:
    return VerifiedSentence(
        section_id="sec_x",
        sentence_text=text,
        provenance_tokens=tokens,
        verifier_pass=True,
    )


def _section(*sentences: VerifiedSentence) -> Section:
    return Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=list(sentences),
        section_verify_pass_rate=1.0 if sentences and all(s.verifier_pass for s in sentences) else 0.5,
        section_status="verified",
    )


def _report(*sections: Section) -> VerifiedReport:
    return VerifiedReport(
        pool_id="pool",
        decision_id="dec",
        sections=list(sections),
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="m",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=120000,
        cost_usd=0.0,
    )


# ---------- Constants ----------

def test_all_dimensions_count():
    assert len(ALL_DIMENSIONS) == 7


# ---------- 1. sourcing_tier_mix ----------

def test_tier_mix_polaris_all_t1():
    pool = _pool(_src(SourceTier.T1, "cochrane.org"), _src(SourceTier.T1, "fda.gov"))
    s = score_sourcing_tier_mix(pool=pool, external_text=None, question=_q())
    assert s.polaris_score == 1.0
    assert s.external_score is None


def test_tier_mix_polaris_mixed():
    pool = _pool(
        _src(SourceTier.T1, "fda.gov"),
        _src(SourceTier.T2, "nejm.org"),
        _src(SourceTier.T3, "clinicaltrials.gov"),
    )
    s = score_sourcing_tier_mix(pool=pool, external_text=None, question=_q())
    assert abs(s.polaris_score - (1.0 + 0.7 + 0.4) / 3) < 1e-9


def test_tier_mix_polaris_empty_pool():
    pool = _pool()
    s = score_sourcing_tier_mix(pool=pool, external_text=None, question=_q())
    assert s.polaris_score == 0.0


def test_tier_mix_external_recognized_hosts():
    text = "See https://www.cochrane.org/CD001 and https://www.nejm.org/doi/abc"
    s = score_sourcing_tier_mix(pool=None, external_text=text, question=_q())
    assert s.external_score is not None
    assert abs(s.external_score - (1.0 + 0.7) / 2) < 1e-9


def test_tier_mix_external_no_recognized_hosts():
    text = "See https://random-blog.example.com/post"
    s = score_sourcing_tier_mix(pool=None, external_text=text, question=_q())
    assert s.external_score == 0.0


# ---------- 2. numeric_grounding ----------

def test_numeric_grounding_polaris_no_decimals():
    """Sentence with no decimals -> trivially grounded."""
    report = _report(_section(_kept("Adults benefited from aspirin.", ["[#ev:s:0-3]"])))
    pool = _pool(_src(SourceTier.T1, "cochrane.org"))
    s = score_numeric_grounding(
        report=report, pool=pool, external_text=None, question=_q()
    )
    assert s.polaris_score == 1.0


def test_numeric_grounding_polaris_with_decimals_grounded():
    """strict_verify already enforced this; assume grounded."""
    report = _report(_section(_kept("52% response [#ev:s:0-100].", ["[#ev:s:0-100]"])))
    pool = _pool(_src(SourceTier.T1, "cochrane.org"))
    s = score_numeric_grounding(
        report=report, pool=pool, external_text=None, question=_q()
    )
    assert s.polaris_score == 1.0


def test_numeric_grounding_no_kept_sentences():
    """All-dropped report -> 0.0 score."""
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id="sec_x",
                sentence_text="bad",
                verifier_pass=False,
                drop_reason="numeric_mismatch",
            )
        ],
        section_verify_pass_rate=0.0,
        section_status="dropped",
    )
    bad_report = VerifiedReport(
        pool_id="p",
        decision_id="d",
        sections=[section],
        overall_verify_pass_rate=0.0,
        pipeline_verdict="abort_no_verified_sections",
        generator_model="m",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )
    pool = _pool(_src(SourceTier.T1, "cochrane.org"))
    s = score_numeric_grounding(
        report=bad_report, pool=pool, external_text=None, question=_q()
    )
    assert s.polaris_score == 0.0


def test_numeric_grounding_external_decimal_near_url():
    """External heuristic: decimal grounded if URL appears within 200 chars."""
    text = "Aspirin reduced events 52% (p<0.001) per https://nejm.org/doi/abc study."
    s = score_numeric_grounding(
        report=None, pool=None, external_text=text, question=_q()
    )
    assert s.external_score is not None
    assert s.external_score > 0.0


def test_numeric_grounding_external_decimal_no_url():
    text = "Aspirin reduced events 52% as commonly reported."
    s = score_numeric_grounding(
        report=None, pool=None, external_text=text, question=_q()
    )
    assert s.external_score is not None
    assert s.external_score == 0.0


def test_numeric_grounding_external_no_decimals():
    text = "Aspirin works for headaches."
    s = score_numeric_grounding(
        report=None, pool=None, external_text=text, question=_q()
    )
    assert s.external_score == 1.0


# ---------- 3. provenance_density ----------

def test_density_polaris_high_density():
    """3 sentences each with 1 token = 1.0 / target 1.5 = 0.667 score."""
    report = _report(_section(
        _kept("a [#ev:s:0-3].", ["[#ev:s:0-3]"]),
        _kept("b [#ev:s:0-3].", ["[#ev:s:0-3]"]),
        _kept("c [#ev:s:0-3].", ["[#ev:s:0-3]"]),
    ))
    s = score_provenance_density(
        report=report, external_text=None, question=_q()
    )
    assert abs(s.polaris_score - (1.0 / PROVENANCE_DENSITY_TARGET)) < 1e-9


def test_density_polaris_target_density():
    """avg = target -> score = 1.0."""
    target_int = int(PROVENANCE_DENSITY_TARGET * 2)
    tokens = [f"[#ev:s:{i}-{i+10}]" for i in range(target_int)]
    report = _report(_section(
        _kept("a " + " ".join(tokens) + ".", tokens),
        _kept("b " + " ".join(tokens) + ".", tokens),
    ))
    s = score_provenance_density(
        report=report, external_text=None, question=_q()
    )
    assert s.polaris_score == 1.0


def test_density_polaris_capped_at_one():
    """Excessive density still capped at 1.0."""
    big = ["[#ev:s:0-3]"] * 20
    report = _report(_section(_kept("a " + " ".join(big) + ".", big)))
    s = score_provenance_density(
        report=report, external_text=None, question=_q()
    )
    assert s.polaris_score == 1.0


def test_density_external_with_urls():
    text = "Adults benefited https://nejm.org/a. Aspirin worked https://cochrane.org/b."
    s = score_provenance_density(
        report=None, external_text=text, question=_q()
    )
    assert s.external_score is not None
    assert s.external_score > 0.0


# ---------- 4. refusal_correctness ----------

def test_refusal_bait_polaris_correctly_refuses():
    s = score_refusal_correctness(
        report=None,
        polaris_intake_status="refused",
        external_text=None,
        question=_q(refusal_bait=True),
    )
    assert s.polaris_score == 1.0


def test_refusal_bait_polaris_correctly_out_of_scope():
    s = score_refusal_correctness(
        report=None,
        polaris_intake_status="out_of_scope",
        external_text=None,
        question=_q(refusal_bait=True),
    )
    assert s.polaris_score == 1.0


def test_refusal_bait_polaris_incorrectly_in_scope():
    s = score_refusal_correctness(
        report=None,
        polaris_intake_status="in_scope",
        external_text=None,
        question=_q(refusal_bait=True),
    )
    assert s.polaris_score == 0.0


def test_refusal_bait_external_refused():
    s = score_refusal_correctness(
        report=None,
        polaris_intake_status=None,
        external_text="I can't help with that, this is out of scope for me.",
        question=_q(refusal_bait=True),
    )
    assert s.external_score == 1.0


def test_refusal_bait_external_did_not_refuse():
    s = score_refusal_correctness(
        report=None,
        polaris_intake_status=None,
        external_text="The 2024 election was contested between...",
        question=_q(refusal_bait=True),
    )
    assert s.external_score == 0.0


def test_non_bait_in_scope_required():
    """For non-bait questions, POLARIS scores 1.0 if it produced a report."""
    report = _report(_section(_kept("a [#ev:s:0-3].", ["[#ev:s:0-3]"])))
    s = score_refusal_correctness(
        report=report,
        polaris_intake_status="in_scope",
        external_text="any output",
        question=_q(refusal_bait=False),
    )
    assert s.polaris_score == 1.0
    assert s.external_score == 1.0


# ---------- 5. coverage_completeness ----------

def test_coverage_polaris_all_axes():
    text = "The population (adults) received intervention (aspirin) and outcome was measured."
    report = _report(_section(_kept(text + " [#ev:s:0-3]", ["[#ev:s:0-3]"])))
    s = score_coverage_completeness(
        report=report,
        external_text=None,
        question=_q(pico=["population", "intervention", "outcome"]),
    )
    assert s.polaris_score == 1.0


def test_coverage_polaris_partial():
    text = "The population (adults) received aspirin."
    report = _report(_section(_kept(text + " [#ev:s:0-3]", ["[#ev:s:0-3]"])))
    s = score_coverage_completeness(
        report=report,
        external_text=None,
        question=_q(pico=["population", "intervention", "outcome"]),
    )
    # Only 'population' covered
    assert abs(s.polaris_score - 1 / 3) < 1e-9


def test_coverage_no_expected_axes_vacuously_full():
    """Refusal-bait with empty expected_pico_axes -> 1.0."""
    s = score_coverage_completeness(
        report=None, external_text="anything",
        question=_q(refusal_bait=True, pico=[]),
    )
    assert s.polaris_score == 1.0
    assert s.external_score == 1.0


def test_coverage_keywords_take_precedence_over_axes():
    """When expected_pico_keywords is set, scorer uses content keywords."""
    text = "Adults with migraine received aspirin and reported relief."
    report = _report(_section(_kept(text + " [#ev:s:0-3]", ["[#ev:s:0-3]"])))
    # All 3 keywords appear; axes ('population' etc.) do NOT appear in text
    s = score_coverage_completeness(
        report=report,
        external_text=None,
        question=_q(
            pico=["population", "intervention", "outcome"],
            keywords=["adults", "aspirin", "migraine"],
        ),
    )
    assert s.polaris_score == 1.0
    # Evidence should reference the matched keywords, not axis names
    assert "adults" in s.polaris_evidence
    assert "aspirin" in s.polaris_evidence


def test_coverage_falls_back_to_axes_when_keywords_empty():
    """expected_pico_keywords=[] -> use axes (backward compat)."""
    text = "Population intervention outcome were the same."
    report = _report(_section(_kept(text + " [#ev:s:0-3]", ["[#ev:s:0-3]"])))
    s = score_coverage_completeness(
        report=report,
        external_text=None,
        question=_q(
            pico=["population", "intervention", "outcome"],
            keywords=[],  # empty -> fallback
        ),
    )
    assert s.polaris_score == 1.0


def test_coverage_keywords_partial_match():
    text = "Adults received aspirin."  # 'migraine' missing
    report = _report(_section(_kept(text + " [#ev:s:0-3]", ["[#ev:s:0-3]"])))
    s = score_coverage_completeness(
        report=report,
        external_text=None,
        question=_q(keywords=["adults", "aspirin", "migraine"]),
    )
    assert abs(s.polaris_score - 2 / 3) < 1e-9


# ---------- 6. latency ----------

def test_latency_zero_ms_full_score():
    s = score_latency(
        polaris_latency_ms=0,
        external_latency_ms=None,
        question=_q(),
    )
    assert s.polaris_score == 1.0


def test_latency_at_budget_zero_score():
    """LATENCY_BUDGET_SECONDS = 600s; at exactly that, score ~= 0."""
    s = score_latency(
        polaris_latency_ms=LATENCY_BUDGET_SECONDS * 1000,
        external_latency_ms=None,
        question=_q(),
    )
    assert s.polaris_score == 0.0


def test_latency_over_budget_clamped_to_zero():
    s = score_latency(
        polaris_latency_ms=LATENCY_BUDGET_SECONDS * 1000 * 2,
        external_latency_ms=None,
        question=_q(),
    )
    assert s.polaris_score == 0.0


def test_latency_unknown_external_returns_none():
    s = score_latency(
        polaris_latency_ms=60_000, external_latency_ms=None, question=_q()
    )
    assert s.external_score is None


def test_latency_unknown_polaris_zero_score():
    s = score_latency(
        polaris_latency_ms=None, external_latency_ms=None, question=_q()
    )
    assert s.polaris_score == 0.0


# ---------- 7. auditability ----------

def test_auditability_polaris_uniquely_one():
    s = score_auditability(
        polaris_bundle_available=True,
        external_bundle_available=False,
        question=_q(),
    )
    assert s.polaris_score == 1.0
    assert s.external_score == 0.0


def test_auditability_no_bundle_zero():
    s = score_auditability(
        polaris_bundle_available=False,
        external_bundle_available=False,
        question=_q(),
    )
    assert s.polaris_score == 0.0
    assert s.external_score == 0.0
