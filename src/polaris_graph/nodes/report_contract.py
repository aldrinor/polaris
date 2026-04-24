"""M-54 (2026-04-23): V30 Report Contract schema + loader.

Codex V30 plan pass-1 CONDITIONAL-no-blockers at
`outputs/codex_findings/v30_fix_plan_review_pass1/findings.md`.

## Architecture

This module defines the RUNTIME TYPES for V30's Report Contract —
the mandatory content model that replaces V29's corpus-driven
emergent-frame approach. See
`outputs/audits/v29/true_root_cause_cross_review.md` for the
architectural diagnosis.

## Layer 1 of 5

M-54 is the foundation: YAML schema + Python dataclasses + strict
loader with precise error messages. Layer 2 (M-55 frame compiler)
consumes this. Layer 3-5 consume the compiled contract.

## Contract semantics (from Codex's framing)

A Report Contract has THREE parts per research-question slug:
1. schema_version — contract schema revision tracking
2. required_entities — list of entities that MUST be rendered:
   each has id, type, identifier (DOI/PMID/URL), required_fields,
   min_fields_for_completion, rendering_slot
3. rendering_slots — declarative slot spec:
   each has section, subsection_title, ordering, required

Entity types at M-54 level (extensible at M-55 compiler):
- pivotal_trial    — named clinical trial primary publication
- mechanism_primary — pharmacology primary (clamp/PK/receptor)
- regulatory       — jurisdiction-specific label/guidance/monograph

## Strict loader contract

- Malformed YAML raises ContractSchemaError with precise field path.
- Unknown entity types are NOT rejected at M-54 level (extensibility
  requirement per Codex review #7: compiler must not hard-code entity
  types). M-55 compiler + M-57/58 renderers are responsible for
  per-type handling.
- Missing required fields raise with path.
- Schema-version mismatch is a WARNING (forward compatibility).

## Descoped at M-54

- **Domain-inheritance / contract composition** (V30 plan §M-54 test
  coverage item (d)): intentionally deferred. The current contract
  is a flat per-slug map. The loader remains a pure YAML-shape
  validator. M-55 (frame_compiler.py) does not implement inheritance
  either — see its "## Descoped at M-55" block for the rationale
  (only one slug exists in V30; adding `extends:` before a concrete
  second-slug use-case would be speculative abstraction).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Codex M-63 REJECT Medium 3 fix: live retrieval assigns ids of
# the form `ev_\d+` (see src/polaris_graph/retrieval/live_retriever.py
# around the `ev_{counter:05d}` format string). Contract entity ids
# share the evidence_pool keyspace with live retrieval — colliding
# ids would silently clobber pool rows. M-54 rejects contract ids
# matching this pattern at schema-load time.
_EV_LIVE_ID_RE = re.compile(r"^ev_\d+$")


class ContractSchemaError(ValueError):
    """Raised when a report contract YAML cannot be loaded into valid
    runtime types. Message includes the exact path inside the YAML
    that failed."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"contract schema error at {path}: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class RequiredEntity:
    """One required entity in the report contract.

    At M-54 level the schema is intentionally permissive on entity
    type — per Codex revision #7 (M-62 generalization proof), the
    compiler + renderers must handle arbitrary entity types without
    code changes. This dataclass carries the raw YAML fields; type-
    specific interpretation is left to M-55 compiler + downstream
    consumers.
    """

    id: str
    type: str
    required_fields: tuple[str, ...]
    min_fields_for_completion: int
    rendering_slot: str
    # Optional identifier fields — interpretation depends on entity type
    doi: str | None = None
    pmid: int | str | None = None
    url_pattern: str | None = None
    # Optional metadata fields — passed through for renderer use
    anchor: str | None = None
    journal: str | None = None
    year: int | None = None
    population_scope: str | None = None
    jurisdiction: str | None = None
    label_name: str | None = None


@dataclass(frozen=True)
class RenderingSlot:
    """Declarative slot spec: where the slot appears in the report and
    in what order."""

    id: str
    section: str
    subsection_title: str
    ordering: int
    required: bool = True


