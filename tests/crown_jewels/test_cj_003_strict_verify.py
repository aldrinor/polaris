"""Crown Jewel I-cj-003 — Strict-verify per-sentence invariant.

Per CLAUDE.md §9.1.3: every sentence in the verified report must pass
strict_verify.verify_sentence — (a) >=1 well-formed token, (b) every
token resolves to a known source, (c) spans within source bounds,
(d) every decimal in sentence appears in span text, (e) >=N shared
content words between sentence and combined span (default N=2).

Mutation pattern: each REJECT test mutates one element of a known-good
fixture and asserts the SPECIFIC drop_reason — this is what the
issue_breakdown calls "mutation tests verify gate teeth."
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.polaris_graph.clinical_generator.strict_verify import verify_sentence
from src.polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


def _pool(full_text: str = "Aspirin reduced mortality by 12.5 percent in adults.") -> EvidencePool:
    src = Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="t",
        snippet="s",
        full_text=full_text,
        full_text_available=True,
        source_id="src-A",
    )
    return EvidencePool(
        pool_id="p1",
        decision_id="d1",
        sources=[src],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 1, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def test_cj_003_pass_on_well_formed_sentence() -> None:
    sentence = "Aspirin reduced mortality by 12.5 percent [#ev:src-A:0-50]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert ok and reason is None


def test_cj_003_reject_no_provenance_token() -> None:
    ok, reason = verify_sentence("This claim has no token.", _pool(), min_content_overlap=2)
    assert not ok and reason == "no_provenance_token"


def test_cj_003_reject_invalid_token_source() -> None:
    sentence = "Claim cites unknown source [#ev:src-MISSING:0-5]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "invalid_token"


def test_cj_003_reject_span_out_of_range() -> None:
    sentence = "Out of bounds [#ev:src-A:0-10000]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "span_out_of_range"


def test_cj_003_reject_numeric_mismatch() -> None:
    sentence = "Aspirin reduced mortality by 99.9 percent [#ev:src-A:0-50]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "numeric_mismatch"


def test_cj_003_reject_overlap_too_low() -> None:
    sentence = "Apples bananas oranges grapes [#ev:src-A:0-50]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "overlap_too_low"


def test_cj_003_synthesis_claim_passes_without_token() -> None:
    ok, reason = verify_sentence(
        "Synthesis observation across sources.",
        _pool(),
        min_content_overlap=2,
        is_synthesis_claim=True,
    )
    assert ok and reason is None
