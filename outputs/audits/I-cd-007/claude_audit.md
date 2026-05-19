# I-cd-007 — Claude architect audit

**Issue:** GH#639 — SGLang vs vLLM serving-engine bakeoff.
**Deliverable:** `docs/models/serving_engine_pick.md` — vLLM locked for both
boxes, per-role SGLang contingencies + TensorRT-LLM direct-backend fallback
documented, I-cd-011 empirical-verification triggers explicit.

## What this PR ships

- `docs/models/serving_engine_pick.md` (NEW, 108 LOC).

## Decision

**vLLM for both boxes** (Box 1 generator DeepSeek V4 Pro on 8×H200; Box 2
evaluator Llama 4 Maverick INT4 on 4×H100).

## Codex trajectory

Brief: iter 1 RC (1 P1 — SGLang + Maverick + INT4 + 4×H100 not
source-verified; pivoted recommendation from iter-1's "SGLang for both" to
vLLM-primary; 4 P2 corrections folded in) → iter 2 APPROVE (3 P2
clarifications folded into the doc).

Key iter-1 findings (Codex web-verified):
- vLLM/Red Hat validates Maverick FP8 only (doesn't fit 4×H100=320GB).
- SGLang docs Maverick on 8×H100/H200 (not 4×H100).
- vLLM V1 has automatic prefix caching (not "no prefix cache" as iter-1
  framed) + `structured_outputs` with xgrammar/guidance.
- vLLM 0.20.0+ documents DeepSeek V4 Pro on 8×H200 with native FP4+FP8.
- NVIDIA Dynamo runs vLLM/SGLang/TensorRT-LLM backends (a wrapper, not a
  replacement); TensorRT-LLM is a real direct-backend option.

## Scope discipline

Lock only. Engine wiring is I-cd-009 (#624); FP4 hardware spike is I-cd-011
(#641); GPU topology is I-cd-008 (#640). The doc documents per-role swap
triggers for I-cd-011 so the FP4 spike has unambiguous criteria.

## Risk surface

- The Maverick INT4 + 4×H100 runtime question is NOT resolved in this PR;
  it's deferred to I-cd-011 (correctly — this issue is "engine chosen,"
  not "engine verified on hardware"). The lock holds vLLM as primary; per-
  role SGLang and model-side Llama 3.1 405B fallbacks are explicit.
- vLLM is already wired in `src/providers/llm_provider.py` → I-cd-009 is
  config-only, no engine-swap cost. If we had locked SGLang, I-cd-009 would
  also need to swap the engine in code.

## Codex P2 dispositions (all folded into the doc)

1. Symmetric SGLang-for-Box-2 contingency branch added.
2. vLLM V4 Pro contingency trigger tightened (benchmark failure /
   instability / unacceptable throughput, not "no FP4 path" — vLLM has
   native FP4+FP8).
3. TensorRT-LLM as direct-backend fallback recorded (separate from Dynamo
   wrapper note).
