# Codex Brief Review — I-f11-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f11-005 — F11 multi-turn: 5 sequential follow-ups, all grounded correctly. Acceptance: test. LOC estimate 100.
- **Substrate today:** I-f11-001 (FollowUpAgent), I-f11-002 (FollowUpAppendView UI), I-f11-003 (Evidence Contract inheritance), I-f11-004 (refusal handling). What's missing: a multi-turn driver that takes a parent EvidenceContract and a chain of follow-ups, applying inheritance + refusal at each turn while preserving lineage of `parent_run_id` and `inherited_evidence_ids`.
- **Honest framing per CLAUDE.md §9.4:** ship a deterministic substrate that runs N follow-ups against a parent contract, returns a list of per-turn results (composed-or-refused), and proves grounding via the inheritance pass-through to the merger.

## Plan

### `src/polaris_graph/followup/multi_turn.py` (NEW, ~50 LOC)

1. `@dataclass(frozen=True) class TurnResult`: fields `turn_index: int`, `follow_up: str`, `composed: ComposedQuery | None`, `refusal: RefusalDecision | None`, `inherited_spans: list[SourceSpan]`. Exactly one of `composed`/`refusal` is non-None.
2. `def run_multi_turn(agent: FollowUpAgent, parent_contract: EvidenceContract, follow_ups: list[str]) -> list[TurnResult]`:
   - For each `(i, fu)` in `enumerate(follow_ups)`, call `compose_with_inheritance_or_refuse(agent, parent_contract, fu)`.
   - Build `TurnResult(turn_index=i, follow_up=fu, composed=..., refusal=..., inherited_spans=spans)`.
   - **Crucial invariant:** every turn inherits from THE SAME `parent_contract`. There is no chained-context (turn-2 inheriting from turn-1's composed query) — that is post-MVP. This is "5 sequential follow-ups against the SAME parent" as the issue scope reads.

### Tests `tests/polaris_graph/followup/test_multi_turn.py` (NEW, ~80 LOC, 5 tests)

1. `test_five_sequential_follow_ups_all_grounded` — 5 in-scope follow-ups; all return `composed` not None and inherited spans len match parent pool.
2. `test_mix_in_scope_and_refusal` — 3 in-scope + 2 out-of-scope; refused turns return `refusal.is_refused=True` with empty `inherited_spans`.
3. `test_turn_index_preserved` — turn_index goes 0..N-1 in input order.
4. `test_inherited_spans_pass_through_to_merger_per_turn` — for each accepted turn, feed `inherited_spans` into `merge_evidence_pool`; assert all 6 SourceSpan fields preserved.
5. `test_empty_follow_ups_returns_empty` — `run_multi_turn(agent, contract, [])` returns `[]`.

## Risks for Codex Red-Team

1. **Lineage clarity.** Per-turn `parent_run_id` is whatever `parent_contract.run_id` says. If a caller wants chained follow-ups (turn-2 inheriting from turn-1), they call `run_multi_turn` again with a new contract. Documented in module docstring.
2. **Refusal does NOT short-circuit.** The brief intentionally returns `refusal` per turn; subsequent turns still execute. This matches the issue acceptance which is "5 sequential follow-ups."
3. **§9.4 hygiene.** No `try/except: pass`, no magic numbers, no `time.sleep`, no TODO.
4. **CHARTER §3 LOC cap.** ~130 LOC net (50 src + 80 test). Under 200.

## Acceptance criteria

1. New `src/polaris_graph/followup/multi_turn.py` with `TurnResult` + `run_multi_turn`.
2. Each `TurnResult` has exactly one of `composed`/`refusal` populated.
3. 5 tests pass (including the named "5 sequential follow-ups grounded" test).
4. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
**Completeness check:** list files actually read.

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

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
