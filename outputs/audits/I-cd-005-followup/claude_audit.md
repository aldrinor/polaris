# I-cd-005-followup — Claude architect audit

**Issue:** GH#637 + GH#638 — re-lock the evaluator pick (and the license
sign-off carrying with it) to the operator-locked model that I-cd-005
drifted away from.

**Deliverable:** rewritten `docs/models/evaluator_pick.md` +
`docs/models/evaluator_license_signoff.md` — both now lock
`google/gemma-4-31B-it`.

## Why this followup

Two compounded Claude failures on the original I-cd-005, both surfaced by
the operator this session:

1. **Failed to surface locked model as HARD CONSTRAINT.** The I-cd-005
   brief said "Class: ~400B operator-locked" but never the specific MODEL.
   Per `feedback_operator_locked_decisions_not_codex_consultable_2026_05_15`
   locked decisions go at the TOP as HARD CONSTRAINTS. I didn't.
2. **Drifted with Codex's web-search expansion.** Codex iter-3 pivoted
   I-cd-005 to Llama 4 Maverick on "newer + most-deployed 2026 MoE 400B."
   I let it through without weighing the Llama 4 Maverick LMArena-tuning
   quality controversy or the operator's original Gemma 4 reference in
   `docs/carney_delivery_plan_v6_2.md`. Per
   `feedback_be_skeptical_of_codex_2026_05_13` Codex-as-advisor gets
   filtered through Claude judgment. I didn't.

Operator pushback this session: "Llama 4 is famous for garbage, what's
wrong here" + "For evaluator, Gemma 4 400 B, no more discussion on it" +
"For model, pls respect what we locked in earlier, and you failed to tell
Codex that we already locked in, it is your 100% failure."

## Recovery flow

1. Branch `bot/I-cd-005-followup` off polaris.
2. Brief iter 1 written with **HARD CONSTRAINTS block at the very top** —
   the explicit pattern I should have used in I-cd-005 originally.
3. Codex iter-1 web-verified: **no released Gemma 4 400B HF checkpoint
   exists**. Codex correctly stayed in operational-verification mode,
   did NOT propose alternative models, flagged the gap as
   operator-escalation P1.
4. Escalated to operator → operator asked "which is best as evaluator" →
   Claude judgment: **31B dense over 26B-A4B MoE** (dense > MoE for
   LLM-as-judge reasoning-bound tasks; 31B-active > 4B-active for careful
   faithfulness chains).
5. Brief iter 2 (this audit's underpinning) — HARD CONSTRAINTS updated to
   `google/gemma-4-31B-it`; Codex iter-2 APPROVE'd with 7 operational
   P2s all folded into the deliverable docs.

## Locked

- Primary: `google/gemma-4-31B-it` (BF16 source of truth).
- 4×H100 runtime: `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` via vLLM with
  `--quantization compressed-tensors`.
- License: Apache 2.0 + Gemma Prohibited Use Policy (cleaner than Llama
  Community — no MAU, no HF gating, no "Built with" placement).
- Hard fallback (kept from I-cd-005): Llama 3.1 405B + AWQ/GPTQ-INT4.
- Two-family vs DeepSeek V4 Pro: passes (`('deepseek', 'gemma')`).

## Scope discipline

This PR rewrites the two superseded docs only. It does NOT:
- Wire the new model id (I-cd-009).
- Run the FP4 hardware spike (I-cd-011 — substantially simpler now since
  Gemma 4 31B INT4 ≈ 16 GB on 4×H100=320GB = enormous headroom).
- Change the engine choice (I-cd-007's vLLM lock holds; vLLM has explicit
  Gemma4 recipe support).

## I-cd-008 impact

I-cd-008 (GPU topology) is paused on `bot/I-cd-008` — will resume after
this followup merges. With Gemma 4 31B at ~16 GB INT4, the per-token
compute load on Box 2 = 4×H100 is dramatically lower than Maverick's
17B-active MoE (or Llama 3.1 405B dense's 405B-active). The topology
probe's risk profile relaxes substantially: 4×H100 is overprovisioned
for the evaluator role with Gemma 4 31B. We could probably evaluate on
2×H100 or 1×H100 if Carney budget tightens — that's a side-finding for
I-cd-008's confirm step.
