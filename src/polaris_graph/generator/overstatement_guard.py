"""Additive overstatement guards for the faithfulness engine (I-deepfix B16, #1360).

Basket B16 root cause: a generator paraphrase can UPGRADE the epistemic status
of a cited span (a stated modeling ASSUMPTION — "we assumed 60%" — re-rendered
as an empirical "estimate"/"finding") or SILENTLY WIDEN/MERGE a time-horizon
(a source's "over five years" reported under a different "2010-2023" window)
while the NUMBERS still match — so strict_verify's numeric leg passes and the
overstatement survives.

These are **ADDITIVE** legs layered on top of `strict_verify` /
`verify_sentence_provenance`. They only ever ADD a failure reason (a drop) or a
soft warning; they NEVER clear an existing failure and NEVER relax any existing
check. Both legs are pure, stdlib-only, network-free leaf functions so they sit
on the hot per-sentence path with zero cost; both are env-flag gated so the
default behaviour is preserved byte-for-byte when disabled.

Design (mirrors the existing `shell_detector` / `_detect_unhedged_superlative`
additive patterns in `provenance_generator`):

  1. EPISTEMIC-MARKER guard — if the cited span carries an explicit modeling /
     projection hedge (``we assumed``, ``projected``, ``modeled``, ``hypothetical
     scenario``, ``for illustration``...) then the generated paraphrase MUST
     carry an epistemic hedge too. A paraphrase that converts the assumption
     into a bare empirical assertion ("the estimate is 60%", "data show 60%")
     drops. A paraphrase that preserves ANY hedge (its own assumption-marker, an
     attribution like "the model assumes", or a generic uncertainty hedge such
     as "may"/"could") passes.

  2. TEMPORAL-SCOPE guard — when BOTH the claim sentence AND the cited span name
     an explicit time-horizon (an "over N years" duration OR a "YYYY-YYYY" year
     range), the claim's horizon must be REPRESENTED in the cited span. A claim
     that asserts a duration / year-range that the span does not contain (the
     "5-year per-firm effect" merged into a "2010-2023 window", or a widened
     duration) drops. If the span names no horizon, or the claim names none, the
     guard is inert (no false drop — the numeric/content legs already govern).
"""

from __future__ import annotations

import os
import re

# ─────────────────────────────────────────────────────────────────────────────
# Env flags (LAW VI — named, env-gated, no magic numbers).
# Default ON: these are faithfulness-TIGHTENING (they only add drops/flags).
# Setting the flag to a falsy value reverts the relevant leg to byte-identical
# pre-B16 behaviour.
# ─────────────────────────────────────────────────────────────────────────────
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on", "enforce", "warn"})


def epistemic_guard_enabled() -> bool:
    """Whether the epistemic-marker preservation leg is active (default ON)."""
    return os.getenv("PG_EPISTEMIC_MARKER_GUARD", "1").strip().lower() in _TRUE_TOKENS


def temporal_scope_guard_enabled() -> bool:
    """Whether the temporal-scope-match leg is active (default ON)."""
    return os.getenv("PG_TEMPORAL_SCOPE_GUARD", "1").strip().lower() in _TRUE_TOKENS


# ─────────────────────────────────────────────────────────────────────────────
# Epistemic markers
# ─────────────────────────────────────────────────────────────────────────────
# A span that carries one of these is making a MODELING ASSUMPTION / PROJECTION,
# not reporting an empirical observation. The verb is the strong signal; a plain
# "estimate" alone is NOT here (a published point estimate is empirical) — we
# require the assumption/projection framing.
# NARROWED to VALUE-LEVEL assumption/projection framing only (I-deepfix-001 Codex
# P1, iter 2): the bare nouns "assumption(s)" and the bare verb "model(ed/ing)"
# match EMPIRICAL statistical-method prose — "the proportional hazards
# assumption", "the normality assumption", "outcomes were modeled using logistic
# regression", "we modeled survival via Cox regression" — none of which render a
# value as a finding. Matching those default-ON would drop faithful empirical
# claims (breadth loss). The triggers below require an explicit assumption /
# projection / hypothetical / simulation FRAMING tied to a stated value, not the
# mere mention of the word "assumption" or "model" in a methods description.
_SPAN_ASSUMPTION_RE = re.compile(
    r"(?:"
    r"\bwe\s+assume(?:d|s)?\b"
    r"|\bif\s+we\s+assume\b"
    r"|\bunder\s+(?:the|an?)\s+assumption\b"
    r"|\bassuming\s+(?:a|an|the|that)\b"
    r"|\bwe\s+project(?:ed|s)?\b"
    r"|\bprojected\s+to\b"
    r"|\bhypothes(?:is|ise[ds]?|ize[ds]?|ised|ized)\b"
    r"|\bhypothetical\b"
    r"|\billustrative\b"
    r"|\bfor\s+illustration\b"
    r"|\bscenario\s+analysis\b"
    r"|\bsimulat(?:e|es|ed|ion|ions)\b"
    r")",
    re.IGNORECASE,
)

