# I-cd-005 — Claude architect audit

**Issue:** GH#637 — Evaluator bakeoff, pick the exact ~400B non-DeepSeek
open-weight model. Locks the evaluator-side of the two-family pair
(generator = DeepSeek V4 Pro, locked separately).

**Deliverable:** `docs/models/evaluator_pick.md` — primary pick, hard fallback,
6 strong alternatives for I-cd-011 revisit, scope boundaries, constraint
reaffirmation.

## What this PR ships

- `docs/models/evaluator_pick.md` (NEW, 105 LOC) — the locked pick.
- `.gitignore` (+3 LOC) — negate the broad `models/` rule for `docs/models/`
  (text docs, not weights). Future model-pick / quant / serving docs from
  I-cd-009/011 can live in the same dir.

## The pick

**Primary:** `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` + community
INT4 quant for 4×H100 weight residency.

**Hard fallback:** `meta-llama/Llama-3.1-405B-Instruct` + AWQ/GPTQ-INT4 (the
most-mature INT4-on-H100 path; safety net if I-cd-011 cannot verify a Maverick
INT4 quant on 4×H100).

## Codex trajectory

iter 1 RC (1 P1) → iter 2 RC (1 P1) → iter 3 RC (1 P1) → **iter 4 APPROVE**
(0 P0 / 0 P1, 5 P2 confirmations + clarifications all folded into the
deliverable doc). Each iter-RC was Codex's web-search-driven expansion of the
candidate set: iter 1 added Qwen3.5-397B-A17B; iter 2 added 5 more MoE
400B-class candidates (Llama 4 Maverick, MiniMax-M1, GLM-4.5, Arcee
Trinity-Large, Hunyuan-Large); iter 3 added Baidu ERNIE-4.5-VL-424B. The
iter-1 baseline (Llama 3.1 405B / Tulu 3 405B / Nemotron-4 340B) was the
2024 dense generation; iter 4's landscape is 2025-2026 MoE 400B-class. The
pick pivoted from Llama 3.1 405B (iter 1/2) to Llama 4 Maverick (iter 3/4).

## Scope discipline

This issue ships ONLY the pick doc. The actual config wiring is I-cd-009
(#624, depends on C-06 sign-off); the FP4 hardware spike is I-cd-011 (#641);
the engine bakeoff is I-cd-007 (#639); license sign-off is I-cd-006 (#638).

## Risk surface

- The pick is a DOC, not a runtime change. Zero immediate execution risk.
- The downstream risk is at I-cd-011: if no working Llama 4 Maverick INT4
  quant on 4×H100 via vLLM/SGLang can be found, the hard-fallback (Llama 3.1
  405B Instruct + AWQ/GPTQ-INT4) is the proven safety net documented in the
  same pick doc.
- License sign-off (I-cd-006) is operator-gated; the pick doc records the
  Llama 4 Community license headline and notes the Hunyuan EU-territory
  clause for re-verify.

## Codex P2 dispositions (all folded into the doc)

1. ERNIE `-PT` clarification + no text-only 424B ERNIE → noted in the
   alternatives table.
2. Largest/highest-active wording → MiniMax-M1 (456B largest), Hunyuan-Large
   (52B highest active) labeled correctly.
3. Ranking caveat ("no published RAG-faithfulness numbers; weighting
   deployment maturity over vendor proxies") → entire "Why deployment
   maturity is weighted" section in the doc.
4. Multimodality caveat applied to Maverick + Qwen3.5 in addition to ERNIE.
5. Hunyuan EU-territory clause noted in the alternatives table.
