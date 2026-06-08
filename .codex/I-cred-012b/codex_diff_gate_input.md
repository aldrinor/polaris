HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings; reserve P0/P1 for real execution blockers; classify cosmetic as P2/P3. APPROVE iff zero P0 AND zero P1.

# DIFF GATE — credibility redesign build phase (umbrella I-ready-021 #1148)

Review the NEW-MODULE diff below for code correctness against its plan-phase spec
(`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`). This is faithfulness-adjacent code.

## HARD CONSTRAINTS (operator-locked)
- **Default-OFF byte-identical:** the module must be inert unless explicitly invoked by a flag/caller; turning it OFF (or not wiring it) leaves existing behavior byte-identical. No production path is changed in this phase.
- **Faithfulness gates UNTOUCHED:** strict_verify (`provenance_generator.py`), 4-role D8, two-family segregation, corpus_approval are NOT edited or weakened. This phase is a NEW module only.
- **LAW VI:** no hardcoded thresholds/paths — config/env; snake_case; no magic numbers; no live data in unit tests (fixtures only).

## VERIFY SPECIFICALLY
1. The module implements its plan-phase spec correctly (read the named layer/phase in the plan).
2. **The phase invariant is actually enforced AND tested** (e.g. P4: a copied row joining a cluster — even higher-authority — cannot change the cluster set / canonical origin; P5: recall-first contradictions + conservative-singleton never over-merges; P3: retraction hard-penalty + config thresholds).
3. The unit tests are MEANINGFUL (not assertion-relaxed to pass) and the attached SMOKE result is green.
4. No faithfulness gate is touched; nothing in the production path changes with the module un-wired.

## SMOKE EVIDENCE (attached below the diff — the offline pytest result is the evidence, not a self-report)

## OUTPUT SCHEMA (YAML)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

