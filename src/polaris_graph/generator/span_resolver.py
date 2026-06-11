"""I-perm-004 (#1198) span resolver — re-anchor a claim to the best ENTAILING span.

The verifier drops a large share of real claims because the [#ev] token points at a span that
does not entail the sentence even though a genuinely-entailing span sits ELSEWHERE in the SAME row
(drb_76: 40 verified / 41 dropped of 81, 29 of them `entailment_failed` with in-row support). The
existing recovery (`provenance_generator._try_reanchor`, #1189) accepts the FIRST passing candidate
with no boilerplate filter and no best-span ranking — so drb_76 re-anchored to the row TITLE
(`reanchored:...0-76`). This module replaces first-passing with a BOILERPLATE-AWARE ARGMAX over the
candidate spans, choosing the best genuinely-entailing prose span (RARR re-point; ALCE precision;
MiniCheck max-over-evidence).

SAFETY — the §-1.1-lethal failure here is MANUFACTURING support (re-pointing to a span that does not
actually entail the sentence). Three structural guards make that impossible:
  1. The resolver NEVER decides entailment itself — the injected ``judge_fn`` (the SAME binding
     entailment gate the pipeline uses, run with ``allow_local_window_fallback=False``) does. The
     resolver only CHOOSES among candidates the judge already accepted; a non-entailing span can
     never be returned.
  2. Boilerplate (title / header / affiliation / nav-link / url / altmetric / reference-list) is a
     DEPRIORITIZATION + confidence PENALTY, never a fabrication path: a claim supported only by a
     title span is returned LABELED low-confidence with ``provenance_quality="title"`` so the caller
     ships it caveated, never silently VERIFIED.
  3. Confidence is dominated by entailment + numeric-verbatim agreement, NOT lexical similarity, so a
     lexically-similar-but-boilerplate span cannot inflate a claim.

PURE: no network, no LLM, no global state. The judge and (optional) numeric-match predicates are
INJECTED, so this module is deterministic and unit-testable with a stub judge. Default behaviour is
opt-in at the call site (the wiring slice gates it behind ``PG_PROVENANCE_REANCHOR``); this module
itself only computes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

# --- provenance_quality vocabulary (Decision B schema) -------------------------------------
QUALITY_PROSE = "prose"
QUALITY_TITLE = "title"
QUALITY_HEADER = "header"
QUALITY_AFFILIATION = "affiliation"
QUALITY_NAV_LINK = "nav_link"
QUALITY_URL = "url"
QUALITY_ALTMETRIC = "altmetric"
QUALITY_REFERENCE_LIST = "reference_list"

# Boilerplate qualities — supported-only-here => LABELED low confidence, never silently verified.
_BOILERPLATE_QUALITIES = frozenset(
    {
        QUALITY_TITLE,
        QUALITY_HEADER,
        QUALITY_AFFILIATION,
        QUALITY_NAV_LINK,
        QUALITY_URL,
        QUALITY_ALTMETRIC,
        QUALITY_REFERENCE_LIST,
    }
)

# Per-quality confidence penalty (subtracted from the entailment-dominated base). Prose = no penalty;
# the further a span is from real prose, the larger the penalty so a boilerplate-supported claim can
# never read as high-confidence. Ranking prefers the SMALLEST penalty (best quality) among entailing
# candidates.
_QUALITY_PENALTY = {
    QUALITY_PROSE: 0.0,
    QUALITY_AFFILIATION: 0.35,
    QUALITY_TITLE: 0.45,
    QUALITY_HEADER: 0.50,
    QUALITY_REFERENCE_LIST: 0.55,
    QUALITY_NAV_LINK: 0.60,
    QUALITY_ALTMETRIC: 0.60,
    QUALITY_URL: 0.65,
}

# --- deterministic boilerplate detection patterns -----------------------------------------
_URL_RE = re.compile(r"https?://|www\.\w|\bdoi\.org/|\b10\.\d{4,9}/", re.IGNORECASE)
_ALTMETRIC_RE = re.compile(
    r"\baltmetric\b|\bmendeley\b|\btweeted\b|\bdimensions\b|\bcited by\b|"
    r"\breaders on\b|\bsocial media\b|\bbadge\b",
    re.IGNORECASE,
)
# A reference-list line: leading numbered/bracketed ref marker, or a dense author-year + doi/pp block.
_REFERENCE_RE = re.compile(
    r"^\s*(?:\[\d+\]|\d+\.)\s+\w|(?:\bet al\.).{0,80}?(?:\(\d{4}\)|doi:|pp?\.\s?\d)",
    re.IGNORECASE,
)
_AFFILIATION_RE = re.compile(
    r"\bdepartment of\b|\buniversity of\b|\bfaculty of\b|\binstitute of\b|"
    r"\bcorrespondence\b|\bcorresponding author\b|\borcid\b|\b[\w.]+@[\w.]+\b|"
    r"\bhospital\b.{0,40}\b(?:road|street|ave|avenue)\b",
    re.IGNORECASE,
)
# Nav chrome KEYWORDS: "skip to", "menu", cookie banners, journal-site link labels.
_NAV_RE = re.compile(
    r"\bskip to (?:main )?content\b|\bcookie\b.{0,30}\b(?:consent|policy|accept)\b|"
    r"\bsign in\b|\bmain menu\b|\btable of contents\b|\bback to top\b|\bsubmit manuscript\b|"
    r"\bauthor guidelines\b|\bfor authors\b|\beditorial board\b|\bcurrent issue\b|"
    r"\bcontact us\b|\babout the journal\b",
    re.IGNORECASE,
)
# Nav chrome STRUCTURE: a pipe/bullet-separated link list ("home | articles | archives | about" OR
# the compact "home|articles|archive|podcasts"). Two or more separators is a link bar, not prose
# (Codex slice-1 P2 — the keyword set alone missed the pipe-list form, and the whitespace-required
# form missed the compact bar; both would classify as prose@conf-1.0). Whitespace around the
# separator is optional.
_NAV_SEPARATOR_RE = re.compile(r"\s*[|•·▪»]\s*")
_SENTENCE_TERMINATOR_RE = re.compile(r"[.!?](?:\s|$)|[:;]\s")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
# A real prose sentence is reasonably long AND ends like a sentence; a title/header is short and has
# no terminal punctuation. These thresholds only steer the prose/title/header split — boilerplate
# patterns above take precedence.
_TITLE_MAX_CHARS = 140
_PROSE_MIN_WORDS = 8


def classify_span(text: str) -> str:
    """Deterministically classify a candidate span's TEXT into a ``provenance_quality`` bucket.

    Boilerplate patterns (url / altmetric / reference-list / affiliation / nav) take precedence;
    otherwise a short, terminator-free fragment is a title/header and a longer sentence-shaped
    fragment is prose. Never raises; empty/whitespace -> ``header`` (uninformative boilerplate).
    """
    stripped = (text or "").strip()
    if not stripped:
        return QUALITY_HEADER
    # Specific boilerplate patterns first (a reference line / affiliation may itself embed a DOI/URL,
    # so the URL bucket is checked LAST among boilerplate).
    if _ALTMETRIC_RE.search(stripped):
        return QUALITY_ALTMETRIC
    if _NAV_RE.search(stripped) or len(_NAV_SEPARATOR_RE.findall(stripped)) >= 2:
        return QUALITY_NAV_LINK
    if _REFERENCE_RE.search(stripped):
        return QUALITY_REFERENCE_LIST
    if _AFFILIATION_RE.search(stripped):
        return QUALITY_AFFILIATION
    words = _WORD_RE.findall(stripped)
    if _URL_RE.search(stripped):
        # A prose sentence that merely contains a trailing citation URL is still prose; a span whose
        # bulk IS the URL is url-boilerplate. Heuristic: URL match AND few sentence words / mostly
        # non-letters.
        letters = sum(c.isalpha() for c in stripped)
        if len(words) < _PROSE_MIN_WORDS or letters < len(stripped) * 0.55:
            return QUALITY_URL
    has_terminator = bool(_SENTENCE_TERMINATOR_RE.search(stripped))
    # Title-case ratio: titles/headers are Title Case (most content words capitalized); prose is
    # sentence case (only the first word + proper nouns). This is the primary prose/title signal —
    # it separates an 8-word TITLE ("Saccharomyces boulardii Fungemia: A Safety Concern.") from an
    # 8-word prose sentence even when both carry punctuation.
    alpha = [w for w in words if len(w) > 2]
    cap_ratio = (sum(1 for w in alpha if w[0].isupper()) / len(alpha)) if alpha else 0.0
    is_title_case = cap_ratio >= 0.45
    if is_title_case and len(stripped) <= _TITLE_MAX_CHARS:
        return QUALITY_HEADER if stripped.endswith(":") or len(words) <= 3 else QUALITY_TITLE
    if len(words) >= _PROSE_MIN_WORDS and (has_terminator or len(stripped) > _TITLE_MAX_CHARS):
        return QUALITY_PROSE
    # Short, terminator-free fragment: a heading if it has a colon / is very short, else a title.
    if len(stripped) <= _TITLE_MAX_CHARS and not has_terminator:
        return QUALITY_HEADER if stripped.endswith(":") or len(words) <= 3 else QUALITY_TITLE
    return QUALITY_PROSE


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "") if len(w) > 2}


def _lexical_overlap(sentence: str, span_text: str) -> float:
    """Cheap content-word Jaccard for PRE-ranking only (never the binding signal)."""
    a, b = _content_words(sentence), _content_words(span_text)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class SpanResolution:
    """The argmax entailing span for one claim (or ``None`` when nothing in-row entails)."""

    best_span: tuple[int, int]
    span_text: str
    provenance_quality: str
    confidence: float
    entailed: bool


# Entailment-dominated confidence base, then subtract the boilerplate penalty and (optionally) a
# numeric-mismatch penalty, then add a small lexical-overlap nudge that can never by itself promote
# a span. Clamped to [0, 1]. Tuned so prose-entailed >= ~0.7 (moderate/high) and boilerplate-entailed
# <= ~0.55 (low), keeping the §-1.1 invariant that a title-only-supported claim is never high.
_ENTAILED_BASE = 1.0
_NUMERIC_MISMATCH_PENALTY = 0.25
_LEXICAL_NUDGE = 0.05


def _span_confidence(
    quality: str,
    lexical: float,
    *,
    numeric_ok: bool,
) -> float:
    confidence = _ENTAILED_BASE - _QUALITY_PENALTY.get(quality, 0.6)
    if not numeric_ok:
        confidence -= _NUMERIC_MISMATCH_PENALTY
    confidence += _LEXICAL_NUDGE * max(0.0, min(1.0, lexical))
    return max(0.0, min(1.0, confidence))


def resolve_best_entailing_span(
    direct_quote: str,
    sentence: str,
    candidate_spans: list[tuple[int, int]],
    *,
    judge_fn: Callable[[str, tuple[int, int], str], bool],
    numeric_match_fn: Optional[Callable[[str, str], bool]] = None,
    top_k: int = 4,
) -> Optional[SpanResolution]:
    """Choose the best genuinely-ENTAILING span for ``sentence`` within ``direct_quote``.

    ``candidate_spans`` are ``(start, end)`` slices of ``direct_quote`` (caller supplies them, e.g.
    via ``provenance_generator._reanchor_candidate_spans``). The candidates are PRE-ranked cheaply by
    (prose-first, lexical overlap); only the top ``top_k`` are handed to ``judge_fn`` (bounded judge
    calls). ``judge_fn(sentence, span, span_text) -> bool`` is the BINDING gate — the wiring passes a
    closure that RE-BINDS the [#ev] token to ``span`` and runs the SAME full faithfulness gate
    (content + numeric + entailment, ``allow_local_window_fallback=False``), so the resolver returns
    ONLY a span the gate accepted and a non-entailing span can never be manufactured into support.
    The span OFFSETS are passed (not just the text) precisely so the judge can re-bind. Among
    accepted candidates the ARGMAX prefers higher provenance quality (prose over boilerplate) then
    higher confidence. Returns ``None`` when no candidate is accepted (caller keeps the drop /
    labels "no grounded source").

    ``numeric_match_fn(sentence, span_text) -> bool`` (optional) lets the caller require the
    sentence's numbers to appear verbatim in the chosen span; a mismatch lowers confidence (never
    promotes). When omitted, numeric agreement is treated as satisfied (no adjustment).
    """
    n = len(direct_quote or "")
    # Each entry: (prerank_key, (start, end), span_text, quality, lexical).
    scored: list[tuple[tuple[float, float], tuple[int, int], str, str, float]] = []
    for start, end in candidate_spans:
        if not (0 <= start < end <= n):
            continue
        span_text = direct_quote[start:end]
        if not span_text.strip():
            continue
        quality = classify_span(span_text)
        lexical = _lexical_overlap(sentence, span_text)
        # PRE-rank key: prose first (smallest penalty), then lexical overlap. This only orders which
        # top_k reach the judge; it never decides entailment.
        prerank = (-_QUALITY_PENALTY.get(quality, 0.6), lexical)
        scored.append((prerank, (start, end), span_text, quality, lexical))

    # Pre-rank descending and judge ONLY the top_k (bounded judge calls).
    scored.sort(key=lambda r: r[0], reverse=True)
    best: Optional[SpanResolution] = None
    best_key: tuple[float, float] = (-1.0, -1.0)
    for _prerank, span, span_text, quality, lexical in scored[: max(1, top_k)]:
        if not judge_fn(sentence, span, span_text):
            continue
        numeric_ok = True if numeric_match_fn is None else numeric_match_fn(sentence, span_text)
        confidence = _span_confidence(quality, lexical, numeric_ok=numeric_ok)
        # ARGMAX: prefer best quality (smallest penalty), then highest confidence.
        key = (-_QUALITY_PENALTY.get(quality, 0.6), confidence)
        if key > best_key:
            best_key = key
            best = SpanResolution(
                best_span=span,
                span_text=span_text,
                provenance_quality=quality,
                confidence=confidence,
                entailed=True,
            )
    return best


def is_boilerplate_quality(quality: str) -> bool:
    """True if ``quality`` is a boilerplate bucket (supported-only-here => label low, never verify)."""
    return quality in _BOILERPLATE_QUALITIES
