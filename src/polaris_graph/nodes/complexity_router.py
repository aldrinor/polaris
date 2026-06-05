"""I-ready-006 (#1082): deterministic query-complexity router (no model, offline, §8.4-safe).

Classifies a research question as ``simple`` (a right-sizeable factual lookup), ``complex`` (the full
heavyweight deep-research path), or ``moderate``. Pure stdlib + ``re`` — no LLM call (burning an LLM
call just to decide a query is simple would defeat the cost-saving point) and no model load.

FAIL-OPEN by design (clinical-safety): anything NOT confidently ``simple`` is classified ``complex``,
so a hard clinical / policy / comparison / mechanism question is NEVER under-served. The caller wires
this behind ``PG_COMPLEXITY_ROUTING`` (default OFF) and only right-sizes when
``complexity == "simple"`` AND ``confidence >= PG_COMPLEXITY_MIN_CONFIDENCE``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ComplexityDecision:
    """The routing decision. ``reasons`` is auditable telemetry for the manifest."""

    complexity: str                       # "simple" | "moderate" | "complex"
    confidence: float                     # 0.0 - 1.0
    reasons: list[str] = field(default_factory=list)


# Intent markers that force the FULL heavyweight path — comparison / causal / mechanism / synthesis /
# clinical-evaluative. Presence of ANY ⇒ NOT simple (fail-open to complex). A clinical dosing / safety
# / efficacy / mechanism question is deliberately routed complex: better to OVER-serve it than under-
# serve it. NOTE: a bare conjunction ("Telus AND Bell ...") is a parallel FACTUAL lookup, not a
# comparison — only explicit compare/versus/difference verbs count here.
_COMPLEX_INTENT = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between|trade[- ]?off|"
    r"why|how does|how do|mechanism|pathophysiolog|causal|cause[sd]?|effect of|impact of|"
    r"efficacy|safety|adverse|contraindicat|dose|dosing|titrat|regimen|"
    r"meta[- ]?analysis|systematic review|guideline|recommend|"
    r"relationship between|associat|correlat|predict|forecast|project|"
    r"should|optimal|best (?:approach|strategy|treatment|option)|evaluate|assess(?:ment)?|"
    r"pros and cons|advantages|risk[- ]?benefit)\b",
    re.IGNORECASE,
)

# Factual / quantity cues that SUGGEST a right-sizeable lookup.
_FACTUAL_CUE = re.compile(
    r"\b(price|stock|share price|cost|value|worth|revenue|profit|market cap|"
    r"how much|how many|what (?:is|was|are|were) the |when (?:did|was|were)|"
    r"population|gdp|rate of|percentage|number of|capital of|headquarter|founded|"
    r"ceo|exchange rate|temperature|distance|height|weight|age)\b",
    re.IGNORECASE,
)

_TEMPORAL_RANGE = re.compile(
    r"\b(over (?:the )?(?:past|last)\s+\d+\s+years?|in \d{4}|since \d{4}|\d+[- ]year)\b",
    re.IGNORECASE,
)


def classify_complexity(question: str) -> ComplexityDecision:
    """Classify ``question``. Deterministic, fail-open. Never raises — a malformed input returns a
    low-confidence ``complex`` decision so the caller takes the full path."""
    try:
        q = (question or "").strip()
        if not q:
            return ComplexityDecision("complex", 0.0, ["empty_question_fail_open"])

        reasons: list[str] = []
        has_complex_intent = bool(_COMPLEX_INTENT.search(q))
        has_factual_cue = bool(_FACTUAL_CUE.search(q))
        has_temporal = bool(_TEMPORAL_RANGE.search(q))

        # Named-entity proxy: a capitalized token NOT at sentence start (so the leading "What"/"How"
        # is excluded), OR an all-caps ticker (2-5 letters).
        words = q.split()
        caps = [w for w in words[1:] if re.match(r"^[A-Z][A-Za-z.&-]+$", w)]
        has_entity = len(caps) >= 1 or bool(re.search(r"\b[A-Z]{2,5}\b", q))
        word_count = len(words)

        # Any explicit compare/causal/mechanism/synthesis intent ⇒ full path (highest priority).
        if has_complex_intent:
            reasons.append("complex_intent_marker")
            return ComplexityDecision("complex", 0.9, reasons)

        # Multi-entity OR single-entity factual lookup with a named entity and a bounded length is the
        # right-sizeable class (e.g. "Telus and Bell stock price over the past 20 years"). The temporal
        # range is corroborating, not required.
        if has_factual_cue and has_entity and word_count <= 25:
            reasons.append("factual_cue+named_entity")
            if has_temporal:
                reasons.append("temporal_range")
            return ComplexityDecision("simple", 0.85, reasons)

        # A short factual question without a clear named entity is a weaker simple signal.
        if has_factual_cue and word_count <= 15:
            reasons.append("factual_cue_short")
            return ComplexityDecision("simple", 0.70, reasons)

        # Not confidently simple ⇒ FAIL OPEN to the full heavyweight path.
        reasons.append("no_simple_signal_fail_open")
        return ComplexityDecision("complex", 0.50, reasons)
    except Exception as exc:  # noqa: BLE001 — never let the router abort a run; fail open to complex.
        return ComplexityDecision("complex", 0.0, [f"router_error_fail_open:{type(exc).__name__}"])
