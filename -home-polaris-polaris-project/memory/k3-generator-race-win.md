---
name: k3-generator-race-win
description: "Swapping the generator GLM-5.2 -> moonshotai/kimi-k3 lifts RACE Overall +0.030 (0.4605->0.4903); the biggest single lever found"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-21: MODEL SWAP is the biggest RACE lever found. Generator GLM-5.2 -> moonshotai/kimi-k3 = RACE Overall 0.4605 -> 0.4903 (+0.030), non-overlapping 3x distributions (K3 min 0.4815 > GLM max 0.4679).** Per-dim: Insight +0.045 (biggest), Comprehensiveness +0.030, Instruction-Following +0.020, Readability +0.008 (barely — the abstractive_writer structure FORBID is upstream of the generator, so a model swap alone adds NO headings/tables; Readability stays the weak dim ~0.444). K3 writes ~56% more words (8131 vs 5194). => model-swap (content: Insight/Comprehensiveness) and Batch-2 structure (Readability) are COMPLEMENTARY, not substitutes. Leaders sit 0.52-0.56; this closes ~half the gap in one move. General (kimi-k3 is a frontier open model, not benchmark-overfit).

**HOW TO SWAP THE GENERATOR (the integration pass — 3 things, all general):**
1. `PG_GENERATOR_MODEL=moonshotai/kimi-k3` (os.getenv override in openrouter_client.py:581).
2. `PG_GENERATOR_PROVIDER_FANOUT=1` — UNPIN the generator: `role_provider_routing('generator')` pins `order=['friendli','baseten','novita']` (GLM-5.2 providers) + allow_fallbacks:False, which don't serve kimi -> NoEndpointError 404 "no endpoints found". Fanout ON takes the `pass` branch (no order/ignore pin) so kimi auto-routes.
3. `OPENROUTER_REQUIRE_PARAMETERS=false` — the pipeline sends `reasoning` + `provider.require_parameters:true`; NO kimi-k3 provider ADVERTISES the reasoning param under strict matching -> 404 (isolated via direct probes: reasoning+require_parameters fails, reasoning alone OK). require_parameters' value is honoring max_tokens budget, so dropping it risks truncation on some providers (K3 report was 67KB/8131w, not truncated, so fine here).
PROPER GENERAL FIX (not yet built, code-only, Sol-gateable): on a structural "no endpoints found" 404 with require_parameters=true, RETRY ONCE relaxed (openrouter_client.py:2458 currently raises NoEndpointError immediately). Helps ANY reasoning-first model swap; no model literals. Then kimi as generator is a clean gated adoption.

**Cost/time:** K3 run ~40min (2x GLM's ~21min), full run+3xRACE cycle ~$6.71. OpenRouter account hit its $2750 ceiling mid-session (billing exhausted, 402); operator topped up +$200 (balance ~$193, ~25-30 cycles left). Watch spend. See [[batch1-evidence-substrate-result]], [[race-maxing-audit]], [[race-champion-config]].

**PENDING before locking K3 in:** score K3's FACT (does denser prose keep citation quality?); build the proper routing fix + Sol/K3 gate; then Batch-2 structure ON TOP of K3 (targets Readability). RACE scoring needs OPENROUTER_API_KEY exported.
