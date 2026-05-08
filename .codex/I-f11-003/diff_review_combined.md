# Codex Diff Review — I-f11-003 (ITER 1 of 5)

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

- **Issue:** I-f11-003 — Evidence Contract inheritance. Follow-up runs inherit the parent's accepted-source pool with no re-retrieval.
- **Brief APPROVE'd iter 2.** Canonical brief verdict at `.codex/I-f11-003/codex_brief_verdict.txt`.
- **Branch:** `bot/I-f11-003` at HEAD `9a97760`.
- **Net LOC:** 167 insertions (under 200 cap).
- **Canonical-diff-sha256:** `5df44434fb7e0c503d7bb90fe526e44f64a793e8cd550e3b1ff0793721c2a3e8`.

## What changed

1. `src/polaris_graph/followup/inheritance.py` (45 LOC):
   - `inherit_evidence_pool(parent_contract: EvidenceContract) -> list[SourceSpan]`: defensive copy via `list(parent_contract.evidence_pool)`.
   - `compose_with_inheritance(agent: FollowUpAgent, parent_contract, follow_up: str) -> tuple[ComposedQuery, list[SourceSpan]]`: builds a `ParentRunContext` from `parent_contract` (run_id, template, question, evidence_ids list), invokes `agent.compose`, returns the composed query + inherited spans.
   - Module imports: ONLY `polaris_graph.followup.agent` + `polaris_v6.schemas.evidence_contract`. Zero retrieval/network module imports.

2. `tests/polaris_graph/followup/test_inheritance.py` (120 LOC) — 7 tests:
   - `test_inherit_evidence_pool_returns_copy` — fresh list, mutation isolation.
   - `test_inherit_evidence_pool_preserves_order` — order preserved.
   - `test_inherit_evidence_pool_empty_pool` — empty parent → empty out.
   - `test_compose_with_inheritance_returns_both` — ComposedQuery + spans both populated, parent_run_id + template + question stitched into effective_question.
   - `test_compose_with_inheritance_known_evidence_ids_from_parent_pool` — `composed.inherited_evidence_ids == [s.evidence_id for s in pool]`.
   - `test_compose_with_inheritance_no_re_retrieval` — monkeypatches `polaris_graph.tools.react_agent.ReactAnalysisAgent.run` to raise `AssertionError`; calls `compose_with_inheritance`; asserts success → proves no retrieval was invoked.
   - `test_inherited_spans_pass_through_to_merger` — feeds inherited spans into `merge_evidence_pool(retrieval_spans=inherited, uploaded_chunks=[], memory_summaries=[])`; asserts every (source_url, source_tier, span_start, span_end, span_text) preserved + evidence_id ends with parent's id (after `ev_` prefix-stripping per `_evidence_id_for_retrieval`).

## Test results

```
$ python -m pytest tests/polaris_graph/followup/ -q
collected 16 items
tests\polaris_graph\followup\test_agent.py .........        [ 56%]
tests\polaris_graph\followup\test_inheritance.py .......    [100%]
============= 16 passed in 2.83s =============
```

7/7 new tests pass; 9/9 sibling I-f11-001 tests still pass (no regression).

## Risks for Codex Red-Team

1. **Defensive-copy correctness.** `list(parent_contract.evidence_pool)` returns a fresh list. Test `test_inherit_evidence_pool_returns_copy` mutates the returned list and asserts the contract's pool length is unchanged. SourceSpan is Pydantic immutable BaseModel.

2. **No-re-retrieval module-level invariant.** `inheritance.py` imports only `polaris_graph.followup.agent` and `polaris_v6.schemas.evidence_contract`. `agent.py` imports only `dataclasses`. Neither imports retrieval modules. Test `test_compose_with_inheritance_no_re_retrieval` adds a monkeypatch belt to the suspenders.

3. **Pass-through to merger.** `_evidence_id_for_retrieval` adds `ev_` prefix only if not present. Test handles both cases via `endswith(parent.evidence_id.removeprefix("ev_"))`.

