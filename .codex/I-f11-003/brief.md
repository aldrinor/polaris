# Codex Brief Review — I-f11-003 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (schema import):** explicit imports — `from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan`. Place the new module at `src/polaris_graph/followup/inheritance.py` but cross-package import is fine since polaris_graph and polaris_v6 are both under `src/`.
- **P1 fix (no-re-retrieval test):** add module-level assertion AND a `monkeypatch` test. Module-level: `inheritance.py` has zero imports from any retrieval/fetch module. Test: monkeypatch `polaris_graph.tools.react_agent.ReactAnalysisAgent.run` (or a similar retrieval entry point) to raise immediately; call `compose_with_inheritance`; assert it succeeds (proving no retrieval was attempted).
- **P1 fix (merger pass-through):** add `test_inherited_spans_pass_through_to_merger` — feeds inherited spans into `polaris_v6.adapters.evidence_pool_merger.merge_evidence_pool(retrieval_spans=inherited, uploaded_chunks=[], memory_summaries=[])` and asserts each output span has the same `evidence_id`, `source_url`, `source_tier`, `span_start`, `span_end`, `span_text` as the parent. Span IDs may get an `ev_` prefix per `_evidence_id_for_retrieval` so test asserts `ends_with(parent.evidence_id)` after stripping leading `ev_` if present.
- **P2 fix:** `compose_with_inheritance` builds `ParentRunContext.known_evidence_ids` from `[s.evidence_id for s in parent_contract.evidence_pool]`. Asserted in a new test.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f11-003 — Evidence Contract inheritance. Scope: follow-up inherits parent's accepted-source pool. Acceptance: integration test; no re-retrieval of parent. LOC estimate 130.
- **Substrate today:** I-f11-001 added `FollowUpAgent` with `ParentRunContext.known_evidence_ids`. No mechanism to convert parent `EvidenceContract.evidence_pool` (list[SourceSpan]) into the follow-up's merger input.
- **Honest framing per CLAUDE.md §9.4:** ship a deterministic helper that takes a parent `EvidenceContract` and returns the accepted source pool as `list[SourceSpan]`, plus a thin integration test verifying the source spans pass through to the merger unchanged.

## Plan

### `src/polaris_graph/followup/inheritance.py` (NEW)

1. `def inherit_evidence_pool(parent_contract: EvidenceContract) -> list[SourceSpan]`: returns a defensive copy of `parent_contract.evidence_pool`. Pure function.
2. `def compose_with_inheritance(agent: FollowUpAgent, parent_contract: EvidenceContract, parent_question: str, follow_up: str) -> tuple[ComposedQuery, list[SourceSpan]]`: orchestrates `agent.compose` + `inherit_evidence_pool`, returning both the composed query and the inherited spans.

### Tests `tests/polaris_graph/followup/test_inheritance.py` (NEW)

3. `test_inherit_evidence_pool_returns_copy`: parent contract → returned list is a fresh copy.
4. `test_inherit_evidence_pool_preserves_order`: spans returned in same order as parent.
5. `test_compose_with_inheritance_returns_both`: ComposedQuery and spans both populated.
6. `test_compose_with_inheritance_no_re_retrieval`: assert that the function does NOT call any retrieval/network function (it's pure given the contract). Use a sentinel: assert `len(returned_spans) == len(parent.evidence_pool)` AND `every(s in returned for s in parent.evidence_pool)`.
7. `test_inherit_evidence_pool_empty_pool`: parent with empty evidence_pool returns empty list.

## Risks for Codex Red-Team

1. **Defensive copy:** `[*parent_contract.evidence_pool]` — fresh list. SourceSpan is Pydantic BaseModel (immutable enough).
2. **§9.4 backend hygiene:** no `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs.
3. **CHARTER §3 LOC cap:** estimated inheritance.py ~30, test ~70 = ~100. Under 200.

## Acceptance criteria

1. New `src/polaris_graph/followup/inheritance.py` with `inherit_evidence_pool` and `compose_with_inheritance`.
2. Functions are pure — no network/retrieval calls.
3. 5 tests in `tests/polaris_graph/followup/test_inheritance.py` pass.
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
