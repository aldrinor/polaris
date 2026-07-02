"""I-deepfix-001 M2 — per-citation document-TYPE WEIGHT-and-DISCLOSE (deterministic, offline).

POLARIS has a CREDIBILITY axis (tier T1-T7, ``authority_score``, ``source_class``,
``predatory_oa``) but NO orthogonal document-TYPE axis. drb_72 asked for "high-quality,
English-language journal articles only," yet the cited corpus is dominated by on-topic
*wrong-genre* sources — arxiv preprints, an Amazon book, WEF/IZA/OECD reports, university
news blogs, BCG/McKinsey consultancy, and a predatory ``ewadirect`` proceedings venue that
*leads* the Corroborated Weighted Findings. There is no per-citation genre label anywhere;
the only existing genre mechanism (``journal_only_filter.py``) is a FILTER-AND-DROP +
``min_distinct_journals`` COUNT-floor that the operator REVERSED on 2026-06-07 and which
must stay dormant.

THIS module is the orthogonal WEIGHT axis, NOT a drop:
  * ``classify_document_type`` reads the OpenAlex genre signals POLARIS already computes
    (``openalex_publication_type`` / ``openalex_source_type`` / ``openalex_is_peer_reviewed``
    / ``predatory_oa``) plus a deterministic host/url fallback, and returns a per-citation
    ``DocumentType`` label + a short basis string. No LLM, no network, no row mutation.
  * ``DEFAULT_DOCUMENT_TYPE_WEIGHTS`` is a multiplicative ``(0, 1]`` SURFACE weight — a
    re-rank/disclosure multiplier, never a threshold/floor/cap. Every source still flows
    through; a misclassification is a visible label + softened display weight, never a
    lost source.
  * The whole path is gated by ``document_type_weighting_active`` — a DOUBLE gate
    (``PG_DOCUMENT_TYPE_WEIGHT=1`` AND the protocol's ``document_type_preference ==
    "journal_article"``). Default-OFF => byte-identical revert (LAW VI).

§-1.3 posture: WEIGHT-and-DISCLOSE, not FILTER-and-DROP. This module NEVER calls the
reversed ``journal_only`` DROP machinery (``journal_only_active`` / ``is_citeable_journal``
exclude branch / ``JournalOnlyLeakError`` / ``assert_no_leak`` / ``prune_contract_plans`` /
``min_distinct_journals``). The faithfulness engine (strict_verify / NLI / 4-role D8 /
span-grounding / provenance) is FROZEN and untouched — the document-type weight is advisory
disclosure of the SAME class as the existing ``credibility_weight`` and is read by NO
abort/approval/release gate.

The journal-POSITIVE test deliberately requires ``source_type == "journal"`` AND
peer-reviewed (NOT publication_type alone): the 2025 OPENBIB/QSS literature confirms
OpenAlex over-marks ~99% of works as "article," so type alone would mislabel preprints and
proceedings as journal articles. This is the same predicate the dormant ``is_citeable_journal``
already encodes, reused here as a WEIGHT signal rather than a drop filter.
"""
from __future__ import annotations

import os
from enum import Enum
from urllib.parse import urlsplit


class DocumentType(str, Enum):
    """Per-citation document GENRE — orthogonal to the T1-T7 credibility tier."""

    JOURNAL_ARTICLE = "JOURNAL_ARTICLE"
    REVIEW_ARTICLE = "REVIEW_ARTICLE"
    PREPRINT = "PREPRINT"
    CONFERENCE_PAPER = "CONFERENCE_PAPER"
    WORKING_PAPER = "WORKING_PAPER"
    BOOK = "BOOK"
    REPORT = "REPORT"
    NEWS = "NEWS"
    PRESS_RELEASE = "PRESS_RELEASE"
    BLOG_COMMENTARY = "BLOG_COMMENTARY"
    ENCYCLOPEDIA = "ENCYCLOPEDIA"
    DATASET = "DATASET"
    UGC = "UGC"
    PREDATORY_OA_JOURNAL = "PREDATORY_OA_JOURNAL"
    UNKNOWN = "UNKNOWN"


