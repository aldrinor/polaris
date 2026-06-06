# FX-01 (#1105) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

## What this is

FX-01 is a **faithfulness P0** in the drb_72 fix campaign (umbrella #1100). The held drb_72 run
shipped the generator's **token-starved chain-of-thought scratchpad** into `report.md` as VERIFIED
prose: content was empty, the model spent its whole budget on reasoning, the planning monologue
ENDED with a period ("...add about 124 more words.") which defeated the I-bug-089 "ends mid-sentence"
heuristic, so the reasoning was promoted to content and EVERY downstream faithfulness gate
(strict_verify + NLI + 4-role) passed the scratchpad. This is the scratchpad-as-verified-prose
failure — lethal in clinical context.

## Your iter-1 decision (which I implemented verbatim)

Iter-1 you returned `REQUEST_CHANGES` and chose:
> "thread-finish_reason + provider length/stop is the faithful floor-independent signal; refuse
> promotion on length and keep heuristics only as fallback."

with these `remaining_blockers_for_execution`:
1. Thread SSE and non-SSE finish_reason into the synthesized response/LLMResponse.
2. Apply finish_reason=='length' refusal before EVERY reasoning-as-content promotion, including retry.
3. Remove caller-param ceiling as the primary guard; do not replicate model-specific floors/clamps.
4. Add tests for floored low-param success, hard-cap length refusal, and retry length refusal.

You ALSO flagged a NOVEL P0: the COT-2 retry leg promotes reasoning-only output WITHOUT the FX-01
guard, so a sparse first attempt followed by a period-terminated length-truncated retry can still
ship the scratchpad.

## What changed (review `.codex/I-ready-017/codex_diff.patch`)

The param-ceiling approach is FULLY REMOVED (grep the patch: `_hit_token_ceiling` and
`output_tokens >= max_tokens` appear ZERO times as code — the only textual mention is one test
DOCSTRING line explaining why the old heuristic was confounded). Replaced with finish_reason
threading:

1. **`LLMResponse` dataclass** — new field `finish_reason: Optional[str] = None` (the canonical
   "stop" | "length" | ... provider signal).
2. **`_accumulate_sse`** (SSE path) — captures the last real (non-"error") finish_reason from the
   delta chunks and stashes it in the returned `usage_data` dict (no tuple-arity change).
3. **`_read_stream` non-SSE branch** (provider returns JSON despite stream:true) — stashes
   `choices[0].finish_reason` into the returned usage dict.
4. **`_call_impl` SSE-built `data`** — the synthesized choice's `finish_reason` is now
   `stream_usage.get("finish_reason")` instead of a hardcoded `"stop"` (so a "length" truncation is
   visible). For the non-streaming `resp.json()` path the real choice already carries finish_reason.
5. **`_call`** — threads the finish_reason into the PRIMARY LLMResponse via
   `_provider_finish_reason = choice.get("finish_reason") or usage_data.get("finish_reason")`.
6. **BOTH promotion guards** refuse when `result.finish_reason == "length"`:
   - the main I-bug-088 branch in `_generate_impl`, AND
   - the COT-2 RETRY promotion (your novel P0).
   When `finish_reason is None` (provider/stream reported none) they fall back to the I-bug-089
   heuristic: `[#ev:]`-absent AND ends-mid-sentence. When finish_reason is "stop" they promote.
7. **All 11 LLMResponse reconstructions** (reason() recoveries, generate() promotions,
   retry-extracted) pass `finish_reason=result.finish_reason` to preserve the signal.

## Evidence (offline; the §-1.1 LIVE truncation micro-run is folded into CANARY-01, pre-spend)

Tests rewritten to **NOT mock `_call`** (your blocker #4 + p1 finding). A faithful fake OpenRouter
SSE byte-stream is installed on `client._client.stream`, so the REAL path runs:
`_read_stream -> _accumulate_sse -> _call_impl data-build -> _call LLMResponse -> _generate_impl
promotion guard`. The 5 new tests:
- `test_fx01_floored_low_param_success_not_false_positive` — caller `max_tokens=80`, model returns
  big COMPLETE answer with `finish_reason='stop'`, `output_tokens` (9000) >> param. MUST promote
  (this is the exact confound the param-ceiling false-positived on). Also asserts
  `result.finish_reason == 'stop'` — proves threading reaches LLMResponse.
- `test_fx01_length_truncation_period_terminated_refused` — period-terminated scratchpad +
  `finish_reason='length'` -> raises (the drb_72 case).
- `test_fx01_retry_length_truncation_refused` — first attempt sparse (<100 chars) -> COT-2 retry ->
  retry returns >=100-char period-terminated monologue with `finish_reason='length'` -> raises
  (your novel P0).
- `test_fx01_legit_reasoning_first_stop_still_promotes` — complete answer, `finish_reason='stop'`
  -> promotes (I-bug-088 unchanged).
- `test_fx01_heuristic_fallback_when_no_finish_reason` — `finish_reason=None` + mid-sentence + no
  `[#ev:]` -> raises (heuristic fallback preserved).

Result: **34/34** reasoning-first/openrouter tests pass (the 5 above + `test_reasoning_first_*` +
`test_generate_structured_reasoning_first_404_iready018` + `test_structural_404_failloud_iready019`
+ `test_reasoning_trace_capture`). The pre-existing I-bug-089 `test_v4_pro_truncated_planning_*`
regex was tightened to `r"I-bug-089.*truncated.*heuristic_fallback=True"` (a STRONGER assertion of
the heuristic path — behavior unchanged, message wording improved to include finish_reason).

## Files I have ALSO checked and they're clean

- `_REASONING_FIRST_MODELS` / `_ALWAYS_REASON_MODELS` (lines 650-664): deepseek-v4-pro IS
  reasoning-first but NOT always-reason, so the FIX-GLM5 branch is skipped for it and the I-bug-088
  `elif len(reasoning)>=100` promotion applies — the path the tests exercise.
- `check_run_budget` (329-344): only raises when accumulated cost > cap; tests call
  `reset_run_cost()` so no cross-test bleed.
- Non-streaming FIX-QWEN-2 path (`resp.json()` at ~1634): `data["choices"][0]["finish_reason"]` is
  the real provider value; `_call` reads it via `choice.get("finish_reason")`. No edit needed.
- Empty-choices guards in `_read_stream` non-SSE branch (returns `data.get("usage")` with no
  finish_reason -> None -> heuristic fallback, safe).
- The dataclass field is additive with a default, so external LLMResponse consumers are unaffected.

## Known residual (intentional, documented)

When the provider reports NO finish_reason (None) AND the trace is truncated BUT ends with a period
AND has no `[#ev:]`, neither signal fires and it promotes. There is no truncation signal in that
case to act on; the param-ceiling that "covered" it was confounded (it dropped COMPLETE answers).
OpenRouter reliably reports finish_reason='length' on real truncation, so this residual is
theoretical. CANARY-01 (pre-spend behavioral canary) will confirm the live provider emits 'length'
on a forced-truncation micro-run before any paid re-run.

## Question for you

Is the finish_reason threading + dual-guard + heuristic-fallback correct and complete against your
iter-1 blockers? Any NEW promotion site I missed, or any way a length-truncated trace can still
reach `report.md` as content?
