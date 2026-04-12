"""
Mesh snowball — bounded feedback formulas (FIX D3, FIX S4).

Four multiplicative mechanisms from the design doc §8. All are bounded:
no runaway feedback, no popularity cascades.

v1 design (CP-A lock):

  Formulas are implemented and proven by tests, but TRIGGERS are
  deferred until the units that actually invoke them exist:
    - M1 (usage reinforcement): triggered on retrieval (Unit 5)
    - M2 (corroboration boost): triggered on answer citation (Unit 7)
    - M4 (upload gravity): triggered during lethal re-rank (Unit 5)
    - M3 (contradiction penalty): triggered during lethal re-rank (Unit 5)

  Unit 4 deliverable: pure functions with bounded output, exhaustively
  tested. Unit 5+ wires them into the live retrieval/compose pipeline.

Bounds from design doc:
  M1: max bonus at times_used=100, age<30d ≈ 1.46; decays to 1.0 at age>2y
  M2: corroboration_factor at count=100 → 1 + 0.3 * sqrt(100) = 4.0
      (real claims rarely have >10 corroborations, so practical max ~1.95)
  M3: penalty is fixed at ×0.7 when any contradiction exists
  M4: upload gravity is fixed at ×1.3 for upload sources
"""

from __future__ import annotations

import math


def usage_bonus(times_used: int, age_days: float) -> float:
    """
    M1: Age-decayed usage reinforcement.

    Returns a multiplicative bonus ≥ 1.0. Claims that get retrieved and
    used in answers receive a bonus that decays over time — a claim
    used 100 times yesterday has a strong bonus, but a claim used 100
    times two years ago has almost none.

    Formula: 1 + log(1 + times_used) * 0.1 * exp(-age_days / 365)

    Bounds:
      times_used=0  → 1.0 (no bonus)
      times_used=100, age=0  → 1 + log(101) * 0.1 ≈ 1.46
      times_used=100, age=730 (2yr) → 1 + log(101) * 0.1 * exp(-2) ≈ 1.06
      Always ≥ 1.0 (never penalizes)
    """
    if times_used <= 0 or age_days < 0:
        return 1.0
    return 1.0 + math.log(1.0 + times_used) * 0.1 * math.exp(-age_days / 365.0)


def corroboration_factor(count: int) -> float:
    """
    M2: Corroboration reinforcement via sqrt.

    Returns a multiplicative factor ≥ 1.0. Claims with more
    corroborating edges get a higher weight, but the sqrt prevents
    runaway amplification.

    Formula: 1 + 0.3 * sqrt(count)

    Bounds:
      count=0  → 1.0
      count=1  → 1.3
      count=4  → 1.6
      count=10 → ~1.95
      count=100 → 4.0 (theoretical max, never reached in practice)
      Always ≥ 1.0
    """
    if count <= 0:
        return 1.0
    return 1.0 + 0.3 * math.sqrt(count)


def contradiction_penalty(has_contradiction: bool) -> float:
    """
    M3: Contradiction presence penalizes a claim.

    Returns a multiplicative factor ≤ 1.0. When any contradiction edge
    exists, both contradicting claims are still surfaced (the retrieval
    always includes both), but each is penalized by ×0.7 in the
    re-ranking score.

    Bounds: either 1.0 (no contradiction) or 0.7 (contradiction exists).
    """
    return 0.7 if has_contradiction else 1.0


def upload_gravity_boost(is_upload: bool) -> float:
    """
    M4: Upload sources get a retrieval boost.

    Returns a multiplicative factor for lethal re-ranking. Upload
    sources (kind='upload', sig_authority=0.95) are user-anchored
    content — the user explicitly provided them, so they deserve a
    boost in ranking.

    Bounds: either 1.0 (web/api source) or 1.3 (upload source).
    """
    return 1.3 if is_upload else 1.0


def lethal_snowball_score(
    *,
    base_score: float,
    times_used: int = 0,
    age_days: float = 0.0,
    corroboration_count: int = 0,
    has_contradiction: bool = False,
    is_upload: bool = False,
) -> float:
    """
    Combine all 4 snowball factors into a single multiplicative score.

    This is the function Unit 5's lethal retrieval will call during
    re-ranking. For v1 it's a pure composition; future versions may
    add additional factors.

    Returns base_score × M1 × M2 × M3 × M4 (all bounded).
    """
    return (
        base_score
        * usage_bonus(times_used, age_days)
        * corroboration_factor(corroboration_count)
        * contradiction_penalty(has_contradiction)
        * upload_gravity_boost(is_upload)
    )
