"""
Contradiction detector — HONEST-REBUILD Phase 3.

Finds pairs of evidence statements that directly contradict each other
on the same (subject, predicate, numeric value) tuple. Surfaces these
to the user before synthesis so the generator cannot silently pick one
side.

ADDRESSES PG_LB_SA_02_CONTENT_AUDIT Section E-06: the pre-rebuild
pipeline found two conflicting efficacy numbers for semaglutide weight
loss (STEP 1: 14.9% vs STEP 5: 17.4%), and the final report cited only
one without disclosing the range. A reader could not tell whether the
disagreement was stratification, dosing, duration, or cherry-picking.

DESIGN:
This detector is deterministic and rule-based. It does NOT use an LLM
to decide whether two claims contradict because LLM-based contradiction
detection has known failure modes on numerical values (confuses 14 and
17 as "roughly similar" even when it's a 17% relative difference).

Approach:
  1. Extract structured claims: (subject, predicate, numeric_value, unit)
     from each evidence row using regex on the direct_quote.
  2. Group claims by normalized (subject, predicate) pair.
  3. Within each group, flag numeric discrepancies > 10% relative
     difference OR > 2.0 absolute unit difference (configurable).
  4. Return a list of ContradictionRecord objects.

The caller (Phase 4 synthesis) inserts a disclosure line for each
contradicted claim: "Sources report X (ref A) and Y (ref B). The
reasons for the difference are [analyst note]."
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.contradiction_detector")


# ─────────────────────────────────────────────────────────────────────────────
# Numeric + unit extraction
# ─────────────────────────────────────────────────────────────────────────────

# Percentage values. Captures the number + "%" or " percent".
# Note: \b after "%" fails because % and space are both non-word chars —
# use a non-capturing boundary or a literal end-of-token check instead.
_PCT_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>%|percent|pct)(?=\s|[,.;:)\]!?]|$)",
    re.IGNORECASE,
)

# Mass / dose values with unit.
_DOSE_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>mg|µg|ug|mcg|g|kg)(?=\s|[,.;:)\]!?]|$)",
    re.IGNORECASE,
)

# HbA1c points. "percentage points" uses an explicit trailing word
# boundary since "points" ends on a word char.
_HBA1C_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>%|percentage\s*points?)",
    re.IGNORECASE,
)

# Time durations
_DURATION_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>weeks?|months?|years?)\b",
    re.IGNORECASE,
)


# Predicate keywords — the ones we most want to catch contradictions on.
# BUG-M-202 fix (deep-dive R7): expanded coverage beyond the original
# obesity/cardiometabolic-only set. A proper domain-YAML-driven
# profile loader is tracked as a follow-up (see docs/todo_list.md);
# this expansion is the minimum-viable fix to close the AF
# anticoagulation silent-failure reproducer.
_EFFICACY_PREDICATES_METABOLIC = (
    # Original obesity / GLP-1 / lipid
    "weight loss", "body weight", "weight reduction",
    "hba1c reduction", "a1c reduction",
    "systolic blood pressure reduction", "diastolic blood pressure reduction",
    "ldl reduction", "cholesterol reduction",
    "cardiovascular risk reduction", "mace reduction",
    "mortality reduction",
)

_EFFICACY_PREDICATES_ANTICOAGULATION = (
    # AF anticoagulation + guideline endpoints (BUG-M-202 R7)
    "stroke rate", "stroke risk", "ischemic stroke",
    "systemic embolism", "stroke or systemic embolism",
    "major bleeding", "clinically relevant non-major bleeding",
    "intracranial hemorrhage", "gastrointestinal bleeding",
    "time in therapeutic range", "ttr", "inr",
    "cha2ds2-vasc", "has-bled",
    "hazard ratio", "relative risk", "odds ratio",
)

_EFFICACY_PREDICATES_TECH = (
    # Tech / ML benchmark endpoints
    "accuracy", "f1 score", "f1-score",
    "precision", "recall", "auc", "roc auc",
    "error rate", "latency", "throughput",
    "inference time", "model size",
    "perplexity", "exact match",
    "exact-match accuracy",
)

_EFFICACY_PREDICATES_POLICY = (
    # Policy / regulatory quantitative endpoints
    "compliance rate", "adoption rate", "enforcement rate",
    "penalty rate", "coverage rate", "participation rate",
    "emissions reduction", "cost savings",
)

_EFFICACY_PREDICATES_DD = (
    # Due diligence / financial endpoints
    "revenue growth", "ebitda margin", "gross margin",
    "operating margin", "market share",
    "customer acquisition cost", "churn rate",
    "debt-to-equity", "cash flow",
)

_EFFICACY_PREDICATES = (
    _EFFICACY_PREDICATES_METABOLIC
    + _EFFICACY_PREDICATES_ANTICOAGULATION
    + _EFFICACY_PREDICATES_TECH
    + _EFFICACY_PREDICATES_POLICY
    + _EFFICACY_PREDICATES_DD
)

_SAFETY_PREDICATES_METABOLIC = (
    "incidence of nausea", "incidence of vomiting",
    "discontinuation rate", "adverse event rate",
    "serious adverse event rate", "pancreatitis incidence",
    "hypoglycemia incidence", "thyroid c-cell",
)

_SAFETY_PREDICATES_ANTICOAGULATION = (
    "bleeding rate", "fatal bleeding", "mortality",
    "all-cause mortality", "cardiovascular mortality",
)

_SAFETY_PREDICATES = (
    _SAFETY_PREDICATES_METABOLIC
    + _SAFETY_PREDICATES_ANTICOAGULATION
)

# Per-domain predicate set for the `domain` kwarg. The union is still
# the default when no domain is passed (backward-compat).
_DOMAIN_PREDICATES: dict[str, tuple] = {
    "clinical": (
        _EFFICACY_PREDICATES_METABOLIC
        + _EFFICACY_PREDICATES_ANTICOAGULATION
        + _SAFETY_PREDICATES_METABOLIC
        + _SAFETY_PREDICATES_ANTICOAGULATION
    ),
    "tech": _EFFICACY_PREDICATES_TECH,
    "policy": _EFFICACY_PREDICATES_POLICY,
    "due_diligence": _EFFICACY_PREDICATES_DD,
}


@dataclass
class ExtractedNumericClaim:
    """A claim like 'X causes Y-value-unit change in Z' extracted from evidence."""

    evidence_id: str
    subject: str      # e.g., "semaglutide"
    predicate: str    # e.g., "weight loss"
    value: float
    unit: str         # "%", "mg", "weeks", etc.
    context_snippet: str  # original text for display
    source_url: str = ""
    source_tier: str = ""
    dose: str = ""             # "2.4 mg", "7.2 mg", or "" if not present
    # arm is positively-known ONLY when a placebo/comparator cue fired. A
    # DEFAULTED arm is NOT positively-known (design §4.3): no-cue -> None, so
    # build_merge_key (Wave-3 step [6]) treats it as an unknown discriminator
    # and keeps the claim a singleton rather than over-merging.
    arm: Optional[str] = None  # "comparator_adjacent" on cue; None = UNKNOWN
    endpoint_phrase: str = ""  # e.g., "at week 68", "from baseline", "mean change"
    # ── Wave-3 positive-known discriminator fields (I-arch-002 [1]) ──────────
    # All default '' = UNKNOWN sentinel. Dormant carriers: no consumer reads
    # them until claim_graph.build_merge_key reads them under
    # PG_SWEEP_CREDIBILITY_REDESIGN. A value is set ONLY when a positive token
    # was extracted (never derived/defaulted) per design §4.3.
    dose_frequency: str = ""    # "qd"/"bid"/"weekly"/... cadence token; '' = UNKNOWN
    comparator: str = ""        # the "vs X" comparator phrase; '' = UNKNOWN
    route_formulation: str = "" # "iv"/"po"/"sc"/"er"/...; '' = UNKNOWN
    effect_measure: str = ""    # "relative"/"absolute"/"hr"/"or"/"raw"; '' = UNKNOWN
    direction: str = ""         # "increase"/"decrease" TOKEN-only; '' = UNKNOWN
    population: str = ""         # "patients with X" cohort phrase; '' = UNKNOWN


@dataclass
class ContradictionRecord:
    """Two claims that contradict on the same (subject, predicate)."""

    subject: str
    predicate: str
    claims: list[ExtractedNumericClaim]
    relative_difference: float      # 0.0-1.0+ (|a-b|/min(|a|,|b|))
    absolute_difference: float
    severity: str                   # "low" / "medium" / "high"
    recommended_action: str = (
        "Disclose both values with their source tiers in the final report. "
        "If one source is T1 (RCT) and another is T5 (industry), note the "
        "authority gap alongside the numeric gap."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_predicate(
    text: str, domain: str | None = None,
) -> Optional[str]:
    """Return the predicate keyword if present in the text.

    BUG-M-202 fix (deep-dive R7): when a domain is supplied, prefer
    domain-specific predicates first (higher specificity), then fall
    back to the union set. Previously, only the metabolic-centric
    union was checked — so AF anticoagulation queries returned zero
    matches because stroke/bleeding vocabulary wasn't in the table.
    """
    t = (text or "").lower()
    # Domain-specific first (more specific endpoints win ties).
    if domain and domain in _DOMAIN_PREDICATES:
        for p in _DOMAIN_PREDICATES[domain]:
            if p in t:
                return p
    # Fall back to union.
    for p in _EFFICACY_PREDICATES + _SAFETY_PREDICATES:
        if p in t:
            return p
    return None


def _normalize_subject(text: str, fallback: str = "unknown") -> str:
    """Extract the first drug name in the text, or fallback.

    This is the legacy API used when no positional anchor is available.
    Prefer _subject_near_position() when you know where the numeric value
    is and want to attribute the number to the nearest drug, not the
    first drug to appear in the wider text.
    """
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE
    m = _DRUG_NAME_RE.search(text or "")
    if m:
        return m.group(1).lower()
    return fallback


def _subject_near_position(
    text: str,
    anchor_pos: int,
    fallback: str = "unknown",
    window: int = 150,
) -> str:
    """R-5 Fix B: return the drug name whose match is CLOSEST to
    anchor_pos in `text`, within ±window chars.

    Used for cross-drug comparisons like:
        "Eli Lilly's Zepbound achieving 25.5% compared to Novo Nordisk's
        CagriSema at 23%, with Lilly's retatrutide at 28.7% and ..."

    Legacy `_normalize_subject(quote)` would return the first drug in
    the full quote (often 'retatrutide' here, even though 25.5% belongs
    to Zepbound). This function searches all drug matches inside the
    ±window chars around anchor_pos and returns the match with the
    smallest absolute distance.

    Falls back to _normalize_subject(text) (first-in-text) only if
    ZERO matches are found inside the window. Returns `fallback` if
    still nothing.
    """
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE

    if not text:
        return fallback
    lo = max(0, anchor_pos - window)
    hi = min(len(text), anchor_pos + window)
    local = text[lo:hi]
    matches = list(_DRUG_NAME_RE.finditer(local))
    if not matches:
        # Widen search to full text as last resort
        return _normalize_subject(text, fallback)
    # Pick the match whose center is closest to the (anchor_pos - lo)
    # position inside `local`.
    anchor_local = anchor_pos - lo
    best = min(
        matches,
        key=lambda m: abs(((m.start() + m.end()) // 2) - anchor_local),
    )
    return best.group(1).lower()


# Fix-1 reject patterns. Numbers that sit inside these contexts are
# filtered BEFORE we pull the value, because they're structurally not
# the claim-under-measurement:
#   - "placebo N%" / "vs placebo" / "versus placebo" → comparator arm
#   - "≥5%" / "at least 5%" / "5% or more" / "5% threshold" → achievement
#     threshold, not the value being measured
#   - "STEP N" / "SUSTAIN N" → trial-program integer, not a value
#   - "week N" / "month N" / "year N" → duration
_PLACEBO_CONTEXT_RE = re.compile(
    r"(?:vs\.?|versus|v\.)\s+placebo|"
    r"placebo\s+(?:recipients|group|arm|patients)|"
    r"in\s+(?:the\s+)?placebo",
    re.IGNORECASE,
)
_ACHIEVEMENT_THRESHOLD_RE = re.compile(
    r"(?:at\s+least|≥|>=|>)\s*-?\d+(?:\.\d+)?\s*%|"
    r"-?\d+(?:\.\d+)?\s*%\s*(?:or\s+more|or\s+greater|threshold|achievement)",
    re.IGNORECASE,
)
_TRIAL_ACRONYM_NUM_RE = re.compile(
    r"\b(?:STEP|SUSTAIN|SURPASS|SURMOUNT|REWIND|LEADER|PIONEER|SELECT)\s*-?\s*\d+",
    re.IGNORECASE,
)
_DURATION_NUM_RE = re.compile(
    r"(?:week|month|year|day)s?\s+-?\d+(?:\.\d+)?|"
    r"-?\d+(?:\.\d+)?\s*(?:week|month|year|day)s?",
    re.IGNORECASE,
)
# A valid claim usually carries a value-phrase verb. "Achieved 14.9%",
# "reduced by 12%", "loss of 15%", "mean change -14.9%". This
# whitelist prevents us from pulling random decimals that happen to be
# in the quote.
_VALUE_PHRASE_VERBS = re.compile(
    r"(?:achiev\w+|reduc\w+|los[ts]?|loss|decreas\w+|"
    r"mean\s+(?:change|weight|reduction|loss|difference)|"
    r"experienc\w+\s+a?\s*\d+|"
    r"reported|produc\w+|demonstrat\w+|"
    r"at\s+(?:week|month|year)\s+\d+)",
    re.IGNORECASE,
)

# ── Wave-3 master flag (I-arch-002) ──────────────────────────────────────────
# Read at CALL time (never import-time) so tests can monkeypatch os.environ and
# the OFF path is honoured per-invocation. Mirrors
# credibility_pass._OFF_VALUES semantics; inlined here to avoid importing the
# synthesis layer into retrieval (no cross-layer / circular-import coupling).
_CRED_REDESIGN_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
_CRED_REDESIGN_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def _credibility_redesign_enabled() -> bool:
    """True when PG_SWEEP_CREDIBILITY_REDESIGN is on. OFF => byte-identical."""
    return (
        os.environ.get(_CRED_REDESIGN_FLAG, "").strip().lower()
        not in _CRED_REDESIGN_OFF_VALUES
    )


# Dose pattern (captures the full "X.X mg" string for grouping).
_DOSE_CAPTURE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*m[gc]g?|\d+(?:\.\d+)?\s*[µu]g|\d+(?:\.\d+)?\s*g\b)",
    re.IGNORECASE,
)

# Wave-3 variant (I-arch-002 [2], DRIFT-MGKG): preserves a per-weight ('/kg') or
# per-time ('/day','/m2',...) denominator so '5 mg/kg' is DISTINCT from '5 mg'
# (design §4.1/§4.3 — prevents a false dose-response merge). This change feeds
# the LEGACY detect_contradictions grouping key (:596 includes dose) and is
# therefore NOT byte-inert when the master flag is OFF; per the non-negotiable
# byte-identity rule it is GATED behind PG_SWEEP_CREDIBILITY_REDESIGN. When the
# flag is OFF the original _DOSE_CAPTURE_RE path runs verbatim.
_DOSE_CAPTURE_MGKG_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*m[gc]g?|\d+(?:\.\d+)?\s*[µu]g|\d+(?:\.\d+)?\s*g\b)"
    r"(\s*/\s*(?:kg|m2|m\^?2|day|d|hr?|h|dose|week|wk))?",
    re.IGNORECASE,
)


def _extract_dose(text: str) -> str:
    """Extract the most-salient dose token from the text (for grouping).

    DRIFT-MGKG (I-arch-002 [2]): under PG_SWEEP_CREDIBILITY_REDESIGN a trailing
    per-weight/per-time denominator ('/kg', '/m2', ...) is preserved so
    '5 mg/kg' != '5 mg'. Flag OFF => original behaviour byte-for-byte.
    """
    if _credibility_redesign_enabled():
        m = _DOSE_CAPTURE_MGKG_RE.search(text or "")
        if not m:
            return ""
        base = m.group(1)
        denom = m.group(2) or ""
        # Normalize internal whitespace out of the denominator ('  / kg' -> '/kg')
        denom = re.sub(r"\s+", "", denom)
        return (base + denom).replace(" ", " ").lower()
    m = _DOSE_CAPTURE_RE.search(text or "")
    if not m:
        return ""
    return m.group(1).replace(" ", " ").lower()


def _detect_placebo_arm(text: str) -> bool:
    if not text:
        return False
    return bool(_PLACEBO_CONTEXT_RE.search(text))


def _extract_endpoint_phrase(text: str) -> str:
    """Extract a short endpoint descriptor ('at week 68', 'from baseline')."""
    if not text:
        return ""
    low = text.lower()
    for pat in (
        r"at\s+week\s+\d+", r"at\s+\d+\s+weeks?",
        r"at\s+month\s+\d+", r"at\s+\d+\s+months?",
        r"from\s+baseline", r"mean\s+change",
        r"intent\s*-?\s*to\s*-?\s*treat",
        r"per\s+protocol",
        r"trial\s+product\s+estimand",
        # Wave-3 (I-arch-002 [2]): day + year endpoint patterns, placed LAST so
        # they fire ONLY when no pre-existing pattern matched. This keeps the
        # extractor byte-identical for every input the current tree already
        # matches (e.g. "change from baseline at day 28" still -> "from
        # baseline"); the day/year forms only newly resolve inputs that
        # previously returned "" ("at day N" / "at N days" / "at year N" /
        # "at N years").
        r"at\s+day\s+\d+", r"at\s+\d+\s+days?",
        r"at\s+year\s+\d+", r"at\s+\d+\s+years?",
    ):
        m = re.search(pat, low)
        if m:
            return m.group(0)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Wave-3 positive-known discriminator extractors (I-arch-002 [2])
#
# Each returns '' (the UNKNOWN sentinel) unless a POSITIVE token was extracted.
# A defaulted or PREDICATE-DERIVED value is NOT "known" (design §4.3): these
# extractors read the evidence text ONLY, never the predicate. Dormant carriers
# until claim_graph.build_merge_key reads them under PG_SWEEP_CREDIBILITY_REDESIGN.
# ─────────────────────────────────────────────────────────────────────────────

# Dosing cadence (per-time schedule). Orthogonal to the per-mass dose axis:
# "15 mg weekly" != "15 mg daily" (the ISMP methotrexate sentinel error).
_DOSE_FREQUENCY_RE = re.compile(
    r"\b(?P<tok>"
    r"q\.?d\.?|b\.?i\.?d\.?|t\.?i\.?d\.?|q\.?i\.?d\.?|"   # latin abbreviations
    r"q\s*\d+\s*h|q\s*\d+\s*hours?|"                       # q8h / q 12 hours
    r"once[-\s]?(?:daily|a\s+day|per\s+day|weekly|a\s+week)|"
    r"twice[-\s]?(?:daily|a\s+day|per\s+day|weekly|a\s+week)|"
    r"three\s+times[-\s]?(?:daily|a\s+day|per\s+day)|"
    r"daily|weekly|biweekly|fortnightly|monthly"
    r")\b",
    re.IGNORECASE,
)

# Normalize a matched cadence token to a canonical key.
_DOSE_FREQUENCY_NORMALIZE = (
    (re.compile(r"^q\.?d\.?$", re.IGNORECASE), "qd"),
    (re.compile(r"^b\.?i\.?d\.?$", re.IGNORECASE), "bid"),
    (re.compile(r"^t\.?i\.?d\.?$", re.IGNORECASE), "tid"),
    (re.compile(r"^q\.?i\.?d\.?$", re.IGNORECASE), "qid"),
    (re.compile(r"^q\s*(\d+)\s*h(?:ours?)?$", re.IGNORECASE), r"q\1h"),
    (re.compile(r"^once[-\s]?(?:daily|a\s+day|per\s+day)$", re.IGNORECASE), "qd"),
    (re.compile(r"^twice[-\s]?(?:daily|a\s+day|per\s+day)$", re.IGNORECASE), "bid"),
    (re.compile(r"^three\s+times[-\s]?(?:daily|a\s+day|per\s+day)$", re.IGNORECASE), "tid"),
    (re.compile(r"^once[-\s]?(?:weekly|a\s+week)$", re.IGNORECASE), "weekly"),
    (re.compile(r"^twice[-\s]?(?:weekly|a\s+week)$", re.IGNORECASE), "biweekly"),
)


def _extract_dose_frequency(text: str) -> str:
    """Cadence token (qd/bid/tid/q\\d+h/once-daily/weekly/...) or '' if none."""
    if not text:
        return ""
    m = _DOSE_FREQUENCY_RE.search(text)
    if not m:
        return ""
    raw = re.sub(r"\s+", " ", m.group("tok").strip()).lower()
    for pat, repl in _DOSE_FREQUENCY_NORMALIZE:
        if pat.match(raw):
            return pat.sub(repl, raw)
    return raw


# Comparator: "vs X" / "versus X" / "compared to X". Captures the comparator
# noun phrase (short, stops at clause punctuation).
_COMPARATOR_RE = re.compile(
    r"(?:vs\.?|versus|compared\s+(?:to|with)|relative\s+to)\s+"
    r"(?P<comp>[a-z0-9][a-z0-9\-\s]{0,40}?)"
    r"(?=[,.;:)\]]|\s+(?:at|in|with|for|over|by|and|was|were|achiev|reduc)\b|$)",
    re.IGNORECASE,
)


def _extract_comparator(text: str) -> str:
    """The 'vs/versus/compared-to X' comparator phrase, or '' if none."""
    if not text:
        return ""
    m = _COMPARATOR_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group("comp").strip()).lower()


# Route / formulation: IV / PO / SC / IM / ER / XR / SR, plus spelled-out forms.
_ROUTE_FORMULATION_RE = re.compile(
    r"\b(?P<tok>"
    r"i\.?v\.?|intravenous(?:ly)?|"
    r"p\.?o\.?|per\s+os|oral(?:ly)?|by\s+mouth|"
    r"s\.?c\.?|subcutaneous(?:ly)?|subq|"
    r"i\.?m\.?|intramuscular(?:ly)?|"
    r"e\.?r\.?|x\.?r\.?|s\.?r\.?|"
    r"extended[-\s]?release|sustained[-\s]?release|immediate[-\s]?release"
    r")\b",
    re.IGNORECASE,
)
_ROUTE_FORMULATION_NORMALIZE = (
    (re.compile(r"^(?:i\.?v\.?|intravenous(?:ly)?)$", re.IGNORECASE), "iv"),
    (re.compile(r"^(?:p\.?o\.?|per\s+os|oral(?:ly)?|by\s+mouth)$", re.IGNORECASE), "po"),
    (re.compile(r"^(?:s\.?c\.?|subcutaneous(?:ly)?|subq)$", re.IGNORECASE), "sc"),
    (re.compile(r"^(?:i\.?m\.?|intramuscular(?:ly)?)$", re.IGNORECASE), "im"),
    (re.compile(r"^(?:e\.?r\.?|extended[-\s]?release)$", re.IGNORECASE), "er"),
    (re.compile(r"^(?:x\.?r\.?)$", re.IGNORECASE), "xr"),
    (re.compile(r"^(?:s\.?r\.?|sustained[-\s]?release)$", re.IGNORECASE), "sr"),
    (re.compile(r"^immediate[-\s]?release$", re.IGNORECASE), "ir"),
)


def _extract_route_formulation(text: str) -> str:
    """Route/formulation token (iv/po/sc/im/er/...) or '' if none."""
    if not text:
        return ""
    m = _ROUTE_FORMULATION_RE.search(text)
    if not m:
        return ""
    raw = re.sub(r"\s+", " ", m.group("tok").strip()).lower()
    for pat, repl in _ROUTE_FORMULATION_NORMALIZE:
        if pat.match(raw):
            return repl
    return raw


# Effect measure: relative / absolute / HR / OR / RR / raw — ONLY on an EXPLICIT
# measure word. "30% relative risk reduction" != "30% absolute risk reduction".
_EFFECT_MEASURE_RE = (
    (re.compile(r"\brelative\s+risk\s+reduction\b|\brelative\s+reduction\b|"
                r"\brelative\s+risk\b|\brrr\b", re.IGNORECASE), "relative"),
    (re.compile(r"\babsolute\s+risk\s+reduction\b|\babsolute\s+reduction\b|"
                r"\babsolute\s+risk\b|\barr\b", re.IGNORECASE), "absolute"),
    (re.compile(r"\bhazard\s+ratio\b|\bhr\b", re.IGNORECASE), "hr"),
    (re.compile(r"\bodds\s+ratio\b|\bor\b", re.IGNORECASE), "or"),
    (re.compile(r"\brisk\s+ratio\b|\brate\s+ratio\b|\brr\b", re.IGNORECASE), "rr"),
)


def _extract_effect_measure(text: str) -> str:
    """Effect-measure type (relative/absolute/hr/or/rr) on explicit word, else ''."""
    if not text:
        return ""
    for pat, label in _EFFECT_MEASURE_RE:
        if pat.search(text):
            return label
    return ""


# Direction: EXPLICIT increase/decrease token ONLY. NEVER inferred from the
# predicate (design §4.3 — the predicate-derived fallback made "rose 5%" and
# "fell 5%" merge and broke design test #5).
_DIRECTION_INCREASE_RE = re.compile(
    r"\b(?:increas\w+|rose|rise|risen|rising|higher|elevat\w+|gain\w*|"
    r"up\s+by|grew|grow\w*|improv\w+|more)\b",
    re.IGNORECASE,
)
_DIRECTION_DECREASE_RE = re.compile(
    r"\b(?:decreas\w+|reduc\w+|reduction|fell|fall\w*|fallen|drop\w*|lower\w*|"
    r"declin\w+|loss|los[ts]?|down\s+by|shrank|shrunk|fewer|less)\b",
    re.IGNORECASE,
)


def _extract_direction(text: str) -> str:
    """'increase'/'decrease' from an EXPLICIT token only; '' if none/ambiguous.

    Token-only by design (§4.3): never derived from the predicate. When BOTH an
    increase and a decrease token appear the direction is ambiguous -> '' (keep
    separate / fail-closed at the merge key).
    """
    if not text:
        return ""
    up = bool(_DIRECTION_INCREASE_RE.search(text))
    down = bool(_DIRECTION_DECREASE_RE.search(text))
    if up and not down:
        return "increase"
    if down and not up:
        return "decrease"
    return ""


# Population / cohort: "in patients with X" / "in adults with X" / "among ...".
# The terminating lookahead stops the cohort phrase at a clause boundary or the
# onset of an outcome verb. Verb stems (achiev/reduc/...) intentionally carry NO
# trailing \b so they match the inflected forms ("achieved", "reduced").
_POPULATION_RE = re.compile(
    r"\b(?:in|among)\s+"
    r"(?P<pop>(?:patients?|adults?|children|subjects?|participants?|women|men|"
    r"individuals?|people)\b[a-z0-9\-\s]{0,50}?)"
    r"(?=[,.;:)\]]|\s+(?:achiev|reduc|experienc|demonstrat|report|produc|"
    r"had\b|who\s+receiv|with\s+a\b)|$)",
    re.IGNORECASE,
)


def _extract_population(text: str) -> str:
    """The 'in/among patients with X' cohort phrase, or '' if none."""
    if not text:
        return ""
    m = _POPULATION_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group("pop").strip()).lower()


def _find_value_in_context(
    text: str, predicate: str,
) -> Optional[tuple[float, str, str, int]]:
    """Find a numeric value that sits INSIDE a value-phrase context.

    Returns (value, unit, matched_context, anchor_position_in_text) or None.

    The algorithm:
      1. Find all percentage matches.
      2. For each, check a ±40-char window for:
         (a) A value-phrase verb  AND
         (b) NOT a reject pattern (placebo, threshold, trial acronym, duration)
      3. Return the first match that satisfies both.

    R-5 Fix B: also returns the anchor position so the caller can
    attribute subject (drug name) to the drug NEAREST the value,
    not the first drug appearing in the full quote.
    """
    if not text:
        return None

    # Predicate-specific unit handling
    if "hba1c" in predicate or "a1c" in predicate:
        for m in _HBA1C_RE.finditer(text):
            window = text[max(0, m.start() - 40): min(len(text), m.end() + 40)]
            if _is_reject_context(window, m.start() - max(0, m.start() - 40)):
                continue
            if not _VALUE_PHRASE_VERBS.search(window):
                continue
            try:
                return (
                    float(m.group("value")), "percentage_points",
                    window, m.start(),
                )
            except ValueError:
                continue
        return None

    for m in _PCT_RE.finditer(text):
        start_win = max(0, m.start() - 40)
        end_win = min(len(text), m.end() + 40)
        window = text[start_win:end_win]
        # Reject if window is a comparator/threshold/acronym/duration
        if _is_reject_context(window, m.start() - start_win):
            continue
        if not _VALUE_PHRASE_VERBS.search(window):
            continue
        try:
            return (float(m.group("value")), "%", window, m.start())
        except ValueError:
            continue
    return None


def _is_reject_context(window: str, num_pos_in_window: int) -> bool:
    """Return True if the number at `num_pos_in_window` is in a reject context.

    We check the immediate left/right 30 chars around the number only —
    this prevents a distant "placebo" elsewhere in the window from
    wrongly rejecting a treatment-arm claim.
    """
    near_start = max(0, num_pos_in_window - 30)
    near_end = min(len(window), num_pos_in_window + 30)
    near = window[near_start:near_end]
    if _PLACEBO_CONTEXT_RE.search(near):
        return True
    if _ACHIEVEMENT_THRESHOLD_RE.search(near):
        return True
    if _TRIAL_ACRONYM_NUM_RE.search(near):
        return True
    # Duration reject: only if the number itself is inside a week/month/year span
    m = _DURATION_NUM_RE.search(near)
    if m and m.start() <= num_pos_in_window - near_start <= m.end():
        return True
    return False


def _extract_numeric_value(text: str, predicate: str) -> Optional[tuple[float, str]]:
    """Back-compat: returns (value, unit) without the context.

    The new pipeline uses _find_value_in_context() directly to also
    capture the endpoint phrase; this shim keeps older call-sites
    working during the Fix-1 rollout.
    """
    if not text:
        return None
    result = _find_value_in_context(text, predicate)
    if result:
        v, u, _ctx, _pos = result
        return (v, u)

    # Fallback: if no value-phrase match, fall back to the previous
    # loose extraction — but ONLY for the predicate-specific regex,
    # not the generic "any percentage in the quote" fallback which
    # was the source of Fix-1 false positives.
    if "hba1c" in predicate or "a1c" in predicate:
        m = _HBA1C_RE.search(text)
        if m:
            try:
                return float(m.group("value")), "percentage_points"
            except ValueError:
                return None
    if "duration" in predicate:
        m = _DURATION_RE.search(text)
        if m:
            try:
                return float(m.group("value")), m.group("unit").lower()
            except ValueError:
                return None
    return None


def extract_numeric_claims(
    evidence: list[dict[str, Any]],
    domain: str | None = None,
) -> list[ExtractedNumericClaim]:
    """Extract structured numeric claims from evidence rows.

    Each evidence dict should have 'evidence_id', 'direct_quote' (or
    'statement'), 'source_url', 'tier'. Missing fields are handled.

    BUG-M-202 fix (deep-dive R7): `domain` parameter routes to a
    broader predicate set for non-clinical queries. Default None
    preserves the union-fallback (original behavior).
    """
    claims: list[ExtractedNumericClaim] = []
    for ev in evidence:
        quote = ev.get("direct_quote") or ev.get("statement") or ""
        if not quote:
            continue
        predicate = _normalize_predicate(quote, domain=domain)
        if not predicate:
            continue

        # Fix-1 uses _find_value_in_context which returns the matched
        # window so we can store the endpoint phrase.
        in_context = _find_value_in_context(quote, predicate)
        if in_context is None:
            continue
        value, unit, ctx_window, anchor_pos = in_context

        # R-5 Fix B: subject must be the drug NEAREST the numeric value,
        # not the first drug in the quote. Cross-drug comparison quotes
        # like "Zepbound 25.5% compared to CagriSema 23%" were mis-
        # attributing to the first drug mentioned earlier in the full
        # direct_quote (often the paragraph's primary topic, e.g.
        # retatrutide). _subject_near_position searches ±150 chars
        # around the value's position and picks the closest drug match.
        subject = _subject_near_position(quote, anchor_pos, fallback="unknown")

        dose = _extract_dose(ctx_window) or _extract_dose(quote)
        # arm classification: if the value sits in a placebo context
        # it wouldn't have passed _find_value_in_context, but we also
        # tag "comparator_adjacent" when the ctx includes "vs placebo"
        # farther out (this is additional info for display, not a filter).
        # Wave-3 (I-arch-002 [2], design §4.3): a DEFAULTED arm is NOT
        # positively-known — so when NO placebo/comparator cue fires the arm is
        # None (UNKNOWN), not the legacy "treatment" default. build_merge_key
        # then treats it as an unknown discriminator and keeps the claim a
        # singleton rather than over-merging.
        if _detect_placebo_arm(ctx_window):
            arm: Optional[str] = "comparator_adjacent"
        else:
            arm = None
        endpoint_phrase = _extract_endpoint_phrase(ctx_window) or _extract_endpoint_phrase(quote)

        # Wave-3 positive-known discriminators (I-arch-002 [2]). Each reads the
        # evidence text ONLY (ctx first, then full quote) and yields '' when no
        # positive token is present. Dormant until build_merge_key reads them.
        dose_frequency = _extract_dose_frequency(ctx_window) or _extract_dose_frequency(quote)
        comparator = _extract_comparator(ctx_window) or _extract_comparator(quote)
        route_formulation = _extract_route_formulation(ctx_window) or _extract_route_formulation(quote)
        effect_measure = _extract_effect_measure(ctx_window) or _extract_effect_measure(quote)
        direction = _extract_direction(ctx_window) or _extract_direction(quote)
        population = _extract_population(ctx_window) or _extract_population(quote)

        claims.append(ExtractedNumericClaim(
            evidence_id=str(ev.get("evidence_id", "")),
            subject=subject,
            predicate=predicate,
            value=value,
            unit=unit,
            context_snippet=ctx_window[:200],
            source_url=ev.get("source_url", ""),
            source_tier=ev.get("tier", ""),
            dose=dose,
            arm=arm,
            endpoint_phrase=endpoint_phrase,
            dose_frequency=dose_frequency,
            comparator=comparator,
            route_formulation=route_formulation,
            effect_measure=effect_measure,
            direction=direction,
            population=population,
        ))
    return claims


# ─────────────────────────────────────────────────────────────────────────────
# Contradiction detection
# ─────────────────────────────────────────────────────────────────────────────

# Relative-difference threshold (|a-b|/min(|a|,|b|)) above which we
# flag a contradiction. Default 0.10 = 10%.
PG_CONTRADICTION_REL_THRESHOLD = float(
    os.getenv("PG_CONTRADICTION_REL_THRESHOLD", "0.10")
)

# Absolute-difference threshold (in the claim's native unit). If the
# relative threshold is tripped, absolute threshold is an AND filter —
# both must exceed to flag (avoids flagging 0.01 vs 0.03 rel=66%).
PG_CONTRADICTION_ABS_THRESHOLD = float(
    os.getenv("PG_CONTRADICTION_ABS_THRESHOLD", "1.0")
)


def _severity(rel: float, abs_: float) -> str:
    if rel >= 0.25 or abs_ >= 5.0:
        return "high"
    if rel >= 0.15 or abs_ >= 2.5:
        return "medium"
    return "low"


def detect_contradictions(
    claims: list[ExtractedNumericClaim],
    *,
    rel_threshold: Optional[float] = None,
    abs_threshold: Optional[float] = None,
) -> list[ContradictionRecord]:
    """Group claims by (subject, predicate, unit, dose) and flag discrepancies.

    Fix-1: grouping key now includes DOSE. A 2.4 mg weight-loss result
    and a 7.2 mg weight-loss result are NOT a contradiction — they're
    expected dose-response differences. They will only be grouped
    together if both happen to have no dose tag (e.g., a narrative
    review that doesn't specify dose).
    """
    if rel_threshold is None:
        rel_threshold = PG_CONTRADICTION_REL_THRESHOLD
    if abs_threshold is None:
        abs_threshold = PG_CONTRADICTION_ABS_THRESHOLD

    grouped: dict[tuple[str, str, str, str], list[ExtractedNumericClaim]] = {}
    for c in claims:
        key = (c.subject, c.predicate, c.unit, c.dose or "")
        grouped.setdefault(key, []).append(c)

    records: list[ContradictionRecord] = []
    for (subject, predicate, unit, dose), group in grouped.items():
        if len(group) < 2:
            continue
        values = [c.value for c in group]
        vmin, vmax = min(values), max(values)
        denom = max(abs(vmin), 1e-9)
        rel = abs(vmax - vmin) / denom
        abs_diff = abs(vmax - vmin)
        if rel >= rel_threshold and abs_diff >= abs_threshold:
            predicate_display = predicate
            if dose:
                predicate_display = f"{predicate} ({dose})"
            records.append(ContradictionRecord(
                subject=subject,
                predicate=predicate_display,
                claims=sorted(group, key=lambda c: c.value),
                relative_difference=round(rel, 4),
                absolute_difference=round(abs_diff, 4),
                severity=_severity(rel, abs_diff),
            ))

    # Sort by severity (high first), then predicate
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    records.sort(key=lambda r: (severity_rank.get(r.severity, 3), r.predicate))
    return records


def format_contradictions_for_user(
    records: list[ContradictionRecord],
) -> str:
    """Human-readable plain-text summary."""
    if not records:
        return "No contradictions detected in the evidence corpus."
    lines = [
        f"Detected {len(records)} contradiction(s) in the evidence corpus.",
        "",
    ]
    for i, r in enumerate(records, 1):
        lines.append(
            f"[{i}] {r.subject} / {r.predicate} — "
            f"severity={r.severity}, rel_diff={r.relative_difference*100:.1f}%, "
            f"abs_diff={r.absolute_difference:.2f} {r.claims[0].unit}"
        )
        for c in r.claims:
            lines.append(
                f"    - {c.value} {c.unit}   "
                f"[ev={c.evidence_id}, tier={c.source_tier}]   "
                f"{c.context_snippet[:120]}"
            )
        lines.append(f"    Action: {r.recommended_action}")
        lines.append("")
    return "\n".join(lines)
