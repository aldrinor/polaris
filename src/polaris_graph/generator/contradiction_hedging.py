"""M-71 contradiction-aware hedging for section prose.

Contradictions are routed using vocabulary carried by the contradiction
record itself.  Section titles are never mapped to a baked-in subject
taxonomy: relevance comes from token overlap with record fields, explicit
record routing metadata, or generic comparative syntax.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("polaris_graph.contradiction_hedging")


# ─────────────────────────────────────────────────────────────────────
# Evidence-derived section relevance
# ─────────────────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"[^\W\d_][\w'-]*", re.UNICODE)
_COMPARISON_RE = re.compile(
    r"\b(?:versus|vs\.?|compared\s+(?:to|with)|relative\s+to|than)\b",
    re.IGNORECASE,
)


def _section_keywords_for(title: str) -> frozenset[str]:
    """Return meaningful vocabulary written in the section title itself."""

    return frozenset(
        token.casefold()
        for token in _WORD_RE.findall(str(title or ""))
        if len(token) > 2
    )


def _iter_text_values(value: Any) -> list[str]:
    """Flatten text-bearing routing metadata without assuming a schema."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [item for entry in value for item in _iter_text_values(entry)]
    if isinstance(value, dict):
        return [item for entry in value.values() for item in _iter_text_values(entry)]
    return []


def _record_routing_tokens(c: dict[str, Any]) -> frozenset[str]:
    """Derive routing vocabulary from the detector record."""

    routing_values: list[str] = []
    for key in (
        "subject",
        "predicate",
        "endpoint",
        "measure",
        "metric",
        "context",
        "section",
        "sections",
        "section_title",
        "topics",
        "tags",
    ):
        routing_values.extend(_iter_text_values(c.get(key)))
    return frozenset(
        token.casefold()
        for value in routing_values
        for token in _WORD_RE.findall(value)
        if len(token) > 2
    )


def _contradiction_text_blob(c: dict[str, Any]) -> str:
    """Concatenate the record's own text-bearing fields."""

    return " ".join(sorted(_record_routing_tokens(c)))


def _is_section_relevant(section_title: str, c: dict[str, Any]) -> bool:
    """Route by evidence-derived vocabulary or generic comparison syntax."""

    explicit_owner = str(c.get("section_title") or "").strip()
    if (
        explicit_owner
        and c.get("comparison_status") == "conflict"
        and c.get("confidence") == "confirmed"
    ):
        return explicit_owner.casefold() == str(section_title or "").strip().casefold()
    section_tokens = _section_keywords_for(section_title)
    record_tokens = _record_routing_tokens(c)
    if section_tokens & record_tokens:
        return True
    if any(token.startswith("compar") for token in section_tokens):
        raw = " ".join(
            value
            for key in ("subject", "predicate", "endpoint", "measure", "metric", "context")
            for value in _iter_text_values(c.get(key))
        )
        return bool(_COMPARISON_RE.search(raw))
    return False


# ─────────────────────────────────────────────────────────────────────
# Severity gate
# ─────────────────────────────────────────────────────────────────────
def _is_high_severity(c: dict[str, Any]) -> bool:
    """Return True iff the contradiction is worth surfacing in body
    prose. Codex's gate: ≥3 distinct values + ≥30% relative spread
    + ≥1 T1 source."""
    if (
        c.get("comparison_status") == "conflict"
        and c.get("confidence") == "confirmed"
        and c.get("reason")
    ):
        return True
    values = c.get("values") or c.get("cited_values") or []
    if not isinstance(values, list) or len(values) < 3:
        return False
    nums: list[float] = []
    for v in values:
        if isinstance(v, (int, float)):
            nums.append(float(v))
        elif isinstance(v, dict):
            nv = v.get("value")
            if isinstance(nv, (int, float)):
                nums.append(float(nv))
    if len(nums) < 3:
        return False
    lo, hi = min(nums), max(nums)
    if lo == 0:
        # Avoid div-by-zero; require absolute spread > 1
        if hi - lo < 1:
            return False
    else:
        rel_spread = abs(hi - lo) / max(abs(lo), abs(hi))
        if rel_spread < 0.30:
            return False
    # Tier mix check
    tiers = c.get("tiers") or c.get("source_tiers") or []
    if isinstance(tiers, list) and not any(
        isinstance(t, str) and t.upper() == "T1" for t in tiers
    ):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SectionContradictionHint:
    """One contradiction routed to one section, ready for prompt
    injection."""
    section_title: str
    subject: str
    predicate: str
    value_range: str  # "5.0 to 93.5%"
    tiers: tuple[str, ...]  # ("T1", "T2", "T4")
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""


