# Codex Diff Review — I-f11-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f11-001 — Follow-up agent with parent-run-context preservation
**Brief:** APPROVED iter 1 (zero P0/P1; 2 P2 incorporated: order-preserving dedup + fresh list)
**Canonical-diff-sha256:** `7c0c13aa46e0b38fe944cd3594625876625c8faa786d37f335b278eeec50e517`
**LOC:** 147 net (under CHARTER §3 200-cap)

## Files

```
src/polaris_graph/followup/__init__.py     NEW +6   (substrate-honest module docstring)
src/polaris_graph/followup/agent.py        NEW +62  (ParentRunContext + ComposedQuery + FollowUpAgent.compose)
tests/polaris_graph/followup/__init__.py   NEW +0
tests/polaris_graph/followup/test_agent.py NEW +79  (9 tests covering preserve / dedup / fresh-list / format / blank / no-summary)
```

## What changed

### `agent.py`
- `ParentRunContext` (frozen): parent_run_id, template, parent_question, known_evidence_ids (default []), parent_summary (default None).
- `ComposedQuery` (frozen): effective_question, inherited_template, parent_run_id, inherited_evidence_ids.
- `_dedup_preserve_order`: returns FRESH list with first-seen-order dedup (Codex iter-1 P2).
- `FollowUpAgent.compose`: ValueError on blank follow-up; effective_question = `f"Follow-up to '{parent.parent_question}': {follow_up.strip()}"`; inherits template + parent_run_id; `_dedup_preserve_order(parent.known_evidence_ids)` for evidence ids.

### Tests
- 9 tests including parametrize over [`""`, `"   "`, `"\t\n"`] for blank rejection.
- Explicit fresh-list-not-aliased test asserts `composed.inherited_evidence_ids is not parent.known_evidence_ids`.

## Verification

- `pytest tests/polaris_graph/followup/test_agent.py`: 9/9 passing in 4.7s.

## Risks for Codex Red-Team

1. **Pure deterministic substrate:** no LLM call; LLM-augmented disambiguation is I-f11-002.
2. **Production wiring deferred:** graph_v4 calling FollowUpAgent + UI surface + scope-gate routing is I-f11-001b.
3. **§9.4:** no `try/except: pass`, no magic numbers, no `time.sleep`, no TODO.
4. **CHARTER §3 LOC cap:** 147 net.

## Output schema (mandatory)

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
