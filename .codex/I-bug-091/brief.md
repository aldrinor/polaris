# Codex Brief — I-bug-091: revert PG_GENERATOR_MODEL default to V3.2-Exp

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- DO NOT call exec / rg.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Empirical evidence

V4 Pro upgrade (PR #337, I-bug-086) → V4 Pro+Gemma post-stack (PR #339 + #340 + #341) → live BEAT-BOTH validation:

```
Run 1 (PR #339 only — I-bug-088): aborted, V4 Pro reasoning-only, no recovery
Run 2 (PR #340 added — I-bug-089): aborted Section 1, fail-loud raised
Run 3 (PR #341 added — I-bug-090, 6000 floor): aborted Section 2,
  V4 Pro emitted 19,843 chars CoT planning with no [#ev:] markers,
  fail-loud raised at 43K-input synthesis section
```

**Pattern:** V4 Pro's CoT-style output is structurally incompatible with `multi_section_generator`'s strict_verify provenance-token requirement (`[#ev:ev_id:start-end]` per claim). The model emits long planning preludes that:
1. Often lack `[#ev:]` markers entirely
2. Exhaust max_tokens before answer-write phase
3. Get correctly fail-loud'd by I-bug-089

I-bug-090's 6000 floor partially helps (Section 1 worked) but Section 2 with 43K input ate the whole budget.

## V3.2-Exp baseline

Prior live BEAT-BOTH on V3.2-Exp + Qwen3-8B (V3.2 era):
```
5 BEAT-BOTH / 1 TIE / 1 BEHIND vs ChatGPT/Gemini DR
```
V3.2-Exp produces clean grounded prose with `[#ev:]` provenance markers. Vectara HHEM 5.3%. Proven in production.

## Plan

Revert `PG_GENERATOR_MODEL` default from `deepseek/deepseek-v4-pro` → `deepseek/deepseek-v3.2-exp`. Update `.env.example` to match. The architectural infrastructure (I-bug-088 reasoning-first recovery + I-bug-089 fail-loud + I-bug-090 token floor + I-bug-087 Gemma 4 31B evaluator) is preserved — these protect against ANY reasoning-first generator if the user opts back in via env var.

## Why not the alternative path

Path B (caller-level retry with explicit `[#ev:...]` re-prompt at multi_section_generator) would be ~30 LOC and architecturally OK, but:
- Still depends on V4 Pro reliably emitting provenance markers, which it empirically doesn't
- Adds complexity to the caller layer
- Doesn't solve the larger-input case (43K context exhausts even 6000 budget)
- Two-family invariant: V3.2-Exp + Gemma 4 31B is still cross-family (DeepSeek vs Google)

V3.2-Exp is the proven-quality, proven-pipeline-fit choice. V4 Pro stays accessible via env var.

## Files changed

- `src/polaris_graph/llm/openrouter_client.py:255-257`: default value + new docstring explaining the revert.
- `.env.example:59`: `PG_GENERATOR_MODEL=deepseek/deepseek-v3.2-exp`
- `.env.example:67`: `OPENROUTER_DEFAULT_MODEL=deepseek/deepseek-v3.2-exp`

## Tests

19/19 pass on adjacent suites (`test_reasoning_first_token_budget.py`, `test_reasoning_first_normalize.py`, `test_deepseek_v4_pricing.py`, `test_gemma_4_evaluator.py`). The `test_gemma_4_31b_passes_two_family_segregation_with_deepseek_v4_pro` test still passes — V4 Pro registry membership unchanged, just not the default.

## LOC

3 src LOC change + .env.example tweaks. Well under CHARTER §3 200-LOC cap.

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
