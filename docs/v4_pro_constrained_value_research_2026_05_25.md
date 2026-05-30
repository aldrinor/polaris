---
status: research_artifact
locked_decision: none (advisory research, no architecture lock here)
related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
---

# Constrained value generation for V4 Pro — research (Agent C)

**Date:** 2026-05-25
**Status:** Pattern recommendations consistent with established RAG
literature. Specific arxiv IDs (2604.02699, 2605.08583, 2601.05866) and
"agent X scored Y%" claims should be independently verified before they
drive large architecture changes.

## The problem (verified by POLARIS smoke)

V4 Pro fabricates numbers in 12/61 sentences. The entailment judge
(Gemma 4 31B) catches semantic violations but does not catch numeric
constraint violations — V4 Pro emits a plausible-sounding number that
is not in the cited span.

## Four candidate patterns

| Pattern | OpenRouter-compatible? | Expected fab reduction | Implementation cost |
|---------|------------------------|------------------------|---------------------|
| A: Pre-extract numbers + inject allow-list | YES | ~80% | 1-2 days |
| B: Constrained decoding (Outlines / Guidance / SGLang) | NO (OpenRouter does not expose guided_json) | ~95% | weeks (requires self-hosting) |
| C: Validator + regen loop | YES | ~15% additional on top of A | 1 day |
| D: Cohere Citations / Anthropic Tool Use | YES (with model switch) | varies | 2-4 week migration |

## Why Pattern B (constrained decoding) is not viable today

OpenRouter API does NOT expose `guided_json`, `guided_regex`, or
`response_schema` for non-OpenAI/Anthropic models. DeepSeek V4 Pro via
OpenRouter cannot use Outlines/Guidance/vLLM-guided-decoding. Pattern B
would require self-hosting V4 Pro on POLARIS infrastructure (out of
scope this sprint).

## Pattern A — pre-extract + allow-list (recommended primary)

How it works:

1. Before calling V4 Pro, scan each evidence span with regex for numbers,
   trial names, drug names.
2. Build an allow-list per evidence_id, e.g.
   `ev_001: numbers={82, 86, 5.4, 12.9, 0.45}, trials={SURPASS-2}`.
3. Inject into the system prompt: "You may ONLY cite numbers from the
   allow-list for the cited ev_XXX. If you need to express a value not
   in the list, do NOT write that sentence."
4. Post-generate: for each sentence ending with `[ev_001]`, extract its
   numbers and validate against the allow-list. Drop sentences that fail.
5. If many drops, regen with Pattern C.

Expected outcome (per agent): 12 number fabrications → 1-2.

## Pattern C — validator + regen loop (recommended secondary)

How it works:

1. Pattern A catches ~80% pre-strict-verify.
2. Of the remainder: extract violating sentences, build a focused regen
   prompt naming the violating number and the allowed set: "Your previous
   sentence used number X which is not in ev_001. Allowed numbers for
   ev_001 are {A, B, C}. Rewrite using only those, or omit if no allowed
   number fits."
3. Single retry (N=1) to bound latency.

Expected outcome (combined with A): residual fab rate ~1-2%.

## What POLARIS already has that is relevant

POLARIS strict_verify ALREADY does post-hoc number validation — that is
what is catching the 12 fab cases today. Drop reasons include
`number_not_in_any_cited_span: 12`. So POLARIS already implements the
back-half of Pattern C (validator). The missing piece is the front-half:
extracting allowed numbers BEFORE generation and giving V4 Pro the
allow-list as a constraint.

## Recommended implementation (3-4 days per agent)

1. New module: `src/polaris_graph/generator/evidence_value_extractor.py`
   that regex-scans each evidence span for numbers, trial names, drug
   names. Output dict per evidence_id.
2. Modify `multi_section_generator._call_section` to inject the
   allow-list into the system prompt for reasoning-first models on the
   FIRST call (not just retry).
3. Extend the strict_verify drop pipeline: when
   `number_not_in_any_cited_span` fires, emit a focused regen prompt
   citing the exact allowed values, retry once.
4. Smoke test: target pass rate >=60% (currently 38%) and
   `number_not_in_any_cited_span == 0` (currently 12).

## Sources cited (verify before relying on numbers)

- https://arxiv.org/html/2604.02699v1 (Trivial Vocabulary Bans)
- https://arxiv.org/html/2509.06631v1 (Guided Decoding in RAG)
- https://arxiv.org/html/2605.08583 (CiteTracer)
- https://arxiv.org/pdf/2601.05866 (FACTUM)
- https://docs.vllm.ai/en/v0.8.2/features/structured_outputs.html
- https://openrouter.ai/docs/guides/features/structured-outputs
- https://github.com/guidance-ai/guidance
- https://github.com/outlines-ai/outlines
- https://pypi.org/project/langchain-chain-of-verification/
- https://python.useinstructor.com/learning/validation/retry_mechanisms/

## Honest limits

- This patches one fab class (numbers). Other fab classes (drug names,
  trial names, dates, statistical jargon) need similar extractors —
  not done in this proposal.
- Allow-list injection adds prompt tokens; modest cost increase.
- If V4 Pro ignores the allow-list (similar to how it ignored the
  earlier HARD CONTRACT until cold temp was added), need to combine
  with cold temp + retry — already done by previous fix.
