## Codex DIFF review brief — I-bug-946 (#932) per-role provider routing

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (bound)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context

You APPROVE'd choice C iter 2 with 5 P2 items on the brief at `.codex/I-bug-946/brief_iter2.md`. Diff implements them all.

## Test results

121 PASS across `tests/dr_benchmark/` + `tests/polaris_graph/llm/` (full pathB + entailment surface). Run:
```
python -m pytest tests/dr_benchmark/ tests/polaris_graph/llm/ -x -q --ignore=tests/polaris_graph/anti_sycophancy --ignore=tests/polaris_graph/benchmark
```
Other pre-existing test files fail at collection on `ModuleNotFoundError: 'polaris_graph'` (NOT related to this diff — same on main).

`tests/dr_benchmark/test_pathB_run_gate.py` 40/40 PASS in 0.68s (suite remains hermetic — no live HTTP).

## What the diff does

### 1. `scripts/dr_benchmark/pathB_run_gate.py` (+80 LOC)
- Adds `resolve_role_provider(model_slug, provider_order) -> str`. Calls `GET /api/v1/models/<id>/endpoints`. Parses `data.endpoints` (Codex P2#2). Filters to status==0 or status absent (Codex P2#4). Intersects case-insensitive (Codex P2#3). Returns catalog-cased provider name of first match in provider_order. Raises GateError on empty endpoints OR no intersection (fail closed).
- `preflight()`: removed strict singleton check on `OPENROUTER_PROVIDER_ORDER`. New rule: non-empty list. Per-role: if `rp.provider_name` empty AND not offline, populated via `resolve_role_provider`. Enforces `PG_ENTAILMENT_MODEL == PG_EVALUATOR_MODEL` when both set (Codex iter-2 P2#3).

### 2. `src/polaris_graph/benchmark/pathB_capture.py` (+41 LOC)
- New `_ROLE_PROVIDER` ContextVar (Codex iter-2 P2#1 — ContextVar precedent already in this file with `_ROLE`/`_SINK`/`_RETRIEVAL`; Codex iter-2 P2#2 — lives in src, not scripts).
- New `set_role_providers(mapping)` / `reset_role_providers(token)` / `current_role_provider() -> str | None`. The last reads BOTH `_ROLE_PROVIDER` mapping AND `_ROLE` to return the provider for the current role.
- `clear_pathB_capture()` also resets `_ROLE_PROVIDER` to None.

### 3. `src/polaris_graph/benchmark/pathB_runner.py` (+12 LOC)
- `gate_around_question()`: after preflight + pin persistence, builds `role_to_provider` mapping from the resolved pin and calls `_capture.set_role_providers(...)`. Token reset on exception path; `clear_pathB_capture()` handles happy-path cleanup.

### 4. `src/polaris_graph/llm/openrouter_client.py` (+13 LOC at :1399-1414)
- Reads `_pathb_capture.current_role_provider()`. If non-None (gate active + role matches mapping), forces `provider_block["order"] = [resolved]` (singleton) + `allow_fallbacks=False`. Otherwise uses env-driven path unchanged.

### 5. `src/polaris_graph/llm/entailment_judge.py` (+30 LOC at :160-200)
- Direct httpx body now includes `provider: {order: [resolved], allow_fallbacks: false, require_parameters: true}` when gate is active. P1#2 from iter-1 brief addressed.
- Lazy import of pathB_capture inside the try so off-mode runs pay zero cost.

### 6. `tests/dr_benchmark/test_pathB_run_gate.py` (+144 LOC, 40 total tests)
- 11 new tests covering: resolver happy path, no-intersection fail-closed, degraded-endpoint skip, empty endpoints, case-insensitivity + catalog spelling, missing-status-treated-eligible, per-role-pin flow, multi-provider acceptance (replaces old singleton-rejection test), empty-order rejection, divergent-entailment-model fail, ContextVar set/get/reset roundtrip.
- Removed obsolete `test_preflight_fatal_on_multi_provider` — superseded by `test_preflight_accepts_multi_provider_post_i_bug_946` (semantic change is intentional per I-bug-946; comment explains).

## Files I have ALSO checked and they're clean

- `scripts/dr_benchmark/score_run.py:51` — pin consumer; provider_name flows through additively.
- `scripts/dr_benchmark/aggregate_systems.py:149,153` — final-report rendering; additive.
- `src/polaris_graph/llm/live_judge.py` — uses OpenRouterClient (gets routing override via #4); no direct httpx.
- `src/polaris_graph/evaluator/run_external_evaluation.py` — rule-only in this sweep, no LLM call (Codex iter-2 P2#4 confirmed).
- `scripts/run_honest_sweep_r3.py:2296,2921,2947` — existing `set_role` calls remain correct.

## Verification chain

- I-bug-944 (provider case): regression `test_post_run_passes_on_provider_case_difference` PASS.
- I-bug-945 (canonical_slug): 5 regressions PASS (test_resolve_canonical_slug_* + test_preflight_persisted_pin_includes_canonical_slug).
- I-bug-946 (per-role provider): 11 new regressions PASS.
- ContextVar precedent: `_SINK`/`_ROLE`/`_RETRIEVAL` pattern; `_ROLE_PROVIDER` follows the same lifecycle.
- Offline tests preserved: existing offline=True tests now skip resolver (Codex iter-2 P2#5); the only new test that exercises the resolver mocks `requests.get`.

## Required from Codex

Review against §-1.1 (clinical-grade pre-registration integrity) and the 5 P2 items from your iter-2 brief APPROVE.

Hand me APPROVE with `convergence_call: accept_remaining` so I can commit + push + relaunch smoke #16.
