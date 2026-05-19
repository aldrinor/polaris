HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. Everything you need is in this brief.

# Codex brief review — I-cd-007 / GH#639: SGLang vs vLLM serving-engine bakeoff

Locks the serving engine for the generator (DeepSeek V4 Pro on Box 1 = 8×H200)
and the evaluator (Llama 4 Maverick on Box 2 = 4×H100 INT4, locked I-cd-005 +
accepted I-cd-006). Engine wiring is I-cd-009; FP4 hardware spike is I-cd-011.

## §0 — Iter-2 revisions (responding to iter-1 REQUEST_CHANGES)

Iter 1: 1 P1 + 4 P2. All addressed; **the recommendation pivots**:

- **P1 (evaluator runtime not source-verified for SGLang + 4×H100 INT4)** —
  No 2026 source confirms SGLang + Llama 4 Maverick + INT4 + 4×H100; SGLang's
  Maverick docs target 8×H100/H200; vLLM/Red Hat validates Maverick **FP8**
  (=~400GB, doesn't fit 4×H100=320GB). Iter 1's "SGLang-for-both" was based
  on an unverified runtime claim. Iter 2 pivots to **vLLM as primary for
  both boxes** (the conservative + currently-wired choice; operational
  simplicity) with SGLang as the per-role contingency at I-cd-011 if a
  documented advantage emerges.
- **P2 (DeepSeek V4 Pro explicit engine support)** — folded into §B: both
  engines now document V4 Pro. **SGLang: 8×H200 FP4 OR 16×H200 FP8**. **vLLM
  0.20.0+: 8×H200, 800K context cap.** This is the genuine SGLang advantage
  (FP4 path) — preserved as a contingency trigger in §D.
- **P2 (RadixAttention vs PagedAttention overclaim)** — tempered: vLLM V1 has
  automatic prefix caching too. SGLang still has a shared-prefix edge for
  evaluator batched scoring, but not "vLLM has no prefix cache."
- **P2 (structured-output overclaim)** — tempered: vLLM exposes
  `structured_outputs` with xgrammar/guidance. SGLang's first-class DSL is
  still ergonomically nicer, not a kind-difference.
- **P2 (NVIDIA Dynamo / TensorRT-LLM)** — added as §B footnote: a 2026
  distributed-serving wrapper that RUNS vLLM/SGLang/TensorRT-LLM backends —
  not a replacement for this pick. Worth tracking; not in scope.

## §A — Operator-locked context

- **Generator (locked separately):** DeepSeek V4 Pro 1.6T MoE / 49B active,
  Box 1 = 8×H200.
- **Evaluator (locked I-cd-005, accepted I-cd-006):** Llama 4 Maverick 400B
  MoE / 17B active + community INT4 quant on Box 2 = 4×H100. Hard fallback:
  Llama 3.1 405B Instruct + AWQ/GPTQ-INT4.
- **Current code state:** `src/providers/llm_provider.py` already uses vLLM
  env vars (`VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`); no SGLang refs.
  Choosing vLLM means **no engine swap is required** at I-cd-009 wiring
  (only model + URL config updates).
- **Operational simplicity matters:** one engine for both boxes is materially
  simpler than two (single monitoring stack, single ops playbook, single
  failure-mode-to-debug, single set of upgrade paths).

## §B — vLLM vs SGLang (2026, Codex iter-1 web-verified facts folded in)

| Dimension | vLLM (UC Berkeley → community) | SGLang (LMSYS → community) |
|---|---|---|
| First released | 2023-06 | 2024-01 |
| Maturity / production deployments at trillion-class MoE | Most-deployed; battle-tested at scale (DeepSeek-V3 multi-year) | Rapidly growing; strong on agent/structured workloads |
| KV-cache | PagedAttention; vLLM V1 also has automatic prefix caching (per iter-1 P2 correction) | RadixAttention (shared-prefix edge for batched evaluator scoring) |
| Structured outputs | `structured_outputs` with xgrammar/guidance (per iter-1 P2 correction) | First-class DSL + xgrammar; ergonomically nicer |
| DeepSeek V4 Pro support | **vLLM 0.20.0+: 8×H200, 800K context cap** (per iter-1 P2) | **SGLang: 8×H200 FP4 OR 16×H200 FP8** (per iter-1 P2) — the FP4 path matches the operator's "FP4 fit" preference more directly |
| Llama 4 Maverick at 4×H100 INT4 | Red Hat validates Maverick FP8 (=400GB, **does not fit** 4×H100=320GB); INT4 ecosystem for Llama 405B-class on H100 is most mature in industry | SGLang documents Maverick on 8×H100/H200; **no source confirms 4×H100 INT4 specifically** (per iter-1 P1) |
| INT4 quants (AWQ/GPTQ) on H100 | Mature, multi-year track record | Supported; newer; community quants increasingly compatible |
| FP8 on H100 / H200 | Mature | Mature |
| OpenAI-compatible API | Yes | Yes |

Footnote (per iter-1 P2): NVIDIA Dynamo / TensorRT-LLM is a 2026
distributed-serving wrapper that runs vLLM, SGLang, or TensorRT-LLM
backends — not a replacement for this engine pick; worth tracking for
later distributed-serving needs.

## §C — Per-role analysis (revised, runtime-grounded)

**Generator (Box 1 = 8×H200, DeepSeek V4 Pro 1.6T):**
- vLLM 0.20.0+ documents V4 Pro on 8×H200 with an 800K context cap — viable.
- SGLang documents V4 Pro on 8×H200 FP4 — also viable; FP4 fit matches the
  operator's "FP4 fit" preference. **Genuine SGLang advantage IF the
  vLLM path requires FP8 + offload tricks that lose throughput.**
- I-cd-011's hardware spike resolves the vLLM-FP4-path-on-V4-Pro-on-8×H200
  question. If vLLM has a clean FP4 path, vLLM stays primary. If not,
  SGLang for Box 1 (per-role split).

**Evaluator (Box 2 = 4×H100, Llama 4 Maverick INT4):**
- Neither engine has a source-confirmed Maverick + INT4 + 4×H100 recipe in
  the public docs as of Codex iter 1 web verification. **I-cd-011 must
  empirically verify ANY engine choice here**, regardless of engine.
- vLLM's INT4-on-H100 ecosystem for Llama 405B-class is the most mature
  in industry (multi-year AWQ/GPTQ track record) → lowest-risk default for
  the Maverick-INT4 community quant work.
- SGLang's structured-output ergonomics + shared-prefix caching are still
  real edges; if I-cd-011 surfaces equal Maverick-INT4-4×H100 viability for
  both engines, the evaluator-role split is worth revisiting.

## §D — Recommendation (revised)

**Primary: vLLM for both boxes** (generator on Box 1 = 8×H200, evaluator on
Box 2 = 4×H100).

Rationale:
- Most-deployed open-source serving engine; battle-tested for trillion-class
  MoE (DeepSeek-V3 multi-year deployment) and Llama 405B-class INT4 on H100.
- Operational simplicity: single engine = single monitoring/ops/upgrade
  stack across both boxes.
- Already wired in `src/providers/llm_provider.py` → I-cd-009 only needs
  model + URL config updates, no engine swap.
- iter-1 P2 corrections confirmed: vLLM V1 has automatic prefix caching AND
  `structured_outputs` with xgrammar/guidance — SGLang's edges in these
  dimensions are real but tempered, not category-defining.

**Per-role SGLang contingency at I-cd-011:** swap Box 1 to SGLang IF I-cd-011's
empirical run shows vLLM's V4 Pro path on 8×H200 cannot achieve a working
FP4 deployment (e.g., FP8 + offload loses throughput badly, or no working
FP4 community quant for vLLM exists). In that case, run **SGLang on Box 1
(V4 Pro FP4)** + **vLLM on Box 2 (Maverick INT4)** — accepting the
operational complexity tax for the documented FP4 advantage. Document the
trigger condition in I-cd-011's brief.

**Hard fallback model-side (already locked):** if Maverick INT4 cannot be
made to fit on 4×H100 via any engine at I-cd-011, fall back to the I-cd-005
hard-fallback model `meta-llama/Llama-3.1-405B-Instruct` (AWQ/GPTQ-INT4 on
vLLM — the most-mature path).

## §E — What this PR ships

Only `docs/models/serving_engine_pick.md` (the locked engine pick + per-role
analysis + SGLang per-role contingency + I-cd-011 revisit conditions) + the
§8.3.5 trajectory log.

Out of scope: engine wiring (I-cd-009), FP4 / INT4 hardware spike (I-cd-011),
GPU topology + capacity (I-cd-008).

## §F — Questions for Codex

1. Concur with locking vLLM for both boxes + SGLang-for-Box-1 contingency at
   I-cd-011, OR push back: split now (SGLang Box 1, vLLM Box 2) on the
   documented FP4 V4 Pro advantage even without I-cd-011 empirical?
2. Is vLLM's V4 Pro path on 8×H200 (0.20.0+, 800K context cap) FP4-capable
   today via a community quant, or is it FP8 + offload only? If FP8-only,
   does it actually fit 8×H200 with usable throughput?
3. Llama 4 Maverick INT4 on 4×H100: ANY 2026 source confirming a working
   community AWQ/GPTQ-INT4 quant on either vLLM or SGLang at this exact
   config, or is I-cd-011 genuinely the empirical-only path?
4. Any 2025-2026 serving engine I should evaluate alongside SGLang/vLLM
   (e.g., NVIDIA TensorRT-LLM as a direct backend, lmdeploy/turbomind,
   Ray-Serve-LLM, Anyscale)?
5. Iter-1 framed Dynamo as a wrapper running vLLM/SGLang/TensorRT-LLM. Is
   adopting Dynamo at any point (post-Carney) worth flagging in this doc as
   a deferred-decision?

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
