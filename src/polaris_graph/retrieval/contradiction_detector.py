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
    arm: str = "treatment"     # "treatment", "placebo", "comparator"
    endpoint_phrase: str = ""  # e.g., "at week 68", "from baseline", "mean change"


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

# Dose pattern (captures the full "X.X mg" string for grouping).
_DOSE_CAPTURE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*m[gc]g?|\d+(?:\.\d+)?\s*[µu]g|\d+(?:\.\d+)?\s*g\b)",
    re.IGNORECASE,
)


def _extract_dose(text: str) -> str:
    """Extract the most-salient dose token from the text (for grouping)."""
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
    ):
        m = re.search(pat, low)
        if m:
            return m.group(0)
    return ""


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
        # tag "comparator" when the ctx includes "vs placebo" farther
        # out (this is additional info for display, not a filter).
        if _detect_placebo_arm(ctx_window):
            arm = "comparator_adjacent"
        else:
            arm = "treatment"
        endpoint_phrase = _extract_endpoint_phrase(ctx_window) or _extract_endpoint_phrase(quote)

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
