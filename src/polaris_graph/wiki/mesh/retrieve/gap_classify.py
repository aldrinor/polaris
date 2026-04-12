"""
Mesh gap classification (FIX S6).

Classifies a retrieval result into one of four categories based on
the quality and quantity of claims found. The classification drives
downstream behavior:

  IN_SCOPE:    sufficient claims, high confidence → compose directly
  NEARBY:      partial coverage → auto-expand search (budget-gated)
  ADJACENT:    entity matches only, no direct semantic matches →
               suggest related workspace questions
  ORTHOGONAL:  nothing found → prompt user for workspace decision

FIX S6: NEARBY auto-expansion has a daily budget per workspace
(`nearby_expansion_budget_daily` column in workspaces table). The
budget counter is checked by `check_nearby_budget()` and incremented
by `increment_nearby_budget()`. The actual auto-expansion search is
deferred to Unit 7+ — for v1, the caller receives the category and
the budget status, then decides what to do.
"""

from __future__ import annotations

import enum
import logging
from datetime import date

from ..store import MeshStore

logger = logging.getLogger(__name__)

IN_SCOPE_MIN_CLAIMS = 5
IN_SCOPE_MIN_SCORE = 0.3


class GapCategory(enum.Enum):
    IN_SCOPE = "IN_SCOPE"
    NEARBY = "NEARBY"
    ADJACENT = "ADJACENT"
    ORTHOGONAL = "ORTHOGONAL"


def classify_gap(
    *,
    seed_count: int,
    entity_count: int,
    total_count: int,
    max_score: float,
) -> GapCategory:
    """
    Classify the retrieval gap based on counts and max score.

    Parameters
    ----------
    seed_count : int
        Claims found by the KNN semantic seed (stage 1).
    entity_count : int
        Additional claims found by entity expansion (stage 2).
    total_count : int
        Total unique claims in the pool after all stages.
    max_score : float
        Highest lethal score in the re-ranked output.
    """
    if total_count >= IN_SCOPE_MIN_CLAIMS and max_score >= IN_SCOPE_MIN_SCORE:
        return GapCategory.IN_SCOPE
    if total_count >= 1:
        return GapCategory.NEARBY
    if entity_count > 0:
        return GapCategory.ADJACENT
    return GapCategory.ORTHOGONAL


def check_nearby_budget(store: MeshStore, workspace_id: str) -> bool:
    """
    FIX S6: check if the workspace has remaining NEARBY expansion budget.

    Returns True if expansions are still allowed today. Resets the
    counter if the last reset date is not today.
    """
    ws = store.get_workspace(workspace_id)
    if ws is None:
        return False

    today_str = date.today().isoformat()
    reset_at = ws.get("nearby_expansion_reset_at")

    if reset_at != today_str:
        store._conn.execute(
            """UPDATE workspaces
               SET nearby_expansions_today = 0,
                   nearby_expansion_reset_at = ?
               WHERE id = ?""",
            (today_str, workspace_id),
        )
        return True

    budget = int(ws.get("nearby_expansion_budget_daily", 50) or 50)
    used = int(ws.get("nearby_expansions_today", 0) or 0)
    return used < budget


def increment_nearby_budget(store: MeshStore, workspace_id: str) -> None:
    """Increment the NEARBY expansion counter for today."""
    store._conn.execute(
        """UPDATE workspaces
           SET nearby_expansions_today = nearby_expansions_today + 1
           WHERE id = ?""",
        (workspace_id,),
    )
