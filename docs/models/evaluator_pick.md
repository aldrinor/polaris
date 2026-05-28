---
status: superseded
superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
superseded_on: 2026-05-28
superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
---

# POLARIS evaluator model — locked pick (I-cd-005-followup, GH#637)

**Decision:** **`google/gemma-4-31B-it`** is the locked POLARIS evaluator,
served via vLLM on Box 2 = 4×H100 using the community INT4 AWQ artifact
`ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` (load with
`--quantization compressed-tensors`, NOT `--quantization awq`, per Codex
iter-2 web verification).

**Supersedes I-cd-005 (PR #661, merged `c5e114e2`)** which locked
`meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`. That lock was wrong on
two counts (both Claude failures):

1. The I-cd-005 brief said "Class: ~400B operator-locked" but never surfaced
   the specific MODEL as a HARD CONSTRAINT, leaving Codex free to propose
   any ~400B candidate. Per
   `feedback_operator_locked_decisions_not_codex_consultable_2026_05_15`,
   locked decisions go at the TOP as HARD CONSTRAINTS.
2. Codex iter-3 pivoted to Llama 4 Maverick on "newer + most-deployed 2026
   MoE 400B" framing. I let it through without weighing the Llama 4
   Maverick LMArena-tuning quality controversy or the operator's original
   Gemma 4 reference in `docs/carney_delivery_plan_v6_2.md`. Per
   `feedback_be_skeptical_of_codex_2026_05_13`, Codex-as-advisor gets
   filtered through Claude judgment. I didn't.

Operator pushback this session ("Llama 4 is famous for garbage, what's
wrong here") + locked-in evaluator restatement ("For evaluator, Gemma 4
400 B, no more discussion on it") triggered this followup. Codex iter-1
web-verified that Gemma 4 400B is unreleased (top released is 31B dense /
26B-A4B MoE); operator escalated → Claude judgment picked **31B dense
over 26B-A4B** for the evaluator role (reasoning below).

## Why Gemma 4 31B dense (primary)

- **Operator-locked, originally-intended model.** The Carney plan v6.2
  already named Gemma 4 as the evaluator. The I-cd-005 drift to Llama 4
  Maverick was a Claude error this followup corrects.
- **Dense beats MoE for LLM-as-judge at comparable total size.** The
  RAG-faithfulness adjudication is reasoning-bound (read cited span,
  decide if sentence follows from it), not throughput-bound. Gemma 4 31B
  dense fires all 31B params per token; Gemma 4 26B-A4B MoE fires only
  ~4B active per token. For careful judgment chains, more per-token
  compute = more reliable verdicts.
- **31B > 26B + 31B-active > 4B-active.** Larger AND more per-token
  compute. Matches the operator's "the largest" preference applied to
  Gemma 4's actual released family.
- **Apache 2.0 license** (Codex iter-2 verified) — cleaner than Llama
  Community: no MAU threshold, no Llama-style HF `request access` gating,
  no "Built with Llama" prominence requirement. Apache-style attribution
  only. The license headline is recorded separately in
  `evaluator_license_signoff.md`.
- **Two-family vs DeepSeek V4 Pro:** `check_family_segregation` returns
  `('deepseek', 'gemma')` — distinct lineages, passes.
- **Serving + quant path proven:** vLLM has Gemma4-specific parser support
  (`docs.vllm.ai/projects/recipes/.../Google/Gemma4.html`); community AWQ
  INT4 artifact `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` loads via
  `--quantization compressed-tensors`. Raw 4-bit weights ~16 GB; practical
  recommended VRAM higher (overhead + KV cache) but trivial on
  4×H100=320GB.

## Runtime artifacts

| Artifact | HF id | Purpose |
|---|---|---|
| BF16 instruct weights | `google/gemma-4-31B-it` | Source of truth; vLLM recipe documents TP=2 on 2× A100/H100 |
| Community INT4 AWQ (vLLM-loadable) | `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` | The intended 4×H100 runtime artifact — load with `--quantization compressed-tensors` |
| NVIDIA NVFP4 sibling | `nvidia/Gemma-4-31B-IT-NVFP4` | Blackwell-only; noted for any future Blackwell migration; NOT the 4×H100 target |

No Google-published FP8/NVFP4/INT4 official sibling repo exists yet (Codex
iter-2 P2). The community AWQ above is the operational choice for 4×H100;
I-cd-011 empirically verifies the load + smoke-test on actual hardware.

## Model-side hard fallback (kept from I-cd-005)

`meta-llama/Llama-3.1-405B-Instruct` + AWQ/GPTQ-INT4 on vLLM — the
most-mature INT4-on-H100 path in industry. Kept as the safety net iff
Gemma 4 31B INT4 cannot be made to work on 4×H100 at I-cd-011 (unlikely
given the 16 GB footprint and vLLM's Gemma4 recipe support — but
documented for completeness).

## I-cd-011 (FP4 readiness spike, #641) responsibilities

Now substantially simpler than the Maverick-locked I-cd-005 spec:
1. Smoke-test `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` on vLLM at 4×H100
   with `--quantization compressed-tensors`.
2. Verify JSON-schema structured output works for the
   evaluator-judgment format.
3. Measure per-second judgment throughput (the evaluator load is
   sentence-by-sentence; reasonable per-token speed required).
4. The hard fallback (Llama 3.1 405B + AWQ/GPTQ-INT4 on vLLM) is a
   secondary smoke-test only if (1) fails.

## What this lock does NOT do

- **Config wiring** — I-cd-009 (#624). The new model id (`google/gemma-4-31B-it`
  or the AWQ sibling) gets wired into `src/providers/llm_provider.py` +
  `.env` there.
- **License sign-off** — `docs/models/evaluator_license_signoff.md` is
  rewritten in this same PR for the Gemma 4 31B-it Apache 2.0 + Gemma PUP
  shape. (I-cd-006's "Auto-merge per Codex" sign-off mode carries.)
- **FP4 hardware spike** — I-cd-011 (#641).
- **Engine bakeoff** — I-cd-007 (#639) locked vLLM for both boxes; vLLM
  recipe support for Gemma 4 confirmed by Codex iter-2 P2.

## Constraints reaffirmed (operator-locked, non-Codex-negotiable)

1. **Evaluator model = `google/gemma-4-31B-it`** (operator-locked 2026-05-19).
2. **Family = non-DeepSeek** (Gemma is distinct lineage; `check_family_
   segregation('deepseek/deepseek-v4-pro', 'google/gemma-4-31b-it')` returns
   `('deepseek', 'gemma')`).
3. **Open-weight, self-hosted on EU/Canada GPU.**
4. **Quality + 4×H100 INT4 weight residency** (~16 GB; massive headroom).
5. **Engine = vLLM** (I-cd-007 lock).
