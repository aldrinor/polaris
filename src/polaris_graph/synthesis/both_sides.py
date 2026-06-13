"""I-cred-007 (Phase 7, L6) — NEUTRAL both-sides disclosure composer (pure module).

For a CONTESTED claim (a claim-cluster pair joined by a Phase-5 ``ContradictionEdge``), compose a
NEUTRAL both-sides disclosure: each side shown as a LEGITIMATE position with its transparent evidence
weight (Phase-6 origin-cluster ``weight_mass``), its independent-origin count, and its cited
``evidence_id``s — in neutral language, ALWAYS visible. The user judges; POLARIS discloses the weight
behind each side honestly rather than labelling one "true" or "fringe" (operator Decision 2, plan §9.3).

POSTURE (binding):
  * ADVISORY / DISCLOSURE ONLY. This is a SEPARATE block (rendered like ``limitations_text``), appended
    AFTER verified prose. It NEVER edits verified sentences, NEVER runs inside ``strict_verify``, NEVER
    touches the 4-role D8 release gate. strict_verify's six checks stay the only binding faithfulness gate.
  * NEUTRAL framing: no "fringe / misinformation / warning / debunked / conspiracy / unreliable" labels.
  * DEFAULT-OFF byte-identical: ``PG_SWEEP_BOTHSIDES_DISCLOSURE`` (no production caller; pure library).
  * Weight is the Phase-6 origin-cluster ``weight_mass`` (authority of independent canonical origins),
    never headcount. Both sides get their honest weight; the LOW-weight side is shown, not dropped.
  * PURE: no input mutation, no network, no faithfulness-file import; LAW VI; snake_case.

This issue ships the pure composer ONLY; wiring the rendered block into the report assembler + the UI
affordance is a separate step (I-cred-007b), keeping this faithfulness-safe and default-OFF.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_FLAG = "PG_SWEEP_BOTHSIDES_DISCLOSURE"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def bothsides_disclosure_enabled() -> bool:
    """True unless ``PG_SWEEP_BOTHSIDES_DISCLOSURE`` is unset/falsey (default OFF => byte-identical)."""
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _num(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if (x != x or x in (float("inf"), float("-inf"))) else x


@dataclass
class SidePosition:
    """One side of a contested claim: WHAT it asserts + its transparent evidence weight."""

    claim_cluster_id: str
    subject: str
    predicate: str
    statement: str                # neutral statement of WHAT this side asserts (the claim text)
    weight_mass: float            # Phase-6 origin-cluster weight-mass behind this side
    independent_origin_count: int
    evidence_ids: tuple           # the cited evidence for this side (one-click span access)


@dataclass
class BothSidesBlock:
    """A contested topic + its 2+ positions, ordered by evidence weight (NOT by "correctness")."""

    subject: str
    sides: list
    source: str                   # which detector raised the contradiction (numeric/qualitative/semantic)
    severity: str


def compose_both_sides(
    contradiction_edges: list,
    weight_mass: list,
    claims: list,
    *,
    verified_count_by_cluster: dict | None = None,
) -> list[BothSidesBlock]:
    """Compose one BothSidesBlock per contradiction edge — pure, no input mutation.

    Maps each ``ContradictionEdge``'s two ``claim_cluster_ids`` to their Phase-6 ``ClaimWeightMass``
    (weight + independent-origin count) and Phase-5 ``AtomicClaim`` info (subject/predicate/evidence_ids).
    Sides are ordered by ``weight_mass`` DESC — disclosing which side has MORE evidence weight, never
    asserting which is true; the low-weight side is kept, never dropped. A missing weight defaults to
    0.0 / 0 (fail-soft disclosure, never a crash, never a fabricated weight).

    I-arch-002 [10] / design §5 FIX-4 (Reading A): when ``verified_count_by_cluster``
    (``claim_cluster_id -> basket verified_support_origin_count``, from the P3.2 baskets) is
    threaded in, each side's ``independent_origin_count`` is OVERWRITTEN with ITS OWN basket's
    ISOLATED-verified count (looked up by the side's ``claim_cluster_id``) instead of the
    clustered, not-verified ``ClaimWeightMass.independent_origin_count``. This OVERWRITES the
    value feeding the existing field — no parallel field is added. When the map is absent
    (default OFF) or a side's cluster is not in it, the legacy ``cwm.independent_origin_count``
    is used BYTE-IDENTICALLY.
    """
    verified_by_cluster = {
        str(k): int(v or 0) for k, v in (verified_count_by_cluster or {}).items()
    }
    weight_by_cluster: dict[str, Any] = {}
    for cwm in (weight_mass or []):
        ccid = str(getattr(cwm, "claim_cluster_id", "") or "")
        if ccid:
            weight_by_cluster[ccid] = cwm

    info: dict[str, dict[str, Any]] = {}
    for claim in (claims or []):
        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
        if not ccid:
            continue
        rec = info.setdefault(ccid, {"subject": "", "predicate": "", "statement": "", "evidence_ids": set()})
        if not rec["subject"]:
            rec["subject"] = str(getattr(claim, "subject", "") or "")
        if not rec["predicate"]:
            rec["predicate"] = str(getattr(claim, "predicate", "") or "")
        if not rec["statement"]:
            rec["statement"] = str(getattr(claim, "text", "") or "").strip()
        eid = str(getattr(claim, "evidence_id", "") or "")
        if eid:
            rec["evidence_ids"].add(eid)

    blocks: list[BothSidesBlock] = []
    for edge in (contradiction_edges or []):
        cluster_ids = tuple(getattr(edge, "claim_cluster_ids", ()) or ())
        if len(cluster_ids) < 2:
            continue  # a both-sides block needs two distinct positions
        sides: list[SidePosition] = []
        for raw_ccid in cluster_ids:
            ccid = str(raw_ccid)
            cwm = weight_by_cluster.get(ccid)
            rec = info.get(ccid, {})
            side_subject = str(rec.get("subject", "") or getattr(edge, "subject", "") or "")
            side_predicate = str(rec.get("predicate", "") or getattr(edge, "predicate", "") or "")
            # WHAT this side asserts: the claim text, falling back to subject+predicate. Without it the
            # disclosure cannot tell the user what Position A vs B claims (Codex #1156 P1).
            side_statement = (
                str(rec.get("statement", "") or "").strip()
                or f"{side_subject} {side_predicate}".strip()
            )
            # Legacy clustered, not-verified count (default-OFF byte-identity).
            legacy_origin_count = (
                int(getattr(cwm, "independent_origin_count", 0) or 0) if cwm is not None else 0
            )
            # I-arch-002 [10]: OVERWRITE with this side's OWN basket verified count when threaded
            # (keyed by the side's claim_cluster_id — its own basket, never the other side's,
            # never a sentence-wide count). Absent => legacy clustered count, byte-identical.
            side_origin_count = verified_by_cluster.get(ccid, legacy_origin_count)
            sides.append(SidePosition(
                claim_cluster_id=ccid,
                subject=side_subject,
                predicate=side_predicate,
                statement=side_statement,
                weight_mass=_num(getattr(cwm, "weight_mass", 0.0)) if cwm is not None else 0.0,
                independent_origin_count=side_origin_count,
                evidence_ids=tuple(sorted(rec.get("evidence_ids", set()))),
            ))
        # Order by weight DESC; stable claim_cluster_id tiebreak for determinism. This discloses which
        # side carries more independent-origin evidence weight — it does NOT assert which is correct.
        sides.sort(key=lambda s: (-s.weight_mass, s.claim_cluster_id))
        blocks.append(BothSidesBlock(
            subject=str(getattr(edge, "subject", "") or (sides[0].subject if sides else "")),
            sides=sides,
            source=str(getattr(edge, "source", "") or ""),
            severity=str(getattr(edge, "severity", "") or "review"),
        ))
    return blocks


def render_both_sides(blocks: list) -> str:
    """Neutral markdown disclosure section. Empty string for no blocks (default-OFF byte-identity).

    Uses only neutral framing ("the evidence diverges", "evidence weight", "independent origins",
    "weigh them yourself") — never a judgemental label. Shows EVERY side with its weight; the user judges.
    """
    if not blocks:
        return ""
    lines = [
        "## Where sources diverge",
        "",
        "On the topics below the evidence does not agree. Each position is shown with its evidence "
        "weight (origin-cluster weight-mass) and the number of independent origins behind it, plus its "
        "cited sources. Both positions are shown as they stand in the evidence; weigh them yourself.",
        "",
    ]
    for block in blocks:
        lines.append(f"### On {block.subject}, the evidence diverges")
        for index, side in enumerate(block.sides):
            label = chr(ord("A") + index)
            cited = ", ".join(side.evidence_ids) if side.evidence_ids else "—"
            statement = side.statement or "(position not stated)"
            lines.append(
                f"- **Position {label}** — \"{statement}\" — evidence weight {side.weight_mass:.2f} "
                f"across {side.independent_origin_count} independent origin(s). Cited: {cited}."
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
