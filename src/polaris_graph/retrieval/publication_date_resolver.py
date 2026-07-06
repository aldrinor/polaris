"""Publication-date resolver — htmldate-style cascade over ALREADY-fetched content.

I-deepfix-001 FF5 (fix-wave, Part A prerequisite): the temporal-scope enforcement
predicate (``constraint_enforcement._row_pub_ym`` / ``_row_out_of_window``) can only
judge a source out-of-window when the source row carries a structured publication
date. Today the ONLY code that stamps a date is the OpenAlex authority enrich, so
every crawled web page / institutional PDF / general-web source arrives UNDATED and
fail-opens straight into the grounding set even under a HARD user-stated date bound
(e.g. "based on academic research published before June 2023").

This module gives the enforcement predicate the dates it lacks by resolving a
publication date from content the pipeline ALREADY fetched — ZERO new network. It is a
pure function: same inputs → same output, no I/O, no env reads, no global state. The
env gate (``PG_RESOLVE_PUBDATE_FROM_HTML``) and the wiring into ``live_retriever`` /
``constraint_enforcement`` are a SEPARATE wave (FF6); this wave ships the pure resolver
plus its unit test only. (FF6 also threads the OpenAlex ``cand.metadata`` — whose
``year`` the authority-enrich path discards — through the new ``search_metadata``
argument, so the leaked 2026 ``openalex.org`` row is dated at zero cost.)

Cascade precedence (htmldate — JOSS 10.21105/joss.02439; Parse.ly / Webz.io metadata
guidance confirm JSON-LD as the most reliable signal, meta tags + <time> as fallbacks).
Structured signals (publisher HTML metadata AND the search-result API metadata) rank
ahead of the weaker URL-slug / PDF-creation heuristics:

  1. JSON-LD ``datePublished`` (then ``dateCreated``) inside <script type="application/ld+json">
  2. meta ``article:published_time`` / ``citation_publication_date`` / ``citation_date``
     / ``DC.date.issued`` / ``prism.publicationDate``
  3. microdata ``itemprop="datePublished"``
  4. ``<time datetime=...>``
  5. structured search-result metadata (``search_metadata`` — e.g. the OpenAlex
     ``cand.metadata['publication_date']`` / ``['year']`` that the OpenAlex-authority
     enrich path discarded; FF5-v2 zero-cost recovery of the leaked 2026 openalex.org row)
  6. URL ``/YYYY/MM/`` pattern
  7. PDF ``/CreationDate`` (``D:YYYYMMDD...``)

Design decisions (deliberate, per the FF5 brief):
- Metadata-first ONLY. NO body-text heuristic date parsing — a "last updated" / comment
  date can mis-date a page and wrongly mask an in-window source. When the cascade finds
  no structured signal, the source stays honestly UNDATED (returns ``(None, None)``);
  it does NOT guess.
- Normalizes to MONTH precision (``YYYY-MM``) because the downstream timeline
  enforcement operates at year*12+month granularity; the day is dropped. A year-only
  signal degrades honestly to ``YYYY`` (year precision downstream).
- Malformed month tokens are rejected at the SEPARATOR, never silently truncated: the
  ``YYYY-MM`` matcher requires a right boundary after the 1-2 month digits (``(?!\\d)``),
  so an over-long token like ``2023-123`` degrades to honest YEAR precision (``2023``)
  instead of over-resolving to ``2023-12`` and wrongly masking an in-window source
  (FF5-v2 correction — the original ``(\\d{1,2})`` grabbed the first two digits with no
  right boundary).
- Accepts a year ONLY when ``1900 <= year <= 2100`` (matches the OpenAlex-path guard in
  ``live_retriever``); anything outside that band is treated as unresolved.
- Fail-open: any parse error anywhere returns ``(None, None)`` — an undated source is
  NEVER masked, so a resolver bug can never wrongly drop an in-window source.

Faithfulness-neutral: the resolved date is fetch-time PROVENANCE metadata only. It never
enters a verified claim; strict_verify / NLI / D8 / provenance span-grounding never read
it. It only feeds the scope/timeline WEIGHT-and-disclose layer.
"""
from __future__ import annotations

import re