# A claim sentence preserves the epistemic status if it carries EITHER an
# explicit assumption/projection marker of its own OR a generic uncertainty
# hedge that does not over-assert empirical certainty.
_CLAIM_HEDGE_RE = re.compile(
    r"\b("
    r"assum(?:e|es|ed|ing|ption|ptions)"
    r"|project(?:ed|s|ion|ions)?"
    r"|model(?:ed|led|s|ing|ling)?"
    r"|hypothes(?:is|ise[ds]?|ize[ds]?|ised|ized)"
    r"|hypothetical(?:ly)?"
    r"|illustrative(?:ly)?"
    r"|scenario"
    r"|simulat(?:e|es|ed|ion|ions)"
    r"|estimat(?:e|es|ed|ion)"   # an "estimate" framing keeps the modeled status (vs a bare assertion)
    r"|may|might|could|would"
    r"|expect(?:ed|s)?"
    r"|forecast(?:ed|s)?"
    r"|predict(?:ed|s|ion|ions)?"
    r"|theoretical(?:ly)?"
    r")\b",
    re.IGNORECASE,
)

# Empirical-certainty verbs that, with NO hedge, STATE an assumption as a finding.
# Used only to confirm the paraphrase is making a bare assertion (precision: a
# span hedge + claim with one of these AND no claim hedge = overstatement).
_CLAIM_EMPIRICAL_RE = re.compile(
    r"\b("
    r"found|finds|showed|shows|demonstrat(?:ed|es)"
    r"|observ(?:ed|es)|report(?:ed|s)?|reveal(?:ed|s)?"
    r"|data\s+show|results?\s+show|the\s+(?:finding|evidence)"
    r"|is|are|was|were|has|have|will\s+(?:add|create|generate|produce)"
    r")\b",
    re.IGNORECASE,
)

# A number token (digits, optional decimal) used to anchor a span's assumed VALUE
# and to confirm the claim reports THAT value as a finding.
_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
# Clause boundary: an assumption marker only governs up to the next break, so a
# number AFTER the break (a downstream RESULT) is not the assumed value. A period
# between digits is a decimal point, NOT a boundary.
_CLAUSE_BOUNDARY_RE = re.compile(r"[,;:]|\.(?!\d)")


def _assumed_values_in_span(span_text: str) -> set[str]:
    """Number tokens the span frames as ASSUMED / PROJECTED VALUES.

    For each assumption/projection marker, collect the numbers that appear in the
    SAME clause (from the marker to the next clause boundary). Returns empty when a
    marker governs a non-numeric methodological condition ("assuming that censoring
    was non-informative", "under the assumption of proportional hazards") — so the
    epistemic leg stays INERT on empirical statistical-method prose (I-deepfix-001
    Codex P1).
    """
    out: set[str] = set()
    for m in _SPAN_ASSUMPTION_RE.finditer(span_text or ""):
        tail = span_text[m.end():]
        boundary = _CLAUSE_BOUNDARY_RE.search(tail)
        clause = tail[: boundary.start()] if boundary else tail
        out.update(_NUMERIC_TOKEN_RE.findall(clause))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Temporal horizons
