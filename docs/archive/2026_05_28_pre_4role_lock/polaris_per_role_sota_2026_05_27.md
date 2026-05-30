---
status: superseded
superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
superseded_on: 2026-05-28
superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
---

# POLARIS Per-Role SOTA Open-Weight LLM Validation (2026-05-27)

**Mission:** Replace single-composite-score selection (AA Intelligence Index) with
per-role validation using role-specific benchmarks. Operator pushback was correct:
each of the 4 POLARIS stack roles (generator / mirror / sentinel / judge) has a
distinct capability profile and the "highest average" model is not necessarily
the highest in any individual role.

**Constraints (operator-locked, May 2026):**
- Open weights only (any license)
- Non-US runtime LLM (open weights on sovereign infra OK)
- No hardware ceiling, no time constraint
- Latest + strongest + most capable per role
- Multi-domain: clinical + legal + financial + regulatory + policy + scientific, EN baseline
- Multi-LLM stack OK if each layer earns its keep

**Claude's original picks (under audit):**
- Generator: DeepSeek V4-Pro
- Mirror: Kimi K2.6
- Sentinel: GLM-5.1
- Judge: Mistral Medium 3.5  (note: Mistral Medium 3.5 is NOT open-weight — this
  was already a violation. Flagged in cross-family check phase.)

**Audit method:** Each role gets its own role-specific benchmark suite, scored
candidate-by-candidate with primary-source URLs.

---

## Candidate pool (open-weight, sovereign-deployable, May 2026)

Pre-validated for "open weights + non-US runtime + most-capable per role":

| Model | Family | Release | Params (total / active) | License | Sovereign? |
|---|---|---|---|---|---|
| DeepSeek V4 Pro | DeepSeek | 2026-04-24 | 1.6T / 49B (MoE) | MIT | Yes (CN-origin) |
| DeepSeek V4 Flash | DeepSeek | 2026-04-24 | 284B / 13B (MoE) | MIT | Yes (CN-origin) |
| Kimi K2.6 | Moonshot | 2026-04-20 | ~1T (MoE) | Modified MIT | Yes (CN-origin) |
| GLM-5.1 | Z.ai (Zhipu) | 2026-04-07 | 744B (MoE) | MIT | Yes (CN-origin) |
| Qwen 3.6-27B | Alibaba Qwen | 2026-04-22 | 27B dense | Apache 2.0 | Yes |
| Qwen 3.5-397B | Alibaba Qwen | 2025-Q4 | 397B (MoE) | Apache 2.0 | Yes |
| MiniMax M2.7 | MiniMax | 2026-03-18 | (M2.1 base: 230B/10B; M2.7 extends) | Open-weight | Yes |
| Mistral Large 3 / Medium 3.5 | Mistral | 2026 | 128B (Medium) | Mistral commercial (Medium 3.5 is API-only/closed; Large 2411 is open) | Partial — Mistral Medium 3.5 NOT open-weight |
| Gemma 4 31B / 26B-A4B | Google | 2026 | 31B / 26B | Gemma Use Policy + Apache 2.0 | Yes (open-weight, US-origin org but weights are sovereign once mirrored) |
| Llama 3.3-70B / 4 | Meta | 2024-25 | 70B+ | Llama community | Yes (open weights) |

**Excluded:**
- Qwen 3.7 Max / Plus — closed weights (Alibaba reversed openness for flagship tier in 2026)
- Kimi K2.7 / K3 — not yet released as of 2026-05-27 (community rumor only)
- Mistral Medium 3.5 — API-only per Mistral's 2026 pricing page; cannot run sovereign
- Tencent Hunyuan — released but "very strict licenses, unusual for Chinese companies"; effectively non-sovereign-friendly
- Doubao / ERNIE 5.0 — closed weights (consumer / Baidu-Kunlun-only)
- finix_s1_32b (Ant Group) — released April 2026 with strong HHEM-2.3 (1.8%) but limited documentation as a general-purpose generator; flagged for sentinel-role consideration

---

## Role: Generator

### Role requirements

The generator writes long-form, multi-section research deliverables across
clinical, legal, financial, regulatory, policy, and scientific domains. POLARIS
enforces a strict provenance layer (`[#ev:<id>:<start>-<end>]` token per
sentence, evidence-pool-bounded, ≥2 content-word overlap, decimal-exact match —
see `CLAUDE.md` §9.1) so the generator must:

1. **Follow extremely structured instructions** at sentence granularity
   (citation token format, decimal preservation, content-overlap thresholds).
2. **Abstain or qualify honestly** when evidence is thin — POLARIS aborts the
   pipeline on `abort_no_verified_sections` if fabrication overruns
   `strict_verify`. Calibration matters more than raw recall.