# ── Deterministic host/url heuristic fallback sets (LAW VI: module defaults; a protocol /
# config may extend them upstream, but these guarantee the offline classifier is never blank).
_PREPRINT_HOSTS = frozenset({
    "arxiv.org", "ssrn.com", "papers.ssrn.com", "osf.io", "psyarxiv.com",
    "researchgate.net", "biorxiv.org", "medrxiv.org",
})
_REPORT_HOSTS = frozenset({
    "weforum.org", "oecd.org", "ilo.org", "imf.org", "worldbank.org",
    "mckinsey.com", "bcg.com", "mercatus.org", "brookings.edu", "iza.org",
    "ftp.iza.org", "docs.iza.org",
})
_NEWS_HOSTS = frozenset({
    "reuters.com", "bloomberg.com", "ft.com", "nytimes.com", "wsj.com",
    "bbc.com", "economist.com",
})
_BLOG_PLATFORMS = frozenset({
    "medium.com", "substack.com", "wordpress.com", "blogspot.com",
})
_BOOK_HOSTS = frozenset({
    "amazon.com", "books.google.com",
})
_ENCYCLOPEDIA_HOSTS = frozenset({
    "wikipedia.org", "britannica.com",
})
# University news/blog surface markers (NOT a peer-reviewed journal); checked against the
# whole lowercased url, not just the host.
_UNI_NEWS_MARKERS = (".edu/20", "/news/", "/blog/")

# ── HIGH-PRECISION POSITIVE journal evidence (I-deepfix-001 fix h). Real peer-reviewed
# journals whose OpenAlex genre signal is ABSENT were mislabeled UNKNOWN ("not a peer-reviewed
# journal article"): JEP/AER (aeaweb.org, 10.1257), JPE (10.1086), QJE (10.1093/qje), Science
# (10.1126/science, science.org). This is a POSITIVE-evidence allowlist — it fires ONLY on
# affirmative journal evidence, NEVER on "not known-bad". §-1.3: LABEL/weight only; it never
# drops a non-journal source. High precision, fail-open on ambiguity.
#
# Pure-journal DOI registrants — the WHOLE registrant serves ONLY journals, never books, so the
# bare prefix is safe positive evidence:
_JOURNAL_DOI_REGISTRANT_PREFIXES = (
    "10.1257/",   # American Economic Association (AER, JEP, AEJ, AEA P&P) — journals only
    "10.1086/",   # University of Chicago Press JOURNALS (JPE, …); Press BOOKS use 10.7208, not this
)
# Path-scoped journal DOIs — the bare registrant ALSO serves books/reference works, so a
# journal-specific path segment is REQUIRED (bare 10.1093 is OUP-wide incl. books => NOT matched):
_JOURNAL_DOI_PATH_PREFIXES = (
    "10.1093/qje/",     # Quarterly Journal of Economics only (registrant 10.1093 also serves BOOKS)
    "10.1126/science",  # Science / Science-family journals (registrant 10.1126, "science…" slug)
)


def _host(url: str) -> str:
    """Lowercased registrable host of ``url`` (empty on a blank/garbage url). Pure, offline."""
    if not url:
        return ""
    try:
        netloc = urlsplit(str(url).strip()).netloc.lower()
    except Exception:
        return ""
    # strip credentials + port
    netloc = netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    return netloc


def _host_in(host: str, host_set: frozenset[str]) -> bool:
    """True iff ``host`` equals or is a sub-domain of any host in ``host_set``."""
    return any(host == h or host.endswith("." + h) for h in host_set)


def _doi_candidate(doi: str, low_url: str) -> str:
    """Best-effort lowercased bare DOI (``10.xxxx/…``) from the ``doi`` field or an embedded
    ``doi.org`` url. Empty when none is parseable. Pure, offline."""
    d = (doi or "").strip().lower()
    for pre in ("https://", "http://"):
        if d.startswith(pre):
            d = d[len(pre):]
    for pre in ("doi.org/", "dx.doi.org/"):
        if d.startswith(pre):
            d = d[len(pre):]
    if d.startswith("10."):
        return d
    marker = "doi.org/"
    idx = low_url.find(marker)
    if idx != -1:
        tail = low_url[idx + len(marker):]
        if tail.startswith("10."):
            return tail
    return ""


