# Claude architect audit — I-meta-005 Phase 2 (source discovery by need-type, #986)

## Scope
NEW discovery package (source_adapter_registry, need_type_router) + config/discovery/jurisdiction_scopes.yaml
(versioned DATA) replacing the domain_backends `if domain ==` 4-branch switch + US-only _POLICY_SITE_FILTERS
on the on-path. research_planner emits additive evidence_needs (10-enum) + jurisdictions (normalized codes);
domain_backends dual-path (on=registry, off=legacy switch byte-identical); live_retriever research_frame seam
with up-front MalformedPlanError validation. All behind PG_USE_RESEARCH_PLANNER (default off), OFF byte-identical.

## Dual-review trajectory (Claude architect + Codex diff-gate)
- Build architect: 4 of 5 axes CLEAN; flagged P1 — open_web + news_press wired to policy_targeted_serper
  (US _POLICY_SITE_FILTERS literal on the ON-path, the exact cross-jurisdiction bug Phase 2 eliminates).
- Fix: open_web → NO registry adapter (core baseline Serper covers it, mirrors S2 exclusion); news_press →
  data-driven issuer scope ONLY; policy_targeted_serper removed from the registry. Smoke asserts US-scoped
  serper never on on-path.
- Codex diff-gate iter1: confirmed open_web fix; P1 — _as_str_list coerced scalar evidence_needs/jurisdictions
  to [] silently (malformed scalar took the empty-needs fallback instead of failing loud). Fix: _as_str_list_strict
  distinguishes absent (None→[]) from present-but-wrong-shape (scalar→MalformedPlanError). P2 coverage-drift:
  P2-4 whole-wiring now covers the sweep/live_retriever seam.
- Codex diff-gate iter2: APPROVE (zero P0/P1/P2). 58 tests green.

## Verification
- Smoke 43/43 Phase-2 (P2-1..P2-11 + malformed + scalar-malformed + sweep-seam) + 15/15 domain_backends
  regression (OFF byte-identity), serialized §8.4.
- Field-agnostic: on-path `if domain ==` count = 0 (AST + sweep seam); NO US/domain host literal on the
  on-path (open_web fix); jurisdiction scopes from versioned jurisdiction_scopes.yaml DATA.
- Malformed evidence_need OR jurisdiction (element OR scalar shape) fails loud up-front before any discovery;
  valid-shape-unknown jurisdiction non-fatal; adapter/network errors fail-open.

## Verdict
APPROVE for merge. No live spend (discovery adapters injected/stubbed in smoke; on-mode opt-in, operator-
gated via Gate-A before any production flip). Phase-2 needs the planner ON; ON-mode discovery is the core
Serper/S2 baseline + the field-agnostic need-type registry.