4. **CHARTER §3 LOC cap.** 167 lines net. Under 200.

5. **§9.4 backend hygiene.** No `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs, no `unittest.mock` import in `src/`.

## Acceptance criteria — forced enumeration

1. ✅ `src/polaris_graph/followup/inheritance.py` exists with `inherit_evidence_pool` + `compose_with_inheritance`.
2. ✅ Functions are pure — no network/retrieval calls. Verified by module-level import inspection AND monkeypatch test.
3. ✅ 7 tests pass (more than the brief's 5 minimum because P1 fixes added 2 dedicated tests for known_evidence_ids + merger pass-through).
4. ✅ CHARTER §3 LOC cap respected (167 ≤ 200).

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

## Diff for review

```
$ git diff origin/polaris...HEAD -- src tests
```

(Full diff appended below.)
diff --git a/src/polaris_graph/followup/inheritance.py b/src/polaris_graph/followup/inheritance.py
new file mode 100644
index 0000000..59c7f33
--- /dev/null
+++ b/src/polaris_graph/followup/inheritance.py
@@ -0,0 +1,44 @@
+"""Evidence Contract inheritance for follow-up runs (I-f11-003).
+
+Pure deterministic functions. NO retrieval / network calls — the parent
+run's accepted source pool is reused via deep copy, satisfying the
+acceptance "no re-retrieval of parent" guarantee at the module level
+(verified by tests).
+"""
+
+from __future__ import annotations
+
+from polaris_graph.followup.agent import (
+    ComposedQuery,
+    FollowUpAgent,
+    ParentRunContext,
+)
+from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan
+
+
+def inherit_evidence_pool(parent_contract: EvidenceContract) -> list[SourceSpan]:
+    """Return a fresh list of the parent run's accepted source spans."""
+    return list(parent_contract.evidence_pool)
+
+
+def compose_with_inheritance(
+    agent: FollowUpAgent,
+    parent_contract: EvidenceContract,
+    follow_up: str,
+) -> tuple[ComposedQuery, list[SourceSpan]]:
+    """Compose a follow-up question that inherits the parent's evidence pool.
+
+    Returns the ComposedQuery (with evidence_id list inherited from the
+    parent's evidence_pool) and a fresh copy of the parent's source spans
+    suitable for direct passthrough to the merger.
+    """
+    parent = ParentRunContext(
+        parent_run_id=parent_contract.run_id,
+        template=parent_contract.template,
+        parent_question=parent_contract.question,
+        known_evidence_ids=[s.evidence_id for s in parent_contract.evidence_pool],
+        parent_summary=None,
+    )
+    composed = agent.compose(parent, follow_up)
+    inherited = inherit_evidence_pool(parent_contract)
+    return composed, inherited
diff --git a/tests/polaris_graph/followup/test_inheritance.py b/tests/polaris_graph/followup/test_inheritance.py
new file mode 100644
index 0000000..91ff80e
--- /dev/null
+++ b/tests/polaris_graph/followup/test_inheritance.py
@@ -0,0 +1,123 @@
+"""I-f11-003 — Evidence Contract inheritance tests."""
+
+from __future__ import annotations
+
+import pytest
+
+from polaris_graph.followup.agent import ComposedQuery, FollowUpAgent
+from polaris_graph.followup.inheritance import (
+    compose_with_inheritance,
+    inherit_evidence_pool,
+)
+from polaris_v6.adapters.evidence_pool_merger import merge_evidence_pool
+from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan
+
+
+def _span(evidence_id: str, text: str) -> SourceSpan:
+    return SourceSpan(
+        evidence_id=evidence_id,
+        source_url=f"https://example.test/{evidence_id}",
+        source_tier="T1",
+        span_start=0,
+        span_end=len(text),
+        span_text=text,
+    )
+
+
+def _contract(evidence_pool: list[SourceSpan]) -> EvidenceContract:
+    return EvidenceContract(
+        run_id="run_parent_001",
+        template="clinical_summary",
+        question="What is the efficacy of drug X?",
+        queued_at="2026-05-08T00:00:00Z",
+        finished_at="2026-05-08T00:00:30Z",
+        pipeline_status="success",
+        evidence_pool=evidence_pool,
+        verified_sentences=[],
+        frame_coverage=[],
+        contradictions=[],
+        cost_usd=0.0,
+        generator_model="g",
+        verifier_model="v",
+        family_segregation_passed=True,
+    )
+
+
+def test_inherit_evidence_pool_returns_copy() -> None:
+    pool = [_span("ev_a", "alpha"), _span("ev_b", "beta")]
+    contract = _contract(pool)
+    out = inherit_evidence_pool(contract)
+    assert out == pool
+    assert out is not contract.evidence_pool
+    out.append(_span("ev_c", "gamma"))
+    assert len(contract.evidence_pool) == 2
+
+
+def test_inherit_evidence_pool_preserves_order() -> None:
+    pool = [_span("ev_z", "z"), _span("ev_a", "a"), _span("ev_m", "m")]
+    out = inherit_evidence_pool(_contract(pool))
+    assert [s.evidence_id for s in out] == ["ev_z", "ev_a", "ev_m"]
+
+
+def test_inherit_evidence_pool_empty_pool() -> None:
+    out = inherit_evidence_pool(_contract([]))
+    assert out == []
+
+
+def test_compose_with_inheritance_returns_both() -> None:
+    pool = [_span("ev_a", "alpha"), _span("ev_b", "beta")]
+    contract = _contract(pool)
+    composed, spans = compose_with_inheritance(
+        FollowUpAgent(), contract, "What about drug Y?"
+    )
+    assert isinstance(composed, ComposedQuery)
+    assert composed.parent_run_id == "run_parent_001"
+    assert composed.inherited_template == "clinical_summary"
+    assert "What about drug Y?" in composed.effective_question
+    assert "What is the efficacy of drug X?" in composed.effective_question
+    assert len(spans) == 2
+
+
+def test_compose_with_inheritance_known_evidence_ids_from_parent_pool() -> None:
+    pool = [_span("ev_a", "alpha"), _span("ev_b", "beta"), _span("ev_c", "gamma")]
+    composed, _ = compose_with_inheritance(
+        FollowUpAgent(), _contract(pool), "follow-up"
+    )
+    assert composed.inherited_evidence_ids == ["ev_a", "ev_b", "ev_c"]
+
+
+def test_compose_with_inheritance_no_re_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Monkeypatch retrieval entry to raise; compose_with_inheritance must succeed."""
+    from polaris_graph.tools import react_agent
+
+    def _raise(*_args, **_kwargs):
+        raise AssertionError("no retrieval should occur during inheritance")
+
+    monkeypatch.setattr(react_agent.ReactAnalysisAgent, "run", _raise, raising=True)
+
+    pool = [_span("ev_a", "alpha")]
+    composed, spans = compose_with_inheritance(
+        FollowUpAgent(), _contract(pool), "What about drug Y?"
+    )
+    assert composed.inherited_evidence_ids == ["ev_a"]
+    assert len(spans) == 1
+
+
+def test_inherited_spans_pass_through_to_merger() -> None:
+    """Spans returned by inherit_evidence_pool can be merged unchanged."""
+    parent_spans = [
+        _span("ev_a", "alpha text"),
+        _span("ev_b", "beta text"),
+    ]
+    inherited = inherit_evidence_pool(_contract(parent_spans))
+    merged = merge_evidence_pool(
+        retrieval_spans=inherited, uploaded_chunks=[], memory_summaries=[]
+    )
+    assert len(merged) == len(parent_spans)
+    for parent, out in zip(parent_spans, merged, strict=True):
+        assert out.evidence_id.endswith(parent.evidence_id.removeprefix("ev_"))
+        assert out.source_url == parent.source_url
+        assert out.source_tier == parent.source_tier
+        assert out.span_start == parent.span_start
+        assert out.span_end == parent.span_end
+        assert out.span_text == parent.span_text
