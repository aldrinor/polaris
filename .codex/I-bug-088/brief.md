# Codex Brief — I-bug-088: reasoning-first model handler architecture

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight — what just happened

User upgraded the default generator to `deepseek/deepseek-v4-pro` per I-bug-086 (PR #337, merged earlier today). First live BEAT-BOTH benchmark run died at the generation step:

```
00:17:42 SSE metrics: 2502 chunks, content=0 bytes (0 chars),
         reasoning=9967 bytes (9963 chars), done=True, has_usage=True
00:17:43 COT-1: Content empty for generate, reasoning has 9963 chars
         (reasoning_enabled=False, response_format=False).
         Returning as-is — caller handles recovery.
00:17:43 generate completed: 1715 in/2500 out/2500 reasoning tokens, $0.0093
00:17:43 COT-2: generate() content empty, no </think> in reasoning (9963 chars).
         Retrying once.
[process exited]
```

V4 Pro is a hybrid CSA+HCA reasoning architecture. It routes ALL tokens through the OpenAI-compatible `reasoning_content` SSE field, leaving `content` empty even when the request specifies `reasoning_enabled=False`. The retry returned the same shape. The pipeline died.

User explicitly directed: **"I want a true ultimate solution, not band-aid"** — so this brief asks for the architecturally correct fix, not a hardcoded model list bump.

## Existing substrate (verified)

`src/polaris_graph/llm/openrouter_client.py`:

1. **`_ALWAYS_REASON_MODELS` frozenset (line 365):**
   ```python
   _ALWAYS_REASON_MODELS = frozenset({
       "z-ai/glm-5", "z-ai/glm-5-turbo", "z-ai/glm-4.7", "z-ai/glm-5.1",
   })
   ```
   Models in this set get a special path inside `generate()`: when content is empty + reasoning has substance, the reasoning is used as content directly (after heuristic CoT-prefix stripping).

2. **`_extract_answer_from_reasoning()` helper (line 548):** splits reasoning text on `</think>` tag (case-insensitive), returns text after. Works for models that emit `<think>...</think>\nanswer`.

3. **`generate()` recovery path (lines 1842-1950):**
   - Strategy A: try `</think>` extraction.
   - Strategy B: if model in `_ALWAYS_REASON_MODELS`, use raw reasoning + multi-strategy CoT-prefix regex stripping (FIX-GLM5-COT). Three strip strategies: numbered-thinking-end (`"1. **Analyze...**\n"`), keyword pivots (`"Now let me"`, `"Here is"`, `"Output:"`), domain-keyword detection (citation tokens, drug names).
   - Strategy C (fallback): retry once with `reasoning_enabled=False`. If still empty + still reasoning-only, attempt extraction again. If still nothing, propagate empty.

4. **`reason()` recovery (COT-3 at line 1588):** has its own analogous recovery, including JSON-extraction fallback when `response_format` is set.

5. **`_call()` core (line 1416):** raises `ValueError` only when BOTH content AND reasoning are empty (the FIX-H2 hard fail). The V4 Pro case slips through because reasoning is non-empty — the failure is downstream when callers see empty `result.content`.

## The architectural question

The current architecture has three coupled problems:

**P-A. Hardcoded family registry.** `_ALWAYS_REASON_MODELS` is a manual list. Every new reasoning-first model (V4 Pro now; Gemma 4 Reasoning, Llama 4 Maverick reasoning mode, future Phi-5 reasoning, etc.) requires a manual code change. We just paid that exact tax.

**P-B. Model-specific CoT-prefix stripping is heuristic and brittle.** The `FIX-GLM5-COT` block has three regex strategies that target GLM-5's specific output format ("1. **Analyze the Request:**", "Now let me", domain keywords). DeepSeek V4 Pro's CoT preamble shape is different. Llama 4 reasoning mode's shape is different again. The regex pile grows linearly with model count and is impossible to test exhaustively.

**P-C. Detection happens too late.** We discover a model is reasoning-first only after the first call returns empty content. For V4 Pro that's 9000+ wasted reasoning tokens + 77 sec of latency before we route around it. The retry (COT-2) wastes another full call before giving up.

## What user wants

User feedback `feedback_no_cost_mentions.md` (saved 2026-05-08): cost is not a concern. Optimize for **quality + reliability**, not token efficiency. The architectural ask is therefore: **a fix that works correctly for any reasoning-first OpenRouter model, present and future, without requiring a manual registry update or per-model regex.**

## Candidate solutions (you decide which is right)

**Option 1 — Auto-detect on first call, then per-instance memoize.**
On the FIRST call to a model whose `_ALWAYS_REASON_MODELS` membership is unknown, observe the response shape (content vs reasoning). If reasoning-first, set an instance flag and route subsequent calls through the reasoning-as-content path. No registry edits. Trade-off: first call still wastes a retry; need cache invalidation if the same model behaves differently across providers/dates.

**Option 2 — Probe at client construction.**
At `OpenRouterClient.__init__`, send a minimal probe call ("respond with the single word OK") and observe shape. Set `self.is_reasoning_first` and route all subsequent calls accordingly. Trade-off: every client construction pays one probe call. We construct many clients per run.

**Option 3 — Treat content + reasoning as a single output stream.**
Reframe the abstraction: `LLMResponse.content` becomes a property that returns whichever field has substance, with a documented preference for `content` when both are populated. Drop the distinction at the call layer — let downstream code decide if it wants prose-only (use `.prose_text` property that strips `<think>` blocks if present) vs full-output (use `.full_text`). Removes the "is this a reasoning model" question entirely. Trade-off: some downstream code may rely on the empty-content signal as a "this call failed" trigger; needs audit.

**Option 4 — Use OpenRouter's `models` endpoint for capability metadata.**
Query `https://openrouter.ai/api/v1/models/{slug}` once per model at first use; check the `architecture.modality` / `capabilities` field for a reasoning-first marker. Cache the answer in `outputs/.openrouter_model_cache.json`. Trade-off: depends on OpenRouter publishing this metadata correctly for every model; we'd need to audit fields.

**Option 5 — Combine: try `content` first, fall back to reasoning treated as content if empty, regardless of model.**
The simplest version: every call, if `content` is empty and `reasoning` has substance, treat `reasoning` as the answer (after `</think>` extraction if present, raw otherwise). Drop `_ALWAYS_REASON_MODELS` entirely. Drop the FIX-GLM5-COT regex pile (test if recent generator/judge code is robust enough to handle CoT preambles in the prose; if not, build a generic CoT-prefix detector). Trade-off: GLM-5 specifically had ergonomic problems with raw reasoning leaking into prose — would need verification that V3.2-Exp/V4 Pro/V4 Flash don't regress.

## What I want from you

1. **Pick the architecturally correct path** (1, 2, 3, 4, 5, or hybrid). Justify in 2-3 sentences.

2. **Identify the actual root cause failure mode** — is it (a) V4 Pro's response shape, (b) the OpenRouter SSE accumulator, (c) our `reasoning_enabled=False` request not being honored by V4 Pro, or (d) something else? Read `_call()` at line 1073 and the SSE parser to confirm.

3. **List the test surface needed** to prove the fix:
   - Unit test on the new path (with mocked SSE response shapes)
   - Integration test against real V4 Pro (5-token probe call, asserts non-empty extraction)
   - Regression test on V3.2-Exp + GLM-5 (existing models continue to work)
   - Crown Jewel candidate? (Should this become I-cj-008 — "all generator output must be non-empty after recovery"?)

4. **Identify follow-on cleanups** — `_ALWAYS_REASON_MODELS` removal? FIX-GLM5-COT regex deletion? `_extract_answer_from_reasoning` simplification?

5. **Estimate LOC** — does this fit in a single PR (under CHARTER §3 200-LOC cap)? If not, propose split.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
recommended_option: 1 | 2 | 3 | 4 | 5 | hybrid
root_cause: <one sentence>
test_surface: [list of test types]
crown_jewel_candidate: yes | no
follow_on_cleanups: [list]
loc_estimate: <number>
loc_split_needed: yes | no
rationale: <2-3 sentences>
```
