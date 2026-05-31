"""Signal A — scholarly-graph authority from OpenAlex /works + /sources fields.

Phase 0a (GH #983). Pure function, data-driven (LAW VI). ZERO venue names.

Computes a scholarly authority sub-score in [0, 1] from:
  - cited_by_count (work)
  - venue summary_stats.h_index + summary_stats.2yr_mean_citedness (source)
  - is_core (source)
  - is_in_doaj vs missing-DOAJ + high apc_prices (predatory-OA smell)

All weights / norms / anchors come from config/authority/scholarly_weights.yaml.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.polaris_graph.authority.source_class import (
    AuthorityConfidence,
    AuthoritySignals,
)


@dataclass
class SignalAResult:
    score: float
    confidence: AuthorityConfidence
    reasons: list[str]
    fired: bool   # whether any scholarly field was present at all
    predatory: bool = False  # predatory-OA smell fired (not in DOAJ AND high APC)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _squash(value: float, low: float, high: float) -> float:
    """Min-max squash of `value` between anchors low->0 and high->1, clamped."""
    if high <= low:
        return _clamp01(value)
    return _clamp01((value - low) / (high - low))


def _max_apc_usd(apc_prices: list | None) -> float:
    """Largest APC price in USD from an OpenAlex apc_prices list, else 0."""
    if not apc_prices:
        return 0.0
    best = 0.0
    for entry in apc_prices:
        if not isinstance(entry, dict):
            continue
        if entry.get("currency") and entry.get("currency") != "USD":
            # Only compare USD entries; OpenAlex usually includes a USD row.
            continue
        price = entry.get("price")
        if isinstance(price, (int, float)) and price > best:
            best = float(price)
    return best


def compute_signal_a(signals: AuthoritySignals, weights: dict) -> SignalAResult:
    """Compute scholarly-graph authority sub-score."""
    reasons: list[str] = []
    anchors = weights["percentile_anchors"]

    cited = signals.cited_by_count
    stats = signals.venue_summary_stats or {}
    h_index = stats.get("h_index") if isinstance(stats, dict) else None
    two_yr = stats.get("2yr_mean_citedness") if isinstance(stats, dict) else None

    have_cite = isinstance(cited, int)
    have_stats = isinstance(h_index, (int, float)) or isinstance(two_yr, (int, float))
    fired = have_cite or have_stats

    # Citation term.
    cite_term = 0.0
    if have_cite:
        cite_log = math.log1p(max(0, cited))
        cite_term = _squash(cite_log, anchors["cite_log_low"], anchors["cite_log_high"])
        reasons.append(f"cited_by_count={cited} (scholarly graph)")

    # h-index term.
    h_term = 0.0
    if isinstance(h_index, (int, float)):
        h_term = _clamp01(float(h_index) / weights["H_NORM"])
        reasons.append(f"venue h_index={h_index}")

    # Recent-impact term.
    recent_term = 0.0
    if isinstance(two_yr, (int, float)):
        recent_term = _clamp01(float(two_yr) / weights["C_NORM"])
        reasons.append(f"venue 2yr_mean_citedness={two_yr}")

    score = (
        weights["w_cite"] * cite_term
        + weights["w_hindex"] * h_term
        + weights["w_recent"] * recent_term
    )

    # is_core bonus.
    if signals.is_core is True:
        score += weights["is_core_bonus"]
        reasons.append("venue is_core=True (curated journal)")

    # Predatory-OA smell: NOT in DOAJ AND high APC.
    max_apc = _max_apc_usd(signals.apc_prices)
    predatory = signals.is_in_doaj is False and max_apc > weights["APC_FLOOR"]
    if predatory:
        score -= weights["predatory_penalty"]
        reasons.append(
            f"predatory-OA smell: not in DOAJ and APC={max_apc:.0f} "
            f"> floor {weights['APC_FLOOR']:.0f}"
        )

    score = _clamp01(score)

    # Confidence: both citation AND venue stats present -> HIGH; one -> MEDIUM;
    # neither -> LOW.
    if have_cite and have_stats:
        confidence = AuthorityConfidence.HIGH
    elif fired:
        confidence = AuthorityConfidence.MEDIUM
    else:
        confidence = AuthorityConfidence.LOW
        reasons.append("no scholarly-graph fields present (thin OpenAlex coverage)")

    return SignalAResult(
        score=score, confidence=confidence, reasons=reasons, fired=fired,
        predatory=predatory,
    )
