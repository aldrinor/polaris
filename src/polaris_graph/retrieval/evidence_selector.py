"""
Evidence selector — BUG-M-201 fix (deep-dive R6).

Pre-fix, `run_one_query` passed `retrieval.evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]`
to the generator — raw retrieval order with no tier awareness. Gates
reasoned over the full pool; generation reasoned over a smaller,
order-biased subset. Real artifacts showed 20 corpus sources but
only 4 evidence rows surviving to generation.

Post-fix, `select_evidence_for_generation()` produces a deterministic,
tier-balanced, relevance-ranked subset. The result is emitted to
`manifest.json.evidence_selection` so downstream consumers can see
exactly what the generator saw.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Tier priority for within-pool ranking. Lower tier number = higher priority.
_TIER_PRIORITY: dict[str, int] = {
    "T1": 1, "T2": 2, "T3": 3, "T4": 4,
    "T5": 5, "T6": 6, "T7": 7, "UNKNOWN": 8,
}

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "as",
    "that", "this", "these", "those", "it", "its", "be", "been",
    "what", "which", "who", "how", "why", "when", "where",
})


def _content_tokens(text: str) -> set[str]:
    """Lowercase content-word tokens, stopword-filtered, 3+ chars."""
    toks = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    return {t for t in toks if t not in _STOPWORDS}


@dataclass
class EvidenceSelection:
    """Result of select_evidence_for_generation."""
    selected_rows: list[dict[str, Any]]
    full_counts: dict[str, int]        # tier -> count in FULL pool
    selected_counts: dict[str, int]    # tier -> count in SELECTED subset
    dropped_count: int
    selection_strategy: str            # stable identifier for telemetry
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_total": (
                sum(self.full_counts.values())
            ),
            "evidence_selected": len(self.selected_rows),
            "selection_strategy": self.selection_strategy,
            "full_tier_counts": dict(self.full_counts),
            "selected_tier_counts": dict(self.selected_counts),
            "dropped_count": self.dropped_count,
            "notes": list(self.notes),
        }


def _row_tier(row: dict[str, Any], url_to_tier: dict[str, str]) -> str:
    """Resolve tier for an evidence row via URL join to classified sources.
    Falls back to row's own `tier` field, then UNKNOWN."""
    url = row.get("source_url") or row.get("url") or ""
    if url in url_to_tier:
        return url_to_tier[url]
    tier = row.get("tier") or "UNKNOWN"
    return str(tier)


def _row_relevance(
    row: dict[str, Any],
    question_tokens: set[str],
    protocol_tokens: set[str],
) -> float:
    """Deterministic lexical relevance score in [0, 1].

    Overlap between the union of question+protocol tokens and the
    evidence's statement+direct_quote content tokens. Jaccard-ish but
    normalized by the question side so longer evidence doesn't dominate.
    """
    text = " ".join(str(row.get(k, "") or "") for k in ("statement", "direct_quote"))
    ev_toks = _content_tokens(text)
    anchors = question_tokens | protocol_tokens
    if not anchors:
        return 0.0
    overlap = ev_toks & anchors
    return len(overlap) / max(1, len(anchors))


