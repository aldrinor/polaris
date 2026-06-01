"""Field-agnostic source discovery by NEED-TYPE — I-meta-005 Phase 2 (#986).

This package replaces the bypassed 4-branch domain enum switch in
`retrieval/domain_backends.run_domain_backends` with a field-agnostic registry
keyed on the planner's DECLARED EvidenceNeed + extracted JURISDICTION — never a
domain. Behind `PG_USE_RESEARCH_PLANNER` (default off); OFF is byte-identical
(the legacy `if domain ==` switch is retained + selected when off).

Public surface:
- `source_adapter_registry`: maps each EvidenceNeed -> its discovery adapter
  callables (the EXISTING functions, re-keyed off the need) + the jurisdiction
  scope loader for the scoped needs.
- `need_type_router.route_needs_to_adapters(frame)`: returns the deduped union
  of adapters for `frame.evidence_needs`; empty -> {primary_literature,
  open_web} safe generic fallback; NO `if domain ==`.
"""
