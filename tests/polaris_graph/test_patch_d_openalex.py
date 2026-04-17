"""PATCH-D: OpenAlex authority tier + work_id dedup tests.

Closes PG_LB_SA_01 authority-gate defects:
 - Motley Rice law firm, Medium blog, thegutpunch blog, Fella Health
   telehealth, NHS JS high-school journal, ResearchSquare preprint
   all tiered SILVER alongside SELECT trial data.

Source pattern: api.openalex.org/works endpoint. `type` + `primary_location.
source.type` + top-level `id` (canonical work_id) drive tier + dedup.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.polaris_graph.tools.openalex_client import OpenAlexWork


# ── Test 1: authority_tier mapping ───────────────────────────────

def test_authority_tier_gold_for_journal_article():
    w = OpenAlexWork(
        work_id="W1", doi="10.1000/x", title="NEJM SELECT",
        type="article", source_type="journal",
        source_name="NEJM", publication_year=2023, is_retracted=False,
    )
    assert w.authority_tier() == "GOLD"


def test_authority_tier_gold_for_journal_review():
    w = OpenAlexWork(
        work_id="W2", doi="10.1000/y", title="Cochrane review",
        type="review", source_type="journal",
        source_name="Cochrane", publication_year=2024, is_retracted=False,
    )
    assert w.authority_tier() == "GOLD"


def test_authority_tier_silver_for_preprint():
    w = OpenAlexWork(
        work_id="W3", doi="", title="ResearchSquare preprint",
        type="preprint", source_type="repository",
        source_name="Research Square", publication_year=2022, is_retracted=False,
    )
    assert w.authority_tier() == "SILVER"


def test_authority_tier_silver_for_repository():
    w = OpenAlexWork(
        work_id="W4", doi="", title="PMC deposit",
        type="article", source_type="repository",
        source_name="PMC", publication_year=2023, is_retracted=False,
    )
    assert w.authority_tier() == "SILVER"


def test_authority_tier_bronze_for_book_chapter():
    w = OpenAlexWork(
        work_id="W5", doi="", title="Book chapter",
        type="book-chapter", source_type="book series",
        source_name="Elsevier series", publication_year=2020, is_retracted=False,
    )
    assert w.authority_tier() == "BRONZE"


def test_authority_tier_blocked_for_retracted():
    w = OpenAlexWork(
        work_id="W6", doi="10.1000/retracted", title="Retracted paper",
        type="article", source_type="journal",
        source_name="Lancet", publication_year=2018, is_retracted=True,
    )
    assert w.authority_tier() == "BLOCKED"


def test_authority_tier_blocked_for_erratum():
    w = OpenAlexWork(
        work_id="W7", doi="", title="Erratum",
        type="erratum", source_type="journal",
        source_name="BMJ", publication_year=2024, is_retracted=False,
    )
    assert w.authority_tier() == "BLOCKED"


# ── Test 2: bibliography integration with mocked OpenAlex ────────

def test_bibliography_attaches_openalex_tier_when_enabled(monkeypatch, tmp_path):
    """_build_bibliography reads openalex_client.canonicalize_sync and
    attaches authority_tier to each entry."""
    monkeypatch.setenv("PG_OPENALEX_ENABLED", "1")
    monkeypatch.setenv("OPENALEX_CACHE_DB", str(tmp_path / "test_oa.sqlite"))

    from src.polaris_graph.wiki.wiki_builder import _build_bibliography
    from src.polaris_graph.tools import openalex_client as _oa

    # Reload ENABLED to pick up env var
    _oa.ENABLED = True

    def _mock_canonicalize(url="", doi="", title=""):
        if "SELECT" in title or "10.1056" in doi:
            return OpenAlexWork(
                work_id="https://openalex.org/W_SELECT",
                doi="10.1056/NEJMoa2307563", title="SELECT trial",
                type="article", source_type="journal",
                source_name="NEJM", publication_year=2023,
                is_retracted=False,
            )
        return None  # unknown source

    with patch.object(_oa, "canonicalize_sync", side_effect=_mock_canonicalize):
        section_claims = {
            "s01": [
                {
                    "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2307563",
                    "source_title": "SELECT trial NEJM",
                    "doi": "10.1056/NEJMoa2307563",
                    "year": 2023, "relevance_score": 0.95,
                    "evidence_id": "ev_a", "authors": [], "source_type": "journal_article",
                },
                {
                    "source_url": "https://www.motleyrice.com/diabetes-lawsuits/ozempic/fda-warning",
                    "source_title": "Ozempic law firm page",
                    "doi": "", "year": 2024, "relevance_score": 0.6,
                    "evidence_id": "ev_b", "authors": [], "source_type": "web",
                },
            ],
        }
        bib = _build_bibliography(section_claims)

    # Two distinct entries
    assert len(bib) == 2
    # Find each by URL
    nejm = next(b for b in bib if "nejm.org" in b["url"])
    motley = next(b for b in bib if "motleyrice" in b["url"])
    # NEJM resolved by OpenAlex as GOLD
    assert nejm["authority_tier"] == "GOLD"
    assert nejm["openalex_id"] == "https://openalex.org/W_SELECT"
    assert nejm["publication_type"] == "article"
    assert nejm["source_type_normalized"] == "journal"
    # Motley Rice not in OpenAlex → UNKNOWN
    assert motley["authority_tier"] == "UNKNOWN"
    assert motley["openalex_id"] == ""


# ── Test 3: disabled flag bypasses OpenAlex entirely ─────────────

def test_bibliography_skips_openalex_when_disabled(monkeypatch):
    """PG_OPENALEX_ENABLED=0 → no HTTP calls, authority_tier defaults UNKNOWN."""
    monkeypatch.setenv("PG_OPENALEX_ENABLED", "0")

    from src.polaris_graph.wiki.wiki_builder import _build_bibliography
    from src.polaris_graph.tools import openalex_client as _oa
    _oa.ENABLED = False

    with patch.object(_oa, "canonicalize_sync") as mock_canon:
        section_claims = {
            "s01": [
                {
                    "source_url": "https://www.example.com/paper",
                    "source_title": "Some paper",
                    "doi": "10.1000/abc", "year": 2024,
                    "relevance_score": 0.8, "evidence_id": "ev_x",
                    "authors": [], "source_type": "journal_article",
                },
            ],
        }
        bib = _build_bibliography(section_claims)

    # OpenAlex never called
    assert mock_canon.call_count == 0
    # Still one entry, tier UNKNOWN
    assert len(bib) == 1
    assert bib[0]["authority_tier"] == "UNKNOWN"


# ── Test 4: OpenAlex work_id dedups same paper at publisher + PMC ─

def test_bibliography_dedups_by_openalex_work_id(monkeypatch, tmp_path):
    """Same work at publisher URL + PMC URL without DOI in one record
    but with DOI in the other — OpenAlex work_id collapses both."""
    monkeypatch.setenv("PG_OPENALEX_ENABLED", "1")
    monkeypatch.setenv("OPENALEX_CACHE_DB", str(tmp_path / "test_oa2.sqlite"))

    from src.polaris_graph.wiki.wiki_builder import _build_bibliography
    from src.polaris_graph.tools import openalex_client as _oa
    _oa.ENABLED = True

    # Both entries resolve to the same work_id
    same_work = OpenAlexWork(
        work_id="https://openalex.org/W_SAME",
        doi="10.1056/NEJMoa2307563", title="SELECT trial",
        type="article", source_type="journal",
        source_name="NEJM", publication_year=2023, is_retracted=False,
    )

    with patch.object(_oa, "canonicalize_sync", return_value=same_work):
        section_claims = {
            "s01": [
                {
                    "source_url": "https://publisher-a.example.com/select-article",
                    "source_title": "SELECT NEJM",
                    "doi": "",  # no DOI on first record
                    "year": 2023, "relevance_score": 0.9,
                    "evidence_id": "ev_pub", "authors": [],
                    "source_type": "journal_article",
                },
                {
                    "source_url": "https://mirror-b.example.com/select-mirror",
                    "source_title": "SELECT trial mirror",
                    # No DOI, no PMC pattern, no FDA setid pattern —
                    # so OpenAlex work_id is the ONLY available key.
                    "doi": "",
                    "year": 2023, "relevance_score": 0.85,
                    "evidence_id": "ev_pmc", "authors": [],
                    "source_type": "journal_article",
                },
            ],
        }
        bib = _build_bibliography(section_claims)

    # OpenAlex work_id collapsed the two entries
    assert len(bib) == 1
    assert set(bib[0]["evidence_ids"]) == {"ev_pub", "ev_pmc"}
    assert bib[0]["authority_tier"] == "GOLD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