# ─────────────────────────────────────────────────────────────────────────────
# Duration windows: "over five years", "over 5 years", "within 10 years",
# "a 5-year period", "5-year".  Captures the numeral (word or digit) + unit.
_NUMWORD = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}
_DURATION_RE = re.compile(
    r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty)"
    r"[\s-]+"
    r"(year|yr|month|week|day|decade)s?\b",
    re.IGNORECASE,
)
# Explicit calendar year ranges: "2010-2023", "2010 to 2023", "2010–2023".
_YEAR_RANGE_RE = re.compile(
    r"\b(19\d{2}|20\d{2})\s*(?:-|–|—|to|through|–)\s*(19\d{2}|20\d{2})\b",
    re.IGNORECASE,
)


def _normalize_number_word(tok: str) -> int | None:
    tok = tok.strip().lower()
    if tok.isdigit():
        return int(tok)
    return _NUMWORD.get(tok)


def _durations_in(text: str) -> set[tuple[int, str]]:
    """Set of (count, unit-singular) durations named in `text`."""
    out: set[tuple[int, str]] = set()
    for m in _DURATION_RE.finditer(text or ""):
        n = _normalize_number_word(m.group(1))
        if n is None:
            continue
        unit = m.group(2).lower().rstrip("s")
        if unit == "yr":
            unit = "year"
        out.add((n, unit))
    return out


def _year_ranges_in(text: str) -> set[tuple[int, int]]:
    """Set of (start_year, end_year) calendar ranges named in `text`."""
    out: set[tuple[int, int]] = set()
    for m in _YEAR_RANGE_RE.finditer(text or ""):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            out.add((a, b))
    return out


# Canonical magnitude (in days) for each duration unit, so equivalent horizons
# expressed in different units compare EQUAL: 12 months == 52 weeks == 1 year.
# (LAW VI: named constants, not magic numbers in the comparison.)
_DAYS_PER_YEAR = 365.0
_DAYS_PER_UNIT = {
    "day": 1.0,
    "week": 7.0,
    "month": _DAYS_PER_YEAR / 12.0,
    "year": _DAYS_PER_YEAR,
    "decade": _DAYS_PER_YEAR * 10.0,
}
# A claim horizon counts as a WIDENING only if its magnitude exceeds the span's
# LONGEST horizon by more than this relative margin. Generous on purpose: the
# guard's overriding constraint is to NEVER false-drop a legitimately-scoped
# claim — unit phrasing ("12 months" vs "one year"), rounding ("52 weeks" vs
# "one year"), and a NARROWER claim horizon must all pass; the leg fires only on
# a genuine scope-widening beyond the cited evidence.
_TEMPORAL_WIDEN_REL_TOLERANCE = 0.25


def _duration_days(count: int, unit: str) -> float:
    return float(count) * _DAYS_PER_UNIT.get(unit, _DAYS_PER_YEAR)


def _range_days(start_year: int, end_year: int) -> float:
    return float(end_year - start_year) * _DAYS_PER_YEAR


def _max_horizon_days(
    durs: set[tuple[int, str]], ranges: set[tuple[int, int]]
) -> float:
    """Longest horizon (in days) named in a text; 0.0 if none."""
    candidates = [_duration_days(n, u) for n, u in durs]
    candidates += [_range_days(a, b) for a, b in ranges]
    return max(candidates) if candidates else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Public leg API.  Each returns a failure-reason string (drop) or None (pass).
# ─────────────────────────────────────────────────────────────────────────────
def epistemic_overstatement_reason(claim: str, span_text: str) -> str | None:
    """Return a drop reason if the paraphrase strips the span's epistemic hedge.

    Fires only when:
      - the cited span explicitly frames the value as an ASSUMPTION/PROJECTION,
      - AND the claim makes a bare empirical assertion (an empirical verb),
      - AND the claim carries NO hedge of its own.
    Otherwise returns None (inert — no false drop).
    """
    if not claim or not span_text:
        return None
    # VALUE-ANCHORED (I-deepfix-001 Codex P1, iter 3->4): fire ONLY when the span
    # frames a specific VALUE as assumed/projected (a number inside the assumption
    # marker's own clause) AND the claim asserts that SAME value as a finding. A
    # methodological caveat governing a non-numeric condition ("assuming that
    # censoring was non-informative", "under the assumption of proportional
    # hazards") carries no in-clause number -> inert (no false drop on methods/
    # results prose). A claim that does not echo the assumed value -> inert.
    assumed_values = _assumed_values_in_span(span_text)
    if not assumed_values:
        return None  # no value-level assumption framing
    if _CLAIM_HEDGE_RE.search(claim):
        return None  # paraphrase preserved an epistemic hedge — faithful
    if not _CLAIM_EMPIRICAL_RE.search(claim):
        return None  # claim isn't asserting empirically; leave to other legs
    claim_numbers = set(_NUMERIC_TOKEN_RE.findall(claim))
    if not (assumed_values & claim_numbers):
        return None  # the claim does not report the assumed value as a finding
    return "epistemic_overstatement_assumption_as_finding"


