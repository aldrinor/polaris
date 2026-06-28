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

import logging
import os
import re
from dataclasses import dataclass

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
    """Four OR'd normalized key-sets of operator-prohibited references for ONE work."""

    canonical_urls: frozenset[str] = frozenset()
    dois: frozenset[str] = frozenset()
    publisher_piis: frozenset[str] = frozenset()
    title_keys: tuple[str, ...] = ()

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
        )

    def is_blocked(
        self, url: str = "", doi: str = "", title: str = ""
    ) -> tuple[bool, str]:
        """True + the matched key/reason iff ANY leg matches the blocked work; else
        ``(False, "")``. The DOI + PII legs ALSO inspect identifiers embedded in ``url``
        so a mirror that is not literally listed still matches. Pure; never raises."""
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
        # 4) title fuzzy leg
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
        for raw_title in _TITLE_FIELD_RE.findall(appendix):
            nt = _normalize_title(raw_title)
            if nt and nt not in titles:
                titles.append(nt)
        registry = BlockedRegistry(
            canonical_urls=frozenset(urls),
            dois=frozenset(dois),
            publisher_piis=frozenset(piis),
            title_keys=tuple(titles),
        )
        logger.info(
            "[blocked_registry] built per-work deny-list: urls=%d dois=%d piis=%d titles=%d",
            len(registry.canonical_urls),
            len(registry.dois),
            len(registry.publisher_piis),
            len(registry.title_keys),
        )
        return registry
    except Exception as exc:  # noqa: BLE001 - FAIL-OPEN: a bad question never aborts a run
        logger.warning(
            "[blocked_registry] build failed (FAIL-OPEN, empty registry): %s", exc
        )
        return BlockedRegistry.empty()
