# Codex Brief Review — I-f11-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f11-001 — Follow-up agent with parent-run-context preservation. Scope: `src/polaris_graph/followup/agent.py`. Acceptance: parent context preserved test. LOC estimate 200.
- **Substrate today:** no `src/polaris_graph/followup/` module exists. F11 (follow-up questions) substrate is greenfield.
- **Honest framing per CLAUDE.md §9.4 + LAW II:**
  - **F11 production wiring (graph_v4 calling the follow-up agent on a follow-up question)** is follow-up I-f11-001b — needs UI surface + scope-gate routing.
  - **This issue ships the standalone agent module + tests:** `FollowUpAgent` class with `compose(parent_run_context, follow_up_question) -> ComposedQuery` that preserves parent topic/template/known-evidence-ids and prepends them to the new query.

## Plan

### `src/polaris_graph/followup/__init__.py` (NEW)

1. Module docstring noting Phase-1 substrate scope per CLAUDE.md §9.4.

### `src/polaris_graph/followup/agent.py` (NEW)

2. `ParentRunContext` dataclass (frozen): `parent_run_id: str`, `template: str`, `parent_question: str`, `known_evidence_ids: list[str]`, `parent_summary: str | None = None`.
3. `ComposedQuery` dataclass (frozen): `effective_question: str`, `inherited_template: str`, `parent_run_id: str`, `inherited_evidence_ids: list[str]`.
4. `FollowUpAgent.compose(parent: ParentRunContext, follow_up: str) -> ComposedQuery`:
   - Validate `follow_up` non-blank.
   - Build effective_question: `f"Follow-up to '{parent.parent_question}': {follow_up}"`.
   - inherit `template` and `parent_run_id` directly.
   - inherit `known_evidence_ids` (deduplicated).
   - return `ComposedQuery`.
5. NO LLM call — pure deterministic substrate. LLM-augmented follow-up disambiguation is I-f11-002.

### Tests `tests/polaris_graph/followup/test_agent.py` (NEW)

6. `test_compose_preserves_parent_template`: parent template in → composed template out.
7. `test_compose_preserves_parent_run_id`: parent_run_id in → composed parent_run_id out.
8. `test_compose_inherits_known_evidence_ids_deduped`: parent has [A, B, A] → composed has [A, B].
9. `test_compose_effective_question_format`: composed effective_question contains parent question + follow-up text.
10. `test_compose_rejects_blank_follow_up`: empty / whitespace-only follow-up raises ValueError.
11. `test_compose_handles_no_parent_summary`: parent_summary=None still valid.

## Risks for Codex Red-Team

1. **§9.4 backend hygiene:** no `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs.
2. **Frozen dataclasses:** no mutable default args; lists default via `field(default_factory=list)`.
3. **CHARTER §3 LOC cap:** estimated agent.py ~70, __init__ ~5, test ~80 = ~155. Under 200.

## Acceptance criteria

1. New `src/polaris_graph/followup/__init__.py` and `agent.py`.
2. `ParentRunContext` and `ComposedQuery` dataclasses defined.
3. `FollowUpAgent.compose` preserves parent template + run_id + dedup'd evidence_ids.
4. Effective question contains parent question + follow-up text.
5. ValueError on blank follow-up.
6. 6 tests in `tests/polaris_graph/followup/test_agent.py` pass.
7. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-7.
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
