HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
Front-load ALL real findings. Reserve P0/P1 for real execution risks; P2/P3 for the rest.

Output the §8.3.9 YAML verdict FIRST:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Codex BRIEF gate iter 6 (confirm) — I-meta-005 Phase 4 (#988): multi-round saturation search

Reviewing ACCEPTANCE-CRITERIA correctness. Parent plan #982 row 50. Phase 4 closes gap #3 (search depth):
single-pass retrieval → a gap-targeted SATURATION LOOP that, when Phase 3's plan-sufficiency gate returns
EXPAND, fires another retrieval round for ONLY the under-covered sub-questions, re-gates, and stops on
gap-closure OR marginal-novelty < ε OR round/budget exhaustion → a PARTIAL report (not a blind abort).

## 0. HARD CONSTRAINTS (operator-locked — NOT Codex-consultable; do not offer the relaxed option)
- **NO per-domain / `if domain ==` / clinical literal as a control value on the on-path.** The loop targets
  the plan's under-covered sub-queries (field-agnostic), never a domain.
- **OFF byte-identical.** Gated on `PG_USE_RESEARCH_PLANNER` (default off). Off = today's SINGLE-PASS
  `run_live_retrieval` → select → (legacy gate), byte-for-byte. On = the saturation loop.
- **MONEY: zero generator tokens until PROCEED.** The loop runs retrieval+selection+Phase-3-gate; the
  generator is billed ONCE, only on the final PROCEED. EXPAND rounds spend retrieval (Serper/S2 calls), NOT
  generator tokens. A budget cap bounds the retrieval rounds.
- **BUILD + SMOKE spend-free.** The loop DECISION logic (novelty metric, stop conditions, gap-query
  selection) is a PURE function tested with stubbed per-round evidence; the live `run_live_retrieval` round
  is exercised only live (Gate-B/Phase-8). Smoke asserts no live client constructed.

## 1. THE PROBLEM (grounded in running code)
- Retrieval is SINGLE-PASS: `run_live_retrieval` (`live_retriever.py:1676`) runs once with a fixed
  `fetch_cap` (`PG_SWEEP_FETCH_CAP`); there is no gap-analysis re-query.
- Phase 3's gate (`run_honest_sweep_r3.py:2776-2819`) computes EXPAND when sections are under-covered, but
  `PG_PLAN_SUFFICIENCY_MAX_ROUNDS` defaults to 0 (`:2785`), so EXPAND collapses to `abort_corpus_inadequate`
  — the gate identifies the gap but cannot CLOSE it. Phase 4 owns the close-the-gap loop.

## 2. THE BUILD (behind PG_USE_RESEARCH_PLANNER)

### 2.1 NEW `src/polaris_graph/retrieval/saturation.py` (pure decision logic)
- `marginal_novelty(prev_evidence_rows, new_round_rows) -> float`: the fraction of the new round's rows that
  are NOVEL. **Single dedup identity = canonical URL via the EXISTING `run_diff` canonicalizer (iter-2 P2):**
  reuse `audit_ir/run_diff.py:220` `_normalize_url` (the existing private helper — add a thin public wrapper if importing a private name is undesirable) which lowercases host, strips `www.`, DROPS tracking
  params (utm_*/fbclid/gclid/ref/...) but PRESERVES + sorts identifier query params — so two distinct
  query-addressed sources (`?abstract_id=123` vs `?abstract_id=456`, `?doi=...`) stay DISTINCT while only
  tracking noise collapses. (eTLD+1+path alone would wrongly merge distinct identifier-addressed pages — the
  `corroboration` host-only primitive is too coarse here.) A new row is NOVEL iff its canonical URL is not in
  `prev_evidence_rows`. **Row URL field = `source_url` (iter-4 P2 — live rows carry `source_url`, not `url`,
  `live_retriever.py:2221`); intra-round duplicates ALSO collapse (two rows in the SAME new round with the
  same canonical URL count as one novel).** Returns `len(novel) / max(1, len(new_round_rows))`.
- `gap_sub_queries(sufficiency_report, plan) -> list[str]`: the sub-query TEXTS to fire next, covering BOTH
  shortfall modes (iter-1 P1 #2 — the gate fails on `covered_count < evidence_target` OR `empty_facets`,
  `plan_sufficiency_gate.py:308`):
  - for an under-covered section with `empty_facets` → the sub-query texts at those empty facet indices;
  - for an under-covered section with `covered_count < evidence_target` but NO empty facets (total shortfall)
    → ALL the section's mapped sub-query texts (fire the whole section to raise total coverage).
  Deduped, field-agnostic, derived from the plan. NEVER empty when a section is under-covered (else the loop
  would have no query to fire — the exact gap Codex flagged).
- `saturation_decision(*, verdict, round_index, max_rounds, novelty, eps) -> Decision` where Decision ∈
  {CONTINUE, STOP_SUFFICIENT, STOP_NOVELTY, STOP_BUDGET}:
  - verdict == proceed → STOP_SUFFICIENT (gap closed).
  - **verdict == abort → STOP_BUDGET (iter-1 P1 #3):** the Phase-3 gate returns `abort` when
    `round_index >= max_rounds` (`plan_sufficiency_gate.py:332`); that is an explicit terminal — map it to
    STOP_BUDGET (rounds/budget exhausted, the loop must terminate; never an unhandled verdict).
  - verdict == expand AND round_index+1 >= max_rounds → STOP_BUDGET (rounds exhausted).
  - verdict == expand AND round_index >= 1 AND novelty < eps → STOP_NOVELTY (the last round added < eps
    novel rows — the findings-per-round curve flattened; more rounds won't help).
  - else (expand, rounds left, novelty ≥ eps) → CONTINUE.

### 2.2 Sweep wiring — the loop (`run_honest_sweep_r3.py`)
- On-mode, wrap retrieval → `select_evidence_for_generation` → Phase-3 `assess_plan_sufficiency` in a loop:
  - round 0 = today's retrieval (unchanged).
  - compute the gate verdict on the round's `evidence_for_gen`. `saturation_decision`:
    - STOP_SUFFICIENT → break to the generator (PROCEED).
    - STOP_NOVELTY / STOP_BUDGET → break to a PARTIAL report (status `partial_saturation` — see 2.3).
    - CONTINUE → fire round N+1: a GAP-ONLY retrieval round that fires ONLY `gap_sub_queries(...)` and does
      NOT re-fire the broad anchor (iter-1 P1 #1 — `run_live_retrieval` always prepends `research_question`
      to `all_queries` at `live_retriever.py:1741`, so a naive `amplified_queries=` call would re-run the
      anchor and waste budget). FIX: add an additive `anchor_seed: bool = True` param to `run_live_retrieval`;
      a gap round calls it with `anchor_seed=False` so `all_queries = gap_sub_queries` only. **AND propagate
      it to the need-type backend (iter-2 P1):** the on-mode seam ALSO calls `run_need_type_backends(...,
      research_question=research_question)` (`live_retriever.py:1839`), and that dispatcher independently
      builds `queries = [research_question]` (`domain_backends.py:648`) — so anchor-suppression must reach
      BOTH. Add `anchor_seed: bool = True` to `run_need_type_backends` too; when False its `queries =
      amplified_queries` ONLY (no `research_question` prepend). The gap round threads `anchor_seed=False`
      through to both the core Serper/S2 path AND the need-type adapters. Then MERGE the
      new rows into the cumulative corpus, **renumbering evidence_ids globally (iter-1 P1 #5):** each
      `run_live_retrieval` call restarts ids at `ev_000`, which would COLLIDE/overwrite in the evidence pool;
      reuse the EXISTING legacy-expansion renumber pattern (`run_honest_sweep_r3.py:2128` — `base =
      len(cumulative_rows); new_id = f"ev_{base+i:03d}"`) so ids are globally unique across rounds. Then
      re-select + re-gate; track `novelty` vs the prior cumulative corpus; increment `round_index`.
  - `PG_SATURATION_MAX_ROUNDS` (default e.g. 3) bounds the rounds; `PG_SATURATION_NOVELTY_EPS` (default e.g.
    0.10) is ε.
  - **Cumulative retrieval-budget cap — PRE-SPEND enforcement (iter-3 P1):** rounds spend per effective query
    INSIDE `run_live_retrieval` (Serper `:1790`, S2 `:1806`, over `effective_queries`), so a post-round
    counter OVERSHOOTS (cumulative 1 below cap + a 40-gap-query round = overspend before STOP_BUDGET). FIX:
    PREFLIGHT before firing round N+1. **Exact accounting (iter-4 P1 #2):** `PG_SATURATION_MAX_RETRIEVAL_CALLS`
    counts DISCOVERY calls. **Per-query WORST-CASE cost — the need-type adapters loop PER QUERY (iter-5 P1
    #1):** core Serper + core S2 (`live_retriever.py:1790`,`:1806`) = 2 calls/query, PLUS the need-type
    dispatcher which calls EACH routed adapter inside `for q in queries` (`domain_backends.py:660`) =
    `adapter_count` calls PER gap query (NOT once per backend — the live result undercounts by recording each
    backend once at `live_retriever.py:1857`; that is the bug, so use the worst-case for the cap).
    `per_query_discovery_cost = 2 + adapter_count` (`adapter_count` from the routed need-type registry,
    `source_adapter_registry.py:247`). (Fetch + OpenAlex `:2085`,`:2100` are bounded by `fetch_cap`, not
    multiplied per gap query — out of this cap's scope.) PREFLIGHT: `remaining = MAX -
    cumulative_discovery_calls`; if `remaining <= 0` → STOP_BUDGET; else the round may fire at most
    `floor(remaining / per_query_discovery_cost)` gap queries — TRUNCATE `gap_sub_queries` to that many so
    the round's WORST-CASE discovery spend (`fired_queries * per_query_discovery_cost`) CANNOT exceed
    `remaining`. After the round, add the WORST-CASE `fired_queries * per_query_discovery_cost` (NOT the
    undercounting observed `api_calls`) to the cumulative counter. INVARIANT (P4-14):
    `cumulative_discovery_calls <= MAX` at ALL times.
  - **Re-gate on the BILLED set each round (iter-3 P2):** every round's re-gate uses the SAME generator-visible
    `evidence_for_gen` Phase 3 certifies — i.e. AFTER the round's selection AND the V30 contract-row
    (`:2719`) + upload-row (`:2749`) injections, immediately before the generator. So the loop wraps
    retrieval → select → [V30/upload inject] → `assess_plan_sufficiency` each round, preserving the Phase-3
    billed-set invariant (the gate always certifies exactly what would be billed).
- Off-mode: the single-pass path runs unchanged (byte-identical); no loop.

### 2.3 PARTIAL report — PRUNED-PLAN generator contract (iter-1 P1 #4)
- When the loop stops at STOP_NOVELTY / STOP_BUDGET with SOME sections still under-covered, Phase 4 emits
  status `partial_saturation`. The generator fixes its output structure to `research_plan.outline`
  (`multi_section_generator.py:4098`), so passing the FULL plan would still RENDER the under-covered sections
  (the exact bug Codex flagged). FIX: build a **PRUNED ResearchPlan** containing ONLY the sufficient sections.
  **Index remap (iter-2 P2):** `ResearchPlan` is index-based (`SectionOutlineItem.sub_query_indices` point
  into `plan.sub_queries`), and the whole-plan facet-union invariant requires
  `union(retained sub_query_indices) == range(len(pruned.sub_queries))`. So the prune MUST: (1) drop the
  under-covered `SectionOutlineItem`s; (2) drop the now-ORPHANED `sub_queries` (those mapped by no retained
  section); (3) REMAP the retained sections' `sub_query_indices` to the compacted `sub_queries` list, so all
  indices stay in-range and the union invariant holds on the pruned plan. Pass THAT pruned plan to
  `generate_multi_section_report` (`run_honest_sweep_r3.py:3012`). So the generator structurally CANNOT
  render an under-covered SECTION. The manifest names the dropped sections + their shortfall + the
  `partial_saturation` status.
- **Disable EVERY out-of-plan generator addition in partial mode (iter-4/5 P1 #1 — EXHAUSTIVE):** the pruned
  plan controls `research_plan.outline`, but the report assembly ALSO appends content OUTSIDE the plan that
  the prune does not reach. In `partial_saturation` mode a single `partial_mode` flag MUST DISABLE ALL of
  these out-of-plan appenders (a fixture that would otherwise trigger each must produce NONE):
  - V30 contract-plan sections (`multi_section_generator.py:4167`, fed from `run_honest_sweep_r3.py:3002`);
  - M50 per-trial summary appendices (`run_honest_sweep_r3.py:3073`, `multi_section_generator.py:5177`);
  - the `### Trial Summary` + timeline (`run_honest_sweep_r3.py:3057`, builder `multi_section_generator.py:4972`);
  - the `## Analyst Synthesis` (`run_honest_sweep_r3.py:3190`, generator-side `multi_section_generator.py:4998`);
  - the `### Limitations` (`run_honest_sweep_r3.py:3199`, builder `multi_section_generator.py:5034`).
  So the FINAL RENDERED report's headings == ONLY the pruned sufficient sections — NO out-of-plan content for
  an under-covered topic. (PROCEED/full mode is UNCHANGED — all of these still render.) Smoke P4-7c uses a
  fixture that would otherwise trigger Trial Summary + Analyst Synthesis + Limitations + V30 + M50, and
  asserts the partial report's headings equal exactly the pruned plan's sections.
- **Money rule (iter-1 P2 — exact wording):** the generator is billed EXACTLY when the final verdict is
  PROCEED (full plan) OR `partial_saturation` (pruned plan = sufficient sections ONLY) — NEVER on an
  under-covered section. If ZERO sections are sufficient → `abort_corpus_inadequate`, no generator bill.
- **Status taxonomy registration (iter-3 P1 #2):** `partial_saturation` is a NEW manifest status — it MUST
  be registered in the runner's known-status set + summary mapping (`run_honest_sweep_r3.py:173`,`:194`) AND
  the regression-lab status mirror (`audit_ir/regression_lab.py:589`) AND the taxonomy-drift guard
  (`tests/polaris_graph/test_md9_regression_lab.py:280`) is updated to include it — else a partial run
  surfaces as unknown/error downstream or breaks the drift test.

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4) — `tests/polaris_graph/retrieval/test_saturation_phase4.py`
- **P4-1 OFF byte-identity:** off → the single-pass retrieval path is unchanged (no loop); pin the existing
  retrieval-trace shape on a fixture.
- **P4-2 novelty metric:** `marginal_novelty` returns 1.0 for all-new, 0.0 for all-duplicate, 0.5 for half.
- **P4-2b identifier-vs-tracking canonicalization (iter-2 P2):** two rows with `?abstract_id=123` and
  `?abstract_id=456` (same host+path) are DISTINCT (both novel); two rows differing only by `?utm_source=x`
  collapse to ONE (the second is a duplicate). Uses the run_diff canonicalizer.
- **P4-3 gap_sub_queries:** an under-covered section mapped to sub-queries [2,4] with facet 4 under-covered →
  returns exactly `[plan.sub_queries[4]]` (the gap facet's text), NOT the whole plan.
- **P4-4 saturation_decision:** proceed→STOP_SUFFICIENT; expand+rounds-exhausted→STOP_BUDGET; expand+round≥1
  +novelty<eps→STOP_NOVELTY; expand+rounds-left+novelty≥eps→CONTINUE.
- **P4-5 loop convergence (the EXIT — findings-per-round flattens):** drive the loop with a STUB retrieval
  that returns decreasing novel rows per round (round0: 5 new, round1: 3 new, round2: 0 new); assert the
  loop STOPS at STOP_NOVELTY when novelty < eps, and the findings-per-round curve flattens (round novelty
  monotonically decreasing to < eps). NO live client constructed.
- **P4-6 gap-closure stop:** stub retrieval that CLOSES the gap on round 1 → STOP_SUFFICIENT → generator
  billed once (spy: generator called exactly once, on PROCEED).
- **P4-7 partial report:** stub where section A stays covered, section B never closes after max_rounds →
  status `partial_saturation`, generator billed ONLY for section A, section B named in the shortfall.
- **P4-8 budget bound:** the loop never exceeds `PG_SATURATION_MAX_ROUNDS`; hitting the cap = STOP_BUDGET.
- **P4-9 spend-free guard:** no live HTTP client constructed in the decision-logic smoke.
- **P4-10 gap-round anchor-suppressed BOTH seams (iter-2 P1):** a gap round with `anchor_seed=False` → the
  effective query list at the CORE Serper/S2 seam AND at the need-type adapters (`run_need_type_backends`) is
  EXACTLY `gap_sub_queries`; the `research_question` anchor is NOT in EITHER (assert adapter-level queries
  too). USE >3 GAP QUERIES (iter-4 P2 — the need-type adapter caps amplified to 3 at `domain_backends.py:650`;
  >3 pins that gap rounds aren't silently truncated to 3 + that the cap is lifted/bypassed for gap rounds).
  ALSO `anchor_seed=False` must defeat the scope-validator anchor reinsertion (`scope_query_validator.py:182`
  `always_keep_anchor`) — a gap round passes `always_keep_anchor=False` so the validator does not re-add the
  research_question.
- **P4-11 total-shortfall gap queries (iter-1 P1 #2):** an under-covered section with `covered_count <
  evidence_target` but `empty_facets == []` → `gap_sub_queries` returns ALL the section's sub-query texts
  (non-empty), so the loop has a query to fire.
- **P4-12 abort → STOP_BUDGET (iter-1 P1 #3):** `saturation_decision(verdict="abort", ...)` → STOP_BUDGET
  (terminal, never unhandled).
- **P4-13 global evidence_id renumber (iter-1 P1 #5):** merging round-1 rows (`ev_000..`) with round-2 rows
  (also `ev_000..`) renumbers so the cumulative pool has globally-unique ids (no overwrite); the merged
  count == sum of round counts (after canonical-URL dedup).
- **P4-14 cumulative retrieval budget NEVER exceeded (iter-3 P1):** drive a loop where rounds spend N
  api_calls each; assert `cumulative_calls <= PG_SATURATION_MAX_RETRIEVAL_CALLS` at EVERY step (pre-spend
  truncation/refusal), and STOP_BUDGET fires when remaining hits 0 — even if `max_rounds` is not reached. A
  round is truncated/refused so it can NEVER push cumulative over the cap.
- **P4-15 partial_saturation taxonomy (iter-3 P1 #2):** `partial_saturation` is in the runner known-status
  set + summary map + regression_lab mirror; the md9 taxonomy-drift test passes WITH it registered (a partial
  run does not surface as unknown/error).
- **P4-16 re-gate on billed set (iter-3 P2):** each round's gate is assessed on the post-V30/upload
  `evidence_for_gen` (the billed set), preserving the Phase-3 invariant across rounds.
- **P4-7 strengthened (pruned plan, iter-1 P1 #4):** the generator receives a PRUNED plan whose outline
  contains ONLY the sufficient sections — the under-covered section is NOT in the plan passed to
  `generate_multi_section_report` (structurally cannot be rendered).
- **P4-7c partial-mode out-of-plan disabled EXHAUSTIVE (iter-5 P1 #1):** a fixture that would otherwise emit
  Trial Summary + Analyst Synthesis + Limitations + V30 contract sections + M50 appendices → in
  `partial_saturation` mode the rendered report's headings == EXACTLY the pruned sufficient sections (none of
  the five out-of-plan appenders fire); PROCEED/full mode still emits them.
- **P4-7b pruned-plan index remap invariant (iter-2 P2):** after pruning, the pruned plan's orphaned
  sub_queries are dropped, the retained sections' sub_query_indices are REMAPPED to the compacted
  sub_queries, ALL indices are in-range, and `union(sub_query_indices)==range(len(pruned.sub_queries))` holds
  (the pruned plan re-passes the Phase-3 fail-closed facet-union validation).
- Plus a regression subset confirming OFF single-pass byte-identity.

## 4. EXIT CRITERIA (issue #988)
On-mode, the saturation loop fires gap-targeted rounds for under-covered sub-questions, the findings-per-round
curve FLATTENS, and the loop STOPS on gap-closure OR marginal-novelty < ε (ε validated) OR budget → a partial
report naming the uncovered sub-questions (via a PRUNED plan, structurally excluding them); gap rounds fire
ONLY the gap sub-queries (anchor-suppressed); evidence_ids globally unique across rounds; cumulative
retrieval spend bounded (not just round count); OFF single-pass byte-identical; zero generator tokens until
PROCEED/partial; all smoke green; spend-free build.

## 5. WHAT I HAVE ALSO CHECKED
- Phase 3 gate (`:2776-2819`) returns `under_covered_units` + per-unit per-facet shortfall — the exact input
  `gap_sub_queries` needs.
- `run_live_retrieval(amplified_queries=...)` (`:1676`) already accepts an amplified-query list (Phase 1/2
  wiring) — the gap round reuses it with the gap sub-queries.
- `PG_PLAN_SUFFICIENCY_MAX_ROUNDS` is the Phase-3 hook Phase 4 drives (rename/alias to PG_SATURATION_MAX_ROUNDS).

## 6. REVIEW QUESTIONS FOR CODEX
1. Is the novelty metric (fraction of new rows that are non-duplicate, canonical-URL dedup) the right
   "marginal-novelty < ε" signal, vs a finding/number-level dedup? Is ε default 0.10 sound?
2. Is gap-targeted re-query (only the under-covered facets' sub-queries) correct, vs re-running all
   sub-queries? Could a gap facet be genuinely un-closable (no such evidence exists) → STOP_NOVELTY is the
   honest stop?
3. Is the PARTIAL report (bill only the sufficient sections, name the uncovered ones) the right honest
   behavior, vs aborting? Does it preserve the money rule (no generator bill on uncovered sections)?
4. Is "decision logic pure + smoke-tested, live retrieval round live-only" the right spend-free boundary?
5. Scope: is the loop the right Phase-4 boundary, with relevance-floor/dedup (Phase 5) + domain-general
   sections (Phase 6) still separate?

APPROVE iff the acceptance criteria are correct, the saturation loop closes gaps / stops honestly on
novelty/budget, the money rule (no generator bill until PROCEED/partial) holds, and OFF stays byte-identical.
This is the build contract.
