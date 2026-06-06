# Claude architect audit — I-ready-018 (#1100 keystone): generate_structured 404 on reasoning-first deepseek

Reviewer: Claude (architect). Scope: the fix on `bot/I-ready-018-structured-404` (commit `34329ece`). Method: §-1.1, against the source + the forensic run artifacts.

## 1. The defect (confirmed against source, not relayed)

`generate_structured()`'s skip-strict-schema gate read the GLM-only `_ALWAYS_REASON_MODELS` (openrouter_client.py:642) while `_call()` forces a reasoning block for the wider `_REASONING_FIRST_MODELS` (line ~1474, which includes the reasoning-first deepseek default). So for `deepseek/deepseek-v4-pro` the gate attached `response_format={json_schema, strict:true}` WHILE reasoning was forced → with the generator provider pin (`role_provider_routing("generator")` order + `allow_fallbacks:false` + `require_parameters:true`) OpenRouter returned `404 "No endpoints found"`. The drb_72 forensic run shows this killed STORM persona-gen (firing_status=attempted_empty) and every agentic-searcher round-analysis (rounds 2–12: 0 new URLs). The same slug served 31 successful `generate()` calls in the same run — proving a routing/config bug, not a dead model.

## 2. The fix (verified)

One line: line 2598 `_ALWAYS_REASON_MODELS` → `_REASONING_FIRST_MODELS`, aligning the gate to the request-side reasoning switch. deepseek-v4-pro/-flash now skip strict schema and use the prompt-based-JSON + reasoning-extraction recovery (lines ~2650–2722), which I verified is **model-agnostic** (not gated on any model set) — so it recovers deepseek's reasoning-dumped JSON. Plus an explanatory comment.

## 3. Narrowness / regression (verified)

- Affects ONLY deepseek-v4-pro/-flash (the two slugs `_REASONING_FIRST_MODELS` adds over `_ALWAYS_REASON_MODELS`). GLM is in BOTH sets → unchanged.
- `generate_structured` only — the generator's long-form `generate()` is untouched.
- Unit test `test_non_reasoning_first_model_still_gets_strict_schema` pins that a non-reasoning model STILL gets strict json_schema (the fix does not disable strict schema globally).
- 13 existing tests green (reasoning-first normalize + deepseek pricing + the new test). `verify_lock --consistency` = OK. No role/model/family/lock change.

## 4. Evidence

- Offline: `tests/polaris_graph/test_generate_structured_reasoning_first_404_iready018.py` — 4 passed (reasoning-first skips schema; non-reasoning-first keeps it; reasoning_enabled=True skips for any model).
- Live before/after (`.codex/I-ready-018/live_smoke.py`, KEYSTONE_SMOKE_OK): same model + same generator provider pin + same env — the OLD body returns `404 "No endpoints found for deepseek/deepseek-v4-pro"`; the FIXED `generate_structured` parses the REAL `AgenticRoundAnalysis` + `StormPersonaBatch`.

## 5. Faithfulness

The change only alters the response-format attachment for reasoning-first structured calls. It cannot weaken strict_verify, the 4-role D8 gate, two-family segregation, or budget enforcement. It RESTORES discovery breadth (necessary for coverage), it does not relax any verifier.

## 6. Codex P2s (accepted, scoped to follow-ups)

- P2 (retry-path recovery gap: a first-parse-failure retry that returns reasoning-only JSON with reasoning_enabled=false raises ValidationError — fail-loud, not a 404 regression): fold into I-ready-019 (fail-loud / recovery hardening).
- P2 (smoke checks `isinstance` only; a permissive schema could parse empty): fold into I-ready-020 (behavioral canary asserts non-trivial discovery output — queries/personas count > 0).

## 7. Verdict

**Architect verdict: APPROVE.** The keystone is correct, narrow, faithfulness-safe, and empirically proven (404 reproduced → real schemas parse). Codex diff-gate APPROVE (0 P0/P1; 2 P2 follow-ups). This unblocks discovery breadth — the dominant lever for drb_72 coverage. Steps 2 (fail-loud) + 3 (canary) + 4 (re-run) follow.