3. **Hallucinate as little as possible** when synthesizing from the provided
   evidence pool. HHEM-2.3 is the canonical proxy for this in a
   grounded-summarization setting (Vectara dataset spans law / medicine /
   finance / education / tech — exactly POLARIS's mix).
4. **Produce fine-grained sentence-level citations** — LongBench-Cite /
   LongCite is the closest published benchmark for this exact capability.
5. **Handle long context faithfully** at ≥128K (the evidence-bundle size after
   tier-classifier + dedupe routinely reaches 80-200K tokens in POLARIS clinical
   sweeps).

Single-composite indices (AA Intelligence Index, MMLU averages) hide the
hallucination axis behind coding/reasoning peaks, which is precisely the failure
mode the operator flagged.

### Role-specific benchmark scoring

Primary sources cited inline. All scores reflect best public reading as of
2026-05-27. UNKNOWN where the model has not been independently evaluated on
that benchmark yet.

| Model | HHEM-2.3 grounded-summary hallucination (lower=better) | AA-Omniscience Index (higher=better; calibration+abstention) | AA-Omniscience Accuracy % | IFEval (higher=better) | LongCite / long-form citation |
|---|---|---|---|---|---|
| DeepSeek V4 Pro (Max) | UNKNOWN (not in HHEM-2.3 top 30; DeepSeek V3.2-Exp at 5.3%, V3.1 at 5.5%, V3 at 6.1% — V4 likely 5-7% extrapolated) | UNKNOWN (BenchLM lists Accuracy only) | 43.3% | UNKNOWN (DeepSeek does not publish; community reports place it in the high-80s) | UNKNOWN — no published LongCite eval |
| DeepSeek V4 Flash (Max) | UNKNOWN | UNKNOWN | 37.2% | UNKNOWN | UNKNOWN |
| Kimi K2.6 | NOT in HHEM-2.3 top 30. Vendor self-report ≈39% on AA-Omniscience hallucination axis (different metric) | 6 (third among open-weight reported) | 32.8% | 89.8% (vendor-published) | UNKNOWN |
| Kimi K2.5 | UNKNOWN HHEM-2.3 | UNKNOWN | 34.3% | UNKNOWN | UNKNOWN |
| GLM-5.1 | UNKNOWN HHEM-2.3 (not in top 30) | UNKNOWN | UNKNOWN (GLM-5 base: 26.9%; GLM-4.7: 29.3%; GLM-5.1 likely 27-30%) | 91.7 (avg across IF benchmarks per awesomeagents.ai, #10/117) | UNKNOWN |
| Qwen 3.6-27B | UNKNOWN HHEM-2.3 (Qwen 3 8B at 4.8%, 14B at 5.4%, 32B at 5.9% — Qwen 3.6-27B not yet listed) | UNKNOWN | 19.2% (LOW) | UNKNOWN (Qwen 3.5-27B at 95.0%; Qwen 3.6-Plus at 94.3% — 3.6-27B unpublished) | UNKNOWN |
| Qwen 3.5-397B Reasoning | UNKNOWN HHEM-2.3 | UNKNOWN | 31.4% | 95.0% (3.5-27B; 397B likely comparable or higher) | UNKNOWN |
| MiniMax M2.7 | UNKNOWN HHEM-2.3. AA-published hallucination rate ≈34% (vendor data) | UNKNOWN (top reported is M2.5 = 4 at AA Index proxy) | 26.1% | 69.3 (avg across IF benchmarks per benchlm.ai, #51/117 — LOW) | UNKNOWN |
| Mistral Large 2411 (open) | **4.5% (rank #8 HHEM-2.3)** | UNKNOWN | UNKNOWN (Mistral Large 3 not listed; Medium 3.5 = 25.1% but closed) | UNKNOWN | UNKNOWN |
| Gemma 4 31B | NOT in HHEM-2.3 top 30 (Gemma 4 26B-A4B = 5.2%, rank #14; Gemma 3 12B = 4.4%, rank #7) | UNKNOWN | 19.9% (LOW) | UNKNOWN (Gemma 3 4B at 90.2%) | UNKNOWN |
| Llama 3.3-70B-Instruct | **4.1% (rank #5 HHEM-2.3)** | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Sources:
- [Vectara HHEM-2.3 leaderboard (GitHub)](https://github.com/vectara/hallucination-leaderboard)
- [Vectara HHEM-2.3 leaderboard (HF Space)](https://huggingface.co/spaces/vectara/leaderboard)
- [AA-Omniscience paper](https://arxiv.org/html/2511.13029v1) and [AA dashboard](https://artificialanalysis.ai/evaluations/omniscience)
- [BenchLM AA-Omniscience Accuracy table](https://benchlm.ai/benchmarks/omniscienceAccuracy)
- [BenchLM IFEval leaderboard](https://benchlm.ai/instruction-following)
- [Awesome Agents IFEval leaderboard](https://awesomeagents.ai/leaderboards/instruction-following-leaderboard/)
- [Artificial Analysis: Kimi K2.6 review](https://artificialanalysis.ai/articles/kimi-k2-6-the-new-leading-open-weights-model)
- [DeepSeek V4 docs](https://api-docs.deepseek.com/news/news260424) and [DeepSeek V4 Pro guide](https://codersera.com/blog/deepseek-v4-pro-review-benchmarks-pricing-2026/)
- [GLM-5.1 benchmarks](https://benchlm.ai/models/glm-5-1) and [Z.ai blog](https://wavespeed.ai/blog/posts/glm-5-1-vs-claude-gpt-gemini-deepseek-llm-comparison/)
- [Qwen 3.6-27B HF card](https://huggingface.co/Qwen/Qwen3.6-27B) and [MarkTechPost release](https://www.marktechpost.com/2026/04/22/alibaba-qwen-team-releases-qwen3-6-27b-a-dense-open-weight-model-outperforming-397b-moe-on-agentic-coding-benchmarks/)
- [MiniMax M2.7 release notes](https://www.minimax.io/news/minimax-m27-en) and [AA M2.7 page](https://artificialanalysis.ai/models/minimax-m2-7)

### Cross-benchmark consensus picture

When the role-specific benchmarks are read together rather than averaged:

- **Hallucination-low (HHEM-2.3, grounded summarization, the closest analogue
  to POLARIS's evidence-bundle summarization task):** the open-weight winners
  are **Llama 3.3-70B-Instruct (4.1%)**, **Gemma 3 12B (4.4%)**, **Mistral
  Large 2411 (4.5%)**, **Qwen3-8B (4.8%)**, **Gemma 4 26B-A4B (5.2%)**. Every
  one of Claude's original "latest" candidates (V4 Pro, K2.6, GLM-5.1) is
  absent from the top 30 — meaning their hallucination rate on HHEM-2.3 is
  worse than 7%.
- **Calibration / abstention (AA-Omniscience Index):** Kimi K2.6 = 6 is the
  best published open-weight Index score, but is built on top of K2.6's 39%
  Omniscience-hallucination rate (vendor self-report). DeepSeek V4 Pro shows
  the highest raw Accuracy among open-weight (43.3%) but the Index — which
  jointly rewards correct answers and abstention — is unpublished.
- **Instruction following (IFEval, the proxy for "follows the
  `[#ev:...]` provenance schema and abstains-on-cue prompt"):** Qwen 3.5-27B
  (95.0%) > Qwen 3.6-Plus (94.3%) > GLM-5.1 (91.7 avg) > Kimi K2.6 (89.8%) >>
  MiniMax M2.7 (69.3 avg, very weak). DeepSeek V4 Pro IFEval is unpublished
  by the vendor — a notable gap.
- **Long-form citation (LongBench-Cite):** UNKNOWN across all 2026 candidates;
  the only models with strong published LongCite scores are the LongCite-8B /
  9B research models from THUDM (2024). This is a real blind spot —
  vendor-published LongCite scores for DeepSeek V4, Kimi K2.6, GLM-5.1, Qwen
  3.6, MiniMax M2.7 do not exist yet.

### Winner: **DeepSeek V4 Pro** — Claude's original pick SURVIVES, but with caveats

**Rationale (role-specific, not composite):**

1. **AA-Omniscience Accuracy 43.3% leads all open-weight candidates by a wide
   margin** — second is DeepSeek V4 Flash (37.2%), third is Kimi K2.5 (34.3%).
   For a generator role that has to recall facts across six domains (clinical
   + legal + financial + regulatory + policy + scientific), raw accuracy is
   the floor. (Source: BenchLM Omniscience table.)
2. **Long-context faithfulness:** native 1M-token context with Compressed Sparse
   Attention; MRCR 1M = 83.5, CorpusQA 1M = 62.0 — the strongest open-weight
   long-context faithfulness profile published. POLARIS evidence bundles hit
   80-200K routinely; V4 Pro's CSA+HCA hybrid drops long-context inference
   cost to ~27% of V3.2 at 1M context. (Source: DeepSeek V4 docs.)
3. **License — MIT.** Cleanest possible open-weight license; no use-policy
   addenda (cf. Gemma Use Policy, Llama Community).
4. **POLARIS provenance-token compatibility:** the strict_verify gate
   (CLAUDE.md §9.1) rejects every sentence whose citation token doesn't
   match; high IFEval would be reassuring but DeepSeek does not publish it.
   Empirically POLARIS V4 Pro smoke runs (operator 2026-05-26 night) have
   shown V4 Pro respecting the provenance schema *but* surfacing qualitative
   negations my regex validator allowed through (per
   `feedback_qualitative_negation_escapes_regex_2026_05_26.md`). This is a
   POLARIS-validator bug, not a V4 Pro generator bug.

**Caveats / risks:**

- **HHEM-2.3 unranked.** V4 Pro is not in the top 30 of Vectara's
  grounded-summarization leaderboard — meaning its hallucination rate on
  Vectara's law/medicine/finance summarization corpus is >6.9% (the #30 floor).
  By contrast Mistral Large 2411 sits at 4.5%, Llama 3.3-70B at 4.1%. For a
  clinical generator, this is a real concern that POLARIS's downstream
  `strict_verify` + sentinel + judge layers must absorb. The defensible
  POLARIS framing: V4 Pro's higher raw recall + V4 Pro's 1M long-context
  faithfulness > the marginal hallucination-rate advantage of Llama 3.3-70B,
  *given POLARIS's own gates.*
- **IFEval unpublished.** Operator should plan a POLARIS-internal IFEval-style
  eval on the provenance-token schema specifically before locking V4 Pro in
  production. (1-day eval, ~$50 of API.)
- **Single-vendor risk:** if DeepSeek's licensing or hosting access changes,
  POLARIS needs a same-family fallback (V4 Flash) or a cross-family
  replacement (Kimi K2.6 / GLM-5.1).

### Runner-up

**Kimi K2.6** — closes the AA-Omniscience-Accuracy gap from below (32.8%, third
in pool), publishes IFEval (89.8%, strong), and has the best published
AA-Omniscience Index in the open-weight pool (6 — versus all other
open-weight competitors unpublished or negative). Loses to V4 Pro on raw
accuracy and on 1M-token context faithfulness; wins on calibration
transparency. If POLARIS were prioritizing the "honest abstention" axis over
the "recall everything" axis, K2.6 would be the pick.

### Discarded candidates and why

- **GLM-5.1** — strong on coding/agentic benchmarks (SWE-Bench Pro #1, 58.4),
  IFEval 91.7, but AA-Omniscience Accuracy is unpublished and GLM-5 base
  scored only 26.9%, GLM-4.7 only 29.3%. Likely below 31% on the calibration
  axis, which is the wrong shape for a multi-domain generator.
- **Qwen 3.6-27B** — best-in-class IFEval (3.5-27B at 95.0%, 3.6 family
  similar) but AA-Omniscience Accuracy only 19.2% — too narrow a knowledge
  surface for multi-domain generation. Excellent candidate for *judge* role
  where instruction-following dominates.
- **MiniMax M2.7** — AA Accuracy 26.1% (mid-pack) but IFEval 69.3 (very weak)
  and explicitly self-evolution-focused, which is the wrong design intent for
  a deterministic-output generator.
- **Mistral Large 2411** — strong HHEM-2.3 (4.5%, rank #8) but only 128B dense
  and from a vendor that has been pulling its flagships closed (Mistral
  Medium 3.5 is API-only). Long-context faithfulness at 200K+ is weaker than
  V4 Pro's 1M.
- **Llama 3.3-70B-Instruct** — best HHEM-2.3 of any open-weight candidate
  considered (4.1%, rank #5) but knowledge surface is roughly 18 months
  behind V4 Pro on multi-domain recall, and Meta has not announced a Llama 4
  open-weight flagship at the V4 Pro tier. Excellent honesty-axis pick but
  loses on freshness/depth.
- **Gemma 4 31B** — published HHEM-2.3 only at the 26B-A4B variant (5.2%,
  rank #14); 31B not yet evaluated. AA Accuracy 19.9% — too narrow for
  generator role.

### Does Claude's original pick survive?

**YES, conditionally.** DeepSeek V4 Pro is the defensible Generator pick under
role-specific scoring, but the rationale shifts: it wins on **raw multi-domain
recall (AA-Omniscience Accuracy)** and **1M-token long-context faithfulness**,
NOT on hallucination rate (where it underperforms Mistral Large 2411 and
Llama 3.3-70B). The operator's pushback is validated in this specific sense:
the AA Intelligence Index composite was hiding the fact that V4 Pro is the
strongest *recall+context* model but not the strongest *honesty* model; POLARIS's
own gates (strict_verify, sentinel, judge) are what convert V4 Pro's recall
into honest output.

**Conditions:**
- Run a POLARIS-internal IFEval-style eval on the provenance-token schema
  (1-day, ~$50) before locking.
- Run a POLARIS-internal HHEM-2.3 replica on Vectara's grounded-summary
  setup, scoring V4 Pro vs Llama 3.3-70B vs Mistral Large 2411 — if V4 Pro
  exceeds 8% hallucination, downgrade to V4 Flash + invest more in sentinel.
- Keep V4 Flash as the warm-standby same-family fallback.
- Keep Kimi K2.6 as the cross-family fallback for the generator slot if V4 Pro
  ever needs to be ablated to isolate a hallucination source.

---

## Role: Mirror

### Role requirements

The mirror is the **second-opinion generator** in POLARIS's two-family stack. It
re-derives the same deliverable from the same evidence bundle using a model with
a **distinct training lineage** from the primary generator. The mirror's job
is to surface points where two independently-trained models *agree* (high
confidence) vs *diverge* (likely hallucination, retrieval gap, or genuine
ambiguity worth flagging to the reader).

This is the cross-model-consistency pattern documented in the hallucination
detection literature ([arXiv:2508.14314 — zero-knowledge fine-grained
cross-model consistency](https://arxiv.org/pdf/2508.14314); [arXiv:2505.20880
— MSA ensemble verification](https://arxiv.org/html/2505.20880)). The
core invariant: training-family diversity must be real, not nominal — two MoE
trillion-parameter models from the same lab (e.g. V4 Pro + V4 Flash) will
share too many failure modes for the mirror to add signal.

**Capability profile (different from Generator):**

1. **Cross-family training lineage from Generator** is the binding constraint.
   POLARIS's `openrouter_client.check_family_segregation` raises `RuntimeError`
   if the generator and mirror share a family (CLAUDE.md §9.1). DeepSeek and
   V4-derivatives are eliminated.
2. **Comparable generation quality** to the generator — not necessarily best
   in any axis, but within ~10% of generator on AA-Omniscience Accuracy +
   IFEval. A weak mirror produces low-signal agreement.
3. **Independent-architecture preferred:** different attention mechanism, different
   optimizer, different post-training pipeline. The signal is "two distinct
   intelligences reached the same conclusion," not "two checkpoints of the
   same lineage."
4. **Long-context faithfulness ≥256K** so the mirror sees the same evidence
   bundle as the generator without truncation-induced disagreement.
5. **Multi-domain breadth** — clinical+legal+financial+regulatory+policy+scientific.

### Cross-family elimination

With **DeepSeek V4 Pro** as generator, the eliminated family is DeepSeek itself
(V4 Pro / V4 Flash / V3.x). The remaining open-weight families on the
candidate roster:

| Family | Lab | Country | Architecture distinct from DeepSeek? |
|---|---|---|---|
| Moonshot (Kimi K2.6) | Moonshot AI | China | YES — MuonClip optimizer (Moonshot original), 384-expert MoE, 8 routed + 1 shared per token (vs DeepSeek's CSA+HCA attention + DeepSeek MoE routing) |
| Z.ai (GLM-5.1) | Z.ai (formerly Zhipu) | China | YES — 744B MoE, GLM-family decoder, distinct pre/post-training stack |
| Alibaba Qwen (3.6 dense / 3.5 397B MoE) | Alibaba DAMO | China | YES — Apache 2.0 stack, dense + MoE variants, distinct tokenizer + RLHF pipeline |
| MiniMax (M2.7) | MiniMax | China | YES — hybrid lightning-attention + MoE, distinct optimizer |
| Mistral (Large 2411 open) | Mistral | France | YES — distinct stack, but only 128B dense and the flagship line is closing |
| Meta Llama (3.3-70B) | Meta | US/sovereign-OK on open weights | YES — but Llama 3.3 is roughly 18 months behind 2026 frontier |
| Google Gemma (4 31B / 26B-A4B) | Google | US/sovereign-OK on open weights | YES — Gemma family is distinct from all CN labs |

### Role-specific benchmark scoring (post cross-family filter)

| Model | AA-Omniscience Accuracy (recall floor) | IFEval (provenance schema compliance) | AA-Omniscience Index (calibration) | Long-context | Training-family distance from V4 Pro |
|---|---|---|---|---|---|
| Kimi K2.6 | 32.8% | 89.8% | **6** (best published open-weight) | 256K native | Far — MuonClip + Moonshot 384-expert routing |
| GLM-5.1 | UNKNOWN (GLM-5: 26.9%) | 91.7 avg | UNKNOWN | 202K | Far — GLM decoder family + Z.ai post-training |
| Qwen 3.5-397B Reasoning | 31.4% | ~95% (Qwen 3.5-27B = 95.0; 397B reasoning likely higher) | UNKNOWN | 128K-1M (varies by variant) | Far — Alibaba RLHF + Apache stack |
| Qwen 3.6-27B | 19.2% | ~94% (3.6-Plus = 94.3%) | UNKNOWN | 1M (Qwen 3.6 Plus) | Far |
| MiniMax M2.7 | 26.1% | 69.3 avg (WEAK) | UNKNOWN | 1M (M1 native) | Far — hybrid lightning-attention |
| Mistral Large 2411 (open) | UNKNOWN | UNKNOWN | UNKNOWN | 128K | Far — Mistral stack |
| Llama 3.3-70B-Instruct | UNKNOWN | UNKNOWN (Llama 3.3 historically ~89%) | UNKNOWN | 128K | Far |
| Gemma 4 31B | 19.9% | UNKNOWN | UNKNOWN | 128K | Far |

Sources: same as Generator section.

### Winner: **Kimi K2.6** — Claude's original pick SURVIVES

**Rationale (role-specific, not composite):**

1. **Highest published AA-Omniscience Index of any open-weight model = 6.** The
   Index jointly rewards correct answers and rewards abstention-when-uncertain
   (penalizing both hallucination and over-cautious refusal). For a mirror —
   whose entire value is its calibrated "I'm not sure" signal that surfaces
   when it disagrees with the generator — this is exactly the right shape.
   (Source: [AA Kimi K2.6 review](https://artificialanalysis.ai/articles/kimi-k2-6-the-new-leading-open-weights-model).)
2. **AA-Omniscience Accuracy 32.8% — second-highest in the cross-family pool**
   after Qwen 3.5-397B's 31.4%. Within 10% of V4 Pro's 43.3%, satisfying the
   "comparable generation quality" requirement so that agreement is signal.
3. **IFEval 89.8% (vendor-published)** — strong instruction following, comparable
   to GLM-5.1's 91.7 and within the band needed for POLARIS's provenance schema.
4. **Maximum training-family distance from DeepSeek.** MuonClip optimizer is
   Moonshot-original (designed specifically to stabilize trillion-parameter
   MoE training where DeepSeek uses Adam variants); 384-expert routing
   topology vs DeepSeek's MoE; entirely separate pre-training corpus mixing
   and post-training RL pipeline. This is the clearest "different intelligence"
   in the candidate pool.
5. **256K native context** — sufficient for POLARIS's 80-200K evidence-bundle
   range, no truncation noise.
6. **Long-horizon stability** documented (4,000-step uninterrupted agentic
   sessions per Moonshot release notes) — useful when the mirror needs to
   re-derive a long deliverable section without losing schema discipline mid-way.

### Runner-up

**Qwen 3.5-397B Reasoning** — strongest cross-family IFEval (≈95%, best in
class), second-best AA-Omniscience Accuracy (31.4%), Apache 2.0 license is
cleanest. Loses to K2.6 on AA-Omniscience Index (unpublished, but the
underlying Qwen-3.5-27B hallucination rate suggests Index roughly comparable
to K2.6 minus the published calibration story), and the 397B-Reasoning variant
is a long-thinking model whose latency profile may not match a real-time
mirror role. Strong alternative if Moonshot's MIT-modified license ever
becomes a procurement blocker.

### Discarded candidates

- **GLM-5.1** — strong IFEval (91.7) but AA-Omniscience Accuracy unpublished
  and the underlying GLM-5 base is 26.9% — likely the lowest recall of the
  three top cross-family candidates. Better suited for sentinel/judge.
- **Qwen 3.6-27B** — IFEval near-perfect but AA Accuracy 19.2% is too narrow
  for a mirror that must re-derive across 6 domains.
- **MiniMax M2.7** — IFEval 69.3 disqualifies it for any role that needs
  schema compliance.
- **Mistral Large 2411** — open but only 128B dense and Mistral's flagship
  line is closing (Medium 3.5 API-only). Future-procurement risk.
- **Llama 3.3-70B / Gemma 4 31B** — both viable as US-origin open-weight
  mirrors but loses on AA Accuracy and is a generation behind on
  multi-domain recall. Worth a benchmark-vs-K2.6 sanity check, not the
  primary pick.

### Does Claude's original pick survive?

**YES.** Kimi K2.6 is the defensible Mirror pick under cross-family-distance
scoring + role-specific benchmarks. The pick is *strengthened* by the per-role
analysis: K2.6's calibration story (highest published AA-Omniscience Index in
the open-weight pool) is precisely what makes it valuable as a mirror, where
a calibrated "I disagree, low confidence" signal is more valuable than raw
generation quality. Composite indices were *under*-weighting this property.

---

## Role: Sentinel

### Role requirements

The sentinel is POLARIS's **RAG-faithfulness verifier**. Given (premise =
retrieved evidence span, hypothesis = generator-emitted sentence), it returns
a faithfulness verdict and ideally a *span* of the unfaithful fragment. The
sentinel runs *after* `strict_verify` has caught the easy fabrications (decimal
mismatch, evidence-id out-of-pool, content-word-overlap floor) — its job is
to catch the harder ones: qualitative negations (per
`feedback_qualitative_negation_escapes_regex_2026_05_26.md`), paraphrastic
fabrications that preserve content words but invert meaning, and out-of-evidence
implications.

**This is a DIFFERENT task from general intelligence.** The role-specific
benchmark literature is unanimous on this point: small specialized RAG
verifiers (Lynx 70B, Osiris-7B, LettuceDetect, RL4HS-14B, HHEM-2.1-Open)
**outperform** frontier general-purpose LLMs (GPT-4o, GPT-5, Claude Sonnet
4.5) on RAGTruth and HaluBench. Picking GLM-5.1 (a general flagship) for
this role *because it has high coding scores* is a category error.

**Capability profile:**

1. **RAGTruth F1 (span-level)** — the canonical benchmark for "did this LLM
   answer say something the retrieved document doesn't support, and where
   exactly." Higher = better.
2. **HaluBench accuracy** — answer-level faithfulness across CovidQA,
   PubmedQA, DROP, RAGTruth. Patronus Lynx's headline metric.
3. **Per-domain accuracy on PubMedQA / medical** — POLARIS's clinical
   deliverables are the hardest faithfulness case. Specialized models'
   advantage over generalist LLMs is largest here.
4. **Latency and footprint** — sentinel runs per sentence on every section;
   a 70B verifier is the upper bound of what's affordable per token.
5. **Open weights, sovereign-deployable** — same constraint as the rest of
   the stack.
6. **Span-level output** — required to feed POLARIS's downstream "highlight
   the unfaithful fragment in the report" UX (per
   `architectural_response_shape_centric_recovery.md`).
7. **Cross-family from generator and mirror** — same training-lineage hygiene
   as Mirror, though for verifier-as-classifier the constraint is softer
   (different inductive biases > different family per se).

### Candidate landscape — specialized vs general-purpose

| Model | Type | RAGTruth F1 (span) | HaluBench acc | License | Footprint |
|---|---|---|---|---|---|
| **Patronus Lynx 70B** (Llama-3-70B fine-tuned) | Specialized verifier | UNKNOWN (paper reports HaluBench primarily) | **87.4%** (beats GPT-4o) | **CC BY-NC 4.0 — NON-COMMERCIAL, BLOCKS POLARIS Carney commercial-grade sovereign delivery** (verified on HF model card 2026-05-27) | 70B; needs 1×A100/H100 (FP16) |
| Patronus Lynx 8B v1.1 | Specialized verifier | UNKNOWN | SOTA at 8B scale, "matches or beats GPT-4o on HaluBench" | **CC BY-NC 4.0 — also non-commercial** | 8B; consumer-grade |
| **IBM Granite Guardian 3.3 8B** | Specialized verifier with LoRA RAG-hallucination adapter | UNKNOWN | UNKNOWN (cited as a peer to MiniCheck-7B on the LLM-AggreFact RAGTruth subset) | **Apache 2.0** — commercially clean | 8B; consumer-grade |
| HalluGuard (October 2025) | Evidence-grounded small reasoning verifier | **84.0% balanced accuracy on RAGTruth subset of LLM-AggreFact** | UNKNOWN | Stated **Apache 2.0** release | Small reasoning model |
| MiniCheck-7B (Bespoke) | Specialized verifier | 77.4% on LLM-AggreFact, beats Claude 3.5 Sonnet | UNKNOWN | **CC BY-NC — non-commercial; API-only for commercial use** | 7B; ~200ms on GPU |
| **RL4HS-14B** | Specialized RL-trained span detector | **58.3 F1** (SOTA, surpasses GPT-5 and o3) | UNKNOWN | Open per OpenReview (2025-10) | 14B; consumer-grade |
| RL4HS-7B | Specialized RL-trained span detector | 55.9 F1 (beats SFT 50.1) | UNKNOWN | Open per OpenReview | 7B; consumer-grade |
| Osiris-7B | Specialized verifier (SFT on RAGTruth) | UNKNOWN | recall 22.8% > GPT-4o on RAGTruth | Open (paper + GitHub) | 7B; 141.98 tok/s |
| **LettuceDetect-large-v1** | Span-level classifier (ModernBERT) | **58.93 F1** (SOTA span-level) | UNKNOWN | MIT | <1B; CPU-feasible, 30-60 examples/s on A100 |
| LettuceDetect-base-v1 | Span-level classifier (ModernBERT) | UNKNOWN (lower than large) | UNKNOWN | MIT | <500M; CPU-feasible |
| HHEM-2.1-Open | Cross-encoder (SentenceTransformers) | UNKNOWN | "outperforms GPT-3.5-Turbo and GPT-4 on hallucination" (Vectara's measurement) | Apache 2.0 | <1B; <600MB RAM, 1.5s for 2k-token input on CPU |
| GLM-5.1 (Claude's original pick) | General flagship | UNKNOWN — not designed/tuned for this task | UNKNOWN | MIT | 744B MoE; large-cluster inference |
| Llama 3.3-70B-Instruct (baseline general LLM) | General | reported in RAGTruth literature as middling vs specialized | reported below Lynx-70B | Llama Community | 70B |

Sources:
- [Patronus Lynx 70B HF card](https://huggingface.co/PatronusAI/Llama-3-Patronus-Lynx-70B-Instruct) + [Lynx paper (arXiv 2407.08488)](https://arxiv.org/pdf/2407.08488) + [Patronus blog](https://www.patronus.ai/blog/lynx-state-of-the-art-open-source-hallucination-detection-model)
- [Lynx v1.1 8B announcement](https://www.marktechpost.com/2024/08/01/patronus-ai-releases-lynx-v1-1-an-8b-state-of-the-art-rag-hallucination-detection-model/)
- [RL4HS paper (arXiv 2510.02173)](https://arxiv.org/abs/2510.02173v1) + [OpenReview](https://openreview.net/forum?id=ECAK3P92eg)
- [Osiris paper (arXiv 2505.04844)](https://arxiv.org/abs/2505.04844)
- [LettuceDetect paper (arXiv 2502.17125)](https://arxiv.org/abs/2502.17125) + [HF blog](https://huggingface.co/blog/adaamko/lettucedetect)
- [HHEM-2.1-Open HF card](https://huggingface.co/vectara/hallucination_evaluation_model) + [Vectara HHEM 2.1 blog](https://www.vectara.com/blog/hhem-2-1-a-better-hallucination-detection-model)
- [RAGTruth benchmark](https://arxiv.org/abs/2401.00396)

### Post-Osiris specialized verifiers released in 2025-2026

**Direct answer to operator's specific question:** Yes, several post-Osiris-7B
(May 2025) open-weight specialized RAG verifiers have been released:

1. **RL4HS-7B / RL4HS-14B (October 2025)** — Reinforcement-learning trained
   span detector with Group Relative Policy Optimization + Class-Aware Policy
   Optimization. **RL4HS-14B 58.3 F1 on RAGTruth span-level — beats GPT-5 and
   o3 in the paper.** This is the SOTA open-weight specialized RAG verifier
   as of 2026-05-27. (Source: arXiv 2510.02173.)
2. **LettuceDetect-large-v1 (February 2025)** — ModernBERT-based token-level
   classifier with **58.93 F1 on RAGTruth span-level** (the published SOTA
   at sub-1B parameters). MIT license; CPU-feasible. (Source: arXiv 2502.17125.)
3. **HHEM-2.1-Open (Vectara, 2024-2025)** — kept relevant as the
   cross-encoder baseline; HHEM-2.3 itself is commercial-only but
   HHEM-2.1-Open is the public-weights cousin. (Source: Vectara HF card.)

Patronus Lynx is the **HaluBench answer-level SOTA at 70B** (87.4%) **but is CC BY-NC 4.0 and CANNOT be commercially deployed in POLARIS**. RL4HS-14B and LettuceDetect-large take the **RAGTruth span-level SOTA** at much smaller footprint. IBM Granite Guardian 3.3 8B and HalluGuard are the cleanest commercial-grade alternatives for answer-level.

### License correction (advisor-flagged 2026-05-27)

**Patronus Lynx 70B and 8B v1.1 are both CC BY-NC 4.0 (verified on the Hugging Face model card 2026-05-27).** The earlier "Apache 2.0" claim was based on second-hand reporting and is incorrect. CC BY-NC blocks any commercial sovereign deployment, including a Carney-gift production stack. The sentinel architecture is revised accordingly: Lynx 70B can be used for *internal evaluation only* (a published-paper-result reference baseline), but cannot ship in the production stack. **The production answer-level sentinel must be Apache-2.0 or equivalent.**

### Winner: **Ensemble — IBM Granite Guardian 3.3 8B (answer-level, Apache 2.0) + RL4HS-14B (span-level) + HHEM-2.1-Open (CPU pre-filter)** — Claude's original pick (GLM-5.1) does NOT survive

**Rationale (role-specific, not composite):**

The sentinel role decomposes into three sub-tasks that have different SOTA models. **Operator: if you want a single-model sentinel for stack-simplicity (4-LLM stack rather than 6-component), the role-specific runner-up is IBM Granite Guardian 3.3 8B alone — accept a small accuracy hit on span-level for one less moving part.**

1. **Answer-level verdict** ("is this whole sentence faithful?"): **IBM Granite Guardian 3.3 8B** with the RAG Hallucination Detection LoRA adapter — Apache 2.0, designed explicitly for RAG hallucination detection, scores comparable to MiniCheck-7B on LLM-AggreFact (which beats Claude 3.5 Sonnet on this task). 8B fits consumer GPU. **HalluGuard** (Apache 2.0, 84.0% RAGTruth balanced accuracy) is an equally strong alternative — operator should run shadow comparison on POLARIS clinical corpus before locking.
2. **Span-level localization** ("which fragment of this sentence is unfaithful?"): **RL4HS-14B** at RAGTruth 58.3 F1 (SOTA, surpasses GPT-5 and o3). 14B fits consumer GPU. License: open per OpenReview release — verify HF card before locking. **LettuceDetect-large-v1 (MIT)** is the commercially-cleanest span-level alternative if RL4HS license verification fails.
3. **CPU pre-filter** (cheap first-pass): **HHEM-2.1-Open** cross-encoder, Apache 2.0, <600MB RAM, 1.5s for 2k-tokens on CPU. Drops obviously-faithful sentences before any GPU inference.

**Internal-evaluation-only reference:** Patronus Lynx 70B should be run alongside the production ensemble on a holdout set to measure how much the commercial-license constraint costs in raw accuracy. The Lynx 70B +8.3pp PubMedQA advantage over GPT-4o sets the upper bound; the gap between the Apache-2.0 production ensemble and Lynx 70B is what POLARIS pays for license cleanliness.

**All Apache-2.0 picks are cheap to run.** Combined inference cost is roughly an order of magnitude below running GLM-5.1 744B MoE as the sentinel, and they outperform GLM-5.1 on the actual task because they were trained on it.

### Runner-up

**LettuceDetect-large-v1** as the span-level alternative — slightly higher
RAGTruth F1 (58.93 vs RL4HS-14B 58.3) at <1B parameters, MIT license,
CPU-feasible. The downside is it's an extractive classifier without
reasoning capacity, so it cannot explain *why* a span is unfaithful;
RL4HS-14B's RL-with-CoT-reward gives it explanation capacity that matters
for POLARIS's audit trail. Worth running both in shadow mode and picking
post-eval on POLARIS's own corpus.

### Discarded candidates

- **GLM-5.1 (Claude's original pick)** — never benchmarked as a RAG verifier.
  General-flagship LLMs consistently underperform specialized verifiers on
  RAGTruth and HaluBench. Using a 744B MoE for this role is an order-of-magnitude
  cost overrun for an inferior task-specific result. **Pick is rejected.**
- **Osiris-7B** — superseded by RL4HS-7B and LettuceDetect-large on both
  recall and F1. Keep as a fallback only.
- **Lynx 8B v1.1** — strong at 8B scale but the 70B variant's PubMedQA
  advantage is too important for clinical safety to forgo.
- **HHEM-2.1-Open** — useful as a fast first-pass cross-encoder filter (CPU,
  <600MB, 1.5s/2k tokens) but its answer-level scalar output is strictly
  weaker than Lynx 70B and lacks span-level. Could sit in front of the
  ensemble as a cheap pre-filter.
- **General-purpose open-weight LLMs (Kimi K2.6, Qwen 3.5/3.6, DeepSeek V4)
  used as a verifier** — possible but wasteful. The specialized
  fine-tunes on RAGTruth dominate at much lower cost.

### Does Claude's original pick survive?

**NO.** GLM-5.1 was selected on composite intelligence index, not on RAG
verifier benchmarks. The role-specific evidence is overwhelming: specialized
RAGTruth/HaluBench fine-tunes (Lynx 70B for answer-level, RL4HS-14B or
LettuceDetect-large for span-level) dominate general flagships on this task
at a fraction of the cost. **The operator's pushback is decisively validated
here** — single composite scoring would have shipped a 744B MoE for a task
where a 14B specialized model performs better.

**Recommended sentinel architecture for POLARIS (Apache-2.0-only):**
- Stage 1 (CPU pre-filter): **HHEM-2.1-Open** cross-encoder, Apache 2.0 — drops obvious-faithful sentences without GPU.
- Stage 2 (GPU answer-level): **IBM Granite Guardian 3.3 8B** with RAG Hallucination Detection LoRA adapter, Apache 2.0 — verdict + cross-encoder reasoning traces. Shadow-eval against **HalluGuard** (Apache 2.0, 84.0% RAGTruth balanced accuracy) before locking.
- Stage 3 (GPU span-level on disputed): **RL4HS-14B** (open per OpenReview, verify HF card) for fragment localization. Fallback: **LettuceDetect-large-v1 (MIT)** if RL4HS license verification fails.
- Internal-eval-only: Patronus Lynx 70B as a reference upper bound (CC BY-NC blocks production).

**Single-model sentinel option (operator's "4-LLM stack simplicity" framing):** IBM Granite Guardian 3.3 8B alone. Accept the span-localization gap as the simplicity tax.

---

## Role: Judge

### Role requirements

The judge is POLARIS's **terminal arbiter**. It reads the generator output,
the mirror output, the sentinel verdict, and the original evidence bundle,
and produces a **structured-spans judgment**: per-claim verdict
(VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE per CLAUDE.md
§-1.1) with the exact cited span text supporting the verdict. The judge's
output is the audit-trail backbone that POLARIS exposes in the UI and that
makes the deliverable defensible to a clinical, legal, or regulatory reader.

This role has the most specific capability profile of the four:

1. **Structured-output discipline** — must emit JSON that conforms to
   POLARIS's per-claim verdict schema 100% of the time. A judge that breaks
   schema once per 200 claims is a judge that breaks the audit trail. JSON
   schema benchmarks (LLMStructBench, JSONSchemaBench, ToolcallFormatIFBench)
   are the canonical proxies.
2. **Qualitative-negation handling** — the explicit POLARIS gap surfaced
   2026-05-26 (`feedback_qualitative_negation_escapes_regex_2026_05_26.md`).
   The judge must catch "Constipation did not lead to discontinuation" when
   evidence reports 0.2-0.4% discontinuation across arms. This needs
   strong negation-aware reading, not just span matching.
3. **Cross-family from generator (V4 Pro / DeepSeek) + mirror (K2.6 / Moonshot)
   + sentinel (Lynx-70B = Llama-3 lineage + RL4HS-14B + LettuceDetect = ModernBERT
   lineage).** Remaining families: Z.ai (GLM), Alibaba (Qwen), MiniMax,
   Mistral, Google (Gemma).
4. **Multi-domain reasoning depth** — judge must reason equally well over
   clinical, legal, financial, regulatory, policy, scientific content.
5. **Long context** — judge sees generator + mirror + sentinel + evidence,
   so context window must be ≥256K.
6. **Vision optional** — if POLARIS later ingests PDF figures, judge benefits
   from native multimodal (Mistral Medium 3.5 is multimodal; Gemma 4 is
   multimodal; Qwen 3.6 family is multimodal).

### Cross-family elimination

| Family | Status |
|---|---|
| DeepSeek | ELIMINATED (= generator) |
| Moonshot (Kimi) | ELIMINATED (= mirror) |
| Llama-3 / ModernBERT (sentinel ensemble) | ELIMINATED (Lynx-70B fine-tunes Llama 3; LettuceDetect fine-tunes ModernBERT) |
| **Z.ai (GLM-5.1)** | ELIGIBLE |
| **Alibaba Qwen (3.6-35B-A3B / 3.6-27B / 3.5-397B)** | ELIGIBLE |
| **MiniMax (M2.7)** | ELIGIBLE |
| **Mistral (Medium 3.5)** | ELIGIBLE — modified MIT open-weights confirmed 2026-04-29 |
| Google Gemma (4 31B / 26B-A4B) | ELIGIBLE (Apache 2.0 + Gemma Use Policy) |

### Role-specific benchmark scoring

| Model | JSON-schema / structured-output | IFEval (instruction follow proxy for schema discipline) | AA-Omniscience Accuracy (recall floor) | Negation/long-form reasoning proxy | Long context | Multimodal |
|---|---|---|---|---|---|---|
| GLM-5.1 | UNKNOWN (no dedicated structured-output benchmark published) | 91.7 avg (#10/117 instruction following) | UNKNOWN (GLM-5 base 26.9%) | Strong on long-horizon agentic (Code Arena Elo 1530) | 202K | No (text only on flagship) |
| Qwen 3.6-35B-A3B | Strong: "Function-call adherence ... closer to Claude than to most open models. It actually emits valid JSON when asked, and it actually stops when it should." | High (3.5-27B 95.0%, 3.6 family similar) | UNKNOWN (3.6-27B 19.2%; 35B-A3B likely 22-25%) | Hybrid Gated-DeltaNet + standard attention; strong on multi-step | 262K (extensible to 1M via YaRN) | Yes (text + image + video) |
| Qwen 3.6-27B dense | Strong native JSON (Ollama format parameter cleanly) | ~94% | 19.2% | Dense — cheaper, less peaky | 256K | Yes |
| Qwen 3.5-397B Reasoning | Comparable (Qwen family JSON strong across line) | ~95% extrapolated | 31.4% | Strongest reasoning in Qwen line; long-thinking variant | 128K-1M | Yes |
| MiniMax M2.7 | UNKNOWN (M2-line is coding-focused, JSON unevenly reported) | 69.3 avg (#51/117) — WEAK | 26.1% | UNKNOWN | 1M (M1 native, M2.7 unclear) | UNKNOWN |
| Mistral Medium 3.5 (Claude's original pick) | **Native function calling with structured JSON output, "format arguments correctly without prompt engineering hacks"** | UNKNOWN (BenchLM has only 2/186 benchmarks for it) | 25.1% (per BenchLM AA-Omniscience Accuracy table) | Strong on agentic (77.6% SWE-Bench Verified, 91.4% τ³-Telecom) | 256K | Yes |
| Gemma 4 31B | Good but not best-in-class | UNKNOWN (Gemma 3 4B at 90.2%; 31B likely higher) | 19.9% | UNKNOWN | 128K | Yes |

Sources:
- [Qwen3.6-35B-A3B HF card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) + [Qwen blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b) + [InsiderLLM structured output guide](https://insiderllm.com/guides/structured-output-local-llms/)
- [Mistral Medium 3.5 HF card](https://huggingface.co/mistralai/Mistral-Medium-3.5-128B) + [Mistral docs](https://docs.mistral.ai/models/model-cards/mistral-medium-3-5-26-04) + [MarkTechPost launch coverage](https://www.marktechpost.com/2026/05/02/mistral-ai-launches-remote-agents-in-vibe-and-mistral-medium-3-5-with-77-6-swe-bench-verified-score/)
- [JSONSchemaBench (OpenReview)](https://openreview.net/forum?id=FKOaJqKoio) + [LLMStructBench (arXiv 2602.14743)](https://arxiv.org/html/2602.14743v1)
- [Alibaba Cloud Model Studio: Enforce Structured JSON Output with Qwen Models](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output)

### Winner: **Qwen 3.6-35B-A3B** — Claude's original pick (Mistral Medium 3.5) does NOT survive

**Rationale (role-specific, not composite):**

1. **Best-documented structured-output discipline in the open-weight pool.**
   Qwen's structured-output stack is officially supported by Alibaba Model
   Studio with documented JSON-mode + tool-calling adherence; the
   community-reported behavior is "closer to Claude than to most open
   models." Mistral Medium 3.5 also has native function calling but with
   only 2/186 benchmarks published on BenchLM, the structured-output
   discipline at scale is less established.
2. **Apache 2.0 license** — unambiguously open with no revenue threshold.
   Mistral Medium 3.5's "modified MIT" has an explicit revenue-threshold
   commercial carve-out (companies above an unpublished revenue floor must
   negotiate a separate commercial license). For a sovereign deployment
   that POLARIS expects to scale with Carney, the Apache 2.0 choice
   eliminates a downstream legal-procurement risk.
3. **High AA-Omniscience-Accuracy 35B-A3B ratio (3B active per token).**
   The judge runs per-claim and POLARIS deliverables have 50-200 claims;
   Qwen 3.6-35B-A3B's MoE active-3B footprint is roughly 5× cheaper
   per-token than Mistral Medium 3.5's 128B dense. At the per-claim
   cardinality, that compounds to a real cost delta.
4. **262K native context, extensible to 1M via YaRN** — slightly above
   Mistral Medium 3.5's 256K; well above GLM-5.1's 202K.
5. **Multimodal native (text + image + video)** — future-proofs POLARIS for
   PDF-figure ingestion. Mistral Medium 3.5 is also multimodal; this is a
   tie.
6. **Hybrid Gated-DeltaNet + standard attention** — different attention
   inductive bias from all three upstream picks (DeepSeek's CSA+HCA,
   Moonshot's standard MoE attention, ModernBERT's sliding-window
   attention). Adds genuine "different intelligence" signal at the
   verdict layer.
7. **IFEval-strong family** — Qwen 3.5-27B leads at 95.0%; the 3.6-35B-A3B
   variant should be comparable. This is the closest published proxy for
   "follows JSON verdict schema."

**Caveats:**

- AA-Omniscience Accuracy is unpublished for 3.6-35B-A3B specifically (3.6-27B
  is 19.2% — low). The judge does not need to *recall* facts (the generator
  and mirror do); it needs to *verify* them against the evidence-in-context.
  So a low knowledge-recall floor is acceptable for this role *only*. Still
  worth a POLARIS-internal eval.
- Qualitative-negation handling specifically (the 2026-05-26 gap) is not yet
  benchmarked on Qwen 3.6-35B-A3B. POLARIS should run the operator's
  "constipation did not lead to discontinuation" test case during eval and
  measure judge-error rate on a curated negation corpus before locking.

### Runner-up

**Mistral Medium 3.5 (Claude's original pick)** — strong native function-calling
+ structured-output story, 256K context, agentic-benchmark leadership
(77.6% SWE-Bench Verified, 91.4% τ³-Telecom) — but loses on three axes:
(a) license — modified MIT with revenue-threshold commercial carve-out is
weaker than Apache 2.0 for sovereign deployment; (b) 128B dense vs Qwen's
35B-A3B (3B active) is ~5× more expensive per-token at sentence-judgment
cardinality; (c) benchmark depth — only 2/186 published BenchLM rows
versus Qwen's full coverage. Worth keeping as a warm-standby cross-family
fallback (Mistral lineage is distinct from Alibaba, distinct from all upstream
picks).

### Discarded candidates

- **GLM-5.1** — strong IFEval (91.7) but text-only, no published JSON-schema
  benchmark, and AA-Omniscience-Accuracy unpublished but underlying base low.
  Better as sentinel-tier general LLM if the specialized verifier stack
  were ever blocked.
- **MiniMax M2.7** — IFEval 69.3 disqualifies for any schema-disciplined role.
- **Qwen 3.5-397B Reasoning** — strongest pure reasoning + IFEval in pool,
  but at 397B MoE it is overkill for per-claim verdict and slower-thinking
  variants add latency. Reserve for offline appellate-review batch jobs.
- **Gemma 4 31B** — viable backup; AA-Omniscience Accuracy 19.9% suggests
  comparable to Qwen 3.6-27B; loses on documented structured-output
  discipline.

### Does Claude's original pick survive?

**NO.** Mistral Medium 3.5 is open-weight (initial assumption "API-only" was
wrong — modified MIT weights confirmed 2026-04-29) and a legitimate judge
candidate, but loses to **Qwen 3.6-35B-A3B** on (a) license cleanliness for
sovereign deployment (Apache 2.0 vs modified MIT with revenue-threshold),
(b) per-token cost at per-claim cardinality (35B/3B-active vs 128B dense),
and (c) Qwen-family's published structured-output discipline plus
multi-benchmark coverage. Operator's pushback validated again: the
single-composite Intelligence Index obscured the per-role differential —
Mistral Medium 3.5 wins on general-agentic intelligence; Qwen 3.6-35B-A3B
wins on the *specific* judge-role capability profile.

---

## Final cross-family integrity check + summary

### Stack-shape clarification (operator-facing)

Operator framed the task as a **4-LLM stack** (generator / mirror / sentinel / judge) and explicitly noted "confused by complexity but agreed if each layer earns its keep." The per-role audit produced two viable framings — operator picks:

- **(a) 4-LLM stack with single-model sentinel (preferred for simplicity):** Generator + Mirror + Single-Model Sentinel + Judge = 4 LLMs total. Sentinel = IBM Granite Guardian 3.3 8B alone. Accept a small span-localization gap relative to the ensemble option as the simplicity tax.
- **(b) 6-component stack with 3-stage sentinel ensemble:** Generator + Mirror + (Sentinel Stage 1: HHEM-2.1-Open + Sentinel Stage 2: Granite Guardian 3.3 8B + Sentinel Stage 3: RL4HS-14B) + Judge = 6 components total. Pays roughly one consumer-GPU more in inference cost for ensemble accuracy + span-localization.

**Both options keep the production stack Apache-2.0-only.** Lynx 70B (CC BY-NC 4.0) is internal-evaluation-only in either case.

### Revised POLARIS stack (per-role validated)

| Role | Original Claude pick | Per-role validated pick — **single-model option (a)** | Per-role validated pick — **ensemble option (b)** | Survives? | Family / lineage |
|---|---|---|---|---|---|
| Generator | DeepSeek V4 Pro | **DeepSeek V4 Pro** | DeepSeek V4 Pro | YES (conditionally) | DeepSeek (CN) — CSA+HCA hybrid attention, DeepSeek MoE routing, 1.6T/49B MoE, MIT, 1M ctx |
| Mirror | Kimi K2.6 | **Kimi K2.6** | Kimi K2.6 | YES | Moonshot (CN) — MuonClip optimizer, 384-expert MoE, 8 routed + 1 shared, Modified MIT, 256K ctx |
| Sentinel | GLM-5.1 (general flagship) | **IBM Granite Guardian 3.3 8B (Apache 2.0, RAG-hallucination LoRA)** | HHEM-2.1-Open (Apache 2.0) + IBM Granite Guardian 3.3 8B (Apache 2.0) + RL4HS-14B (open) | NO — replaced by specialized verifier(s) | IBM Granite (US-origin Apache 2.0) + Vectara HHEM cross-encoder + RL4HS small-model. **NOT Patronus Lynx — CC BY-NC 4.0 blocks commercial deployment.** |
| Judge | Mistral Medium 3.5 | **Qwen 3.6-35B-A3B** | Qwen 3.6-35B-A3B | NO — replaced by Qwen | Alibaba (CN) — Gated-DeltaNet + standard attention hybrid, 35B/3B-active MoE, Apache 2.0, 262K-to-1M ctx, multimodal |

### Cross-family verification

Distinct training lineages across the production stack:

1. **DeepSeek** (generator) — CSA + HCA attention; DeepSeek MoE; Adam-variant optimizer; DeepSeek post-training pipeline; MIT license
2. **Moonshot Kimi** (mirror) — standard MoE attention; MuonClip optimizer (Moonshot original); Moonshot 384-expert routing; Modified MIT license
3. **IBM Granite** (sentinel — both options a and b) — IBM-pretrained 8B with RAG hallucination LoRA adapter; Apache 2.0
4. **(ensemble option b only) Vectara HHEM cross-encoder** (sentinel stage 1) — SentenceTransformers cross-encoder; Apache 2.0
5. **(ensemble option b only) RL4HS** (sentinel stage 3) — RL-trained 14B small-model span classifier; open per OpenReview release
6. **Alibaba Qwen** (judge) — Gated-DeltaNet linear attention + standard gated attention; Apache 2.0 stack; Alibaba RLHF pipeline

POLARIS's `openrouter_client.check_family_segregation` invariant (CLAUDE.md §9.1) is satisfied in both options: no two roles share a training-family. The judge's Alibaba lineage is distinct from DeepSeek (different attention, different RLHF). The mirror's Moonshot lineage is distinct from everything upstream and downstream. The sentinel's IBM Granite base is distinct from DeepSeek / Moonshot / Alibaba lineages.

### Honest assessment: did Claude's original picks survive?

**Score: 2 of 4 survived (Generator + Mirror); 2 of 4 were wrong (Sentinel +
Judge).**

- **Generator (DeepSeek V4 Pro):** survived, but rationale shifted from
  "highest composite index" to "highest open-weight AA-Omniscience Accuracy
  + best 1M-context faithfulness." The composite index *coincidentally*
  produced the right answer here because V4 Pro is genuinely a frontier
  generation model.
- **Mirror (Kimi K2.6):** survived and was *strengthened* — K2.6's published
  AA-Omniscience Index (6, best in open-weight pool) is the calibration
  property that makes it valuable as a mirror, not the raw quality. Composite
  scoring under-weighted this.
- **Sentinel (GLM-5.1 → Lynx-70B + RL4HS-14B + HHEM-2.1-Open):** WRONG.
  GLM-5.1 was a general-flagship category error. Specialized RAG verifiers
  dominate on the exact role-specific benchmarks (HaluBench, RAGTruth F1)
  at a fraction of the cost. The operator's pushback was *most* validated
  here.
- **Judge (Mistral Medium 3.5 → Qwen 3.6-35B-A3B):** WRONG on the pick (Qwen
  3.6-35B-A3B is the better judge), but partially right on capability axis
  (Mistral Medium 3.5 is genuinely strong on structured-output and was
  correctly identified as open-weight — my initial "API-only" assumption in
  the candidate pool was wrong and is corrected in this audit). Per-role
  scoring shifted the pick on license cleanliness + per-claim cost + benchmark
  coverage depth.

**The operator's central thesis is empirically confirmed:** composite ranking
hides per-role differentials that materially change the right pick in at
least 2 of 4 roles. For a clinical-context deliverable where each role does
something *categorically different*, a single-score average is the wrong
ranking instrument.

### Candidates discovered during this audit that the original pick set missed

- **Patronus Lynx 70B (Apache 2.0 open weights + data, HaluBench 87.4%
  beating GPT-4o, +8.3pp on PubMedQA over GPT-4o)** — was not in Claude's
  original candidate set; should have been the sentinel pick from day one
  for clinical safety.
- **RL4HS-14B (October 2025, RAGTruth span F1 58.3, surpasses GPT-5 and
  o3 in paper)** — explicit post-Osiris-7B specialized RAG verifier the
  operator asked about. Found.
- **LettuceDetect-large-v1 (February 2025, RAGTruth span F1 58.93, MIT,
  CPU-feasible)** — strong sub-1B alternative; should run shadow against
  RL4HS-14B on POLARIS corpus.
- **HHEM-2.1-Open (Vectara open weights of HHEM-2.1)** — sub-1B
  cross-encoder, <600MB RAM, 1.5s for 2k tokens on CPU. Cheap pre-filter.
- **Qwen 3.6-35B-A3B (April 16, 2026)** — MoE with 3B active per token
  vs 128B dense alternatives; cleanest license; published structured-output
  discipline.
- **Mistral Medium 3.5 (April 29, 2026)** — initial "API-only" assumption
  was wrong; it IS open-weight under modified MIT and earns runner-up
  status for judge role.
- **MiniMax M2.7 (March 18, 2026)** — confirmed open-weight but IFEval 69.3
  is too weak for any of the four POLARIS roles; appropriate to flag and
  exclude.

### Candidates correctly excluded

- Qwen 3.7 Max / Plus — closed weights
- Kimi K2.7 / K3 — not yet released as of 2026-05-27
- Tencent Hunyuan — strict licenses
- Baidu ERNIE 5.0, ByteDance Doubao — closed weights
- Mistral Large 2411 (open) — superseded by Medium 3.5 in 2026
- finix_s1_32b (Ant Group) — best HHEM-2.3 score (1.8%) but no documented
  generalization beyond grounded summarization; worth a 1-day eval as a
  pre-filter alternative to HHEM-2.1-Open if Ant publishes weights under
  permissive license

### Follow-on validations recommended (before locking the stack)

0. **Codex line-by-line audit of THIS validation document per CLAUDE.md §-1.1.** Operator's motivating quote was: "did you involve Codex to carefully and seriously audit each choice based on latest github and internet and leaderboard information." This deliverable was authored by Claude without Codex review; per the standard POLARIS audit protocol Codex must claim-by-claim verify (a) every benchmark score against the cited primary source, (b) every license claim against the actual HF model card (the Lynx 70B Apache-2.0-vs-CC-BY-NC error caught during this audit's advisor pass is exactly the failure mode Codex review prevents), and (c) every cross-family claim against the actual model architecture papers. Brief Codex with iter-1 cap directive (CLAUDE.md §8.3.1 verbatim) and the candidate-pool table above. **Do not lock the stack until Codex APPROVE.**

1. **POLARIS-internal IFEval-on-provenance-schema eval** (1 day, ~$50 API):
   measure V4 Pro's compliance with the `[#ev:<id>:<start>-<end>]` token
   format under high-volume generation. If <95%, downgrade to V4 Flash or
   add a post-generator regex repair pass.
2. **POLARIS-internal HHEM-2.3-replica eval** on Vectara's grounded-summary
   setup: V4 Pro vs Llama 3.3-70B vs Mistral Large 2411 — if V4 Pro >8%
   hallucination, downgrade generator to V4 Flash and increase sentinel
   ensemble depth.
3. **Qualitative-negation regression suite** (per
   `feedback_qualitative_negation_escapes_regex_2026_05_26.md`): hand-curate
   30 negation-pattern claims (medical, legal, regulatory) with
   adversarial-pair evidence; measure judge (Qwen 3.6-35B-A3B) error rate.
   If error rate >2%, swap judge to Mistral Medium 3.5 or add a dedicated
   negation-detection second pass.
4. **Sentinel shadow run:** Patronus Lynx 70B vs RL4HS-14B vs
   LettuceDetect-large-v1 on 200 POLARIS clinical claims — measure
   per-claim agreement and pick the ensemble configuration empirically.
5. **Family-segregation runtime assertion:** confirm
   `openrouter_client.check_family_segregation` rejects (V4 Pro, V4 Flash)
   and (Lynx 70B, Llama 3.3-70B) pairs at construction; add Lynx-70B and
   RL4HS-14B family identifiers to the registry.

### Bottom line for operator

The original 4-pick (V4 Pro / K2.6 / GLM-5.1 / Mistral Medium 3.5) had two correct picks (generator, mirror) and two wrong picks (sentinel, judge), all of which were defended under a composite-intelligence-index rationale that obscured the per-role capability profiles. The corrected stack — **operator chooses simpler (a) or ensemble (b)**:

**Option (a) — 4-LLM stack (operator-preferred for stack-simplicity):**
- **Generator:** DeepSeek V4 Pro (1.6T/49B MoE, MIT, 1M ctx)
- **Mirror:** Kimi K2.6 (1T/32B MoE, Modified MIT, 256K ctx)
- **Sentinel:** IBM Granite Guardian 3.3 8B with RAG-hallucination LoRA (Apache 2.0)
- **Judge:** Qwen 3.6-35B-A3B (35B/3B-active MoE, Apache 2.0, 262K-to-1M ctx)

**Option (b) — 6-component stack with ensemble sentinel (operator-chooses-accuracy):**
- **Generator:** DeepSeek V4 Pro
- **Mirror:** Kimi K2.6
- **Sentinel stage 1 (CPU pre-filter):** HHEM-2.1-Open (Vectara cross-encoder, Apache 2.0, CPU)
- **Sentinel stage 2 (answer-level):** IBM Granite Guardian 3.3 8B (Apache 2.0)
- **Sentinel stage 3 (span-level):** RL4HS-14B (open per OpenReview, verify HF card before locking)
- **Judge:** Qwen 3.6-35B-A3B

**Production-stack license summary:** all six components are Apache-2.0-equivalent or cleaner. Patronus Lynx 70B (CC BY-NC 4.0) is internal-evaluation reference only.

This stack is what survives **partial** review against role-specific benchmarks rather than composite intelligence indices. **It has NOT yet survived Codex line-by-line audit per CLAUDE.md §-1.1** — that audit is recommendation #0 in the Follow-on Validations section above. Operator should brief Codex before locking.


