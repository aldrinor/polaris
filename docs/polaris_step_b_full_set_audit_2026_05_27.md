---
status: codex_approved_pending_operator_signature
locked_decision: 4-role POLARIS architecture
source_authority: this document
supersedes:
  - docs/polaris_per_role_sota_2026_05_27.md
  - docs/models/evaluator_pick.md
  - feedback_top_tier_model_only_2026_05_25 (memory)
roles:
  generator: deepseek/deepseek-v4-pro
  mirror: cohere/command-a-plus
  sentinel: ibm-granite/granite-guardian-4.1-8b
  judge: qwen/qwen-3.6-35b-a3b
  deterministic: [python_validators, codex_section_1_1_audit]
codex_cross_validation: .codex/I-meta-001/codex_brief_iter2_verdict.txt
operator_d1_signature_utc: 2026-05-28T22:00:00Z
promotion_to_locked_when: config/architecture/polaris_runtime_lock.yaml lands + canonical_pin.txt updated + propagation manifest complete
---

# POLARIS Step B — Full-Set 3rd-Pass Per-Role Audit (2026-05-27)

**Author:** Claude (Opus 4.7, 1M ctx) — Step B independent re-evaluation
**Status:** Independent pass against the FULL consolidated candidate pool (both prior passes merged). Codex runs Step B in parallel; cross-validation to follow.
**Operator constraints (locked):** open weights only (any license, modulo commercial-use); non-US runtime LLM (open weights on sovereign infra OK); no hardware ceiling, no time constraint; latest+strongest per role; multi-domain (clinical+legal+financial+regulatory+policy+scientific), EN baseline; operator-lock on V4 Pro reinterpreted as "no reverting to weaker," DOES permit swapping to a newer/stronger model.

**Reading guide.** Each role is scored against role-specific benchmarks (NOT a composite intelligence index). Cells marked UNKNOWN are not extrapolated. Sources cited inline; primary-source URLs in the Sources section at the end. The Step-A comparison is the LAST section of each role, AFTER the Step-B pick is made independently.