@dataclass(frozen=True)
class ReportContract:
    """Resolved report contract for one research-question slug.

    Produced by M-55 frame compiler; consumed by M-57 planner
    + M-58 slot-bound generator + M-59 validator + M-60 gap renderer.
    """

    slug: str
    schema_version: str
    required_entities: tuple[RequiredEntity, ...]
    rendering_slots: tuple[RenderingSlot, ...]
    # Optional explicit section ordering. When None the M-55 compiler
    # falls back to alphabetic-by-label ordering and emits a warning.
    # Fixes Codex M-55 audit Medium (cross-section order was fragile
    # to section-label rename/localization).
    section_order: tuple[str, ...] | None = None

    def entities_by_id(self) -> dict[str, RequiredEntity]:
        return {e.id: e for e in self.required_entities}

    def slots_by_id(self) -> dict[str, RenderingSlot]:
        return {s.id: s for s in self.rendering_slots}

    def entities_by_slot(self) -> dict[str, list[RequiredEntity]]:
        """Slot id -> entities whose rendering_slot points to it.
        Typically 1:1 but the schema allows multi-entity-per-slot
        (e.g. a table row populated from multiple evidence rows)."""
        out: dict[str, list[RequiredEntity]] = {}
        for e in self.required_entities:
            out.setdefault(e.rendering_slot, []).append(e)
        return out


# ─────────────────────────────────────────────────────────────────────
# Schema-version registry.
# Forward-compat: if a template declares a newer schema_version than
# the runtime knows, we WARN (via `schema_version_warnings`), not raise.
# ─────────────────────────────────────────────────────────────────────
_KNOWN_SCHEMA_VERSIONS = frozenset({"v30.1"})


# Required top-level keys in the `required_entities[*]` object.
_REQUIRED_ENTITY_KEYS = {
    "id", "type", "required_fields", "min_fields_for_completion",
    "rendering_slot",
}

# Required top-level keys in the `rendering_slots[*]` object.
_REQUIRED_SLOT_KEYS = {
    "section", "subsection_title", "ordering",
}