# ─────────────────────────────────────────────────────────────────────────────
# Effect-size conditional/threshold guard (WS-5 FIX-b, I-deepfix-001 beat-both).
#
# The re-smoke residual D1: the Eloundou span reads
#   "...roughly 1.8% of jobs could have over half their tasks affected by LLMs...
#    When accounting for current and likely future software developments that
#    complement LLM capabilities, this share jumps to just over 46% of jobs."
# so the "46%" figure is GOVERNED by the antecedent "when accounting for future
# software developments" (a conditional) and the threshold "over half their tasks
# affected". A re-lift that renders "just over 46% of jobs are exposed to
# LLM-related technologies" keeps the NUMBER (strict_verify's numeric leg passes)
# but DROPS the governing condition — an effect-size over-claim.
#
# This leg is ANNOTATE-ONLY (§-1.3): it returns a reason so the render layer can
# APPEND a [confidence] caveat (or so the composer can carry the antecedent). It
# NEVER drops a sentence, NEVER widens a span, NEVER changes a verdict. It is NOT
# wired into strict_verify's drop path. Gated by PG_FIGURE_CONSISTENCY_ANNOTATE
# (default ON); OFF -> inert (byte-identical). Pure, stdlib-only, network-free.
# ─────────────────────────────────────────────────────────────────────────────
def figure_consistency_annotate_enabled() -> bool:
    """Whether the effect-size conditional/threshold annotate leg is active (default ON)."""
    return os.getenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1").strip().lower() in _TRUE_TOKENS


# Provenance / numbered-citation markers stripped off the CLAIM before number
# extraction, so a span offset inside "[#ev:eloundou:0-800]" or a "[7]" marker is
# never mistaken for a claimed figure.
_CLAIM_CITATION_STRIP_RE = re.compile(r"\[#ev:[^\]]+\]|\[\d+\]")

# A governing conditional / threshold token in the SPAN. When one of these
# precedes a number in the span's number-bearing sentence, that number is
# CONDITIONAL (its magnitude holds only under the stated antecedent/threshold),
# not an unconditional empirical count. The task's three canonical cues
# ("when accounting for", "could have", "over half") lead the set; the rest are
# the standard conditional/threshold/scenario framings.
_SPAN_EFFECT_CONDITION_RE = re.compile(
    r"(?:"
    r"when\s+accounting\s+for"
    r"|when\s+we\s+account\s+for"
    r"|\bcould\s+have\b"
    r"|\bover\s+half\b"
    r"|\bup\s+to\b"
    r"|\bas\s+(?:much|many)\s+as\b"
    r"|\bassum(?:e|es|ed|ing)\b"
    r"|\bif\s+(?:we|you|the|current|future)\b"
    r"|\bprovided\s+that\b"
    r"|\bunder\s+(?:the|a|an)\s+\w+\s+scenario\b"
    r"|\bhypothetical(?:ly)?\b"
    r"|\bscenario\b"
    r")",
    re.IGNORECASE,
)

# A governing condition/hedge CARRIED BY THE CLAIM. If the claim reproduces any
# of these, the antecedent travelled with the number (the paraphrase is faithful)
# -> the leg is inert (no caveat). Deliberately EXCLUDES bare epistemic verbs like
# "estimate"/"found" (those keep the value framed as a finding, NOT as conditional)
# so a bare re-lift such as "they estimate that just over 46% of jobs..." still
# fires; it targets the specific conditional/threshold antecedent only.
_CLAIM_ANTECEDENT_CARRIED_RE = re.compile(
    r"(?:"
    r"account(?:ing|s|ed)?\s+for"
    r"|\bcould\b|\bmay\b|\bmight\b|\bwould\b"
    r"|\bup\s+to\b|\bas\s+(?:much|many)\s+as\b|\bover\s+half\b"
    r"|\bif\b|\bassum(?:e|es|ed|ing)\b|\bprovided\b"
    r"|\bscenario\b|\bhypothetical(?:ly)?\b"
    r"|\bwhen\b"
    r"|future\s+(?:software|developments|technolog)"
    r")",
    re.IGNORECASE,
)

