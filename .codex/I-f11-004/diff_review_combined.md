# Codex Diff Review — I-f11-004 (ITER 1 of 5)

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

- **Issue:** I-f11-004 — Refusal handling for out-of-scope follow-ups.
- **Brief APPROVE iter 2.** `.codex/I-f11-004/codex_brief_verdict.txt`.
- **Net LOC:** 178 (under 200).
- **Branch:** `bot/I-f11-004`.

## What changed

1. `src/polaris_graph/followup/refusal.py` (NEW, 56 LOC):
   - `RefusalDecision` frozen dataclass.
   - `detect_out_of_scope(parent_template, follow_up, *, min_overlap=1)` — `general` bypasses; otherwise zero shared keyword tokens triggers refusal.
   - `compose_or_refuse(agent, parent, follow_up)` — routes through `detect_out_of_scope` first.
2. `src/polaris_graph/followup/inheritance.py` (MODIFY, +25 LOC net):
   - New `compose_with_inheritance_or_refuse(agent, parent_contract, follow_up)`. Returns `(RefusalDecision, [])` on out-of-scope; `(ComposedQuery, inherited_spans)` otherwise.
3. `tests/polaris_graph/followup/test_refusal.py` (NEW, 97 LOC, 7 tests):
   - `test_refuses_zero_overlap_specific_template` (adversarial — "sky blue" vs `clinical_summary`)
   - `test_accepts_one_keyword_overlap` (`summary` shared)
   - `test_general_template_never_refuses`
   - `test_compose_or_refuse_returns_composed_when_in_scope`
   - `test_compose_or_refuse_returns_refusal_when_out_of_scope`
   - `test_adversarial_punctuation_and_case` ("WHAT ABOUT THE SUMMARY?!")
   - `test_compose_with_inheritance_or_refuse_routes_refusal` — both refused and accepted inheritance paths.

## Test results

```
$ pytest tests/polaris_graph/followup/ -q
collected 23 items
test_agent.py .........        [ 39%]
test_inheritance.py .......    [ 69%]
test_refusal.py .......        [100%]
============= 23 passed in 2.78s =============
```

## Risks for Codex Red-Team

1. **Heuristic quality.** Exact-token overlap is naive. Single-token templates over-refuse. Documented as MVP debt in module docstring.
2. **`compose_with_inheritance_or_refuse` separate function** preserves `compose_with_inheritance` (I-f11-003) backward-compatible — callers can opt-in to refusal.
3. **§9.4 hygiene.** No `try/except: pass`, no magic numbers (`min_overlap=1` is a named keyword arg with explicit comparison), no `time.sleep`, no TODO, no `unittest.mock` import.
4. **CHARTER §3 LOC cap.** 178 net (under 200).
5. **Adversarial test (issue acceptance)** — `test_refuses_zero_overlap_specific_template` is the explicit named test.

## Acceptance criteria — forced enumeration

1. ✅ `src/polaris_graph/followup/refusal.py` with `detect_out_of_scope` + `compose_or_refuse`.
2. ✅ Inheritance path routed through refusal via `compose_with_inheritance_or_refuse`.
3. ✅ Refusal returns typed `RefusalDecision` with explanation `reason`.
4. ✅ 7 tests pass (1 adversarial + inheritance route).
5. ✅ CHARTER §3 LOC cap (178 ≤ 200).

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

(Full diff appended below.)
diff --git a/src/polaris_graph/followup/inheritance.py b/src/polaris_graph/followup/inheritance.py
index 59c7f33..ef1ad43 100644
--- a/src/polaris_graph/followup/inheritance.py
+++ b/src/polaris_graph/followup/inheritance.py
@@ -13,6 +13,7 @@ from polaris_graph.followup.agent import (
     FollowUpAgent,
     ParentRunContext,
 )
+from polaris_graph.followup.refusal import RefusalDecision, compose_or_refuse
 from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan
 
 
