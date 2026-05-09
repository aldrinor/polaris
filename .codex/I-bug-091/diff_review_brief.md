# Codex Diff Review — I-bug-091 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- DO NOT call exec / rg.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- Brief APPROVE'd iter 1.
- Diff: `.codex/I-bug-091/codex_diff.patch` (canonical-diff-sha256: `1e4e7ee2baa6f1a24a3cf9b0458be1cb207e6d79d5af1f510239103d14a0f8bc`)
- Files:
  - `src/polaris_graph/llm/openrouter_client.py:255-258`: revert default `PG_GENERATOR_MODEL` to `deepseek/deepseek-v3.2-exp` + 13-line docstring explaining the empirical revert.
  - `.env.example:59,67`: matching `PG_GENERATOR_MODEL` and `OPENROUTER_DEFAULT_MODEL`.

## Constraints

1. Tests: 19/19 pass. The `test_v4_pro_passes_two_family_segregation` regression continues to pass — V4 Pro registry membership unchanged, just no longer default.
2. Two-family invariant unchanged: `deepseek/deepseek-v3.2-exp` (deepseek family) + `google/gemma-4-31b-it` (gemma family) still pass `check_family_segregation()`.
3. Budget-guard invariant unchanged: V3.2-Exp uses generic `"deepseek/"` price tier `(0.27, 0.38)` per `_PRICE_TABLE_USD_PER_M`.
4. CHARTER §3 LOC: ~3 src LOC + 13 docstring LOC + 2 .env.example lines.
5. §9.4 hygiene clean.
6. Architectural infrastructure preserved: I-bug-088 + I-bug-089 + I-bug-090 stack remains active and protects against ANY reasoning-first generator if user opts back to V4 Pro via env var.
7. V4 Pro remains accessible via `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro` env override. The `_REASONING_FIRST_MODELS` registry, the 6000 floor, and the response-shape-centric recovery still work for V4 Pro.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: []
```