def _positive_journal_basis(doi: str, host: str, low_url: str) -> "str | None":
    """HIGH-PRECISION positive journal evidence (fix h) — returns a basis string iff there is
    AFFIRMATIVE evidence this is a peer-reviewed journal article, else ``None`` (fail-open).

    Never "not known-bad": a match requires a pure-journal DOI registrant, a path-scoped
    journal DOI, or a host+journal-path pattern. Registrants that ALSO serve books (bare
    10.1093 OUP, wiley, etc.) are NOT matched — they need the journal-specific path segment.
    """
    d = _doi_candidate(doi, low_url)
    if d:
        for pre in _JOURNAL_DOI_REGISTRANT_PREFIXES:
            if d.startswith(pre):
                return f"journal_doi_registrant:{pre.rstrip('/')}"
        for pre in _JOURNAL_DOI_PATH_PREFIXES:
            if d.startswith(pre):
                return f"journal_doi_path:{pre}"
    # Host + REQUIRED journal path/pattern (url-only cases with no parseable DOI field). Each
    # host also serves non-journal content, so a journal-specific path segment is mandatory.
    if _host_in(host, frozenset({"aeaweb.org"})) and (
        "/articles" in low_url or "/jep" in low_url or "/aer" in low_url or "/journals/" in low_url
    ):
        return "journal_host_path:aeaweb.org"
    if _host_in(host, frozenset({"science.org"})) and "/doi/10.1126/science" in low_url:
        return "journal_host_path:science.org"
    if _host_in(host, frozenset({"nature.com"})) and "/articles/s" in low_url:
        return "journal_host_path:nature.com"
    return None


def classify_document_type(
    *,
    openalex_publication_type: str = "",
    openalex_source_type: str = "",
    openalex_is_peer_reviewed: "bool | None" = None,
    predatory_oa: bool = False,
    source_class: str = "",
    url: str = "",
    title: str = "",
    doi: str = "",
) -> "tuple[DocumentType, str]":
    """Classify a source's document GENRE deterministically (no LLM, no network).

    Returns ``(DocumentType, basis)`` where ``basis`` is a short provenance string for audit.

    Priority:
      1. OpenAlex GOLD genre signals (require ``source_type == "journal"`` AND peer-reviewed
         for the journal-POSITIVE verdict — ``publication_type`` alone over-marks ~99% as
         "article", so type alone is NOT trusted). ``predatory_oa`` short-circuits a
         predatory venue BEFORE the journal verdict.
      2. ``source_class`` secondary (field-agnostic credibility class).
      3. Deterministic host/url fallback (when OpenAlex genre is absent).
    UNKNOWN (neutral weight) when nothing resolves — never punished, never dropped.
    """
    pt = (openalex_publication_type or "").strip().lower()
    st = (openalex_source_type or "").strip().lower()
    host = _host(url)

    # 1) OpenAlex GOLD signal.
    if predatory_oa and pt in ("article", "review"):
        return DocumentType.PREDATORY_OA_JOURNAL, f"oa_predatory:{pt}"
    if st == "journal" and openalex_is_peer_reviewed and pt == "review":
        return DocumentType.REVIEW_ARTICLE, "oa_journal_review"
    if st == "journal" and openalex_is_peer_reviewed and pt == "article":
        return DocumentType.JOURNAL_ARTICLE, "oa_journal_article"
    if pt == "preprint" or st == "repository":
        return DocumentType.PREPRINT, f"oa_preprint:{pt or st}"
    if pt in ("book", "book-chapter") or st in ("ebook platform", "book series"):
        return DocumentType.BOOK, f"oa_book:{pt or st}"
    if st == "conference" or pt == "proceedings-article":
        return DocumentType.CONFERENCE_PAPER, "oa_conference"
    if pt in ("report", "working-paper"):
        return DocumentType.REPORT, f"oa_report:{pt}"

    # 2) source_class secondary.
    sc = (source_class or "").strip().upper()
    if sc == "PRESS_RELEASE":
        return DocumentType.PRESS_RELEASE, "sourceclass_press"
    if sc == "UGC":
        return DocumentType.UGC, "sourceclass_ugc"

    # 3) deterministic host/url fallback.
    low_url = (url or "").lower()
    # 3a) HIGH-PRECISION positive journal evidence (fix h): a real peer-reviewed journal whose
    # OpenAlex genre signal was ABSENT (otherwise step 1 already labeled it). Requires POSITIVE
    # evidence (pure-journal DOI registrant / path-scoped journal DOI / host+journal-path),
    # never "not known-bad". Runs AFTER the step-1 negative genre signals (book/preprint/
    # conference/report), so an explicit book-chapter or preprint genre still wins over this.
    positive_basis = _positive_journal_basis(doi, host, low_url)
    if positive_basis is not None:
        return DocumentType.JOURNAL_ARTICLE, positive_basis
    if _host_in(host, _PREPRINT_HOSTS):
        return DocumentType.PREPRINT, f"host_preprint:{host}"
    if _host_in(host, _BOOK_HOSTS):
        return DocumentType.BOOK, f"host_book:{host}"
    if _host_in(host, _ENCYCLOPEDIA_HOSTS):
        return DocumentType.ENCYCLOPEDIA, f"host_encyclopedia:{host}"
    if _host_in(host, _REPORT_HOSTS):
        return DocumentType.REPORT, f"host_report:{host}"
    if _host_in(host, _NEWS_HOSTS):
        return DocumentType.NEWS, f"host_news:{host}"
    if _host_in(host, _BLOG_PLATFORMS) or any(m in low_url for m in _UNI_NEWS_MARKERS):
        return DocumentType.BLOG_COMMENTARY, "host_blog_or_uni_news"
    if sc == "PRIMARY_SCHOLARLY":
        return DocumentType.JOURNAL_ARTICLE, "sourceclass_scholarly_fallback"
    if sc == "COMMENTARY":
        return DocumentType.BLOG_COMMENTARY, "sourceclass_commentary"
    return DocumentType.UNKNOWN, "unresolved"


