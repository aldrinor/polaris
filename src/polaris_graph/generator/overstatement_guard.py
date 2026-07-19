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
from src.polaris_graph.settings import resolve

# ─────────────────────────────────────────────────────────────────────────────
# Env flags (LAW VI — named, env-gated, no magic numbers).
# Default ON: these are faithfulness-TIGHTENING (they only add drops/flags).
# Setting the flag to a falsy value reverts the relevant leg to byte-identical
# pre-B16 behaviour.
# ─────────────────────────────────────────────────────────────────────────────
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on", "enforce", "warn"})


def epistemic_guard_enabled() -> bool:
    """Whether the epistemic-marker preservation leg is active (default ON)."""
    return resolve("PG_EPISTEMIC_MARKER_GUARD").strip().lower() in _TRUE_TOKENS


def temporal_scope_guard_enabled() -> bool:
    """Whether the temporal-scope-match leg is active (default ON)."""
    return resolve("PG_TEMPORAL_SCOPE_GUARD").strip().lower() in _TRUE_TOKENS


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
    return resolve("PG_FIGURE_CONSISTENCY_ANNOTATE").strip().lower() in _TRUE_TOKENS


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


def _effect_size_conditional_core(claim: str, span_text: str) -> str | None:
    """FLAG-FREE detection core (shared by the ANNOTATE leg and the #9 DROP leg): return
    the shared-number reason iff the claim re-lifts a span number while dropping the
    conditional/threshold antecedent that governs it in the cited span; else None. Pure."""
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
            return ",".join(sorted(shared))
    return None


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
    shared = _effect_size_conditional_core(claim, span_text)
    return None if shared is None else "effect_size_conditional_stripped:num=" + shared


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 B4-render #9 (#1344): tasks-vs-jobs UNIT-CONFLATION guard.
#
# The drb_72 residual #9 headline "just over 46% of jobs" misstates a share of TASKS as a share of
# JOBS. The existing S5 leg (``numeric_qualifier_retention_reason``) already DROPS the companion
# defect — a headline number re-lifted while its span-bound conditional/threshold qualifier is
# stripped — so the conditional-strip class is covered. This leg closes the ORTHOGONAL gap S5 does
# NOT own: a claim that binds a percentage to a COUNTABLE-UNIT noun (jobs / workers / occupations /
# positions) that the cited span binds the SAME percentage to a DIFFERENT unit (tasks / activities /
# work), and the span does NOT also state that percentage for the claim's unit. That is a units
# MISSTATEMENT ("46% of tasks" rendered as "46% of jobs"), not a number mismatch, so strict_verify's
# numeric leg passes it. HIGH-PRECISION: it fires only on the exact-same percentage value attached
# to genuinely different measure nouns, so a claim whose unit the span DOES support is inert.
# ADDITIVE faithfulness-TIGHTENING: APPENDS a drop; never clears a failure, never widens a span,
# drops NO source. LAW VI kill-switch ``PG_UNIT_CONFLATION_GUARD``; OFF reverts byte-identically.
# ─────────────────────────────────────────────────────────────────────────────
def unit_conflation_guard_enabled() -> bool:
    """Whether the tasks-vs-jobs unit-conflation drop leg is active (default ON)."""
    return resolve("PG_UNIT_CONFLATION_GUARD").strip().lower() in _TRUE_TOKENS


# The two measure-unit families that get conflated. A "job unit" counts positions/people; a "task
# unit" counts activities. The same percentage attached to one in the claim and the OTHER in the
# span (and never the claim's unit) is a units misstatement.
_JOB_UNIT_RE = re.compile(
    r"\b(?:jobs?|workers?|occupations?|positions?|employees?|roles?)\b", re.IGNORECASE,
)
_TASK_UNIT_RE = re.compile(
    r"\b(?:tasks?|activit(?:y|ies)|work\s+activit(?:y|ies)|duties|duty)\b", re.IGNORECASE,
)
# A percentage immediately bound to a unit noun within a short window ("46% of jobs", "46 percent of
# tasks"). Group 1 = the numeric string (same shape as ``_NUMERIC_TOKEN_RE``); group 2 = the unit.
_PCT_OF_JOB_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?|per\s*cent)\s+of\s+(?:\w+\s+){0,3}?"
    r"(jobs?|workers?|occupations?|positions?|employees?|roles?)\b",
    re.IGNORECASE,
)
_PCT_OF_TASK_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?|per\s*cent)\s+of\s+(?:\w+\s+){0,3}?"
    r"(tasks?|activit(?:y|ies)|duties|duty)\b",
    re.IGNORECASE,
)


