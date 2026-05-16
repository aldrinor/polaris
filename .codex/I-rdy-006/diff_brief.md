HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-rdy-006

You are reviewing the **code diff** for Issue #502 / I-rdy-006 against its
APPROVED brief (`.codex/I-rdy-006/brief_iter4.md`, verdict APPROVE iter-4,
`boundary_ruling: ratified`, `scope_ruling: class_a_only`).

## Diff under review

`.codex/I-rdy-006/codex_diff.patch` — canonical diff `origin/polaris...HEAD`,
26 files, 113 insertions / 69 deletions, commit `304c1268`.

## What the brief authorized

Replace stale generator/evaluator model references in **pipeline-A** with
the operator-LOCKED pair: DeepSeek V4 Pro generator + Gemma 4 31B evaluator.
Stale tokens: `deepseek/deepseek-v3.2-exp`, `qwen/qwen3-8b`,
`qwen/qwen-2.5-72b-instruct`, `z-ai/glm-5.1`, prose "DeepSeek V3.2-Exp" /
"Qwen3-8B". HARD CONSTRAINT (operator-locked, not Codex-consultable): the
generator IS DeepSeek V4 Pro and the evaluator IS Gemma 4 31B — do not
propose alternatives.

## Changes (all single-line, mechanical, behavior-preserving)

- **Runtime defaults:** `openrouter_client.py` OPENROUTER_MODEL,
  `generator2/real_completion.py` load_config fallback, `transparency.py`
  `/transparency` evaluator_models fallbacks, `analyst_synthesis.py` model
  default, `sentence_repair.py` ×2, `disambiguation_route.py`, `deploy.sh`,
  `.env.example`.
- **Docstrings / comments only:** `live_qwen_judge.py`,
  `live_deepseek_generator.py`, `multi_section_generator.py`,
  `hallucination_detector.py`, `model_pin.py`, `evaluator_gate.py`,
  `__init__.py` ×2.
- **Docs current-state claims:** `architecture.md`, `README.md`,
  `ground_rules.md`, `docs/runbook.md`, `docs/transparency.md`.
- **Sweep-script log/header strings:** `run_honest_sweep_r3.py`,
  `run_live_honest_cycle.py`, `run_honest_on_prerebuild_corpus.py`.
- **Tests:** NEW `tests/v6/test_transparency_model_fallback.py` (default
  pair + env-override); `test_real_completion.py` default-model assertion
  updated to track the `real_completion.py` fallback change.

## Verification already run

- `pytest` (new test + test_real_completion.py): **28 passed**.
- Import smoke (transparency, openrouter_client, real_completion,
  disambiguation_route): **OK**.

## Two deliberate exclusions — please rule explicitly

1. **`carney_delivery_plan_v6_2.md:439` NOT touched.** It is a historical
   reconciliation-log entry; its real staleness is the wholesale-superseded
   OVH/8×H200/V4-Flash hardware path (superseded by #486 sovereign pivot).
   Fixing only the model token would leave a more-misleading half-stale
   line. Claude's call: out of this config-alignment issue's scope; belongs
   to a carney-doc issue. **Rule: agree (out of scope) or REQUEST_CHANGES.**
2. **Class B identifiers NOT renamed** — `evaluator_gate.py` `qwen_*` symbol
   names, `live_qwen_judge.py` module filename, `qwen_judge_output.json`
   artifact name. Identifier/filename renames carry call-site + artifact-
   consumer churn risk; carved to a follow-up issue. **Rule: agree or
   REQUEST_CHANGES.**

## Review focus

1. Each runtime-default change: is `deepseek/deepseek-v4-pro` /
   `google/gemma-4-31b-it` the correct token, and does no downstream
   registry/cost-table/family-segregation path KeyError on it?
2. Any stale model reference in the 26 files MISSED (still says V3.2-Exp /
   Qwen3-8B / glm-5.1 / qwen-2.5-72b after the diff)?
3. Two-family segregation invariant (CLAUDE.md §9.1.1): generator family
   `deepseek` ≠ evaluator family `gemma` — still holds?
4. Are the two exclusions above defensible, or a real gap?

## Output schema (bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
