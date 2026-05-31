"""Signal E — recency / temporal-fit decay.

Phase 0a (GH #983). Data-driven (LAW VI).

Phase-0a has no planner recency need wired in, so with the default horizon of 0
this returns a NEUTRAL score (old does not mean worthless). When a positive
horizon IS supplied, an exponential half-life decay is applied with a floor.
All knobs live in config/authority/recency_profile.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SignalEResult:
    score: float
    reasons: list[str]


def compute_signal_e(
    publication_year: int | None,
    current_year: int,
    profile: dict,
    horizon_years: int | None = None,
) -> SignalEResult:
    """Compute the recency sub-score.

    Returns the neutral score when there is no recency need (horizon 0) or no
    known year. Otherwise applies half-life decay clamped to a floor.
    """
    neutral = float(profile["neutral_score"])
    horizon = profile["default_horizon_years"] if horizon_years is None else horizon_years

    if not horizon or horizon <= 0:
        return SignalEResult(score=neutral, reasons=["recency neutral (no temporal need)"])
    if not isinstance(publication_year, int) or publication_year <= 0:
        return SignalEResult(score=neutral, reasons=["recency neutral (no known year)"])

    age = max(0, current_year - publication_year)
    halflife = float(profile["decay_halflife_years"])
    floor = float(profile["floor_score"])
    decay = 0.5 ** (age / halflife) if halflife > 0 else 1.0
    score = floor + (1.0 - floor) * decay
    score = floor if score < floor else (1.0 if score > 1.0 else score)
    return SignalEResult(
        score=score,
        reasons=[f"recency decay: age={age}y, horizon={horizon}y, score={score:.2f}"],
    )