============ THE DIFF + SMOKE EVIDENCE ============
## PHASE: I-cred-012b (#1165) — production credibility JUDGE factory diff. make_credibility_judge(call_llm)->judge(question,payload)->dict for P2 score_source_credibility. PURE prompt-format (build_credibility_prompt) + JSON-parse (parse_credibility_response, tolerates code-fence/prose, non-dict/no-JSON => {}). call_llm DEPENDENCY-INJECTED (runner binds open-weight model + OpenRouter in 012a; tests inject a stub). Transport raise => {} => P2 bounded per-row judge_error. Contract verified to match credibility_skill._apply_judge (reliability_score required, relevance defaults 1.0). NO network in the module; spend only when 012a threads it under PG_SWEEP_CREDIBILITY_REDESIGN. SMOKE: 9 passed (parse/fence/non-dict/transport-fail/flows-through-P2-nonerror/malformed-judge_error/prompt-content).
```diff
diff --git a/src/polaris_graph/authority/credibility_judge.py b/src/polaris_graph/authority/credibility_judge.py
new file mode 100644
index 00000000..2882b521
--- /dev/null
+++ b/src/polaris_graph/authority/credibility_judge.py
@@ -0,0 +1,85 @@
+"""I-cred-012b — production credibility JUDGE factory (LLM-backed) for the P2 credibility skill.
+
+Builds the injected ``judge(research_question, payload) -> dict`` that
+``credibility_skill.score_source_credibility`` consumes per source. The factory is PURE prompt-format +
+JSON-parse; the LLM call is DEPENDENCY-INJECTED (``call_llm``) so it is offline-testable and the model /
+client live entirely in the caller the sweep runner supplies (012a). Open-weight model ONLY (the certified
+voter slate) — the caller binds the model.
+
+Robustness contract (matches `credibility_skill._apply_judge`): on ANY malformed LLM output the judge
+returns a dict missing/!=reliability_score (or ``{}``), which P2 isolates as a per-row ``judge_error``
+(recall-first, fail-loud-but-bounded). It NEVER raises into P2 (P2 catches, but we keep it clean).
+"""
+from __future__ import annotations
+
+import json
+import re
+from typing import Any, Callable
+
+# The judge sees ONLY the bounded payload (source identity + title/url/snippet + authority prior +
+# domain_hint) — same payload `credibility_skill._build_judge_payload` assembles. No rubric branch.
+_PROMPT = (
+    "You are a source-credibility judge for ONE source against ONE research question. Judge only this "
+    "source, for this question.\n"
+    "QUESTION: {question}\n"
+    "SOURCE:\n"
+    "  title: {title}\n"
+    "  url: {url}\n"
+    "  snippet: {snippet}\n"
+    "  authority_score (deterministic prior, 0..1): {authority_score}\n"
+    "  domain_hint: {domain_hint}\n\n"
+    "Return STRICT JSON only, no prose, no code fence:\n"
+    '{{"reliability_score": <0..1: how reliable/authoritative this source is FOR THIS QUESTION>, '
+    '"relevance_score": <0..1: how on-topic this source is>, '
+    '"rationale": "<one sentence>", '
+    '"signals_cited": [<signal names you relied on>], '
+    '"query_need": "<a follow-up query if this source is thin, else empty>"}}'
+)
+
+
+def build_credibility_prompt(research_question: str, payload: dict[str, Any]) -> str:
+    """Pure: render the per-source judging prompt from the P2 payload."""
+    payload = payload or {}
+    return _PROMPT.format(
+        question=research_question,
+        title=payload.get("title", ""),
+        url=payload.get("url", ""),
+        snippet=payload.get("snippet", ""),
+        authority_score=payload.get("authority_score", ""),
+        domain_hint=payload.get("domain_hint", ""),
+    )
+
+
+def parse_credibility_response(text: str) -> dict[str, Any]:
+    """Best-effort: parse the first JSON object in the LLM text. Non-dict / no-JSON => {} (=> judge_error)."""
+    if not text or not isinstance(text, str):
+        return {}
+    match = re.search(r"\{.*\}", text, re.DOTALL)  # tolerate code fences / leading prose
+    if not match:
+        return {}
+    try:
+        obj = json.loads(match.group(0))
+    except (ValueError, TypeError):
+        return {}
+    return obj if isinstance(obj, dict) else {}
+
+
+def make_credibility_judge(call_llm: Callable[[str], str]) -> Callable[[str, dict], dict]:
+    """Return ``judge(research_question, payload) -> dict`` for ``score_source_credibility``.
+
+    ``call_llm(prompt) -> text`` is injected — the sweep runner (012a) binds the open-weight model + the
+    OpenRouter client; tests inject a deterministic stub. The judge formats the prompt, calls the LLM, and
+    parses JSON; a malformed/empty response yields ``{}`` so P2 records a bounded per-row ``judge_error``.
+    """
+    if call_llm is None:
+        raise ValueError("make_credibility_judge requires an injected call_llm(prompt) -> text")
+
+    def judge(research_question: str, payload: dict) -> dict:
+        prompt = build_credibility_prompt(research_question, payload)
+        try:
+            text = call_llm(prompt)
+        except Exception:
+            return {}  # transport failure for this row => P2 judge_error (isolated, bounded)
+        return parse_credibility_response(text)
+
+    return judge
diff --git a/tests/polaris_graph/authority/test_credibility_judge_phase12b.py b/tests/polaris_graph/authority/test_credibility_judge_phase12b.py
new file mode 100644
index 00000000..b30b9fa7
--- /dev/null
+++ b/tests/polaris_graph/authority/test_credibility_judge_phase12b.py
@@ -0,0 +1,66 @@
+"""I-cred-012b — production credibility judge factory. Offline, deterministic, no network."""
+from __future__ import annotations
+
+import pytest
+
+from src.polaris_graph.authority.credibility_judge import (
+    build_credibility_prompt,
+    make_credibility_judge,
+    parse_credibility_response,
+)
+from src.polaris_graph.authority.credibility_skill import score_source_credibility
+
+
+def test_requires_call_llm():
+    with pytest.raises(ValueError):
+        make_credibility_judge(None)
+
+
+def test_happy_path_parses_json():
+    judge = make_credibility_judge(
+        lambda p: '{"reliability_score": 0.8, "relevance_score": 0.9, "rationale": "ok"}'
+    )
+    out = judge("q", {"title": "t", "url": "u"})
+    assert out["reliability_score"] == 0.8 and out["relevance_score"] == 0.9
+
+
+def test_code_fence_and_prose_tolerated():
+    judge = make_credibility_judge(lambda p: 'Sure:\n```json\n{"reliability_score": 0.5}\n```')
+    assert judge("q", {})["reliability_score"] == 0.5
+
+
+def test_malformed_returns_empty_dict():
+    assert make_credibility_judge(lambda p: "no json here")("q", {}) == {}
+    assert make_credibility_judge(lambda p: "[1,2,3]")("q", {}) == {}  # non-dict JSON
+
+
+def test_transport_failure_returns_empty():
+    def boom(prompt):
+        raise RuntimeError("503 upstream")
+
+    assert make_credibility_judge(boom)("q", {}) == {}
+
+
+def test_prompt_includes_question_and_source():
+    p = build_credibility_prompt("does X work?", {"title": "Study A", "url": "http://a", "snippet": "snip"})
+    assert "does X work?" in p and "Study A" in p and "http://a" in p
+
+
+def test_parse_helper_direct():
+    assert parse_credibility_response('{"a": 1}') == {"a": 1}
+    assert parse_credibility_response("") == {}
+    assert parse_credibility_response("nope") == {}
+
+
+def test_flows_through_p2_as_non_error_judgment():
+    judge = make_credibility_judge(lambda p: '{"reliability_score": 0.7, "relevance_score": 1.0}')
+    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH", "signal_scores": {"x": 1}}]
+    out = score_source_credibility("q", rows, judge=judge)[0]
+    assert out.judge_error is False and out.reliability_score == 0.7
+
+
+def test_malformed_judge_marks_p2_judge_error():
+    judge = make_credibility_judge(lambda p: "garbage, no json")
+    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH", "signal_scores": {"x": 1}}]
+    out = score_source_credibility("q", rows, judge=judge)[0]
+    assert out.judge_error is True
```
