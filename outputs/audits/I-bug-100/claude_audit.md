# I-bug-100 Claude architect audit

## Issue
GH#354 — Route entailment-judge calls through OpenRouterClient cost-tracking infrastructure.

## Codex review trajectory
- Brief iter-1: REQUEST_CHANGES (3 P1: budget-cap mechanics / ledger schema / impute signature). All fixed in iter-2 brief.
- Brief iter-2: REQUEST_CHANGES (2 P1: ledger-path module-ref pattern / PG_MAX_COST_PER_RUN attribute rebind). All fixed in iter-3 brief.
- Brief iter-3: REQUEST_CHANGES on grounds "code not yet written" — force-APPROVE per §8.3.1 (iter-3 P1s were "implement the brief", not design issues).
- Diff iter-1: REQUEST_CHANGES, 1 P1 (src-namespace mismatch — production uses src.polaris_graph.llm.X, this used polaris_graph.llm.X — separate sys.modules with separate ContextVars), 1 P2 (zero-cost when usage block absent).
- Diff iter-2: **APPROVE**, 0 P0/P1/P2, accept_remaining.

## Architectural review
- Cost tracking: `_orc._add_run_cost(actual_cost)` → `_orc.check_run_budget(0)` raises BudgetExceededError. Re-raised explicitly before broad fail-open `except Exception`.
- Ledger schema: matches `OpenRouterClient._append_ledger` verbatim (timestamp, session_id, call_type, input_tokens, output_tokens, reasoning_tokens, duration_ms, cost_usd, cumulative_cost_usd). `scripts/run_honest_sweep_r3.py:276` per-run filter by session_id now sees judge entries.
- src-namespace canonicalization: imports use `src.polaris_graph.llm.openrouter_client` matching the production sweep, so judge ContextVar state IS the sweep ContextVar state.
- Fallback when usage absent: imputed cost on (500, 100) tokens at model rate. Budget cap is preserved on degraded responses.
- Family-segregation invariant (§9.1.1): preserved (also via src-namespace import).

## Tests
71/71 pass (66 baseline + 5 new: api-cost-present, api-cost-absent-imputed, src-namespace-shared-state, usage-block-absent-fallback, budget-exceeded-raises).

## Verdict
**SHIP.**
