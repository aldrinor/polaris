HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. Everything you need is in this brief.

# Codex brief review — I-cd-005 / GH#637: pick the exact ~400B non-DeepSeek evaluator model

Locks the EVALUATOR. Config wiring: **I-cd-009** (#624, deps C-06). License
sign-off: **I-cd-006** (#638, operator-gated). FP4 hardware spike: **I-cd-011**
(#641). Engine bakeoff: **I-cd-007** (#639).

## §0 — Iter-4 revisions (responding to iter-3 REQUEST_CHANGES)

Iter 3: 1 P1 + 3 P2. All addressed:
- **P1 (Baidu ERNIE-4.5-VL-424B-A47B-PT missing)** — added as a core candidate
  in §B with the verified HF URL. At 424B total / 47B active under Apache 2.0,
  it is now the LARGEST candidate in the class. Evaluated in §C.1/§C.4/§C.5
  and weighed against Llama 4 Maverick in §D. Two caveats flagged: the `-PT`
  suffix's exact semantics (Pre-Trained base vs PyTorch format) and the
  vision-language vs text-only fit for the evaluator role.
- **P2 (Arcee HF id missing)** — replaced the docs URL with the concrete HF
  repo id `arcee-ai/Trinity-Large-Thinking` so I-cd-011 has an executable
  target. If a different Trinity variant is intended, the recommendation row
  in §D names that explicitly.
- **P2 (§D count "4 other" but lists 5)** — corrected to "5 other".
- **P2 (ERNIE-4.5-300B-A47B-PT as below-class fallback)** — added alongside
  Qwen3-235B-A22B in §B's below-class fallback list.

Iter-3 fixes preserved (5 MoE 400B-class candidates folded in; weight-residency-
only framing; explicit "no candidate publishes RAG-faithfulness numbers" caveat).
Iter-1/2 fixes preserved (Qwen3.5-397B included; Tulu rationale corrected;
FP4/H100 wording; per-model serving claims; Qwen3-235B demoted).

## §A — Operator-locked constraints (NOT Codex-negotiable)

1. Class **~400B** (locked, repeated 6+ times).
2. Family **non-DeepSeek** (generator = DeepSeek V4 Pro; enforced by
   `openrouter_client.check_family_segregation`).
3. Open-weight, self-hosted on EU GPU. Sovereignty = no US-LLM-vendor runtime
   calls + no US-jurisdiction data; open-weight self-hosted is fine regardless
   of pre-training lineage origin.
4. **Quality + 4×H100 (4×80GB = 320GB) FP4 fit** — "FP4" = INT4/FP4 weight
   residency (AWQ / GPTQ-INT4 / community FP4), runtime ops FP8 or BF16; native
   FP4 (NVFP4) = Blackwell-only, out of scope for H100.
5. Rank by quality benchmarks; **no cost columns**.
6. License sign-off is operator-gated at I-cd-006; this brief records license
   names + headline terms only.

## §B — Candidate set (~400B non-DeepSeek open-weight, May 2026 landscape)

| # | Hugging Face id | Arch | Params (total/active) | License | Released | Source verified by Codex iter-N |
|---|---|---|---|---|---|---|
| 1 | `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` | MoE 128 experts | 400B / 17B | Llama 4 Community | 2025 | iter-2 P1 |
| 2 | `meta-llama/Llama-3.1-405B-Instruct` | dense | 405B / 405B | Llama 3.1 Community | 2024-07 | iter-1 baseline |
| 3 | `allenai/Llama-3.1-Tulu-3-405B` (+ `-SFT`) | dense (Llama base + AI2 recipe) | 405B / 405B | AI2 ImpACT + Llama 3.1 base | 2025-01 | iter-1 baseline |
| 4 | `nvidia/Nemotron-4-340B-Instruct` | dense | 340B / 340B | NVIDIA Open Model License | 2024-06 | iter-1 baseline |
| 5 | `Qwen/Qwen3.5-397B-A17B-FP8` (+ `nvidia/Qwen3.5-397B-A17B-NVFP4` Blackwell-only) | MoE | 397B / 17B | Apache 2.0 | 2026-02 | iter-1 P1 |
| 6 | `MiniMaxAI/MiniMax-M1-80k-hf` | MoE | 456B / 45.9B | Apache 2.0 | 2025 | iter-2 P1 |
| 7 | `zai-org/GLM-4.5` | MoE | 355B / 32B | MIT | 2025 | iter-2 P1 |
| 8 | `arcee-ai/Trinity-Large-Thinking` | MoE | 398-400B / 13B | Apache 2.0 | 2025 | iter-2 P1 (HF id fixed iter-3 P2) |
| 9 | `tencent/Tencent-Hunyuan-Large` | MoE | 389B / 52B | Tencent license | 2024-11 | iter-2 P1 |
| 10 | `baidu/ERNIE-4.5-VL-424B-A47B-PT` | MoE (vision-language) | 424B / 47B | Apache 2.0 | 2025-2026 | iter-3 P1 |

Below-class (not core; sub-class safe-fallback only if every ~400B candidate
fails I-cd-011 hardware verification):
- `Qwen/Qwen3-235B-A22B-Instruct` — 235B MoE / 22B active, Apache 2.0.
- `baidu/ERNIE-4.5-300B-A47B-PT` — 300B MoE / 47B active, Apache 2.0 (iter-3 P2).

## §C — Evaluation

### §C.1 — 4×H100 INT4/FP4 weight residency (320GB total)

| # | Model | Total params | INT4 weight residency only |
|---|---|---|---|
| 1 | Llama 4 Maverick | 400B | ~200 GB |
| 2 | Llama 3.1 405B Instruct | 405B | ~203 GB |
| 3 | Tulu 3 405B | 405B (same arch) | ~203 GB |
| 4 | Nemotron-4 340B | 340B | ~170 GB |
| 5 | Qwen3.5-397B-A17B | 397B | ~199 GB |
| 6 | MiniMax-M1 | 456B | ~228 GB |
| 7 | GLM-4.5 | 355B | ~178 GB |
| 8 | Arcee Trinity-Large | 398-400B | ~200 GB |
| 9 | Hunyuan-Large | 389B | ~195 GB |
| 10 | ERNIE-4.5-VL-424B-A47B | 424B (incl. vision tower) | ~212 GB (text-only weights only would be slightly less; the VL component is unused by the evaluator role) |

All ten fit weight-residency-wise on 4×H100. KV-cache headroom, quant
metadata, NCCL/activation/fragmentation overhead, and actual usable context
length **are I-cd-011's empirical job** — not estimated here. MoE models also
have an expert-offload escape valve (vLLM/SGLang MoE expert-CPU-offload) that
dense models lack.

### §C.2 — Quality

**Explicit limitation:** none of these candidates have published comparable
RAGTruth / FEVER / RAGAS / TriviaQA-RAG numbers. The decision uses **general
LLM-as-judge proxies** — MMLU-Pro, IFEval, AlpacaEval-2, Arena-Hard — which
correlate with but do not directly measure RAG-faithfulness adjudication.

Within-cluster comparison:

- **Dense 2024 cluster** (Llama 3.1 405B, Tulu 3 405B, Nemotron-4 340B):
  Llama 3.1 405B Instruct is the independently-reproduced reference (MMLU ~88,
  MMLU-Pro ~73, IFEval ~88, AlpacaEval-2 ~39, Arena-Hard ~69). Tulu 3 405B
  beats vanilla Llama 3.1 405B Instruct on aggregate + AlpacaEval-2 but NOT on
  MMLU or IFEval (per AI2's own 405B card — corrected from iter 1).
  Nemotron-4 340B trails the 405B class on broad knowledge (MMLU ~81).
- **2025-2026 MoE cluster** (Llama 4 Maverick, Qwen3.5-397B-A17B, MiniMax-M1,
  GLM-4.5, Arcee Trinity-Large, Hunyuan-Large): all claim parity or gains on
  the same proxies vs the dense Llama 3.1 405B baseline. Most of those
  benchmark numbers are **vendor-reported** and pending independent
  third-party reproduction at scale. Llama 4 Maverick is the most-cited and
  most-deployed of the MoE 400B-class as of May 2026; Meta-published FP8
  checkpoint specifically.

### §C.3 — Two-family vs DeepSeek V4 Pro

All nine have pre-training lineages distinct from DeepSeek. All pass
`check_family_segregation`.

### §C.4 — Serving (per-model, per-engine, what I can claim from this session)

I can claim confidently WITHOUT independent re-verification:
- **Llama 3.1 405B Instruct + AWQ/GPTQ-INT4 on vLLM/SGLang**: production-
  deployed at scale for >1 year; the most mature INT4-on-H100 path in this set.
- **Llama 4 Maverick (FP8 published by Meta)**: vLLM/SGLang support documented
  (Codex iter-2 P1 verified). FP8 checkpoint = 400 GB → does NOT fit 4×H100
  FP8 (only 320 GB). An INT4 community quant is needed for 4×H100; quant
  ecosystem maturity is lower than Llama 3.1 405B's (Maverick is newer).
- **Tulu 3 405B**: same Llama-3.1 loader path; fewer maintained INT4 quants on
  HF than vanilla Llama 3.1 405B.
- **Nemotron-4 340B Instruct**: NVIDIA-published serving recipes; vLLM/SGLang
  support exists; smaller than the operator-locked "the largest" preference.
- **MoE 2025-2026 cluster** (Qwen3.5-397B-A17B, MiniMax-M1, GLM-4.5, Arcee
  Trinity-Large, Hunyuan-Large, ERNIE-4.5-VL-424B): all have vLLM/SGLang
  support per Codex web verification. Community INT4 quants for the specific
  400B-class MoE variants on 4×H100 vary in maturity and are the empirical
  unknown that I-cd-011 resolves. ERNIE-4.5-VL-424B specifically: the
  `-PT` suffix needs clarification (Pre-Trained base implies a base model that
  is NOT instruct-tuned — unusable as an evaluator without an additional
  -Instruct/-Chat checkpoint); and the vision-language tower is unused by the
  text-only evaluator role — verify whether a text-only variant exists.

### §C.5 — License (informational; I-cd-006 owns sign-off)

| Model | License | Headline |
|---|---|---|
| Llama 4 Maverick | Llama 4 Community | Llama 4 specific (typically tightened vs Llama 3.1 — verify at I-cd-006); MAU/acceptable-use clauses |
| Llama 3.1 405B | Llama 3.1 Community | 700M MAU acceptable-use threshold |
| Tulu 3 405B | AI2 ImpACT + Llama 3.1 base | Inherits Llama 3.1's 700M MAU |
| Nemotron-4 340B | NVIDIA Open Model | Permissive, commercial OK |
| Qwen3.5-397B-A17B | Apache 2.0 | Most permissive; no MAU |
| MiniMax-M1 | Apache 2.0 | Most permissive |
| GLM-4.5 | MIT | Most permissive |
| Arcee Trinity-Large | Apache 2.0 | Most permissive |
| Hunyuan-Large | Tencent | Custom; verify at I-cd-006 |
| ERNIE-4.5-VL-424B | Apache 2.0 | Most permissive; no MAU |

## §D — Recommendation (revised after iter-2 P1)

**Primary: `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`** (use with a
community INT4 quant for 4×H100 residency).

Rationale:
- ~400B class (400B total — matches "the largest" within the operator-locked
  ~400B target).
- Meta's current generation (Llama 4, April 2025) — picking Llama 3.1 405B
  (July 2024) over Llama 4 in May 2026 was the iter-1/iter-2 blind spot.
- MoE 17B active = much higher evaluator throughput per token than dense 405B
  (the evaluator scores every sentence in every report; throughput matters).
- vLLM/SGLang documented; Meta-published FP8 checkpoint (lowering quant-recipe
  risk vs vanilla open-weights).
- Different lineage from DeepSeek → two-family ✓.
- License acceptable pending I-cd-006 (Llama 4 Community — verify headline at
  sign-off).

**Hard-fallback (proven-deployable today): `meta-llama/Llama-3.1-405B-Instruct`
+ AWQ/GPTQ-INT4.** The most-mature INT4-on-H100 path in the candidate set. If
I-cd-011 verifies no working Llama 4 Maverick INT4 quant on 4×H100, this is
the safety net.

**MoE alternatives at the same class** (any may displace primary if I-cd-011
proves it has a better INT4-on-H100 path and Codex prefers its
quality/license profile):
- `baidu/ERNIE-4.5-VL-424B-A47B-PT` — Apache 2.0, MoE 47B active, **largest in
  the class (424B total)**. Strong candidate IF the `-PT` suffix denotes an
  instruct-tuned checkpoint (vs Pre-Trained base, which would disqualify it as
  an evaluator without further tuning) AND the vision-language tower's weight
  footprint is acceptable for a text-only evaluator role.
- `Qwen/Qwen3.5-397B-A17B-FP8` — Apache 2.0, MoE 17B active, cleanest
  sovereignty story (Alibaba lineage, no US-origin discussion at all).
- `MiniMaxAI/MiniMax-M1-80k-hf` — Apache 2.0, MoE 45.9B active (highest active
  param count of the MoE set; strongest "compute per token" within the set).
- `zai-org/GLM-4.5` — MIT, MoE 32B active.
- `arcee-ai/Trinity-Large-Thinking` — Apache 2.0, MoE 13B active (lowest
  active params).
- `tencent/Tencent-Hunyuan-Large` — Tencent license, MoE 52B active.

**Decision rule I am asking Codex to confirm:** lock Llama 4 Maverick FP8
(use with community INT4 quant) as the I-cd-005 pick, with Llama 3.1 405B
Instruct as the proven-deployable hard-fallback if I-cd-011 cannot verify a
Maverick INT4 quant on 4×H100. The 6 other MoE alternatives (including
ERNIE-4.5-VL pending PT/VL clarification) are documented as
"comparable-class options at I-cd-011-revisit if Maverick fails."

## §E — What this PR ships

Only `docs/models/evaluator_pick.md` (the locked pick + per-candidate
comparison + alternatives + fallback + I-cd-011 revisit conditions) + the
§8.3.5 trajectory log.

Out of scope: config wiring (I-cd-009), license sign-off (I-cd-006), FP4
hardware spike (I-cd-011), engine bakeoff (I-cd-007).

## §F — Questions for Codex

1. Lock Llama 4 Maverick FP8 + community INT4 quant as primary, with Llama
   3.1 405B Instruct as the proven hard-fallback? Or push back: pick one of
   the Apache-2.0 MoE alternatives (ERNIE-4.5-VL-424B / Qwen3.5-397B-A17B /
   MiniMax-M1 / GLM-4.5 / Arcee Trinity-Large) as primary now on
   license-purity + sovereignty grounds, accepting an additional INT4-quant
   maturity risk?
2. **ERNIE-4.5-VL-424B-A47B-PT**: does the `-PT` suffix denote an
   instruct-tuned checkpoint (usable as evaluator) or a Pre-Trained base
   (NOT usable without further instruct tuning)? And is there a text-only
   ERNIE-4.5 in the ~400B class so the vision-language tower's weight
   footprint is avoided for the evaluator role?
3. Any further ~400B-class non-DeepSeek open-weight candidate STILL missing
   from §B?
4. §C.4 per-model/per-engine claims: are they appropriately conservative
   now, or still over-claiming?
5. Is "no candidate publishes comparable RAGTruth/FEVER/RAGAS numbers,
   decision uses LLM-as-judge proxies" the right honest framing, or should
   §C.2 be even more cautious?

## §G — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
