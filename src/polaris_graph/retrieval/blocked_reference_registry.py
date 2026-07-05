"""Per-WORK blocked-reference deny-list (I-deepfix-001 B2, GH #1346).

THE ONE legitimate HARD DROP in the pipeline (CLAUDE.md §-1.3). Everything else in
POLARIS is WEIGHT-and-CONSOLIDATE — a source is never dropped to hit a number. This
module is the single exception, and ONLY because the drop is an EXPLICIT OPERATOR
PROHIBITION: a DeepResearch-Bench-II research question can carry a trailing
"do-not-view / blocked references" appendix ("...you are not allowed to view the
following article and urls: {...}. ...do not quote it."). That appendix names a
specific paper (e.g. the Salari et al. "Impacts of generative artificial intelligence
on the future of labor market" systematic review, DOI 10.1016/j.chbr.2025.100652,
PII S2451958825000673) that the report must NOT view or cite. This is a prohibition,
NOT a relevance / credibility / tier call.

Without this deny-list the prohibition is never parsed, so the blocked paper is
queried across ~6 mirrors (sciencedirect/linkinghub PII, herts researchprofiles,
uhra handle, doaj, scilit, doi.org), fetched OK, tiered T1/T2, selected into
evidence_for_gen, corpus-approved, and CITED — containment is pure luck.

The registry holds FOUR OR'd normalized key-sets, each an independent matching leg so
a mirror that is NOT literally in the appendix still gets caught:

* ``canonical_urls`` — every URL in the appendix, normalized via ``w3lib.url`` (scheme/
  www/query/fragment/trailing-slash stripped, percent-normalized) so case/scheme/query
  variants of a listed mirror match.
* ``dois`` — Crossref-canonical DOIs (lowercased, ``https?://`` / ``dx.``/``doi.org/`` /
  ``doi:`` prefixes stripped). Catches the ``doi.org`` mirror even when it is not the
  exact URL listed.
* ``publisher_piis`` — Elsevier PII (``S\\d{16}[\\dX]?``) + arXiv ids, INCLUDING the PII
  embedded inside sciencedirect / linkinghub URLs. Catches the ``linkinghub`` mirror
  (a different URL carrying the SAME PII) even when it is not in the appendix.
* ``title_keys`` — normalized-title fuzzy match (>= ``TITLE_FUZZY_THRESHOLD``). Catches a
  mirror (semanticscholar, an institutional repository, etc.) by the fetched page TITLE
  when its URL carries neither the listed URL, the DOI, nor the PII. HIGH threshold so a
  legitimate same-topic-different-paper is NOT over-blocked.

Pure / no network. FAIL-OPEN on any build error (a malformed question must never crash
the run — the registry is then empty and ``is_blocked`` is always ``(False, "")``).

Kill-switch ``PG_BLOCKED_REFERENCE_DENYLIST`` (default ON). OFF => the registry is empty
and every wired seam is byte-identical to the pre-B2 behaviour.

The faithfulness engine (strict_verify / NLI / 4-role / provenance / span-grounding) is
NEVER touched by this module.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.polaris_graph.retrieval.injection_appendix import locate_injected_appendix

logger = logging.getLogger("polaris_graph.blocked_reference_registry")

# --- canonical-URL normalization (w3lib, BSD; already a project dependency) -----------
try:  # pragma: no cover - import shim
    from w3lib.url import canonicalize_url as _canonicalize_url
except Exception:  # pragma: no cover - w3lib absent (should not happen; it is installed)
    _canonicalize_url = None  # type: ignore[assignment]

# --- title fuzzy backend: rapidfuzz if importable, else stdlib difflib ----------------
try:  # pragma: no cover - import shim
    from rapidfuzz import fuzz as _rapidfuzz_fuzz
except Exception:  # pragma: no cover - rapidfuzz optional
    _rapidfuzz_fuzz = None  # type: ignore[assignment]

import difflib  # noqa: E402 - stdlib fallback for the fuzzy title leg

# --- named constants (LAW VI: no magic numbers) ---------------------------------------
_DENYLIST_FLAG = "PG_BLOCKED_REFERENCE_DENYLIST"
_OFF_TOKENS = frozenset({"0", "false", "no", "off", "disabled", ""})
# Title fuzzy floor. HIGH (>= 0.92) so a same-topic but DIFFERENT paper is not blocked;
# a true mirror of the blocked paper carries the same title and scores ~1.0.
TITLE_FUZZY_THRESHOLD = 0.92

# --- extraction regexes ---------------------------------------------------------------
# A URL token inside the appendix (stops at whitespace and the dict/list delimiters the
# DRB-II appendix uses: quotes, < > ( ) [ ] { }).
_URL_RE = re.compile(r"https?://[^\s'\"<>)\]}]+", re.IGNORECASE)
# A Crossref DOI (``10.<registrant>/<suffix>``); suffix stops at the same delimiters.
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s'\"<>)\]}]+", re.IGNORECASE)
# Elsevier PII: ``S`` + 16 digits + an optional check char (digit or X).
_ELSEVIER_PII_RE = re.compile(r"S\d{16}[\dX]?", re.IGNORECASE)
# arXiv id (new-style ``NNNN.NNNNN`` optionally ``vN``), only in an explicit arXiv context
# so a bare numeric token is never mistaken for an arXiv id.
_ARXIV_RE = re.compile(r"arxiv(?:\.org/abs/|\s*:\s*)(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
# The labelled ``'title': '...'`` field of the appendix dict literal.
_TITLE_FIELD_RE = re.compile(r"""['"]title['"]\s*:\s*['"]([^'"]+)['"]""", re.IGNORECASE)
# The labelled ``'authors': [...]`` / ``'author': '...'`` field of the appendix dict literal.
_AUTHORS_FIELD_RE = re.compile(
    r"""['"]authors?['"]\s*:\s*(\[[^\]]*\]|['"][^'"]+['"])""", re.IGNORECASE
)
_QUOTED_STR_RE = re.compile(r"""['"]([^'"]+)['"]""")

# --- DOAJ-id identity leg (I-deepfix-001 P0-1) ----------------------------------------
# A DOAJ article id is a 32-hex token. It appears (a) inside a doaj.org/article/<id> URL,
# (b) as an explicit ``'doaj_id'`` metadata field / ``DOAJ id: <id>`` mention, and (c) —
# crucially — inside a MIRROR repository URL path (library.kab.ac.ug/.../items/<id>). The
# BUILD side (registry construction) is CONSERVATIVE: it registers a 32-hex only from an
# explicit doaj.org/article URL or a labelled doaj_id field, so a random hex token in the
# appendix is never mistaken for a blocked id. The MATCH side (a candidate under test) is
# PERMISSIVE: it grabs any 32-hex from the candidate URL/metadata, which is safe because a
# hit only fires when that id is in the (conservatively-built) registry set.
_DOAJ_ARTICLE_RE = re.compile(r"doaj\.org/article/([0-9a-f]{32})", re.IGNORECASE)
_DOAJ_ID_FIELD_RE = re.compile(
    r"""doaj[_\s]?id['"\s:]+([0-9a-f]{32})""", re.IGNORECASE
)
_HEX32_RE = re.compile(r"[0-9a-f]{32}", re.IGNORECASE)
_BARE_HEX32_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_SURNAME_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_doaj_id(value: str) -> str:
    """Canonical (lowercased) DOAJ article id from a URL, a ``doaj.org/article/<id>``
    link, or a bare 32-hex metadata value. Empty when none is parseable. Never raises."""
    if not value:
        return ""
    v = str(value).strip().lower()
    if not v:
        return ""
    m = _DOAJ_ARTICLE_RE.search(v)
    if m:
        return m.group(1).lower()
    if _BARE_HEX32_RE.match(v):
        return v
    return ""


def _extract_doaj_id_candidates(url: str) -> set[str]:
    """MATCH-side DOAJ ids from a candidate URL: the explicit doaj.org/article id AND any
    32-hex segment in the path (a mirror repository id). Permissive on purpose — a hit only
    fires against the conservatively-built registry set. Never raises ('' on bad input)."""
    out: set[str] = set()
    if not url:
        return out
    low = str(url).strip().lower()
    m = _DOAJ_ARTICLE_RE.search(low)
    if m:
        out.add(m.group(1).lower())
    for tok in _HEX32_RE.findall(low):
        out.add(tok.lower())
    return out


def _first_author_surname(authors: "Any") -> str:
    """Order-robust surname of the FIRST author. Handles a list of author strings or a
    single string, and both ``'Surname, Given'`` and ``'Given Surname'`` name orders.
    Empty when no author is parseable. Never raises."""
    first = ""
    if isinstance(authors, (list, tuple)):
        for a in authors:
            if a is not None and str(a).strip():
                first = str(a).strip()
                break
    elif authors is not None:
        first = str(authors).strip()
    if not first:
        return ""
    if "," in first:
        surname = first.split(",", 1)[0]
    else:
        parts = first.split()
        surname = parts[-1] if parts else ""
    return _SURNAME_ALNUM_RE.sub("", surname.lower()).strip()


def _title_author_hash(title: str, authors: "Any") -> str:
    """Stable identity key from a normalized title + the first-author surname. Empty when
    either component is missing (so the leg never over-blocks on title-only or author-only
    input). Surname-based + order-robust so ``'Salari, Amirreza'`` and ``'Amirreza Salari'``
    hash identically. Never raises."""
    nt = _normalize_title(title)
    sn = _first_author_surname(authors)
    if not nt or not sn:
        return ""
    return hashlib.sha1(f"{nt}|{sn}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceIdentity:
    """The normalized identity legs of ONE candidate source, extracted once and reused by
    the fetch / selection / claim-level seams. Every field is empty when absent (fail-open)."""

    doi: str = ""
    doaj_id: str = ""
    title_author_hash: str = ""
    host: str = ""


def _candidate_field(candidate: "Any", *names: str) -> "Any":
    """First present, non-None value across the given field names (dict OR object)."""
    if isinstance(candidate, Mapping):
        for n in names:
            if n in candidate and candidate.get(n) is not None:
                return candidate.get(n)
        return None
    for n in names:
        v = getattr(candidate, n, None)
        if v is not None:
            return v
    return None


def extract_source_identity(candidate: "Any") -> SourceIdentity:
    """Normalize a candidate source (dict OR object) to its identity legs.

    Reuses the module normalizers (``_normalize_doi`` / ``_normalize_url``) plus the DOAJ +
    title-author legs. The DOAJ id is recovered from an explicit ``doaj_id`` field, a
    doaj.org URL, OR any 32-hex segment of the candidate URL path (so a mirror repository
    URL that carries the id is caught). Pure / offline; never raises."""
    url = str(_candidate_field(candidate, "url", "source_url") or "")
    doi_raw = str(_candidate_field(candidate, "doi") or "")
    title = str(_candidate_field(candidate, "title") or "")
    authors = _candidate_field(candidate, "authors", "author")
    doaj_field = str(_candidate_field(candidate, "doaj_id") or "")

    doaj_id = _normalize_doaj_id(doaj_field)
    if not doaj_id:
        _cands = _extract_doaj_id_candidates(url)
        doaj_id = next(iter(sorted(_cands)), "") if _cands else ""
    return SourceIdentity(
        doi=_normalize_doi(doi_raw) or next(iter(sorted(_extract_dois(url))), ""),
        doaj_id=doaj_id,
        title_author_hash=_title_author_hash(title, authors),
        host=_host_of(url),
    )


def _host_of(url: str) -> str:
    """Lowercased host of ``url`` (empty on blank/garbage). Local, no external dep."""
    if not url:
        return ""
    try:
        from urllib.parse import urlsplit  # noqa: PLC0415

        netloc = urlsplit(str(url).strip()).netloc.lower()
        return netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    except Exception:  # noqa: BLE001 - never raise on a garbage url
        return ""


def is_blocked_source(candidate: "Any", registry: "BlockedRegistry | None") -> tuple[bool, str]:
    """Whole-candidate blocked check: extract every identity leg (url / doi / pii / doaj /
    title+author) from ``candidate`` (dict OR object) and match it against ``registry``.

    ``(False, "")`` on an empty/None registry (byte-identical no-op). Pure; never raises —
    a bad candidate is treated as not-blocked (fail-open) so it can never abort a run."""
    if registry is None or registry.is_empty:
        return (False, "")
    try:
        url = str(_candidate_field(candidate, "url", "source_url") or "")
        doi = str(_candidate_field(candidate, "doi") or "")
        title = str(_candidate_field(candidate, "title") or "")
        authors = _candidate_field(candidate, "authors", "author")
        doaj_id = str(_candidate_field(candidate, "doaj_id") or "")
        return registry.is_blocked(
            url=url, doi=doi, title=title, doaj_id=doaj_id, authors=authors
        )
    except Exception:  # noqa: BLE001 - fail-open: a bad candidate is never blocked-by-error
        return (False, "")

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)
_DOI_PREFIX_RE = re.compile(r"^(?:dx\.)?doi\.org/", re.IGNORECASE)
_DOI_SCHEME_LABEL_RE = re.compile(r"^doi:\s*", re.IGNORECASE)
_TITLE_NONALNUM_RE = re.compile(r"[^a-z0-9]+")
_TITLE_WS_RE = re.compile(r"\s+")


def denylist_enabled() -> bool:
    """Kill-switch. DEFAULT ON. ``PG_BLOCKED_REFERENCE_DENYLIST=0`` => empty registry
    everywhere => every wired seam byte-identical to pre-B2 behaviour."""
    return os.getenv(_DENYLIST_FLAG, "1").strip().lower() not in _OFF_TOKENS


def _normalize_url(url: str) -> str:
    """Mirror-robust canonical URL key: w3lib-canonicalize (percent / dot-segment / port /
    fragment), then strip scheme + leading ``www.`` + query + trailing slash and lowercase.

    The query is dropped on purpose (as the benchmark's own blocked-source matcher does)
    so ``?via=ihub``-style mirror variants of the SAME path still match; the path PII / DOI
    legs distinguish genuinely different articles. Never raises ('' on bad input)."""
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""
    canon = raw
    if _canonicalize_url is not None:
        try:
            canon = _canonicalize_url(raw)
        except Exception:  # noqa: BLE001 - fall back to the raw string, never raise
            canon = raw
    canon = _SCHEME_RE.sub("", canon)
    canon = _WWW_RE.sub("", canon)
    canon = canon.split("?", 1)[0].split("#", 1)[0]
    return canon.rstrip("/").lower()


def _normalize_doi(doi: str) -> str:
    """Crossref-canonical DOI key: lowercase, strip ``https?://`` / ``dx.``|``doi.org/`` /
    ``doi:`` prefixes, drop any trailing query/fragment + slash. DOI suffixes are
    case-insensitive per the Crossref rule. Never raises ('' on bad input)."""
    if not doi:
        return ""
    d = doi.strip().lower()
    if not d:
        return ""
    d = _SCHEME_RE.sub("", d)
    d = _DOI_PREFIX_RE.sub("", d)
    d = _DOI_SCHEME_LABEL_RE.sub("", d)
    d = d.split("?", 1)[0].split("#", 1)[0]
    return d.rstrip("/.")


def _extract_dois(text: str) -> set[str]:
    """Every normalized DOI appearing in ``text`` (handles bare DOIs AND DOIs embedded in
    ``doi.org`` URLs)."""
    out: set[str] = set()
    for raw in _DOI_RE.findall(text or ""):
        nd = _normalize_doi(raw)
        if nd:
            out.add(nd)
    return out


def _extract_piis(text: str) -> set[str]:
    """Every publisher PII / arXiv id in ``text`` (incl. PIIs embedded in sciencedirect /
    linkinghub URLs). Stored uppercased / namespaced so the match is case-insensitive."""
    out: set[str] = set()
    for raw in _ELSEVIER_PII_RE.findall(text or ""):
        out.add(raw.upper())
    for raw in _ARXIV_RE.findall(text or ""):
        out.add("ARXIV:" + raw.lower())
    return out


def _parse_appendix_authors(appendix: str) -> list[str]:
    """Author strings from the appendix ``'authors': [...]`` / ``'author': '...'`` field
    (build-side title+author leg). Empty when no author field is present. Never raises."""
    m = _AUTHORS_FIELD_RE.search(appendix or "")
    if not m:
        return []
    return _QUOTED_STR_RE.findall(m.group(1))


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/whitespace to a single space-joined token string."""
    if not title:
        return ""
    low = title.lower()
    low = _TITLE_NONALNUM_RE.sub(" ", low)
    return _TITLE_WS_RE.sub(" ", low).strip()


def _title_ratio(a: str, b: str) -> float:
    """Similarity in [0, 1] between two normalized titles (rapidfuzz if available, else
    stdlib difflib). Both inputs are already ``_normalize_title``-d."""
    if not a or not b:
        return 0.0
    if _rapidfuzz_fuzz is not None:
        return float(_rapidfuzz_fuzz.ratio(a, b)) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass(frozen=True)
class BlockedRegistry:
    """Six OR'd normalized key-sets of operator-prohibited references for ONE work.

    The original FOUR legs (canonical url / DOI / publisher PII / fuzzy title) are joined by
    the I-deepfix-001 P0-1 identity legs — DOAJ article id + title+first-author hash — so a
    DOAJ MIRROR that carries the same article id (in its URL path or metadata) but NOT the
    listed URL / DOI / PII / a matchable title is still caught."""

    canonical_urls: frozenset[str] = frozenset()
    dois: frozenset[str] = frozenset()
    publisher_piis: frozenset[str] = frozenset()
    title_keys: tuple[str, ...] = ()
    doaj_ids: frozenset[str] = frozenset()
    title_author_hashes: frozenset[str] = frozenset()

    @classmethod
    def empty(cls) -> "BlockedRegistry":
        """An empty registry — ``is_blocked`` is always ``(False, "")``."""
        return cls()

    @property
    def is_empty(self) -> bool:
        return not (
            self.canonical_urls
            or self.dois
            or self.publisher_piis
            or self.title_keys
            or self.doaj_ids
            or self.title_author_hashes
        )

    def is_blocked(
        self,
        url: str = "",
        doi: str = "",
        title: str = "",
        doaj_id: str = "",
        authors: "Any" = None,
    ) -> tuple[bool, str]:
        """True + the matched key/reason iff ANY leg matches the blocked work; else
        ``(False, "")``. The DOI + PII + DOAJ legs ALSO inspect identifiers embedded in
        ``url`` so a mirror that is not literally listed still matches. Pure; never raises."""
        if self.is_empty:
            return (False, "")
        # 1) canonical-URL leg
        norm_url = _normalize_url(url)
        if norm_url and norm_url in self.canonical_urls:
            return (True, f"url:{norm_url}")
        # 2) DOI leg — explicit doi arg OR a DOI embedded in the url
        candidate_dois = _extract_dois(url)
        explicit = _normalize_doi(doi)
        if explicit:
            candidate_dois.add(explicit)
        candidate_dois |= _extract_dois(doi)
        for cd in candidate_dois:
            if cd in self.dois:
                return (True, f"doi:{cd}")
        # 3) PII leg — identifiers embedded in the url / doi text
        for pii in _extract_piis(url) | _extract_piis(doi):
            if pii in self.publisher_piis:
                return (True, f"pii:{pii}")
        # 4) DOAJ-id leg (I-deepfix-001 P0-1) — explicit doaj_id arg OR an id embedded in
        # the candidate URL path (the mirror-repository case). Conservatively-built set, so
        # a permissive candidate scan never over-blocks.
        if self.doaj_ids:
            _cand_doaj = _extract_doaj_id_candidates(url)
            _ex_doaj = _normalize_doaj_id(doaj_id)
            if _ex_doaj:
                _cand_doaj.add(_ex_doaj)
            for cdj in _cand_doaj:
                if cdj in self.doaj_ids:
                    return (True, f"doaj:{cdj}")
        # 5) title+first-author hash leg — exact-match fallback when no id is available
        if self.title_author_hashes:
            tah = _title_author_hash(title, authors)
            if tah and tah in self.title_author_hashes:
                return (True, f"title_author:{tah[:16]}")
        # 6) title fuzzy leg
        norm_title = _normalize_title(title)
        if norm_title and self.title_keys:
            for bt in self.title_keys:
                if _title_ratio(norm_title, bt) >= TITLE_FUZZY_THRESHOLD:
                    return (True, f"title:{bt[:80]}")
        return (False, "")


def build_blocked_registry(question_text: str) -> BlockedRegistry:
    """Parse the operator do-not-view / blocked-references appendix out of
    ``question_text`` and return the deny-list. Empty registry when the kill-switch is
    OFF, when there is no appendix, or on ANY parse error (FAIL-OPEN — never crash a run).

    The appendix is located with the SAME regexes the report-echo strip uses
    (``injection_appendix.locate_injected_appendix``) so the two legs can never drift.
    """
    if not denylist_enabled():
        return BlockedRegistry.empty()
    try:
        appendix = locate_injected_appendix(question_text or "")
        if not appendix:
            return BlockedRegistry.empty()
        urls: set[str] = set()
        for raw in _URL_RE.findall(appendix):
            nu = _normalize_url(raw)
            if nu:
                urls.add(nu)
        dois = _extract_dois(appendix)
        piis = _extract_piis(appendix)
        titles: list[str] = []
        raw_titles = _TITLE_FIELD_RE.findall(appendix)
        for raw_title in raw_titles:
            nt = _normalize_title(raw_title)
            if nt and nt not in titles:
                titles.append(nt)
        # I-deepfix-001 P0-1: DOAJ article ids — CONSERVATIVE build (explicit doaj.org/article
        # URL or a labelled doaj_id field only, never a bare hex token) so a stray 32-hex in the
        # appendix is not registered.
        doaj_ids: set[str] = set()
        for _m in _DOAJ_ARTICLE_RE.findall(appendix):
            doaj_ids.add(_m.lower())
        for _m in _DOAJ_ID_FIELD_RE.findall(appendix):
            doaj_ids.add(_m.lower())
        # I-deepfix-001 P0-1: title+first-author identity hash — pair the appendix title(s)
        # with the appendix authors field (order-robust, surname-based).
        title_author_hashes: set[str] = set()
        appendix_authors = _parse_appendix_authors(appendix)
        if appendix_authors and raw_titles:
            for raw_title in raw_titles:
                tah = _title_author_hash(raw_title, appendix_authors)
                if tah:
                    title_author_hashes.add(tah)
        registry = BlockedRegistry(
            canonical_urls=frozenset(urls),
            dois=frozenset(dois),
            publisher_piis=frozenset(piis),
            title_keys=tuple(titles),
            doaj_ids=frozenset(doaj_ids),
            title_author_hashes=frozenset(title_author_hashes),
        )
        logger.info(
            "[blocked_registry] built per-work deny-list: urls=%d dois=%d piis=%d "
            "titles=%d doaj_ids=%d title_author=%d",
            len(registry.canonical_urls),
            len(registry.dois),
            len(registry.publisher_piis),
            len(registry.title_keys),
            len(registry.doaj_ids),
            len(registry.title_author_hashes),
        )
        return registry
    except Exception as exc:  # noqa: BLE001 - FAIL-OPEN: a bad question never aborts a run
        logger.warning(
            "[blocked_registry] build failed (FAIL-OPEN, empty registry): %s", exc
        )
        return BlockedRegistry.empty()