def unit_conflation_reason(claim: str, span_text: str) -> str | None:
    """Return a DROP reason iff the leg is enabled AND the claim binds a percentage to a JOB unit
    that the cited span binds to a TASK unit (same value) while the span never states that
    percentage for a job unit — a tasks-vs-jobs units misstatement. Else None (inert). Pure,
    stdlib-only, network-free (mirrors the other additive B16 legs)."""
    if not unit_conflation_guard_enabled():
        return None
    if not claim or not span_text:
        return None
    claim_bare = _CLAIM_CITATION_STRIP_RE.sub("", claim)
    # Percentages the claim binds to a JOB unit.
    claim_job_pcts = {m.group(1) for m in _PCT_OF_JOB_RE.finditer(claim_bare)}
    if not claim_job_pcts:
        return None
    # Percentages the span binds to a TASK unit, and (separately) to a JOB unit.
    span_task_pcts = {m.group(1) for m in _PCT_OF_TASK_RE.finditer(span_text)}
    span_job_pcts = {m.group(1) for m in _PCT_OF_JOB_RE.finditer(span_text)}
    # Fire only when the SAME value is a share-of-tasks in the span but a share-of-jobs in the claim,
    # and the span does NOT also support that value as a share-of-jobs (then the claim's unit is OK).
    conflated = sorted((claim_job_pcts & span_task_pcts) - span_job_pcts)
    if conflated:
        return "unit_conflation_tasks_as_jobs:num=" + ",".join(conflated)
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
    return resolve("PG_PRIMACY_FRAME_ANNOTATE").strip().lower() in _TRUE_TOKENS


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


# ═════════════════════════════════════════════════════════════════════════════
# I-deepfix-001 group w4-SL — four ADDITIVE, faithfulness-TIGHTENING drop legs
# (S5 / L1 / L2 / L3). Every one is pure, stdlib-only, network-free, env-gated
# DEFAULT-ON, and STRICTLY ADDITIVE: it can only APPEND a drop reason. None ever
# clears an existing failure, relaxes an existing check, widens a span, or changes
# a verdict — so setting its kill-switch to a falsy value reverts the leg
# BYTE-IDENTICAL. They are wired into ``verify_sentence_provenance`` (the BeatBoth
# composer / abstractive-writer strict-verify path) against the SAME cited-span
# aggregate the numeric/content legs use. DNA (§-1.3): the faithfulness engine is
# the only hard gate; these TIGHTEN it, they never relax it. UNDER-DROP IS SAFE;
# OVER-DROP hurts only breadth (the composer's verbatim K-span fallback still
# ships the faithful, qualifier-carrying source text). Each leg is HIGH-PRECISION
# + FAIL-OPEN — inert on the ambiguous majority, firing only on a clear defect.
# ═════════════════════════════════════════════════════════════════════════════


# ── S5 — span-faithful qualifier retention on HEADLINE numerics ───────────────
#
# A headline figure ("just over 46% of jobs are exposed", "up to 46 million jobs
# could be automated") whose cited span binds the number to a governing
# CONDITIONAL / THRESHOLD antecedent ("when accounting for current and likely
# future software developments", "if adoption accelerates", "up to") but whose
# CLAIM drops that antecedent asserts UNCONDITIONALLY what the source stated only
# under the condition. This is the render-layer ``effect_size_conditional_reason``
# ANNOTATE leg promoted to a strict-verify DROP: the composer then falls back to
# the member's verbatim K-span, which retains the condition by construction. It is
# distinct from the P5 epistemic-qualifier gate (which keys on HEDGE markers and
# EXCLUDES bare integers): S5 keys on CONDITIONAL/THRESHOLD clauses and covers
# unit-bearing INTEGER headline numerics the P5 substantive-numeral set skips.
def numeric_qualifier_retention_enabled() -> bool:
    """Whether the S5 headline-numeric conditional-retention DROP leg is active
    (default ON). Kill-switch PG_STRICT_VERIFY_NUMERIC_QUALIFIER_RETENTION=0
    reverts byte-identical."""
    return (
        resolve("PG_STRICT_VERIFY_NUMERIC_QUALIFIER_RETENTION").strip().lower()
        in _TRUE_TOKENS
    )


