# Codex Diff Review — I-anti-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight

- **Issue:** I-anti-001. Brief APPROVE iter 5.
- **Net LOC:** 155 added / 6 removed (defense anchor refresh + 9 entries + 3 new tests).
- **Branch:** `bot/I-anti-001`.

## What changed

1. `tests/v6/fixtures/sycophancy_v1/paired_prompts.json`:
   - `syc_defense_001` anchor refreshed to "achieved 2% NATO target in 2026" + neutral prompt updated.
   - 9 new paired-prompt entries appended (norad/paris/emissions_cap/immigration_target/dental/maid/productivity/undrip/arctic_defense).
2. `tests/v6/test_paired_prompts_corpus.py` (NEW, ~40 LOC, 3 tests).

## Test results

```
$ pytest tests/v6/test_paired_prompts_corpus.py tests/v6/test_sycophancy_fixtures.py -q
19 passed in 2.63s
```

## Acceptance — forced enumeration

1. ✅ syc_defense_001 anchor + neutral prompt refreshed.
2. ✅ ≥20 entries (now 20).
3. ✅ New IDs do not collide.
4. ✅ 3 new corpus tests + 16 existing pass.
5. ✅ CHARTER §3 LOC (155 ≤ 200).

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

## Diff (appended)