# Split the span into sentences so a conditional only governs numbers in its OWN
# sentence (a period that is NOT a decimal point is a boundary).
_SPAN_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def effect_size_conditional_reason(claim: str, span_text: str) -> str | None:
    """Return an ANNOTATE reason if the claim re-lifts a span number while dropping
    the conditional/threshold antecedent that governs it in the cited span.

    Fires only when ALL hold:
      - the leg is enabled (PG_FIGURE_CONSISTENCY_ANNOTATE, default ON),
      - the claim carries NO governing conditional/threshold of its own (a bare
        assertion — "they estimate that just over 46% of jobs are exposed..."),
      - the cited span has a sentence whose governing conditional/threshold token
        PRECEDES a number, and
      - the claim reproduces that governed number.
    Otherwise returns None (inert — no false caveat). ANNOTATE-only: the caller
    APPENDS a [confidence] caveat; this NEVER drops, widens a span, or changes a
    verdict (§-1.3).
    """
    if not figure_consistency_annotate_enabled():
        return None
    if not claim or not span_text:
        return None
    claim_bare = _CLAIM_CITATION_STRIP_RE.sub("", claim)
    claim_numbers = set(_NUMERIC_TOKEN_RE.findall(claim_bare))
    if not claim_numbers:
        return None  # no figure re-lifted — nothing to over-claim
    if _CLAIM_ANTECEDENT_CARRIED_RE.search(claim_bare):
        return None  # the claim carries the governing condition — antecedent travelled, faithful
    for sentence in _SPAN_SENTENCE_SPLIT_RE.split(span_text):
        cond = _SPAN_EFFECT_CONDITION_RE.search(sentence)
        if not cond:
            continue
        # Numbers AFTER the conditional in this sentence are the ones it governs.
        governed = set(_NUMERIC_TOKEN_RE.findall(sentence[cond.start():]))
        shared = claim_numbers & governed
        if shared:
            return "effect_size_conditional_stripped:num=" + ",".join(sorted(shared))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# One-sidedness PRIMACY advisory (I-deepfix-001 Wave-2, one-sidedness framing).
#
# A claim can headline ONE figure as the sentence's lead number while the SAME
# cited basket ALSO carries a materially-different COMPANION figure of the SAME
# measure kind that the claim omits — a primacy / one-sidedness frame. Example (the
# Eloundou exposure span): the claim leads with "1.8% of jobs exposed" while the
# basket also reports "just over 46% of tasks exposed" (the same "% of jobs/tasks
# exposed" measure). Surfacing only the small headline while the basket carries a
# far-larger same-kind companion under-states the picture.
#
# ADVISORY-ONLY (§-1.3): returns a reason so the caller APPENDS a soft-warning; it
# NEVER drops a sentence, NEVER fails is_verified, NEVER widens a span, NEVER
# changes a verdict, and NEVER drops / rewrites / alters any verified number. NOT
# wired into any drop path. Gated by PG_PRIMACY_FRAME_ANNOTATE (default ON); OFF ->
# inert (byte-identical). Pure, stdlib-only, network-free (mirrors the
# effect_size_conditional_reason leg above).
#
# HIGH-PRECISION + FAIL-OPEN. Two gates keep it inert on the ambiguous majority of
# basket numbers (sample sizes, years, CI bounds, page numbers):
#   (1) SAME UNIT — both the headline and the companion must be PERCENT figures
#       ("46%", "46 percent"); a bare digit carries no "%" so it can never be a
#       companion, and a claim with no headline percent is inert immediately.
#   (2) SAME CONTEXT — the headline's local measure context and the companion's
#       local measure context must share a content-word stem (jobs / tasks /
#       exposed), so two unrelated percentages (e.g. "46% of tasks" vs "95% CI")
#       never pair.
# PLUS a MATERIAL magnitude gap (absolute AND ratio), so rounding neighbours
# ("1.8%" vs "1.9%") never fire. A percent whose context is a confidence-interval /
# significance level is skipped outright.
# ─────────────────────────────────────────────────────────────────────────────
def primacy_frame_annotate_enabled() -> bool:
    """Whether the one-sidedness primacy annotate leg is active (default ON)."""
    return os.getenv("PG_PRIMACY_FRAME_ANNOTATE", "1").strip().lower() in _TRUE_TOKENS


