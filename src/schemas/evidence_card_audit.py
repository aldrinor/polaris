#!/usr/bin/env python3
"""Closed schemas and stable receipt types for the evidence-card corpus audit.

This module is DATA, not policy: it names the four verdict values, the closed set of top-level and
support-edge card fields the v2 miner emits, the closed vocabulary of provenance CONTENT CLASSES the
CoT-contamination test assigns, and the stable machine reason codes every deterministic receipt cites.

Nothing here is task-specific. There is no DOI, title, subject, venue or benchmark literal anywhere in
this file, and there must never be one: the audit fires on STRUCTURE, so a clinical, legal, economics or
computer-science corpus is screened by the identical rules (Sol §Generality, Phase 8 metamorphic law).

Sol §2 verdict contract: an audit dimension resolves to exactly one of PASS / FAIL / UNCERTAIN /
NOT_APPLICABLE. The DETERMINISTIC (Tier-0) screen in `card_audit.tier0` never invents a PASS it cannot
prove offline: a dimension it cannot decide without a model resolves to NEEDS_OPUS, which is a ROUTING
status (Tier-1 must decide it), never a composer-facing verdict. NEEDS_OPUS is deliberately NOT in
`VERDICTS`; it can never appear in the clean set.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- Sol §2: the four composer-facing verdict values ---------------------------------------------
PASS = 'PASS'
FAIL = 'FAIL'
UNCERTAIN = 'UNCERTAIN'
NOT_APPLICABLE = 'NOT_APPLICABLE'
VERDICTS = frozenset({PASS, FAIL, UNCERTAIN, NOT_APPLICABLE})

# A Tier-0-only routing status. It is NOT a verdict: a dimension a deterministic screen cannot decide
# offline (semantic support, relevance, atom-level faithfulness) is handed to Opus, never passed.
NEEDS_OPUS = 'NEEDS_OPUS'
# A Tier-0-only routing status for the facet dimension when no contract taxonomy has been pinned yet:
# Sol §Relevance-and-facet — "If the question or exact contract cannot be pinned, the audit stops. It
# must not invent a fallback topic." So an unpinned taxonomy is NEVER a silent PASS.
NEEDS_CONTRACT = 'NEEDS_CONTRACT'

# ---- Sol §CoT: the closed vocabulary of allowed provenance content classes -----------------------
# Every non-empty string field must be classified into EXACTLY ONE of these. Absence of a suspicious
# phrase is never sufficient (Sol §CoT); the test is POSITIVE — a field passes only when its bytes are
# proven to belong to one of these classes.
SOURCE_BYTES = 'SOURCE_BYTES'                    # exact verified source substring, e.g. span_raw
CANONICAL_SOURCE_VIEW = 'CANONICAL_SOURCE_VIEW'  # deterministic normalization of verified bytes, e.g. span
DERIVED_CACHE = 'DERIVED_CACHE'                  # byte-for-byte recomputable from audited fields, e.g. claim
GRAPH_METADATA = 'GRAPH_METADATA'               # exactly matches live Work/Expression/Manifestation
REGISTRY_VALUE = 'REGISTRY_VALUE'               # member of an allowed closed vocabulary
ATOMIC_EVIDENCE_VALUE = 'ATOMIC_EVIDENCE_VALUE'  # concise extracted value supported by its source window
EMPTY = 'EMPTY'
CONTENT_CLASSES = frozenset({
    SOURCE_BYTES, CANONICAL_SOURCE_VIEW, DERIVED_CACHE, GRAPH_METADATA,
    REGISTRY_VALUE, ATOMIC_EVIDENCE_VALUE, EMPTY,
})

# ---- The dimensions the Tier-0 deterministic screen decides --------------------------------------
DIM_STRUCTURE = 'structure_schema'      # closed schema, required fields, types, id present
DIM_BINDING = 'binding'                 # verify_span, resolve_attribution, stored-target, identity, policy
DIM_CACHES = 'caches'                   # claim==derive_claim, has_number, span_numbers, complete_tuple, counts
DIM_NUMERIC = 'numeric_tokens'          # mechanical: no claim number the span does not stand-alone carry
DIM_COT = 'cot_structural'              # positive content-class per non-empty field
DIM_FACET = 'facet_presence'            # facet_tags_span ⊆ taxonomy and (if a tagger is pinned) recompute
DIM_CORROBORATOR = 'corroborator_bindings'  # every nested support edge has a complete independent binding
TIER0_DIMENSIONS = (
    DIM_STRUCTURE, DIM_BINDING, DIM_CACHES, DIM_NUMERIC, DIM_COT, DIM_FACET, DIM_CORROBORATOR,
)

# ---- Stable machine reason codes (Sol §Report: quarantine counts by stable reason code) ----------
RC_SCHEMA_UNKNOWN_FIELD = 'schema.unknown_field'
RC_SCHEMA_MISSING_FIELD = 'schema.missing_required_field'
RC_SCHEMA_BAD_TYPE = 'schema.bad_type'
RC_SCHEMA_EMPTY_ID = 'schema.empty_id'
RC_SCHEMA_DUP_ID = 'schema.duplicate_id'
RC_BINDING_UNBOUND = 'binding.unbound'
RC_BINDING_SPAN_UNVERIFIED = 'binding.span_does_not_verify'
RC_BINDING_POLICY_REFUSED = 'binding.source_policy_refused'
RC_BINDING_STALE_TARGET = 'binding.stale_attribution_target'
RC_BINDING_IDENTITY = 'binding.identity_not_proven'
RC_BINDING_EXPR_MISMATCH = 'binding.expression_mismatch'
RC_BINDING_UNIT_MISMATCH = 'binding.evidence_unit_mismatch'
RC_BINDING_POLICY_MISMATCH = 'binding.stored_policy_mismatch'
RC_CACHE_CLAIM_MISMATCH = 'cache.claim_not_derive_claim'
RC_CACHE_HAS_NUMBER = 'cache.has_number_mismatch'
RC_CACHE_SPAN_NUMBERS = 'cache.span_numbers_mismatch'
RC_CACHE_COMPLETE_TUPLE = 'cache.complete_tuple_mismatch'
RC_CACHE_COUNTS = 'cache.source_counts_mismatch'
RC_NUMERIC_FABRICATED = 'numeric.claim_number_not_in_span'
RC_NUMERIC_UNIT = 'numeric.claim_unit_not_in_span'
RC_COT_SCAFFOLD = 'cot.prompt_or_json_scaffold'
RC_COT_UNCLASSIFIED = 'cot.unclassified_free_text'         # NEEDS_OPUS, not a fail
RC_COT_STALE_CACHE = 'cot.derived_cache_does_not_recompute'
RC_ACT_UNKNOWN = 'act.not_in_registry'
RC_FACET_NOT_IN_TAXONOMY = 'facet.tag_not_in_taxonomy'
RC_FACET_UNSUPPORTED = 'facet.tag_not_recomputed'
RC_CORR_INCOMPLETE_BINDING = 'corroborator.incomplete_binding'
RC_CORR_SPAN_UNVERIFIED = 'corroborator.span_does_not_verify'

# ---- The closed v2 card schema -------------------------------------------------------------------
# Sol §Structure: "Unknown fields fail schema validation until explicitly added to the schema." This is
# the whole closed set the miner serializes; a field not here fails DIM_STRUCTURE.
TOP_LEVEL_FIELDS = frozenset({
    'id', 'claim', 'span', 'span_raw', 'span_start', 'span_end', 'span_numbers', 'has_number',
    'level', 'horizon', 'method', 'mechanisms', 'doi', 'authors', 'venue', 'year',
    'attribution', 'source', 'work_id', 'evidence_unit_id', 'expression_id',
    'attribution_target_expression_id', 'permitted_expression_ids', 'manifestation_id',
    'content_hash', 'source_policy', 'act', 'act_registry_version', 'card_kind',
    'effect', 'unit', 'comparator', 'outcome', 'finding', 'holding', 'authority',
    'recommendation', 'limitation', 'population', 'geography', 'period', 'technology',
    'industry', 'unit_of_analysis', 'design', 'uncertainty', 'study_design', 'geographic_scope',
    'section', 'section_weight', 'context_start', 'context_end', 'field_provenance',
    'source_version', 'text_field', 'facet_tags', 'facet_tags_span', 'complete_tuple',
    'corroborating_sources', 'same_unit_other_expressions', 'n_sources', 'n_evidence_units',
})

# Fields that MUST exist and be non-empty for a card to be structurally auditable at all.
REQUIRED_FIELDS = frozenset({
    'id', 'manifestation_id', 'content_hash', 'span_start', 'span_end', 'span_raw', 'act',
    'work_id', 'expression_id', 'evidence_unit_id',
})

# Declared JSON types for the fields whose type the screen enforces.
FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    'id': str, 'claim': str, 'span': str, 'span_raw': str, 'span_start': int, 'span_end': int,
    'span_numbers': list, 'has_number': bool, 'mechanisms': list, 'authors': list,
    'permitted_expression_ids': list, 'manifestation_id': str, 'content_hash': str,
    'work_id': str, 'evidence_unit_id': str, 'expression_id': str,
    'attribution_target_expression_id': str, 'act': str, 'source_policy': str,
    'facet_tags': list, 'facet_tags_span': list, 'complete_tuple': bool,
    'corroborating_sources': list, 'same_unit_other_expressions': list,
    'n_sources': int, 'n_evidence_units': int, 'field_provenance': dict,
}

# A nested support edge (`corroborating_sources` entry) that the miner serializes WITHOUT `span_raw` or
# `permitted_expression_ids` cannot be independently verified — Sol §Structure "Every nested
# corroborator has a complete independent binding." These are the fields a complete edge binding needs.
SUPPORT_EDGE_BINDING_FIELDS = frozenset({
    'manifestation_id', 'content_hash', 'span_start', 'span_end', 'span_raw',
    'permitted_expression_ids',
})

# The extracted typed fields whose content is an ATOMIC_EVIDENCE_VALUE. Deterministically these can be
# proven clean ONLY when they are a verbatim slice of their declared source window; otherwise they are
# NEEDS_OPUS (their semantic support requires a model). This is DATA read from the act registry at
# runtime, but the union below is the safe superset the screen falls back to.
ATOMIC_FIELDS = frozenset({
    'effect', 'unit', 'comparator', 'outcome', 'finding', 'holding', 'authority',
    'recommendation', 'limitation', 'population', 'geography', 'period', 'technology',
    'industry', 'unit_of_analysis', 'design', 'uncertainty', 'level', 'horizon', 'method',
    'study_design', 'geographic_scope',
})

# Fields whose value must byte-for-byte match live graph metadata (GRAPH_METADATA class).
GRAPH_METADATA_FIELDS = frozenset({
    'manifestation_id', 'content_hash', 'work_id', 'evidence_unit_id', 'expression_id',
    'attribution_target_expression_id', 'doi', 'venue', 'year', 'attribution', 'source_version',
    'authors', 'permitted_expression_ids',
})

# Fields the CoT loop does not classify directly: nested structures screened by their own pass, and the
# facet/number list caches decided by DIM_FACET / DIM_CACHES.
COT_SKIP_FIELDS = frozenset({
    'corroborating_sources', 'same_unit_other_expressions', 'field_provenance',
    'facet_tags', 'facet_tags_span', 'span_numbers',
    'id',  # the card's own coordinate identifier — screened by DIM_STRUCTURE / DIM_BINDING, not content
})

# Fields whose value must be a member of a closed vocabulary (REGISTRY_VALUE class).
REGISTRY_FIELDS = frozenset({
    'act', 'act_registry_version', 'card_kind', 'source_policy', 'text_field', 'section',
})


@dataclass
class DimensionResult:
    """One dimension's decision on one audit row or support edge."""
    verdict: str                       # PASS / FAIL / UNCERTAIN / NOT_APPLICABLE / NEEDS_OPUS / NEEDS_CONTRACT
    reason_codes: list[str] = field(default_factory=list)
    detail: str = ''

    def to_json(self) -> dict:
        return dict(verdict=self.verdict, reason_codes=list(self.reason_codes), detail=self.detail)


