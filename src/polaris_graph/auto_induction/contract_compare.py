"""M-D1 contract structural comparison.

Given two `ReportContract` objects (curator + induced), score how well
the induced contract reproduces the curator's structural commitments:

  - section_order set equality (no missing / extra sections)
  - per-section required_entities set equality (by entity_id)
  - per-entity rendering_slot agreement
  - per-entity min_fields_for_completion agreement (numeric)
  - per-entity type agreement (Codex round-1 review fix)
  - per-entity required_fields set agreement (Codex round-1 fix:
    a partial pseudo-contract that omits required_fields was
    scoring 0.8 trivially)

Returns a ContractComparison with field-by-field disagreement detail
plus a single match_score in [0.0, 1.0]. Default scoring weights:
  - section_order match: 15%
  - entities-by-id match: 25%
  - rendering_slot match: 15%
  - min_fields agreement: 15%
  - type agreement (NEW v2): 15%
  - required_fields IoU (NEW v2): 15%

The thresholds in M-D1 acceptance criteria (>= 0.8 precision) refer
to this match_score.

This module is structural-only; it does NOT compare wording of
clarifying notes, justifications, or freeform fields. Wording-level
diff is out-of-scope for M-D1; the inductor's job is to reproduce
structure, not prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContractComparison:
    """Result of comparing two ReportContract objects."""

    curator_slug: str
    induced_slug: str | None
    match_score: float  # in [0.0, 1.0]
    section_order_score: float
    entities_by_id_score: float
    rendering_slot_score: float
    min_fields_score: float
    type_score: float
    required_fields_score: float
    # Specific disagreements for debugging.
    sections_only_in_curator: tuple[str, ...] = field(default_factory=tuple)
    sections_only_in_induced: tuple[str, ...] = field(default_factory=tuple)
    entities_only_in_curator: tuple[str, ...] = field(default_factory=tuple)
    entities_only_in_induced: tuple[str, ...] = field(default_factory=tuple)
    rendering_slot_mismatches: tuple[str, ...] = field(default_factory=tuple)
    min_fields_mismatches: tuple[str, ...] = field(default_factory=tuple)
    type_mismatches: tuple[str, ...] = field(default_factory=tuple)
    required_fields_mismatches: tuple[str, ...] = field(default_factory=tuple)


def _set_iou(a: set[str], b: set[str]) -> float:
    """Intersection-over-union; 1.0 if both empty (vacuous match)."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def compare_contracts(
    curator: Any,
    induced: Any | None,
    *,
    section_weight: float = 0.15,
    entities_weight: float = 0.25,
    rendering_weight: float = 0.15,
    min_fields_weight: float = 0.15,
    type_weight: float = 0.15,
    required_fields_weight: float = 0.15,
) -> ContractComparison:
    """Compare a curator-reviewed contract against an induced one.

    `curator` and `induced` must be `src.polaris_graph.nodes.report_contract.ReportContract`
    objects (or anything with the same shape: `slug`, `section_order`
    list, and `required_entities` list of objects with `id`, `type`,
    `rendering_slot`, `min_fields_for_completion`, `required_fields`).

    If `induced` is None (the inductor abstained or failed), returns
    a comparison with match_score=0.0 and all fields zeroed — caller
    can detect this via `induced_slug is None`.
    """
    weights_sum = (
        section_weight + entities_weight
        + rendering_weight + min_fields_weight
        + type_weight + required_fields_weight
    )
    if abs(weights_sum - 1.0) > 1e-6:
        raise ValueError(
            f"contract-compare weights must sum to 1.0; got {weights_sum}"
        )

    curator_slug = getattr(curator, "slug", "?")
    if induced is None:
        return ContractComparison(
            curator_slug=curator_slug,
            induced_slug=None,
            match_score=0.0,
            section_order_score=0.0,
            entities_by_id_score=0.0,
            rendering_slot_score=0.0,
            min_fields_score=0.0,
            type_score=0.0,
            required_fields_score=0.0,
        )

    induced_slug = getattr(induced, "slug", "?")
    cur_sections = set(getattr(curator, "section_order", ()) or ())
    ind_sections = set(getattr(induced, "section_order", ()) or ())
    section_score = _set_iou(cur_sections, ind_sections)

    cur_entities = list(getattr(curator, "required_entities", ()) or ())
    ind_entities = list(getattr(induced, "required_entities", ()) or ())
    cur_eids = {getattr(e, "id", str(e)) for e in cur_entities}
    ind_eids = {getattr(e, "id", str(e)) for e in ind_entities}
    entities_score = _set_iou(cur_eids, ind_eids)

    # Rendering-slot, type, min_fields, required_fields agreement: only
    # over the intersection of entity ids.
    common_eids = cur_eids & ind_eids
    cur_by_id = {getattr(e, "id", str(e)): e for e in cur_entities}
    ind_by_id = {getattr(e, "id", str(e)): e for e in ind_entities}

    rendering_mismatches: list[str] = []
    rendering_matches = 0
    for eid in common_eids:
        cur_slot = getattr(cur_by_id[eid], "rendering_slot", None)
        ind_slot = getattr(ind_by_id[eid], "rendering_slot", None)
        if cur_slot == ind_slot:
            rendering_matches += 1
        else:
            rendering_mismatches.append(
                f"{eid}: curator={cur_slot!r} induced={ind_slot!r}"
            )
    rendering_score = (
        rendering_matches / len(common_eids) if common_eids else 1.0
    )

    min_fields_mismatches: list[str] = []
    min_fields_matches = 0
    for eid in common_eids:
        cur_min = getattr(cur_by_id[eid], "min_fields_for_completion", None)
        ind_min = getattr(ind_by_id[eid], "min_fields_for_completion", None)
        if cur_min == ind_min:
            min_fields_matches += 1
        else:
            min_fields_mismatches.append(
                f"{eid}: curator={cur_min!r} induced={ind_min!r}"
            )
    min_fields_score = (
        min_fields_matches / len(common_eids) if common_eids else 1.0
    )

    # Codex round-1 review fix: include type + required_fields in the
    # match score. Without these, an inducer that produces the right
    # entity ids + slots but wrong types or missing required_fields
    # was hitting match_score=0.8 trivially.
    type_mismatches: list[str] = []
    type_matches = 0
    for eid in common_eids:
        cur_type = getattr(cur_by_id[eid], "type", None)
        ind_type = getattr(ind_by_id[eid], "type", None)
        if cur_type == ind_type:
            type_matches += 1
        else:
            type_mismatches.append(
                f"{eid}: curator={cur_type!r} induced={ind_type!r}"
            )
    type_score = type_matches / len(common_eids) if common_eids else 1.0

    required_fields_mismatches: list[str] = []
    rf_iou_sum = 0.0
    for eid in common_eids:
        cur_fields = set(getattr(cur_by_id[eid], "required_fields", ()) or ())
        ind_fields = set(getattr(ind_by_id[eid], "required_fields", ()) or ())
        rf_iou = _set_iou(cur_fields, ind_fields)
        rf_iou_sum += rf_iou
        if rf_iou < 1.0:
            required_fields_mismatches.append(
                f"{eid}: curator={sorted(cur_fields)!r} "
                f"induced={sorted(ind_fields)!r} (iou={rf_iou:.2f})"
            )
    required_fields_score = (
        rf_iou_sum / len(common_eids) if common_eids else 1.0
    )

    match_score = (
        section_weight * section_score
        + entities_weight * entities_score
        + rendering_weight * rendering_score
        + min_fields_weight * min_fields_score
        + type_weight * type_score
        + required_fields_weight * required_fields_score
    )

    return ContractComparison(
        curator_slug=curator_slug,
        induced_slug=induced_slug,
        match_score=match_score,
        section_order_score=section_score,
        entities_by_id_score=entities_score,
        rendering_slot_score=rendering_score,
        min_fields_score=min_fields_score,
        type_score=type_score,
        required_fields_score=required_fields_score,
        sections_only_in_curator=tuple(sorted(cur_sections - ind_sections)),
        sections_only_in_induced=tuple(sorted(ind_sections - cur_sections)),
        entities_only_in_curator=tuple(sorted(cur_eids - ind_eids)),
        entities_only_in_induced=tuple(sorted(ind_eids - cur_eids)),
        rendering_slot_mismatches=tuple(rendering_mismatches),
        min_fields_mismatches=tuple(min_fields_mismatches),
        type_mismatches=tuple(type_mismatches),
        required_fields_mismatches=tuple(required_fields_mismatches),
    )