# S5 CLAIM-CARRIED antecedent set (I-deepfix-001 Codex P1, iter 1). The render-layer
# ``effect_size_conditional_reason`` treats a bare epistemic modal ("could"/"may"/
# "might"/"would") as a carried antecedent — appropriate there because that leg only
# APPENDS a soft caveat, never drops. But for the S5 DROP leg a bare modal is NOT a
# threshold ("up to") and NOT a conditional ("if ..."/"when accounting for ..."): a
# claim that keeps only "could" while dropping the span's governing "up to N ... if
# ..." antecedent asserts the number MORE strongly than the source stated it. So
# "46 million jobs could be automated", derived from "Up to 46 million jobs could be
# automated if firms accelerate adoption", must DROP — the "up to" ceiling and the
# "if" precondition both vanished and a modal does not carry either. This set is the
# shared ``_CLAIM_ANTECEDENT_CARRIED_RE`` MINUS the bare-modal alternation, so S5
# fires on the modal-only case without changing the annotate leg's behaviour.
_S5_CLAIM_ANTECEDENT_CARRIED_RE = re.compile(
    r"(?:"
    r"account(?:ing|s|ed)?\s+for"
    r"|\bup\s+to\b|\bas\s+(?:much|many)\s+as\b|\bover\s+half\b"
    r"|\bif\b|\bassum(?:e|es|ed|ing)\b|\bprovided\b"
    r"|\bscenario\b|\bhypothetical(?:ly)?\b"
    r"|\bwhen\b"
    r"|future\s+(?:software|developments|technolog)"
    r")",
    re.IGNORECASE,
)


def numeric_qualifier_retention_reason(claim: str, span_text: str) -> str | None:
    """Return a DROP reason when the claim re-lifts a span number while dropping
    the conditional/threshold antecedent that governs it in the cited span.

    Fires only when ALL hold: the leg is enabled; the claim carries NO governing
    conditional/threshold of its own (a bare assertion); the cited span has a
    sentence whose governing conditional/threshold token PRECEDES a number; and the
    claim reproduces that governed number. Otherwise returns None (inert — no false
    drop). DROP-severity (unlike ``effect_size_conditional_reason`` which annotates)
    so the composer falls back to the qualifier-carrying verbatim K-span (§-1.3
    faithfulness tightening; under-drop is the safe direction)."""
    if not numeric_qualifier_retention_enabled():
        return None
    if not claim or not span_text:
        return None
    claim_bare = _CLAIM_CITATION_STRIP_RE.sub("", claim)
    claim_numbers = set(_NUMERIC_TOKEN_RE.findall(claim_bare))
    if not claim_numbers:
        return None  # no figure re-lifted — nothing to over-assert
    if _S5_CLAIM_ANTECEDENT_CARRIED_RE.search(claim_bare):
        return None  # the claim carries a real threshold/conditional antecedent — faithful
    for sentence in _SPAN_SENTENCE_SPLIT_RE.split(span_text):
        cond = _SPAN_EFFECT_CONDITION_RE.search(sentence)
        if not cond:
            continue
        governed = set(_NUMERIC_TOKEN_RE.findall(sentence[cond.start():]))
        shared = claim_numbers & governed
        if shared:
            return "headline_numeric_qualifier_dropped:num=" + ",".join(sorted(shared))
    return None