def select_evidence_for_generation(
    *,
    research_question: str,
    protocol: dict[str, Any] | None,
    classified_sources: list[Any],
    evidence_rows: list[dict[str, Any]],
    max_rows: int,
) -> EvidenceSelection:
    """Pick up to max_rows evidence rows, tier-balanced + relevance-ranked.

    Strategy (deterministic, stable):
      1. Join evidence rows to classified sources by URL → tier per row.
      2. Compute full_tier_counts.
      3. Score each row by lexical relevance (question+protocol anchors
         vs statement+direct_quote content words).
      4. Sort within each tier by (-relevance, original_index) for
         deterministic top-N per tier.
      5. Allocate slots proportionally to full_tier_counts but with
         floors for high-value tiers that are present (each T1-T3 tier
         present gets at least min(1, available)).
      6. Fill remaining slots globally by (tier_priority, -relevance,
         original_index).

    Args:
        research_question: the user's raw question.
        protocol: scope protocol dict (uses population/intervention/
            comparator/outcome/research_question if present).
        classified_sources: list of objects with .url and .tier (or
            dict-like with those keys). Used for URL→tier join.
        evidence_rows: full evidence row pool.
        max_rows: target selection size.

    Returns:
        EvidenceSelection with selected_rows + telemetry.
    """
    if max_rows <= 0 or not evidence_rows:
        return EvidenceSelection(
            selected_rows=[], full_counts={}, selected_counts={},
            dropped_count=0, selection_strategy="tier_balanced_v1",
            notes=["no evidence rows or max_rows <= 0"],
        )

    # Build URL → tier map from classified_sources (whatever shape).
    url_to_tier: dict[str, str] = {}
    for src in classified_sources or []:
        url = getattr(src, "url", None) or (
            src.get("url") if isinstance(src, dict) else None
        )
        tier = getattr(src, "tier", None) or (
            src.get("tier") if isinstance(src, dict) else None
        )
        if url and tier:
            url_to_tier[str(url)] = str(tier)

    # Compute relevance tokens from research question + protocol anchors.
    question_tokens = _content_tokens(research_question or "")
    protocol_tokens: set[str] = set()
    if protocol:
        for key in ("population", "intervention", "comparator",
                    "outcome", "research_question"):
            v = protocol.get(key)
            if v:
                protocol_tokens |= _content_tokens(str(v))

    # Score every row and tag with tier + original index.
    scored: list[tuple[int, float, str, dict[str, Any]]] = []
    for idx, row in enumerate(evidence_rows):
        tier = _row_tier(row, url_to_tier)
        score = _row_relevance(row, question_tokens, protocol_tokens)
        scored.append((idx, score, tier, row))

    # Full tier counts (FROM evidence_rows, the selectable universe).
    full_counts: dict[str, int] = {}
    for _, _, tier, _ in scored:
        full_counts[tier] = full_counts.get(tier, 0) + 1

    # Early exit: if total <= max_rows, keep everything (but still emit
    # telemetry so the manifest is consistent).
    if len(scored) <= max_rows:
        selected_counts = dict(full_counts)
        return EvidenceSelection(
            selected_rows=list(evidence_rows),
            full_counts=full_counts,
            selected_counts=selected_counts,
            dropped_count=0,
            selection_strategy="tier_balanced_v1_all",
            notes=[f"pool_size<=max_rows ({len(scored)}/{max_rows})"],
        )

    # Floors: reserve at least 1 slot for each present T1, T2, T3
    # (high-value tiers) if pool has any.
    present_hv = [t for t in ("T1", "T2", "T3") if full_counts.get(t, 0) > 0]

    # Proportional allocation.
    quotas: dict[str, int] = {}
    allocated = 0
    # First pass: proportional (round down).
    for tier, n in full_counts.items():
        share = int(round(max_rows * n / len(scored)))
        quotas[tier] = share
        allocated += share

    # Enforce floors for high-value tiers present.
    for tier in present_hv:
        if quotas.get(tier, 0) < 1:
            delta = 1 - quotas.get(tier, 0)
            quotas[tier] = quotas.get(tier, 0) + delta
            allocated += delta

    # Cap: can't give a tier more than it has.
    for tier in list(quotas.keys()):
        quotas[tier] = min(quotas[tier], full_counts[tier])

    # Rebalance: while allocated != max_rows, adjust.
    allocated = sum(quotas.values())
    # If over-allocated: deduct from lowest-priority tiers first.
    while allocated > max_rows:
        lowest = max(
            (t for t, q in quotas.items() if q > 0),
            key=lambda t: (_TIER_PRIORITY.get(t, 9), t),
        )
        # Don't deduct below floor for high-value present tiers.
        if lowest in present_hv and quotas[lowest] <= 1:
            # try next-lowest
            candidates = [
                t for t, q in quotas.items() if q > 0
                and not (t in present_hv and q <= 1)
            ]
            if not candidates:
                break
            lowest = max(candidates, key=lambda t: (_TIER_PRIORITY.get(t, 9), t))
        quotas[lowest] -= 1
        allocated -= 1
    # If under-allocated: add to highest-priority tiers with remaining capacity.
    while allocated < max_rows:
        candidates = [
            t for t, q in quotas.items()
            if q < full_counts.get(t, 0)
        ]
        if not candidates:
            break
        best = min(candidates, key=lambda t: (_TIER_PRIORITY.get(t, 9), t))
        quotas[best] += 1
        allocated += 1

    # Now pick within each tier by (-score, original_idx).
    by_tier: dict[str, list[tuple[int, float, str, dict[str, Any]]]] = {}
    for item in scored:
        by_tier.setdefault(item[2], []).append(item)
    for tier in by_tier:
        by_tier[tier].sort(key=lambda x: (-x[1], x[0]))

    selected: list[tuple[int, float, str, dict[str, Any]]] = []
    for tier, quota in quotas.items():
        selected.extend(by_tier.get(tier, [])[:quota])

    # Sort final selection by (tier_priority, -score, original_idx) for
    # deterministic output order.
    selected.sort(key=lambda x: (_TIER_PRIORITY.get(x[2], 9), -x[1], x[0]))

    selected_rows = [item[3] for item in selected]
    selected_counts: dict[str, int] = {}
    for _, _, tier, _ in selected:
        selected_counts[tier] = selected_counts.get(tier, 0) + 1

    notes: list[str] = []
    if sum(selected_counts.values()) < max_rows:
        notes.append(
            f"could not fill max_rows={max_rows}; "
            f"selected {sum(selected_counts.values())}"
        )

    return EvidenceSelection(
        selected_rows=selected_rows,
        full_counts=full_counts,
        selected_counts=selected_counts,
        dropped_count=len(evidence_rows) - len(selected_rows),
        selection_strategy="tier_balanced_v1",
        notes=notes,
    )
