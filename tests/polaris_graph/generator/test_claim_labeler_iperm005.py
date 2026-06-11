"""I-perm-005 (#1199) — per-claim confidence labeler (pure keystone).

The §-1.1 invariant under test: a non-VERIFIED claim can NEVER render `high`; unknown credibility
never inflates; a claim with no resolvable cited evidence renders `no-source-found`; and `low` /
`no-source-found` markers read as NOT-asserted-as-fact.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator import claim_labeler as cl


@pytest.fixture(autouse=True)
def _clear_thresholds(monkeypatch):
    # Use the shipped default disclosure thresholds (do not let a stray env skew the bucket).
    # monkeypatch.delenv RESTORES the prior env after the test (no leak into later tests — Codex P2).
    for var in (
        "PG_DISCLOSURE_HIGH_CRED",
        "PG_DISCLOSURE_LOW_CRED",
        "PG_DISCLOSURE_HIGH_MIN_ORIGINS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


def test_no_cited_evidence_is_no_source_found():
    assert (
        cl.confidence_bucket(
            is_verified=False, credibility=None, origin_count=0, has_cited_evidence=False
        )
        == cl.BUCKET_NO_SOURCE
    )
    # Even a (defensively) "verified" claim with no cited evidence -> no-source-found.
    assert (
        cl.confidence_bucket(
            is_verified=True, credibility=0.9, origin_count=3, has_cited_evidence=False
        )
        == cl.BUCKET_NO_SOURCE
    )


def test_non_verified_never_high():
    # The lethal over-confidence the reframe must not introduce.
    for cred in (None, 0.99, 0.5):
        for origins in (0, 1, 5):
            bucket = cl.confidence_bucket(
                is_verified=False,
                credibility=cred,
                origin_count=origins,
                has_cited_evidence=True,
            )
            assert bucket != cl.BUCKET_HIGH
            assert bucket == cl.BUCKET_LOW  # not-verified -> low (per the shared thresholds)


def test_verified_high_requires_credibility_and_origins():
    # High default thresholds: high_cred ~0.8, high_min_origins ~2 (from disclosure_population).
    assert (
        cl.confidence_bucket(
            is_verified=True, credibility=0.95, origin_count=2, has_cited_evidence=True
        )
        == cl.BUCKET_HIGH
    )
    # Verified but only one origin -> not high.
    assert (
        cl.confidence_bucket(
            is_verified=True, credibility=0.95, origin_count=1, has_cited_evidence=True
        )
        != cl.BUCKET_HIGH
    )
    # Verified but unknown credibility -> low (never inflates).
    assert (
        cl.confidence_bucket(
            is_verified=True, credibility=None, origin_count=3, has_cited_evidence=True
        )
        == cl.BUCKET_LOW
    )


def test_marker_text_unmistakable():
    low = cl.render_confidence_marker(cl.BUCKET_LOW)
    nsf = cl.render_confidence_marker(cl.BUCKET_NO_SOURCE)
    assert "low" in low and ("not confirmed" in low.lower() or "unverified" in low.lower())
    assert "unverified" in nsf.lower() or "no grounded source" in nsf.lower()
    # An unknown bucket fails safe to the low wording (never implies support).
    assert cl.render_confidence_marker("bogus") == cl.render_confidence_marker(cl.BUCKET_LOW)


def test_is_asserted_as_fact():
    assert cl.is_asserted_as_fact(cl.BUCKET_HIGH)
    assert cl.is_asserted_as_fact(cl.BUCKET_MODERATE)
    assert not cl.is_asserted_as_fact(cl.BUCKET_LOW)
    assert not cl.is_asserted_as_fact(cl.BUCKET_NO_SOURCE)


def test_bucket_matches_disclosure_certainty_label():
    """confidence_bucket must REUSE the shared disclosure thresholds (no drift) for the
    verified/with-evidence path."""
    from src.polaris_graph.synthesis.disclosure_population import _certainty_label

    for is_verified, cred, origins in [
        (True, 0.95, 2),
        (True, 0.6, 1),
        (True, None, 3),
        (False, 0.9, 2),
    ]:
        assert cl.confidence_bucket(
            is_verified=is_verified,
            credibility=cred,
            origin_count=origins,
            has_cited_evidence=True,
        ) == _certainty_label(is_verified, origins, cred)
