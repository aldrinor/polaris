"""I-deepfix-001 tier_venue_exemption (Codex P1 #2) — no-laundering wiring test.

THE BUG (offline RED->GREEN):
The tier classifier already LABELS a short known-scholarly-venue stub
``tier_result.fetch_degraded=True`` (it keeps its venue-authority tier — WEIGHT,
never a drop — but must be excluded from grounded-content adequacy so venue
authority cannot launder a contentless stub into "adequate"). But the live
evidence row built at ``live_retriever.py:~5769`` copied only
``tier_result.tier.value`` and NEVER ``tier_result.fetch_degraded``. So a short
DOI / OpenAlex-peer-reviewed stub that is NOT otherwise
``content_starved`` / ``landing_page`` / ``fetch_failed`` still counted as
grounded content: ``count_grounded_rows`` (corpus_adequacy_gate.py:52) excludes
only the degraded flags PRESENT on the row.

THE FIX propagates ``tier_result.fetch_degraded`` onto the row via the pure
helper ``live_retriever._row_degraded_flags`` (called at the 5769 row build), so
the stub keeps its tier WEIGHT but is EXCLUDED from the grounded-content count.

FAITHFULNESS: the fix only ADDS the ``fetch_degraded`` label to a row the tier
layer already flagged; it touches no claim, span, citation, or the faithfulness
engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding).

Offline: pure functions, no GPU, no network, no paid LLM.
"""
from __future__ import annotations

from src.polaris_graph.nodes.corpus_adequacy_gate import count_grounded_rows
from src.polaris_graph.retrieval.live_retriever import _row_degraded_flags
from src.polaris_graph.retrieval.tier_classifier import (
    T7_STUB_CONTENT_CHARS,
    ClassificationSignals,
    TierLevel,
    classify_source_tier,
)

# A REAL peer-reviewed venue (The Lancet) fetched as a short stub — the exact
# shape the tier layer labels fetch_degraded=True while keeping T1 venue authority.
_LANCET_STUB = ClassificationSignals(
    url="https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(23)01200-X/fulltext",
    title="Tirzepatide once weekly for the treatment of obesity: a randomized controlled trial",
    openalex_publication_type="article",
    openalex_source_type="journal",
    openalex_venue="The Lancet",
    fetched_content_length=480,  # << T7_STUB_CONTENT_CHARS (1000)
)
_LANCET_FULL = ClassificationSignals(
    url="https://www.thelancet.com/journals/lancet/article/full",
    title="Tirzepatide once weekly: a randomized controlled trial",
    openalex_publication_type="article",
    openalex_source_type="journal",
    openalex_venue="The Lancet",
    fetched_content_length=8000,  # full text
)


def _build_row_like_live_retriever(signals: ClassificationSignals) -> dict:
    """Mirror the grounded evidence-row build at live_retriever.py:~5769 for the
    fields under test: copy the tier value AND merge the degraded-flag propagation
    (the fix). Uses the REAL tier classifier so the tier_result is production-shaped."""
    tier_result = classify_source_tier(signals)
    row = {
        "evidence_id": "ev_000",
        "source_url": signals.url,
        "title": signals.title,
        "direct_quote": "some short but real fetched body text about the trial",
        "tier": tier_result.tier.value,
        "source": "openalex",
    }
    row.update(_row_degraded_flags(tier_result))
    return row


def test_fixture_is_a_substub() -> None:
    """Guard: the stub is genuinely sub-threshold so the assertions exercise the stub path."""
    assert 0 < _LANCET_STUB.fetched_content_length < T7_STUB_CONTENT_CHARS


def test_venue_stub_row_is_flagged_degraded_and_excluded_but_keeps_tier() -> None:
    """A short peer-reviewed venue stub row gets fetch_degraded=True AND is excluded from
    the grounded-content count, WHILE keeping its T1 venue tier weight (no laundering)."""
    row = _build_row_like_live_retriever(_LANCET_STUB)

    # Tier WEIGHT preserved — the venue authority still rides on the row.
    assert row["tier"] == TierLevel.T1.value

    # The degraded label is now propagated onto the row (RED pre-fix: helper absent /
    # flag never set, so the key was missing).
    assert row.get("fetch_degraded") is True

    # And the grounded-content count EXCLUDES it (the no-laundering contract). Pre-fix
    # the row carried no degraded flag, so count_grounded_rows counted it as grounded.
    assert count_grounded_rows([row]) == 0


def test_full_length_venue_row_is_not_degraded_and_counts() -> None:
    """A full-length venue row is NOT flagged and DOES count toward grounded content
    (byte-identical: the fix only fires on a tier-flagged stub)."""
    row = _build_row_like_live_retriever(_LANCET_FULL)
    assert row["tier"] == TierLevel.T1.value
    assert "fetch_degraded" not in row       # additive-only: absent when not degraded
    assert count_grounded_rows([row]) == 1


def test_row_degraded_flags_is_additive_only() -> None:
    """_row_degraded_flags returns an empty dict for a non-degraded tier_result (so the row
    is byte-identical) and {'fetch_degraded': True} for a degraded one."""
    non_degraded = classify_source_tier(_LANCET_FULL)
    degraded = classify_source_tier(_LANCET_STUB)
    assert _row_degraded_flags(non_degraded) == {}
    assert _row_degraded_flags(degraded) == {"fetch_degraded": True}


def test_recovered_row_does_not_inherit_stale_degraded_flag() -> None:
    """BUG-B02/B04 guard: when a forced re-fetch upgraded a stub to full text, the row is a
    normal full-text row — the stale classification-time fetch_degraded MUST NOT propagate
    (else a recovered row would be wrongly excluded from grounded content)."""
    degraded = classify_source_tier(_LANCET_STUB)
    assert degraded.fetch_degraded is True                     # stale classification-time flag
    assert _row_degraded_flags(degraded, recovered=True) == {}  # cleared on recovery
    assert _row_degraded_flags(degraded, recovered=False) == {"fetch_degraded": True}