_PEER_REVIEWED_JOURNAL = frozenset({DocumentType.JOURNAL_ARTICLE, DocumentType.REVIEW_ARTICLE})


def is_peer_reviewed_journal_article(dt: "DocumentType") -> bool:
    """True only for a peer-reviewed journal/review article (the journal-only POSITIVE class)."""
    return dt in _PEER_REVIEWED_JOURNAL


# ── Multiplicative SURFACE weights in ``(0, 1]`` — a disclosure/re-rank multiplier, NOT a
# threshold/floor/cap. UNKNOWN carries a neutral 0.5 (never punished). LAW VI overridable.
DEFAULT_DOCUMENT_TYPE_WEIGHTS: dict[str, float] = {
    "JOURNAL_ARTICLE": 1.0,
    "REVIEW_ARTICLE": 1.0,
    "PREPRINT": 0.7,
    "WORKING_PAPER": 0.6,
    "CONFERENCE_PAPER": 0.7,
    "BOOK": 0.5,
    "REPORT": 0.5,
    "NEWS": 0.4,
    "PRESS_RELEASE": 0.35,
    "BLOG_COMMENTARY": 0.3,
    "ENCYCLOPEDIA": 0.25,
    "DATASET": 0.4,
    "UGC": 0.2,
    "PREDATORY_OA_JOURNAL": 0.25,
    "UNKNOWN": 0.5,
}

JOURNAL_DOC_WEIGHT_FLAG = "PG_DOCUMENT_TYPE_WEIGHT"


def _flag_on() -> bool:
    """The ``PG_DOCUMENT_TYPE_WEIGHT`` leg of the double gate (default OFF)."""
    return os.getenv(JOURNAL_DOC_WEIGHT_FLAG, "0").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def document_type_weighting_active(protocol: "dict | None") -> bool:
    """DOUBLE gate: ``PG_DOCUMENT_TYPE_WEIGHT`` flag ON AND the protocol declares
    ``document_type_preference: journal_article``. Both must hold => byte-identical OFF.

    ``protocol`` is the RAW scope-template dict (it carries ``document_type_preference``;
    the serialized ``ProtocolDocument`` drops fixed-field-unknown keys, so callers pass the
    raw template — same pattern as the journal_only config read).
    """
    if not _flag_on():
        return False
    if not protocol:
        return False
    pref = str((protocol or {}).get("document_type_preference") or "").strip().lower()
    return pref == "journal_article"


def resolve_document_type_weight(dt: "DocumentType", protocol: "dict | None") -> float:
    """The multiplicative document-type weight for ``dt`` — protocol override else module default.

    The protocol's ``document_type_weights`` keys may be lower-case (YAML convention,
    e.g. ``journal_article``) while ``DocumentType.value`` is upper-case, so override keys
    are normalized to upper-case before lookup. Always returns a finite ``(0, 1]`` float.
    """
    overrides = (protocol or {}).get("document_type_weights") or {}
    norm = {}
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            try:
                norm[str(k).strip().upper()] = float(v)
            except (TypeError, ValueError):
                continue
    key = dt.value
    if key in norm:
        return norm[key]
    return float(DEFAULT_DOCUMENT_TYPE_WEIGHTS.get(key, DEFAULT_DOCUMENT_TYPE_WEIGHTS["UNKNOWN"]))