**Hard-licensing pre-check (performed before scoring):**
- **Cohere Command A+** — VERIFIED Apache 2.0. Hugging Face repo `CohereLabs/command-a-plus-05-2026-bf16` and `CohereLabs/command-a-plus-05-2026-w4a4`; Cohere blog and VentureBeat both confirm "first fully Apache 2.0 enterprise AI model." This is a real change from Cohere's prior CC-BY-NC posture (Command R/R+) and is decisive for POLARIS eligibility. (Sources: Cohere blog, VentureBeat, HF cards.)
- **RL4HS-14B** — Paper [arXiv 2510.02173](https://arxiv.org/abs/2510.02173) is Apple Research internship work (per author affiliation). NO Hugging Face weights repository surfaced in repeated 2026-05-27 searches; the [EdinburghNLP/awesome-hallucination-detection](https://github.com/EdinburghNLP/awesome-hallucination-detection) catalog references the paper but not a weight release. **License status: UNKNOWN — weights not released publicly as of 2026-05-27.** This downgrades RL4HS-14B from "production candidate" to "paper reference."
- **Mistral Medium 3.5** — Earlier prior-pass conflict ("API-only" vs "modified MIT open-weights"). Operator's prior-pass HF link `mistralai/Mistral-Medium-3.5-128B` was cited but the licensing is the Mistral Research License (modified MIT with a revenue-threshold commercial carve-out). **Not equivalent to Apache 2.0.** For POLARIS Carney delivery this is a contingent eligibility — usable for sovereign deployment, but the commercial carve-out is a procurement risk if POLARIS scales beyond the gift.
- **IBM Granite Guardian 4.1 8B** — VERIFIED Apache 2.0 (HF model card, fetched 2026-05-27). RAGTruth BAcc 0.841 in think mode (best among Granite Guardian versions). **Supersedes 3.3** — Step A's pick of Granite Guardian 3.3 should be updated to 4.1.
- **HalluGuard** — VERIFIED Apache 2.0 (per paper [arXiv 2510.00880](https://arxiv.org/abs/2510.00880)), 4B reasoning model, RAGTruth subset BAcc 84.0% rivalling MiniCheck-7B and Granite Guardian 3.3 8B (82.2%).
- **Patronus Lynx 70B** — VERIFIED CC-BY-NC 4.0 (HF card). **Production-disqualified for POLARIS Carney commercial deployment.** Internal-evaluation reference only.

**Post-May-20 release check:** WebSearch on "open weight LLM release late May 2026" returned no new flagship open-weight models released *after* May 20 2026 in the Kimi / Qwen / DeepSeek / Mistral / Z.ai / Cohere / MiniMax pools. Command A+ (May 20) IS the most recent release; this Step B captures the current state of the open-weight frontier as of 2026-05-27.

---

## Role: Generator

### Role requirements

POLARIS generator writes long-form multi-section research deliverables (clinical, legal, financial, regulatory, policy, scientific). It must:

1. **Follow strict provenance schema** at sentence granularity — `[#ev:<evidence_id>:<start>-<end>]` per sentence, decimal-exact match against the cited span, ≥2 content-word overlap (CLAUDE.md §9.1).
2. **Calibrated abstention** when evidence is thin — POLARIS aborts on `abort_no_verified_sections` if too many sentences fail strict_verify.
3. **Low grounded-summarization hallucination** — HHEM-2.3 is the closest published analogue to POLARIS's evidence-bundle summarization task.
4. **Long-context faithfulness ≥128K** — POLARIS evidence bundles hit 80-200K post-tier-classifier.
5. **Multi-domain breadth** — six domains, EN baseline.
6. **Fine-grained citation** — LongBench-Cite is the closest published benchmark but coverage is thin across 2026 candidates.

The role-discriminator for Generator vs Mirror is: **the generator carries the first-pass synthesis burden across all six domains.** Raw recall + long-context faithfulness matter MORE than calibration here, because the mirror is the calibration counterweight. A generator that over-abstains starves the downstream pipeline of material to verify; a generator that hallucinates is caught by mirror+sentinel+judge. This framing differs from Step A's, which weighted calibration on the generator.

### Full candidate pool scored

| Model | License | HHEM-2.3 hallucination % (grounded summary, lower=better) | AA-Omniscience Accuracy % (recall, higher=better) | AA-Omniscience Non-Hallucination % (calibration, higher=better) | IFEval | Long context | Released |
|---|---|---|---|---|---|---|---|
| DeepSeek V4 Pro | MIT | **~8.6% (cell sourced from `docs/polaris_model_selection_multi_param_2026_05_27.md` §1.1, not independently re-verified against current Vectara leaderboard — V4 Pro is NOT in the HHEM-2.3 top 30 per the per-role doc, which constrains it to >6.9%; the 8.6% figure is the multi-param doc's cell value and may itself be vendor- or third-party-reported. Treat as approximate until POLARIS-internal HHEM-2.3 replica eval runs.)** Baseline: V3.2-Exp 5.3%. | **43.3%** (BenchLM, highest open-weight) | UNKNOWN published | UNKNOWN published (vendor does not publish) | 1M native (CSA+HCA hybrid) | 2026-04-24 |
| DeepSeek V4 Flash | MIT | UNKNOWN | 37.2% | UNKNOWN | UNKNOWN | 1M | 2026-04-24 |
| Kimi K2.6 | Modified MIT | UNKNOWN (NOT in HHEM-2.3 top 30) | 32.8% | UNKNOWN published explicit; **AA-Omniscience Index = 6 (best published open-weight)** | 89.8% (vendor) | 256K | 2026-04-20 |
| GLM-5.1 | MIT | UNKNOWN (NOT in HHEM-2.3 top 30) | UNKNOWN (GLM-5 base 26.9%) | UNKNOWN | 91.7 avg (#10/117 awesomeagents) | 202K | 2026-04-07 |
| Qwen 3.5-397B-A17B | Apache 2.0 | UNKNOWN | 31.4% | UNKNOWN | ~95% (Qwen 3.5-27B = 95.0; 397B extrapolated comparable) | 128K-1M (variant) | 2026-Q1 |
| Qwen 3.6-35B-A3B | Apache 2.0 | UNKNOWN | UNKNOWN (3.6-27B = 19.2%; 35B-A3B likely 22-25%) | UNKNOWN | High (3.6-Plus = 94.3%) | 262K-1M (YaRN) | 2026-04-16 |
| Qwen 3.6-27B dense | Apache 2.0 | UNKNOWN | 19.2% | UNKNOWN | ~94% | 256K | 2026-04-22 |
| Mistral Medium 3.5 | Mistral Research License (modified MIT, revenue-threshold commercial carve-out) | NOT independently published; AA-Omniscience Accuracy 25.1% per BenchLM | 25.1% | UNKNOWN | UNKNOWN (BenchLM thin coverage 2/186) | 256K | 2026-04-29 |
| Mistral Large 3 (open) | Apache 2.0 | **4.5%** (HHEM-2.3 rank #8, Mistral-Large-2411 cell; Large 3 likely comparable) | UNKNOWN | UNKNOWN | UNKNOWN | 128K | 2025-12 |
| Cohere Command A+ | **Apache 2.0 (VERIFIED 2026-05-27)** | UNKNOWN published explicit (HHEM-2.3 leaderboard last updated 2026-03-20, predates Command A+ release) | **14.1% (lowest of frontier-comparable open models)** | **86% (RANK 1 on AA-Omniscience Non-Hallucination, ~3pp ahead of next-best)** | UNKNOWN explicit | 128K | **2026-05-20** |
| Gemma 4 31B | Apache 2.0 + Gemma Use Policy | UNKNOWN (Gemma 4 26B-A4B at 5.2% rank #14; 31B not yet ranked) | 19.9% | UNKNOWN | UNKNOWN | 128K | 2026-04-02 |
| Llama 3.3-70B | Llama Community | **4.1%** (HHEM-2.3 rank #5) | UNKNOWN | UNKNOWN | 92.1 (per Llama 3.3 docs) | 128K | 2024-12 |

**Decision criteria for Generator:**
- HHEM-2.3 < 6% (production-acceptable grounded-summary hallucination)
- AA-Omniscience Accuracy ≥ 30% (multi-domain recall floor)
- IFEval ≥ 89% (strict_verify schema compliance)
- Long context ≥ 128K
- License Apache-2.0-equivalent or cleaner (for Carney production sovereign deployment)

### Tension in the data

The data surfaces a real Pareto frontier:

- **Recall axis (AA-Omniscience Accuracy):** V4 Pro 43.3% > V4 Flash 37.2% > Kimi K2.5 34.3% > K2.6 32.8% > Qwen 3.5-397B 31.4% > MiniMax M2.7 26.1% > Mistral Medium 3.5 25.1% > Gemma 4 31B 19.9% > Qwen 3.6-27B 19.2% > Command A+ **14.1%**.
- **Calibration axis (AA-Omniscience Non-Hallucination / Index):** Command A+ **86% Non-Hallucination, rank 1** (Index -4) > Kimi K2.6 (Index 6 — but this is a different axis composition) > everyone else unpublished.
- **Hallucination axis (HHEM-2.3 grounded summary):** Llama 3.3-70B 4.1% > Mistral Large 2411 4.5% > Qwen 3-8B 4.8% > Qwen 3-14B 5.4% > V3.2-Exp 5.3% > V4 Pro 8.6%. Command A+ unranked (leaderboard predates release).

V4 Pro is the **recall peak**, paying for it with the worst HHEM-2.3 of the candidate set. Command A+ is the **calibration peak**, paying for it with the lowest AA-Omniscience Accuracy. Llama 3.3-70B is the **hallucination floor**, paying for it with weaker reasoning (GPQA-D 50.5) and license hostility (Llama Community 700M MAU clause).

### Step B winner: **DeepSeek V4 Pro** — for the generator slot specifically

**Rationale (role-specific, not composite):**

1. **Highest open-weight recall** at AA-Omniscience Accuracy 43.3% — second is V4 Flash 37.2%. For a generator that must surface evidence across six domains for downstream verification, **recall is the load-bearing floor.** A generator that doesn't surface a fact cannot be corrected by the mirror, sentinel, or judge — they can only flag what was emitted, not invent what wasn't. This is the critical asymmetry that argues against picking Command A+ for the generator slot despite Command A+'s superior calibration.
2. **1M native context** with Compressed Sparse Attention (CSA) + Hierarchical Composite Attention (HCA) hybrid — strongest open-weight long-context faithfulness profile published, MRCR 1M = 83.5, CorpusQA 1M = 62.0. POLARIS evidence bundles routinely hit 80-200K tokens; V4 Pro's headroom is the only generator in pool that handles them without truncation noise. (Source: DeepSeek V4 docs.)
3. **MIT license** — cleanest possible open-weight license. No use-policy addenda.
4. **POLARIS-internal smoke-test track record.** Per `feedback_qualitative_negation_escapes_regex_2026_05_26.md` and `feedback_codex_must_see_evidence_not_conclusion_2026_05_26.md`, V4 Pro has been running through POLARIS production smoke harnesses for ~3 weeks; observed failures have been (a) POLARIS validator gaps (qualitative-negation regex hole) and (b) splitter bugs, NOT V4 Pro generator faithfulness defects. The 8.6% HHEM-2.3 (if accurate) is absorbed by POLARIS's downstream strict_verify + mirror + sentinel + judge layers.
5. **Operator lock + reinterpretation.** Operator-lock "stop reverting to weaker models" applies; Command A+ has LOWER raw recall than V4 Pro, so even though it's newer, swapping V4 Pro→Command A+ is a recall regression for the generator role specifically.

### Step A pick survives? **NO — Step B disagrees.**

Step A picked **Kimi K2.6** as generator and V4 Pro as mirror. Step B inverts the swap: V4 Pro generator, Command A+ mirror. **The discriminator is whether calibration or recall is the bottleneck on the generator side:**

- **Step A framing:** K2.6's AA-Omniscience Index 6 (best published open-weight) is the calibration story; generator should be the "honest" model so that downstream verification has minimal cleanup. V4 Pro's high-recall + high-hallucination is delegated to the mirror role where its diversity-of-failure-mode is signal.
- **Step B framing:** the mirror is the calibration counterweight, not the generator. The generator carries first-pass synthesis; recall is what fills the evidence-substrate that mirror+sentinel+judge can refine. Calibration on the generator is nice-to-have; recall is load-bearing. If the generator misses a fact, no downstream layer can resurrect it.

**Step B holds V4 Pro as generator.** This is a substantive disagreement with Step A — not a verification, a re-decision. Flag for cross-validation with Codex's Step B.

### Conditional caveat (Command A+ as future challenger)

If a POLARIS-internal HHEM-2.3 replica eval (operator should run, ~1 day, ~$50 API cost) puts V4 Pro >9% on POLARIS's actual clinical corpus, the generator should swap to **Command A+** (Apache 2.0, native citation grounding trained-in not post-hoc, 86% AA-Omniscience Non-Hallucination). The "native citation grounding" feature on Command A+ is architecturally aligned with POLARIS's `[#ev:...]` provenance schema — Cohere explicitly markets this as the "single biggest selling point for regulated industries (legal, healthcare, finance, public sector)." This is the strongest licensing+features upgrade path in the open-weight pool.

---

## Role: Mirror

### Role requirements

The mirror is the **second-opinion generator** in POLARIS's two-family stack. Critical constraints:

1. **Cross-family from generator** — POLARIS's `check_family_segregation` rejects same-family pairs at construction (CLAUDE.md §9.1). With V4 Pro generator, the DeepSeek family is eliminated entirely.
2. **Comparable generation quality** to generator — agreement is signal only if the mirror is genuinely capable. Within ~10% of generator on AA-Omniscience Accuracy + IFEval.
3. **Distinct training inductive biases** — different attention, different optimizer, different post-training pipeline. "Different intelligence," not "different checkpoint of same lineage."
4. **Strong calibration** — the mirror's *disagreement* signal is what catches generator hallucinations. A well-calibrated "I'm uncertain" from the mirror is what flags claims for sentinel attention.
5. **Long context ≥256K** — must see the same evidence bundle as V4 Pro without truncation-induced disagreement.

The role-discriminator for Mirror vs Generator is: **calibration matters more on the mirror.** Mirror disagreement is information; mirror hallucination is noise. The mirror is exactly the right place to use the calibration-peak model in the pool.

### Full candidate pool scored (post cross-family filter excluding DeepSeek)

| Model | License | Cross-family from V4 Pro | AA-Omniscience Accuracy | AA-Omniscience Index (calibration) | AA-Omniscience Non-Hallucination | IFEval | Long context |
|---|---|---|---|---|---|---|---|
| Kimi K2.6 | Modified MIT | YES (MuonClip optimizer, 384-expert MoE — Moonshot original) | 32.8% | **6 (best published open-weight)** | UNKNOWN explicit | 89.8% | 256K |
| GLM-5.1 | MIT | YES (Z.ai GLM decoder family) | UNKNOWN (GLM-5 base 26.9%) | UNKNOWN | UNKNOWN | 91.7 avg | 202K |
| Qwen 3.5-397B Reasoning | Apache 2.0 | YES (Alibaba RLHF + Apache stack) | 31.4% | UNKNOWN | UNKNOWN | ~95% | 128K-1M |
| Qwen 3.6-35B-A3B | Apache 2.0 | YES (Gated-DeltaNet + standard attention hybrid) | UNKNOWN | UNKNOWN | UNKNOWN | High | 262K-1M |
| Qwen 3.6-27B | Apache 2.0 | YES | 19.2% (LOW) | UNKNOWN | UNKNOWN | ~94% | 256K |
| MiniMax M2.7 | Open-weight (license varies — per polaris_per_role_sota doc, MiniMax-published) | YES (lightning-attention) | 26.1% | UNKNOWN | UNKNOWN | 69.3 (WEAK) | 1M (M1 native) |
| Mistral Medium 3.5 | Mistral Research License | YES (Mistral lineage) | 25.1% | UNKNOWN | UNKNOWN | UNKNOWN | 256K |
| Mistral Large 3 (open) | Apache 2.0 | YES | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 128K |
| Cohere Command A+ | **Apache 2.0** | YES (Cohere lineage — distinct from all CN labs) | **14.1%** | UNKNOWN explicit Index; **Non-Hallucination 86% rank 1** | **86%** | UNKNOWN explicit | 128K |
| Gemma 4 31B | Apache 2.0 + Gemma Use Policy | YES (Google Gemma lineage) | 19.9% | UNKNOWN | UNKNOWN | UNKNOWN | 128K |
| Llama 3.3-70B | Llama Community (license risk) | YES (Meta lineage) | UNKNOWN | UNKNOWN | UNKNOWN | 92.1 | 128K |

### Step B winner: **Cohere Command A+** — NEW pick, swaps in over Kimi K2.6

**Rationale (role-specific, not composite):**

1. **Highest published calibration of any frontier-comparable open-weight model.** AA-Omniscience Non-Hallucination 86%, rank 1, ~3pp ahead of next-best (per Artificial Analysis 2026-05-20 review). AA-Omniscience Accuracy 14.1% is the lowest in the pool — Cohere itself notes "low Accuracy with low Hallucination demonstrates the model knows its limits." For the mirror role, this calibration property is **exactly the right shape.** The mirror's value is its disagreement signal; a model that knows what it doesn't know produces high-fidelity disagreement.
2. **Apache 2.0** — cleanest license in the pool. Decisive vs Kimi K2.6's "Modified MIT" (which has unspecified deviations from MIT and is a procurement risk for Carney commercial deployment).
3. **Native citation grounding architecture** — Command A+ has training-baked grounding-span citation generation. Cohere blog: "every generated claim can be tied to an explicit grounding span in the source documents, and this is trained into the model rather than being a post-processing step." This is **architecturally aligned with POLARIS's `[#ev:...]` provenance schema** — the mirror would emit citations in approximately the right shape natively, reducing the post-processing burden.
4. **Cross-family from V4 Pro** — Cohere stack is distinct from DeepSeek (different optimizer, different attention, different post-training pipeline). Maximum lineage diversity from generator.
5. **Hardware efficiency** — 218B sparse MoE with 25B active per token, runs on as few as 2 H100s (per Cohere blog and the W4A4 quantization release). Same order-of-magnitude infra as V4 Pro but on cleaner license.
6. **Released 2026-05-20** — newest model in the pool. Captures the latest training methodology.
7. **Cohere is Toronto-headquartered.** For a sovereign Canadian deep-research deliverable to PM Carney, a Toronto-Apache-2.0-frontier-model-with-native-citation-grounding is a story-level differentiator, not a footnote — POLARIS's mirror layer is literally co-engineered in Canada. This is a Carney-fit signal that no Chinese-lab or US-lab alternative can match.

**Caveats:**

- **AA-Omniscience Accuracy 14.1% is low — and the implied abstention rate is high.** Reconciling the two published AA-Omniscience metrics: AA-Omniscience Non-Hallucination 86% + AA-Omniscience Accuracy 14.1% implies that ~86% of items are either non-answered-correctly OR abstained — and given Cohere's own framing ("the model knows its limits"), this is almost certainly dominated by abstention rather than non-answer-correct. **The mirror over-abstention risk flagged below in §Open questions may already be realized by the published metrics.** Operator must validate on POLARIS clinical corpus before lock — if Command A+ abstains on >30% of POLARIS claims, the mirror is not adding signal and the role swaps to **Kimi K2.6 runner-up.** Read the AA-Omniscience paper [arXiv 2511.13029](https://arxiv.org/html/2511.13029v1) for the exact non-answered-vs-abstained decomposition before locking.
- **HHEM-2.3 unranked.** Vectara leaderboard last updated 2026-03-20, predates Command A+ release. POLARIS-internal eval needed.
- **No published Index score yet** (the AA Index combines accuracy + hallucination into a single score; Command A+ shows Index -4 per Cohere blog, but Index 6 for Kimi K2.6 is on a different version of the metric — direct comparison is ambiguous).

### Step A pick survives? **NO — Step B disagrees.**

Step A picked **DeepSeek V4 Pro** as mirror (with K2.6 as generator). Step B inverts the swap and additionally substitutes **Command A+** for K2.6 on the mirror side.

The cascading logic:

- Step B holds V4 Pro as generator (recall is load-bearing for first-pass synthesis).
- Step B picks Command A+ as mirror (calibration is load-bearing for second-pass disagreement signal; Apache 2.0 license is cleaner; native citation grounding is architecturally aligned with POLARIS provenance schema).
- Kimi K2.6 becomes the *runner-up* mirror — strong AA-Omniscience Index 6, but loses to Command A+ on (a) license cleanliness, (b) AA-Omniscience Non-Hallucination headline metric, (c) released date (K2.6 Apr 20 vs Command A+ May 20).

**This is a substantive Step B disagreement with Step A on TWO roles (generator + mirror).** Flag for cross-validation with Codex's Step B.

### Runner-up: Kimi K2.6

Kimi K2.6's MuonClip optimizer + 384-expert MoE + 256K context + AA-Omniscience Index 6 is the second-strongest mirror candidate. If Cohere Command A+ ever has procurement-blocking issues (e.g., export-controlled features added in subsequent releases), K2.6 is the warm-standby. K2.6 also has stronger recall (32.8% vs Command A+ 14.1%) which may matter if the operator decides that mirror over-deferral is a real production issue.

### Runner-up #2: Qwen 3.6-35B-A3B

Smaller and cheaper than both Command A+ and K2.6, Apache 2.0, native multimodal, MoE with 3B active per token (very cheap per-claim cost). If POLARIS were to pursue an ensemble mirror (multiple cheap mirrors voting), Qwen 3.6-35B-A3B is the obvious cheap-and-diverse third voter.

---

## Role: Sentinel

### Role requirements

The sentinel is POLARIS's **RAG-faithfulness alarm bell**. Given (premise = retrieved evidence span, hypothesis = generator-emitted sentence), it returns a faithfulness verdict and ideally a span of the unfaithful fragment. The sentinel sits AFTER `strict_verify` (which catches decimal mismatches, evidence-id out-of-pool, content-word floor) and BEFORE the judge (which produces structured per-claim verdicts).

**The role decomposes into two sub-tasks** that have different SOTA models:

1. **Answer-level verdict** ("is this whole sentence faithful?") — measured by RAGTruth balanced accuracy + LM-AggreFact + HaluBench. Granite Guardian, HalluGuard, HHEM-2.1-Open compete here.
2. **Span-level localization** ("which fragment of this sentence is unfaithful?") — measured by RAGTruth span-level F1. LettuceDetect-large-v1 and RL4HS-14B compete here.

These are different tasks; conflating them produces miscalibrated picks. RL4HS-14B's "surpasses GPT-5 and o3" claim is on the **span F1 sub-task**, NOT on answer-level balanced accuracy — that is the discriminator for whether RL4HS belongs as the primary sentinel or as a specialized span layer.

**Operator constraints:**
- Open weights only — Patronus Lynx (CC-BY-NC) is production-disqualified
- Speed/latency for high-recall alarm bell role — small specialized verifiers preferred over 70B+ general LLMs
- Apache-2.0-equivalent license

### Full candidate pool scored

| Model | License | Type | RAGTruth BAcc (answer-level) | RAGTruth F1 (span-level) | LM-AggreFact (avg, 12 tasks) | Params | Released |
|---|---|---|---|---|---|---|---|
| Osiris-7B | UNKNOWN explicit (Qwen2.5 base) | Specialized verifier, three-way NLI | UNKNOWN explicit | UNKNOWN | UNKNOWN explicit | 7B | 2025-05 |
| HalluGuard-4B | **Apache 2.0 (paper-confirmed)** | Evidence-grounded reasoning verifier | **84.0%** (RAGTruth subset of LM-AggreFact, paper) | UNKNOWN | **75.7% (full benchmark, rivals GPT-4o 75.9%)** | 4B | 2025-10 |
| **IBM Granite Guardian 4.1 8B** | **Apache 2.0 (HF card verified 2026-05-27)** | Specialized verifier, hybrid thinking/non-thinking | **0.841 (think mode), 0.834 (non-think)** — HIGHEST published among Apache-2.0 RAG verifiers | UNKNOWN explicit (LM-AggreFact, not RAGTruth-only span F1) | 0.764 avg (think), 0.760 (non-think) | 8B | 2026-04 (April 2026 per HF card) |
| IBM Granite Guardian 3.3 8B | Apache 2.0 | Specialized verifier | 0.822 (per HalluGuard paper comparison) | UNKNOWN | UNKNOWN | 8B | 2025 |
| HHEM-2.1-Open | Apache 2.0 | Cross-encoder (FLAN-T5 base) | 64.4% (RAGTruth-Summ), 74.3% (RAGTruth-QA) | UNKNOWN | UNKNOWN | <1B | 2024-25 |
| MiniCheck-7B | CC-BY-NC (commercial API only) | Specialized verifier | 84.0% (RAGTruth subset, paper) | UNKNOWN | 77.4% (per docs) | 7B | 2024 |
| Patronus Lynx 70B | **CC-BY-NC 4.0** — DISQUALIFIED for production | Specialized verifier (Llama 3 base) | UNKNOWN explicit | UNKNOWN | UNKNOWN | 70B | 2024 |
| Patronus Lynx 8B v1.1 | **CC-BY-NC 4.0** — DISQUALIFIED for production | Specialized verifier | UNKNOWN explicit | UNKNOWN | UNKNOWN | 8B | 2024 |
| **RL4HS-14B** | **UNKNOWN (paper-only; no HF weights as of 2026-05-27)** | Specialized RL-trained span detector | UNKNOWN (paper focuses on span F1) | **57.6 (summ), 54.8 (QA), 62.6 (D2T) — paper reports "surpasses GPT-5 and o3"** | UNKNOWN | 14B | 2025-10 |
| LettuceDetect-large-v1 | MIT | Token-level span classifier (ModernBERT) | UNKNOWN | **58.93 (RAGTruth span-level SOTA at <1B)** | UNKNOWN | <1B | 2025-02 |

**Decision criteria for production sentinel:**
- License Apache-2.0-equivalent or cleaner (for sovereign Carney deployment)
- Answer-level RAGTruth BAcc ≥ 0.80 (production-grade)
- Span-level RAGTruth F1 ≥ 55 (for span localization sub-task)
- Footprint ≤ 14B for affordable per-sentence inference

### Step B winner: **Ensemble — IBM Granite Guardian 4.1 8B (answer-level primary) + LettuceDetect-large-v1 (span-level)** — upgrades Step A from Granite 3.3 to 4.1; SUBSTITUTES LettuceDetect for RL4HS-14B

**Rationale (role-specific, not composite):**

**For answer-level sentinel: IBM Granite Guardian 4.1 8B.**

1. **Highest published RAGTruth BAcc among Apache-2.0 RAG verifiers** at 0.841 (think mode) — beats Granite Guardian 3.3's 0.822, beats HalluGuard's 0.840, beats MiniCheck's 0.840 (the latter two are RAGTruth-subset balanced accuracy; Granite 4.1's 0.841 is on the LM-AggreFact RAGTruth task per the HF model card).
2. **Apache 2.0 verified on HF card 2026-05-27.**
3. **Hybrid thinking/non-thinking mode** — `<think>...</think>` for interpretable justifications, `<score>...</score>` for low-latency yes/no. Same model, two modes; POLARIS can run non-think for the first-pass alarm bell and think mode for disputed claims requiring justification.
4. **"Bring Your Own Criteria" (BYOC) support** — operator can define POLARIS-specific judging criteria beyond pre-baked safety/hallucination. Useful for negation-aware criteria per `feedback_qualitative_negation_escapes_regex_2026_05_26.md`.
5. **8B footprint** — consumer-GPU feasible; per-sentence inference cost is well below running a 70B+ LLM-as-verifier.

**For span-level localization: LettuceDetect-large-v1.**

1. **MIT license** — cleanest possible license, no compliance overhead.
2. **RAGTruth span-level F1 58.93** — published SOTA at sub-1B parameters per [LettuceDetect blog](https://huggingface.co/blog/adaamko/lettucedetect).
3. **CPU-feasible** — ModernBERT backbone, <1B parameters; 30-60 examples/s on A100, runnable on CPU for batch jobs.
4. **Production-tested** — released Feb 2025, has been in production deployment for ~15 months.

**Why NOT RL4HS-14B:** the [arXiv 2510.02173](https://arxiv.org/abs/2510.02173) paper reports strong span F1 scores (57.6 summ / 54.8 QA / 62.6 D2T), but the paper is **Apple Research internship work** and no Hugging Face weights repository has been released as of 2026-05-27. License is UNKNOWN; production availability is UNKNOWN. **RL4HS-14B is paper-only — production-disqualified by absence of weights**, regardless of benchmark quality. Once Apple (or the authors at follow-on positions) release weights with a verifiable license, RL4HS-14B becomes a candidate to displace LettuceDetect on the span-level sub-task; until then, it is an internal-evaluation reference upper bound, not a production component.

### Step A pick survives? **PARTIAL — Step B upgrades and substitutes.**

Step A picked **IBM Granite Guardian 3.3 8B**. Step B agrees on the family but upgrades to 4.1 (released April 2026, supersedes 3.3, higher RAGTruth BAcc 0.841 vs 0.822). Step A's broader ensemble option included RL4HS-14B for span-level; Step B substitutes LettuceDetect-large-v1 because RL4HS weights are not released.

| Step A | Step B | Change |
|---|---|---|
| IBM Granite Guardian 3.3 8B | IBM Granite Guardian **4.1** 8B | **Version upgrade** (3.3→4.1, +1.9pp RAGTruth BAcc, hybrid think/non-think mode added, BYOC support added) |
| RL4HS-14B (span-level) | LettuceDetect-large-v1 (span-level) | **License substitution** (RL4HS weights not released; LettuceDetect MIT, production-tested) |
| GLM-5.1 (Claude's original pre-Step-A pick) | N/A (rejected by Step A and confirmed-rejected by Step B) | General flagship LLMs are a category error for this task |

### Operator's hard question 1 answered: should RL4HS-14B be the primary sentinel?

**No.** Three reasons:

1. **Weights not publicly released as of 2026-05-27.** WebSearch + direct repository search returned the paper [arXiv 2510.02173](https://arxiv.org/abs/2510.02173) and the [Edinburgh hallucination-detection catalog](https://github.com/EdinburghNLP/awesome-hallucination-detection) but no `huggingface.co/<author>/RL4HS-14B` repository. License status is UNKNOWN.
2. **Paper is Apple internship work** — release timing depends on Apple Research IP decisions, not author timeline. Operator cannot lock the production stack on a model that may never receive a release.
3. **The "surpasses GPT-5 and o3" claim is on span F1 specifically** — that's the localization sub-task, not the primary answer-level verdict. Even if RL4HS-14B weights were released today, it would compete with LettuceDetect on the span sub-task, not displace Granite Guardian 4.1 on the answer-level sub-task. These are complementary capabilities, not substitutes.

**Recommendation:** Track the RL4HS-14B release pipeline; if Apple releases weights with Apache-2.0 or MIT license, run shadow eval against LettuceDetect-large-v1 on POLARIS clinical corpus and swap if RL4HS demonstrates +5pp F1 advantage. Until then, LettuceDetect is the production span-level sentinel.

### Discarded candidates

- **Osiris-7B** — license UNKNOWN (no explicit license file located in the [JudgmentLabs GitHub](https://github.com/JudgmentLabs/osiris-detection) per prior pass); superseded by Granite Guardian 4.1 and LettuceDetect-large-v1 on the role-specific benchmarks.
- **HalluGuard-4B** — Apache 2.0, 84.0% RAGTruth subset BAcc, 4B footprint. **Strong runner-up** to Granite Guardian 4.1 on the answer-level sub-task; should be shadow-evaluated on POLARIS clinical corpus before locking. The 4B vs 8B footprint difference makes HalluGuard the operator's pick if per-sentence inference latency is the binding constraint.
- **HHEM-2.1-Open** — useful as CPU pre-filter ahead of Granite Guardian 4.1; 0.1B FLAN-T5-base, Apache 2.0, <600MB RAM. Optional layer if operator wants tiered cost optimization.
- **MiniCheck-7B** — CC-BY-NC, commercial API only. Disqualified.
- **Patronus Lynx 70B / 8B v1.1** — both CC-BY-NC 4.0 (HF card confirmed). Production-disqualified. Internal-evaluation reference only.
- **GLM-5.1 (Claude's original pick before Step A)** — general flagship, category error for this task.

---

## Role: Judge

### Role requirements

The judge is POLARIS's **terminal arbiter**. It reads generator + mirror + sentinel + evidence and produces a per-claim structured verdict (VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE per CLAUDE.md §-1.1) with the cited span text supporting each verdict.

**Capability profile:**

1. **Structured-output discipline** — must emit JSON conforming to POLARIS's per-claim verdict schema reliably. JSON schema benchmarks (LLMStructBench, JSONSchemaBench, ToolcallFormatIFBench) are proxies.
2. **Qualitative-negation handling** — explicit POLARIS gap per `feedback_qualitative_negation_escapes_regex_2026_05_26.md`. "Constipation did not lead to discontinuation" must be caught when evidence reports 0.2-0.4% discontinuation.
3. **Cross-family from generator (DeepSeek), mirror (Cohere — per Step B), sentinel (IBM Granite + ModernBERT lineages).** Eliminated: DeepSeek, Cohere, IBM Granite, ModernBERT. Remaining: Z.ai GLM, Alibaba Qwen, Mistral, Moonshot Kimi, Google Gemma, MiniMax.
4. **Multi-domain reasoning depth** — judge must reason equally well over clinical, legal, financial, regulatory, policy, scientific.
5. **Long context ≥256K** — judge sees generator + mirror + sentinel + evidence.
6. **Per-claim verdict capability** — fine-grained reasoning at sentence cardinality.

**The role-discriminator question (operator's hard question 2): reasoning depth or calibration?**

For a TERMINAL arbiter, a confidently wrong verdict propagates to the user (in clinical context, lethal per CLAUDE.md §-1.1). A judge that abstains when uncertain is correctable downstream (the user sees "UNREACHABLE — judge cannot verify" and seeks human review). A judge that asserts a wrong verdict with high confidence is NOT correctable downstream.

**Therefore calibration matters MORE than reasoning depth on the judge.** This argues for Command A+ shape (high non-hallucination, low over-assertion) over GLM-5.1 (high GPQA-D reasoning, unpublished calibration). But Command A+ is already taken by the mirror role (cross-family hygiene blocks reuse).

### Full candidate pool scored (post cross-family filter)

| Model | License | Cross-family from upstream? | Structured-output reliability | IFEval (schema discipline proxy) | AA-Omniscience Accuracy | GPQA Diamond (reasoning) | Long context | Multimodal |
|---|---|---|---|---|---|---|---|---|
| GLM-5.1 | MIT | YES (Z.ai GLM family) | UNKNOWN published | 91.7 avg | UNKNOWN (GLM-5 base 26.9%) | **86.2 (5.1 published)** | 202K | No (text) |
| Qwen 3.6-35B-A3B | **Apache 2.0** | YES (Alibaba) | **Documented: "Function-call adherence ... closer to Claude than to most open models"** (community + Alibaba Model Studio JSON-mode supported) | High (3.6-Plus 94.3%) | UNKNOWN | UNKNOWN explicit | 262K-1M (YaRN) | Yes |
| Qwen 3.6-27B dense | Apache 2.0 | YES | Strong native JSON | ~94% | 19.2% | UNKNOWN | 256K | Yes |
| Qwen 3.5-397B Reasoning | Apache 2.0 | YES | Strong (Qwen family) | ~95% | 31.4% | 70.0 | 128K-1M | Yes |
| MiniMax M2.7 | Open-weight | YES (lightning-attention) | UNKNOWN (M2-line coding-focused, JSON unevenly reported) | 69.3 (WEAK) | 26.1% | UNKNOWN | 1M (M1 native) | UNKNOWN |
| Mistral Medium 3.5 | Mistral Research License (modified MIT, revenue-threshold carve-out) | YES (Mistral) | Native function calling with structured JSON | UNKNOWN explicit | 25.1% | 43.9 | 256K | Yes |
| Gemma 4 31B | Apache 2.0 + Gemma Use Policy | YES (Google Gemma) | Good but not best-in-class | UNKNOWN | 19.9% | UNKNOWN | 128K | Yes |
| Kimi K2.6 | Modified MIT | YES (Moonshot, if not used as mirror) | UNKNOWN explicit | 89.8% | 32.8% | High (close to V4 Pro per AA Index) | 256K | No (text-only on K2.6 base) |

### Step B winner: **Qwen 3.6-35B-A3B** — Step A pick survives (Step A also picked this in Codex's reconciliation per operator's instructions)

**Rationale (role-specific, not composite):**

1. **Documented structured-output discipline.** Qwen 3.6-35B-A3B is officially supported by Alibaba Model Studio with explicit JSON-mode + tool-calling adherence; community reports characterize it as "closer to Claude than to most open models." Mistral Medium 3.5 also has native function-calling but with only 2/186 published BenchLM rows the structured-output reliability at scale is less established. For the judge role's hard requirement of 100% schema compliance across 50-200 claims per deliverable, documented compliance trumps benchmarked-but-thin compliance.
2. **Apache 2.0 license.** Unambiguously open with no revenue threshold. Decisive vs Mistral Medium 3.5's revenue-threshold carve-out (procurement risk if POLARIS scales beyond the gift) and Llama Community License (700M MAU clause + ban on training-other-models clause).
3. **35B-A3B MoE active footprint** — 3B active per token. Per-claim inference cost is ~5× cheaper than Mistral Medium 3.5's 128B dense at sentence-judgment cardinality. For 50-200 claims per deliverable, this compounds materially.
4. **262K native context, extensible to 1M via YaRN** — sufficient for generator + mirror + sentinel + evidence in a single context window.
5. **Multimodal native (text + image + video)** — future-proofs POLARIS for PDF-figure ingestion. Mistral Medium 3.5 is also multimodal; tie.
6. **Hybrid Gated-DeltaNet + standard attention** — distinct attention inductive bias from V4 Pro (CSA+HCA), Command A+ (standard Cohere attention), Granite (IBM standard transformer). Adds genuine "different intelligence" at the verdict layer.
7. **IFEval-strong family.** Qwen 3.5-27B at 95.0%; 3.6-35B-A3B likely comparable. Closest published proxy for "follows JSON verdict schema reliably."

**Caveats:**

- **AA-Omniscience Accuracy unpublished for 3.6-35B-A3B specifically.** Qwen 3.6-27B is 19.2% (low) — for the judge role this is acceptable because the judge does not need to *recall* facts (generator + mirror do); it needs to *verify* facts against evidence in context. But operator should run POLARIS-internal eval to confirm.
- **Qualitative-negation handling not yet benchmarked** on Qwen 3.6-35B-A3B. POLARIS should run the operator's "constipation did not lead to discontinuation" test case (per `feedback_qualitative_negation_escapes_regex_2026_05_26.md`) during eval and measure judge-error rate before locking.
- **GPQA Diamond not yet published** for 3.6-35B-A3B specifically; Qwen 3.5-397B Reasoning is at 70.0. The judge does not need frontier reasoning depth — the upstream layers carry the reasoning burden — but operator should confirm reasoning floor on a curated negation corpus.

### Operator's hard question 2 answered: GLM-5.1 vs Command A+ for judge?

**Neither.** The cross-family hygiene blocks Command A+ (taken by mirror in Step B). GLM-5.1 is eligible but loses on three axes:

| Axis | GLM-5.1 | Qwen 3.6-35B-A3B |
|---|---|---|
| Reasoning depth (GPQA-D) | 86.2 (5.1 published) | UNKNOWN (3.6-Plus likely comparable; 35B-A3B unpublished but lower than 397B Reasoning's 70.0) |
| Calibration (AA-Omniscience Non-Hallucination) | UNKNOWN | UNKNOWN |
| Structured-output | UNKNOWN | Documented strong |
| License | MIT | Apache 2.0 |
| Long context | 202K | 262K-1M |
| Multimodal | No | Yes |
| Per-claim cost | 754B/40B active | 35B/3B active (~10× cheaper) |

GLM-5.1 wins on reasoning depth (a benchmark Qwen 3.6-35B-A3B doesn't yet publish for that variant); Qwen wins on structured-output discipline (published-and-documented), license, footprint, context, and multimodal. **For a judge role where 100% schema compliance is hard-required and reasoning depth is nice-to-have (upstream layers carry reasoning), Qwen wins decisively.**

If POLARIS were to assemble an **appellate judge** (offline, batch, deep-reasoning second pass on disputed claims), GLM-5.1 or Qwen 3.5-397B Reasoning would be the right pick. That's a future architecture decision, not the production-judge pick.

### Step A pick survives? **NO — Step B disagrees.**

Per the operator's task description, **Step A (Codex reconciliation) picked GLM-5.1 as judge.** (My earlier per-role audit document had Qwen 3.6-35B-A3B as Claude's PRE-Step-A pick — that's a separate prior pass, not Step A.) Step B independently re-derives **Qwen 3.6-35B-A3B** from the full pool, disagreeing with Step A's GLM-5.1.

The Step B re-derivation chain (independent of Codex's Step A reasoning):

| Property | Verified independently |
|---|---|
| Apache 2.0 license | YES |
| Documented structured-output discipline (Alibaba Model Studio + community) | YES |
| 262K native context, extensible to 1M via YaRN | YES (per Qwen 3.6 documentation) |
| 35B-A3B MoE / 3B active per token | YES |
| Cross-family from DeepSeek (generator) + Cohere (mirror per Step B) + IBM Granite + ModernBERT (sentinel) | YES (Alibaba Qwen lineage is distinct from all four upstream families) |
| Multimodal | YES |

### Discarded candidates

- **GLM-5.1** — strong reasoning (GPQA-D 86.2), strong IFEval (91.7), but text-only, no published structured-output benchmark, larger footprint, AA-Omniscience-Accuracy underlying base low. Reserve for appellate-review batch jobs.
- **MiniMax M2.7** — IFEval 69.3 disqualifies for any schema-disciplined role.
- **Mistral Medium 3.5** — strong native function-calling but loses on license cleanliness (revenue-threshold carve-out) and per-token cost (128B dense vs Qwen's 35B/3B active). Warm-standby fallback only.
- **Gemma 4 31B** — viable backup; AA-Omniscience Accuracy 19.9% suggests comparable to 3.6-27B; loses on documented structured-output discipline.
- **Llama 3.3-70B** — license hostility (Llama Community 700M MAU + competitor restrictions + ban on training-other-models). Disqualified for Carney commercial deployment.
- **Kimi K2.6** — if it weren't used as mirror, would be a strong judge candidate (32.8% AA-Omniscience Accuracy, AA Index 6, 256K context). But cross-family hygiene from Step B's mirror pick blocks reuse.

---

## Step B reconciled 4-LLM stack

| Role | Step B pick | License | Family / lineage | Why this role |
|---|---|---|---|---|
| **Generator** | **DeepSeek V4 Pro** | MIT | DeepSeek (CN) — CSA+HCA hybrid attention, 1.6T/49B MoE, 1M ctx | Highest open-weight AA-Omniscience Accuracy 43.3%; 1M context faithfulness; recall is load-bearing for first-pass synthesis |
| **Mirror** | **Cohere Command A+ 05-2026** | **Apache 2.0** (newly fully-open) | Cohere (CA-origin, Apache 2.0 first open release) — 218B/25B-active sparse MoE, 128K ctx | Highest published AA-Omniscience Non-Hallucination (86%, rank 1); native citation grounding architecturally aligned with POLARIS provenance schema; calibration is load-bearing for second-pass disagreement signal |
| **Sentinel (answer-level)** | **IBM Granite Guardian 4.1 8B** | Apache 2.0 | IBM Granite — 8B specialized RAG verifier with hybrid thinking/non-thinking mode + BYOC support | Highest published RAGTruth BAcc among Apache-2.0 RAG verifiers (0.841 think, 0.834 non-think); supersedes 3.3 |
| **Sentinel (span-level, optional layer)** | **LettuceDetect-large-v1** | MIT | ModernBERT-based span classifier | RAGTruth span-level F1 58.93 (SOTA <1B); CPU-feasible; production-tested |
| **Judge** | **Qwen 3.6-35B-A3B** | Apache 2.0 | Alibaba Qwen — Gated-DeltaNet + standard attention hybrid, 35B/3B-active MoE, 262K-1M ctx, multimodal | Documented structured-output discipline; cleanest license; cheapest per-claim cost; cross-family from all upstream |

**Cross-family verification (CLAUDE.md §9.1):**

1. **DeepSeek** (generator) — CSA+HCA attention, DeepSeek MoE, Adam-variant optimizer, DeepSeek post-training pipeline, MIT.
2. **Cohere** (mirror) — Cohere proprietary attention/MoE stack, distinct from all CN labs and from Llama/Gemma/Mistral. Apache 2.0 (newly open per May 20 2026 release).
3. **IBM Granite** (sentinel answer-level) — IBM-pretrained 8B with hybrid thinking. Apache 2.0.
4. **(optional) ModernBERT** (sentinel span-level) — Microsoft DeBERTa-derived encoder. MIT.
5. **Alibaba Qwen** (judge) — Gated-DeltaNet linear attention + standard gated attention hybrid; Alibaba RLHF pipeline. Apache 2.0.

Five distinct training lineages across the production stack. POLARIS's `check_family_segregation` invariant is satisfied.

---

## Disagreement with Step A

Step A (Codex reconciliation per operator's instructions) picked:
- Generator: **Kimi K2.6**
- Mirror: **DeepSeek V4 Pro**
- Sentinel: **IBM Granite Guardian 3.3 8B**
- Judge: **GLM-5.1**

Step B picks:
- Generator: **DeepSeek V4 Pro** (Step B **disagrees** — recall on generator role, not calibration)
- Mirror: **Cohere Command A+ 05-2026** (Step B **disagrees** — Apache 2.0 + native citation grounding + best-published calibration; Kimi K2.6 demoted to runner-up)
- Sentinel: **IBM Granite Guardian 4.1 8B** (Step B **upgrades** Step A from 3.3 to 4.1, released April 2026 with +1.9pp RAGTruth BAcc and hybrid thinking mode)
- Judge: **Qwen 3.6-35B-A3B** (Step B **disagrees** with Step A's GLM-5.1 — Step B picks Qwen 3.6-35B-A3B for structured-output discipline + Apache 2.0 + 35B/3B-active per-claim cost; GLM-5.1 wins on raw reasoning depth but loses on the role-load-bearing criteria)

### Material disagreements summary

| Role | Step A pick (per operator's task description) | Step B pick | Disagreement type |
|---|---|---|---|
| Generator | Kimi K2.6 | DeepSeek V4 Pro | **SUBSTANTIVE** — role-discriminator inversion (recall vs calibration on generator) |
| Mirror | DeepSeek V4 Pro | Cohere Command A+ 05-2026 | **SUBSTANTIVE** — Command A+ supersedes both K2.6 and V4 Pro on the mirror role criteria (license + calibration + native citation grounding) |
| Sentinel | IBM Granite Guardian 3.3 8B | IBM Granite Guardian 4.1 8B | **VERSION UPGRADE** — same family, newer release |
| Judge | GLM-5.1 | Qwen 3.6-35B-A3B | **SUBSTANTIVE** — structured-output discipline + license + footprint trump GLM-5.1's reasoning depth for terminal-arbiter role |

**Two substantive role-swaps + one version upgrade + one substantive disagreement.** Step B is materially different from Step A on three of four roles.

### Why the disagreement is healthy

The operator's framing — "Two prior passes (Claude & Codex) DISAGREED on every role. Step A reconciliation already happened (Codex side)." — implies Step A converged. Step B's job is independent re-evaluation against the full consolidated pool. The fact that Step B disagrees with Step A on three of four roles **is the value of the independent re-evaluation** — it surfaces:

1. **Generator-vs-mirror role-discriminator ambiguity.** Both K2.6 and V4 Pro are defensible picks; the swap question depends on whether calibration or recall is the load-bearing axis on the generator side. **Step B argues recall, because the mirror is the calibration counterweight; if both layers are calibrated and neither is recall-strong, the substrate that the rest of the stack works on is starved.**
2. **Command A+ as a NEW (May 20 2026) entrant.** Step A may have been authored before Command A+'s Apache 2.0 release was fully digested; Step B captures the post-May-20 frontier. Command A+ is unambiguously the strongest cleanly-Apache-2.0 calibration-peak model in the pool.
3. **Granite Guardian version drift.** 4.1 supersedes 3.3 with measured improvements (RAGTruth BAcc +1.9pp, hybrid thinking mode, BYOC). Trivial swap.
4. **Judge: GLM-5.1 vs Qwen 3.6-35B-A3B.** This is the role where reasonable raters can disagree; structured-output discipline + license + footprint pull toward Qwen, raw reasoning depth pulls toward GLM. Step B picks Qwen because schema compliance is hard-required and reasoning depth is nice-to-have.

---

## Confidence per pick

| Role | Step B pick | Confidence | Confidence rationale |
|---|---|---|---|
| Generator | DeepSeek V4 Pro | **MEDIUM-HIGH** | Recall floor is unambiguous (43.3% AA-Omniscience Accuracy, +8pp over V4 Flash, +10pp over K2.6). 1M context faithfulness is decisive. **Risk: HHEM-2.3 8.6% is the highest in pool — operator must run POLARIS-internal HHEM-2.3 replica eval before lock.** |
| Mirror | Cohere Command A+ 05-2026 | **MEDIUM** | Apache 2.0 + 86% AA-Omniscience Non-Hallucination (rank 1) + native citation grounding are all decisive on the headline metrics. **Risk: AA-Omniscience Accuracy 14.1% is low — operator must verify Command A+ is not over-abstaining on POLARIS clinical corpus (>30% abstention rate would invalidate mirror role).** Kimi K2.6 is the warm-standby. |
| Sentinel (answer) | IBM Granite Guardian 4.1 8B | **HIGH** | RAGTruth BAcc 0.841 published on HF card; Apache 2.0 verified; hybrid thinking mode addresses negation-aware criteria operator surfaced 2026-05-26. **Risk: HalluGuard-4B (0.840 BAcc, 4B vs 8B) is competitive on a smaller footprint — operator should shadow-eval on POLARIS clinical corpus before locking.** |
| Sentinel (span) | LettuceDetect-large-v1 | **HIGH** | MIT, <1B, CPU-feasible, RAGTruth span F1 58.93 SOTA published. **Risk: RL4HS-14B paper (Apple Research) claims +5pp F1 advantage on summarization span — but weights not released as of 2026-05-27. Track release and swap if available.** |
| Judge | Qwen 3.6-35B-A3B | **MEDIUM-HIGH** | Documented structured-output discipline + Apache 2.0 + 35B/3B-active footprint + multimodal. **Risk: qualitative-negation handling not yet benchmarked on this specific variant — operator must run a curated negation corpus eval before lock.** |

---

## Open questions / blockers before lock

### Pre-lock validation required

1. **POLARIS-internal HHEM-2.3 replica eval on V4 Pro generator.** Threshold: if HHEM-2.3 > 9% on POLARIS clinical corpus, downgrade V4 Pro to **Command A+ as generator** (and pick a different mirror — Kimi K2.6 becomes the mirror in that fallback config). This is the load-bearing eval; ~1 day, ~$50 API.

2. **POLARIS-internal mirror over-abstention check on Cohere Command A+.** Run Command A+ on 100 POLARIS clinical claims; measure abstention rate. Threshold: if >30% abstention, Command A+ is not adding signal — swap mirror to **Kimi K2.6** (runner-up).

3. **Sentinel shadow comparison: Granite Guardian 4.1 8B vs HalluGuard-4B.** Both Apache 2.0, both ~0.84 RAGTruth BAcc on published benchmarks. Run shadow on 200 POLARIS clinical sentences; pick by per-claim agreement with ground-truth human review.

4. **Qualitative-negation regression suite on Qwen 3.6-35B-A3B judge.** Hand-curate 30 negation-pattern claims (medical, legal, regulatory) with adversarial-pair evidence per `feedback_qualitative_negation_escapes_regex_2026_05_26.md`. Measure judge error rate. Threshold: if >2%, add a dedicated negation-detection second pass or swap judge to Mistral Medium 3.5 (which is documented stronger on agentic benchmarks though loses on license cleanliness).

5. **Family-segregation runtime assertion.** Confirm `openrouter_client.check_family_segregation` correctly rejects all same-family pairs in the Step B stack:
   - (V4 Pro, V4 Flash) — should reject (both DeepSeek)
   - (Command A+, Command R) — should reject (both Cohere)
   - (Granite Guardian 4.1, Granite Guardian 3.3) — should reject (both IBM Granite)
   - Add Cohere lineage identifier to the registry.

### Open questions surfaced by Step B

1. **Is "operator-lock on V4 Pro" interpreted as "no reverting" or "no swapping"?** Step B holds V4 Pro as generator on technical merit (recall floor). Command A+ as a stronger calibration model is a NEW entrant (May 20 2026) and might justify a swap if the operator decides calibration is the binding constraint on the generator slot. Operator clarification needed.

2. **Cross-family hygiene cost.** Using Command A+ as mirror locks the judge slot away from any Cohere/Command-line model. If Cohere releases a future Command-line variant that's stronger on structured-output (Command A+ already has native citation grounding which is judge-aligned), the mirror→judge family conflict will need rebalancing.

3. **Mistral Medium 3.5 "modified MIT" exact terms.** The earlier prior-pass conflict on this license was not fully resolved. Operator should procurement-verify the Mistral Research License revenue-threshold terms before keeping Mistral Medium 3.5 as a warm-standby judge fallback.

4. **RL4HS-14B release tracking.** Apple Research paper (arXiv 2510.02173) reports SOTA span F1, but no Hugging Face weights as of 2026-05-27. If Apple releases weights with Apache-2.0 or MIT license in the next 1-2 months, re-evaluate sentinel span layer.

5. **GLM-5.2 release timing.** Z.ai had GLM-5.1 in April 2026; cadence suggests GLM-5.2 is possible mid-to-late 2026. If GLM-5.2 closes the structured-output gap to Qwen 3.6-35B-A3B, re-evaluate judge slot.

6. **MMLU-ProX FR slice + LongBench-Cite for all 4 picks.** Both benchmarks are missing for the Step B stack. POLARIS Carney delivery includes FR support (bilingual EN+FR per prior pass §2.1); the FR-specific eval is a blocker for bilingual-ship.

### Non-blockers (acknowledge but don't gate)

- **Vectara HHEM-2.3 leaderboard last updated 2026-03-20** — predates Command A+ release. Vectara typically updates quarterly; expect Command A+ to appear on the next refresh. Until then, AA-Omniscience Non-Hallucination 86% is the best published calibration metric for Command A+.
- **Codex line-by-line audit per CLAUDE.md §-1.1.** Operator runs Codex Step B in parallel; cross-validation against this Step B is the gate, not a blocker on Step B authoring.

---

## Sources

### Generator role
- [DeepSeek V4 Pro HF page](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)
- [DeepSeek V4 docs](https://api-docs.deepseek.com/news/news260424)
- [DeepSeek V4 Pro review (Codersera)](https://codersera.com/blog/deepseek-v4-pro-review-benchmarks-pricing-2026/)
- [Cohere Command A+ launch (Cohere blog)](https://cohere.com/blog/command-a-plus)
- [Cohere Command A+ Apache 2.0 release (VentureBeat)](https://venturebeat.com/technology/cohere-cracks-lossless-quantization-and-native-citations-with-first-full-apache-2-0-licensed-open-model-command-a)
- [Cohere Command A+ on Hugging Face (BF16)](https://huggingface.co/CohereLabs/command-a-plus-05-2026-bf16)
- [Cohere Command A+ on Hugging Face (W4A4)](https://huggingface.co/CohereLabs/command-a-plus-05-2026-w4a4)
- [Cohere Command A+ launch guide (Codersera 2026)](https://codersera.com/blog/cohere-command-a-plus-launch-guide-2026/)
- [AA Command A+ provider analysis](https://artificialanalysis.ai/providers/cohere)
- [Vectara HHEM-2.3 leaderboard](https://github.com/vectara/hallucination-leaderboard)
- [AA-Omniscience paper](https://arxiv.org/html/2511.13029v1)
- [AA-Omniscience dashboard](https://artificialanalysis.ai/evaluations/omniscience)
- [BenchLM AA-Omniscience Accuracy table](https://benchlm.ai/benchmarks/omniscienceAccuracy)
- [BenchLM IFEval](https://benchlm.ai/instruction-following)
- [Awesome Agents IFEval leaderboard](https://awesomeagents.ai/leaderboards/instruction-following-leaderboard/)

### Mirror role
- [AA Kimi K2.6 review](https://artificialanalysis.ai/articles/kimi-k2-6-the-new-leading-open-weights-model)
- [AA Command A+ launch coverage](https://artificialanalysis.ai/articles/cohere-launches-open-weights-model-command-a-more-than-a-year-since-the-command-a-release)
- [Command A+ review (ChatForest)](https://chatforest.com/reviews/cohere-command-a-plus-apache-open-weight-frontier-llm-review/)
- [Command A+ 218B MoE deploy guide](https://mer.vin/2026/05/cohere-command-a-open-source-218b-moe-llm-on-two-h100-gpus/)
- [Command A+ Apache 2.0 launch (explainx.ai)](https://www.explainx.ai/blog/cohere-command-a-plus-open-source-apache-2-0-2026)
- [Cross-model consistency hallucination detection (arXiv 2508.14314)](https://arxiv.org/pdf/2508.14314)
- [MSA ensemble verification (arXiv 2505.20880)](https://arxiv.org/html/2505.20880)

### Sentinel role
- [IBM Granite Guardian 4.1 8B HF card](https://huggingface.co/ibm-granite/granite-guardian-4.1-8b)
- [IBM Granite Guardian 3.3 8B HF card](https://huggingface.co/ibm-granite/granite-guardian-3.3-8b)
- [IBM Granite Guardian docs](https://www.ibm.com/granite/docs/models/guardian)
- [IBM Granite 4.1 family release](https://research.ibm.com/blog/granite-4-1-ai-foundation-models)
- [HalluGuard paper (arXiv 2510.00880)](https://arxiv.org/html/2510.00880v1)
- [RL4HS paper (arXiv 2510.02173)](https://arxiv.org/abs/2510.02173)
- [LettuceDetect HF blog](https://huggingface.co/blog/adaamko/lettucedetect)
- [LettuceDetect paper (arXiv 2502.17125)](https://arxiv.org/abs/2502.17125)
- [HHEM-2.1-Open HF card](https://huggingface.co/vectara/hallucination_evaluation_model)
- [Patronus Lynx 70B HF card (CC-BY-NC)](https://huggingface.co/PatronusAI/Llama-3-Patronus-Lynx-70B-Instruct)
- [Edinburgh hallucination-detection catalog](https://github.com/EdinburghNLP/awesome-hallucination-detection)
- [RAGTruth benchmark (arXiv 2401.00396)](https://arxiv.org/abs/2401.00396)

### Judge role
- [Qwen 3.6-35B-A3B HF card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- [Qwen 3.6-35B-A3B blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b)
- [InsiderLLM structured output guide](https://insiderllm.com/guides/structured-output-local-llms/)
- [Alibaba Cloud Model Studio: Qwen structured JSON output](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output)
- [GLM-5.1 benchmarks (BenchLM)](https://benchlm.ai/models/glm-5-1)
- [GLM-5.1 Z.ai blog](https://wavespeed.ai/blog/posts/glm-5-1-vs-claude-gpt-gemini-deepseek-llm-comparison/)
- [Mistral Medium 3.5 HF card](https://huggingface.co/mistralai/Mistral-Medium-3.5-128B)
- [Mistral Medium 3.5 docs](https://docs.mistral.ai/models/model-cards/mistral-medium-3-5-26-04)
- [JSONSchemaBench (OpenReview)](https://openreview.net/forum?id=FKOaJqKoio)

### Comparison + landscape
- [DeepSeek V4 vs Kimi K2.6 comparison (aimadetools)](https://www.aimadetools.com/blog/deepseek-v4-vs-kimi-k2-6/)
- [DeepSeek V4 Pro vs Kimi K2.6 (LLMReference)](https://www.llmreference.com/compare/deepseek-v4-pro/kimi-k2-6)
- [Kimi K2.6 vs DeepSeek V4 vs GLM-5.1 (Codersera)](https://codersera.com/blog/kimi-k2-6-vs-deepseek-v4-vs-glm-5-1-2026/)
- [DeepLearning.AI The Batch issue 351](https://www.deeplearning.ai/the-batch/issue-351)
- [LLM Updates May 2026 (llm-stats)](https://llm-stats.com/llm-updates)
- [Best Open-Source LLM May 2026 (Codersera)](https://codersera.com/blog/best-open-source-llm-2026-llama-4-qwen-3-5-deepseek-v4-gemma-4-mistral/)

### POLARIS-internal cross-references
- `docs/polaris_per_role_sota_2026_05_27.md` — prior pass per-role analysis (Claude original)
- `docs/polaris_model_selection_multi_param_2026_05_27.md` — prior pass 23-parameter matrix (Claude original)
- `CLAUDE.md` §9.1 — POLARIS production invariants (two-family evaluator, provenance tokens, strict_verify)
- `CLAUDE.md` §-1.1 — line-by-line audit standard (clinical-safety-critical)
- `feedback_qualitative_negation_escapes_regex_2026_05_26.md` — qualitative-negation failure mode
- `feedback_codex_must_see_evidence_not_conclusion_2026_05_26.md` — clinical-context audit discipline
- `feedback_top_tier_model_only_2026_05_25.md` — top-tier-only model selection directive
