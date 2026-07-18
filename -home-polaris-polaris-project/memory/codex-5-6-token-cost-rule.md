---
name: codex-5-6-token-cost-rule
description: "Cost cliff for codex 5.6 sol (gpt-5.6) — keep each request's INPUT under 272K tokens"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ea997c8e-37cf-4d9a-8a80-f7728137f18b
---

When using codex 5.6 sol (gpt-5.6, the deep-think gate) via the codex CLI on the user's ChatGPT plan, keep every request's INPUT under 272K tokens.

**Why:** Prompts with >272K input tokens are priced at **2× input AND 1.5× output for the ENTIRE request** (not just the overage). GPT-5.6's Codex window is 372K (95%-effective ~353.4K), so long tasks CAN cross the 272K cliff into the expensive tier. The user is on a paid plan and prioritizes cost ("save me money").

**How to apply:** Feed codex only the targeted context it needs (a focused brief + specific code excerpts, NOT whole files or full logs). Chunk big investigations into multiple sub-272K calls instead of one giant call. Rough budget: ~4 chars/token, so keep prompt text well under ~1MB (aim <~900KB / ~258K tokens for margin). The comprehensive design prompt so far was ~33KB (~10K tokens) — safely tiny.

Related: [[user]] wants Opus as orchestrator with codex 5.6 sol max as the deep-think gate (replacing Fable), routed through the codex CLI on their plan (not the OpenRouter API) to save money.
