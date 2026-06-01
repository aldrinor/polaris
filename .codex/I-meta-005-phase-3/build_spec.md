# Phase 3 BUILD SPEC — plan-sufficiency gate (the money-trap fix, #987). BINDING.

**The APPROVED brief `.codex/I-meta-005-phase-3/brief.md` (Codex APPROVE, 6-round convergence) is the detailed
design contract. Implement it EXACTLY.** This is the file-by-file checklist.

## HARD CONSTRAINTS (brief §0 — do not relax)
1. Everything behind `PG_USE_RESEARCH_PLANNER` (default off). **OFF byte-identical** — legacy
   `assess_corpus_adequacy` domain-keyed gate retained + selected when off.
2. **NO per-domain threshold dict / `if domain ==` / clinical literal as a control value on the on-path.**
   Sufficiency = plan × authority, never a domain.
3. **MONEY: the binding gate runs ONCE on-mode, on the FINAL `evidence_for_gen`, immediately before
   `generate_multi_section_report` (:2805) — after selection (:2568) + V30 contract prepend (:2719) + upload
   prepend (:2749).** Legacy `:2001/:2152/:2249` sites are telemetry-only on-mode (do NOT abort).
4. **BUILD + SMOKE spend-free** — the gate is a pure function over rows; the planner is faked in smoke;
   assert no generator/downstream LLM client constructed on EXPAND/ABORT.
5. snake_case; no `unittest.mock` in `src/`; additive fields default-safe so OFF is byte-identical.

## FILE-BY-FILE (implement brief §2)
1. **`src/polaris_graph/planning/research_planner.py`** (brief §2.1/§2.1b/§2.3a):
   - `SectionOutlineItem` += `sub_query_indices: list[int]` (additive, default `[]`); planner prompt emits it.
   - `to_canonical_dict()` (`:271`) serializes `sub_query_indices` (into the SHA-pinned plan).
   - **Fail-closed post-finalization validation** in `plan_research()` AFTER `_merge_truncate_subqueries`
     (`:596`): each on-mode section MUST have ≥1 in-range `sub_query_index` + `evidence_target ≥ 1`, AND
     `union(all sections' sub_query_indices) == set(range(len(final sub_queries)))` (every planned facet
     mapped). Any violation → raise `MalformedPlanError` (before retrieval/generation). Off-mode: `[]` inert.
2. **`src/polaris_graph/retrieval/live_retriever.py`** (brief §2.3a):
   - At the on-mode evidence-row build (`:2222-2230`), ADD `authority_score: float` + `authority_confidence:
     str` to each row, computed DIRECTLY via `score_source_authority(...)` whenever `PG_USE_RESEARCH_PLANNER`
     is on — INDEPENDENT of `PG_USE_AUTHORITY_MODEL`. Honest low score + LOW confidence if signals thin (never
     a silent 0.0). Additive, default `0.0`/`""` off-mode → byte-identical.
3. **NEW `src/polaris_graph/adequacy/__init__.py` + `plan_sufficiency_gate.py`** (brief §2.1/§2.2):
   - `assess_plan_sufficiency(*, plan, corpus_rows, authority_floor, round_index, max_rounds) ->
     PlanSufficiencyReport`. Pure. Enriches any billed row missing the sidecar via `score_source_authority`
     (contract/upload rows). Per section: relevance = provenance-first (`query_origin` ∈ section's
     sub-query texts), fallback = `_content_words` + `MIN_CONTENT_WORD_OVERLAP` against the section's
     sub-query texts ONLY for empty/sentinel origins `{primary_trial_doi_seed, need_type_backend,
     domain_backend}`; coverage = above-`authority_floor` relevant rows. Section SUFFICIENT iff total ≥
     `evidence_target` AND every mapped sub_query_index has ≥ `PG_PLAN_SUFFICIENCY_MIN_PER_FACET` (default 1)
     above-floor rows. Verdict: PROCEED (all sufficient) / EXPAND (under-covered, round<max) / ABORT
     (under-covered, exhausted). `PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR` (float [0,1]).
4. **`src/polaris_graph/generator/multi_section_generator.py`** (brief §2.2b):
   - On-mode `_assign_evidence_to_planned_outline` (`:618`) becomes PROVENANCE-FIRST: assign each row to the
     section(s) whose `sub_query_indices` its `query_origin` matches (sentinel/empty → content-word fallback).
     Off-mode: the round-robin `ev_ids[i::n_sections]` path is byte-identical.
5. **`scripts/run_honest_sweep_r3.py`** (brief §2.3):
   - On-mode: the legacy `assess_corpus_adequacy` at `:2001/:2152/:2249` becomes telemetry-only (record, do
     NOT abort). The binding gate is a SINGLE `assess_plan_sufficiency(...)` call on the FINAL
     `evidence_for_gen` immediately before `generate_multi_section_report` (`:2805`), after the V30 contract
     (`:2719`) + upload (`:2749`) prepends. PROCEED → generator; EXPAND/ABORT → status
     `abort_corpus_inadequate`, ZERO generator tokens. Off-mode: legacy gate aborts as today (byte-identical).

## SMOKE — `tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py`
Implement ALL brief cases P3-1..P3-17 (serialized §8.4; plain-class fakes, no unittest.mock; real dict rows).
Non-relaxable: **P3-1 OFF byte-identity**, **P3-3/P3-4 trap (housing/sovereignty) → ZERO generator call**,
**P3-8 zero-generator-bill-on-hold**, **P3-9 facet-level (empty sub-query → UNDER_COVERED)**, **P3-12
fail-closed mapping**, **P3-14 whole-plan facet union**, **P3-15/P3-16 gate-the-billed-set + provenance
assignment**, **P3-17 injected-row enrichment**. Run `python -m pytest tests/polaris_graph/adequacy/ -q
-p no:cacheprovider` → green; then a corpus_adequacy regression subset for OFF byte-identity.
