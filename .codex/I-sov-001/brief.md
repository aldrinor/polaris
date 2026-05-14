# I-sov-001 brief — env-configurable LLM endpoint for vLLM sovereign cutover

**GH:** #199
**Branch:** `bot/I-sov-001-vllm-base-url`
**Head commit:** `8ebcc9a5`

## What

Make the POLARIS LLM call path point at the sovereign OVH H200 vLLM endpoint
via one env var (`OPENROUTER_BASE_URL`) instead of hardcoded OpenRouter URLs.

## Why this is small (the G2 investigation)

`.codex/I-sov-001/g2_dual_backend_findings.md` — ran an identical chat-
completion request through real OpenRouter (DeepSeek V4 Pro) AND a self-
hosted OpenAI-compatible endpoint (Ollama, vLLM-equivalent plain-OpenAI
contract). Both raw responses run through POLARIS's actual parsers.

Findings:
- BOTH parsers (`real_completion._extract_text`, `openrouter_client` path)
  passed against BOTH backends.
- OpenRouter's `system_fingerprint` for DeepSeek V4 Pro is literally
  `vllm-0.20.1rc1...` — OpenRouter already serves DeepSeek V4 Pro via vLLM.
  The OVH cutover is a hosting change, not an engine change.
- `openrouter_client.py` (2469 LOC, imported by 56 files) was already
  vLLM-ready: reads `OPENROUTER_BASE_URL`, checks both `reasoning_content`
  (vLLM key) and `reasoning` (OpenRouter key). The I-bug-088/089 work
  already hardened it.
- Only 2 peripheral files hardcoded the endpoint.

Codex's 7-day-prep consultation estimated G2 as "2 days, audit every
callsite, build a backend abstraction." The evidence narrowed it to
27 source-LOC across 2 files. (Per `feedback_be_skeptical_of_codex_2026_05_13`
— Codex was directionally right but overstated the blast radius.)

## Changes (27 src insertions / 7 deletions; tests +103)

### `src/polaris_graph/generator2/real_completion.py`
- `OPENROUTER_ENDPOINT` is now derived from `OPENROUTER_BASE_URL` env var
  (default `https://openrouter.ai/api/v1`, trailing slash tolerated via
  `.rstrip("/")`). Mirrors `openrouter_client.py:43-45`.
- `_extract_text` reasoning fallback now checks BOTH `reasoning_content`
  (vLLM-native key) AND `reasoning` (OpenRouter key). Previously only
  `reasoning` — an empty-content vLLM response with reasoning would have
  been missed. Aligns with `openrouter_client.py:1389-1393`.
- Empty-content `RuntimeError` now includes `endpoint=` for debug; wording
  changed "OpenRouter" → "LLM backend" (accurate post-cutover).

### `src/polaris_graph/llm/entailment_judge.py`
- `_EntailmentJudge.__init__` reads `OPENROUTER_BASE_URL` and stores
  `self._endpoint`. `judge()` POSTs to `self._endpoint` instead of the
  hardcoded `https://openrouter.ai/api/v1/chat/completions`.
- `usage.cost`-absent path already had the `_impute_cost_from_tokens`
  backstop — no change needed there.

## Files I have ALSO checked and they're clean

- `openrouter_client.py` — already env-configurable (`OPENROUTER_BASE_URL`,
  line 44) + already dual-key reasoning handling. NO change needed.
- `providers/llm_provider.py` — already reads `OPENROUTER_BASE_URL`. NO
  change needed.
- The other 56 files matching `openrouter` import the client; they do NOT
  make direct HTTP calls (verified: only 3 files have direct httpx/requests
  calls to an openrouter URL — the 2 changed here + openrouter_client.py).
- No code anywhere depends on the OpenRouter-specific top-level `provider`
  response field (grep returned zero hits).
- `openrouter_client.py:1295` — `https://openrouter.ai/settings/credits`
  in an error message string; cosmetic, not an endpoint, left as-is.

## Out of scope (deferred — these are dress-rehearsal G1 checks, not code)

- vLLM on the OVH H200 must be launched with `--reasoning-parser deepseek_r1`
  if DeepSeek V4 Pro reasoning should be split into `reasoning_content`
  (otherwise reasoning merges into `content`, which POLARIS also handles).
- `entailment_judge.py` sends `response_format: {"type": "json_object"}`;
  vLLM supports this but the server must be started with guided-decoding.
  Verify at dress rehearsal — it's a launch flag, not a code change.

## Tests (+5 new, 238 passed / 4 skipped across generator2/ + llm/)

- `test_real_completion.py`:
  - `test_extract_text_falls_back_to_reasoning_content_vllm_key` — vLLM's
    `reasoning_content` key recovered when content empty
  - `test_extract_text_prefers_content_over_reasoning_content` — content wins
  - `test_endpoint_defaults_to_openrouter` — default unchanged
  - `test_endpoint_respects_vllm_base_url` — env override + trailing slash
- `test_entailment_judge_cost.py`:
  - `test_judge_endpoint_defaults_to_openrouter`
  - `test_judge_endpoint_respects_vllm_base_url`
  - `test_judge_posts_to_configured_endpoint` — POST targets `self._endpoint`

The 4 skips are `test_strict_verify_entailment_live.py` (needs a live key —
expected skip offline).

## Direct questions for Codex

1. Is the `OPENROUTER_BASE_URL` reuse correct, or should I-sov-001 introduce
   a distinct `POLARIS_LLM_BASE_URL`? I reused `OPENROUTER_BASE_URL` because
   `openrouter_client.py` + `llm_provider.py` already use it — one env var
   flips the whole stack. A new var would require touching those 2 files
   too (more LOC, more drift surface). APPROVE the reuse?
2. The `_extract_text` precedence: `content` (string) → `content` (list) →
   `reasoning_content` → `reasoning`. Is that the right order? My reasoning:
   real content always wins; reasoning is the empty-content fallback only.
3. `entailment_judge.py` keeps the `Authorization: Bearer` header even when
   pointed at vLLM (which ignores it). Harmless — vLLM tolerates an unused
   auth header — but should I gate it? I left it unconditional to minimize
   LOC and because the OVH H200 vLLM MAY be started with `--api-key` for
   defense-in-depth, in which case the header IS needed.
4. Anything else blocking APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