# ── structural bounds / precompiled patterns (module-level constants, §4.1) ────────────
# Accept only plausibly-real publication years. Mirrors the OpenAlex-path guard in
# live_retriever.py (1900 <= year <= 2100).
MIN_PUBLICATION_YEAR = 1900
MAX_PUBLICATION_YEAR = 2100

# Raw <script type="application/ld+json"> block capture (mirrors live_retriever's pattern
# so the resolver works whether or not the caller pre-extracted the JSON-LD).
_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

# JSON-LD date keys, searched as raw JSON string values so nesting (@graph arrays, nested
# objects) and block concatenation are handled uniformly without a strict JSON parse.
_JSONLD_DATE_KEYS = ("datePublished", "dateCreated")

# Ordered meta-tag identifiers (name= / property= value), most-authoritative first.
_META_DATE_KEYS = (
    "article:published_time",
    "citation_publication_date",
    "citation_date",
    "dc.date.issued",
    "prism.publicationdate",
)

# Ordered structured search-result metadata keys (e.g. OpenAlex cand.metadata), most
# precise first: an explicit publication_date (month precision) before a bare year.
_SEARCH_METADATA_DATE_KEYS = (
    "publication_date",
    "pub_date",
    "published",
    "date",
    "publication_year",
    "year",
)

