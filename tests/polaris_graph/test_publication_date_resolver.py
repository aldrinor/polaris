"""I-deepfix-001 FF5 — publication_date_resolver cascade unit tests.

RED before the build: the module did not exist, so a post-window web source (e.g. the
St Louis Fed 2025 page in the drb_72 corpus) was NOT date-resolvable from its fetched
HTML — it arrived UNDATED and fail-opened straight into the grounding set under a HARD
"published before June 2023" bound. GREEN after: the htmldate-style cascade resolves a
month-precision publication date from the ALREADY-fetched content, with ZERO network.

Each test exercises ONE cascade rung on an inline fixture (no network). The headline
case is the exact FF5-brief GREEN-A: a JSON-LD ``datePublished`` of ``2025-03-01``
resolves to ``("2025-03", 2025)``.

FF5-v2 (this revision) adds two Codex-found corrections and their RED/GREEN tests:
  * ``_YM_SEPARATED_RE`` now requires a right boundary after the 1-2 month digits, so an
    over-long token like ``2023-123`` degrades to honest YEAR precision (``2023``)
    instead of over-resolving to a bogus ``2023-12`` (which could wrongly mask an
    in-window source under a "before June 2023" bound).
  * a ``search_metadata`` cascade rung recovers the leaked ``openalex.org`` 2026 row
    whose ``metadata['year']`` the OpenAlex-authority enrich path had discarded.

Faithfulness-neutral: this module only produces fetch-time provenance metadata; it never
touches strict_verify / NLI / D8 / provenance span-grounding.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.publication_date_resolver import (
    resolve_publication_date,
)


# ── headline RED/GREEN: the surviving-defect St Louis Fed 2025 post-window source ──────
def test_jsonld_datepublished_resolves_month_precision():
    """FF5 GREEN-A: JSON-LD datePublished 2025-03-01 => ("2025-03", 2025) (day dropped,
    month precision matches the downstream timeline gate)."""
    raw_html = (
        '<html><head>'
        '<script type="application/ld+json">'
        '{"@type":"NewsArticle","headline":"St Louis Fed 2025 report",'
        '"datePublished":"2025-03-01"}'
        '</script></head><body>...</body></html>'
    )
    iso, year = resolve_publication_date(
        raw_html=raw_html, jsonld="", url="https://stlouisfed.org/2025-report", pdf_meta=None
    )
    assert iso == "2025-03"
    assert year == 2025


def test_jsonld_from_extracted_jsonld_param():
    """The caller may pass the pre-extracted JSON-LD (the _extract_jsonld_blocks output)
    instead of raw HTML — both paths resolve identically."""
    jsonld = '{"@type":"Article","datePublished":"2023-05-11T09:00:00Z"}'
    iso, year = resolve_publication_date(
        raw_html="", jsonld=jsonld, url="https://example.org/x", pdf_meta=None
    )
    assert iso == "2023-05"
    assert year == 2023


def test_jsonld_datecreated_fallback_when_no_datepublished():
    jsonld = '{"@type":"Article","dateCreated":"2021-08-01"}'
    iso, year = resolve_publication_date(raw_html="", jsonld=jsonld, url="", pdf_meta=None)
    assert iso == "2021-08"
    assert year == 2021


def test_jsonld_nested_graph_array():
    """datePublished nested inside an @graph array must still be found (raw-string scan,
    not a strict single-object json.loads)."""
    jsonld = (
        '{"@context":"https://schema.org","@graph":['
        '{"@type":"WebSite","name":"x"},'
        '{"@type":"Article","datePublished":"2019-12-15"}]}'
    )
    iso, year = resolve_publication_date(raw_html="", jsonld=jsonld, url="", pdf_meta=None)
    assert iso == "2019-12"
    assert year == 2019


# ── cascade rung 2: meta tags (OpenGraph / citation / Dublin Core / PRISM) ─────────────
def test_meta_article_published_time():
    raw_html = '<meta property="article:published_time" content="2022-06-30T00:00:00Z">'
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2022-06"
    assert year == 2022


def test_meta_citation_publication_date_slash_format():
    raw_html = '<meta name="citation_publication_date" content="2020/11/02">'
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2020-11"
    assert year == 2020


def test_meta_dc_date_issued_and_prism():
    for raw_html, expect in (
        ('<meta name="DC.date.issued" content="2018-04">', ("2018-04", 2018)),
        ('<meta name="prism.publicationDate" content="2017-09-01">', ("2017-09", 2017)),
    ):
        iso, year = resolve_publication_date(
            raw_html=raw_html, jsonld="", url="", pdf_meta=None
        )
        assert (iso, year) == expect


def test_meta_attribute_order_independent():
    """content= before name= must still parse."""
    raw_html = '<meta content="2016-02-14" name="citation_date">'
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2016-02"
    assert year == 2016


# ── cascade rung 3: microdata itemprop="datePublished" ────────────────────────────────
def test_microdata_time_itemprop_datetime():
    raw_html = '<time itemprop="datePublished" datetime="2015-07-20">July 20, 2015</time>'
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2015-07"
    assert year == 2015


def test_microdata_span_inner_text():
    raw_html = '<span itemprop="datePublished">2014-03-09</span>'
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2014-03"
    assert year == 2014


# ── cascade rung 4: <time datetime=...> ───────────────────────────────────────────────
def test_time_element_datetime():
    raw_html = '<article><time datetime="2013-10-05T12:00:00+00:00">Oct 2013</time></article>'
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2013-10"
    assert year == 2013


# ── cascade rung 5: structured search-result metadata (OpenAlex cand.metadata) ────────
def test_search_metadata_openalex_year_recovered_ff5v2():
    """FF5-v2 GREEN: the leaked openalex.org 2026 row [12] — the OpenAlex search carried
    metadata['year']=2026 but the authority-enrich path discarded it, so the row reached
    the timeline gate UNDATED and fail-opened. The new search_metadata rung recovers it at
    year precision (RED pre-v2: the resolver had no search_metadata parameter/rung, so the
    2026 year could not be recovered and the row stayed undated)."""
    iso, year = resolve_publication_date(
        raw_html="",
        jsonld="",
        url="https://openalex.org/W1234",
        pdf_meta=None,
        search_metadata={"year": 2026},
    )
    assert iso == "2026"
    assert year == 2026


def test_search_metadata_publication_date_month_precision():
    """A structured publication_date in the search metadata resolves at month precision."""
    iso, year = resolve_publication_date(
        raw_html="", jsonld="", url="", pdf_meta=None,
        search_metadata={"publication_date": "2021-04-18"},
    )
    assert iso == "2021-04"
    assert year == 2021


def test_html_structured_date_wins_over_search_metadata_year():
    """Precedence: the publisher's own HTML structured date (month precision) is NOT
    coarsened by a competing year-only search-metadata signal — JSON-LD ranks above the
    search_metadata rung."""
    raw_html = (
        '<script type="application/ld+json">{"datePublished":"2023-03-01"}</script>'
    )
    iso, year = resolve_publication_date(
        raw_html=raw_html, jsonld="", url="", pdf_meta=None,
        search_metadata={"year": 2023},
    )
    assert iso == "2023-03"
    assert year == 2023


def test_search_metadata_ranks_above_url_and_pdf_heuristics():
    """The structured API year is preferred over the weaker URL-slug / PDF-creation
    heuristics (a URL date-slug that disagrees must not override the API metadata)."""
    iso, year = resolve_publication_date(
        raw_html="",
        jsonld="",
        url="https://example.org/2011/09/some-post",
        pdf_meta={"CreationDate": "D:20090101000000"},
        search_metadata={"publication_year": 2022},
    )
    assert iso == "2022"
    assert year == 2022


# ── cascade rung 6: URL /YYYY/MM/ ─────────────────────────────────────────────────────
def test_url_year_month_path():
    iso, year = resolve_publication_date(
        raw_html="", jsonld="", url="https://blog.example.com/2012/08/15/some-post", pdf_meta=None
    )
    assert iso == "2012-08"
    assert year == 2012


def test_url_year_month_no_day():
    iso, year = resolve_publication_date(
        raw_html="", jsonld="", url="https://news.example.org/2011/04/story.html", pdf_meta=None
    )
    assert iso == "2011-04"
    assert year == 2011


# ── cascade rung 7: PDF /CreationDate ─────────────────────────────────────────────────
def test_pdf_creationdate():
    iso, year = resolve_publication_date(
        raw_html="", jsonld="", url="https://example.org/paper.pdf",
        pdf_meta={"CreationDate": "D:20100615120000+00'00'"},
    )
    assert iso == "2010-06"
    assert year == 2010


# ── precedence: JSON-LD wins over a competing meta tag ────────────────────────────────
def test_precedence_jsonld_over_meta():
    raw_html = (
        '<meta property="article:published_time" content="2001-01-01">'
        '<script type="application/ld+json">{"datePublished":"2025-03-01"}</script>'
    )
    iso, year = resolve_publication_date(raw_html=raw_html, jsonld="", url="", pdf_meta=None)
    assert iso == "2025-03"
    assert year == 2025


# ── FF5-v2 RED/GREEN: malformed over-long month token must degrade, not over-resolve ──
def test_overlong_month_token_degrades_to_year_precision_ff5v2():
    """FF5-v2 GREEN: a malformed over-long month token like ``2023-123`` must degrade to
    honest YEAR precision (``("2023", 2023)``), NOT over-resolve to ``("2023-12", 2023)``.

    RED (pre-v2): ``_YM_SEPARATED_RE = ^\\s*(\\d{4})[-/.](\\d{1,2})`` grabbed the first two
    month digits with no right boundary, so ``2023-123`` resolved to month 12 — a bogus
    in-window date that could wrongly MASK an in-window source under a HARD
    "before June 2023" bound. The ``(?!\\d)`` right boundary fixes it deterministically.
    """
    for raw_val, expect in (
        ("2023-123", ("2023", 2023)),   # 3-digit month field → degrade to year
        ("2023-1234", ("2023", 2023)),  # 4-digit month field → degrade to year
        ("2020-050", ("2020", 2020)),   # over-long even with a leading zero
    ):
        jsonld = '{"datePublished":"' + raw_val + '"}'
        iso, year = resolve_publication_date(raw_html="", jsonld=jsonld, url="", pdf_meta=None)
        assert (iso, year) == expect, f"{raw_val!r} should degrade to {expect}, got {(iso, year)}"


def test_valid_two_digit_month_still_month_precision_after_ff5v2():
    """Regression guard for the FF5-v2 right boundary: a legitimate 1-2 digit month
    followed by a real separator (a day) or end-of-token still resolves at month
    precision — the ``(?!\\d)`` only rejects a THIRD glued digit."""
    for raw_val, expect in (
        ("2023-05-01", ("2023-05", 2023)),  # month then '-day' → month precision kept
        ("2023-5", ("2023-05", 2023)),      # single-digit month, no day → month precision
        ("2020/11/02", ("2020-11", 2020)),  # slash separators, day present
    ):
        jsonld = '{"datePublished":"' + raw_val + '"}'
        iso, year = resolve_publication_date(raw_html="", jsonld=jsonld, url="", pdf_meta=None)
        assert (iso, year) == expect, f"{raw_val!r} should keep {expect}, got {(iso, year)}"


# ── honest-undated: no structured signal => (None, None), NOT a guess ─────────────────
def test_unresolved_returns_none_no_guess():
    """A plain web page with no structured date (only body prose that MENTIONS a year)
    stays honestly UNDATED — the resolver never body-heuristic-guesses."""
    raw_html = "<html><body><p>Copyright 2024. Updated recently. Some text about 2023.</p></body></html>"
    iso, year = resolve_publication_date(
        raw_html=raw_html, jsonld="", url="https://example.org/about", pdf_meta=None
    )
    assert iso is None
    assert year is None


def test_empty_inputs_return_none():
    assert resolve_publication_date(raw_html="", jsonld="", url="", pdf_meta=None) == (None, None)
    assert resolve_publication_date(
        raw_html=None, jsonld=None, url=None, pdf_meta=None
    ) == (None, None)
    # An empty / non-dict search_metadata must not raise and must stay undated.
    assert resolve_publication_date(
        raw_html="", jsonld="", url="", pdf_meta=None, search_metadata={}
    ) == (None, None)
    assert resolve_publication_date(
        raw_html="", jsonld="", url="", pdf_meta=None, search_metadata={"year": None}
    ) == (None, None)


# ── year-bound guard: reject implausible years (1900..2100) ───────────────────────────
def test_out_of_band_year_rejected():
    raw_html = '<script type="application/ld+json">{"datePublished":"1823-05-01"}</script>'
    assert resolve_publication_date(
        raw_html=raw_html, jsonld="", url="", pdf_meta=None
    ) == (None, None)


def test_malformed_month_degrades_to_year_precision():
    """A malformed month (e.g. 2023-99) must NOT be dropped wholesale — the valid year
    is kept at year precision (honest, never a guess)."""
    jsonld = '{"datePublished":"2023-99-01"}'
    iso, year = resolve_publication_date(raw_html="", jsonld=jsonld, url="", pdf_meta=None)
    assert iso == "2023"
    assert year == 2023
