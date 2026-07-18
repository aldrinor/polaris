# Lessons: Model & token governance / sovereignty constraint

Canonical home: CLAUDE.md §9.1 invariant 8 (+ invariant 1 two-family); memory `feedback_llm_model_token_max_governance_2026_06_13.md`.

This hub covers matching every LLM call to the operator-signed runtime lock, the MAX token/reasoning rule, reading the provider API instead of guessing, open-weight sovereignty, and the two-family evaluator.

## Set max_tokens to the model's REAL provider cap and reasoning effort to MAX — a starved budget collapses the run

When a model's max_tokens or provider cap is below its real reasoning need, the reasoning truncates, content comes back empty, and the pipeline fails or falls back — a "half-ass job" that looks like a different bug. Set max_tokens to the model's real serving-provider limit and reasoning effort to the max (high/xhigh). max_tokens is billed by actual usage, so a generous cap is free insurance. Give every slow or GPU call a real timeout so it cannot hang forever.

Why: This is operator-locked §9.1.8 and was the dominant completeness blocker in the beat-both campaign. A starved budget truncates reasoning into empty content silently.

Evidence: `logs/bug_log.md` #1183 I-provider-001 (V4 Pro's ~18k reasoning exceeded DeepInfra's 16384 cap, content truncated, routed to Novita 393k), BUG-088 (LettuceDetect GPU call hung 70+ min with no timeout), BUG-089/090/030/008/010 (structured-output and revision timeouts too tight), BUG-BATCHTIMEOUT (47% batch timeout on GLM 5.1).

Recurrence: Recurring — token-cap and timeout starvation across many runs; codified as §9.1.8.

## Read the live provider API for real field names, response shape, and limits — do not guess

Assuming a provider's field name, response shape, or encoding repeatedly produced silent zeros. Read the actual live response shape and the provider's real limits before wiring. Per-model max = `GET https://openrouter.ai/api/v1/models` (`context_length` + `top_provider.max_completion_tokens`), reconciled against the serving provider's actual cap.

Why: This is the other half of §9.1.8 ("Read the API, DON'T guess"). Each instance produced a confident-but-wrong number for cost, tokens, or results rather than a loud failure, so it survived until forensics. Also, the runtime lock pins MODELS (generator deepseek-v4-pro, mirror glm, sentinel minimax, judge qwen; side judges map to the mirror; NO gemma, no closed-source for sovereignty), and the token-budget gap is what let the starvation drift undetected.

Evidence: `logs/bug_log.md` BUG-B14 (OpenAlex `host_venue` deprecated → HTTP 400 on all queries), BUG-077 (`reasoning_tokens` nested in `completion_tokens_details`, always read as 0), BUG-020/007/024 (model name not in the pricing table + token extraction from the wrong location → 99% cost undercount), BUG-BROTLI (aiohttp advertised Brotli it could not decode → 100% fetch failure).

Recurrence: Recurring — 4+ distinct provider-contract incidents; codified as §9.1.8.