# One <meta ...> tag.
_META_TAG_RE = re.compile(r"<meta\b[^>]*?>", re.IGNORECASE)
# attr="value" or attr='value' inside a tag.
_ATTR_RE = re.compile(
    r"""([a-zA-Z][\w:.\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
)

# A tag carrying itemprop="datePublished" (microdata).
_ITEMPROP_DATEPUB_TAG_RE = re.compile(
    r"""<[a-zA-Z][^>]*?itemprop\s*=\s*["']datePublished["'][^>]*?>""",
    re.IGNORECASE,
)
# The inner text immediately following such a tag (for <span itemprop=...>2023-05-01</span>).
_ITEMPROP_DATEPUB_INNER_RE = re.compile(
    r"""<([a-zA-Z][\w\-]*)[^>]*?itemprop\s*=\s*["']datePublished["'][^>]*?>(.*?)</\1>""",
    re.IGNORECASE | re.DOTALL,
)

# A <time ...> element and its datetime attribute.
_TIME_TAG_RE = re.compile(r"<time\b[^>]*?>", re.IGNORECASE)

# URL /YYYY/MM/ (optionally /DD/) date path segment.
_URL_YMD_RE = re.compile(r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])(?:/\d{1,2})?(?:/|$|[?#])")

# PDF metadata CreationDate keys (pypdf/pdfminer surface these variously).
_PDF_CREATIONDATE_KEYS = ("CreationDate", "creationDate", "creationdate", "/CreationDate")

# Normalisation: leading "D:" (PDF), then either separated Y-M[-D] or compact YYYYMMDD.
# _YM_SEPARATED_RE requires a RIGHT BOUNDARY after the 1-2 month digits ((?!\d)) so an
# over-long month token (2023-123) does NOT truncate to a bogus 2-digit month — it fails
# this leg and degrades to year precision via _YEAR_ONLY_RE (FF5-v2 correction).
_LEADING_PDF_PREFIX_RE = re.compile(r"^\s*D:\s*")
_YM_SEPARATED_RE = re.compile(r"^\s*(\d{4})[-/.](\d{1,2})(?!\d)")
_YMD_COMPACT_RE = re.compile(r"^\s*(\d{4})(\d{2})(\d{2})")
_YEAR_ONLY_RE = re.compile(r"^\s*(\d{4})(?!\d)")


def _normalize_ym(raw: "str | None") -> "tuple[str, int] | None":
    """Normalize a raw date token to ``(iso, year)`` at MONTH precision.

    Returns ``("YYYY-MM", year)`` when a valid 1-12 month is present, ``("YYYY", year)``
    for a year-only token, or ``None`` when no in-band (1900-2100) year can be parsed.
    The day component is intentionally dropped — the downstream timeline gate is
    month-precision. Malformed / out-of-range months degrade to year precision rather
    than guessing.
    """
    if not raw:
        return None
    s = _LEADING_PDF_PREFIX_RE.sub("", str(raw)).strip()
    if not s:
        return None

    year: "int | None" = None
    month: "int | None" = None

    m = _YM_SEPARATED_RE.match(s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
    else:
        m = _YMD_COMPACT_RE.match(s)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
        else:
            m = _YEAR_ONLY_RE.match(s)
            if m:
                year = int(m.group(1))

    if year is None or not (MIN_PUBLICATION_YEAR <= year <= MAX_PUBLICATION_YEAR):
        return None
    if month is not None and not (1 <= month <= 12):
        month = None  # malformed month → honest year precision, never a guess
    if month is None:
        return (f"{year:04d}", year)
    return (f"{year:04d}-{month:02d}", year)


def _iter_tag_attrs(tag: str) -> "dict[str, str]":
    """Parse a single HTML tag's attributes into a lowercased-key dict."""
    attrs: "dict[str, str]" = {}
    for a in _ATTR_RE.finditer(tag):
        key = a.group(1).lower()
        val = a.group(2) if a.group(2) is not None else a.group(3)
        attrs[key] = val if val is not None else ""
    return attrs


def _combined_jsonld(raw_html: str, jsonld: str) -> str:
    """Combine the caller-supplied JSON-LD with any <script ld+json> blocks still
    present in the raw HTML (the caller may pass one, the other, or both)."""
    parts: "list[str]" = []
    if jsonld:
        parts.append(jsonld)
    if raw_html and "ld+json" in raw_html.lower():
        try:
            parts.extend(m.group(1) for m in _JSONLD_SCRIPT_RE.finditer(raw_html))
        except Exception:  # noqa: BLE001 — additive; never break resolution on a bad regex input
            pass
    return "\n".join(p for p in parts if p)


def _from_jsonld(raw_html: str, jsonld: str) -> "tuple[str, int] | None":
    """Step 1 — JSON-LD datePublished (then dateCreated).

    Searches the raw JSON-LD text for the key's string value. A raw-string search (rather
    than a strict json.loads) is used deliberately: ``_extract_jsonld_blocks`` concatenates
    every block, so the combined text is frequently not a single valid JSON document, and
    ``datePublished`` may live at any nesting depth (e.g. inside an ``@graph`` array).
    """
    text = _combined_jsonld(raw_html, jsonld)
    if not text:
        return None
    for key in _JSONLD_DATE_KEYS:
        pat = re.compile(r'"' + re.escape(key) + r'"\s*:\s*"([^"]+)"', re.IGNORECASE)
        m = pat.search(text)
        if m:
            norm = _normalize_ym(m.group(1))
            if norm:
                return norm
    return None


def _from_meta(raw_html: str) -> "tuple[str, int] | None":
    """Step 2 — OpenGraph / citation / Dublin Core / PRISM meta tags."""
    if not raw_html:
        return None
    # Map every identifiable meta tag → its content, then try keys in precedence order.
    content_by_id: "dict[str, str]" = {}
    for tm in _META_TAG_RE.finditer(raw_html):
        attrs = _iter_tag_attrs(tm.group(0))
        content = attrs.get("content")
        if content is None:
            continue
        ident = attrs.get("property") or attrs.get("name") or attrs.get("itemprop")
        if not ident:
            continue
        ident = ident.strip().lower()
        # First occurrence wins (top-of-head meta is the canonical one).
        content_by_id.setdefault(ident, content)
    for key in _META_DATE_KEYS:
        if key in content_by_id:
            norm = _normalize_ym(content_by_id[key])
            if norm:
                return norm
    return None


def _from_microdata(raw_html: str) -> "tuple[str, int] | None":
    """Step 3 — microdata itemprop="datePublished" (content=, datetime=, or inner text)."""
    if not raw_html:
        return None
    for tm in _ITEMPROP_DATEPUB_TAG_RE.finditer(raw_html):
        attrs = _iter_tag_attrs(tm.group(0))
        for attr_key in ("content", "datetime"):
            if attr_key in attrs:
                norm = _normalize_ym(attrs[attr_key])
                if norm:
                    return norm
    # Inner-text form: <span itemprop="datePublished">2023-05-01</span>
    im = _ITEMPROP_DATEPUB_INNER_RE.search(raw_html)
    if im:
        norm = _normalize_ym(im.group(2).strip())
        if norm:
            return norm
    return None


def _from_time_element(raw_html: str) -> "tuple[str, int] | None":
    """Step 4 — <time datetime=...>."""
    if not raw_html:
        return None
    for tm in _TIME_TAG_RE.finditer(raw_html):
        attrs = _iter_tag_attrs(tm.group(0))
        dt = attrs.get("datetime")
        if dt:
            norm = _normalize_ym(dt)
            if norm:
                return norm
    return None


def _from_search_metadata(search_metadata: "dict | None") -> "tuple[str, int] | None":
    """Step 5 — structured search-result API metadata (e.g. OpenAlex cand.metadata).

    Recovers the exact leaked class from the FF5 forensic (the ``openalex.org`` 2026 row
    [12]): the OpenAlex search already carried ``metadata['year'] = 2026``, but the
    authority-enrich path discarded it, so the row reached the timeline gate UNDATED.
    Reading it here — most-precise key first (``publication_date`` → ... → ``year``) — is a
    ZERO-cost recovery of an ALREADY-fetched structured value. It ranks ABOVE the weaker
    URL-slug / PDF-creation heuristics but BELOW the publisher's own HTML structured date
    so finer month precision from the page is never coarsened.
    """
    if not search_metadata or not isinstance(search_metadata, dict):
        return None
    for key in _SEARCH_METADATA_DATE_KEYS:
        if key in search_metadata:
            val = search_metadata[key]
            if val is None:
                continue
            norm = _normalize_ym(str(val))
            if norm:
                return norm
    return None


def _from_url(url: str) -> "tuple[str, int] | None":
    """Step 6 — URL /YYYY/MM/ date path."""
    if not url:
        return None
    m = _URL_YMD_RE.search(str(url))
    if m:
        return _normalize_ym(f"{m.group(1)}-{m.group(2)}")
    return None


def _from_pdf_meta(pdf_meta: "dict | None") -> "tuple[str, int] | None":
    """Step 7 — PDF /CreationDate (``D:YYYYMMDD...``)."""
    if not pdf_meta or not isinstance(pdf_meta, dict):
        return None
    for key in _PDF_CREATIONDATE_KEYS:
        if key in pdf_meta:
            norm = _normalize_ym(pdf_meta[key])
            if norm:
                return norm
    return None


def resolve_publication_date(
    *,
    raw_html: "str | None",
    jsonld: "str | None",
    url: "str | None",
    pdf_meta: "dict | None" = None,
    search_metadata: "dict | None" = None,
) -> "tuple[str | None, int | None]":
    """Resolve a publication date from ALREADY-fetched content (ZERO new network).

    Runs the htmldate-style cascade (JSON-LD → meta → microdata → <time> → structured
    search-result metadata → URL → PDF) and returns the FIRST successful resolution as
    ``(iso, year)`` where ``iso`` is ``"YYYY-MM"`` (month precision) or ``"YYYY"``
    (year-only signals), and ``year`` is an int in ``[1900, 2100]``.

    ``search_metadata`` carries the structured search-result metadata dict (e.g. an
    OpenAlex candidate's ``metadata``) whose ``year`` / ``publication_date`` the
    OpenAlex-authority enrich path may have discarded — a zero-cost recovery of an
    already-fetched structured value (FF5-v2).

    Returns ``(None, None)`` when nothing resolves — the source stays honestly UNDATED;
    it does NOT guess. Fail-open: any unexpected error returns ``(None, None)`` so a
    resolver fault can never wrongly mask an in-window source.
    """
    try:
        raw_html = raw_html or ""
        jsonld = jsonld or ""
        url = url or ""
        # Lazy cascade: each step is evaluated in precedence order and the FIRST hit
        # short-circuits (later, less-authoritative signals are not even consulted).
        for step in (
            lambda: _from_jsonld(raw_html, jsonld),
            lambda: _from_meta(raw_html),
            lambda: _from_microdata(raw_html),
            lambda: _from_time_element(raw_html),
            lambda: _from_search_metadata(search_metadata),
            lambda: _from_url(url),
            lambda: _from_pdf_meta(pdf_meta),
        ):
            hit = step()
            if hit is not None:
                return (hit[0], hit[1])
        return (None, None)
    except Exception:  # noqa: BLE001 — fail-open: a resolver fault must never mask a source
        return (None, None)
