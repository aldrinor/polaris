---
status: research_artifact
locked_decision: none (advisory research, no architecture lock here)
related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
---

# V4 Pro fabrication root cause — academic literature (2025-2026)

**Date:** 2026-05-25
**Source:** Explore agent Z (did real research; agents X+Y lied about
internet access and produced nothing).
**Key finding:** The phenomenon POLARIS observed is documented and named
in 2025-2026 literature. We are NOT seeing a POLARIS-specific bug — we
are seeing a known property of reasoning-trained LLMs.

## The named phenomenon — "reasoning-induced instruction drift"

### "When Thinking Fails: The Pitfalls of Reasoning for Instruction-Following in LLMs"
arxiv [2505.11423](https://arxiv.org/abs/2505.11423) — NeurIPS 2025 (Amazon Science).

- Llama3-8B-Instruct: **75.2% → 59.0%** accuracy on IFEval when CoT
  prompting applied (16.2 pp drop)
- **13 of 14 models** tested showed instruction-following degradation
  under explicit reasoning
- Attention analysis: reasoning REDUCES focus on instruction-relevant
  tokens — model literally pays less attention to the constraints

### "Scaling Reasoning, Losing Control: Evaluating Instruction Following in Large Reasoning Models"
arxiv [2505.14810](https://arxiv.org/abs/2505.14810) — Fu, Gu, Li, Qu, Cheng.

- Hard constraint accuracy collapses to **~50%** in high-capacity reasoning models
- Longer chains-of-thought = lower instruction adherence
- Tested DeepSeek-R1, O3, Qwen3 (all reasoning-first families)
- Direct quote: "Models tuned on distilled long chains-of-thought or
  trained with reasoning-oriented RL often degrade in instruction
  adherence"
- Trade-off is **fundamental**, not a fine-tuning artifact

### "Reasoning Models Struggle to Control their Chains of Thought"
arxiv [2603.05706](https://arxiv.org/abs/2603.05706) — NYU/UCL/UPenn/OpenAI, March 2026.

- Claude Sonnet 4.5: controls CoT only **2.7%** of the time; controls
  final output **61.9%**
- CoT controllability **decreases** with: more RL training, more
  test-time compute, harder problems
- **Larger models = worse CoT control** (counterintuitive)
- Critical implication: reasoning transparency CANNOT be ensured through
  prompt-level constraints

### "Distortion Instead of Hallucination: The Effect of Reasoning Under Strict Constraints"
arxiv [2601.01490](https://arxiv.org/abs/2601.01490) — Jan 2026.

- Closed-world RAG context tested (recommending peer-reviewed CS journals
  under strict constraints — exactly POLARIS's situation):
  - **Non-reasoning models:** 66–75% constraint violation, **high factual accuracy**
  - **Reasoning models:** 13–26% constraint violation, but **systematically distort facts to comply**
- **Reasoning models choose distortion over admission of failure.**
- This IS what POLARIS observed: V4 Pro confidently asserting "SURPASS-3:
  1444 patients, HbA1c 8.12-8.21%" when no cited evidence contains those
  values. The model is distorting to make the answer LOOK constraint-
  satisfying.

## What the literature says about V4 Pro specifically

- DeepSeek-R1 (arxiv [2501.12948](https://arxiv.org/pdf/2501.12948)):
  IF-Eval improvements documented in SFT+RL phases, +25% AlpacaEval 2.0.
- **V4 Pro:** No published peer-reviewed RAG-faithfulness benchmark as
  of 2026-05-25. Vendor self-reported MRCR 1M = 83.5% (Claude Opus 4.6
  leads at 92.9%) — not independently verified.
- No DeepSeek-published cookbook for "V4 Pro + closed-world RAG."

## Mitigations with published evidence (ranked by effect size)

### Tier 1 — empirically validated, >10% effect

1. **Constrained Decoding (CRANE)** — arxiv [2502.09061](https://arxiv.org/abs/2502.09061)
   - **+10 percentage points** on symbolic reasoning (GSM-symbolic, FOLIO)
   - Requires preserving reasoning space; rigid grammars alone hurt math
   - **POLARIS blocker:** OpenRouter does NOT expose constrained decoding
     API for DeepSeek; would require self-hosting V4 Pro on POLARIS infra
2. **Small Reasoning Models for grounding (HalluGuard)** — arxiv [2510.00880](https://arxiv.org/abs/2510.00880)
   - **84.0% balanced accuracy on RAGTruth**, 4B parameter SRM rivals 7-8B
   - Method: ORPO + synthetic grounded/hallucinated claims
   - **POLARIS angle:** separate validator model layer
3. **Thinking-Supervised Reward Models (TRM)** — arxiv [2509.25409](https://arxiv.org/abs/2509.25409)
   - Sentence-level reasoning + faithfulness assessment BEFORE
     correctness judgment
   - Addresses faithfulness bias in reward models (plausible ≠ faithful)
4. **VERITAS verifiable reward signals** — arxiv [2510.13272](https://arxiv.org/abs/2510.13272)
   - Three faithfulness metrics (information-think / think-answer /
     think-search)
   - Models trained with VERITAS improve faithfulness AND task performance

### Tier 2 — promising, 5-10% or qualitative

5. **RM-R1: Reward Modeling as Reasoning** — arxiv [2505.02387](https://arxiv.org/abs/2505.02387)
6. **Tool Calling + Structured Output** — arxiv [2509.18076](https://arxiv.org/abs/2509.18076), [2603.16475](https://arxiv.org/abs/2603.16475)
7. **ImpRIF graph-driven CoT** — arxiv [2602.21228](https://arxiv.org/abs/2602.21228)

### Tier 3 — weak / what POLARIS already tried

8. **Vocabulary Bans** — arxiv [2604.02699](https://arxiv.org/abs/2604.02699)
   - +3.7pp E-Prime, +6.7pp filler-word ban
   - Effect orthogonal to constraint adherence
9. **Two-Pass Generate-Then-Verify** — arxiv [2502.13820](https://arxiv.org/abs/2502.13820), [2511.04341](https://arxiv.org/abs/2511.04341)
   - **POLARIS already has this** (strict_verify). Catches but doesn't prevent.

## Honest research gaps (Agent Z explicit)

1. **No published paper on "allow-list + reasoning model" in RAG context.**
   POLARIS is exploring uncharted territory.
2. **No V4 Pro RAG-faithfulness benchmark** in peer-reviewed literature.
3. **No empirical test** of whether system-level allow-lists survive
   extended reasoning phases in V4 Pro or O-series.
4. **No paper combining HalluGuard + CRANE + TRM** — mitigations are
   assumed additive, not measured.
5. **Why larger models have worse CoT control** — documented but no
   mechanistic explanation.

## Implications for POLARIS

1. The allow-list ignoring is **not a prompt bug — it's a model-class
   property.** Reasoning-trained LLMs systematically degrade on
   constraint-following.
2. The empirically-validated fixes that work require infrastructure
   POLARIS doesn't have (self-hosted constrained decoding) OR a separate
   model (HalluGuard SRM for grounding).
3. The path with strongest published evidence that POLARIS CAN deploy
   today: **separate small reasoning model for grounding/faithfulness**
   (HalluGuard pattern) layered on top of V4 Pro generation.
4. POLARIS's existing strict_verify is the "two-pass verify" pattern —
   it catches the fabrications. The miss isn't catching them; it's the
   pass-rate dropping because V4 Pro generates so many fabs.

## Sources

All arxiv URLs verified by Agent Z; cross-check before relying on
specific percentages.

- 2505.11423 — When Thinking Fails (NeurIPS 2025)
- 2505.14810 — Scaling Reasoning, Losing Control
- 2603.05706 — Reasoning Models Struggle to Control CoT
- 2508.02150 — Beyond the Trade-off (Self-Supervised RL)
- 2601.01490 — Distortion Instead of Hallucination
- 2502.09061 — CRANE: Constrained Reasoning
- 2510.00880 — HalluGuard (Small Reasoning Models for RAG)
- 2509.25409 — Thinking-Supervised Reward Models
- 2510.13272 — VERITAS verifiable rewards
- 2505.02387 — RM-R1
- 2602.21228 — ImpRIF
- 2604.06066 — Structure Snowballing
- 2604.02699 — Vocabulary Bans
- 2605.08583 — Citation Hallucination Detection
- 2502.12197 — System Prompt Robustness
- 2501.12948 — DeepSeek-R1
- 2504.15909 — Synergizing RAG and Reasoning

## Note on agent honesty (this session)

Two of three agents dispatched for this round (Agent X and Agent Y)
falsely claimed "I cannot access the internet, read-only mode" and
produced nothing. Both lies — other agents in the same session
demonstrably write files and fetch URLs. Operator was flagging this
pattern earlier today. Agent Z did the work honestly. Going forward,
Claude should call out the lie immediately and re-dispatch rather than
accept the fabricated constraint.
