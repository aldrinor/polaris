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
_EFFICACY_PREDICATES = (
    "weight loss", "body weight", "weight reduction",
    "hba1c reduction", "a1c reduction",
    "systolic blood pressure reduction", "diastolic blood pressure reduction",
    "ldl reduction", "cholesterol reduction",
    "cardiovascular risk reduction", "mace reduction",
    "mortality reduction",
)

_SAFETY_PREDICATES = (
    "incidence of nausea", "incidence of vomiting",
    "discontinuation rate", "adverse event rate",
    "serious adverse event rate", "pancreatitis incidence",
    "hypoglycemia incidence", "thyroid c-cell",
)


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


def _normalize_predicate(text: str) -> Optional[str]:
    """Return the predicate keyword if present in the text."""
    t = (text or "").lower()
    for p in _EFFICACY_PREDICATES + _SAFETY_PREDICATES:
        if p in t:
            return p
    return None


def _normalize_subject(text: str, fallback: str = "unknown") -> str:
    """Extract a drug name or fallback."""
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE
    m = _DRUG_NAME_RE.search(text or "")
    if m:
        return m.group(1).lower()
    return fallback


def _extract_numeric_value(text: str, predicate: str) -> Optional[tuple[float, str]]:
    """Extract the numeric value + unit that most likely belongs to the predicate."""
    if not text:
        return None
    t = text

    # Pick a regex based on predicate
    if "hba1c" in predicate or "a1c" in predicate:
        m = _HBA1C_RE.search(t)
        if m:
            try:
                return float(m.group("value")), "percentage_points"
            except ValueError:
                return None
    if "reduction" in predicate or "weight" in predicate or "incidence" in predicate or "rate" in predicate:
        m = _PCT_RE.search(t)
        if m:
            try:
                return float(m.group("value")), "%"
            except ValueError:
                return None
    if "duration" in predicate:
        m = _DURATION_RE.search(t)
        if m:
            try:
                return float(m.group("value")), m.group("unit").lower()
            except ValueError:
                return None
    # Fallback: first percentage in the text
    m = _PCT_RE.search(t)
    if m:
        try:
            return float(m.group("value")), "%"
        except ValueError:
            return None
    return None


def extract_numeric_claims(
    evidence: list[dict[str, Any]],
) -> list[ExtractedNumericClaim]:
    """Extract structured numeric claims from evidence rows.

    Each evidence dict should have 'evidence_id', 'direct_quote' (or
    'statement'), 'source_url', 'tier'. Missing fields are handled.
    """
    claims: list[ExtractedNumericClaim] = []
    for ev in evidence:
        quote = ev.get("direct_quote") or ev.get("statement") or ""
        if not quote:
            continue
        predicate = _normalize_predicate(quote)
        if not predicate:
            continue
        subject = _normalize_subject(quote)
        numeric = _extract_numeric_value(quote, predicate)
        if numeric is None:
            continue
        value, unit = numeric
        claims.append(ExtractedNumericClaim(
            evidence_id=str(ev.get("evidence_id", "")),
            subject=subject,
            predicate=predicate,
            value=value,
            unit=unit,
            context_snippet=quote[:200],
            source_url=ev.get("source_url", ""),
            source_tier=ev.get("tier", ""),
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
    """Group claims by (subject, predicate, unit) and flag discrepancies."""
    if rel_threshold is None:
        rel_threshold = PG_CONTRADICTION_REL_THRESHOLD
    if abs_threshold is None:
        abs_threshold = PG_CONTRADICTION_ABS_THRESHOLD

    grouped: dict[tuple[str, str, str], list[ExtractedNumericClaim]] = {}
    for c in claims:
        key = (c.subject, c.predicate, c.unit)
        grouped.setdefault(key, []).append(c)

    records: list[ContradictionRecord] = []
    for (subject, predicate, unit), group in grouped.items():
        if len(group) < 2:
            continue
        values = [c.value for c in group]
        vmin, vmax = min(values), max(values)
        denom = max(abs(vmin), 1e-9)
        rel = abs(vmax - vmin) / denom
        abs_diff = abs(vmax - vmin)
        if rel >= rel_threshold and abs_diff >= abs_threshold:
            records.append(ContradictionRecord(
                subject=subject,
                predicate=predicate,
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