# ── L2 — numeric-fidelity span re-check: VALUE AND ROLE (currency + multiplier) ─
#
# Extends the percent-role match (``PG_PROVENANCE_PERCENT_ROLE_MATCH``) to two more
# measure ROLES so a printed number must appear in its cited span in the SAME role,
# not merely as a bare digit (a page number / a year / a reference index):
#   * CURRENCY   — "$14 billion" must be grounded by a currency figure of the same
#                  value (and, when BOTH sides name a scale, the same scale — so
#                  "$14 billion" is NOT grounded by "$14 million").
#   * MULTIPLIER — "14-fold" / "14× higher" must be grounded by a same-value
#                  multiplier, not by a bare "14" elsewhere in the span.
# FAIL-OPEN: a claim value with NO scale is satisfied by ANY same-value currency in
# the span (a scale conflict fires ONLY when both sides carry a differing, non-empty
# scale) — so an abbreviation the extractor does not recognize can never false-drop.
_L2_SCALE_WORD = r"(?:thousand|million|billion|trillion)"
_L2_CUR_SYMBOL = r"[$€£¥₹]"
_L2_CUR_CODE = r"(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|CNY|INR)"
_L2_CUR_WORD = r"(?:dollars?|euros?|pounds?|yen|francs?|yuan|rupees?)"
# symbol / ISO-code BEFORE the number, optional scale word after ("$14", "$14 billion",
# "USD 14 million").
_L2_CURRENCY_PRE_RE = re.compile(
    r"(?:" + _L2_CUR_SYMBOL + r"|\b" + _L2_CUR_CODE + r"\b\s?)"
    r"(\d+(?:[.,]\d+)?)\s*(" + _L2_SCALE_WORD + r")?",
    re.IGNORECASE,
)
# number then optional scale then currency WORD ("14 billion dollars", "14 euros").
_L2_CURRENCY_POST_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(" + _L2_SCALE_WORD + r")?\s*" + _L2_CUR_WORD + r"\b",
    re.IGNORECASE,
)
# A MULTIPLIER: N-fold / N× / N x / "N times <comparative>" (bare "N times" without a
# comparative is frequency, not a magnitude — deliberately excluded for precision).
_L2_MULTIPLIER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:"
    r"-?\s*fold\b"
    r"|×"
    r"|x(?=[\s.,;:)]|$)"
    r"|\s*times\s+(?:higher|greater|lower|smaller|larger|more|less|faster|slower|"
    r"as\s+(?:many|much|likely))"
    r")",
    re.IGNORECASE,
)


def _l2_currency_entries(text: str) -> "set[tuple[str, str]]":
    """Currency figures in `text` as a set of (value, scale) — value comma-stripped,
    scale lower-cased or "" when none. Reads both symbol/code-before and word-after
    forms so "$14 billion" and "14 billion dollars" canonicalize identically."""
    out: set[tuple[str, str]] = set()
    for rx in (_L2_CURRENCY_PRE_RE, _L2_CURRENCY_POST_RE):
        for m in rx.finditer(text or ""):
            val = (m.group(1) or "").replace(",", "")
            scale = (m.group(2) or "").lower()
            if val:
                out.add((val, scale))
    return out


def _l2_multiplier_values(text: str) -> "set[str]":
    """Multiplier magnitudes in `text` ("14-fold", "14×", "14 times higher") as the
    set of value strings."""
    return {m.group(1) for m in _L2_MULTIPLIER_RE.finditer(text or "")}


def numeric_role_match_enabled() -> bool:
    """Whether the L2 currency/multiplier VALUE-AND-ROLE DROP leg is active (default
    ON). Kill-switch PG_PROVENANCE_NUMERIC_ROLE_MATCH=0 reverts byte-identical."""
    return (
        resolve("PG_PROVENANCE_NUMERIC_ROLE_MATCH").strip().lower()
        in _TRUE_TOKENS
    )


def numeric_role_match_reason(claim: str, span_text: str) -> str | None:
    """Return a DROP reason when the claim prints a CURRENCY or MULTIPLIER figure
    whose value+role is not grounded by the SAME role in the cited span.

    High-precision + fail-open. Currency: a claim value missing from the span's
    currency figures drops; a claim value present but with a CONFLICTING non-empty
    scale (billion vs million) drops; a claim value with no scale, or a span figure
    with no recognized scale, never conflicts. Multiplier: a claim multiplier value
    absent from the span's multipliers drops. A claim carrying no currency/multiplier
    figure is inert (the percent-role + numeric legs already govern bare digits)."""
    if not numeric_role_match_enabled():
        return None
    if not claim or not span_text:
        return None
    claim_bare = _CLAIM_CITATION_STRIP_RE.sub("", claim)
    parts: list[str] = []

    claim_cur = _l2_currency_entries(claim_bare)
    if claim_cur:
        span_cur = _l2_currency_entries(span_text)
        span_scales_by_val: dict[str, set[str]] = {}
        for val, scale in span_cur:
            span_scales_by_val.setdefault(val, set()).add(scale)
        missing_cur: set[str] = set()
        for val, scale in claim_cur:
            if val not in span_scales_by_val:
                missing_cur.add(f"{val}:{scale or '-'}")  # value never appears AS currency
            elif scale and all(
                s and s != scale for s in span_scales_by_val[val]
            ):
                missing_cur.add(f"{val}:{scale}")  # value present but every span scale conflicts
        if missing_cur:
            parts.append("currency=" + ",".join(sorted(missing_cur)))

    claim_mul = _l2_multiplier_values(claim_bare)
    if claim_mul:
        missing_mul = claim_mul - _l2_multiplier_values(span_text)
        if missing_mul:
            parts.append("multiplier=" + ",".join(sorted(missing_mul)))

    if parts:
        return "numeric_role_mismatch:" + ":".join(parts)
    return None


