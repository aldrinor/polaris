# Codex Diff Review — I-f11-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f11-005 — multi-turn driver. Brief APPROVE iter 1.
- **Net LOC:** 152 (under 200).
- **Branch:** `bot/I-f11-005`.

## What changed

1. `src/polaris_graph/followup/multi_turn.py` (NEW, 55 LOC):
   - `TurnResult` frozen dataclass.
   - `run_multi_turn(agent, parent_contract, follow_ups)` iterates each follow-up through `compose_with_inheritance_or_refuse`, packs result into `TurnResult` (exactly one of composed/refusal non-None).

2. `tests/polaris_graph/followup/test_multi_turn.py` (NEW, 97 LOC, 5 tests):
   - `test_five_sequential_follow_ups_all_grounded` — named acceptance test; asserts `parent_run_id`, `inherited_template`, and `inherited_evidence_ids == ["ev_a", "ev_b"]` per accepted turn (P2 lineage assertion from brief review).
   - `test_mix_in_scope_and_refusal` — 3 in-scope + 2 out-of-scope; refused turns have empty `inherited_spans`.
   - `test_turn_index_preserved` — 0..N-1 in input order.
   - `test_inherited_spans_pass_through_to_merger_per_turn` — feeds spans into `merge_evidence_pool` per accepted turn.
   - `test_empty_follow_ups_returns_empty`.

## Test results

```
$ pytest tests/polaris_graph/followup/ -q
collected 28 items
test_agent.py .........        [ 32%]
test_inheritance.py .......    [ 57%]
test_multi_turn.py .....       [ 75%]
test_refusal.py .......        [100%]
============= 28 passed in 3.06s =============
```

## Risks for Codex Red-Team

1. **No chained-context.** Each turn inherits from the SAME parent contract; documented in module docstring. Chained follow-ups are post-MVP.
2. **Refusal does not short-circuit.** Subsequent turns still execute; consistent with "5 sequential follow-ups" as the issue acceptance reads.
3. **§9.4 hygiene.** No `try/except: pass`, no magic numbers, no `time.sleep`, no TODO.
4. **CHARTER §3 LOC cap.** 152 net.

## Acceptance criteria — forced enumeration

1. ✅ `multi_turn.py` with `TurnResult` + `run_multi_turn`.
2. ✅ Each `TurnResult` has exactly one of `composed`/`refusal` populated.
3. ✅ 5 tests pass (named "5 sequential follow-ups" test included).
4. ✅ CHARTER §3 LOC cap (152 ≤ 200).

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

## Diff (appended below)
