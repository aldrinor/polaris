"""I-cred-006 (Phase 6, L5) — origin-cluster weight-mass aggregator (pure module).

Aggregate, per claim cluster, a **weight-mass** = Σ over INDEPENDENT origin clusters of
``cluster_mass``, where ``cluster_mass = authority_score(canonical_origin)`` (plan §148 — credibility
is disclosed separately, NOT a mass factor) and every derivative copy contributes ZERO. This is the executable form of plan
§148: 50 copies of one press release count ONCE, at the origin's authority — the vax-defense.

POSTURE (binding):
  * ADVISORY ONLY. Weight-mass is a DISCLOSED side-output. The 4-role D8 release policy
    (``roles/release_policy.py``) stays the single binding release gate; ``strict_verify``'s six
    checks stay the only binding faithfulness gate. This module touches neither.
  * DEFAULT-OFF byte-identical: ``PG_SWEEP_WEIGHT_MASS`` (no production caller; pure library).
  * Copies contribute ZERO to the mass; adding a copy of ANY authority cannot inflate the mass
    (origin-cluster invariant — copies are excluded, the canonical origin alone carries the mass).
  * PURE: no row mutation, no network, no faithfulness-file import; LAW VI env-overridable; snake_case.

This issue ships ONLY the pure aggregator. Removing the journal count-floor, wiring weight-mass into
``corpus_adequacy_gate``, and the per-claim clinical source-type veto are the gate-touching follow-up
(I-cred-006b) with their own flag — they modify faithfulness-adjacent gates.

INPUT join (all on the stable per-evidence ``evidence_id``):
  * ``rows``: evidence rows, each carrying ``evidence_id``, ``origin_cluster_id`` + ``is_canonical_origin``
    (Phase-4 assignment merged onto the row by the caller), and ``authority_score``. A row with no
    ``origin_cluster_id`` is treated as its OWN independent origin (it was never flagged a copy).
  * ``claims``: Phase-5 atomic claims (``claim_cluster_id`` + ``evidence_id``).
  * ``judgments``: Phase-2 credibility judgments (``evidence_id`` -> ``credibility_weight``); a canonical
    with NO judgment uses ``credibility_weight = 1.0`` (mass = pure authority).
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

_FLAG = "PG_SWEEP_WEIGHT_MASS"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def weight_mass_enabled() -> bool:
    """True unless ``PG_SWEEP_WEIGHT_MASS`` is unset/falsey (default OFF => byte-identical)."""
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _num(value: Any) -> float:
    """Coerce to a finite float; non-numeric / NaN / inf -> 0.0 (fail-soft on a disclosure signal)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if (math.isnan(x) or math.isinf(x)) else x


def _clamp01(value: Any) -> float:
    x = _num(value)
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass
class OriginContribution:
    """One independent origin's contribution to a claim cluster's weight-mass."""

    origin_cluster_id: str
    canonical_evidence_id: str
    authority_score: float       # of the canonical origin
    credibility_weight: float    # Phase-2 weight of the canonical origin (1.0 if none)
    cluster_mass: float          # = authority_score(canonical) ONLY (plan §148); credibility disclosed, not a factor
    copy_count: int              # derivative copies attributed to this origin (disclosure)


@dataclass
class ClaimWeightMass:
    """A claim cluster's aggregated, copy-uninflatable weight-mass + its origin breakdown."""

    claim_cluster_id: str
    weight_mass: float
    independent_origin_count: int
    contributions: list


def _origin_id_for_row(row: dict[str, Any]) -> str:
    ocid = str(row.get("origin_cluster_id", "") or "").strip()
    # An uncollapsed row (never flagged a copy) is its OWN independent origin.
    return ocid if ocid else f"origin::{row.get('evidence_id', '')}"


