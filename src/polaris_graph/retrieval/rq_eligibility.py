"""LEVER B — the task-derived SOURCE-ELIGIBILITY plan builder.

This is the FOUNDATION of Batch 1: it takes the constraints the RQ *itself* states
(``source_types`` / ``languages`` / ``recency``), parsed generically from the prompt by
``instruction/constraint_extractor.py`` and cached on ``protocol['_rq_constraints']``, and
turns them into a per-URL DEMOTE map at the citable-generation-pool boundary.

It is a strict GENERALIZATION of the PROVEN date-window / scope WEIGHT seam
(``evidence_selector._select_evidence_for_generation_impl``): build a per-URL multiplicative
demote weight in ``(0, 1]`` + a tail-partition set + disclosed exclusion records, and fold the
weight into the SAME selection sort key. Nothing is hard-dropped (DNA §-1.3 WEIGHT-not-FILTER):
an ineligible row (wrong source-type / non-English / out-of-recency) is DEMOTED, tail-partitioned,
KEPT in the corpus, and disclosed; an UNRESOLVED row (unknown genre / unknown language / undated)
is FAIL-OPEN (weight 1.0, never punished) and flagged for fetch recovery.

Generalization (hard rule): every constraint is read from the RQ's OWN parsed words — there are NO
domain- or task-specific literals and no per-topic branches. The source-type
vocabulary is the SAME canonical vocabulary ``constraint_extractor`` already emits for ANY prompt,
and the genre classifier is the field-agnostic ``document_type_classifier``. An RQ that states no
source/language/recency constraint yields an EMPTY plan (byte-identical selection).

Default OFF: ``PG_RQ_SOURCE_ELIGIBILITY_ENFORCE`` empty/falsey => ``build_rq_eligibility`` returns
an EMPTY plan => the selection sort key + tail partition are byte-identical. No post-generation
entailment/verification/sentence-drop gate is added (upstream-only, LAW/DNA-compliant).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.polaris_graph.settings import resolve
from src.polaris_graph.retrieval.document_type_classifier import (
    DocumentType,
    classify_document_type,
)

logger = logging.getLogger("polaris_graph.rq_eligibility")

_ENFORCE_FLAG = "PG_RQ_SOURCE_ELIGIBILITY_ENFORCE"
_DEMOTE_WEIGHT_FLAG = "PG_RQ_SOURCE_ELIGIBILITY_DEMOTE_WEIGHT"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})
_ON_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})

# Mirror of the date/scope demote default: an ineligible row is KEPT at a low weight, never zeroed.
_DEFAULT_DEMOTE_WEIGHT = 0.3

_YEAR_RE = re.compile(r"\b(19|20|21)\d{2}\b")


# ── Canonical RQ source-type  ->  the DocumentType GENRE family it admits ────────────────────
# Keys are the SAME canonical tokens ``constraint_extractor._SOURCE_TYPE_ALIASES`` emits for any
# prompt (journal_article, peer_reviewed, news_article, ...). A row is ELIGIBLE under a stated
# source-type constraint iff its classified genre is in the UNION of the admitted families across
# every stated type. Field-agnostic; no task literals.
_SOURCE_TYPE_TO_GENRES: dict[str, frozenset[DocumentType]] = {
    "journal_article": frozenset({DocumentType.JOURNAL_ARTICLE, DocumentType.REVIEW_ARTICLE}),
    "peer_reviewed": frozenset({DocumentType.JOURNAL_ARTICLE, DocumentType.REVIEW_ARTICLE}),
    "conference_paper": frozenset({DocumentType.CONFERENCE_PAPER}),
    "working_paper": frozenset({DocumentType.WORKING_PAPER}),
    "preprint": frozenset({DocumentType.PREPRINT}),
    "book": frozenset({DocumentType.BOOK}),
    "book_chapter": frozenset({DocumentType.BOOK}),
    "report": frozenset({DocumentType.REPORT}),
    "government_report": frozenset({DocumentType.REPORT}),
    "news_article": frozenset({DocumentType.NEWS, DocumentType.PRESS_RELEASE}),
    "blog_post": frozenset({DocumentType.BLOG_COMMENTARY}),
    "website": frozenset({DocumentType.BLOG_COMMENTARY, DocumentType.ENCYCLOPEDIA}),
    "grey_literature": frozenset(
        {DocumentType.REPORT, DocumentType.WORKING_PAPER, DocumentType.PREPRINT}
    ),
}


def eligibility_enabled() -> bool:
    """LEVER B kill-switch. DEFAULT OFF (operator activates on the slate). OFF =>
    ``build_rq_eligibility`` returns an EMPTY plan => byte-identical selection."""
    raw = (resolve(_ENFORCE_FLAG) or "").strip().lower()
    return raw not in _OFF_VALUES


def demote_weight() -> float:
    """The multiplicative ranking demote for an INELIGIBLE row (LAW VI overridable). Clamped to
    (0, 1) — a demoted source is KEPT at low weight, never zero/dropped (mirrors the date/scope
    demote)."""
    raw = (resolve(_DEMOTE_WEIGHT_FLAG) or "").strip()
    if not raw:
        return _DEFAULT_DEMOTE_WEIGHT
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_DEMOTE_WEIGHT
    return min(max(val, 0.01), 0.99)


@dataclass
class RQEligibilityPlan:
    """The demote / disclose / fetch-recovery decisions for one corpus under one RQ's stated
    source/language/recency intent. Empty plan => byte-identical widest+deepest run."""

    url_to_eligibility_weight: dict[str, float] = field(default_factory=dict)
    ineligible_urls: set[str] = field(default_factory=set)
    fetch_recovery_urls: set[str] = field(default_factory=set)
    eligibility_records: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.url_to_eligibility_weight or self.ineligible_urls)


def _field(source: "Any", *names: str) -> "Any":
    if isinstance(source, Mapping):
        for n in names:
            if n in source and source.get(n) is not None:
                return source.get(n)
        return None
    for n in names:
        v = getattr(source, n, None)
        if v is not None:
            return v
    return None


def _row_url(row: "Any") -> str:
    return str(_field(row, "source_url", "url") or "")


def _row_year(row: "Any") -> "int | None":
    """Best-effort explicit publication year, or None (undated => fail-open)."""
    for key in ("year", "publication_year", "pub_date", "publication_date", "published", "date"):
        v = _field(row, key)
        if v is None:
            continue
        m = _YEAR_RE.search(str(v))
        if m:
            try:
                return int(m.group(0))
            except (TypeError, ValueError):
                continue
    meta = _field(row, "metadata")
    if isinstance(meta, Mapping):
        v = meta.get("year")
        if v is not None:
            m = _YEAR_RE.search(str(v))
            if m:
                try:
                    return int(m.group(0))
                except (TypeError, ValueError):
                    return None
    return None


_SOURCE_ROUTING_FLAG = "PG_SOURCE_ROUTING"


def source_routing_enabled() -> bool:
    """LEVER 4 kill-switch (``PG_SOURCE_ROUTING``). DEFAULT OFF (empty => off). OFF => ``_row_language``
    is byte-identical (sidecar-only, NO offline detection)."""
    return (resolve(_SOURCE_ROUTING_FLAG) or "").strip().lower() not in _OFF_VALUES


# ── LEVER 4: OFFLINE language detection (no network, no task literals, general). Two CONFIDENT signals
# only; anything ambiguous returns None so the caller stays FAIL-OPEN (unknown => never punished). ──
# (1) SCRIPT signal: letters dominated by a non-Latin Unicode block => that language family.
# (2) Latin-script STOPWORD signal: a strong ratio of one language's function words (and not English).
_SCRIPT_RANGES: "tuple[tuple[int, int, str], ...]" = (
    (0x0600, 0x06FF, "ar"), (0x0750, 0x077F, "ar"),   # Arabic (+ supplement)
    (0x0400, 0x04FF, "ru"),                             # Cyrillic
    (0x0370, 0x03FF, "el"),                             # Greek
    (0x0590, 0x05FF, "he"),                             # Hebrew
    (0x0900, 0x097F, "hi"),                             # Devanagari
    (0x0E00, 0x0E7F, "th"),                             # Thai
    (0xAC00, 0xD7AF, "ko"),                             # Hangul
    (0x3040, 0x30FF, "ja"),                             # Hiragana + Katakana
    (0x4E00, 0x9FFF, "zh"),                             # CJK Unified (kana above disambiguates ja)
)
_STOPWORDS: "dict[str, frozenset[str]]" = {
    "en": frozenset({"the", "of", "and", "in", "to", "for", "on", "with", "an", "is", "are", "from", "by"}),
    "es": frozenset({"el", "la", "los", "las", "de", "y", "en", "para", "con", "una", "del", "por", "que"}),
    "fr": frozenset({"le", "la", "les", "des", "et", "dans", "pour", "avec", "une", "du", "sur", "que", "au"}),
    "de": frozenset({"der", "die", "das", "und", "für", "mit", "eine", "ein", "von", "den", "im", "auf", "zur"}),
    "it": frozenset({"il", "la", "le", "dei", "di", "e", "per", "con", "una", "del", "sul", "che", "gli"}),
    "pt": frozenset({"o", "os", "as", "de", "em", "para", "com", "uma", "um", "do", "da", "no", "na"}),
    "pl": frozenset({"i", "w", "na", "z", "do", "dla", "oraz", "jest", "się", "nie", "przez", "który"}),
}


def detect_language_offline(text: "str | None") -> "str | None":
    """CONFIDENT ISO-639-1 code for ``text`` (a row title/snippet) or None. Offline, no network,
    general (any language via script/stopwords), NO task literals. Conservative: returns None unless
    a signal is strong, so an ambiguous row stays fail-open (unknown => never punished)."""
    if not text:
        return None
    s = str(text)
    letters = [ch for ch in s if ch.isalpha()]
    if len(letters) < 4:
        return None
    counts: "dict[str, int]" = {}
    latin = 0
    for ch in letters:
        cp = ord(ch)
        if cp < 0x0250 or (0x1E00 <= cp <= 0x1EFF):   # Basic/Extended Latin => Latin-script
            latin += 1
            continue
        for lo, hi, code in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        top = max(counts, key=counts.get)
        if counts[top] >= 0.35 * len(letters):        # decisive non-Latin script
            return top
    if latin < 0.5 * len(letters):
        return None
    words = re.findall(r"[^\W\d_]+", s.lower(), re.UNICODE)
    if len(words) < 5:
        return None
    hits = {lang: sum(1 for w in words if w in sw) for lang, sw in _STOPWORDS.items()}
    en = hits.get("en", 0)
    best_lang, best = max(hits.items(), key=lambda kv: kv[1])
    if best_lang != "en" and best >= 3 and best > en * 2:   # clear non-English lead
        return best_lang
    return None


def _row_language(row: "Any") -> "str | None":
    """Best-effort ISO-639-1 language of a row, or None (unknown => fail-open). Reads a row's
    own ``language``/``lang`` sidecar (or ``metadata.language``). LEVER 4 (``PG_SOURCE_ROUTING``, off
    by default): when NO sidecar is present, an OFFLINE detector (no network) supplies a CONFIDENT
    code as a fallback; a low-confidence row still returns None (stays fail-open). OFF => sidecar-only,
    byte-identical."""
    for key in ("language", "lang"):
        v = _field(row, key)
        if v:
            s = str(v).strip().lower()
            if s:
                return s[:2]
    meta = _field(row, "metadata")
    if isinstance(meta, Mapping):
        v = meta.get("language") or meta.get("lang")
        if v:
            s = str(v).strip().lower()
            if s:
                return s[:2]
    # LEVER 4: offline detection fallback — ONLY when the sidecar is absent AND source routing is on.
    if source_routing_enabled():
        text = " ".join(
            str(_field(row, k) or "") for k in ("title", "snippet", "text", "abstract")
        ).strip()
        code = detect_language_offline(text)
        if code:
            return code
    return None


def _row_genre(row: "Any") -> DocumentType:
    """Classify a row's document GENRE, reusing the field-agnostic deterministic classifier.
    Prefers a pre-stamped ``document_type`` (from tier_classifier) and otherwise runs the
    offline host/url/DOI classifier. Fail-open to UNKNOWN on any error (never punished)."""
    pre = _field(row, "document_type")
    if pre is not None:
        try:
            stamped = DocumentType(str(pre).strip().upper())
            if stamped != DocumentType.UNKNOWN:
                return stamped
        except (ValueError, TypeError):
            pass
    try:
        dt, _basis = classify_document_type(
            openalex_publication_type=str(_field(row, "openalex_publication_type") or ""),
            openalex_source_type=str(_field(row, "openalex_source_type") or ""),
            source_class=str(_field(row, "source_class") or ""),
            url=_row_url(row),
            title=str(_field(row, "title") or ""),
            doi=str(_field(row, "doi") or ""),
        )
        if dt != DocumentType.UNKNOWN:
            return dt
    except Exception:  # noqa: BLE001 - fail-open: an unclassifiable row is UNKNOWN (neutral)
        pass

    # ``journal`` is an explicit schema alias for an article's publication venue. ``venue`` is
    # populated by scholarly discovery backends after they have resolved a publication venue.
    # Apply this positive signal only after explicit/stamped non-journal types and the generic
    # URL/DOI classifier have had first refusal, so repository, working-paper, news, blog, book,
    # and report manifestations cannot be promoted merely because they mention a venue.
    if _field(row, "journal", "venue"):
        return DocumentType.JOURNAL_ARTICLE
    return DocumentType.UNKNOWN


def _admitted_genres(source_types: list[str]) -> "frozenset[DocumentType] | None":
    """Union of the admitted genres across the RQ's stated canonical source types. Returns None
    when NONE of the stated types map to a known genre family (=> source-type is UNRESOLVED =>
    no source-type demotion, fail-open)."""
    admitted: set[DocumentType] = set()
    resolved_any = False
    for st in source_types or []:
        fam = _SOURCE_TYPE_TO_GENRES.get(str(st).strip().lower())
        if fam:
            admitted |= set(fam)
            resolved_any = True
    return frozenset(admitted) if resolved_any else None


# Comparator vocabulary parsed generically from any RQ recency phrase. "before/until/up to/prior to/
# no later than" => an UPPER bound (ceiling); "after/since/from/newer than/no earlier than" => a
# LOWER bound (floor). Field-agnostic; NO task literals.
_BEFORE_RE = re.compile(
    r"\b(?:before|prior\s+to|up\s+to|no\s+later\s+than|not?\s+later\s+than|until|through|by|"
    r"earlier\s+than|older\s+than|pre)\b",
    re.IGNORECASE,
)
_AFTER_RE = re.compile(
    r"\b(?:after|since|from|starting|newer\s+than|no\s+earlier\s+than|not?\s+earlier\s+than|"
    r"more\s+recent\s+than|onward|onwards|post)\b",
    re.IGNORECASE,
)

# A two-year CLOSED-RANGE phrasing that a single before/after comparator misclassifies:
#   "from 2018 to 2022"   (only "from" matches _AFTER_RE => would be read as a bare lower bound)
#   "between 2018 and 2022"
#   "2018 to 2022" / "2018 through 2022"
#   "2018-2022" / "2018–2022" (hyphen / en-dash / em-dash, optional spaces)
# The span connective ("to"/"through"/"and"/dash) sits BETWEEN the two 4-digit years. Field-
# agnostic; NO task literals.
_YR = r"(?:19|20|21)\d{2}"
_RANGE_RE = re.compile(
    rf"\b(?:from\s+)?{_YR}\s*(?:to|through|thru|and|-|–|—|until)\s*{_YR}\b|"
    rf"\bbetween\s+{_YR}\s+and\s+{_YR}\b",
    re.IGNORECASE,
)


def _parse_recency_bounds(recency: "Any") -> "tuple[int | None, int | None]":
    """Parse a free-text recency phrase into ``(floor, ceiling)`` inclusive year bounds, preserving
    the stated comparator DIRECTION.

    - ``(floor, None)``   for a lower-bound phrase ("since 2020", "after 2019").
    - ``(None, ceiling)`` for an upper-bound phrase ("before 2023", "up to 2021").
    - ``(lo, hi)``        for an explicit two-year RANGE ("between 2018 and 2022", "2018-2022",
                          "last 5 years (2020-2025)").
    - ``(min_year, None)`` for a bare year with NO comparator (relative/recency default: treat the
                          MIN stated year as a floor, matching the classic recency-window intent).
    - ``(None, None)``    when the phrase carries no resolvable 4-digit year (fail-open).

    Pure; never raises."""
    if not recency:
        return (None, None)
    text = str(recency)
    years: list[int] = []
    for y in re.findall(r"\b(?:19|20|21)\d{2}\b", text):
        try:
            years.append(int(y))
        except (TypeError, ValueError):
            continue
    if not years:
        return (None, None)
    lo, hi = min(years), max(years)

    has_before = bool(_BEFORE_RE.search(text))
    has_after = bool(_AFTER_RE.search(text))

    # An explicit TWO-YEAR CLOSED-RANGE phrasing ("from 2018 to 2022", "between 2018 and 2022",
    # "2018-2022", "2018 through 2022") is a closed window across the two stated years, EVEN when
    # only ONE direction word matched (e.g. "from" in "from X to Y" trips only _AFTER_RE, which
    # would otherwise be read as a bare lower bound and lose the ceiling). Check this FIRST so the
    # range form is never demoted to a single-sided bound.
    if len(years) >= 2 and lo != hi and _RANGE_RE.search(text):
        return (lo, hi)
    # An explicit multi-year span with balanced/absent direction words is also a closed window.
    if len(years) >= 2 and lo != hi and not (has_before ^ has_after):
        return (lo, hi)
    if has_before and not has_after:
        return (None, hi)  # "before/up to YEAR" => upper bound
    if has_after and not has_before:
        return (lo, None)  # "after/since YEAR" => lower bound
    if has_before and has_after:
        # both directions present ("from 2018 to 2022") => closed window across the stated years.
        return (lo, hi)
    # No comparator word: bare year(s) => recency-window floor (classic "recent since MIN" intent).
    return (lo, None)


def ensure_rq_constraints(
    protocol: "dict[str, Any] | None",
    research_question: "str | None" = None,
) -> "Mapping[str, Any] | None":
    """Populate and cache ``protocol['_rq_constraints']`` from the research question when absent.

    This is the WIRING seam: ``build_rq_eligibility`` reads the constraints the RQ itself stated
    from ``protocol['_rq_constraints']``, but nothing else in the pipeline writes it. When the
    enforce flag is on and the cache is absent, extract the constraints GENERICALLY from the RQ's
    own words via the shared ``constraint_extractor`` (the SAME canonical vocabulary used for any
    prompt — no task literals) and cache the result so this runs at most once per protocol.

    Fail-open: any extraction error (e.g. the live extractor disabled) caches an EMPTY dict so we
    never re-attempt and eligibility stays byte-identical (an empty plan). Returns the cached
    mapping (possibly empty), or None when there is no protocol / the flag is off."""
    prompt_scope_on = (resolve("PG_PROMPT_SCOPE_WEIGHTING") or "").strip().lower() not in _OFF_VALUES
    if protocol is None or not (eligibility_enabled() or prompt_scope_on):
        return None
    cached = protocol.get("_rq_constraints")
    if isinstance(cached, Mapping):
        return cached
    rq_text = ""
    if research_question:
        rq_text = str(research_question).strip()
    if not rq_text:
        for key in ("research_question", "question", "prompt", "task"):
            v = protocol.get(key)
            if v and str(v).strip():
                rq_text = str(v).strip()
                break
    constraints: dict[str, Any] = {}
    if rq_text:
        try:
            from src.polaris_graph.instruction.constraint_extractor import (  # noqa: PLC0415
                extract_constraints,
            )
            extracted = extract_constraints(
                rq_text,
                max_tokens=int(resolve("PG_EXTRACTION_MAX_TOKENS")),
            )
            if isinstance(extracted, Mapping):
                constraints = dict(extracted)
        except Exception as exc:  # noqa: BLE001 - fail-open: no RQ constraints => empty plan
            logger.info(
                "[rq_eligibility] constraint extraction unavailable (%s); "
                "caching empty constraints (byte-identical selection)", exc,
            )
            constraints = {}
    protocol["_rq_constraints"] = constraints
    return constraints


def build_rq_eligibility(
    protocol: "dict[str, Any] | None",
    evidence_rows: "list[Any] | None",
    research_question: "str | None" = None,
) -> RQEligibilityPlan:
    """Build the RQ-source-eligibility plan for one corpus (LEVER B).

    Reads the constraints the RQ itself stated from ``protocol['_rq_constraints']`` (the
    ``constraint_extractor`` output: ``source_types`` / ``languages`` / ``recency``) and demotes
    each citable row that is DEFINITIVELY ineligible under one of them. When the cache is absent it
    is populated once via :func:`ensure_rq_constraints`. Returns an EMPTY plan when the enforce flag
    is OFF, when the RQ yields no cached constraints, or when the RQ states no
    source/language/recency constraint (byte-identical). Pure; never raises."""
    plan = RQEligibilityPlan()
    if not eligibility_enabled():
        return plan
    if not protocol:
        return plan
    rows = list(evidence_rows or [])
    if not rows:
        return plan

    rq = ensure_rq_constraints(protocol, research_question)
    if not isinstance(rq, Mapping):
        return plan

    source_types = [str(x) for x in (rq.get("source_types") or []) if str(x).strip()]
    languages = [str(x).strip().lower()[:2] for x in (rq.get("languages") or []) if str(x).strip()]
    recency = rq.get("recency")

    admitted = _admitted_genres(source_types)
    # A recency phrase carries a comparator DIRECTION ("before"/"until"/"up to" => upper bound;
    # "after"/"since"/"from"/"newer than" => lower bound) and one or two stated 4-digit years.
    # Parse BOTH bounds generically from the RQ's OWN words so an "after"-style phrase is not
    # applied as a "before" (the inversion bug). FAIL-OPEN on a purely relative phrase carrying no
    # resolvable year (no bound a row can be proven to violate).
    recency_floor, recency_ceiling = _parse_recency_bounds(recency)

    have_constraint = bool(
        admitted or languages or recency_floor is not None or recency_ceiling is not None
    )
    if not have_constraint:
        return plan

    _dw = demote_weight()

    for row in rows:
        url = _row_url(row)
        if not url:
            continue

        ineligible_reasons: list[str] = []
        unresolved = False

        # ── source-type eligibility ──
        if admitted is not None:
            genre = _row_genre(row)
            if genre == DocumentType.UNKNOWN:
                unresolved = True  # unknown genre => fail-open, flag for fetch recovery
            elif genre not in admitted:
                ineligible_reasons.append(
                    f"source_type: genre={genre.value} not in requested "
                    f"{sorted(g.value for g in admitted)}"
                )

        # ── language eligibility (fail-open when unknown) ──
        if languages:
            lang = _row_language(row)
            if lang is None:
                unresolved = True  # unknown language => fail-open
            elif lang not in languages:
                ineligible_reasons.append(
                    f"language: row={lang} not in requested {languages}"
                )

        # ── recency eligibility (fail-open when undated) ──
        if recency_floor is not None or recency_ceiling is not None:
            yr = _row_year(row)
            if yr is None:
                unresolved = True  # undated => fail-open
            else:
                if recency_floor is not None and yr < recency_floor:
                    ineligible_reasons.append(
                        f"recency: year={yr} < floor={recency_floor}"
                    )
                if recency_ceiling is not None and yr > recency_ceiling:
                    ineligible_reasons.append(
                        f"recency: year={yr} > ceiling={recency_ceiling}"
                    )

        if ineligible_reasons:
            plan.url_to_eligibility_weight[url] = _dw
            plan.ineligible_urls.add(url)
            plan.eligibility_records.append({
                "source_url": url,
                "action": "demoted_ineligible_kept",
                "weight": _dw,
                "reasons": ineligible_reasons,
            })
        elif unresolved:
            # KEPT at full weight (fail-open), but flagged so the operator can fetch-recover the
            # missing genre/language/date signal (disclosure, NOT a demote or drop).
            plan.fetch_recovery_urls.add(url)

    if not plan.is_empty():
        logger.info(
            "[rq_eligibility] LEVER B: demoted=%d ineligible source(s) "
            "(kept at weight=%.2f, sorted last — §-1.3 disclose, NOT dropped); "
            "flagged_for_fetch_recovery=%d (source_types=%s languages=%s "
            "recency_floor=%s recency_ceiling=%s)",
            len(plan.url_to_eligibility_weight), _dw, len(plan.fetch_recovery_urls),
            source_types or None, languages or None, recency_floor, recency_ceiling,
        )
    return plan


def build_rq_eligibility_from_constraints(
    constraints: "Mapping[str, Any] | None",
    evidence_rows: "list[Any] | None",
) -> RQEligibilityPlan:
    """Build the same keep-all weight plan from already-extracted prompt constraints.

    Unlike :func:`build_rq_eligibility`, this pure entry point has no feature-gate or
    live-extraction side effect.  It exists for callers that have already run the
    shared constraint extractor asynchronously and activate behavior under their own
    central gate.  Every row is retained; the result contains weights and disclosure
    records only.
    """

    plan = RQEligibilityPlan()
    if not isinstance(constraints, Mapping):
        return plan
    rows = list(evidence_rows or [])
    if not rows:
        return plan

    source_types = [
        str(x) for x in (constraints.get("source_types") or []) if str(x).strip()
    ]
    languages = [
        str(x).strip().lower()[:2]
        for x in (constraints.get("languages") or [])
        if str(x).strip()
    ]
    admitted = _admitted_genres(source_types)
    recency_floor, recency_ceiling = _parse_recency_bounds(constraints.get("recency"))
    if not (admitted or languages or recency_floor is not None or recency_ceiling is not None):
        return plan

    weight = demote_weight()
    for row in rows:
        url = _row_url(row)
        # A stable evidence id is a safe local key for prebuilt corpora whose URL
        # metadata is absent; selector callers still naturally key by URL.
        key = url or str(_field(row, "evidence_id") or "")
        if not key:
            continue
        reasons: list[str] = []
        unresolved = False
        if admitted is not None:
            genre = _row_genre(row)
            if genre == DocumentType.UNKNOWN:
                unresolved = True
            elif genre not in admitted:
                reasons.append(
                    f"source_type: genre={genre.value} not in requested "
                    f"{sorted(g.value for g in admitted)}"
                )
        if languages:
            language = _row_language(row)
            if language is None:
                unresolved = True
            elif language not in languages:
                reasons.append(f"language: row={language} not in requested {languages}")
        if recency_floor is not None or recency_ceiling is not None:
            year = _row_year(row)
            if year is None:
                unresolved = True
            else:
                if recency_floor is not None and year < recency_floor:
                    reasons.append(f"recency: year={year} < floor={recency_floor}")
                if recency_ceiling is not None and year > recency_ceiling:
                    reasons.append(f"recency: year={year} > ceiling={recency_ceiling}")
        if reasons:
            plan.url_to_eligibility_weight[key] = weight
            plan.ineligible_urls.add(key)
            plan.eligibility_records.append({
                "source_url": url,
                "evidence_id": str(_field(row, "evidence_id") or ""),
                "action": "demoted_ineligible_kept",
                "weight": weight,
                "reasons": reasons,
            })
        elif unresolved:
            plan.fetch_recovery_urls.add(key)
    return plan
