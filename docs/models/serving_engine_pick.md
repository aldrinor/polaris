# POLARIS serving engine — locked pick (I-cd-007, GH#639)

**Decision:** **vLLM** is the locked serving engine for both boxes — generator
(DeepSeek V4 Pro on Box 1 = 8×H200) and evaluator (Llama 4 Maverick INT4 on
Box 2 = 4×H100). Per-role SGLang contingencies + TensorRT-LLM as a direct
backend fallback are documented below, with empirical triggers resolved at
I-cd-011 (FP4 hardware spike).

Codex brief review: iter 1 RC → **iter 2 APPROVE**. iter 1's "SGLang for
both" was overconfident — no 2026 source confirmed SGLang + Maverick + INT4
+ exactly 4×H100, while vLLM V1 has automatic prefix caching and
`structured_outputs` with xgrammar/guidance, tempering SGLang's iter-1
"category" advantages.

## Why vLLM (primary)

- **Most-deployed open-source serving engine** — battle-tested at scale for
  trillion-class MoE (multi-year DeepSeek-V3 deployment) and for Llama
  405B-class INT4 on H100 (multi-year AWQ/GPTQ track record).
- **Already wired in `src/providers/llm_provider.py`** (`VLLM_BASE_URL`,
  `VLLM_MODEL`, `VLLM_API_KEY`) — I-cd-009 only needs model + URL config
  updates, no engine swap.
- **vLLM 0.20.0+ documents DeepSeek V4 Pro on 8×H200** with native FP4+FP8
  weights, 800K context cap (per Codex iter-2 P2 source:
  `recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Pro`). The Box-1 generator path is
  source-confirmed.
- **Per Codex iter-1 P2 corrections:** vLLM V1 has automatic prefix caching
  (not "no prefix cache" as iter-1 framed) AND `structured_outputs` with
  xgrammar/guidance — SGLang's KV-cache and structured-output edges are real
  ergonomic wins but not category-defining.
- **Operational simplicity** — single engine across both boxes = single
  monitoring stack, single ops playbook, single failure-mode surface, single
  upgrade path.

## The unverified runtime risk (resolved at I-cd-011)

**Neither vLLM nor SGLang has a source-confirmed Llama 4 Maverick + INT4 +
exactly 4×H100 recipe in 2026 public docs.** vLLM/Red Hat validates Maverick
**FP8** (~400GB, doesn't fit 4×H100=320GB); SGLang docs target Maverick on
8×H100/H200. Both engines need empirical verification of a community AWQ /
GPTQ-INT4 quant of Maverick on exactly 4×H100. I-cd-011 (#641, FP4 readiness
spike, ~$400 GPU) does this verification.

If I-cd-011 confirms vLLM Maverick INT4 on 4×H100 works, the lock holds.

## I-cd-011 contingency branches (per-role swaps if empirical fails)

**Box 1 (Generator, DeepSeek V4 Pro, 8×H200) — swap to SGLang if:**
- vLLM's native FP4+FP8 V4 Pro on 8×H200 path empirically fails at I-cd-011 —
  benchmark failure, instability, or throughput materially below an SGLang
  FP4 V4 Pro path (per Codex iter-2 P2: the trigger is empirical failure,
  not merely "no FP4 path" — vLLM has FP4).
- In that case: SGLang on Box 1 (V4 Pro FP4 documented), vLLM stays on
  Box 2 (per-role split).

**Box 2 (Evaluator, Llama 4 Maverick INT4, 4×H100) — swap to SGLang if:**
- vLLM Maverick INT4 on 4×H100 cannot be made to work at I-cd-011, AND
  SGLang Maverick INT4 on 4×H100 CAN be made to work (per Codex iter-2 P2's
  symmetric branch).
- In that case: SGLang on Box 2, vLLM stays on Box 1.

**Model-side hard fallback (already locked at I-cd-005):** if Maverick INT4
cannot be made to fit on 4×H100 via ANY tested engine, fall back to
`meta-llama/Llama-3.1-405B-Instruct` + AWQ/GPTQ-INT4 on vLLM — the
most-mature path in the industry. This is the safety net.

**Direct-backend fallback (Codex iter-2 P2):** NVIDIA TensorRT-LLM is a
real direct-backend candidate if vLLM AND SGLang both miss I-cd-011 targets
on either box. Not the same as the Dynamo wrapper (which RUNS vLLM /
SGLang / TensorRT-LLM backends). Worth tracking as the third engine option;
not in scope for this lock.

## Per-engine state recorded (2026, Codex web-verified)

| Dimension | vLLM | SGLang |
|---|---|---|
| First released | 2023-06 | 2024-01 |
| Production at trillion-class MoE | Multi-year DeepSeek-V3 | Rapidly growing |
| Prefix caching | vLLM V1 automatic prefix caching | RadixAttention (shared-prefix edge for batched scoring) |
| Structured outputs | `structured_outputs` with xgrammar/guidance | First-class DSL + xgrammar |
| DeepSeek V4 Pro | 0.20.0+: 8×H200, native FP4+FP8, 800K context | 8×H200 FP4 OR 16×H200 FP8 |
| Llama 4 Maverick | Red Hat validates FP8 (doesn't fit 4×H100); INT4 path = I-cd-011 empirical | Documented on 8×H100/H200; INT4 on 4×H100 = I-cd-011 empirical |
| INT4 (AWQ/GPTQ) on H100 | Mature, multi-year | Supported, newer |
| OpenAI-compatible API | Yes | Yes |

## NVIDIA Dynamo (deferred decision)

A 2026 distributed-serving orchestration wrapper that runs vLLM, SGLang, or
TensorRT-LLM backends. Worth tracking for any post-Carney distributed-serving
expansion. Not relevant to this lock — the per-box single-engine choice is
what matters here.

## What this lock does NOT do

- **Engine wiring** — I-cd-009 (#624) updates `src/providers/llm_provider.py`
  + `.env` with the picked engine + model URLs.
- **FP4 / INT4 hardware spike** — I-cd-011 (#641, ~$400 GPU) is the
  empirical verification gate.
- **GPU topology confirm + capacity probe** — I-cd-008 (#640).

## Constraints reaffirmed (operator-locked, non-Codex-negotiable)

1. Two boxes: Box 1 = 8×H200 (generator), Box 2 = 4×H100 (evaluator).
2. Two-family segregation enforced by
   `src/polaris_graph/llm/openrouter_client.py:check_family_segregation`.
3. Open-weight, self-hosted on Canadian or EU GPU.
4. Quality + INT4/FP4 weight residency + operational simplicity.
5. Engine maturity at the trillion-class MoE serving scale.
