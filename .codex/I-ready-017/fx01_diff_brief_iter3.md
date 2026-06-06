# FX-01 (#1105) diff-gate — ITER 3 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context

FX-01 (faithfulness P0, drb_72 campaign #1100): refuse to promote a TRUNCATED reasoning trace into
`report.md` content. iter-1 chose finish_reason threading; iter-2 confirmed threading + the
raw-promotion guards but returned `REQUEST_CHANGES` with TWO P1s + a centralization blocker.

## Your iter-2 findings (all addressed this iter)

iter-2 verdict: `REQUEST_CHANGES`, `novel_p0: []`, `continuing_p0: []`, two P1s:
1. P1: `</think>` extraction sites (primary ~2411 + retry ~2603) ran `_extract_answer_from_reasoning`
   then returned `LLMResponse(content=extracted, ...)` WITHOUT a finish_reason=='length' refusal — a
   length-truncated trace with `</think>` + >20 chars could still reach `report.md`.
2. P1: the `_ALWAYS_REASON_MODELS` (GLM) promotion (~2434) promoted reasoning→content without the
   refusal.
`remaining_blockers_for_execution`: "Centralize the FX-01 promotion guard and call it before every
generate() branch... primary/retry </think> extraction, _ALWAYS_REASON_MODELS, primary raw
promotion, retry raw promotion" + "Add tests for finish_reason=='length' refusal on primary </think>
extraction, retry </think> extraction, and the always-reason promotion branch."

## What changed since iter-2 (review `.codex/I-ready-017/codex_diff.patch`)

**Centralized the guard** into ONE method on `OpenRouterClient`:
```
_refuse_if_truncated_reasoning_promotion(*, candidate_text, finish_reason, trace_id, leg)
```
It raises `ReasoningFirstTruncationError` when `finish_reason == "length"` (canonical) OR, when
`finish_reason is None`, the I-bug-089 heuristic on the CANDIDATE text (`[#ev:]`-absent AND
ends-mid-sentence). It is now called before **all FIVE** generate() reasoning→content legs:
- `primary_think_extraction` (POOL-FALLBACK `</think>` split) — NEW guard
- `always_reason_promotion` (GLM `_ALWAYS_REASON_MODELS`, checks the CLEANED reasoning) — NEW guard
- `primary_raw_promotion` (I-bug-088) — inline guard REPLACED by the centralized call
- `retry_think_extraction` (retry `</think>` split) — NEW guard
- `retry_raw_promotion` (retry I-bug-088) — inline guard REPLACED by the centralized call

The two prior inline guards are GONE (no duplicated policy). Grep the patch: the only `if ... ==
"length"` / heuristic logic now lives in the single helper; the five call sites pass `candidate_text`
= exactly the text each leg would copy into content.

## Tests (NOT mocking `_call` — real SSE byte-stream)

+3 new (your blocker), all driving the real `_read_stream → _accumulate_sse → _call → _generate_impl`
path via the fake SSE transport:
- `test_fx01_length_truncation_primary_think_extraction_refused` — reasoning with `</think>` + cut-off
  answer, `finish_reason='length'` → raises.
- `test_fx01_length_truncation_retry_think_extraction_refused` — sparse first attempt → COT-2 retry →
  retry `</think>` + cut-off answer, `finish_reason='length'` → raises.
- `test_fx01_length_truncation_always_reason_promotion_refused` — model `z-ai/glm-5.1` (always-reason),
  no `</think>`, `finish_reason='length'` → raises.

Plus the iter-2 five (floored-low-param SUCCESS confound, length raw refusal, retry raw refusal,
legit stop promote, no-finish_reason heuristic fallback). **37/37** reasoning-first/openrouter tests
pass (8 FX-01 + token-budget + normalize + trace-capture + 404 iready018/019).

## Files ALSO checked clean

- All 11 LLMResponse reconstructions still preserve `finish_reason`.
- The `else:` SF-15 fail-loud after exhausted retries (~2709) is unchanged (already fails loud).
- `_extract_answer_from_reasoning` requires `</think>` + >=20 chars, so non-reasoning-first models
  without `</think>` skip the extraction legs entirely (byte-identical for them).

## Question

Is the centralized guard now applied at EVERY reasoning→content promotion in generate(), with no
remaining path by which a `finish_reason=='length'` trace reaches `report.md` content?
