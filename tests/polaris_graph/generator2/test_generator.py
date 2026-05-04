"""Tests for the generator orchestrator (network-free)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pytest

from polaris_graph.generator2.generator import (
    DEFAULT_VERIFIER_PASS_THRESHOLD,
    process_generation,
)
from polaris_graph.generator2.section_blueprint import (
    Blueprint,
    SectionPlan,
)
from polaris_graph.generator2.verified_report import (
    GenerationError,
    VerifiedReport,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------------------------------------------------------------------------
# Pool fixtures
# ---------------------------------------------------------------------------

def _src(
    source_id: str = "src-1",
    full_text: str = (
        "The randomized trial enrolled 1247 adults with chronic migraines. "
        "Aspirin 325mg demonstrated significant headache reduction at "
        "outcomes assessment. Adverse events occurred in 8% of participants."
    ),
) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet=full_text[:200],
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
    )


def _adequate_pool() -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=[_src(source_id="src-1"), _src(source_id="src-2")],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={
                SourceTier.T1: 2,
                SourceTier.T2: 0,
                SourceTier.T3: 0,
            },
            min_required_per_tier={
                SourceTier.T1: 0,
                SourceTier.T2: 0,
                SourceTier.T3: 0,
            },
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _inadequate_pool() -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=[],
        adequacy=AdequacyVerdict(
            is_adequate=False,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={
                SourceTier.T1: 2,
                SourceTier.T2: 4,
                SourceTier.T3: 2,
            },
            failure_reason="not enough sources",
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


# ---------------------------------------------------------------------------
# Stub completion_fn factories
# ---------------------------------------------------------------------------

def _good_completion(text_per_call: list[str]) -> Callable:
    state = {"i": 0}

    def fn(prompt, section_plan, pool):
        i = state["i"]
        state["i"] = i + 1
        if i < len(text_per_call):
            return text_per_call[i]
        return text_per_call[-1] if text_per_call else ""

    return fn


def _good_efficacy_text() -> str:
    """Sentence with valid token + decimal in span + content overlap."""
    full = (
        "The randomized trial enrolled 1247 adults with chronic migraines. "
        "Aspirin 325mg demonstrated significant headache reduction at "
        "outcomes assessment. Adverse events occurred in 8% of participants."
    )
    return (
        f"The trial enrolled 1247 adults with chronic migraines and showed "
        f"significant aspirin headache reduction "
        f"[#ev:src-1:0-{len(full)}]."
    )


# ---------------------------------------------------------------------------
# Validation paths
# ---------------------------------------------------------------------------

def test_inadequate_pool_returns_error():
    err = process_generation(_inadequate_pool())
    assert isinstance(err, GenerationError)
    assert err.code == "inadequate_pool"


def test_default_completion_fn_returns_error():
    err = process_generation(_adequate_pool())
    assert isinstance(err, GenerationError)
    assert err.code == "completion_backend_unavailable"


def test_completion_exception_returns_error():
    def boom(prompt, section_plan, pool):
        raise ConnectionError("simulated outage")

    err = process_generation(_adequate_pool(), completion_fn=boom)
    assert isinstance(err, GenerationError)
    assert err.code == "completion_backend_unavailable"
    assert "ConnectionError" in err.message


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_adequate_pool_with_good_text_returns_success():
    fn = _good_completion([_good_efficacy_text()])
    result = process_generation(
        _adequate_pool(),
        completion_fn=fn,
        scope_class="clinical_efficacy",
    )
    assert isinstance(result, VerifiedReport)
    assert result.pipeline_verdict == "success"
    assert len(result.sections) == 4  # efficacy blueprint = 4 sections
    assert all(s.section_status != "dropped" for s in result.sections)


def test_pool_decision_id_propagates_to_report():
    fn = _good_completion([_good_efficacy_text()])
    pool = _adequate_pool()
    result = process_generation(
        pool, completion_fn=fn, scope_class="clinical_efficacy"
    )
    assert isinstance(result, VerifiedReport)
    assert result.pool_id == pool.pool_id
    assert result.decision_id == pool.decision_id


# ---------------------------------------------------------------------------
# All-section drop -> abort
# ---------------------------------------------------------------------------

def test_token_less_text_drops_all_sections():
    """If completion returns sentences with NO provenance tokens, every
    section ends up dropped → pipeline aborts."""
    fn = _good_completion(["Aspirin works in adults. The trial was good."])
    result = process_generation(
        _adequate_pool(),
        completion_fn=fn,
        scope_class="clinical_efficacy",
    )
    assert isinstance(result, VerifiedReport)
    assert result.pipeline_verdict == "abort_no_verified_sections"
    assert all(s.section_status == "dropped" for s in result.sections)


def test_invalid_token_drops_all_sections():
    fn = _good_completion(["Aspirin works [#ev:bogus:0-100]."])
    result = process_generation(
        _adequate_pool(),
        completion_fn=fn,
        scope_class="clinical_efficacy",
    )
    assert isinstance(result, VerifiedReport)
    assert result.pipeline_verdict == "abort_no_verified_sections"


# ---------------------------------------------------------------------------
# Regeneration path
# ---------------------------------------------------------------------------

def test_first_attempt_fails_second_passes_marks_regenerated():
    """First call returns token-less text (drops below threshold), second
    returns valid text — section marked 'regenerated'."""
    bad = "Aspirin works."
    good = _good_efficacy_text()

    # 4 sections × 2 attempts each = 8 calls; first per section bad, second good
    pattern = []
    for _ in range(4):
        pattern.append(bad)
        pattern.append(good)
    fn = _good_completion(pattern)

    result = process_generation(
        _adequate_pool(),
        completion_fn=fn,
        scope_class="clinical_efficacy",
    )
    assert isinstance(result, VerifiedReport)
    assert result.pipeline_verdict == "success"
    assert all(s.section_status == "regenerated" for s in result.sections)


# ---------------------------------------------------------------------------
# Custom blueprint / threshold
# ---------------------------------------------------------------------------

def test_custom_blueprint_used():
    custom = Blueprint(
        scope_class="custom_test",
        sections=(
            SectionPlan("sec_only", "Only", "single section test"),
        ),
    )
    fn = _good_completion([_good_efficacy_text()])
    result = process_generation(
        _adequate_pool(),
        completion_fn=fn,
        blueprint=custom,
    )
    assert isinstance(result, VerifiedReport)
    assert len(result.sections) == 1
    assert result.sections[0].section_id == "sec_only"


def test_custom_threshold_zero_passes_anything():
    """Threshold=0 means even a 0% pass-rate section is 'verified'."""
    fn = _good_completion(["Aspirin works."])  # no token, all drop
    result = process_generation(
        _adequate_pool(),
        completion_fn=fn,
        scope_class="clinical_efficacy",
        verifier_pass_threshold=0.0,
    )
    assert isinstance(result, VerifiedReport)
    assert result.pipeline_verdict == "success"


def test_default_threshold_is_0_4():
    assert DEFAULT_VERIFIER_PASS_THRESHOLD == 0.40


# ---------------------------------------------------------------------------
# Latency + cost
# ---------------------------------------------------------------------------

def test_report_latency_non_negative():
    fn = _good_completion([_good_efficacy_text()])
    result = process_generation(
        _adequate_pool(), completion_fn=fn, scope_class="clinical_efficacy"
    )
    assert isinstance(result, VerifiedReport)
    assert result.latency_ms >= 0


def test_report_cost_zero_in_pr6():
    """PR 6 ships orchestrator with stubbed completion; PR 7 wires real cost."""
    fn = _good_completion([_good_efficacy_text()])
    result = process_generation(
        _adequate_pool(), completion_fn=fn, scope_class="clinical_efficacy"
    )
    assert isinstance(result, VerifiedReport)
    assert result.cost_usd == 0.0


def test_scope_class_explicit_routes_blueprint():
    """When scope_class is passed explicitly, the matching blueprint is used."""
    pool = _adequate_pool()
    fn = _good_completion([_good_efficacy_text()])
    result = process_generation(
        pool, completion_fn=fn, scope_class="clinical_safety"
    )
    assert isinstance(result, VerifiedReport)
    # safety blueprint has 4 sections; section_ids differ from efficacy
    assert len(result.sections) == 4
    section_ids = {s.section_id for s in result.sections}
    assert "sec_adverse_events" in section_ids


def test_no_scope_class_falls_back_to_default_efficacy_blueprint():
    pool = _adequate_pool()
    fn = _good_completion([_good_efficacy_text()])
    result = process_generation(pool, completion_fn=fn)
    assert isinstance(result, VerifiedReport)
    section_ids = {s.section_id for s in result.sections}
    # Default = CLINICAL_EFFICACY blueprint
    assert "sec_outcomes" in section_ids
    assert "sec_intervention" in section_ids
