"""Generic offline classifiers for retrieval-time citation eligibility."""
from __future__ import annotations

import re
from typing import Mapping
from urllib.parse import urlsplit

from src.polaris_graph.retrieval.rq_eligibility import detect_language_offline

# These are publication-surface classes, not journal-name allowlists.  They are deliberately
# conservative: a known repository/working-paper/news/blog surface vetoes every positive signal.
_PREPRINT_OR_WORKING_PAPER_HOSTS = frozenset({
    "arxiv.org", "ssrn.com", "nber.org", "preprints.org", "researchsquare.com",
    "biorxiv.org", "medrxiv.org", "osf.io", "psyarxiv.com", "researchgate.net",
    "academia.edu",
})
_NON_JOURNAL_HOSTS = _PREPRINT_OR_WORKING_PAPER_HOSTS | frozenset({
    "medium.com", "substack.com", "wordpress.com", "blogspot.com",
})
_NON_JOURNAL_DOI_REGISTRANTS = frozenset({
    "10.1101",   # bioRxiv / medRxiv
    "10.17605",  # OSF
    "10.2139",   # SSRN
    "10.3386",   # NBER working papers
    "10.48550",  # arXiv
    "10.5061",   # Dryad datasets
    "10.5281",   # Zenodo repository records
    "10.6084",   # Figshare repository records
    "10.7910",   # Dataverse datasets
})
_MIXED_PUBLICATION_DOI_REGISTRANTS = frozenset({
    "10.1109",
    "10.1145",
})
_NON_JOURNAL_TEXT_RE = re.compile(
    r"\b(?:pre[ -]?print|working[ -]?paper|discussion[ -]?paper|policy[ -]?brief|"
    r"conference|proceedings|press[ -]?release|government[ -]?report|"
    r"white[ -]?paper|news(?:letter)?|blog)\b",
    re.IGNORECASE,
)
_CHROME_TITLE_RE = re.compile(
    r"^(?:just a moment|error\b|access denied|page not found|cookies? (?:are )?(?:disabled|turned off))",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"\b(10\.\d{4,9})/[\w.()/:+-]+", re.IGNORECASE)

# Generic article-route shapes used by journal platforms.  No venue or task names are encoded.
_JOURNAL_ARTICLE_URL_RES = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"/articles/pmc\d+/?$",
    r"/science/article/pii/",
    r"/journals?/[^?#]*/articles?/",
    r"/article/10\.\d{4,9}/",
    r"/doi/(?:abs/|full/|pdf/|epdf/)?10\.\d{4,9}/",
    r"/core/journals/[^/]+/article/",
    r"/(?:ojs/)?index\.php/[^/]+/article/(?:view|download)/",
    r"/article/\d+/\d+/",
    r"/article/(?:view|download)/\d+",
    r"/content/\d+/\d+/",
))
_JOURNAL_HOST_LABEL_RE = re.compile(r"^(?:journal|journals)[.-]", re.IGNORECASE)
_JOURNAL_VENUE_RE = re.compile(r"\b(?:journal|review|quarterly)\b", re.IGNORECASE)
_VOLUME_ISSUE_RE = re.compile(
    r"\b(?:vol(?:ume)?\.?\s*\d+\s*[,;:]?\s*(?:no\.?|issue)\s*\d+|\d+\s*\(\s*\d+\s*\))\b",
    re.IGNORECASE,
)


def _host(row: Mapping[str, object]) -> str:
    url = str(row.get("source_url") or row.get("url") or "")
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _host_in(host: str, choices: frozenset[str]) -> bool:
    return any(host == item or host.endswith("." + item) for item in choices)


def known_non_journal_surface(row: Mapping[str, object]) -> bool:
    """Return True only for an affirmative offline non-journal surface signal."""
    host = _host(row)
    if _host_in(host, _NON_JOURNAL_HOSTS):
        return True
    text = " ".join(str(row.get(key) or "") for key in (
        "title", "source_url", "url", "source_class", "document_type",
    ))
    text_signal = bool(_NON_JOURNAL_TEXT_RE.search(text))
    if text_signal:
        return True
    doi_match = _DOI_RE.search(" ".join(str(row.get(key) or "") for key in (
        "doi", "source_url", "url",
    )))
    if not doi_match:
        return False
    registrant = doi_match.group(1).lower()
    if registrant in _NON_JOURNAL_DOI_REGISTRANTS:
        return True
    # Mixed registrants publish both journal articles and proceedings. Their
    # prefix is never a veto by itself; only the independent host/text checks
    # above may establish that this manifestation is non-journal.
    if registrant in _MIXED_PUBLICATION_DOI_REGISTRANTS:
        return False
    return False


def known_preprint_or_working_paper_host(row: Mapping[str, object]) -> bool:
    """Return True for a recognized preprint/repository/working-paper hostname."""
    return _host_in(_host(row), _PREPRINT_OR_WORKING_PAPER_HOSTS)


def _unknown_row_has_journal_signal(row: Mapping[str, object]) -> bool:
    """Conservative positive classifier for otherwise-UNKNOWN rows; pure and offline."""
    if known_non_journal_surface(row):
        return False
    title = str(row.get("title") or "").strip()
    if not title or _CHROME_TITLE_RE.search(title):
        return False
    url = str(row.get("source_url") or row.get("url") or "")
    host = _host(row)

    # A resolvable DOI is affirmative publication metadata unless its registrant/surface is one of
    # the explicit repository and working-paper classes vetoed above.
    if _DOI_RE.search(" ".join((str(row.get("doi") or ""), url))):
        return True
    if any(pattern.search(url) for pattern in _JOURNAL_ARTICLE_URL_RES):
        return True
    if _JOURNAL_HOST_LABEL_RE.search(host + ".") and "/article" in url.lower():
        return True

    venue = " ".join(str(row.get(key) or "") for key in ("journal", "venue"))
    publication = " ".join((title, venue, str(row.get("citation") or "")))
    return bool(
        _JOURNAL_VENUE_RE.search(venue)
        and _VOLUME_ISSUE_RE.search(publication)
    )
