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
diff --git a/src/polaris_graph/followup/multi_turn.py b/src/polaris_graph/followup/multi_turn.py
new file mode 100644
index 0000000..0644237
--- /dev/null
+++ b/src/polaris_graph/followup/multi_turn.py
@@ -0,0 +1,54 @@
+"""Multi-turn follow-up driver (I-f11-005).
+
+Runs N follow-ups against the SAME parent contract. Each turn flows
+through `compose_with_inheritance_or_refuse`: out-of-scope → typed
+RefusalDecision; in-scope → ComposedQuery + inherited spans. Refusal
+does NOT short-circuit; subsequent turns still execute. Chained-context
+follow-ups (turn-2 inheriting from turn-1) are post-MVP — call
+run_multi_turn again with a new contract to chain.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+from polaris_graph.followup.agent import ComposedQuery, FollowUpAgent
+from polaris_graph.followup.inheritance import compose_with_inheritance_or_refuse
+from polaris_graph.followup.refusal import RefusalDecision
+from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan
+
+
+@dataclass(frozen=True)
+class TurnResult:
+    turn_index: int
+    follow_up: str
+    composed: ComposedQuery | None
+    refusal: RefusalDecision | None
+    inherited_spans: list[SourceSpan]
+
+
+def run_multi_turn(
+    agent: FollowUpAgent,
+    parent_contract: EvidenceContract,
+    follow_ups: list[str],
+) -> list[TurnResult]:
+    results: list[TurnResult] = []
+    for i, fu in enumerate(follow_ups):
+        decision, spans = compose_with_inheritance_or_refuse(
+            agent, parent_contract, fu
+        )
+        if isinstance(decision, RefusalDecision):
+            results.append(
+                TurnResult(
+                    turn_index=i, follow_up=fu, composed=None,
+                    refusal=decision, inherited_spans=spans,
+                )
+            )
+        else:
+            results.append(
+                TurnResult(
+                    turn_index=i, follow_up=fu, composed=decision,
+                    refusal=None, inherited_spans=spans,
+                )
+            )
+    return results
diff --git a/tests/polaris_graph/followup/test_multi_turn.py b/tests/polaris_graph/followup/test_multi_turn.py
new file mode 100644
index 0000000..bd6a618
--- /dev/null
+++ b/tests/polaris_graph/followup/test_multi_turn.py
@@ -0,0 +1,98 @@
+"""I-f11-005 — multi-turn follow-up tests."""
+
+from __future__ import annotations
+
+from polaris_graph.followup.agent import ComposedQuery, FollowUpAgent
+from polaris_graph.followup.multi_turn import TurnResult, run_multi_turn
+from polaris_graph.followup.refusal import RefusalDecision
+from polaris_v6.adapters.evidence_pool_merger import merge_evidence_pool
+from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan
+
+
+def _span(eid: str, text: str) -> SourceSpan:
+    return SourceSpan(
+        evidence_id=eid, source_url=f"https://x.test/{eid}",
+        source_tier="T1", span_start=0, span_end=len(text), span_text=text,
+    )
+
+
+def _contract(spans: list[SourceSpan] | None = None) -> EvidenceContract:
+    return EvidenceContract(
+        run_id="run_p", template="clinical_summary",
+        question="Drug X efficacy?",
+        queued_at="2026-05-08T00:00:00Z", finished_at="2026-05-08T00:00:30Z",
+        pipeline_status="success",
+        evidence_pool=spans if spans is not None else [_span("ev_a", "alpha"), _span("ev_b", "beta")],
+        verified_sentences=[], frame_coverage=[], contradictions=[],
+        cost_usd=0.0, generator_model="g", verifier_model="v",
+        family_segregation_passed=True,
+    )
+
+
+def test_five_sequential_follow_ups_all_grounded() -> None:
+    contract = _contract()
+    follow_ups = [
+        "Tell me about the clinical methodology",
+        "What about secondary clinical endpoints?",
+        "Summarize the clinical adverse events",
+        "What clinical biomarkers were measured?",
+        "How does the clinical dose schedule work?",
+    ]
+    results = run_multi_turn(FollowUpAgent(), contract, follow_ups)
+    assert len(results) == 5
+    for i, r in enumerate(results):
+        assert r.turn_index == i
+        assert isinstance(r.composed, ComposedQuery)
+        assert r.refusal is None
+        assert r.composed.parent_run_id == "run_p"
+        assert r.composed.inherited_template == "clinical_summary"
+        assert r.composed.inherited_evidence_ids == ["ev_a", "ev_b"]
+        assert len(r.inherited_spans) == 2
+
+
+def test_mix_in_scope_and_refusal() -> None:
+    contract = _contract()
+    follow_ups = [
+        "Tell me about the clinical methodology",
+        "Why is the sky blue?",
+        "What about clinical safety?",
+        "Random topic about cars",
+        "Summarize clinical findings",
+    ]
+    results = run_multi_turn(FollowUpAgent(), contract, follow_ups)
+    accepted = [r for r in results if r.composed is not None]
+    refused = [r for r in results if r.refusal is not None]
+    assert len(accepted) == 3
+    assert len(refused) == 2
+    for r in refused:
+        assert r.refusal is not None and r.refusal.is_refused is True
+        assert r.inherited_spans == []
+
+
+def test_turn_index_preserved() -> None:
+    results = run_multi_turn(
+        FollowUpAgent(), _contract(),
+        ["clinical a", "clinical b", "clinical c"],
+    )
+    assert [r.turn_index for r in results] == [0, 1, 2]
+
+
+def test_inherited_spans_pass_through_to_merger_per_turn() -> None:
+    parent_spans = [_span("ev_a", "alpha"), _span("ev_b", "beta")]
+    results = run_multi_turn(
+        FollowUpAgent(), _contract(parent_spans),
+        ["clinical findings 1", "clinical findings 2"],
+    )
+    for r in results:
+        assert r.composed is not None
+        merged = merge_evidence_pool(
+            retrieval_spans=r.inherited_spans, uploaded_chunks=[], memory_summaries=[]
+        )
+        assert len(merged) == len(parent_spans)
+        for parent, out in zip(parent_spans, merged, strict=True):
+            assert out.span_text == parent.span_text
+            assert out.source_url == parent.source_url
+
+
+def test_empty_follow_ups_returns_empty() -> None:
+    assert run_multi_turn(FollowUpAgent(), _contract(), []) == []
