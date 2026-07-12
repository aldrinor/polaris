"""Offline unit tests for S2 source-metadata enrichment (deterministic, no LLM/network).

Locks the §-1.3 contract: POPULATE-only, RE-TIER on clear signal, NEVER downgrade a real tier,
never invent metadata that is not literally present in the evidence.
"""
from src.polaris_graph.retrieval.source_metadata import (
    enrich_row_metadata,
    extract_doi,
    domain_of,
)


def test_doi_from_quote():
    row = {"direct_quote": "as shown in Acemoglu & Restrepo (doi:10.1257/jep.29.3.3) the ...",
           "source_url": "https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3", "tier": "UNKNOWN"}
    enrich_row_metadata(row)
    assert row["doi"] == "10.1257/jep.29.3.3"
    # has-DOI + aeaweb domain => T1 (upgraded from UNKNOWN)
    assert row["tier"] == "T1"
    assert row["journal"] == "American Economic Association"


def test_journal_name_from_text_beats_domain():
    row = {"direct_quote": "published in the Journal of Economic Perspectives, this paper ...",
           "source_url": "https://example.org/x", "tier": ""}
    enrich_row_metadata(row)
    assert row["journal"] == "Journal of Economic Perspectives"


def test_never_downgrade_real_tier():
    row = {"direct_quote": "no doi here", "source_url": "https://medium.com/@x/post", "tier": "T1"}
    enrich_row_metadata(row)
    # medium.com maps to T7 but the row already has a real T1 => must be PRESERVED.
    assert row["tier"] == "T1"


def test_domain_tier_upgrade_without_doi():
    row = {"direct_quote": "BLS reports employment figures", "source_url": "https://www.bls.gov/x",
           "tier": "UNKNOWN"}
    enrich_row_metadata(row)
    assert row["tier"] == "T3"
    assert row["journal"] == "U.S. Bureau of Labor Statistics"


def test_no_invention_when_no_signal():
    row = {"direct_quote": "plain text no ids", "source_url": "https://randomblog.example/p",
           "tier": "UNKNOWN"}
    enrich_row_metadata(row)
    assert not row.get("doi")
    assert not row.get("journal")
    assert row["tier"] == "UNKNOWN"  # no clear signal => unchanged


def test_existing_doi_not_overwritten():
    row = {"doi": "10.9999/keep.me", "direct_quote": "10.1257/jep.29.3.3", "source_url": "", "tier": "T2"}
    enrich_row_metadata(row)
    assert row["doi"] == "10.9999/keep.me"


def test_helpers():
    assert domain_of("https://www.aeaweb.org/articles?id=1") == "aeaweb.org"
    assert extract_doi("see 10.1016/j.jecon.2020.01.001.", "") == "10.1016/j.jecon.2020.01.001"
