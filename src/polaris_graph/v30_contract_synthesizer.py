"""I-arch-001b — synthesize a v30.1 per_query_report_contract from a v6 template.

Input: v6 template JSON (config/v6_templates/<template_id>.json), query_slug.
Output: {query_slug: <v30.1 contract dict>} ready to merge into a scope
template's `per_query_report_contract` key, where M-55 frame_compiler and
load_report_contract_for_slug both consume it.

Per Codex APPROVE iter 5: every entity carries a concrete http(s) url_pattern
from T1 + a stable anchor; this satisfies M-56's `_fetch_url_pattern()` which
treats the value as a literal URL, not a regex.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Per-template defaults for the type discriminator + identifier field names.
# Codex iter-2: rolled clinical→drug/condition into a generic "frame" entity-
# type so the v30 compiler doesn't try to dispatch on type-specific paths
# that don't exist for synthesized contracts.
_TYPE_FOR_TEMPLATE: dict[str, str] = {
    "clinical": "drug",
    "policy": "policy",
    "tech": "policy",
    "due_diligence": "policy",
    "ai_sovereignty": "policy",
    "canada_us": "policy",
    "workforce": "policy",
    "custom": "policy",
}

_REQUIRED_FIELDS_FOR_TEMPLATE: dict[str, list[str]] = {
    "clinical": ["rxcui", "drugbank_id", "icd_10"],
    "policy": ["jurisdiction", "policy_id", "year"],
    "tech": ["jurisdiction", "technology_id", "year"],
    "due_diligence": ["entity_id", "jurisdiction", "year"],
    "ai_sovereignty": ["bill_id", "jurisdiction", "year"],
    "canada_us": ["jurisdiction", "treaty_id", "year"],
    "workforce": ["jurisdiction", "indicator_id", "year"],
    "custom": ["jurisdiction", "topic_id", "year"],
}

# Last-resort URL when a template has empty T1. Per Codex iter-5 P2 accepted-
# remaining: this is acceptable for v1 (all 8 current templates have T1);
# future templates should fail-loud, deferred to follow-up.
_EMPTY_T1_FALLBACK = "https://www.canada.ca/en/research.html"


def _anchor_for(template_id: str, frame_id: str, query_slug: str) -> str:
    """Stable, unique anchor: <template>:<frame>:<slug_prefix>:<sha256_8>.

    Used as a secondary stable id (not the retrieval locator — url_pattern is).
    Collision-safe for any realistic curator workload (2^32 combinations).
    """
    h = hashlib.sha256(
        f"{template_id}|{frame_id}|{query_slug}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{template_id}:{frame_id}:{query_slug[:40]}:{h}"


def _concrete_url_for_entity(frame_idx: int, source_tiers: dict[str, Any]) -> str:
    """Concrete http(s) URL for this entity, rotated through T1 by frame index.

    M-56's `_fetch_url_pattern()` treats this value as a literal URL, NOT a
    regex (per Codex iter-4 P1 verification at frame_fetcher.py:780,1046).
    Returning a regex would fail to fetch.

    Rotation: entity[i] uses T1[i % len(T1)]. Different frames retrieve
    different roots; strict_verify later filters per-frame relevance.
    """
    t1 = source_tiers.get("T1") or []
    if t1:
        return t1[frame_idx % len(t1)]
    return _EMPTY_T1_FALLBACK


def build_v30_contract(
    v6_template: dict[str, Any],
    query_slug: str,
    question: str | None = None,
) -> dict[str, Any]:
    """Synthesize a v30.1 per_query_report_contract.{query_slug} dict from a v6 template.

    Args:
        v6_template: loaded v6 template JSON (config/v6_templates/<id>.json)
        query_slug: pipeline-A URL-safe slug (e.g. "clinical_glp1_t2dm")
        question: reserved for future question-aware seeding; iter-1 implementation
                  uses frame_id as entity_id basis.

    Returns:
        {query_slug: <contract>} where <contract> has schema_version="v30.1",
        required_entities, rendering_slots (dict-keyed by slot_id), and
        section_order. Round-trips clean via load_report_contract_for_slug.
    """
    del question  # reserved; suppress unused-arg warning
    template_id = v6_template.get("template_id", "")
    frame_manifest = v6_template.get("frame_manifest") or []
    source_tiers = v6_template.get("source_tiers") or {}

    entity_type = _TYPE_FOR_TEMPLATE.get(template_id, "policy")
    required_fields = _REQUIRED_FIELDS_FOR_TEMPLATE.get(
        template_id, ["jurisdiction", "year"]
    )

    required_entities: list[dict[str, Any]] = []
    rendering_slots: dict[str, dict[str, Any]] = {}
    sections_seen: list[str] = []  # ordered, deduped

    for idx, frame in enumerate(frame_manifest):
        frame_id = frame.get("frame_id", f"frame_{idx}")
        frame_name = frame.get("frame_name", frame_id.replace("_", " ").title())
        slot_id = f"{frame_id}_slot"
        section = _section_for_frame(template_id, frame_id, idx)
        if section not in sections_seen:
            sections_seen.append(section)

        rendering_slots[slot_id] = {
            "section": section,
            "subsection_title": frame_name,
            "ordering": idx + 1,
            "required": True,
        }
        required_entities.append({
            "id": f"{frame_id}_entity",
            "type": entity_type,
            "required_fields": list(required_fields),
            "min_fields_for_completion": 1,
            "rendering_slot": slot_id,
            "url_pattern": _concrete_url_for_entity(idx, source_tiers),
            "anchor": _anchor_for(template_id, frame_id, query_slug),
        })

    contract = {
        "schema_version": "v30.1",
        "required_entities": required_entities,
        "rendering_slots": rendering_slots,
        "section_order": sections_seen,
    }
    return {query_slug: contract}


def _section_for_frame(template_id: str, frame_id: str, idx: int) -> str:
    """Group frames into 2-4 sections per template. Mechanical grouping; per-
    template overrides can be added later via report_contract_override blocks.
    """
    # Per Codex iter-5 P2: section grouping is left mechanical-but-stable;
    # template-specific overrides are a follow-up.
    if template_id == "clinical":
        section_map = {
            "efficacy": "Efficacy",
            "safety": "Safety",
            "labelling": "Regulatory",
            "post_market": "Post-market",
            "subgroup": "Subgroups",
        }
    else:
        # Policy templates default: split into Background / Findings / Implications.
        if idx < 2:
            return "Background"
        if idx < 4:
            return "Findings"
        return "Implications"
    return section_map.get(frame_id, "Other")
