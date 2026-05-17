"""Sovereignty CI — legal-cleared spans only (I-f15-006)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.audit_bundle.manifest_builder import build_manifest_and_files
from polaris_graph.audit_bundle.sovereignty_guard import (
    LEGAL_CLEARED_KEY,
    assert_all_pool_sources_legal_cleared,
)
from polaris_graph.clinical_generator.verified_report import (
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
from polaris_graph.scope.scope_decision import AmbiguityAxis, ScopeDecision


def _src(source_id: str, provenance: dict) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title=f"Source {source_id}",
        snippet="snippet",
        full_text="trial of aspirin",
        full_text_available=True,
        source_id=source_id,
        provenance=provenance,
    )


def _decision() -> ScopeDecision:
    return ScopeDecision(
        decision_id="dec-sov-1",
        status="in_scope",
        scope_class="clinical_efficacy",
        ambiguity_axes=[
            AmbiguityAxis(axis="population", plausible_interpretations=["adults"], needs_clarification=False),
        ],
    )


def _pool(sources: list[Source]) -> EvidencePool:
    return EvidencePool(
        pool_id="pool-sov-1",
        decision_id="dec-sov-1",
        sources=sources,
        adequacy=AdequacyVerdict(is_adequate=True),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _report(cited_source_ids: list[str]) -> VerifiedReport:
    sentences = [
        VerifiedSentence(
            section_id="sec_x",
            sentence_text=f"claim [#ev:{sid}:0-3].",
            provenance_tokens=[f"[#ev:{sid}:0-3]"],
            verifier_pass=True,
        )
        for sid in cited_source_ids
    ]
    return VerifiedReport(
        pool_id="pool-sov-1",
        decision_id="dec-sov-1",
        sections=[
            Section(
                section_id="sec_x",
                section_title="X",
                verified_sentences=sentences,
                section_verify_pass_rate=1.0,
                section_status="verified",
            )
        ],
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="test/model",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def test_legal_cleared_source_passes_guard():
    src = _src("src-A", {LEGAL_CLEARED_KEY: True})
    assert_all_pool_sources_legal_cleared(_pool([src]))


def test_uncleared_source_fails_guard():
    src = _src("src-A", {})
    with pytest.raises(ValueError, match="copyrighted span"):
        assert_all_pool_sources_legal_cleared(_pool([src]))


def test_explicit_false_legal_cleared_fails_guard():
    src = _src("src-A", {LEGAL_CLEARED_KEY: False})
    with pytest.raises(ValueError, match="copyrighted span"):
        assert_all_pool_sources_legal_cleared(_pool([src]))


def test_one_cleared_one_uncleared_fails_guard():
    cleared = _src("src-A", {LEGAL_CLEARED_KEY: True})
    bad = _src("src-B", {})
    with pytest.raises(ValueError, match="src-B"):
        assert_all_pool_sources_legal_cleared(_pool([cleared, bad]))


def test_uncited_uncleared_source_still_fails_guard():
    """Uncited sources still ship in evidence_pool.json, so they must be cleared."""
    cleared = _src("src-A", {LEGAL_CLEARED_KEY: True})
    bad = _src("src-B", {})
    with pytest.raises(ValueError, match="src-B"):
        assert_all_pool_sources_legal_cleared(_pool([cleared, bad]))


def test_build_manifest_refuses_uncleared_source_integration():
    bad = _src("src-A", {})
    with pytest.raises(ValueError, match="copyrighted span"):
        build_manifest_and_files(_decision(), _pool([bad]), _report(["src-A"]))