# ── L1 — judge the clinical qualifier as a UNIT (number + population/indication) ─
#
# A span-faithful number can be bound to the WRONG population / indication and still
# pass span-grounding — the exact failure that hurts patients. This leg judges the
# number together with the governing clinical POPULATION/INDICATION antecedent the
# span binds to it (the effect-size-conditional pattern extended to clinical
# qualifiers): if the span binds a shared number to a population token within a
# proximity window and the CLAIM carries neither that population nor a synonym of it
# (dropped OR conflicting population), DROP. High-precision curated population
# lexicon; population tokens are stem-matched so plural/singular never false-drops.
_L1_POPULATION_RE = re.compile(
    r"\b(?:"
    r"immunocompromised|immunosuppressed|immunodeficient"
    r"|pregnan(?:t|cy)|breastfeed\w*|lactating|neonat\w*|infants?|newborns?"
    r"|children|child|paediatric|pediatric|adolescents?|elderly|geriatric|adults?"
    r"|renal(?:\s+impair\w+)?|hepatic(?:\s+impair\w+)?|dialysis"
    r"|diabetic|diabetes|hypertensive|cirrho\w+|immunonaive"
    r"|treatment-naive|treatment-experienced|opioid-naive"
    r")\b",
    re.IGNORECASE,
)


def _l1_pop_stem(token: str) -> str:
    """A short case-folded stem for a population token so plural/singular and light
    inflection ("adults"/"adult", "infants"/"infant") match; keeps precision by
    stripping only a trailing 's'."""
    t = re.sub(r"s$", "", token.lower())
    return t[:6]


def _l1_pop_stems(text: str) -> "set[str]":
    return {_l1_pop_stem(m.group(0)) for m in _L1_POPULATION_RE.finditer(text or "")}


def _l1_span_populations_near(sentence: str, number: str, window: int) -> "set[str]":
    """Population stems within `window` whitespace tokens of an occurrence of
    `number` (whole-number match) inside `sentence`."""
    toks = sentence.split()
    pops: set[str] = set()
    for i, tok in enumerate(toks):
        if number not in _NUMERIC_TOKEN_RE.findall(tok):
            continue
        lo = max(0, i - window)
        hi = min(len(toks), i + window + 1)
        pops |= _l1_pop_stems(" ".join(toks[lo:hi]))
    return pops


def clinical_qualifier_unit_enabled() -> bool:
    """Whether the L1 clinical population/indication-unit DROP leg is active
    (default ON). Kill-switch PG_STRICT_VERIFY_CLINICAL_QUALIFIER_UNIT=0 reverts
    byte-identical."""
    return (
        resolve("PG_STRICT_VERIFY_CLINICAL_QUALIFIER_UNIT").strip().lower()
        in _TRUE_TOKENS
    )


# Proximity window (whitespace tokens) binding a population token to a number.
_L1_PROXIMITY_TOKENS = 12


def clinical_qualifier_unit_reason(claim: str, span_text: str) -> str | None:
    """Return a DROP reason when the span binds a shared number to a clinical
    population/indication the claim fails to carry.

    Fires only when a span SENTENCE co-locates a shared number and a curated
    population token within the proximity window AND none of that sentence's
    bound-population stems appears in the claim. Otherwise inert (no population
    binding in the span, or the claim carries the population -> the qualifier
    travelled with the number). DROP so the composer falls back to the K-span that
    keeps the number bound to its population (§-1.3 clinical-safety tightening —
    over-crediting a mis-populated number is lethal; under-drop is safe)."""
    if not clinical_qualifier_unit_enabled():
        return None
    if not claim or not span_text:
        return None
    claim_bare = _CLAIM_CITATION_STRIP_RE.sub("", claim)
    claim_numbers = set(_NUMERIC_TOKEN_RE.findall(claim_bare))
    if not claim_numbers:
        return None  # no number to mis-bind
    claim_pops = _l1_pop_stems(claim_bare)
    for sentence in _SPAN_SENTENCE_SPLIT_RE.split(span_text):
        shared = claim_numbers & set(_NUMERIC_TOKEN_RE.findall(sentence))
        for number in sorted(shared):
            span_pops = _l1_span_populations_near(
                sentence, number, _L1_PROXIMITY_TOKENS
            )
            if span_pops and not (span_pops & claim_pops):
                return (
                    "clinical_qualifier_unit_dropped:num=" + number
                    + ":span_pop=" + ",".join(sorted(span_pops))
                )
    return None