@dataclass
class FieldContentClass:
    """The CoT-contamination content class assigned to one non-empty field."""
    field: str
    content_class: str                 # a CONTENT_CLASSES member, or '' when it could not be assigned
    verdict: str                       # PASS / FAIL / NEEDS_OPUS
    reason_code: str = ''

    def to_json(self) -> dict:
        return dict(field=self.field, content_class=self.content_class,
                    verdict=self.verdict, reason_code=self.reason_code)


@dataclass
class DeterministicReceipt:
    """The append-only Tier-0 receipt for one audit row or one support edge (Sol Phase 1 §6:
    deterministic_receipts.jsonl). Reopening it and rerunning must reproduce the same decision."""
    audit_row_id: str
    card_id: str
    scope: str                         # 'top_level' | 'support_edge' | 'same_unit_expression'
    json_pointer: str
    overall: str                       # PASS / FAIL / NEEDS_OPUS
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    content_classes: list[FieldContentClass] = field(default_factory=list)

    def to_json(self) -> dict:
        return dict(
            audit_row_id=self.audit_row_id, card_id=self.card_id, scope=self.scope,
            json_pointer=self.json_pointer, overall=self.overall,
            dimensions={k: v.to_json() for k, v in self.dimensions.items()},
            content_classes=[c.to_json() for c in self.content_classes],
        )
