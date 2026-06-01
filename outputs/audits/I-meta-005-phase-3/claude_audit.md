# Claude architect audit — I-meta-005 Phase 3 (plan-sufficiency money-trap gate, #987)

## Scope
NEW adequacy/plan_sufficiency_gate.py: adequacy = per-section evidence_target coverage (facet-level,
provenance-first row→section mapping via query_origin × sub_query_indices) × numeric authority_score floor,
computed from the Phase-1 ResearchPlan + Phase-0a authority (NO _DEFAULT_DOMAIN_THRESHOLDS domain dict);
single binding gate on the FINAL evidence_for_gen before generate_multi_section_report — a shallow corpus is
held at EXPAND/ABORT with ZERO generator tokens. research_planner sub_query_indices + fail-closed whole-plan
facet-union validation + canonical SHA; live_retriever per-row authority sidecar (planner-mode, independent of
PG_USE_AUTHORITY_MODEL); multi_section_generator provenance-first + per-facet-reserved assignment. All behind
PG_USE_RESEARCH_PLANNER (default off), OFF byte-identical.

## Dual-review trajectory
- Codex brief-gate: APPROVE after 6-round convergence (authority type/persistence, provenance mapping,
  facet-level coverage, billed-set handoff, gate placement — a NEW genuine flaw each round, not re-litigation).
- Build architect: 4/5 axes CLEAN; flagged P1 — the on-mode assignment did flat-concat-then-slice, which
  could truncate a certified facet's only row (facet-level money-trap at the cap boundary). Fixed: per-facet
  reservation + authority_floor threaded.
- Codex diff-gate iter1: P1 — the reservation could still be truncated when a section maps MORE facets than
  max_ev_per_section (31-facet repro). Fixed: clamp order so the reserved per-facet set is sacred (size cap
  applies only to filler). Deviations A/B/C (untestable-offline sweep block, tuning defaults, anchor-query
  scope) ruled acceptable Phase-3 scope by Codex.
- Codex diff-gate iter2: APPROVE (zero P0/P1/P2). 26 Phase-3 + 22 planner regression green.

## Verification
- Smoke 26 Phase-3 (P3-1..P3-17 + P3-15e per-facet truncation + P3-15f floor-threading + P3-15g size-cap) +
  44 generator/planner regression green, serialized §8.4.
- OFF byte-identity: legacy assess_corpus_adequacy + round-robin assignment unchanged; additive fields inert.
- Zero generator bill on hold: single binding gate runs before generate_multi_section_report; EXPAND/ABORT →
  abort_corpus_inadequate with no generator/downstream LLM client constructed.

## Verdict
APPROVE for merge. No live spend (gate pure over rows; on-mode opt-in, operator-gated via Gate-A; tuning-
default calibration is a Phase-4 first-live-run task). The money-trap is closed end-to-end: a shallow corpus
cannot bill the generator, and the facet-level depth guarantee carries into the billed evidence set.
