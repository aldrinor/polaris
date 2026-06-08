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
## PHASE: I-cred-012b production credibility JUDGE — DIFF gate ITER 2. Iter-1 P1 + 2 P2 all addressed: (P1) build_credibility_prompt now surfaces the FULL P2 deterministic-signal set per plan §9.1 — authority_score, authority_confidence, source_class, corroboration_count, signal_scores, junk_class, predatory_oa, origin_cluster_id (was only title/url/snippet/authority); + REQUIRED_SIGNAL_FIELDS constant guards against a future drop, asserted in the test. (P2-1) parse_credibility_response now uses json.JSONDecoder().raw_decode to take the FIRST JSON object (not greedy first-{ to last-}); tolerates leading code-fence/prose, ignores trailing prose/second object, and a brace inside a string value no longer prematurely closes it. (P2-2) test strengthened: asserts ALL required signals in the prompt + trailing-prose + brace-in-string parse. call_llm still injected (offline); malformed/transport-fail => {} => P2 bounded judge_error. SMOKE: 9 passed.
```diff
diff --git a/src/polaris_graph/authority/credibility_judge.py b/src/polaris_graph/authority/credibility_judge.py
new file mode 100644
index 00000000..b6743024
--- /dev/null
+++ b/src/polaris_graph/authority/credibility_judge.py
@@ -0,0 +1,118 @@
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
+# The judge sees ONLY the bounded payload — the SAME deterministic signals `_build_judge_payload`
+# assembles (plan §9.1): identity + descriptors + authority prior + source_class + corroboration_count +
+# authority_confidence + signal_scores + junk_class + predatory_oa + origin_cluster_id. No rubric branch.
+_PROMPT = (
+    "You are a source-credibility judge for ONE source against ONE research question. Judge only this "
+    "source, for this question, reasoning from the deterministic signals below.\n"
+    "QUESTION: {question}\n"
+    "SOURCE:\n"
+    "  title: {title}\n"
+    "  url: {url}\n"
+    "  snippet: {snippet}\n"
+    "  authority_score (deterministic prior, 0..1): {authority_score}\n"
+    "  authority_confidence: {authority_confidence}\n"
+    "  source_class: {source_class}\n"
+    "  corroboration_count (independent corroborating sources): {corroboration_count}\n"
+    "  signal_scores: {signal_scores}\n"
+    "  junk_class: {junk_class}\n"
+    "  predatory_oa (predatory open-access flag): {predatory_oa}\n"
+    "  origin_cluster_id (Phase-4 independence cluster): {origin_cluster_id}\n"
+    "  domain_hint: {domain_hint}\n\n"
+    "Return STRICT JSON only, no prose, no code fence:\n"
+    '{{"reliability_score": <0..1: how reliable/authoritative this source is FOR THIS QUESTION, '
+    "reasoning from authority_score / authority_confidence / source_class / corroboration_count / "
+    "signal_scores / junk_class / predatory_oa>, "
+    '"relevance_score": <0..1: how on-topic this source is for the question>, '
+    '"rationale": "<one sentence citing the signals you relied on>", '
+    '"signals_cited": [<deterministic signal names you relied on, e.g. authority_score, corroboration_count>], '
+    '"query_need": "<a follow-up query if this source is thin, else empty>"}}'
+)
+
+# The deterministic signal fields the prompt MUST surface (plan §9.1 — guards against a future edit
+# dropping them again, which would have the judge score credibility blind to its evidence).
+REQUIRED_SIGNAL_FIELDS = (
+    "authority_score", "authority_confidence", "source_class", "corroboration_count",
+    "signal_scores", "junk_class", "predatory_oa", "origin_cluster_id",
+)
+
+
+def build_credibility_prompt(research_question: str, payload: dict[str, Any]) -> str:
+    """Pure: render the per-source judging prompt from the FULL P2 deterministic-signal payload."""
+    payload = payload or {}
+    return _PROMPT.format(
+        question=research_question,
+        title=payload.get("title", ""),
+        url=payload.get("url", ""),
+        snippet=payload.get("snippet", ""),
+        authority_score=payload.get("authority_score", ""),
+        authority_confidence=payload.get("authority_confidence", ""),
+        source_class=payload.get("source_class", ""),
+        corroboration_count=payload.get("corroboration_count", ""),
+        signal_scores=payload.get("signal_scores", {}),
+        junk_class=payload.get("junk_class", ""),
+        predatory_oa=payload.get("predatory_oa", ""),
+        origin_cluster_id=payload.get("origin_cluster_id", ""),
+        domain_hint=payload.get("domain_hint", ""),
+    )
+
+
+def parse_credibility_response(text: str) -> dict[str, Any]:
+    """Parse the FIRST JSON object in the LLM text (Codex #012b P2-1: not the greedy first-{ to last-}).
+
+    Tolerates a leading code fence / prose; trailing prose or extra objects are ignored. Non-dict / no
+    valid first object => {} (=> P2 bounded per-row judge_error)."""
+    if not text or not isinstance(text, str):
+        return {}
+    stripped = text.strip()
+    if stripped.startswith("```"):
+        stripped = re.sub(r"^```[a-zA-Z0-9_]*\n?", "", stripped)
+        stripped = re.sub(r"\n?```\s*$", "", stripped).strip()
+    start = stripped.find("{")
+    if start == -1:
+        return {}
+    try:
+        obj, _ = json.JSONDecoder().raw_decode(stripped[start:])  # FIRST JSON value, ignores the rest
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
index 00000000..4e2246dd
--- /dev/null
+++ b/tests/polaris_graph/authority/test_credibility_judge_phase12b.py
@@ -0,0 +1,82 @@
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
+def test_prompt_surfaces_ALL_required_deterministic_signals():
+    # Codex #012b P1: the judge must reason from the full P2 signal set, not just title/url/authority.
+    from src.polaris_graph.authority.credibility_judge import REQUIRED_SIGNAL_FIELDS
+    payload = {
+        "title": "Study A", "url": "http://a", "snippet": "snip", "authority_score": 0.8,
+        "authority_confidence": "HIGH", "source_class": "journal", "corroboration_count": 4,
+        "signal_scores": {"scholarly": 0.9}, "junk_class": "none", "predatory_oa": False,
+        "origin_cluster_id": "oc1", "domain_hint": "clinical",
+    }
+    p = build_credibility_prompt("does X work?", payload)
+    assert "does X work?" in p and "Study A" in p and "http://a" in p
+    for field in REQUIRED_SIGNAL_FIELDS:
+        assert field in p, f"prompt must surface the deterministic signal {field!r} (plan §9.1)"
+    assert "corroboration_count" in p and "4" in p and "journal" in p
+
+
+def test_parse_helper_direct_and_trailing_prose():
+    assert parse_credibility_response('{"a": 1}') == {"a": 1}
+    assert parse_credibility_response("") == {}
+    assert parse_credibility_response("nope") == {}
+    # FIRST object only — trailing prose / a second object must not break the valid first one (P2-1)
+    assert parse_credibility_response('{"reliability_score": 0.6} then some chatter {"x": 9}') == {"reliability_score": 0.6}
+    # a brace inside a string value must not prematurely close the object
+    assert parse_credibility_response('{"rationale": "uses a { brace", "reliability_score": 0.5}') == {
+        "rationale": "uses a { brace", "reliability_score": 0.5}
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
