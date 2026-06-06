"""I-ready-017 FX-02 (#1106) — verifier-side empty/contentless-sentence floor (BUG-03).

BUG-03: a sentence with no content words AND no decimals/numbers passed strict_verify vacuously —
`provenance_generator`'s content-overlap floor is GATED behind `if sentence_content:`, so a
token-only / punctuation-only / all-stopword "sentence" (residue reduces to ".") was SKIPPED and
counted VERIFIED. A token-only sentence is never a valid clinical claim. The floor runs
UNCONDITIONALLY (it must not be bypassable via `require_number_match=False`).

BUG-01 Layer-2 (discourse-narration floor) was IMPLEMENTED then REMOVED on Codex's explicit
recommendation across three diff-gate rounds: every surface pattern that matched the drb_72
scratchpad vocabulary also false-dropped real clinical prose (split/combine = dosing, repetitive =
rTMS, "X attempt:" = procedure labels, rephrase/"use the exact phrase" = patient communication &
aphasia rehab, and even "N more words" = speech-language vocabulary targets). §-1.1: a false-drop of
a real clinical claim is LETHAL, so a pattern-based discourse floor is unsafe. FX-01 (#1105,
generation-side, verified) is the defense — a length-truncated scratchpad is never promoted to
content, so the quote-wrapping narration never reaches strict_verify in the first place.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.polaris_graph.clinical_generator.strict_verify import verify_sentence
from src.polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)
from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance


def _src(full_text: str, source_id: str = "src-1") -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0},
            min_required_per_tier={SourceTier.T1: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


# ---------------------------------------------------------------------------
# BUG-03 — clinical strict_verify.verify_sentence
# ---------------------------------------------------------------------------
def test_bug03_contentless_token_only_sentence_dropped() -> None:
    """A token-only sentence ('[#ev:src-1:0-5].') has no content words AND no decimals -> drop."""
    pool = _pool(_src(full_text="Aspirin reduced cardiovascular events in adults by 23.5%."))
    passed, reason = verify_sentence("[#ev:src-1:0-5].", pool)
    assert passed is False
    assert reason == "empty_or_contentless_sentence"


def test_bug03_real_clinical_sentence_with_content_still_passes() -> None:
    """A real clinical sentence with content words is NOT a BUG-03 drop (entailment off)."""
    full = "Aspirin reduced cardiovascular events in adults."
    pool = _pool(_src(full_text=full))
    passed, reason = verify_sentence(
        f"Aspirin reduced cardiovascular events in adults [#ev:src-1:0-{len(full)}].",
        pool,
        min_content_overlap=2,
    )
    assert passed is True, f"unexpected drop: {reason}"


# ---------------------------------------------------------------------------
# BUG-03 — provenance_generator: the empty floor runs UNCONDITIONALLY
# ---------------------------------------------------------------------------
def _prov_pool() -> dict:
    # provenance token regex requires [A-Za-z0-9_]+ for the evidence id (no hyphens).
    return {"src_1": {"direct_quote": "Aspirin reduced cardiovascular events in adults by 23.5%."}}


@pytest.mark.parametrize("require_number_match", [True, False])
def test_bug03_provenance_token_only_dropped_regardless_of_number_match(
    require_number_match: bool,
) -> None:
    """A token-only sentence must drop in BOTH require_number_match modes — the floor must NOT be
    bypassable via require_number_match=False (Codex iter-1 P2)."""
    result = verify_sentence_provenance(
        "[#ev:src_1:0-5].", _prov_pool(), require_number_match=require_number_match
    )
    assert result.is_verified is False
    assert "empty_or_contentless_sentence" in result.failure_reasons


def test_bug03_provenance_numeric_only_fragment_dropped_when_number_match_off() -> None:
    """Codex iter-2 P2: with require_number_match=False the numeric block is skipped, so a
    numeric-only fragment ('23.5 [#ev:...]') is never validated against the span — a bare number
    with no content words is unverifiable and must be dropped."""
    pool = {"src_1": {"direct_quote": "The event rate was 23.5 percent in the treatment arm."}}
    result = verify_sentence_provenance(
        "23.5 [#ev:src_1:0-5].", pool, require_number_match=False
    )
    assert result.is_verified is False
    assert "empty_or_contentless_sentence" in result.failure_reasons


def test_bug03_provenance_real_sentence_passes_with_number_match_off() -> None:
    """A real grounded sentence is NOT false-dropped by the unconditional empty floor when
    require_number_match=False (the floor only fires on truly contentless sentences)."""
    full = "Aspirin reduced cardiovascular events in adults by 23.5%."
    pool = {"src_1": {"direct_quote": full}}
    result = verify_sentence_provenance(
        f"Aspirin reduced cardiovascular events in adults [#ev:src_1:0-{len(full)}].",
        pool,
        require_number_match=False,
    )
    assert result.is_verified is True, f"unexpected drop: {result.failure_reasons}"
    assert "empty_or_contentless_sentence" not in result.failure_reasons
