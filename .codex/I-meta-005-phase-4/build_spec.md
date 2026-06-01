# Phase 4 BUILD SPEC — multi-round saturation search (#988). BINDING.

**The APPROVED brief `.codex/I-meta-005-phase-4/brief.md` (Codex APPROVE, 6-round) is the detailed design
contract. Implement it EXACTLY.** This is the file-by-file checklist.

## HARD CONSTRAINTS (brief §0)
1. Everything behind `PG_USE_RESEARCH_PLANNER` (default off). **OFF byte-identical** — the single-pass
   `run_live_retrieval` → select → legacy gate path unchanged (no loop).
2. NO `if domain ==` / clinical literal as a control value on the on-path. The loop targets the plan's
   under-covered sub-queries.
3. MONEY: zero generator tokens until PROCEED/partial. The loop spends retrieval rounds only.
4. **BUILD + SMOKE spend-free**: the loop DECISION logic (`saturation.py`) is pure + smoke-tested with
   stubbed per-round evidence; the live `run_live_retrieval` round is live-only. Assert no live client.
5. snake_case; no `unittest.mock` in `src/`.

## FILE-BY-FILE (implement brief §2)
1. **NEW `src/polaris_graph/retrieval/saturation.py`** (brief §2.1, pure):
   - `marginal_novelty(prev_rows, new_round_rows) -> float`: novel iff canonical URL (via `audit_ir/run_diff
     ._normalize_url`, add a public wrapper to import) of the row's `source_url` not in prev; intra-round
     dups collapse too. `len(novel)/max(1,len(new))`.
   - `gap_sub_queries(report, plan) -> list[str]`: empty-facet sub-query texts; AND for a total-shortfall
     section (covered<target, no empty facets) → ALL the section's sub-query texts. Never empty when a
     section is under-covered.
   - `saturation_decision(*, verdict, round_index, max_rounds, novelty, eps) -> str`: proceed→STOP_SUFFICIENT;
     abort→STOP_BUDGET; expand+round+1>=max→STOP_BUDGET; expand+round>=1+novelty<eps→STOP_NOVELTY; else
     CONTINUE.
2. **`src/polaris_graph/retrieval/live_retriever.py`** (brief §2.2): add `anchor_seed: bool = True` to
   `run_live_retrieval`; when False `all_queries = amplified_queries` (no research_question prepend) AND it
   passes through to `run_need_type_backends(..., anchor_seed=False)` AND `validate_amplified_queries(...,
   always_keep_anchor=False)` (so the scope validator does not re-add the anchor). Off-mode default True =
   byte-identical.
3. **`src/polaris_graph/retrieval/domain_backends.py`** (brief §2.2): add `anchor_seed: bool = True` to
   `run_need_type_backends`; when False `queries = amplified_queries` only (no research_question prepend);
   lift the 3-query amplified cap for gap rounds (anchor_seed=False fires all gap queries).
4. **`src/polaris_graph/generator/multi_section_generator.py` + `scripts/run_honest_sweep_r3.py`**
   (brief §2.3): a `partial_mode` flag (status==partial_saturation) DISABLES all five out-of-plan appenders
   (V30 contract plans :4167/:3002, M50 :3073/:5177, Trial Summary :3057/:4972, Analyst Synthesis :3190/:4998,
   Limitations :3199/:5034). Build a PRUNED ResearchPlan (sufficient sections only; drop orphaned sub_queries;
   REMAP sub_query_indices; re-validate facet-union) and pass it to the generator.
5. **`scripts/run_honest_sweep_r3.py`** the LOOP (brief §2.2): wrap retrieval→select→[V30/upload inject]→
   `assess_plan_sufficiency` in a loop; on CONTINUE fire a gap-only round (`anchor_seed=False`,
   `gap_sub_queries`), merge with global evidence_id renumber (reuse :2128 pattern), re-select, re-gate.
   PRE-SPEND budget: `per_query_discovery_cost = 2 + adapter_count`; preflight truncate gap queries to
   `floor(remaining/cost)`; cumulative_discovery_calls += fired*cost (worst-case). STOP_SUFFICIENT→generator
   (full plan); STOP_NOVELTY/STOP_BUDGET→`partial_saturation` (pruned plan + partial_mode) OR
   `abort_corpus_inadequate` if zero sufficient. `PG_SATURATION_MAX_ROUNDS`, `PG_SATURATION_NOVELTY_EPS`,
   `PG_SATURATION_MAX_RETRIEVAL_CALLS`. Off-mode: single-pass unchanged.
6. **status taxonomy** (brief §2.3): register `partial_saturation` in the runner known-status set + summary
   map (`run_honest_sweep_r3.py:173`,`:194`) + `audit_ir/regression_lab.py:589` mirror + update
   `tests/polaris_graph/test_md9_regression_lab.py:280` drift guard.

## SMOKE — `tests/polaris_graph/retrieval/test_saturation_phase4.py`
Implement ALL P4-1..P4-16 (serialized §8.4; plain-class stubs, no unittest.mock). Non-relaxable: P4-1 OFF
byte-identity, P4-5 loop-convergence (novelty flatten → STOP_NOVELTY), P4-6 gap-closure (generator once),
P4-7/7b/7c partial (pruned plan + index remap + ALL FIVE out-of-plan appenders disabled), P4-10 gap-only BOTH
seams (>3 queries, no anchor), P4-13 global evidence_id renumber, P4-14 budget NEVER exceeded (worst-case),
P4-15 partial_saturation taxonomy. Run `python -m pytest tests/polaris_graph/retrieval/test_saturation_phase4.py
-q -p no:cacheprovider` → green; then a retrieval/generator regression subset for OFF byte-identity.