# A PERCENT figure: a numeric token (the SAME ``\d+(?:\.\d+)?`` shape as
# ``_NUMERIC_TOKEN_RE``) immediately carrying a percent unit. Group 1 is the number
# string, so a headline/companion value is compared and reported in the same format
# ``_NUMERIC_TOKEN_RE`` yields (the omission check against the claim's numeric tokens
# is therefore exact).
_PRIMACY_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?\b|per\s*cent\b)",
    re.IGNORECASE,
)
# A percent sitting in a confidence-interval / significance context is a precision /
# uncertainty figure, NOT a headline measure — skip it (never a companion).
_PRIMACY_CI_CONTEXT_RE = re.compile(
    r"\bC\.?I\.?\b|confidence\s+interval|\bp\s*[<=>]|significan",
    re.IGNORECASE,
)
# Function words dropped when comparing the MEASURE CONTEXT of two percents, so the
# same-kind test keys on salient content words (jobs, tasks, exposed), not on glue.
_PRIMACY_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "was", "were", "are", "has", "have", "had", "its", "their", "they", "them",
    "just", "over", "under", "about", "than", "then", "which", "could", "would",
    "may", "might", "into", "onto", "per", "cent", "percent", "percentage",
    "points", "point", "roughly", "around", "approximately", "some", "more",
    "most", "such", "when", "while", "also", "only", "but", "not",
})
# Alphabetic content word (>=4 letters) inside a percent's local context window.
_PRIMACY_WORD_RE = re.compile(r"[A-Za-z]{4,}")
# Light stem length + the local context window (chars each side of the percent).
_PRIMACY_STEM_LEN = 5
_PRIMACY_CONTEXT_WINDOW = 48
# A companion fires only on a MATERIAL magnitude gap: both an absolute
# percentage-point gap AND a ratio, so rounding neighbours never trip it.
_PRIMACY_MIN_ABS_GAP_PCT = 5.0
_PRIMACY_MIN_RATIO = 1.5


def _primacy_percents(text: str) -> list[tuple[str, float, frozenset]]:
    """Percent figures in `text` as (number_str, value, context-stems).

    Skips a percent whose local window is a confidence-interval / significance
    context (a precision figure, not a headline measure). Context-stems are the
    5-char prefixes of content words (>=4 letters, non-stopword) within
    ``_PRIMACY_CONTEXT_WINDOW`` chars of the percent, CLAMPED to the percent's own
    sentence — so a measure noun in a DIFFERENT sentence never leaks into this
    percent's context (mirrors the per-sentence scoping of the effect-size leg via
    ``_SPAN_SENTENCE_SPLIT_RE``). This is the 'same measure kind' signal.
    """
    out: list[tuple[str, float, frozenset]] = []
    for sentence in _SPAN_SENTENCE_SPLIT_RE.split(text or ""):
        for m in _PRIMACY_PERCENT_RE.finditer(sentence):
            lo = max(0, m.start() - _PRIMACY_CONTEXT_WINDOW)
            hi = min(len(sentence), m.end() + _PRIMACY_CONTEXT_WINDOW)
            window = sentence[lo:hi]
            if _PRIMACY_CI_CONTEXT_RE.search(window):
                continue
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            stems = frozenset(
                w.lower()[:_PRIMACY_STEM_LEN]
                for w in _PRIMACY_WORD_RE.findall(window)
                if w.lower() not in _PRIMACY_STOPWORDS
            )
            out.append((m.group(1), val, stems))
    return out