# ── L3 — negation / contraindication semantic polarity guard ──────────────────
#
# "not contraindicated" must never render from a "contraindicated" span (and
# vice-versa). For a curated set of CLINICAL RELATION stems, if the claim's polarity
# toward the stem (negated vs asserted) DISAGREES with the cited span's polarity for
# the SAME stem, DROP. Deterministic pre-stem negation window + expanded negative
# contractions; a mention is treated as negated if ANY occurrence is negated
# (conservative — a report that inverts a contraindication is §-1.1-lethal).
_L3_RELATION_STEMS: tuple[str, ...] = (
    "contraindicat",
    "recommend",
    "indicated",
    "approv",
    "efficac",
    "effective",
    "superior",
    "toler",         # tolerated / tolerability
    "benefici",
    "associat",
    "respons",       # responsive / response
    "eligib",
    "safe",
)
# Negative contractions -> "X not" so the pre-stem negator fires on contraction spelling.
_L3_NEG_CONTRACTIONS = {
    "aren't": "are not", "isn't": "is not", "wasn't": "was not", "weren't": "were not",
    "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "won't": "will not", "wouldn't": "would not", "can't": "can not", "couldn't": "could not",
    "shouldn't": "should not", "mustn't": "must not", "needn't": "need not",
    "cannot": "can not",
}
# A negation cue that, appearing shortly BEFORE the stem (<=30 interposed chars),
# inverts it: "not contraindicated", "no known contraindication", "never
# recommended", "fails to be effective", "not associated with".
_L3_NEG_BEFORE_RE = re.compile(
    r"\b(?:no|not|never|without|none|neither|nor|lacks?|lacking|absent|"
    r"absence\s+of|no\s+evidence\s+of|fails?\s+to|failed\s+to|"
    r"free\s+of|devoid\s+of|unlikely\s+to\s+be|ruled?\s+out|rules?\s+out)\b"
    r"[\w\s,'()/-]{0,30}?$",
    re.IGNORECASE,
)


def _l3_expand(text: str) -> str:
    text = text.replace("’", "'").lower()
    for contraction, expanded in _L3_NEG_CONTRACTIONS.items():
        text = text.replace(contraction, expanded)
    return text


def _l3_relation_polarity(text: str, stem: str) -> "bool | None":
    """None if `stem` is absent; True if any occurrence is negated by a pre-stem
    cue; False if the stem is present and no occurrence is negated."""
    negated = False
    found = False
    for m in re.finditer(stem, text):
        found = True
        pre = text[max(0, m.start() - 40):m.start()]
        if _L3_NEG_BEFORE_RE.search(pre):
            negated = True
            break
    if not found:
        return None
    return negated


def clinical_polarity_guard_enabled() -> bool:
    """Whether the L3 clinical negation/contraindication polarity DROP leg is active
    (default ON). Kill-switch PG_STRICT_VERIFY_CLINICAL_POLARITY=0 reverts
    byte-identical."""
    return (
        resolve("PG_STRICT_VERIFY_CLINICAL_POLARITY").strip().lower()
        in _TRUE_TOKENS
    )


def clinical_polarity_reason(claim: str, span_text: str) -> str | None:
    """Return a DROP reason when a clinical relation stem shared by the claim and its
    cited span carries OPPOSITE polarity (one negated, one asserted). Inert when no
    shared stem, or both polarities agree. DROP — a negated clinical relation
    rendered from a non-negated span (or vice-versa) is a lethal inversion (§-1.3)."""
    if not clinical_polarity_guard_enabled():
        return None
    if not claim or not span_text:
        return None
    claim_norm = _l3_expand(_CLAIM_CITATION_STRIP_RE.sub("", claim))
    span_norm = _l3_expand(span_text)
    for stem in _L3_RELATION_STEMS:
        pc = _l3_relation_polarity(claim_norm, stem)
        if pc is None:
            continue
        ps = _l3_relation_polarity(span_norm, stem)
        if ps is None:
            continue
        if pc != ps:
            return (
                "clinical_polarity_mismatch:stem=" + stem
                + ":claim=" + ("neg" if pc else "pos")
                + ":span=" + ("neg" if ps else "pos")
            )
    return None
