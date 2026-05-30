## Codex DIFF review brief — I-bug-946 (#932) per-role provider routing — iter 2

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

## Iter 1 verdict (REQUEST_CHANGES)

You caught 2 real P1 blockers and 2 P2. All 4 addressed below.

### P1#1 — _role_pins env-first-entry bypass — FIXED

`src/polaris_graph/benchmark/pathB_runner.py:_role_pins()` now passes `provider_name=""` for both roles. `scripts/dr_benchmark/pathB_run_gate.py:preflight()` now ALWAYS calls `resolve_role_provider()` when `not offline` — the previous `if not rp.provider_name:` guard is removed. The persisted pin's `provider_name` is the resolver's catalog-cased output for each role. Offline tests pre-inject `provider_name` directly (the offline path skips the resolver entirely — `if not offline:`).

### P1#2 — entailment judge ambient-role bug — FIXED

`src/polaris_graph/benchmark/pathB_capture.py` adds `get_role_provider(role: str) -> str | None` — explicit-role lookup, does NOT read ambient `_ROLE`. `src/polaris_graph/llm/entailment_judge.py:166-184` now calls `get_role_provider("evaluator")` explicitly. Behavior: even when entailment fires under `_ROLE=='generator'` (in-generation provenance verification), the JSON body's `provider.order` resolves to the evaluator's pin.

### P2#1 — online preflight regression test — ADDED

`test_preflight_online_resolves_per_role_distinct_providers` — sets `OPENROUTER_PROVIDER_ORDER=fireworks,novita`, mocks `requests.get` to return distinct endpoint lists per model (Fireworks for deepseek-v4-pro, Novita for gemma), and asserts the persisted pin has `provider_name == "Fireworks"` for generator and `"Novita"` for evaluator. This is the exact smoke-#15 scenario in unit form.

### P2#2 — effective-value entailment check — STRENGTHENED

`preflight()` now compares EFFECTIVE values: `eff_entail = PG_ENTAILMENT_MODEL or _DEFAULT_ENTAILMENT_MODEL`; `eff_eval = PG_EVALUATOR_MODEL or _DEFAULT_EVALUATOR_MODEL`. Fails closed when `eff_entail != eff_eval`, including the case where ONLY PG_ENTAILMENT_MODEL is set divergently. Regression: `test_preflight_fatal_when_only_entailment_model_diverges`.

## Test results

43/43 PASS in `tests/dr_benchmark/test_pathB_run_gate.py` (1.18s, suite hermetic). Run:
```
python -m pytest tests/dr_benchmark/test_pathB_run_gate.py -x -q
```

3 new tests since iter-1 review (40 → 43):
- `test_preflight_online_resolves_per_role_distinct_providers` (P1#1 + P2#1)
- `test_preflight_fatal_when_only_entailment_model_diverges` (P2#2)
- `test_get_role_provider_explicit_lookup_ignores_ambient_role` (P1#2)

## Changed files since iter 1

- `src/polaris_graph/benchmark/pathB_runner.py:52-66` — `provider_name=""` for both roles
- `scripts/dr_benchmark/pathB_run_gate.py:213-225` — drop empty-name guard; always resolve when online
- `scripts/dr_benchmark/pathB_run_gate.py:227-237` — effective-value entailment check
- `src/polaris_graph/benchmark/pathB_capture.py:108-128` — new `get_role_provider(role)` explicit lookup; `current_role_provider()` doc updated
- `src/polaris_graph/llm/entailment_judge.py:172-181` — calls `get_role_provider("evaluator")` explicitly
- `tests/dr_benchmark/test_pathB_run_gate.py` — +3 regressions

## Required from Codex (iter 2)

Confirm both P1 fixes are correct + the test coverage proves them.

Hand me APPROVE with `convergence_call: accept_remaining` so I can commit + push + relaunch smoke #16.
