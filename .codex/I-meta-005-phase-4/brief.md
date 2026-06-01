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

# Codex BRIEF gate — I-meta-005 Phase 4 (#988): multi-round saturation search

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
  are NOVEL (not a duplicate of an already-seen row). Dedup key = canonical URL (eTLD+1 + path) AND/OR the
  finding/number asserted (reuse the existing dedup primitive if one exists; else canonical-URL). Returns
  `len(novel) / max(1, len(new_round_rows))`.
- `gap_sub_queries(sufficiency_report, plan) -> list[str]`: the sub-query TEXTS for the under-covered
  facets — `{plan.sub_queries[i] for section in under_covered for i in section.sub_query_indices where the
  facet is under min_per_facet}`. These are the ONLY queries the next round fires (gap-targeted, not a blind
  re-run). Field-agnostic — derived from the plan, no domain.
- `saturation_decision(*, verdict, round_index, max_rounds, novelty, eps) -> Decision` where Decision ∈
  {CONTINUE, STOP_SUFFICIENT, STOP_NOVELTY, STOP_BUDGET}:
  - verdict == proceed → STOP_SUFFICIENT (gap closed).
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
    - CONTINUE → fire round N+1: `run_live_retrieval(amplified_queries=gap_sub_queries(...), ...)`, MERGE
      the new rows into the cumulative corpus (dedup), re-select, re-gate; track `novelty` vs the prior
      cumulative corpus; increment `round_index`.
  - `PG_SATURATION_MAX_ROUNDS` (default e.g. 3) bounds the rounds; `PG_SATURATION_NOVELTY_EPS` (default e.g.
    0.10) is ε. Each round respects the existing per-run retrieval budget cap (the loop cannot exceed it;
    hitting the cap = STOP_BUDGET).
- Off-mode: the single-pass path runs unchanged (byte-identical); no loop.

### 2.3 PARTIAL report (the honest stop — not a blind abort)
- When the loop stops at STOP_NOVELTY / STOP_BUDGET with SOME sections still under-covered, the brief #982
  row 50 says "→ partial report". Phase 4 emits status `partial_saturation`: the generator IS billed, but
  ONLY for the sections that ARE sufficient (the under-covered sections are omitted + named in the manifest
  with their shortfall). So the user gets a verified partial answer + an explicit "these sub-questions could
  not be covered" list — NOT a silent thin report, NOT a blind abort. (Confirm this is the right honest
  behavior vs aborting; the money rule still holds — the generator is billed only for covered sections.)
  - NOTE: if ZERO sections are sufficient, it remains `abort_corpus_inadequate` (nothing to bill).

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4) — `tests/polaris_graph/retrieval/test_saturation_phase4.py`
- **P4-1 OFF byte-identity:** off → the single-pass retrieval path is unchanged (no loop); pin the existing
  retrieval-trace shape on a fixture.
- **P4-2 novelty metric:** `marginal_novelty` returns 1.0 for all-new rows, 0.0 for all-duplicate, 0.5 for
  half; canonical-URL dedup (same URL different path = distinct; same URL = dup).
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
- Plus a regression subset confirming OFF single-pass byte-identity.

## 4. EXIT CRITERIA (issue #988)
On-mode, the saturation loop fires gap-targeted rounds for under-covered sub-questions, the findings-per-round
curve FLATTENS, and the loop STOPS on gap-closure OR marginal-novelty < ε (ε validated) OR budget → a partial
report naming the uncovered sub-questions; OFF single-pass byte-identical; zero generator tokens until
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
