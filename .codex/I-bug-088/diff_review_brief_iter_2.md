# Codex Diff Review — I-bug-088 (ITER 2 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1 (now iter 2 since iter 1 produced no verdict).
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Iter-1 status

Iter 1 produced no final verdict — Codex exhausted its turn budget exploring the codebase and trying to run `pytest` (which isn't on PATH in the sandbox). No P0/P1 findings were articulated. This iter 2 brief includes the local test-run evidence inline so Codex can verify without re-running.

## Pre-flight (unchanged from iter 1)

- **Issue:** I-bug-088 — reasoning-first model handler architecture.
- **Architectural recommendation already APPROVE'd by you (iter 1 of brief review).** Codex chose hybrid Option 5 + Option 3 boundary: response-shape-centric recovery, drop hardcoded model-family registry as the recovery switch (registry retained for now; deletion is a follow-on per Codex's own `follow_on_cleanups` list).
- **Diff:** `.codex/I-bug-088/codex_diff.patch` (canonical-diff-sha256: `964660356321692e92a7b88f53d7cb08958386f5552765751a5ee2530ce9550a`).
- **Files changed:**
  - `src/polaris_graph/llm/openrouter_client.py` (49+ / 3-)
  - `tests/polaris_graph/test_reasoning_first_normalize.py` (NEW, 191 LOC)
- **LOC budget:** 49 src LOC well under CHARTER §3 200-LOC cap.

## What the diff does (in plain prose)

In `generate()`, after the existing `</think>`-extraction (Strategy A) and the `_ALWAYS_REASON_MODELS` regex stripping (Strategy B), insert a NEW Strategy B.5:

> If the model is NOT in `_ALWAYS_REASON_MODELS`, AND `</think>` extraction produced nothing, AND `result.reasoning.strip()` is ≥ 100 chars: treat the raw reasoning as the answer (assign to `result.content`, preserve raw in `result.reasoning`). This is the V4 Pro fix.

The existing Strategy C (COT-2 retry) now only fires when reasoning is sparse (< 100 chars), which is the original intent. The retry path also gets the same B.5 fall-through for the case where retry comes back reasoning-only too.

## Local test run evidence (verbatim from `python -m pytest tests/polaris_graph/test_reasoning_first_normalize.py -v`)

```
tests/polaris_graph/test_reasoning_first_normalize.py::test_v4_pro_reasoning_only_promoted_to_content PASSED [ 16%]
tests/polaris_graph/test_reasoning_first_normalize.py::test_content_present_wins_over_reasoning PASSED [ 33%]
tests/polaris_graph/test_reasoning_first_normalize.py::test_think_tag_extraction_still_wins PASSED [ 50%]
tests/polaris_graph/test_reasoning_first_normalize.py::test_glm5_legacy_path_preserved PASSED [ 66%]
tests/polaris_graph/test_reasoning_first_normalize.py::test_sparse_reasoning_falls_to_retry_path PASSED [ 83%]
tests/polaris_graph/test_reasoning_first_normalize.py::test_both_fields_empty_raises PASSED [100%]
============================== 6 passed in 6.28s ==============================
```

Companion regression on adjacent suites — `python -m pytest tests/polaris_graph/test_gemma_4_evaluator.py tests/polaris_graph/test_deepseek_v4_pricing.py tests/polaris_graph/test_reasoning_first_normalize.py`:
```
============================= 12 passed in 6.26s ==============================
```

If you need to verify locally, the invocation is `python -m pytest <path>` (this sandbox doesn't have `pytest` directly on PATH). DO NOT call bare `pytest`; it will exit 1.

## Acceptance criteria

1. ✅ V4 Pro reasoning-only response yields non-empty `LLMResponse.content` after `generate()`. Pinned by `test_v4_pro_reasoning_only_promoted_to_content`. (Crown Jewel candidate per iter-1 verdict.)
2. ✅ Content-present cases continue to use content (regression). Pinned by `test_content_present_wins_over_reasoning`.
3. ✅ `</think>` extraction continues to fire (regression). Pinned by `test_think_tag_extraction_still_wins`.
4. ✅ GLM-5 family continues through FIX-GLM5-COT regex stripping (registry intentionally NOT removed). Pinned by `test_glm5_legacy_path_preserved`.
5. ✅ Sparse reasoning still triggers COT-2 retry. Pinned by `test_sparse_reasoning_falls_to_retry_path`.
6. ✅ SF-15 fail-loud preserved. Pinned by `test_both_fields_empty_raises`.

## Red-team

1. **Why 100-char threshold?** Below 100 chars, reasoning is a transient leak (a few stray tokens) — promoting would mask a real failure. Above 100 chars, the reasoning IS the answer, just routed to the wrong SSE field. Threshold matches existing FIX-GLM5-COT logic that uses `>= 100` for stripped CoT prefix length. Tunable in code, not env-var-gated because it's a structural threshold.
2. **Why minimal change vs full Option 5/Option 3 helper extraction now?** Iter-1 verdict explicitly classifies "Move recovery to a shared output-normalization helper" and "Stop using `_ALWAYS_REASON_MODELS` as a recovery switch" as `follow_on_cleanups`. Doing them in this PR mixes concerns and risks regressing GLM-5. One change at a time; verify V4 Pro works in production; then deletion follow-up.
3. **`reason()` and `generate_structured()` not changed — by design.** Both already have V4 Pro recovery via existing code paths (lines 1612+ free-form reasoning-as-content, line 1729+ schema JSON-from-reasoning, line 2080+ structured content-empty fallback to reasoning JSON extraction). Only `generate()` was missing the response-shape-centric fall-through.
4. **Two-family invariant preserved.** No change to `check_family_segregation()` or `_FAMILY_PREFIXES`.
5. **Budget-guard invariant preserved.** No change to `_PRICE_TABLE_USD_PER_M` or `_impute_cost_from_tokens()`.
6. **§9.4 hygiene clean.** No `try: except: pass`, no `unittest.mock` in `src/`, no magic numbers (100-char threshold has docstring), no `time.sleep()`, no TODO/FIXME, no real-DB mocking.
7. **No live API call in tests.** Tests mock `client._call`. A live V4 Pro probe-call test belongs to a follow-on integration test gated on `PG_LIVE_TESTS=1`.

## What I want from you, immediately

Return only the verdict block. Do not re-run tests. Do not re-explore the codebase — you already did that in iter 1. Read the diff at `.codex/I-bug-088/codex_diff.patch`, evaluate against the red-team checklist, and respond with the schema below. Keep response under 300 lines.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
