# I-cd-034 (#634) — scope consult

## Operator directive 2026-05-20
"For all decision, ask Codex to decide based on highest quality impact."

## Reality

Parent #516 acceptance: "matrix green on the product journey pre-cutover; CI gate live; Codex APPROVE."

The matrix (`docs/carney_handover/test_matrix.md`) has 24 rows × 11 journey stages = ~264 test surfaces. Execution requires:
1. Real OpenRouter API spend (clinical/policy/workforce/etc. real LLM calls).
2. Live deployed product (OVH VM `polaris-orchestrator` per project_polaris_already_deployed memory).
3. Probably 4-6 hours of test wall-clock + curated result recording.

This is the same operator-supervised shape as I-cd-016b (#674): real money + real deployed system.

## Options

### A. Defer to operator-action follow-up Issue + ship the runner skeleton
- New Issue I-cd-034-followup: "operator runs the 24×J matrix against polaris-orchestrator OVH VM".
- This PR ships: `scripts/run_test_matrix.py` skeleton that takes a target base URL + OpenRouter key from env, iterates the 24 rows, emits a structured results YAML. Operator runs locally with budget.
- 200-300 LOC.

### B. Author only the operator instructions (no runner)
- Update docs/carney_handover/test_matrix.md to mark "execution pending operator action" + acceptance: operator runs each row manually.
- ~30 LOC.

### C. Execute synthetic-only rows now; defer LLM-spend rows
- Some rows are unit/property tests (existing pytest matrix). Run those now; carve LLM-spend rows to follow-up.
- ~80 LOC + result recording.

## Question

Rank A/B/C by quality impact. Which option best matches the operator-supervised execution pattern + delivers real value now?
