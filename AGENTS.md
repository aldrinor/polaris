# AGENTS.md — POLARIS agent operating rules

This file is read by Codex and any coding agent working in this repo. It mirrors the binding
LLM-governance rules in `CLAUDE.md` §9.1.8. `CLAUDE.md` is the full operating charter; read it first.

## LLM MODEL + TOKEN MAX GOVERNANCE (operator-locked 2026-06-13 — GH I-arch-003 #1253)

These are land-mine rules. Every LLM call in this repo is subject to them.

1. **Model must be RIGHT — always double-check.** Every LLM call's model must match the
   operator-signed lock `config/architecture/polaris_runtime_lock.yaml`:
   - generator = `deepseek/deepseek-v4-pro`
   - mirror = `z-ai/glm-5.1`
   - sentinel = `minimax/minimax-m2`
   - judge = `qwen/qwen3.6-35b-a3b`
   - **NO `google/gemma-*`**, no closed-source (openai / anthropic / google-closed) at runtime — sovereignty.
   - The side judges (entailment / semantic_conflict / credibility) are NOT one of the 4 locked roles;
     they map to the **mirror** (GLM-5.1) per the lock's `legacy_compat` (the retired `PG_EVALUATOR_MODEL`).
   - Stale Gemma defaults drifting into those judges caused #1249/#1251/#1252. Verify the model on EVERY call.

2. **Reasoning effort + max_tokens ALWAYS go MAX.** Never starve reasoning or output.
   - Set `max_tokens` to the model's REAL OpenRouter limit; set reasoning effort to the max (high / xhigh).
   - A starved budget truncates reasoning → empty content → fail / coverage-collapse ("half-ass job").
   - `max_tokens` is a CAP, not a target (OpenRouter bills actual usage) → a generous cap is free insurance.

3. **Read the API doc, DON'T guess** the allowed max per model:
   `GET https://openrouter.ai/api/v1/models` → per-model `context_length` + `top_provider.max_completion_tokens`.
   Reconcile vs the actual serving provider's cap (e.g. deepseek-v4-pro: OpenRouter says 384000 but the
   DeepInfra provider binary-searched to 16384).

4. The architecture lock pins MODELS but historically NOT token budgets — that gap let the starvation drift
   undetected by the conformance gate. Token caps are now a first-class governed setting; extend conformance.

Real per-model limits (OpenRouter API 2026-06-13): deepseek-v4-pro ctx 1,048,576 / out 384,000 (DeepInfra
caps 16,384); glm-5.1 ctx 202,752 / out unbounded(=ctx); minimax-m2 ctx 204,800 / out 196,608;
qwen3.6-35b-a3b ctx 262,144 / out 262,144.