def load_report_contract_for_slug(
    template: dict[str, Any] | None,
    slug: str,
) -> ReportContract | None:
    """M-54 public accessor: load the resolved report contract for
    one research-question slug from a loaded scope template.

    Returns None when the template has no contract for this slug
    (backwards-compatible: V28/V29 runs continue to work without
    contract).

    Raises ContractSchemaError with precise path on any schema
    malformation.

    Used by M-55 frame compiler. Not called directly by generator
    stages — those consume the resolved ReportContract object.
    """
    if not isinstance(template, dict):
        return None
    if not isinstance(slug, str) or not slug.strip():
        return None
    by_slug = template.get("per_query_report_contract")
    if by_slug is None:
        return None
    if not isinstance(by_slug, dict):
        raise ContractSchemaError(
            "per_query_report_contract",
            f"expected dict, got {type(by_slug).__name__}",
        )
    raw = by_slug.get(slug)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}",
            f"expected dict, got {type(raw).__name__}",
        )

    # ── schema_version ────────────────────────────────────────────
    schema_version = raw.get("schema_version")
    if schema_version is None:
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}.schema_version",
            "missing required field",
        )
    if not isinstance(schema_version, str):
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}.schema_version",
            f"expected string, got {type(schema_version).__name__}",
        )
    # Forward-compat: warn (don't raise) on unknown schema version
    # via logger in M-55 compiler. At loader level we accept.

    # ── required_entities ─────────────────────────────────────────
    entities_raw = raw.get("required_entities")
    if not isinstance(entities_raw, list):
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}.required_entities",
            f"expected list, got {type(entities_raw).__name__}",
        )
    if not entities_raw:
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}.required_entities",
            "must contain at least one entity",
        )
    entities: list[RequiredEntity] = []
    entity_yaml_index: dict[str, int] = {}  # entity id -> YAML list index
    seen_entity_ids: set[str] = set()
    for i, e in enumerate(entities_raw):
        path = f"per_query_report_contract.{slug}.required_entities[{i}]"
        if not isinstance(e, dict):
            raise ContractSchemaError(
                path, f"expected dict, got {type(e).__name__}"
            )
        missing = _REQUIRED_ENTITY_KEYS - set(e.keys())
        if missing:
            raise ContractSchemaError(
                path, f"missing required keys: {sorted(missing)}"
            )
        # id must be unique within contract
        eid = e["id"]
        if not isinstance(eid, str) or not eid.strip():
            raise ContractSchemaError(
                f"{path}.id",
                "must be non-empty string",
            )
        if eid in seen_entity_ids:
            raise ContractSchemaError(
                f"{path}.id",
                f"duplicate entity id: {eid!r}",
            )
        # Codex M-63 REJECT Medium 3 fix: contract entity_ids MUST
        # NOT collide with the live-retrieval `ev_\d+` namespace.
        # `register_frame_rows_into_evidence_pool` keys by entity_id;
        # a colliding id would clobber a legitimate live retrieval
        # pool row. Keep the contract namespace distinct from live
        # retrieval at schema-load time so the failure fires loudly
        # before any generator token is billed.
        if _EV_LIVE_ID_RE.match(eid):
            raise ContractSchemaError(
                f"{path}.id",
                f"entity id {eid!r} matches the reserved "
                f"live-retrieval namespace `ev_<digits>`; pick a "
                f"distinct id (e.g. `{eid}_primary`, "
                f"`{eid}_anchor`) — contract ids share the "
                f"evidence_pool keyspace with live retrieval and "
                f"must not collide.",
            )
        # ASCII-only: M-58 `render_slot_prose` Title Cases the first
        # codepoint for strict_verify sentence-boundary compatibility
        # (splitter only triggers on ASCII `[A-Z]`). A non-ASCII
        # entity id would propagate into field labels (contract
        # entities drive required_fields) and risk silent sentence-
        # boundary failure. Enforce at schema load rather than at
        # render time so the failure surfaces next to the rest of
        # contract schema validation.
        try:
            eid.encode("ascii")
        except UnicodeEncodeError:
            raise ContractSchemaError(
                f"{path}.id",
                f"entity id {eid!r} contains non-ASCII characters; "
                f"contract entity ids must be ASCII (required for "
                f"M-58 render_slot_prose sentence-splitter "
                f"compatibility).",
            )
        seen_entity_ids.add(eid)
        # type must be non-empty string (compiler enforces type vocab)
        etype = e["type"]
        if not isinstance(etype, str) or not etype.strip():
            raise ContractSchemaError(
                f"{path}.type", "must be non-empty string"
            )
        # required_fields must be non-empty list of strings
        rf = e["required_fields"]
        if not isinstance(rf, list) or not rf:
            raise ContractSchemaError(
                f"{path}.required_fields",
                "must be non-empty list of field names",
            )
        if not all(isinstance(f, str) and f.strip() for f in rf):
            raise ContractSchemaError(
                f"{path}.required_fields",
                "every element must be non-empty string",
            )
        # min_fields_for_completion in 1..len(required_fields)
        min_fields = e["min_fields_for_completion"]
        if not isinstance(min_fields, int):
            raise ContractSchemaError(
                f"{path}.min_fields_for_completion",
                f"expected int, got {type(min_fields).__name__}",
            )
        if min_fields < 1 or min_fields > len(rf):
            raise ContractSchemaError(
                f"{path}.min_fields_for_completion",
                f"must be between 1 and len(required_fields) "
                f"[={len(rf)}]; got {min_fields}",
            )
        # rendering_slot must be non-empty string (checked against
        # slots later)
        rs = e["rendering_slot"]
        if not isinstance(rs, str) or not rs.strip():
            raise ContractSchemaError(
                f"{path}.rendering_slot",
                "must be non-empty string",
            )
        entity_yaml_index[eid] = i
        entities.append(RequiredEntity(
            id=eid,
            type=etype,
            required_fields=tuple(rf),
            min_fields_for_completion=min_fields,
            rendering_slot=rs,
            doi=(e.get("doi") if isinstance(e.get("doi"), str) else None),
            pmid=e.get("pmid"),
            url_pattern=(
                e.get("url_pattern")
                if isinstance(e.get("url_pattern"), str) else None
            ),
            anchor=(
                e.get("anchor") if isinstance(e.get("anchor"), str) else None
            ),
            journal=(
                e.get("journal") if isinstance(e.get("journal"), str) else None
            ),
            year=(e.get("year") if isinstance(e.get("year"), int) else None),
            population_scope=(
                e.get("population_scope")
                if isinstance(e.get("population_scope"), str) else None
            ),
            jurisdiction=(
                e.get("jurisdiction")
                if isinstance(e.get("jurisdiction"), str) else None
            ),
            label_name=(
                e.get("label_name")
                if isinstance(e.get("label_name"), str) else None
            ),
        ))

    # ── rendering_slots ───────────────────────────────────────────
    slots_raw = raw.get("rendering_slots")
    if not isinstance(slots_raw, dict):
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}.rendering_slots",
            f"expected dict, got {type(slots_raw).__name__}",
        )
    if not slots_raw:
        raise ContractSchemaError(
            f"per_query_report_contract.{slug}.rendering_slots",
            "must contain at least one slot",
        )
    slots: list[RenderingSlot] = []
    for slot_id, spec in slots_raw.items():
        path = f"per_query_report_contract.{slug}.rendering_slots.{slot_id}"
        if not isinstance(slot_id, str) or not slot_id.strip():
            raise ContractSchemaError(
                path, "slot id must be non-empty string"
            )
        if not isinstance(spec, dict):
            raise ContractSchemaError(
                path, f"expected dict, got {type(spec).__name__}"
            )
        missing = _REQUIRED_SLOT_KEYS - set(spec.keys())
        if missing:
            raise ContractSchemaError(
                path, f"missing required keys: {sorted(missing)}"
            )
        section = spec["section"]
        if not isinstance(section, str) or not section.strip():
            raise ContractSchemaError(
                f"{path}.section", "must be non-empty string"
            )
        subsection_title = spec["subsection_title"]
        if not isinstance(subsection_title, str):
            raise ContractSchemaError(
                f"{path}.subsection_title",
                f"expected string, got {type(subsection_title).__name__}",
            )
        ordering = spec["ordering"]
        if not isinstance(ordering, int):
            raise ContractSchemaError(
                f"{path}.ordering",
                f"expected int, got {type(ordering).__name__}",
            )
        required = spec.get("required", True)
        if not isinstance(required, bool):
            raise ContractSchemaError(
                f"{path}.required",
                f"expected bool, got {type(required).__name__}",
            )
        slots.append(RenderingSlot(
            id=slot_id,
            section=section,
            subsection_title=subsection_title,
            ordering=ordering,
            required=required,
        ))

    # ── Referential integrity ─────────────────────────────────────
    # Every entity's rendering_slot must resolve to a declared slot.
    # Path uses the YAML list index (entity_yaml_index[e.id]) so callers
    # can map the error to the exact YAML node, not the logical id.
    declared_slot_ids = {s.id for s in slots}
    for e in entities:
        if e.rendering_slot not in declared_slot_ids:
            idx = entity_yaml_index[e.id]
            raise ContractSchemaError(
                f"per_query_report_contract.{slug}.required_entities"
                f"[{idx}].rendering_slot",
                f"entity id={e.id!r} references unknown slot "
                f"{e.rendering_slot!r}; known slots: "
                f"{sorted(declared_slot_ids)}",
            )

    # ── Optional section_order ────────────────────────────────────
    # Addresses Codex M-55 audit Medium: cross-section rendering
    # order was alphabetic-by-label. When `section_order:` is
    # declared, M-55 compiler uses it instead. Every section
    # referenced by a rendering_slot must appear in section_order
    # if the field is present.
    section_order_raw = raw.get("section_order")
    section_order: tuple[str, ...] | None = None
    if section_order_raw is not None:
        if not isinstance(section_order_raw, list):
            raise ContractSchemaError(
                f"per_query_report_contract.{slug}.section_order",
                f"expected list, got {type(section_order_raw).__name__}",
            )
        if not all(
            isinstance(s, str) and s.strip() for s in section_order_raw
        ):
            raise ContractSchemaError(
                f"per_query_report_contract.{slug}.section_order",
                "every element must be non-empty string",
            )
        if len(section_order_raw) != len(set(section_order_raw)):
            raise ContractSchemaError(
                f"per_query_report_contract.{slug}.section_order",
                "duplicates not allowed",
            )
        referenced_sections = {s.section for s in slots}
        missing_from_order = referenced_sections - set(section_order_raw)
        if missing_from_order:
            raise ContractSchemaError(
                f"per_query_report_contract.{slug}.section_order",
                f"missing sections that slots reference: "
                f"{sorted(missing_from_order)}",
            )
        section_order = tuple(section_order_raw)

    return ReportContract(
        slug=slug,
        schema_version=schema_version,
        required_entities=tuple(entities),
        rendering_slots=tuple(slots),
        section_order=section_order,
    )


def get_known_schema_versions() -> frozenset[str]:
    """Expose the set of schema versions this runtime understands.
    Used by M-55 compiler to emit forward-compat warnings."""
    return _KNOWN_SCHEMA_VERSIONS
