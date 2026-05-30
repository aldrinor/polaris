---
status: research_artifact
locked_decision: none (advisory research, no architecture lock here)
related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
---

# V4 Pro production users — number fabrication research (Agent B)

**Date:** 2026-05-25
**CAVEAT:** Specific benchmark numbers in this file (Vectara HHEM 8.6% V4 /
3.9% V3, AA-Omniscience 94%) come from a research agent and need
independent verification. The pattern recommendations are consistent
with established production RAG literature; specific numeric claims
should be checked before they drive a decision.

## Key finding

DeepSeek V4 Pro fabricates numbers in RAG tasks. Confirmed independently
by POLARIS smoke (12/61 sentences). Multiple production reports suggest
this is a **model-behavior issue, not a prompt-engineering issue.**

## Reported V4 Pro hallucination signals (verify each)

| Source | Claim | Status |
|--------|-------|--------|
| Vectara HHEM 2.3 leaderboard | V4 Pro 8.6% hallucination vs V3 3.9% | UNVERIFIED |
| AA-Omniscience benchmark | V4 Pro 94% hallucinates when uncertain | UNVERIFIED |
| github.com/sgl-project/sglang #23752 | "v4 pro model outputs meaningless numbers mixed in" | URL plausible; verify |
| Fireworks AI Apr 2026 blog | Token-level corruption in V4 Pro reasoning traces | UNVERIFIED |
| BerriAI/litellm #26395 | V4 Pro multi-turn reasoning_content bug | VERIFIED in prior research |

## What production teams reportedly do (consistent with general RAG SOTA)

1. Structured output + tool calling — JSON schema forces output shape
2. Two-phase pipeline — extract with V4 Flash (cheap) → verify with V4 Pro (smart)
3. Cold temperature — V4 Pro default is 1.0; setting to 0.0 is non-default
4. Confidence scoring + abstain — model emits confidence; pipeline routes low-confidence to human
5. V4 Flash for stage 1, Pro for stage 2 — Flash is reportedly 12.4x cheaper

## What does NOT work according to the report

- Negative prompting (telling the model not to invent numbers) — no measurable effect
- Cold temperature alone — does not fix model-level training bias
- System-prompt-only constraints — DeepSeek guidance reportedly says put rules in user prompt

## Sources cited by agent (verify each)

- https://api-docs.deepseek.com
- https://github.com/vectara/hallucination-leaderboard
- https://github.com/sgl-project/sglang/issues/23752
- https://fireworks.ai/blog/deepseek-v4-pro-validating-frontier-models-for-production
- https://github.com/BerriAI/litellm/issues/26395
- https://www.medrxiv.org/content/10.1101/2025.09.12.25334809
- https://www.medrxiv.org/content/10.1101/2025.09.11.25335607
- https://arxiv.org/pdf/2602.14158
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12689871/

## Bottom line

V4 Pro reportedly fabricates more than V3.2-Exp on RAG tasks. Even if
exact numbers do not verify, the direction is consistent with multiple
sources: V4 Pro trades reasoning capacity for fabrication risk.
Production teams either use validator+regen on top of V4 Pro OR fall
back to V3.2-Exp for high-stakes accuracy tasks.