@@ -42,3 +43,27 @@ def compose_with_inheritance(
     composed = agent.compose(parent, follow_up)
     inherited = inherit_evidence_pool(parent_contract)
     return composed, inherited
+
+
+def compose_with_inheritance_or_refuse(
+    agent: FollowUpAgent,
+    parent_contract: EvidenceContract,
+    follow_up: str,
+) -> tuple[ComposedQuery | RefusalDecision, list[SourceSpan]]:
+    """Inheritance-aware compose that routes through out-of-scope refusal.
+
+    Returns (RefusalDecision, []) when the follow-up is out-of-scope, or
+    (ComposedQuery, inherited_spans) when in-scope.
+    """
+    parent = ParentRunContext(
+        parent_run_id=parent_contract.run_id,
+        template=parent_contract.template,
+        parent_question=parent_contract.question,
+        known_evidence_ids=[s.evidence_id for s in parent_contract.evidence_pool],
+        parent_summary=None,
+    )
+    decision = compose_or_refuse(agent, parent, follow_up)
+    if isinstance(decision, RefusalDecision):
+        return decision, []
+    inherited = inherit_evidence_pool(parent_contract)
+    return decision, inherited
diff --git a/src/polaris_graph/followup/refusal.py b/src/polaris_graph/followup/refusal.py
new file mode 100644
index 0000000..4ea4fd8
--- /dev/null
+++ b/src/polaris_graph/followup/refusal.py
@@ -0,0 +1,56 @@
+"""Out-of-scope refusal handling for follow-up runs (I-f11-004).
+
+Heuristic: a follow-up is out-of-scope when zero of its tokens
+(case-insensitive, punctuation-stripped) appear in the parent
+template's `_`-separated keyword list. MVP debt: single-token templates
+over-refuse; LLM-augmented intent matching is post-MVP.
+"""
+
+from __future__ import annotations
+
+import re
+from dataclasses import dataclass
+
+from polaris_graph.followup.agent import (
+    ComposedQuery,
+    FollowUpAgent,
+    ParentRunContext,
+)
+
+
+_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
+
+
+@dataclass(frozen=True)
+class RefusalDecision:
+    is_refused: bool
+    reason: str | None
+    template_keywords: list[str]
+    question_overlap: list[str]
+
+
+def detect_out_of_scope(
+    parent_template: str, follow_up: str, *, min_overlap: int = 1
+) -> RefusalDecision:
+    keywords = [t for t in parent_template.lower().split("_") if t]
+    if parent_template == "general":
+        return RefusalDecision(False, None, keywords, [])
+    words = _PUNCT_RE.sub(" ", follow_up.lower()).split()
+    kw_set = set(keywords)
+    overlap = [w for w in words if w in kw_set]
+    if len(overlap) < min_overlap:
+        reason = (
+            f"follow-up has {len(overlap)} shared keyword(s) with parent "
+            f"template '{parent_template}' (need >= {min_overlap}); out-of-scope"
+        )
+        return RefusalDecision(True, reason, keywords, overlap)
+    return RefusalDecision(False, None, keywords, overlap)
+
+
+def compose_or_refuse(
+    agent: FollowUpAgent, parent: ParentRunContext, follow_up: str
+) -> ComposedQuery | RefusalDecision:
+    decision = detect_out_of_scope(parent.template, follow_up)
+    if decision.is_refused:
+        return decision
+    return agent.compose(parent, follow_up)
diff --git a/tests/polaris_graph/followup/test_refusal.py b/tests/polaris_graph/followup/test_refusal.py
new file mode 100644
index 0000000..b933307
--- /dev/null
+++ b/tests/polaris_graph/followup/test_refusal.py
@@ -0,0 +1,97 @@
+"""I-f11-004 — refusal handling tests."""
+
+from __future__ import annotations
+
+from polaris_graph.followup.agent import (
+    ComposedQuery,
+    FollowUpAgent,
+    ParentRunContext,
+)
+from polaris_graph.followup.inheritance import compose_with_inheritance_or_refuse
+from polaris_graph.followup.refusal import (
+    RefusalDecision,
+    compose_or_refuse,
+    detect_out_of_scope,
+)
+from polaris_v6.schemas.evidence_contract import EvidenceContract, SourceSpan
+
+
+def _ctx(template: str = "clinical_summary") -> ParentRunContext:
+    return ParentRunContext(
+        parent_run_id="run_42", template=template,
+        parent_question="What is the efficacy of drug X?",
+        known_evidence_ids=["ev_a"], parent_summary=None,
+    )
+
+
+def _contract(template: str = "clinical_summary") -> EvidenceContract:
+    return EvidenceContract(
+        run_id="run_42", template=template,
+        question="What is the efficacy of drug X?",
+        queued_at="2026-05-08T00:00:00Z", finished_at="2026-05-08T00:00:30Z",
+        pipeline_status="success",
+        evidence_pool=[SourceSpan(evidence_id="ev_a", source_url="https://example.test/a",
+                                  source_tier="T1", span_start=0, span_end=5, span_text="alpha")],
+        verified_sentences=[], frame_coverage=[], contradictions=[],
+        cost_usd=0.0, generator_model="g", verifier_model="v",
+        family_segregation_passed=True,
+    )
+
+
+def test_refuses_zero_overlap_specific_template() -> None:
+    decision = detect_out_of_scope("clinical_summary", "Why is the sky blue?")
+    assert decision.is_refused is True
+    assert decision.reason is not None
+    assert "clinical_summary" in decision.reason
+    assert decision.template_keywords == ["clinical", "summary"]
+    assert decision.question_overlap == []
+
+
+def test_accepts_one_keyword_overlap() -> None:
+    decision = detect_out_of_scope(
+        "clinical_summary", "What about the summary statistics?"
+    )
+    assert decision.is_refused is False
+    assert decision.question_overlap == ["summary"]
+
+
+def test_general_template_never_refuses() -> None:
+    decision = detect_out_of_scope("general", "random topic completely off")
+    assert decision.is_refused is False
+
+
+def test_compose_or_refuse_returns_composed_when_in_scope() -> None:
+    result = compose_or_refuse(
+        FollowUpAgent(), _ctx(), "Tell me more about the clinical efficacy"
+    )
+    assert isinstance(result, ComposedQuery)
+    assert "clinical efficacy" in result.effective_question
+
+
+def test_compose_or_refuse_returns_refusal_when_out_of_scope() -> None:
+    result = compose_or_refuse(FollowUpAgent(), _ctx(), "Why is the sky blue?")
+    assert isinstance(result, RefusalDecision)
+    assert result.is_refused is True
+    assert result.reason is not None
+
+
+def test_adversarial_punctuation_and_case() -> None:
+    decision = detect_out_of_scope("clinical_summary", "WHAT ABOUT THE SUMMARY?!")
+    assert decision.is_refused is False
+    assert decision.question_overlap == ["summary"]
+
+
+def test_compose_with_inheritance_or_refuse_routes_refusal() -> None:
+    refused, spans = compose_with_inheritance_or_refuse(
+        FollowUpAgent(), _contract(), "Why is the sky blue?"
+    )
+    assert isinstance(refused, RefusalDecision)
+    assert refused.is_refused is True
+    assert spans == []
+
+    composed, inherited = compose_with_inheritance_or_refuse(
+        FollowUpAgent(), _contract(), "Tell me more about the clinical findings"
+    )
+    assert isinstance(composed, ComposedQuery)
+    assert len(inherited) == 1
+    assert inherited[0].evidence_id == "ev_a"