def aggregate_weight_mass(
    claims: list,
    rows: list[dict[str, Any]],
    judgments: list,
) -> list[ClaimWeightMass]:
    """Aggregate per-claim-cluster origin-cluster weight-mass — ADVISORY, pure, no row mutation.

    For each claim cluster, group its supporting rows by ``origin_cluster_id``; for each origin use the
    CANONICAL origin's ``authority_score`` as the cluster mass (credibility is disclosed, not a factor —
    plan §148); copies contribute
    ZERO (only ``copy_count`` for disclosure). The claim weight-mass is the sum once per origin cluster.
    """
    rows = list(rows or [])
    row_by_eid = {str(r.get("evidence_id", "")): r for r in rows}
    cred_by_eid: dict[str, float] = {}
    for judgment in (judgments or []):
        eid = str(getattr(judgment, "evidence_id", "") or "")
        if eid:
            cred_by_eid[eid] = _clamp01(getattr(judgment, "credibility_weight", None))

    # The canonical row per origin cluster (global across all rows), so a claim supported only by
    # COPIES still attributes the mass to the origin's authority, never a copy's. VALIDATED: each
    # COLLAPSED origin must carry EXACTLY ONE is_canonical_origin row (Phase-4 metadata) — FAIL-LOUD
    # on missing/duplicate, never fail-soft to a member (a copy must never become the mass carrier;
    # Codex #1155 P1-1). An uncollapsed row is its own singleton canonical.
    canonical_by_origin: dict[str, dict[str, Any]] = {}
    canonical_counts: dict[str, int] = {}
    collapsed_origins: set[str] = set()
    for row in rows:
        ocid = _origin_id_for_row(row)
        if str(row.get("origin_cluster_id", "") or "").strip():
            collapsed_origins.add(ocid)
            if row.get("is_canonical_origin"):
                canonical_counts[ocid] = canonical_counts.get(ocid, 0) + 1
                canonical_by_origin[ocid] = row
        else:
            canonical_by_origin.setdefault(ocid, row)  # uncollapsed singleton = its own canonical
    for ocid in sorted(collapsed_origins):
        count = canonical_counts.get(ocid, 0)
        if count != 1:
            raise ValueError(
                f"weight_mass: origin cluster {ocid!r} must carry EXACTLY ONE is_canonical_origin "
                f"row (Phase-4 canonical metadata); found {count}. No fail-soft fallback — a copy "
                f"must never become the mass carrier (Codex #1155 P1-1)."
            )

    claim_eids: dict[str, list] = {}
    for claim in (claims or []):
        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
        eid = str(getattr(claim, "evidence_id", "") or "")
        if ccid:
            claim_eids.setdefault(ccid, []).append(eid)

    out: list[ClaimWeightMass] = []
    for ccid in sorted(claim_eids):
        members_by_origin: dict[str, set] = {}
        for eid in claim_eids[ccid]:
            row = row_by_eid.get(eid)
            if row is None:
                continue
            members_by_origin.setdefault(_origin_id_for_row(row), set()).add(eid)

        contributions: list[OriginContribution] = []
        for ocid in sorted(members_by_origin):
            members = members_by_origin[ocid]
            canonical = canonical_by_origin[ocid]  # guaranteed present by the validation above
            canon_eid = str(canonical.get("evidence_id", ""))
            authority = _clamp01(canonical.get("authority_score"))
            credibility = cred_by_eid.get(canon_eid, 1.0)  # no judgment => neutral 1.0
            contributions.append(OriginContribution(
                origin_cluster_id=ocid,
                canonical_evidence_id=canon_eid,
                authority_score=authority,
                credibility_weight=credibility,
                # cluster_mass = authority_score(canonical origin) ONLY (plan §148). credibility_weight
                # is carried as a DISCLOSED field but is NOT a mass factor: folding it in breaks the
                # no-inflation invariant (a high-authority / low-credibility origin, 0.8x0.1=0.08, could
                # be OVERTAKEN by adding a lower-authority copy with no judgment, 0.3x1.0=0.3 — adding a
                # copy raises the mass). Mass is pure independence-authority; credibility is disclosed
                # separately and combined downstream (Phase 7/8). Codex #1155 iter-2 P1.
                cluster_mass=authority,
                # Supporting members that are NOT the canonical = the derivative copies of this
                # origin backing this claim. Counting "members minus canonical" (not len-1) is
                # correct even when the claim is supported ONLY by copies and the canonical row
                # backs a different claim (Codex #1155 P2-2 — no 0-copy undercount).
                copy_count=sum(1 for m in members if m != canon_eid),
            ))

        out.append(ClaimWeightMass(
            claim_cluster_id=ccid,
            weight_mass=sum(c.cluster_mass for c in contributions),
            independent_origin_count=len(contributions),
            contributions=contributions,
        ))
    return out
