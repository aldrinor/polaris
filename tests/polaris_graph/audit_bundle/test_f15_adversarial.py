"""F15 adversarial tests (I-f15-005): paywalled, oversize per-source, partial run."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.audit_bundle.manifest_builder import build_manifest_and_files
from polaris_graph.audit_bundle.snapshot_sources import MAX_SOURCE_TEXT_BYTES
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

PAYWALL_SNIPPET = "paywalled snippet text 50 chars exactly here."


def _src(source_id: str, full_text: str | None, snippet: str = "snippet") -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title=f"Source {source_id}",
        snippet=snippet,
        full_text=full_text,
        full_text_available=(full_text is not None),
        source_id=source_id,
        provenance={"legal_cleared": True},
    )


def _decision() -> ScopeDecision:
    return ScopeDecision(
        decision_id="dec-adv-1",
        status="in_scope",
        scope_class="clinical_efficacy",
        ambiguity_axes=[
            AmbiguityAxis(axis="population", plausible_interpretations=["adults"], needs_clarification=False),
        ],
    )


def _pool(sources: list[Source]) -> EvidencePool:
    return EvidencePool(
        pool_id="pool-adv-1",
        decision_id="dec-adv-1",
        sources=sources,
        adequacy=AdequacyVerdict(is_adequate=True),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _report(sentences: list[VerifiedSentence], verdict: str = "success") -> VerifiedReport:
    if verdict == "success":
        section = Section(
            section_id="sec_x",
            section_title="X",
            verified_sentences=sentences,
            section_verify_pass_rate=1.0,
            section_status="verified",
        )
    else:
        section = Section(
            section_id="sec_x",
            section_title="X",
            verified_sentences=sentences,
            section_verify_pass_rate=0.0,
            section_status="dropped",
        )
    return VerifiedReport(
        pool_id="pool-adv-1",
        decision_id="dec-adv-1",
        sections=[section],
        overall_verify_pass_rate=1.0 if verdict == "success" else 0.0,
        pipeline_verdict=verdict,
        generator_model="test/model",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def test_paywalled_source_falls_back_to_snippet():
    paywall = _src("src-A", full_text=None, snippet=PAYWALL_SNIPPET)
    sentence = VerifiedSentence(
        section_id="sec_x",
        sentence_text=f"claim [#ev:src-A:0-{len(PAYWALL_SNIPPET)}].",
        provenance_tokens=[f"[#ev:src-A:0-{len(PAYWALL_SNIPPET)}]"],
        verifier_pass=True,
    )
    _, files = build_manifest_and_files(_decision(), _pool([paywall]), _report([sentence]))
    snapshot = files["sources/src-A.txt"].decode("utf-8")
    assert snapshot == PAYWALL_SNIPPET


def test_500mb_per_source_capped():
    big = lambda sid: _src(sid, full_text="x" * 250_000)
    sources = [big(f"src-{i}") for i in range(5)]
    sentences = [
        VerifiedSentence(
            section_id="sec_x",
            sentence_text=f"claim [#ev:src-{i}:0-100].",
            provenance_tokens=[f"[#ev:src-{i}:0-100]"],
            verifier_pass=True,
        )
        for i in range(5)
    ]
    _, files = build_manifest_and_files(_decision(), _pool(sources), _report(sentences))
    snapshot_paths = [p for p in files if p.startswith("sources/")]
    assert len(snapshot_paths) == 5
    for path in snapshot_paths:
        assert len(files[path]) <= MAX_SOURCE_TEXT_BYTES + 500, (
            f"{path} exceeded per-source cap: {len(files[path])} bytes"
        )


def test_partial_run_aborts_bundle_build():
    src = _src("src-A", full_text="something")
    dropped = VerifiedSentence(
        section_id="sec_x",
        sentence_text="claim text.",
        provenance_tokens=[],
        verifier_pass=False,
        drop_reason="no_provenance_token",
    )
    with pytest.raises(ValueError, match="verdict"):
        build_manifest_and_files(
            _decision(), _pool([src]), _report([dropped], verdict="abort_no_verified_sections")
        )
