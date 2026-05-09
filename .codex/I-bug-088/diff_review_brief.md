# Codex Diff Review — I-bug-088 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-bug-088 — reasoning-first model handler architecture.
- **Brief APPROVE'd iter 1.** Architectural recommendation: hybrid Option 5 + Option 3 boundary. Drop reliance on hardcoded model-family registry as the recovery switch; recover based on response shape. This PR is the minimal-viable change from that recommendation; follow-on cleanups (centralizing the helper into a shared normalizer, deleting `_ALWAYS_REASON_MODELS` as a recovery switch, deleting the FIX-GLM5-COT regex pile) are deferred follow-up Issues.
- **Diff:** `.codex/I-bug-088/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - `src/polaris_graph/llm/openrouter_client.py` — `generate()` recovery path: add response-shape-centric fall-through for non-`_ALWAYS_REASON_MODELS` models that emit reasoning-only output. New branch fires when `len(reasoning.strip()) >= 100` and prior strategies (`</think>` extraction, `_ALWAYS_REASON_MODELS` regex stripping) didn't fire. Same recovery applied symmetrically inside the COT-2 retry branch so a retry that comes back reasoning-only is also promoted.
  - `tests/polaris_graph/test_reasoning_first_normalize.py` — NEW. 6 unit tests pinning the public `generate()` invariant.

## Acceptance criteria (verified locally — 12/12 pass on touched suites)

1. ✅ V4 Pro reasoning-only response yields non-empty `LLMResponse.content` after `generate()` returns. `tests/polaris_graph/test_reasoning_first_normalize.py::test_v4_pro_reasoning_only_promoted_to_content` pins this at the public-method boundary.
2. ✅ Content-present cases continue to use content (regression).
3. ✅ `</think>` extraction continues to fire when applicable (regression).
4. ✅ GLM-5 family (`_ALWAYS_REASON_MODELS`) continues through the existing FIX-GLM5-COT regex stripping path (regression — registry is intentionally NOT removed in this PR).
5. ✅ Sparse reasoning (< 100 chars) still triggers the COT-2 retry path.
6. ✅ SF-15 fail-loud `RuntimeError` after exhausting retry preserved.
7. ✅ ~52 LOC change in `openrouter_client.py` + 191-line test file → comfortably under CHARTER §3 200-LOC cap (cap counts SRC LOC; tests are not gated).

## Red-team checklist

1. **Why 100-char threshold for "substance"?** Below 100 chars, reasoning is a transient blip (a few tokens leaked into the wrong field) — promoting it would mask a real failure. Above 100 chars, the reasoning is essentially the answer the model produced, just routed to the wrong SSE field. Threshold matches existing FIX-GLM5-COT logic (`>= 100` for stripped CoT prefix length). Tunable via the constant if false-positives appear; not env-var gated because it's a structural threshold not a deployment knob.
2. **Why not extend `_ALWAYS_REASON_MODELS` instead?** That's the band-aid the user explicitly rejected. Adding `deepseek/deepseek-v4-pro` to the registry would fix V4 Pro but the next reasoning-first model (Llama 4 Maverick reasoning, future Phi-5 reasoning) would re-trigger the same failure. The architectural answer per Codex iter-1 verdict is response-shape-centric: recover based on the shape of the response we got, not the slug we sent.
3. **Why not delete `_ALWAYS_REASON_MODELS` and FIX-GLM5-COT now?** Codex iter-1 verdict explicitly classifies these as `follow_on_cleanups`. Doing them in this PR would balloon LOC, mix concerns (registry change + regex deletion + new fall-through), and risk regressing GLM-5 specifically (which has its own CoT preamble shape that the regex IS designed to strip; we'd want a regression suite first). One change at a time; verify V4 Pro works in production; then deletion follow-up.
4. **`reason()` and `generate_structured()` not changed — by design.** Both already have V4 Pro recovery: `reason()` no-schema path (line 1612+) uses raw reasoning as content directly; `reason()` with-schema path (line 1729+) extracts JSON from reasoning; `generate_structured()` already extracts JSON from reasoning at line 2080+. Only `generate()` was missing the response-shape-centric fall-through.
5. **Two-family invariant preserved.** No change to `check_family_segregation()` or `_FAMILY_PREFIXES`. V4 Pro family resolves to "deepseek"; Gemma 4 31B resolves to "gemma" — the pair passes segregation.
6. **Budget-guard invariant preserved.** No change to `_PRICE_TABLE_USD_PER_M` or `_impute_cost_from_tokens()`.
7. **§9.4 hygiene** — clean: no `try: except: pass`, no `unittest.mock` in `src/`, no magic numbers (100-char threshold has a docstring rationale), no `time.sleep()`, no TODO/FIXME, no real-DB mocking in integration tests.
8. **No live API call.** Tests mock `client._call`. The fix proves out via mocked SSE response shapes; a live V4 Pro probe call belongs to a follow-on integration test.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
