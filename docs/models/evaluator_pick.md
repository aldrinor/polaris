# POLARIS evaluator model — locked pick (I-cd-005, GH#637)

**Decision:** `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` is the
locked I-cd-005 evaluator pick. Use with a community INT4 quant for 4×H100
weight residency. Re-visit at I-cd-011 if no working Llama 4 Maverick INT4
quant on 4×H100 can be verified empirically — in that case, fall back to
`meta-llama/Llama-3.1-405B-Instruct` (AWQ / GPTQ-INT4, the most-mature
INT4-on-H100 path).

Codex brief review: iter 1 RC → iter 2 RC → iter 3 RC → **iter 4 APPROVE**
(trajectory P1 1→1→1→0; the three iter-RCs were Codex's web-search-driven
expansion of the candidate set — Qwen3.5-397B-A17B, then 5 more MoE 400B-class
candidates, then Baidu ERNIE-4.5-VL-424B — all folded in before locking).

## Why Llama 4 Maverick (primary)

- **~400B class** — operator-locked at ~400B (the LARGEST in the class is
  MiniMax-M1 at 456B; Maverick at 400B sits squarely within the locked target).
- **Meta's current generation** (Llama 4, April 2025) — picking Llama 3.1
  405B (July 2024) in May 2026 is the obviously-older choice and was
  Codex's iter-2 P1.
- **MoE 400B / 17B active** — evaluator scores every sentence in every report,
  so per-token throughput matters. 17B active vs Llama 3.1's dense 405B active
  is a large efficiency edge.
- **Meta-published FP8 checkpoint** — `Llama-4-Maverick-17B-128E-Instruct-FP8`
  lowers quant-recipe risk vs starting from BF16 weights and building a
  community quant from scratch.
- **vLLM / SGLang documented** — confirmed by Codex's iter-2 web verification.
- **Two-family** — Meta lineage, distinct from DeepSeek V4 Pro generator.
  `openrouter_client.check_family_segregation` passes.
- **License acceptable pending I-cd-006** — Llama 4 Community license;
  headline terms operator-signed-off at I-cd-006.

**The single risk that I-cd-011 must verify before this lock is final:** a
community INT4 (AWQ / GPTQ-INT4 / community FP4) quant of Llama 4 Maverick
exists and works on 4×H100 via vLLM/SGLang. If no such quant works, the
fallback below is the safety net.

## Hard fallback (proven-deployable today)

`meta-llama/Llama-3.1-405B-Instruct` + AWQ / GPTQ-INT4. The most-mature
INT4-on-H100 path in the entire ~400B candidate set; production-deployed for
over a year. Strictly older-generation than Maverick, but if Maverick's INT4
quant ecosystem proves immature at I-cd-011, this is the safety net that keeps
the demo timeline.

## Strong alternatives — comparable class, revisit at I-cd-011

Any of these may displace the primary at I-cd-011 if it shows a better
INT4-on-H100 path AND its license / quality profile is preferred.

| HF id | License | Total / active | Note |
|---|---|---|---|
| `MiniMaxAI/MiniMax-M1-80k-hf` | Apache 2.0 | 456B / 45.9B | **Largest in class.** Strong "compute per token" within the Apache-2.0 MoE set. |
| `baidu/ERNIE-4.5-VL-424B-A47B-PT` | Apache 2.0 | 424B / 47B | Vision-language; the `-PT` suffix is **PyTorch format** (not "pre-trained" semantically) — Codex iter-4 P2 confirmed this is a Posttraining/Chat checkpoint, usable as evaluator. Baidu's text-only A47B line tops out at 300B (below class). |
| `Qwen/Qwen3.5-397B-A17B-FP8` | Apache 2.0 | 397B / 17B | Cleanest sovereignty story (Alibaba lineage, no US-origin discussion). NVIDIA's NVFP4 sibling checkpoint is Blackwell-only; on 4×H100 use Qwen's FP8 + a community INT4 quant. |
| `zai-org/GLM-4.5` | MIT | 355B / 32B | Most permissive license; FP8/BF16 published. |
| `arcee-ai/Trinity-Large-Thinking` | Apache 2.0 | 398-400B / 13B | Lowest active params in the MoE set. |
| `tencent/Tencent-Hunyuan-Large` | Tencent (custom; **EU territory limitation**, Codex iter-4 P2) | 389B / 52B | Highest active params in the MoE set. Re-verify the EU clause at I-cd-006 license sign-off. |

Note on multimodality (Codex iter-4 P2): Maverick and Qwen3.5-397B-A17B are
also multimodal artifacts — not unique to ERNIE-4.5-VL. The evaluator role is
text-only; the unused multimodal components add weight footprint but are
inactive at inference.

## Why deployment maturity is weighted over vendor benchmark numbers

Codex iter-4 P2 noted: §C.2 of the brief did not rank MoE candidates by proxy
benchmarks because **no candidate publishes comparable RAGTruth / FEVER / RAGAS
/ TriviaQA-RAG numbers** — every candidate's headline scores are
vendor-reported on MMLU-Pro / IFEval / AlpacaEval-2 / Arena-Hard, with no
common independent RAG-faithfulness reproduction.

Given that, the I-cd-005 lock weights **deployment + INT4-on-H100 quant
maturity** above marginal vendor-reported proxy gains from newer Apache/MIT
models (Qwen3.5-397B-A17B, GLM-4.5, MiniMax-M1). The conservative pick today
is Llama 4 Maverick (Meta-maintained, FP8 checkpoint published, most-deployed
of the 2025-2026 MoE 400B-class). Revisit at I-cd-011 if empirical quant
verification on 4×H100 changes that calculus.

## What this lock does NOT do

- **Config wiring** — I-cd-009 (#624, dep I-cd-006) writes the picked model
  into `.env` / config.
- **License sign-off** — I-cd-006 (#638, operator-gated). I-cd-005 records
  license name + headline only.
- **FP4 hardware spike** — I-cd-011 (#641, ~$400 GPU). The empirical
  verification that a Maverick INT4 quant works on 4×H100 via vLLM/SGLang.
- **Engine bakeoff** — I-cd-007 (#639). SGLang vs vLLM choice is engine
  layer, not model layer.

## Constraints reaffirmed (operator-locked, non-Codex-negotiable)

1. **Class ~400B** — operator-locked, repeated 6+ times.
2. **Family non-DeepSeek** — generator is DeepSeek V4 Pro; two-family
   segregation enforced by
   `src/polaris_graph/llm/openrouter_client.py:check_family_segregation`.
3. **Open-weight, self-hosted on EU GPU** — sovereignty rule
   (`feedback_sovereignty_threat_model_2026_05_13`).
4. **Quality + 4×H100 (320GB) INT4/FP4 weight residency** — "FP4" means
   weight-residency-only on H100 (no native FP4 tensor cores; NVFP4 is
   Blackwell-only). Runtime ops FP8/BF16.
5. **Rank by quality benchmarks; no cost columns**
   (`feedback_no_cost_mentions`).
6. **License sign-off is a separate operator-gated issue** (I-cd-006).