def filter_section_contradictions(
    section_title: str,
    contradictions: list[dict[str, Any]] | None,
    *,
    max_per_section: int = 2,
) -> list[SectionContradictionHint]:
    """Return up to `max_per_section` contradiction hints relevant
    to the named section. Filters by:
      1. Section keyword overlap with subject+predicate
      2. High-severity (Codex gate)
      3. Top-N truncation by relative spread (largest first)
    """
    if not contradictions:
        return []
    if not _section_keywords_for(section_title):
        return []

    candidates: list[tuple[float, SectionContradictionHint]] = []
    confirmed: list[SectionContradictionHint] = []
    for c in contradictions:
        if not isinstance(c, dict):
            continue
        if not _is_section_relevant(section_title, c):
            continue
        if not _is_high_severity(c):
            continue
        if c.get("comparison_status") == "conflict" and c.get("confidence") == "confirmed":
            confirmed.append(SectionContradictionHint(
                section_title=section_title,
                subject=str(c.get("subject", "")),
                predicate=str(c.get("predicate", "")),
                value_range="",
                tiers=(),
                evidence_ids=tuple(str(item) for item in (c.get("evidence_ids") or [])),
                reason=str(c.get("reason") or ""),
            ))
            continue
        # Severity score (= relative spread)
        values = c.get("values") or c.get("cited_values") or []
        nums: list[float] = []
        for v in values:
            if isinstance(v, (int, float)):
                nums.append(float(v))
            elif isinstance(v, dict):
                nv = v.get("value")
                if isinstance(nv, (int, float)):
                    nums.append(float(nv))
        if len(nums) < 3:
            continue
        lo, hi = min(nums), max(nums)
        spread = abs(hi - lo)

        tiers_raw = c.get("tiers") or c.get("source_tiers") or []
        tiers = tuple(
            t for t in tiers_raw if isinstance(t, str)
        )
        hint = SectionContradictionHint(
            section_title=section_title,
            subject=str(c.get("subject", "")),
            predicate=str(c.get("predicate", "")),
            value_range=f"{lo:g} to {hi:g}",
            tiers=tiers,
        )
        candidates.append((spread, hint))

    # Sort by spread descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    return confirmed + [h for _, h in candidates[:max_per_section]]


def render_section_hedging_block(
    hints: list[SectionContradictionHint],
) -> str:
    """Render a section-local hedging instruction block for the LLM
    prompt. Returns empty string when no hints (no prompt change for
    that section)."""
    if not hints:
        return ""
    lines = [
        "",
        "=== M-71 SECTION-LOCAL HEDGING REQUIREMENT ===",
        (
            "The contradiction detector flagged the following "
            "high-severity numeric disagreements in this section's "
            "evidence pool. INCLUDE ONE HEDGED SENTENCE acknowledging "
            "the disagreement in the body prose (not just the "
            "Limitations appendix). Use language like 'sources disagree "
            "on the magnitude of', 'reported values range from X to Y', "
            "or 'T1 vs T4 evidence diverges on'. Cite the relevant "
            "[ev_XXX] markers when stating the range."
        ),
        "",
    ]
    for h in hints:
        if h.reason and h.evidence_ids:
            rows = " and ".join(h.evidence_ids)
            lines.append(
                f"  - Rows {rows} report incompatible findings on the same quantity or "
                f"relationship: {h.reason} Address the disagreement explicitly and say what "
                "differs (population, method, period, or measure)."
            )
            continue
        tier_str = "/".join(h.tiers) if h.tiers else "mixed tiers"
        lines.append(
            f"  - Subject: {h.subject!r}, Predicate: {h.predicate!r}; "
            f"reported values range {h.value_range} (source tiers: {tier_str})"
        )
    lines.append("")
    return "\n".join(lines)
