"""Batch-1 LEVER B — wiring + logic unit checks (Round-2 fixes).

Covers the two wiring gaps and the two logic-correctness fixes the re-gate flagged:

  #1  RQ-source-eligibility actually FIRES (fired_count > 0) once the constraints are cached
      on the protocol, and the wiring seam ``ensure_rq_constraints`` populates that cache.
  #3  Citation re-anchor requires a STRICTLY-MORE-PRIMARY candidate AND a STRUCTURAL same-fact
      match — a lower-tier/non-primary row sharing only generic stopwords is NEVER re-anchored.
  #4  Recency comparator DIRECTION is preserved: a "before YEAR" constraint demotes a LATER row
      and keeps an EARLIER one (the inverse of a "since YEAR" floor).

All default-OFF paths stay byte-identical (empty plan / unchanged id). No network, no LLM.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval import rq_eligibility as rqe
from src.polaris_graph.planning import citation_reanchor as car


# ── #1: eligibility FIRES ────────────────────────────────────────────────────────────────────


def _row(url, *, document_type="UNKNOWN", year=None, language=None):
    r = {"source_url": url, "document_type": document_type}
    if year is not None:
        r["year"] = year
    if language is not None:
        r["language"] = language
    return r


def test_eligibility_off_is_empty_plan(monkeypatch):
    monkeypatch.delenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", raising=False)
    protocol = {"_rq_constraints": {"source_types": ["journal_article"]}}
    rows = [_row("u1", document_type="NEWS")]
    plan = rqe.build_rq_eligibility(protocol, rows)
    assert plan.is_empty()
    assert not plan.url_to_eligibility_weight


def test_eligibility_fires_on_source_type(monkeypatch):
    """The core wiring assertion: with constraints cached + enforce ON, at least one ineligible
    row is DEMOTED (fired_count > 0) — the lever is no longer inert."""
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    protocol = {"_rq_constraints": {"source_types": ["journal_article"]}}
    rows = [
        _row("journal", document_type="JOURNAL_ARTICLE"),  # eligible
        _row("news", document_type="NEWS"),                # INELIGIBLE -> demoted
    ]
    plan = rqe.build_rq_eligibility(protocol, rows)
    fired_count = len(plan.url_to_eligibility_weight)
    assert fired_count > 0, "eligibility must FIRE (demote >=1 ineligible source)"
    assert "news" in plan.ineligible_urls
    assert "journal" not in plan.ineligible_urls
    assert 0.0 < plan.url_to_eligibility_weight["news"] < 1.0  # demoted, KEPT (weight-not-drop)


def test_ensure_rq_constraints_populates_cache(monkeypatch):
    """The wiring seam: when the cache is absent and extraction is unavailable (live extractor
    off), ``ensure_rq_constraints`` still CACHES a (possibly empty) dict so the read succeeds and
    the extractor is never re-attempted — the '_rq_constraints never written' gap is closed."""
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    monkeypatch.delenv("PG_CONSTRAINT_EXTRACT_LIVE", raising=False)
    protocol = {"research_question": "peer-reviewed journal articles about X"}
    assert "_rq_constraints" not in protocol
    cached = rqe.ensure_rq_constraints(protocol, protocol["research_question"])
    assert "_rq_constraints" in protocol  # WRITTEN, not just read
    assert cached is protocol["_rq_constraints"]


def test_unresolved_row_is_recovery_flagged_not_demoted(monkeypatch):
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    protocol = {"_rq_constraints": {"source_types": ["journal_article"]}}
    rows = [_row("mystery", document_type="UNKNOWN")]  # unknown genre => fail-open + recovery
    plan = rqe.build_rq_eligibility(protocol, rows)
    assert "mystery" not in plan.ineligible_urls
    assert "mystery" in plan.fetch_recovery_urls


# ── #4: recency direction ────────────────────────────────────────────────────────────────────


def test_recency_before_demotes_later_keeps_earlier(monkeypatch):
    """'published before 2023' => an UPPER bound: 2024 is ineligible, 2022 is fine (the inverse of
    a 'since' floor). This is the exact inversion bug the re-gate flagged."""
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    protocol = {"_rq_constraints": {"recency": "published before 2023"}}
    rows = [_row("old", year=2022), _row("new", year=2024)]
    plan = rqe.build_rq_eligibility(protocol, rows)
    assert "new" in plan.ineligible_urls   # 2024 > ceiling 2023 => demoted
    assert "old" not in plan.ineligible_urls  # 2022 kept


def test_recency_since_demotes_earlier_keeps_later(monkeypatch):
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    protocol = {"_rq_constraints": {"recency": "since 2020"}}
    rows = [_row("old", year=2018), _row("new", year=2024)]
    plan = rqe.build_rq_eligibility(protocol, rows)
    assert "old" in plan.ineligible_urls   # 2018 < floor 2020 => demoted
    assert "new" not in plan.ineligible_urls


def test_recency_range_is_closed_window(monkeypatch):
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    protocol = {"_rq_constraints": {"recency": "between 2019 and 2021"}}
    rows = [_row("lo", year=2018), _row("mid", year=2020), _row("hi", year=2023)]
    plan = rqe.build_rq_eligibility(protocol, rows)
    assert "lo" in plan.ineligible_urls
    assert "hi" in plan.ineligible_urls
    assert "mid" not in plan.ineligible_urls


def test_parse_recency_bounds_directions():
    assert rqe._parse_recency_bounds("before 2023") == (None, 2023)
    assert rqe._parse_recency_bounds("since 2020") == (2020, None)
    assert rqe._parse_recency_bounds("2018-2022") == (2018, 2022)
    assert rqe._parse_recency_bounds("recent work") == (None, None)


def test_parse_recency_from_x_to_y_is_closed_range():
    """The exact re-gate bug: 'from 2018 to 2022' matched only the 'from' (after) comparator and
    parsed to a bare lower bound (2018, None), dropping the 2022 ceiling. It must be a CLOSED
    range (2018, 2022). Cover the sibling range phrasings too."""
    assert rqe._parse_recency_bounds("from 2018 to 2022") == (2018, 2022)
    assert rqe._parse_recency_bounds("from 2018 through 2022") == (2018, 2022)
    assert rqe._parse_recency_bounds("between 2018 and 2022") == (2018, 2022)
    assert rqe._parse_recency_bounds("2018 to 2022") == (2018, 2022)
    # A genuine single-sided bound is unaffected (no second year => no range).
    assert rqe._parse_recency_bounds("from 2020") == (2020, None)


def test_from_x_to_y_range_demotes_out_of_window(monkeypatch):
    """End-to-end: a 'from 2018 to 2022' recency demotes rows OUTSIDE the closed window on BOTH
    sides (the pre-fix ceiling loss let a 2024 row through)."""
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    protocol = {"_rq_constraints": {"recency": "from 2018 to 2022"}}
    rows = [_row("lo", year=2017), _row("mid", year=2020), _row("hi", year=2024)]
    plan = rqe.build_rq_eligibility(protocol, rows)
    assert "lo" in plan.ineligible_urls   # 2017 < floor 2018
    assert "hi" in plan.ineligible_urls   # 2024 > ceiling 2022 (would have leaked pre-fix)
    assert "mid" not in plan.ineligible_urls


# ── #3: re-anchor same-fact / strictly-more-primary ──────────────────────────────────────────


def _ev(tier, *, doc="", doi="", text=""):
    return {"tier": tier, "document_type": doc, "doi": doi, "statement": text}


def test_reanchor_off_is_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_CITATION_REANCHOR_PRIMARY", raising=False)
    pool = {"a": _ev("T5", doc="NEWS"), "b": _ev("T1", doc="JOURNAL_ARTICLE", doi="10.1/x")}
    assert car.reanchor_citation(
        sentence="unemployment fell 3.2%", current_ev_id="a", evidence_pool=pool,
    ) == "a"


def test_reanchor_swaps_to_stronger_primary_same_numbers(monkeypatch):
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    pool = {
        "news": _ev("T5", doc="NEWS", text="unemployment fell 3.2% last year"),
        "journal": _ev("T1", doc="JOURNAL_ARTICLE", doi="10.1/x",
                        text="We estimate unemployment fell 3.2% over the period."),
    }
    out = car.reanchor_citation(
        sentence="unemployment fell 3.2%", current_ev_id="news", evidence_pool=pool,
    )
    assert out == "journal", "should re-anchor to the stronger PRIMARY sharing the same figure"


def test_reanchor_refuses_generic_stopword_overlap(monkeypatch):
    """The exact false-positive the re-gate found: an unrelated news row sharing only 'the'/'for'
    must NEVER be accepted as same-fact, even if it is a lower tier."""
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    pool = {
        "cur": _ev("T4", doc="JOURNAL_ARTICLE", doi="10.1/cur",
                   text="Inflation rose for the quarter."),
        "unrelated": _ev("T1", doc="NEWS",
                          text="The mayor spoke for the city about the parade."),
    }
    out = car.reanchor_citation(
        sentence="Inflation rose for the quarter.", current_ev_id="cur", evidence_pool=pool,
    )
    assert out == "cur", "generic stopword overlap ('the'/'for') must not re-anchor"


def test_reanchor_refuses_nonprimary_candidate(monkeypatch):
    """A lower-tier but NON-primary (news) candidate is never an eligible re-anchor target even
    when the fact matches — the candidate must itself be primary (genre or DOI)."""
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    pool = {
        "cur": _ev("T5", doc="BLOG_COMMENTARY", text="GDP grew 2.1% in the region."),
        "news": _ev("T1", doc="NEWS", text="GDP grew 2.1% in the region, officials said."),
    }
    out = car.reanchor_citation(
        sentence="GDP grew 2.1% in the region.", current_ev_id="cur", evidence_pool=pool,
    )
    assert out == "cur", "a non-primary (news) candidate must not be an anchor target"


def test_is_more_primary_requires_primary_candidate():
    news_hi = _ev("T1", doc="NEWS")
    journal_lo = _ev("T5", doc="JOURNAL_ARTICLE", doi="10.1/x")
    # A higher-tier NEWS row is NOT more-primary than a lower-tier journal (must itself be primary).
    assert car.is_more_primary(news_hi, journal_lo) is False


def test_reanchor_refuses_doi_bearing_news_candidate(monkeypatch):
    """A DOI alone is NOT primary: a DOI-bearing NEWS row (news outlets mint DOIs) must never be
    an eligible re-anchor target, even at a stronger tier and matching the fact."""
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    pool = {
        "cur": _ev("T5", doc="JOURNAL_ARTICLE", doi="10.1/cur",
                   text="Mortality dropped 4.5% in the cohort."),
        # stronger tier, same figure, carries a DOI — but it is NEWS, not a primary source:
        "news": _ev("T1", doc="NEWS", doi="10.9/news",
                    text="Mortality dropped 4.5% in the cohort, the paper reported."),
    }
    out = car.reanchor_citation(
        sentence="Mortality dropped 4.5% in the cohort.", current_ev_id="cur", evidence_pool=pool,
    )
    assert out == "cur", "a DOI-bearing NEWS candidate must not be treated as primary"


def test_is_more_primary_doi_alone_is_not_primary():
    news_doi = _ev("T1", doc="NEWS", doi="10.9/news")
    journal_lo = _ev("T5", doc="JOURNAL_ARTICLE", doi="10.1/x")
    # A higher-tier DOI-bearing NEWS row is NOT more-primary than a lower-tier journal.
    assert car.is_more_primary(news_doi, journal_lo) is False


def test_is_primary_source_rejects_contradictory_journal_sidecar():
    """A KNOWN non-primary genre is DECISIVE: a NEWS row carrying a contradictory
    ``is_journal_article=True`` sidecar must NOT be classed primary (the genre wins, checked first)."""
    row = {"tier": "T1", "document_type": "NEWS", "is_journal_article": True, "doi": "10.9/news"}
    assert car._is_primary_source(row) is False
    # and a genuine primary genre with the same sidecar is still primary:
    assert car._is_primary_source(
        {"tier": "T1", "document_type": "JOURNAL_ARTICLE", "is_journal_article": True}
    ) is True


def test_is_primary_source_unknown_genre_doi_is_not_primary():
    """An UNKNOWN/absent genre backed ONLY by a bare DOI is NOT primary — a positive primary signal
    (a primary genre or the is_journal_article sidecar) is required; a DOI alone is insufficient."""
    assert car._is_primary_source({"tier": "T2", "document_type": "UNKNOWN", "doi": "10.1/x"}) is False
    assert car._is_primary_source({"tier": "T2", "document_type": "", "doi": "10.1/x"}) is False
    # the sidecar (not the bare DOI) is what lifts an otherwise-unclassified row to primary:
    assert car._is_primary_source(
        {"tier": "T2", "document_type": "UNKNOWN", "is_journal_article": True}
    ) is True


def test_reanchor_refuses_unknown_genre_doi_candidate(monkeypatch):
    """End-to-end: an UNKNOWN-genre candidate whose only primary signal is a bare DOI must NOT be an
    eligible re-anchor target, even at a stronger tier and matching the same figure."""
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    pool = {
        "cur": _ev("T5", doc="JOURNAL_ARTICLE", doi="10.1/cur",
                   text="Emissions fell 6.7% over the decade."),
        # stronger tier, same figure, carries a DOI — but genre is UNKNOWN, so a bare DOI can't promote:
        "mystery": _ev("T1", doc="UNKNOWN", doi="10.9/mystery",
                       text="Emissions fell 6.7% over the decade, the dataset shows."),
    }
    out = car.reanchor_citation(
        sentence="Emissions fell 6.7% over the decade.", current_ev_id="cur", evidence_pool=pool,
    )
    assert out == "cur", "an unknown-genre DOI-only candidate must not be treated as primary"


def test_required_substring_matches_verifier_haystack_not_title(monkeypatch):
    """The required_substring guard must match the EXACT verifier haystack (direct_quote|statement),
    NOT the title. A candidate carrying the cited span ONLY in its title is rejected — it would fail
    downstream span resolution (the resolver never reads the title)."""
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    quote = "unemployment fell 3.2%"
    pool = {
        "news": _ev("T5", doc="NEWS", text=quote),
        # stronger primary, same figure, BUT carries the verbatim span only in its TITLE
        # (its statement/direct_quote paraphrases it) => the span resolver could not anchor it.
        "journal": {
            "tier": "T1", "document_type": "JOURNAL_ARTICLE", "doi": "10.1/x",
            "title": "unemployment fell 3.2% in the review",
            "statement": "a 3.2% decline in joblessness was estimated over the period",
        },
    }
    out = car.reanchor_citation(
        sentence=quote, current_ev_id="news", evidence_pool=pool, required_substring=quote,
    )
    assert out == "news", "span present only in the title must NOT satisfy the verifier-haystack guard"


def test_required_substring_guard_preserves_verification(monkeypatch):
    """The compose wiring passes the member's verbatim quote as required_substring; a candidate
    that does NOT contain it is rejected so the re-derived span still resolves (faithfulness)."""
    monkeypatch.setenv("PG_CITATION_REANCHOR_PRIMARY", "1")
    quote = "unemployment fell 3.2%"
    pool = {
        "news": _ev("T5", doc="NEWS", text=quote),
        # stronger primary, same number, but does NOT contain the verbatim quote span:
        "journal": _ev("T1", doc="JOURNAL_ARTICLE", doi="10.1/x",
                       text="a 3.2% decline in joblessness was observed"),
    }
    out = car.reanchor_citation(
        sentence=quote, current_ev_id="news", evidence_pool=pool, required_substring=quote,
    )
    assert out == "news", "no candidate contains the verbatim span => no swap (verify-safe)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
