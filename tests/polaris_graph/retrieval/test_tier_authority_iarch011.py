"""I-arch-011 B17 / B11 (KEYSTONE) — venue authority is SEPARATE from fetch completeness.

These tests pin the keystone fix for two related defects:

  * B17: the tier classifier demoted a real scholarly journal (Lancet / Brain /
    Movement Disorders) to the T7 length floor purely because the fetch came
    back as a SHORT STUB — a regression of I-bug-775 (#815). The fix keeps the
    venue-authority tier (no drop), on BOTH the legacy-rules path
    (``PG_USE_AUTHORITY_MODEL`` OFF) AND the authority-model path
    (``PG_USE_AUTHORITY_MODEL`` ON), and LABELS the row ``fetch_degraded=True``.
  * B11: ``build_corpus_credibility_disclosure`` fell back to the flat per-tier
    ``tier_prior`` for every source because the deterministic, domain-aware
    ``authority_score`` was never reaching it. The fix restores
    ``weight_basis == "authority_score"`` as the primary basis by computing it
    deterministically when no pre-computed score is on the object / join map.

The non-laundering invariant is load-bearing and explicitly tested: a known
venue keeps its AUTHORITY weight, but the contentless stub MUST be labelled
``fetch_degraded=True`` so a downstream ADEQUACY lane excludes it from
grounded-content counts — venue authority can never launder an empty stub into
"adequate" grounded content. (The grounded-content COUNT itself lives in an
off-limits gate; ``fetch_degraded is True`` is the in-scope contract this lane
owns and that the adequacy lane consumes.)

Fail-loud / fail-before-pass-after: with the fix REVERTED (T7 demotion applied
regardless of venue + tier_prior basis), the venue-tier and authority_score
assertions below FAIL.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
from src.polaris_graph.nodes.weighted_corpus_gate import (
    build_corpus_credibility_disclosure,
)
from src.polaris_graph.retrieval.tier_classifier import (
    T7_STUB_CONTENT_CHARS,
    ClassificationSignals,
    TierLevel,
    classify_source_tier,
)

# A REAL scholarly venue (The Lancet) whose fetch came back as a short stub:
# the body is well below the T7 stub threshold, but every venue signal (host on
# the peer-reviewed-journal list, OpenAlex journal+venue, primary-study title)
# is present. This is the exact shape B17 regressed on.
_LANCET_STUB = ClassificationSignals(
    url="https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(23)01200-X/fulltext",
    title="Tirzepatide once weekly for the treatment of obesity: a randomized controlled trial",
    openalex_publication_type="article",
    openalex_source_type="journal",
    openalex_venue="The Lancet",
    fetched_content_length=480,  # << T7_STUB_CONTENT_CHARS (1000)
)


def _set_authority_model(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    if on:
        monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    else:
        monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)


# Sanity: the fixture is genuinely a sub-threshold stub, so the assertions below
# actually exercise the stub path (guards against a future threshold change
# silently turning these into no-op full-length tests).
def test_fixture_is_a_substub() -> None:
    assert 0 < _LANCET_STUB.fetched_content_length < T7_STUB_CONTENT_CHARS


@pytest.mark.parametrize("authority_model_on", [False, True], ids=["legacy_rules", "authority_model"])
def test_lancet_stub_keeps_venue_authority_and_is_labelled_degraded(
    monkeypatch: pytest.MonkeyPatch, authority_model_on: bool
) -> None:
    """BOTH paths: a Lancet stub keeps a venue-authority tier (NOT the T7 floor)
    and is labelled ``fetch_degraded=True``."""
    _set_authority_model(monkeypatch, authority_model_on)
    result = classify_source_tier(_LANCET_STUB)

    # Venue authority is preserved — NOT demoted to the T7 length floor.
    assert result.tier != TierLevel.T7, (
        f"Lancet stub was demoted to {result.tier} (the T7 length floor) — B17 "
        f"regression: venue authority must survive a short fetch."
    )
    # A real peer-reviewed primary RCT on The Lancet lands T1.
    assert result.tier == TierLevel.T1, (
        f"expected the venue tier T1 for a Lancet primary RCT, got {result.tier}"
    )
    # The stub is LABELLED degraded so the adequacy lane excludes it from
    # grounded-content counts (the non-laundering contract this lane owns).
    assert result.fetch_degraded is True, (
        "a venue-authority stub MUST be labelled fetch_degraded=True so the "
        "adequacy lane excludes the empty stub from grounded content."
    )


@pytest.mark.parametrize("authority_model_on", [False, True], ids=["legacy_rules", "authority_model"])
def test_non_scholarly_short_stub_still_demotes_to_t7_not_degraded(
    monkeypatch: pytest.MonkeyPatch, authority_model_on: bool
) -> None:
    """The carve-out is venue-scoped: a NON-scholarly short stub is still T7 and
    is NOT labelled degraded (no blanket un-stubbing)."""
    _set_authority_model(monkeypatch, authority_model_on)
    junk = ClassificationSignals(
        url="https://randomblog.example.com/post/1",
        title="some thoughts on a drug",
        fetched_content_length=300,
    )
    result = classify_source_tier(junk)
    assert result.tier == TierLevel.T7
    assert result.fetch_degraded is False


@pytest.mark.parametrize("authority_model_on", [False, True], ids=["legacy_rules", "authority_model"])
def test_genuine_conference_abstract_stays_t7_not_degraded(
    monkeypatch: pytest.MonkeyPatch, authority_model_on: bool
) -> None:
    """Separation of 'T7 because the fetch was short' from 'T7 because it IS an
    abstract': a genuine conference abstract on a journal host stays T7 and is
    NOT un-stubbed / NOT labelled degraded."""
    _set_authority_model(monkeypatch, authority_model_on)
    abstract = ClassificationSignals(
        url="https://academic.oup.com/jcem/article/Supplement_1/abc",
        title="1745-P: Long-Term Safety of Tirzepatide (Conference Abstract)",
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_venue="JCEM",
        fetched_content_length=400,
    )
    result = classify_source_tier(abstract)
    assert result.tier == TierLevel.T7, (
        f"a genuine conference abstract must stay T7, got {result.tier}"
    )
    assert result.fetch_degraded is False, (
        "a real abstract is not a degraded fetch of a full paper — must NOT be "
        "labelled fetch_degraded (else it would be wrongly re-fetched / counted)."
    )


@pytest.mark.parametrize("authority_model_on", [False, True], ids=["legacy_rules", "authority_model"])
def test_full_length_lancet_unchanged(
    monkeypatch: pytest.MonkeyPatch, authority_model_on: bool
) -> None:
    """A full-length Lancet article is unchanged: T1, NOT degraded (the fix only
    touches the sub-threshold stub case)."""
    _set_authority_model(monkeypatch, authority_model_on)
    full = ClassificationSignals(
        url="https://www.thelancet.com/journals/lancet/article/full",
        title="Tirzepatide once weekly: a randomized controlled trial",
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_venue="The Lancet",
        fetched_content_length=8000,
    )
    result = classify_source_tier(full)
    assert result.tier == TierLevel.T1
    assert result.fetch_degraded is False


def test_disclosure_weight_basis_is_authority_score_for_real_rows() -> None:
    """B11: ``build_corpus_credibility_disclosure`` weights by the deterministic,
    domain-aware ``authority_score`` (computed when absent) — NOT the flat
    per-tier ``tier_prior`` — for real scholarly rows. The corpus still flows
    through whole (no drop); this is a WEIGHT restoration only."""
    sources = [
        CorpusSource(
            url="https://www.thelancet.com/x",
            tier="T1",
            domain="thelancet.com",
            title="A randomized controlled trial of tirzepatide",
        ),
        CorpusSource(
            url="https://www.nejm.org/y",
            tier="T1",
            domain="nejm.org",
            title="Semaglutide cardiovascular outcomes trial",
        ),
    ]
    disclosure = build_corpus_credibility_disclosure(
        classified_sources=sources,
        tier_counts={"T1": 2},
        tier_fractions={"T1": 1.0},
        total_sources=2,
        had_material_deviation=False,
        domain="clinical",
        research_question="efficacy of incretin therapies",
    )
    assert len(disclosure.per_source) == 2
    for row in disclosure.per_source:
        assert row.weight_basis == "authority_score", (
            f"{row.url} fell back to {row.weight_basis!r}; B11 requires the "
            f"deterministic authority_score to be the primary weight basis."
        )
        # The weight is the REAL computed authority signal, not the flat T1
        # tier-prior (0.95) — i.e. domain-aware weighting actually ran.
        assert 0.0 <= row.credibility_weight <= 1.0
        assert row.credibility_weight != pytest.approx(0.95), (
            "weight equals the T1 tier_prior (0.95) — the flat prior leaked "
            "back in instead of the computed authority_score."
        )


def test_disclosure_falls_back_to_tier_prior_when_no_url() -> None:
    """The ``tier_prior`` fallback still fires when there is genuinely no signal
    to compute from (no url) — so the disclosure is never blank, and the
    fallback is a graceful WEIGHT, never a drop."""
    sources = [CorpusSource(url="", tier="T4", domain="", title="")]
    disclosure = build_corpus_credibility_disclosure(
        classified_sources=sources,
        tier_counts={"T4": 1},
        tier_fractions={"T4": 1.0},
        total_sources=1,
        had_material_deviation=False,
        domain="clinical",
        research_question="q",
    )
    assert disclosure.per_source[0].weight_basis == "tier_prior"
