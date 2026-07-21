"""LEVER B — upstream CITATION RE-ANCHORING (primary-source grounding selection).

When a claim sentence's cited ``[#ev]`` token points at a SECONDARY source (e.g. a news article
or blog restating a finding) but a PRIMARY row for the SAME fact — same normalized finding /
numbers, higher credibility tier, and a primary scholarly genre (or a non-contradictory
``is_journal_article`` sidecar) — exists in the SAME evidence pool, this helper re-points the
sentence's grounding token to the PRIMARY row.

This is an UPSTREAM grounding-SOURCE selection performed BEFORE strict_verify runs. It is NOT a
post-generation entailment / verification / sentence-drop / filtering gate: it never removes a
sentence, never drops a citation, never edits prose beyond swapping ONE evidence id for a
strictly-better one that grounds the SAME numbers. If no better primary exists, the token is left
exactly as-is.

Generalization: "primary vs secondary" is decided GENERICALLY from each row's tier + document
genre — a primary scholarly genre, or a non-contradictory ``is_journal_article`` sidecar; a bare
DOI never qualifies on its own (via the field-agnostic classifiers) — plus a numeric/keyword-overlap
match of the claim's own content — there are NO task literals. The re-anchor target must corroborate the
SAME salient numbers the sentence states, so the swap can only ever strengthen grounding.

Default OFF: ``PG_CITATION_REANCHOR_PRIMARY`` empty/falsey => ``reanchor_citation`` /
``reanchor_sentences`` return their input UNCHANGED (byte-identical tokens).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Mapping, Optional, Sequence

from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.citation_reanchor")

_ENABLE_FLAG = "PG_CITATION_REANCHOR_PRIMARY"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

# Tier ordinal: lower = stronger (mirrors evidence_selector._TIER_PRIORITY).
_TIER_PRIORITY: dict[str, int] = {
    "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5, "T6": 6, "T7": 7, "UNKNOWN": 8,
}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?%?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
# A number immediately followed by a unit/currency/percent token — the STRUCTURAL fingerprint of a
# quantitative fact. Generic; matches "12.5%", "3 mg", "$4.2 billion", "2020 patients", etc.
_NUM_UNIT_RE = re.compile(
    r"[$€£¥]?-?\d+(?:[.,]\d+)?\s?(?:%|percent|percentage points?|pp|"
    r"[a-zµμ]{1,6}(?:/[a-z]{1,6})?|billion|million|thousand|trillion|k|m|bn)?",
    re.IGNORECASE,
)

# Generic English stopwords — NEVER counted toward same-fact keyword overlap (the bug: an unrelated
# news row shared only "the"/"for"). Domain-neutral; NO task literals.
_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "into", "onto", "over", "under",
    "was", "were", "has", "have", "had", "are", "been", "being", "its", "their", "them",
    "which", "while", "when", "where", "what", "who", "whom", "than", "then", "there",
    "these", "those", "such", "some", "any", "all", "one", "two", "not", "but", "our",
    "your", "his", "her", "out", "per", "via", "also", "more", "most", "less", "least",
    "about", "between", "among", "during", "after", "before", "since", "until", "each",
    "other", "both", "same", "will", "would", "could", "should", "may", "might", "can",
    "study", "studies", "found", "shows", "showed", "report", "reported", "according",
})


def reanchor_enabled() -> bool:
    """LEVER B re-anchoring kill-switch. DEFAULT OFF => the re-anchor functions are no-ops =>
    every ``[#ev]`` token is byte-identical."""
    raw = (resolve(_ENABLE_FLAG) or "").strip().lower()
    return raw not in _OFF_VALUES


def _get(row: "Any", *names: str) -> "Any":
    if isinstance(row, Mapping):
        for n in names:
            if n in row and row.get(n) is not None:
                return row.get(n)
        return None
    for n in names:
        v = getattr(row, n, None)
        if v is not None:
            return v
    return None


def _tier_rank(row: "Any") -> int:
    return _TIER_PRIORITY.get(str(_get(row, "tier") or "UNKNOWN"), 8)


# PRIMARY scholarly genres: peer-reviewed articles, reviews, preprints, conference & working
# papers — the genres that constitute a PRIMARY grounding source. Field-agnostic; NO task literals.
_PRIMARY_GENRES: frozenset[str] = frozenset({
    "JOURNAL_ARTICLE", "REVIEW_ARTICLE", "PREPRINT", "CONFERENCE_PAPER", "WORKING_PAPER",
})
# Genres that are DEFINITIVELY NOT primary sources even when they carry a DOI (news outlets,
# press releases, blogs, encyclopedias, UGC, and predatory OA all mint/echo DOIs). A DOI on one
# of these NEVER promotes it to primary — the exact bug: a DOI-bearing NEWS row read as primary.
_NON_PRIMARY_GENRES: frozenset[str] = frozenset({
    "NEWS", "PRESS_RELEASE", "BLOG_COMMENTARY", "ENCYCLOPEDIA", "UGC",
    "PREDATORY_OA_JOURNAL", "DATASET",
})


def _genre(row: "Any") -> str:
    """The row's pre-stamped document genre (uppercased), or ``""`` when unknown."""
    dt = str(_get(row, "document_type") or "").upper().strip()
    return dt


def _is_primary_source(row: "Any") -> bool:
    """True iff the row is a GENUINE PRIMARY grounding source, decided by a POSITIVE primary
    signal — a primary scholarly GENRE (journal / review / preprint / conference / working paper),
    or the classifier's ``is_journal_article`` sidecar on a row whose genre is NOT known-non-primary.

    A resolved DOI is NEVER sufficient on its own — news outlets, press releases, blogs, datasets and
    predatory journals all mint/echo DOIs, so neither a bare DOI nor a contradictory
    ``is_journal_article`` sidecar can promote a KNOWN non-primary genre. Precedence (order matters):
      1. a KNOWN non-primary genre (news/press-release/blog/…) => NOT primary — DECISIVE and checked
         FIRST, so a contradictory ``is_journal_article`` sidecar or a bare DOI never overrides it;
      2. a primary scholarly genre => PRIMARY;
      3. the ``is_journal_article`` sidecar on a not-known-non-primary row => PRIMARY;
      4. otherwise (unknown/absent genre, no positive signal) => NOT primary — a bare DOI alone is
         insufficient (news/press/blog/dataset/predatory all carry DOIs).
    Field-agnostic; NO task literals; fail-closed to False when there is no positive primary signal.
    """
    g = _genre(row)
    # (1) A KNOWN non-primary genre is decisive and checked FIRST — a contradictory
    #     is_journal_article sidecar or a bare DOI can never promote a NEWS/press/blog/dataset row.
    if g in _NON_PRIMARY_GENRES:
        return False
    # (2) A primary scholarly genre is a positive primary signal.
    if g in _PRIMARY_GENRES:
        return True
    # (3) The is_journal_article sidecar counts ONLY now that a known non-primary genre is ruled out.
    if _get(row, "is_journal_article") is True:
        return True
    # (4) Unknown/absent genre with no positive primary signal: a bare DOI is NOT sufficient.
    return False


def _row_text(row: "Any") -> str:
    return " ".join(
        str(_get(row, k) or "") for k in ("statement", "direct_quote", "quote", "text", "title")
    )


def _verifier_haystack(row: "Any") -> str:
    """The EXACT text the downstream span resolver searches when it re-derives a cited span's
    offsets: the row's ``direct_quote``, else its ``statement`` (mirrors
    ``verified_compose._member_global_span``: ``row.get("direct_quote") or row.get("statement")``).

    The ``required_substring`` faithfulness guard MUST match against THIS haystack — NOT the wider
    ``_row_text`` (which folds in ``title``/``quote``/``text``). A candidate that carries the cited
    span only in its TITLE would pass a ``_row_text`` check yet FAIL span resolution (the resolver
    never looks at the title), leaving the swapped token unresolvable and dropped by strict_verify.
    """
    return str(_get(row, "direct_quote") or "") or str(_get(row, "statement") or "")


def _numbers(text: str) -> set[str]:
    return {m.rstrip("%") for m in _NUM_RE.findall(text or "")}


def _num_units(text: str) -> set[str]:
    """The STRUCTURAL numeric+unit fingerprints in a text (e.g. '12.5%', '3mg'). Whitespace and
    case normalized so 'the 3 mg dose' and 'a 3mg tablet' fingerprint identically."""
    out: set[str] = set()
    for m in _NUM_UNIT_RE.findall(text or ""):
        s = re.sub(r"\s+", "", str(m)).strip().lower().rstrip(".,")
        if s and any(ch.isdigit() for ch in s):
            out.add(s)
    return out


def _keywords(text: str) -> set[str]:
    """Content keywords, EXCLUDING generic stopwords (so 'the'/'for' never count as a match)."""
    return {
        w.lower() for w in _WORD_RE.findall(text or "")
        if w.lower() not in _STOPWORDS
    }


def is_more_primary(candidate: "Any", current: "Any") -> bool:
    """True iff ``candidate`` is a STRICTLY stronger PRIMARY grounding source than ``current``.

    The candidate must ITSELF be a primary source (a primary scholarly GENRE, or a non-contradictory
    ``is_journal_article`` sidecar — a bare DOI is NOT enough) — a merely-lower-tier row that is NOT
    primary is never accepted. Given that, it wins when
    it has a better (lower) tier, OR the same tier while carrying a primary-genre advantage the
    current lacks. Conservative — ties that don't strictly improve return False (no swap)."""
    # Hard gate: the candidate must be a GENUINE PRIMARY source (primary scholarly GENRE — a DOI
    # alone is NOT primary, so a DOI-bearing NEWS/press-release/blog row is rejected here). A
    # lower-tier but non-primary row (e.g. a higher-authority NEWS outlet) is NOT an anchor target.
    cand_primary = _is_primary_source(candidate)
    if not cand_primary:
        return False
    ct, rt = _tier_rank(candidate), _tier_rank(current)
    if ct < rt:
        return True
    if ct > rt:
        return False
    # same tier: only swap when the candidate is primary AND the current is NOT (a real upgrade).
    cur_primary = _is_primary_source(current)
    return not cur_primary


def _same_fact(sentence: str, current: "Any", candidate: "Any") -> bool:
    """True iff ``candidate`` grounds the SAME salient fact as the sentence + ``current`` source.

    STRUCTURAL match, using the claim's OWN text (the ``sentence``) plus the ``current`` row's text:
      1. numeric+unit identity — every numeric+unit fingerprint the claim states must also appear
         in the candidate (so the swap can only re-ground the SAME figures+units); AND the candidate
         must corroborate the claim's content keywords (stopwords excluded). OR
      2. when the claim states NO numeric+unit fact, a STRONG content-keyword overlap between the
         claim (unioned with the current row's own keywords) and the candidate — well above the
         2-generic-word floor that produced the false re-anchor.

    Conservative: two generic shared words can NEVER satisfy this (stopwords are excluded and the
    threshold scales with the claim length). An ambiguous match returns False (no swap)."""
    s_nums = _num_units(sentence)
    cand_text = _row_text(candidate)
    cand_nums = _num_units(cand_text)
    s_kw = _keywords(sentence)
    cand_kw = _keywords(cand_text)

    if s_nums:
        # Every quantitative fingerprint in the claim must be corroborated by the candidate.
        if not s_nums.issubset(cand_nums):
            return False
        # Plus at least one shared content keyword so we don't match on the number alone
        # (a bare "2023" appearing in an unrelated row must not qualify).
        return len(s_kw & cand_kw) >= 1

    # No numeric fact in the claim: require a STRONG non-stopword keyword overlap. Union the
    # current row's own keywords so a terse claim still carries enough signal; the candidate must
    # share a substantial fraction — never just two generic words.
    ref_kw = s_kw | _keywords(_row_text(current))
    if not ref_kw:
        return False
    overlap = len(ref_kw & cand_kw)
    # Absolute floor of 3 real content words AND ~40% of the claim's own keywords.
    kw_floor = max(3, (len(s_kw) + 1) // 2)
    return overlap >= kw_floor and (not s_kw or len(s_kw & cand_kw) >= 1)


def reanchor_citation(
    *,
    sentence: str,
    current_ev_id: "str | None",
    evidence_pool: "Mapping[str, Any] | Sequence[Any]",
    id_of: "Optional[Callable[[Any], str]]" = None,
    required_substring: "str | None" = None,
) -> "str | None":
    """Return the ev-id the sentence SHOULD cite: the current id UNCHANGED unless a strictly-more-
    primary pool row grounds the SAME fact, in which case that row's id. Pure; never raises.

    ``evidence_pool`` may be a mapping ``ev_id -> row`` or a sequence of rows (then ``id_of`` must
    extract each row's id, defaulting to ``row['ev_id']`` / ``row.ev_id``). OFF (default) or no
    resolvable current row => returns ``current_ev_id`` unchanged (byte-identical).

    ``required_substring``: when set (the compose wiring passes the member's verbatim
    ``direct_quote``), the candidate row's text MUST CONTAIN it — so the cited span still resolves
    against the new row and the UNCHANGED ``strict_verify`` still passes. Guarantees the swap only
    re-points to a row that literally carries the same quoted span (faithfulness preserved)."""
    if not reanchor_enabled():
        return current_ev_id
    if not current_ev_id:
        return current_ev_id

    # Normalize the pool to an (id, row) list.
    if isinstance(evidence_pool, Mapping):
        items = list(evidence_pool.items())
    else:
        def _default_id(r: "Any") -> str:
            return str(_get(r, "ev_id", "id") or "")
        _idf = id_of or _default_id
        items = [(_idf(r), r) for r in (evidence_pool or [])]
    by_id = {str(i): r for (i, r) in items if str(i)}

    current = by_id.get(str(current_ev_id))
    if current is None:
        return current_ev_id  # can't compare -> leave as-is (fail-open)

    req = str(required_substring) if required_substring else ""

    best_id = str(current_ev_id)
    best_row = current
    for cand_id, cand in items:
        cand_id = str(cand_id)
        if not cand_id or cand_id == str(current_ev_id) or cand is current:
            continue
        # Faithfulness guard: the candidate must literally contain the cited span text in the
        # EXACT verifier haystack (direct_quote|statement) the downstream span resolver searches —
        # NOT the wider _row_text (title/quote/text). A candidate carrying the span only in its
        # title would otherwise be accepted, then fail span resolution and get dropped.
        if req and req not in _verifier_haystack(cand):
            continue
        if is_more_primary(cand, best_row) and _same_fact(sentence, current, cand):
            best_id, best_row = cand_id, cand

    if best_id != str(current_ev_id):
        logger.info(
            "[citation_reanchor] LEVER B: re-anchored citation %s -> %s "
            "(same fact, stronger primary source) BEFORE strict_verify",
            current_ev_id, best_id,
        )
    return best_id


def reanchor_sentences(
    sentences: "Sequence[tuple[str, str | None]]",
    evidence_pool: "Mapping[str, Any] | Sequence[Any]",
    id_of: "Optional[Callable[[Any], str]]" = None,
) -> "list[tuple[str, str | None]]":
    """Batch helper: re-anchor a list of ``(sentence_text, cited_ev_id)`` pairs. Returns a NEW
    list with each cited id possibly swapped to a stronger primary (prose untouched). OFF (default)
    => returns pairs with UNCHANGED ids (a shallow copy — byte-identical tokens)."""
    if not reanchor_enabled():
        return list(sentences)
    out: list[tuple[str, str | None]] = []
    for text, ev_id in sentences:
        out.append((text, reanchor_citation(
            sentence=text, current_ev_id=ev_id, evidence_pool=evidence_pool, id_of=id_of,
        )))
    return out