def primacy_frame_reason(claim: str, basket_span_text: str) -> str | None:
    """Return an ANNOTATE reason if the claim headlines one percent figure while the
    cited basket also holds a materially-different SAME-KIND companion percent the
    claim omits (a one-sidedness / primacy frame).

    Fires only when ALL hold:
      - the leg is enabled (PG_PRIMACY_FRAME_ANNOTATE, default ON),
      - the claim asserts at least one PERCENT headline figure,
      - the basket holds a PERCENT companion whose value the claim OMITS,
      - that companion shares a measure-context stem with a claim headline (same
        unit AND same context — e.g. both "% of jobs/tasks exposed"), and
      - the headline<->companion magnitudes differ MATERIALLY (absolute AND ratio).
    Otherwise returns None (inert — bare digits: sample sizes, years, CI bounds,
    page numbers carry no "%", so they can never fire). ADVISORY-only: the caller
    APPENDS a soft-warning; this NEVER drops, widens a span, changes a verdict, or
    alters any verified number (§-1.3).
    """
    if not primacy_frame_annotate_enabled():
        return None
    if not claim or not basket_span_text:
        return None
    claim_bare = _CLAIM_CITATION_STRIP_RE.sub("", claim)
    claim_pcts = _primacy_percents(claim_bare)
    if not claim_pcts:
        return None  # no headline percent — nothing to be one-sided about
    basket_pcts = _primacy_percents(basket_span_text)
    if not basket_pcts:
        return None  # basket carries no same-unit companion (bare digits) — inert
    claim_numbers = set(_NUMERIC_TOKEN_RE.findall(claim_bare))
    for c_str, c_val, c_stems in basket_pcts:
        if c_str in claim_numbers:
            continue  # the claim already presents this figure — not omitted
        for h_str, h_val, h_stems in claim_pcts:
            if not (c_stems & h_stems):
                continue  # different measure kind (no shared context stem)
            gap = abs(c_val - h_val)
            hi_val, lo_val = max(c_val, h_val), min(c_val, h_val)
            if gap < _PRIMACY_MIN_ABS_GAP_PCT:
                continue  # not a material absolute gap (rounding neighbour)
            if lo_val <= 0.0 or (hi_val / lo_val) < _PRIMACY_MIN_RATIO:
                continue  # not a material ratio
            return (
                "primacy_frame_companion_omitted:headline="
                + h_str + "%:companion=" + c_str + "%"
            )
    return None


def temporal_scope_reason(claim: str, span_text: str) -> str | None:
    """Return a drop reason if the claim's time-horizon is not in the cited span.

    Fires only when BOTH the claim AND the span name an explicit horizon and the
    claim's named horizon (duration or year-range) is absent from the span's
    horizons. If the span names no horizon, or the claim names none, returns None
    (inert — the numeric/content legs already govern those cases).
    """
    if not claim or not span_text:
        return None

    claim_durs = _durations_in(claim)
    claim_ranges = _year_ranges_in(claim)
    if not claim_durs and not claim_ranges:
        return None  # claim makes no temporal-scope assertion

    span_durs = _durations_in(span_text)
    span_ranges = _year_ranges_in(span_text)
    if not span_durs and not span_ranges:
        return None  # span carries no horizon to compare against — inert

    # Fire ONLY on a genuine WIDENING: a claim horizon whose MAGNITUDE exceeds
    # the span's LONGEST horizon by more than the tolerance. Comparing raw
    # (count, unit) tuples here over-drops legitimately-scoped claims — "12
    # months" vs "one year", "52 weeks" vs "one year", or a NARROWER claim
    # horizon are all supported by the cited span and must pass
    # (I-deepfix-001 Codex P1). Equivalence/narrowing -> no drop; only a horizon
    # longer than the evidence supports is an overstatement.
    span_max_days = _max_horizon_days(span_durs, span_ranges)
    widen_ceiling = span_max_days * (1.0 + _TEMPORAL_WIDEN_REL_TOLERANCE)
    missing_durs = {
        (n, u) for (n, u) in claim_durs if _duration_days(n, u) > widen_ceiling
    }
    missing_ranges = {
        (a, b) for (a, b) in claim_ranges if _range_days(a, b) > widen_ceiling
    }
    if not missing_durs and not missing_ranges:
        return None

    parts: list[str] = []
    if missing_durs:
        parts.append(
            "durations=" + ",".join(f"{n}{u}" for n, u in sorted(missing_durs))
        )
    if missing_ranges:
        parts.append(
            "ranges=" + ",".join(f"{a}-{b}" for a, b in sorted(missing_ranges))
        )
    return "temporal_scope_mismatch:" + ":".join(parts)
