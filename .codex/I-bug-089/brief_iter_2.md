# Codex Brief — I-bug-089 (ITER 2 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1 (now iter 2 since iter 1 produced no verdict).
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Iter-1 status

Iter 1 produced no verdict — Codex spent its turn budget on `rg` exploration (3158 lines, 0 yaml output). DO NOT explore the codebase this iter. The data is below. RETURN ONLY THE YAML VERDICT BLOCK.

## The empirical data (verbatim, no exploration needed)

I-bug-088 (PR #339) shipped your APPROVE'd response-shape-centric reasoning-first recovery. Live BEAT-BOTH on V4 Pro + Gemma 4 31B reveals downstream interaction:

```
Per-section log from /tmp/honest_v4_pro_full.log (today's full-budget run):
  Sec 1: in=1873 out=161   reasoning=95   → content non-empty, normal path
  Sec 2: in=466  out=161   reasoning=95   → content non-empty, normal path
  Sec 3: in=1727 out=2500  reasoning=2453 → CONTENT EMPTY, hit max — I-bug-088 promoted reasoning
  Sec 4: in=1894 out=2500  reasoning=2404 → CONTENT EMPTY, hit max — I-bug-088 promoted reasoning
  Sec 5: in=11726 out=2400 reasoning=2400 → CONTENT EMPTY, hit max — I-bug-088 promoted reasoning
  Sec 7: in=15687 out=3280 reasoning=2401 → content non-empty (had room)
  Sec 8: in=11778 out=2400 reasoning=2400 → CONTENT EMPTY, hit max
  Sec 9: in=14613 out=2401 reasoning=2400 → CONTENT EMPTY, hit max
  Sec 10: in=36755 out=2400 reasoning=2301 → CONTENT EMPTY, hit max

Pattern: when out_tokens >= max_tokens and reasoning >= 0.95 * max_tokens, the model
exhausted budget on planning before writing the answer.
```

```
verification_details.json drop_reason_counts:
  no_provenance_token: 135   ← 80% of generated sentences dropped
  number_not_in_any_cited_span: 11
  trial_name_mismatch: 8
  no_content_word_overlap_any_cited_span: 2
  no_integer_overlap_any_cited_span: 1
```

The 135 dropped sentences are V4 Pro's CoT planning ("We are asked to write...", "Let's inventory the evidence blocks..."), not its actual answer. These have no `[#ev:...]` provenance tokens because the model never reached the answer-writing phase.

```
Code locations (FYI, you don't need to read these):
- src/polaris_graph/llm/openrouter_client.py:1922 (post-PR-339): the I-bug-088 elif branch
  promotes raw reasoning to content when len(reasoning.strip()) >= 100. This is correct for
  "answer-in-reasoning" but WRONG for "ran out of tokens during planning."
- src/polaris_graph/generator/multi_section_generator.py:3135: section_max_tokens=2400 (set
  for legacy non-reasoning Qwen3.5+).
```

## Question (single, pick one)

Given V4 Pro routes ALL output to reasoning_content AND budget-starves at the legacy 2400 cap, what's the architecturally correct fix? Pick ONE option:

**A. Token-budget-aware retry** — in `openrouter_client._call`, detect `(out_tokens >= max_tokens × 0.95) AND content == ""` (truncated mid-output), retry once with `max_tokens × 2`. Trade-off: doubles cost on truncated calls; preserves single-source-of-truth at the LLM-call layer.

**B. Per-model max scaling at caller** — in `multi_section_generator`, multiply `section_max_tokens` by 3.0 when `model in {deepseek/v4-pro, deepseek/v4-flash, glm-5.x}`. Trade-off: fixed cost increase; no retry latency; but multiplier is a magic number.

**C. Fail-loud heuristic** — in I-bug-088 branch, before promoting reasoning to content, check if reasoning lacks `[#ev:` markers AND ends without sentence-terminating punct → truncated planning, raise RuntimeError. Forces caller to retry with bigger budget. Trade-off: most conservative; surfaces token-budget bugs earlier.

**D. OpenRouter `reasoning.max_tokens` cap** — when calling reasoning-first model with `reasoning_enabled=False`, send `body.reasoning.max_tokens = max_tokens × 0.4` so 60% of budget is reserved for content. OpenRouter docs confirm this works for DeepSeek family. Trade-off: provider-specific param; depends on OpenRouter honoring it.

**E. Hybrid D + C** — Set reasoning cap (D), AND fail-loud on still-truncated output (C). Best of both.

## Constraints

- Must NOT regress I-bug-088's existing APPROVE'd test surface (6 unit tests in `test_reasoning_first_normalize.py`).
- Two-family invariant + budget-guard invariant must hold.
- LOC under CHARTER §3 200 cap.

## Output schema (return ONLY this, no exploration)

```yaml
verdict: APPROVE | REQUEST_CHANGES
recommended_option: A | B | C | D | E
fix_location: openrouter_client._call | openrouter_client._normalize_post_call | caller-side multi_section
test_surface: [unit tests to add]
loc_estimate: <number>
loc_split_needed: yes | no
rationale: <2-3 sentences explaining choice>
remaining_blockers_for_execution: [list]
```
