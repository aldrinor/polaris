"""V32 — M-71 contradiction-aware hedging for section prose.

Codex strategic review (2026-04-25): run-9..run-11 Qwen flagged
hedging_appropriateness=needs_revision because the explicit
contradiction disclosure lives only in the appendix while the body
sections (Safety, Comparative, Population Subgroups) make assertive
claims without acknowledging the disagreements.

This module:

  1. CLASSIFIES contradictions by section relevance using
     subject/predicate keyword tagging.
  2. FILTERS to high-severity, same-endpoint/same-population
     clusters per section so the LLM doesn't get flooded by noisy
     detector output.
  3. RENDERS a SECTION_HEDGING_BLOCK that gets injected into the
     section prompt instructing the LLM to add ONE hedged sentence
     when a contradiction materially changes interpretation.

Codex's framing (verbatim):
  "Run-11 Qwen is mainly objecting to hedging, not to section
   layout or missing section types. You already have contradiction
   JSON and the relevant body sections. The missing step is
   section-local injection: feed only high-severity, same-endpoint/
   same-population disagreement clusters into Safety, Comparative,
   and Population Subgroups, and require one hedged sentence when
   a contradiction materially changes interpretation."

## Section relevance taxonomy

| Section            | Relevant predicates / subjects                   |
|--------------------|--------------------------------------------------|
| Safety             | hypoglycemia, adverse events, GI events, AE     |
| Comparative        | weight, body weight, HbA1c, vs                  |
| Population Subgroups | weight loss, BMI, age, dose                    |
| Efficacy           | HbA1c, primary endpoint, ETD                    |

A contradiction is relevant to a section iff its
subject/predicate matches one of the section's keyword lists.

## Severity gate

A contradiction is high-severity iff:
  - At least 3 distinct values cited (i.e., genuine multi-source
    disagreement, not a single outlier)
  - Numeric range > 30% relative spread
  - Tier mix includes ≥1 T1 source (so the disagreement isn't
    pure noise from low-tier outliers)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("polaris_graph.contradiction_hedging")


# ─────────────────────────────────────────────────────────────────────
# Section relevance classification
# ─────────────────────────────────────────────────────────────────────
_SECTION_KEYWORDS: dict[str, frozenset[str]] = {
    "safety": frozenset({
        "hypoglycemia", "adverse", "gi", "gastrointestinal",
        "nausea", "vomiting", "diarrhea", "discontinuation",
        "tolerability", "ae", "serious",
    }),
    "comparative": frozenset({
        "weight", "body weight", "weight loss", "hba1c",
        "ttr", "weight reduction", "vs", "versus",
    }),
    "population subgroups": frozenset({
        "weight loss", "weight reduction", "bmi",
        "body mass index", "age", "elderly", "dose",
        "ethnicity", "subgroup",
    }),
    "efficacy": frozenset({
        "hba1c", "primary endpoint", "etd",
        "treatment difference", "glycemic", "glucose",
    }),
}


def _section_keywords_for(title: str) -> frozenset[str]:
    """Look up the section's keyword set by title (case-insensitive,
    fuzzy)."""
    norm = title.strip().lower()
    for key, kws in _SECTION_KEYWORDS.items():
        if key in norm:
            return kws
    return frozenset()


def _contradiction_text_blob(c: dict[str, Any]) -> str:
    """Concatenate subject + predicate + dose into a search blob."""
    parts = []
    for k in ("subject", "predicate", "dose", "endpoint", "context"):
        v = c.get(k)
        if isinstance(v, str):
            parts.append(v.lower())
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────
# Severity gate
# ─────────────────────────────────────────────────────────────────────
def _is_high_severity(c: dict[str, Any]) -> bool:
    """Return True iff the contradiction is worth surfacing in body
    prose. Codex's gate: ≥3 distinct values + ≥30% relative spread
    + ≥1 T1 source."""
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
    keywords = _section_keywords_for(section_title)
    if not keywords:
        return []

    candidates: list[tuple[float, SectionContradictionHint]] = []
    for c in contradictions:
        if not isinstance(c, dict):
            continue
        blob = _contradiction_text_blob(c)
        if not any(kw in blob for kw in keywords):
            continue
        if not _is_high_severity(c):
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
    return [h for _, h in candidates[:max_per_section]]


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
        tier_str = "/".join(h.tiers) if h.tiers else "mixed tiers"
        lines.append(
            f"  - Subject: {h.subject!r}, Predicate: {h.predicate!r}; "
            f"reported values range {h.value_range} (source tiers: {tier_str})"
        )
    lines.append("")
    return "\n".join(lines)
