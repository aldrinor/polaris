HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, nothing else):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# I-ready-018 (#1100 keystone) — REVIEW the generate_structured 404 fix ON THE EVIDENCE

You are reviewing BOTH (1) whether the diagnosis is correct against the cited code + run logs, and (2) whether the one-line fix is correct, narrow, and regression-safe. The operator demands an evidence-based review.

## The defect (diagnosis — verify against source yourself)

The drb_72 paid benchmark HELD at coverage 0.286 because DISCOVERY was 100% dead from LLM call #1. Root cause:
- `src/polaris_graph/llm/openrouter_client.py` `generate_structured()` gate (was line 2598): `_effective_reasoning = reasoning_enabled or (self.model in _ALWAYS_REASON_MODELS)`.
- `_ALWAYS_REASON_MODELS` (line ~641) = GLM-only `{z-ai/glm-5, glm-5-turbo, glm-4.7, glm-5.1}`.
- `_REASONING_FIRST_MODELS` (line ~651) = `_ALWAYS_REASON_MODELS` + `deepseek/deepseek-v4-pro` + `deepseek/deepseek-v4-flash`. This is the REQUEST-side set; `_call()` at line ~1474 forces a `reasoning` block for it.
- So for the reasoning-first deepseek default, `_effective_reasoning` was `False` → generate_structured attached `response_format={json_schema, strict:true}` WHILE `_call()` forced reasoning. With the generator provider pin (`role_provider_routing("generator")` order + `allow_fallbacks:false` + `require_parameters:true`), OpenRouter found no endpoint serving both → `404 "No endpoints found"`.
- The FIX-GLM5-STRUCTURED comment (2026-04-12, lines ~2586) documents EXACTLY this incompatibility — it was patched for GLM by checking `_ALWAYS_REASON_MODELS` and never extended to the reasoning-first deepseek default.
- The same slug is ALIVE: it served 31 successful `generate()` calls + 126/156 verified claims in the SAME run; only `generate_structured` 404'd. So this is a routing/config bug, NOT a dead model.

Run-log evidence (in `outputs/audits/I-ready-017/run_artifacts/run_drb72.log`): STORM persona-gen 404×3 on the first LLM call → 8 template personas → `firing_status=attempted_empty`; agentic round 1 = 137 URLs (template seeds), rounds 2-12 every "LLM analysis failed: 404" → 0 new URLs.

## The fix (committed `34329ece` on `bot/I-ready-018-structured-404`, base `bot/I-ready-consolidated`)

One-line: line 2598 `self.model in _ALWAYS_REASON_MODELS` → `self.model in _REASONING_FIRST_MODELS` (+ an explanatory comment). This aligns the skip-response_format gate with the request-side reasoning switch, so deepseek-v4-pro/-v4-flash skip strict schema and use the model-agnostic prompt-based-JSON / reasoning-extraction recovery (lines ~2650, which is NOT gated on any model set). Diff: `.codex/I-ready-018/codex_diff.patch`. Read the committed file directly to verify.

## Evidence the fix works (smoke)

- Offline unit tests `tests/polaris_graph/test_generate_structured_reasoning_first_404_iready018.py` — **4 passed**:
  - reasoning-first models (deepseek-v4-pro/-flash) → `response_format` is None (skipped) when `reasoning_enabled=False`.
  - a NON-reasoning-first model (qwen3.5-plus) → STILL gets strict json_schema (the fix is NARROW; strict schema not disabled for models that support it).
  - `reasoning_enabled=True` → skips schema for any model (unchanged).
- Live smoke `.codex/I-ready-018/live_smoke.py` → **KEYSTONE_SMOKE_OK** (same model, same provider pin, same env):
  - PART A control: the OLD body (strict json_schema + reasoning + the generator's EXACT provider pin `order=[streamlake,siliconflow,baidu,novita,gmicloud,deepseek]`, `allow_fallbacks:false`, `require_parameters:true`) → **HTTP 404 "No endpoints found for deepseek/deepseek-v4-pro"** (reproduces the production failure).
  - PART B fix: `generate_structured(reasoning_enabled=False)` on deepseek-v4-pro with the REAL discovery schemas `AgenticRoundAnalysis` (searcher round-analysis) and `StormPersonaBatch` (STORM persona-gen) → both PARSED.

## Verify (your job)

1. **Diagnosis correctness:** does the cited code (lines 641-655 model sets, 1474 request-side force, 2586-2609 the gate, recovery ~2650) actually produce the 404 for deepseek-v4-pro on the old gate, and does aligning to `_REASONING_FIRST_MODELS` actually fix it? Confirm or refute against the source.
2. **Narrowness / regression:** does the change affect ANY model other than deepseek-v4-pro/-v4-flash? Does it break (a) the GLM path (GLM is in BOTH sets — unchanged), (b) the generator's normal long-form `generate()` (generate_structured only — confirm), or (c) ANY OTHER `generate_structured` caller that passes a deepseek model AND requires strict json_schema enforcement (grep callers — are there any that NEED strict schema and won't parse via reasoning-extraction)?
3. **Recovery soundness:** for deepseek now skipping response_format, is the prompt-based-JSON + reasoning-extraction recovery (lines ~2650-2722) truly model-agnostic and sufficient (the live smoke parsed the real schemas — but is there a schema class or code path where it would silently return empty/wrong)?
4. **Faithfulness:** confirm this change cannot weaken strict_verify, the 4-role gate, two-family segregation, or budget enforcement (it only changes the response-format attachment for discovery structured calls).
5. **Scope check:** this is the keystone (step 1 of an 8-step plan). Fail-loud-on-404 (step 2) and the behavioral canary (step 3) are SEPARATE follow-up PRs — do NOT require them here; only review THIS diff. But if you see a way THIS fix could itself silently fail, name it.

If the diagnosis holds and the fix is correct + narrow + safe, APPROVE. Otherwise name the specific blocker.
