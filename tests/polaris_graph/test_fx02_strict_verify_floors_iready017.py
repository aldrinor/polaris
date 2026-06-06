"""I-ready-017 FX-02 (#1106) — verifier-side floors complementing FX-01 (generation-side).

BUG-03 (empty/contentless sentence): a sentence with no content words AND no decimals/numbers
passed strict_verify vacuously (the provenance_generator content-overlap floor is GATED behind
`if sentence_content:`, so it was SKIPPED). A token-only / punctuation-only "sentence" must never
be a verified clinical claim.

BUG-01 Layer-2 (discourse narration): the drb_72 scratchpad WRAPPED a verbatim source quote in
writing-act narration ("We can split it: ... too choppy", "I'll use the exact phrase",
"Final attempt:", "I need to add about 124 more words"). The embedded quote passes strict_verify
(>=2 content-word overlap) AND the entailment judge (it is entailed), so the narration rode along
and shipped as VERIFIED clinical prose. FX-02 adds a config-driven (LAW VI), flag-gated
(PG_STRICT_VERIFY_DISCOURSE_FLOOR, default off), high-precision discourse-narration floor, applied
LAST. It must drop the scratchpad sentences WITHOUT false-dropping real clinical prose.

Entailment is set to `off` in the discourse tests so the sentence reaches the discourse floor via
the mechanical checks alone (the floor runs regardless of entailment mode); this isolates the floor
without a live LLM judge call.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.polaris_graph.clinical_generator.strict_verify import (
    is_discourse_narration,
    verify_sentence,
)
from src.polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


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
# BUG-03 — empty / contentless sentence floor
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
# BUG-01 Layer-2 — discourse-narration floor (pure pattern unit first)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sentence",
    [
        'We can split it: "Strong complementarities increase productivity." But that might be too choppy.',
        "That's three sentences from the thesis.",
        'I\'ll use the exact phrase: "However, automation also complements labor." That\'s fine, even if short.',
        "Final attempt: the labor market adjusts over decades.",
        "Still 176. I need to add about 124 more words.",
    ],
)
def test_bug01l2_discourse_sentences_match(sentence: str) -> None:
    """The exact drb_72 scratchpad shapes are detected as discourse narration."""
    assert is_discourse_narration(sentence) is not None, f"missed narration: {sentence!r}"


@pytest.mark.parametrize(
    "sentence",
    [
        # Real clinical/scientific prose that MUST NOT be flagged (no false-drop).
        "We can administer tirzepatide at 5 mg weekly with dose titration.",
        "We can keep the maintenance dose at 5 mg in renally impaired adults.",
        "Clinicians can use this agent when metformin is contraindicated.",
        "The trial was short, lasting only twelve weeks, but the effect was durable.",
        "Tirzepatide did not increase cardiovascular risk versus placebo.",
        "For example, SURPASS-2 enrolled adults with type 2 diabetes.",
        "Strong complementarities between automation and labor increase productivity.",
    ],
)
def test_bug01l2_clinical_prose_not_flagged(sentence: str) -> None:
    """High-precision patterns must not match genuine clinical/scientific sentences."""
    assert is_discourse_narration(sentence) is None, f"false-positive on: {sentence!r}"


# ---------------------------------------------------------------------------
# BUG-01 Layer-2 — end-to-end through verify_sentence (flag-gated)
# ---------------------------------------------------------------------------
def _discourse_pool() -> tuple[EvidencePool, str]:
    full = "Strong complementarities between automation and labor increase productivity."
    pool = _pool(_src(full_text=full))
    # Discourse narration WRAPPING the verbatim span quote — clears overlap (>=2) + (entailment off).
    sentence = (
        'We can split it: "Strong complementarities between automation and labor increase '
        f'productivity." But that might be too choppy [#ev:src-1:0-{len(full)}].'
    )
    return pool, sentence


def test_bug01l2_enforce_drops_discourse_wrapping_quote(monkeypatch) -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_DISCOURSE_FLOOR", "enforce")
    pool, sentence = _discourse_pool()
    passed, reason = verify_sentence(sentence, pool, min_content_overlap=2)
    assert passed is False
    assert reason == "discourse_narration"


def test_bug01l2_off_is_noop_discourse_passes(monkeypatch) -> None:
    """Flag OFF (default) -> the discourse sentence passes (byte-unchanged behavior)."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_DISCOURSE_FLOOR", "off")
    pool, sentence = _discourse_pool()
    passed, reason = verify_sentence(sentence, pool, min_content_overlap=2)
    assert passed is True, f"off-mode must be a no-op; got drop {reason}"


def test_bug01l2_enforce_keeps_real_clinical_claim(monkeypatch) -> None:
    """A real clinical claim wrapping the SAME span quote (no narration) survives enforce mode."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_DISCOURSE_FLOOR", "enforce")
    full = "Strong complementarities between automation and labor increase productivity."
    pool = _pool(_src(full_text=full))
    sentence = (
        f"Strong complementarities between automation and labor increase productivity "
        f"[#ev:src-1:0-{len(full)}]."
    )
    passed, reason = verify_sentence(sentence, pool, min_content_overlap=2)
    assert passed is True, f"real clinical claim false-dropped: {reason}"
