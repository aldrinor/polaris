"""Reviewer-blind walkthrough test (I-f15-004).

Verifies a third party can locate the cited span in the bundle and that
the bundle build refuses to ship unreachable spans.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from polaris_graph.audit_bundle.manifest_builder import (
    FILE_EVIDENCE_POOL,
    FILE_METADATA,
    FILE_REVIEWER_README,
    FILE_SCOPE_DECISION,
    FILE_VERIFIED_REPORT,
    build_manifest_and_files,
)
from polaris_graph.audit_bundle.snapshot_sources import MAX_SOURCE_TEXT_BYTES
from polaris_graph.generator2.provenance import extract_tokens
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
from polaris_graph.scope.scope_decision import AmbiguityAxis, ScopeDecision


def _src(source_id: str = "src-A", full_text: str = "Aspirin reduces headache pain.") -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
        provenance={"legal_cleared": True},
    )


def _pool(sources: list[Source]) -> EvidencePool:
    return EvidencePool(
        pool_id="pool-walk-1",
        decision_id="dec-walk-1",
        sources=sources,
        adequacy=AdequacyVerdict(is_adequate=True),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _decision() -> ScopeDecision:
    return ScopeDecision(
        decision_id="dec-walk-1",
        status="in_scope",
        scope_class="clinical_efficacy",
        ambiguity_axes=[
            AmbiguityAxis(axis="population", plausible_interpretations=["adults"], needs_clarification=False),
        ],
    )


def _report(sentence: VerifiedSentence) -> VerifiedReport:
    return VerifiedReport(
        pool_id="pool-walk-1",
        decision_id="dec-walk-1",
        sections=[
            Section(
                section_id="sec_x",
                section_title="X",
                verified_sentences=[sentence],
                section_verify_pass_rate=1.0,
                section_status="verified",
            )
        ],
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="test/model",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def test_happy_path_reviewer_blind_walkthrough():
    sentence = VerifiedSentence(
        section_id="sec_x",
        sentence_text="Aspirin reduces headache [#ev:src-A:0-29].",
        provenance_tokens=["[#ev:src-A:0-29]"],
        verifier_pass=True,
    )
    manifest, files = build_manifest_and_files(_decision(), _pool([_src()]), _report(sentence))

    for required in (
        FILE_SCOPE_DECISION,
        FILE_EVIDENCE_POOL,
        FILE_VERIFIED_REPORT,
        FILE_METADATA,
        FILE_REVIEWER_README,
        "sources/src-A.txt",
    ):
        assert required in files, f"missing {required}"

    readme_disk = (Path(__file__).resolve().parents[3] / "src/polaris_graph/audit_bundle/REVIEWER_README.md").read_bytes()
    assert files[FILE_REVIEWER_README] == readme_disk

    tokens = extract_tokens(sentence.sentence_text)
    assert tokens, "test fixture must produce at least one token"
    tok = tokens[0]
    source_text = files[f"sources/{tok.source_id}.txt"].decode("utf-8")
    span = source_text[tok.span_start : tok.span_end]
    assert span == "Aspirin reduces headache pain"
    assert manifest.file_by_content_type("source_snapshot")


def test_fail_path_truncation_boundary():
    big_source = _src(full_text="x" * 250_000)
    span_end = MAX_SOURCE_TEXT_BYTES + 100
    sentence = VerifiedSentence(
        section_id="sec_x",
        sentence_text=f"claim [#ev:src-A:0-{span_end}].",
        provenance_tokens=[f"[#ev:src-A:0-{span_end}]"],
        verifier_pass=True,
    )
    with pytest.raises(ValueError, match="cited span unreachable"):
        build_manifest_and_files(_decision(), _pool([big_source]), _report(sentence))


def test_fail_path_token_only_in_sentence_text():
    sentence = VerifiedSentence(
        section_id="sec_x",
        sentence_text="claim [#ev:src-A:0-1000000] words.",
        provenance_tokens=["[#ev:src-A:0-5]"],
        verifier_pass=True,
    )
    with pytest.raises(ValueError, match="cited span unreachable"):
        build_manifest_and_files(_decision(), _pool([_src()]), _report(sentence))


def test_fail_path_missing_source():
    sentence = VerifiedSentence(
        section_id="sec_x",
        sentence_text="claim [#ev:ghost:0-3].",
        provenance_tokens=["[#ev:ghost:0-3]"],
        verifier_pass=True,
    )
    with pytest.raises(ValueError, match="cited span unreachable"):
        build_manifest_and_files(_decision(), _pool([_src()]), _report(sentence))
