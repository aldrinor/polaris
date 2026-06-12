# I-perm-021 (#1213) — RequiredEntityLedger: forensic plan (durable)

Forensic by the parallel Claude agent (2026-06-11), persisted so it is not lost.

## TL;DR
The completeness gap is mostly UPSTREAM (retrieval + extraction), NOT reduce-time. POLARIS
already MEASURES required-entity coverage (post-verify, report-level, in `native_gate_b_inputs.py`)
and already has a bounded gap-driven retrieval lane (`run_required_entity_lane`, #1190) — but that
lane is S0-safety-only, fires once pre-generation, and never closes the loop. The honest scope of
#1213 is wiring existing pieces into a closed feedback loop: extend gap-driven retrieval beyond S0
to all required slots, add a POST-strict_verify ledger that forces inclusion of verified slots and
discloses the rest as explicit gaps. It is NOT a reduce-time invention; the owner's proposed
`_run_section` hook is at the WRONG altitude (misses the S1 trial entities). Codex design-gate must
settle the altitude question before any code.

## 1. Root cause (grounded)
- Required entities declared in `config/scope_templates/{clinical,policy,workforce}.yaml`
  `per_query_report_contract[<slug>].required_entities` (id/type/severity/anchor/canonical-id
  doi|pmid|url_pattern/rendering_slot/required_fields; S0 adds s0_category + content reqs).
  e.g. clinical.yaml:283-331 (S1 SURPASS trials, rendering_slot efficacy_surpass_*), 437-525 (S0 safety).
  Loader `native_gate_b_inputs.load_required_entities` (:216-234, fail-closed).
- Coverage MEASURED post-report at Gate-B: `build_native_gate_b_inputs` (:649-783) iterates
  `multi.sections[*].kept_sentences_pre_resolve` (strict_verify-VERIFIED; guard :683-684), computes
  `covered_element_ids` via `_claim_covers_entity` (:514-535) = claim cites evidence whose CANONICAL id
  EXACTLY equals the entity's (`_entity_canonical_match` :293-309). Emits `CoverageLedger` (:778).
  So `missing = required − ⋃covered` is ALREADY computable here — what's missing is the feedback loop.
- REDUCE: two paths. (a) V30 contract path `run_contract_section` (contract_section_runner.py:483,
  dispatched multi_section_generator.py:5112-5128) renders the S1 trial entities by rendering_slot AND
  ALREADY discloses unfillable slots faithfully (compose_gap_payload :370-372; the "did not survive
  strict verification… curator-actionable gap" sentence :993-1019). (b) legacy/distill path `_run_section`
  (:2320), distill REDUCE branch (:1706-1769), then UNCHANGED strict_verify (:2426-2430); zero-verified →
  _GAP_STUB_SENTENCE (:2597-2599) / _NO_EVIDENCE_GAP_STUB_SENTENCE (:2356-2373).
  NEITHER path knows about required_entities. `generate_multi_section_report` (:4711-4812) receives NO
  template/slug/required_entities. So a `_run_section`-local ledger is structurally blind to the S1 trial
  entities AND only fires when PG_SECTION_DISTILL is also on.
- VERIFIED authority = strict_verify on the section OUTPUT (:2430) → kept_sentences_pre_resolve.
- Existing #1190 lane `run_required_entity_lane` (required_entity_retrieval.py:295-428) wired at
  run_honest_sweep_r3.py:4808 (PG_REQUIRED_ENTITY_RETRIEVAL, default OFF). Bounded (max 12 entities,
  3 q/entity, 5 results/q, 3 seed URLs/entity :90-100), via run_live_retrieval(seed_only=True), fetched
  rows carry REAL URLs never keyed to an entity_id (:319 the faithfulness invariant). BUT fires once
  pre-gen, only for unsatisfied FrameRows, query map S0-only (:113-123).

## 2. Design — TWO-PHASE ledger (resolves the sequencing contradiction)
The issue's "ledger BEFORE reduce" + "missing = required − verified_bindings" + "strict_verify is sole
VERIFIED authority" CANNOT all hold (strict_verify runs on reduce OUTPUT). Resolve as two phases:
- Phase A (pre-gen, report-level): seed ledger from required_entities; mark MISSING/RETRIEVED/MAPPED
  from CORPUS PRESENCE (does any row carry the entity's canonical id + a usable span?). Phase-A MISSING
  drives the extended pre-gen targeted retrieval (the #1190 lane, past S0).
- Phase B (post-strict_verify, report-level): missing = required − {entity has a VERIFIED binding} via
  the exact `_claim_covers_entity` over kept_sentences_pre_resolve. Authoritative VERIFIED/INCLUDED +
  GAP_DISCLOSED decision.
NEW `src/polaris_graph/generator/required_entity_ledger.py` (pure, DI for retrieval): RequiredSlotState
∈ {MISSING,RETRIEVED,MAPPED,VERIFIED,INCLUDED,GAP_DISCLOSED}; RequiredSlot + RequiredEntityLedger with
missing()/mark_corpus()/mark_verified()/finalize(). Reuse `_claim_covers_entity`+`_entity_canonical_match`
verbatim (do NOT re-implement matching). Gap disclosures are DETERMINISTIC TEMPLATED strings (no LLM),
following _GAP_STUB_SENTENCE / the contract gap-sentence precedents — a structured evidence_gaps list,
never fabricated prose. Bounded recovery round optional (PG_REQUIRED_ENTITY_LEDGER_GAP_ROUNDS default 0).

## 3. Faithfulness (every failure path)
1. Forcing inclusion of an UNVERIFIED slot → forbidden: INCLUDED reachable ONLY from VERIFIED, set ONLY
   by mark_verified reading strict_verify is_verified=True. Ledger never sets is_verified.
2. Gap retrieval relabeling a row as the entity → prevented (#1190 invariant :319; coverage still requires
   EXACT canonical match; alt URL can't flip a url_pattern entity — recovery gets CONTENT in, never forces coverage).
3. evidence_gaps filled with unsupported claim → forbidden: templated strings, no fabricated citation.
4. Re-generation bypassing strict_verify → forbidden: re-gen re-runs UNCHANGED strict_verify (:2426-2430).
5. D8 coverage fraction inflated by ledger credit → must NOT: ledger VERIFIED/INCLUDED set MUST equal
   `_claim_covers_entity` (no new credit path). New credit = §-1.1-lethal, out of scope.
6. MAPPED (distiller fuzzy) leaking into VERIFIED → forbidden: only post-strict_verify bindings transition.

## 4. Edits + default-OFF flag PG_REQUIRED_ENTITY_LEDGER (read at call time, never import — I-cap-005 lesson)
NEW required_entity_ledger.py; EDIT required_entity_retrieval.py (extend query map past S0, accept ledger
missing()); EDIT run_honest_sweep_r3.py (Phase A near :4808; Phase B after generate :5703 + finalize → report
disclosure + manifest). Flag-OFF byte-identical (module never imported, no disclosure, manifest unchanged).

## 5. SEVEN open design questions for the Codex design-gate
1. ALTITUDE (pivotal): per-section (_run_section, owner's hook) vs REPORT-LEVEL (post-generate, pre/at
   build_native_gate_b_inputs)? Evidence strongly favors report-level (S1 trials render via contract path;
   _run_section dark unless PG_SECTION_DISTILL; missing already lives report-level + post-verify). RECOMMEND report-level.
2. SEQUENCING: accept the two-phase split, or insist on a single pre-reduce ledger (internally contradictory)?
3. Pre-gen retrieval budget for the extended non-S0 lane: reuse #1190 caps, or a reserved budget? (no-overshoot
   1000-fetch envelope #1168 — must be explicit.)
4. Post-verify gap-recovery round IN-SCOPE for #1213, or ship INCLUSION+DISCLOSURE ONLY (no 2nd generation,
   lower risk, smaller diff) and defer recovery to a follow-up? RECOMMEND split.
5. evidence_gaps placement: per-section body (like contract gap sentence) vs consolidated "Coverage gaps"
   section vs manifest-only? §-1.1 + blind operator → explicit body section.
6. "Required" sourcing benchmark vs production: ledger MUST use the native scope template only (the §-1.1
   contamination lock native_gate_b_inputs.py:10-16 — NEVER read outputs/dr_benchmark/). Confirm inheritance.
7. MAPPED for url_pattern-only entities: exact-equality means alt URL can't flip coverage; does that class
   need a distinct "content present but cited URL not canonical" note?

## 6. Honest caveats
- Gap is LARGELY UPSTREAM. A reduce-time ledger cannot manufacture coverage; if POLARIS still loses on
  completeness, the residual lever is retrieval breadth/recall (#1204 source-funnel campaign), not this ledger.
- Risk concentration = the gap-recovery round (Q4). Lowest-risk #1213 = inclusion+disclosure ONLY (no 2nd LLM
  generation); recovery round a gated follow-up. RECOMMEND Codex split.
- url_pattern regulatory entities are structurally un-flippable by alt-URL retrieval — ledger gets content in
  + discloses, cannot raise their measured coverage. Don't promise coverage gains for that class.
- Paid §-1.1 smoke genuinely required (the effect + no-fabrication claim can't be proven offline; flag-OFF
  byte-identical can).
- Out of scope: D8 thresholds, new coverage credit (that's #1212 coverage_binder), strict_verify/4-role/the
  operator-locked _entity_canonical_match exact-equality gate.

Key files: native_gate_b_inputs.py (_claim_covers_entity/_entity_canonical_match/CoverageLedger/
normalize_evidence_pool_lookup/§-1.1 lock), required_entity_retrieval.py (#1190 lane), coverage_binder.py
(#1212 additive-credit precedent), multi_section_generator.py (generate :4711, _run_section :2320, distill
REDUCE :1706/:2386-2430, gap stubs :190-205/:2597-2599, dispatch :5112-5168), evidence_distiller.py,
contract_section_runner.py (V30 trial slot gap disclosure :370-388/:993-1019), run_honest_sweep_r3.py
(:4808-4869/:5703/:7173+), clinical.yaml (:283-525), docs/drb76_downstream_solutions.md (VerifiedCoverageLedger spine).
