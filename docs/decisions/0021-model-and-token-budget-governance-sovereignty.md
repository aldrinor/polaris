# 0021. LLM model must match the signed lock; reasoning effort and token budgets always go MAX

Status: accepted

Date: 2026-06-13

## Context

Two failures drove this rule. Stale Gemma defaults silently drifted into the side judges (#1249/#1251/#1252). And 60/100/512-token caps drifted into the judge layer, starving the models so reasoning truncated into empty content and coverage collapsed into a "half-ass" run. The runtime lock pinned MODELS but historically not token budgets, so the conformance gate never caught the starvation. Operator-locked (2026-06-13, I-arch-003 #1253, `CLAUDE.md` §9.1 invariant 8).

## Decision

Every LLM call's model must match the operator-signed lock `config/architecture/polaris_runtime_lock.yaml`: generator `deepseek/deepseek-v4-pro`, mirror `z-ai/glm-5.1`, sentinel `minimax/minimax-m2`, judge `qwen/qwen3.6-35b-a3b`. NO Gemma, no closed-source at runtime — this is the sovereignty constraint (open-weight only). The side judges (entailment / semantic_conflict / credibility) are not one of the four locked roles, so they map to the MIRROR (GLM) per `legacy_compat`.

Reasoning effort and `max_tokens` ALWAYS go to the real per-model maximum. Read the real limit from `GET https://openrouter.ai/api/v1/models` (`context_length` plus `top_provider.max_completion_tokens`) and reconcile against the serving provider's actual cap — never guess. For example deepseek-v4-pro shows 384000 on OpenRouter but DeepInfra caps completion at 16384.

## Consequences

- `max_tokens` is a CAP billed by actual usage, not a target, so a generous cap is free insurance while a starved budget truncates reasoning into empty content. Never starve a budget to "save" anything.
- Token budgets are now a first-class governed setting, not an afterthought — the gap that let the starvation go undetected is closed.
- The model must be double-checked on every call; a wrong or starved model quietly degrades every downstream verdict, which is exactly the Gemma-drift failure this rule prevents.
- Sovereignty means open-weight only at runtime; a closed-source model, however capable, violates the lock and must not be wired in.
