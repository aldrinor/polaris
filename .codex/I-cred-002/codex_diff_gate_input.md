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
## PHASE: P2 credibility-skill (#1151) — DIFF gate iter 1. The BRIEF was Codex-APPROVED iter 2 (.codex/I-cred-002/codex_brief_verdict_iter2.txt — 0 P0/P1, accept_remaining). This diff implements that approved contract verbatim: ONE generic adaptive credibility skill (reliability x relevance); domain is a HINT field only (no rubric branch / no domain-keyed table); judge is dependency-INJECTED (judge=None -> priors-only, NO network/client); anti-fabrication cap (LOW/thin: reliability <= clamp01(authority_score)+PG_CREDIBILITY_MAX_UPLIFT default 0.15; the judge MAY down-rate below the prior — prior is not a floor); NaN/inf/non-dict/missing-reliability -> per-row judge_error fallback (isolated); relevance unknown = 1.0 (multiplicative-neutral); credibility_weight = fixed product; signals_cited intersected with present signals; PURE, no row mutation, no faithfulness-file import, default-OFF (PG_SWEEP_CREDIBILITY_SKILL). Advisory only — strict_verify stays the binding gate. SMOKE: 28 passed (all 11 ACs).
```diff
diff --git a/src/polaris_graph/authority/credibility_skill.py b/src/polaris_graph/authority/credibility_skill.py
new file mode 100644
index 00000000..4ac93201
--- /dev/null
+++ b/src/polaris_graph/authority/credibility_skill.py
@@ -0,0 +1,250 @@
+"""I-cred-002 (Phase 2, L1 / §9.1) — adaptive LLM credibility skill (reliability × relevance).
+
+ONE generic, domain-agnostic credibility skill. Per research question it scores EACH candidate
+source on RELIABILITY × RELEVANCE with a written, inspectable rationale, consuming POLARIS's
+already-computed deterministic authority signals (``authority_score`` / ``source_class`` /
+``corroboration_count`` / ``authority_confidence`` / ``signal_scores`` / ``junk_class`` /
+``predatory_oa``) as its PRIORS. There are NO fixed domain rubrics: the detected ``domain`` is a
+single HINT field the judge reasons over, never a branch that swaps rubrics — so this scales to any
+field (operator directive 2026-06-08, plan §9.1).
+
+FAITHFULNESS POSTURE (binding):
+  * ADVISORY ONLY. This never becomes a faithfulness gate — ``strict_verify``'s six per-sentence
+    checks (``generator/provenance_generator.py``) remain the ONLY binding gate. A credibility
+    weight/rationale is a side-output to disclose, never a reason to keep or drop a sentence.
+  * DEFAULT-OFF byte-identical: ``PG_SWEEP_CREDIBILITY_SKILL`` (no production caller is added here).
+  * The LLM call is DEPENDENCY-INJECTED (``judge``); with no judge → no network, no client, no spend
+    (mirrors ``retrieval/semantic_conflict_detector``). The production judge is wired by the caller,
+    never constructed in this pure library.
+  * NO row mutation, NO faithfulness-file import. Pure functions, snake_case, explicit imports.
+  * LAW VI: every threshold is an env-overridable named constant (no magic numbers, no hardcoded
+    model/endpoint).
+
+ANTI-FABRICATION (the LOW/thin guardrail): for a LOW-confidence or thin-signal source the judge's
+reliability is capped at ``clamp01(authority_score) + PG_CREDIBILITY_MAX_UPLIFT`` — the model cannot
+invent authority that the deterministic signals do not support. The judge MAY freely DOWN-rate any
+source below its prior (a high-authority but irrelevant/weak source can score low); the prior is NOT
+a lower bound. The deterministic priors-only judgment is the fallback ONLY on a judge error / no
+judge, never a universal floor.
+"""
+from __future__ import annotations
+
+import math
+import os
+from dataclasses import dataclass, field
+from typing import Any, Callable, Optional
+
+# ── flag (default OFF — matches supersession.py / claim_graph.py) ─────────────
+_FLAG = "PG_SWEEP_CREDIBILITY_SKILL"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+# ── env knobs (LAW VI: named, env-overridable, no magic numbers) ──────────────
+_ENV_MAX_UPLIFT = "PG_CREDIBILITY_MAX_UPLIFT"
+_ENV_SNIPPET_CHARS = "PG_CREDIBILITY_SNIPPET_CHARS"
+_DEFAULT_MAX_UPLIFT = 0.15
+_DEFAULT_SNIPPET_CHARS = 1200
+
+# The deterministic prior-signal names the judge may cite (anti-hallucination: a
+# ``signals_cited`` entry that is not one of these AND present on the row is dropped).
+_PRIOR_SIGNAL_KEYS = (
+    "authority_score",
+    "source_class",
+    "corroboration_count",
+    "authority_confidence",
+    "signal_scores",
+    "junk_class",
+    "predatory_oa",
+)
+
+
+def credibility_skill_enabled() -> bool:
+    """True unless ``PG_SWEEP_CREDIBILITY_SKILL`` is unset/falsey (default OFF => byte-identical).
+
+    Caller kill-switch: no production caller invokes this library while OFF, so the rendered report
+    + manifest are unchanged. The pure functions below do NOT read the flag — they are total +
+    offline-testable; the caller gates invocation.
+    """
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _float_env(name: str, default: float) -> float:
+    try:
+        return float(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _int_env(name: str, default: int) -> int:
+    try:
+        return int(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _clamp01(value: Any) -> float | None:
+    """Clamp a numeric to [0, 1]. Returns ``None`` for non-numeric / NaN / inf (the caller treats
+    that as a judge error — never a NaN weight, never a crash)."""
+    try:
+        x = float(value)
+    except (TypeError, ValueError):
+        return None
+    if math.isnan(x) or math.isinf(x):
+        return None
+    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
+
+
+@dataclass
+class CredibilityJudgment:
+    """One source's advisory credibility judgment (a side-output, never a verdict input).
+
+    ``reliability_score`` is AFTER the anti-fabrication cap; ``relevance_score`` is the judged
+    directness to the question (unknown => 1.0, multiplicative-neutral); ``credibility_weight`` is
+    the FIXED product ``clamp01(reliability * relevance)``. ``signals_cited`` is the subset of the
+    deterministic prior signals the judge reasoned from. ``judge_error`` is True iff the injected
+    judge raised / returned malformed output for THIS source (isolated; priors-only fallback used).
+    """
+
+    evidence_id: str
+    reliability_score: float
+    relevance_score: float
+    credibility_weight: float
+    rationale: str
+    signals_cited: list[str] = field(default_factory=list)
+    query_need: str = ""
+    judge_error: bool = False
+
+
+def _present_signals(row: dict[str, Any]) -> list[str]:
+    """The deterministic prior signals actually present (non-empty) on this row."""
+    return [k for k in _PRIOR_SIGNAL_KEYS if row.get(k) not in (None, "", {}, [])]
+
+
+def _row_snippet(row: dict[str, Any], max_chars: int) -> str:
+    text = str(row.get("direct_quote") or row.get("statement") or row.get("text") or "")
+    return text[:max_chars]
+
+
+def _build_judge_payload(
+    research_question: str, row: dict[str, Any], domain: str | None
+) -> dict[str, Any]:
+    """Pure: assemble the judge payload for ONE source. Does NOT mutate ``row``.
+
+    Carries source identity + bounded descriptors (title / url / snippet — so RELEVANCE is actually
+    judgeable) + the deterministic authority priors + the ``domain_hint`` (a single string field,
+    NOT a branch / rubric table). The judge sees ONLY this payload.
+    """
+    snippet_chars = _int_env(_ENV_SNIPPET_CHARS, _DEFAULT_SNIPPET_CHARS)
+    return {
+        "research_question": research_question,
+        "evidence_id": str(row.get("evidence_id", "")),
+        "title": str(row.get("title", "") or ""),
+        "url": str(row.get("source_url", "") or row.get("url", "") or ""),
+        "snippet": _row_snippet(row, snippet_chars),
+        "authority_score": row.get("authority_score"),
+        "source_class": row.get("source_class"),
+        "corroboration_count": row.get("corroboration_count"),
+        "authority_confidence": row.get("authority_confidence"),
+        "signal_scores": dict(row.get("signal_scores") or {}),
+        "junk_class": row.get("junk_class", ""),
+        "predatory_oa": row.get("predatory_oa", False),
+        "domain_hint": domain or "",
+    }
+
+
+def _is_low_or_thin(row: dict[str, Any]) -> bool:
+    """A source is LOW/thin (subject to the anti-fabrication cap) when its authority_confidence is
+    LOW, or it has no authority_score, or it has no signal_scores."""
+    if str(row.get("authority_confidence") or "").strip().upper() == "LOW":
+        return True
+    if row.get("authority_score") is None:
+        return True
+    if not (row.get("signal_scores") or {}):
+        return True
+    return False
+
+
+def _priors_only_judgment(row: dict[str, Any]) -> CredibilityJudgment:
+    """The deterministic fallback (no judge / judge error): reliability from the prior, relevance
+    neutral (1.0). Never fabricates relevance it cannot judge."""
+    auth = _clamp01(row.get("authority_score"))
+    reliability = auth if auth is not None else 0.0
+    return CredibilityJudgment(
+        evidence_id=str(row.get("evidence_id", "")),
+        reliability_score=reliability,
+        relevance_score=1.0,
+        credibility_weight=reliability,  # == clamp01(reliability * 1.0)
+        rationale="no judge wired — deterministic priors only",
+        signals_cited=_present_signals(row),
+        query_need="",
+        judge_error=False,
+    )
+
+
+def _apply_judge(
+    research_question: str,
+    row: dict[str, Any],
+    domain: str | None,
+    judge: Callable[[str, dict], dict],
+) -> CredibilityJudgment:
+    """Run the injected judge for ONE source; fall back to priors on ANY error / malformed output
+    (isolated to this row — recall-first, fail-loud-but-bounded)."""
+    payload = _build_judge_payload(research_question, row, domain)
+    try:
+        raw = judge(research_question, payload)
+    except Exception:
+        fallback = _priors_only_judgment(row)
+        fallback.judge_error = True
+        return fallback
+    if not isinstance(raw, dict):
+        fallback = _priors_only_judgment(row)
+        fallback.judge_error = True
+        return fallback
+
+    reliability = _clamp01(raw.get("reliability_score"))
+    if reliability is None:  # missing / NaN / inf reliability => judge error for this row
+        fallback = _priors_only_judgment(row)
+        fallback.judge_error = True
+        return fallback
+    relevance = _clamp01(raw.get("relevance_score"))
+    if relevance is None:  # unknown / malformed relevance => multiplicative-neutral
+        relevance = 1.0
+
+    # Anti-fabrication cap: a LOW/thin source's reliability cannot exceed prior + max_uplift.
+    if _is_low_or_thin(row):
+        auth = _clamp01(row.get("authority_score")) or 0.0
+        cap = _clamp01(auth + _float_env(_ENV_MAX_UPLIFT, _DEFAULT_MAX_UPLIFT))
+        if cap is not None:
+            reliability = min(reliability, cap)
+
+    present = set(_present_signals(row))
+    cited = [s for s in (raw.get("signals_cited") or []) if s in present]
+    weight = _clamp01(reliability * relevance)
+    return CredibilityJudgment(
+        evidence_id=str(row.get("evidence_id", "")),
+        reliability_score=reliability,
+        relevance_score=relevance,
+        credibility_weight=weight if weight is not None else 0.0,
+        rationale=str(raw.get("rationale", "")),
+        signals_cited=cited,
+        query_need=str(raw.get("query_need", "")),
+        judge_error=False,
+    )
+
+
+def score_source_credibility(
+    research_question: str,
+    rows: list[dict[str, Any]],
+    *,
+    domain: str | None = None,
+    judge: Optional[Callable[[str, dict], dict]] = None,
+) -> list[CredibilityJudgment]:
+    """Score each source on reliability × relevance — ADVISORY ONLY, pure, no row mutation.
+
+    With ``judge=None`` returns one priors-only judgment per row (no network, total + offline). With
+    an injected ``judge(research_question, payload) -> dict`` runs it PER SOURCE so a judge error is
+    isolated to one row. ``domain`` is forwarded only as the ``domain_hint`` payload field — there is
+    no domain-keyed branch or rubric table (operator: no fixed rubrics).
+    """
+    if judge is None:
+        return [_priors_only_judgment(row) for row in (rows or [])]
+    return [_apply_judge(research_question, row, domain, judge) for row in (rows or [])]
diff --git a/tests/polaris_graph/authority/test_credibility_skill_phase2.py b/tests/polaris_graph/authority/test_credibility_skill_phase2.py
new file mode 100644
index 00000000..540b034f
--- /dev/null
+++ b/tests/polaris_graph/authority/test_credibility_skill_phase2.py
@@ -0,0 +1,195 @@
+"""I-cred-002 (Phase 2) — adaptive credibility skill. Offline, deterministic fake judges, no network,
+no live data, no LLM client. Each test maps to a brief acceptance criterion (AC-1..AC-11)."""
+from __future__ import annotations
+
+import copy
+
+import pytest
+
+from src.polaris_graph.authority.credibility_skill import (
+    CredibilityJudgment,
+    _build_judge_payload,
+    credibility_skill_enabled,
+    score_source_credibility,
+)
+
+
+def _row(eid, **kw):
+    row = {"evidence_id": eid}
+    row.update(kw)
+    return row
+
+
+# ── AC-1: flag default-OFF ────────────────────────────────────────────────────
+def test_flag_default_off(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_SKILL", raising=False)
+    assert credibility_skill_enabled() is False
+
+
+@pytest.mark.parametrize("off", ["", "0", "false", "off", "no", "  ", "FALSE", "Off"])
+def test_flag_off_values(monkeypatch, off):
+    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_SKILL", off)
+    assert credibility_skill_enabled() is False
+
+
+@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
+def test_flag_on_values(monkeypatch, on):
+    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_SKILL", on)
+    assert credibility_skill_enabled() is True
+
+
+# ── AC-2: judge=None => priors-only (total, offline) ──────────────────────────
+def test_judge_none_priors_only():
+    rows = [
+        _row("e1", authority_score=0.7, signal_scores={"signal_a_scholarly": 0.8}),
+        _row("e2"),  # no authority at all
+    ]
+    out = score_source_credibility("q", rows)
+    assert len(out) == 2
+    assert out[0].reliability_score == 0.7 and out[0].relevance_score == 1.0
+    assert out[0].credibility_weight == 0.7 and out[0].judge_error is False
+    assert out[1].reliability_score == 0.0  # no authority -> 0.0, never crashes
+
+
+# ── AC-3: injected judge flows through; weight is the fixed product ───────────
+def test_injected_judge_flows_through():
+    def judge(q, payload):
+        return {"reliability_score": 0.8, "relevance_score": 0.5, "rationale": "r", "query_need": "n"}
+
+    rows = [_row("e1", authority_score=0.6, authority_confidence="HIGH", signal_scores={"x": 1})]
+    j = score_source_credibility("q", rows, judge=judge)[0]
+    assert j.reliability_score == 0.8 and j.relevance_score == 0.5
+    assert abs(j.credibility_weight - 0.4) < 1e-9
+    assert j.rationale == "r" and j.query_need == "n" and j.judge_error is False
+
+
+# ── AC-4: anti-fabrication cap (exact) + judge may down-rate ──────────────────
+def test_anti_fabrication_cap_low_thin():
+    def overclaim(q, p):
+        return {"reliability_score": 0.99, "relevance_score": 1.0}
+
+    rows = [_row("low", authority_score=0.30, authority_confidence="LOW", signal_scores={"x": 1})]
+    out = score_source_credibility("q", rows, judge=overclaim)
+    assert abs(out[0].reliability_score - 0.45) < 1e-9  # 0.30 + 0.15 default uplift
+
+
+def test_judge_may_downrate_high_authority():
+    def downrate(q, p):
+        return {"reliability_score": 0.10, "relevance_score": 1.0}
+
+    rows = [_row("hi", authority_score=0.95, authority_confidence="HIGH", signal_scores={"x": 1})]
+    out = score_source_credibility("q", rows, judge=downrate)
+    assert out[0].reliability_score == 0.10  # the prior is NOT a lower bound
+
+
+# ── AC-5: signals_cited subset of present ────────────────────────────────────
+def test_signals_cited_subset_of_present():
+    def judge(q, p):
+        return {"reliability_score": 0.5, "relevance_score": 1.0,
+                "signals_cited": ["authority_score", "junk_class", "not_a_signal", "predatory_oa"]}
+
+    rows = [_row("e1", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1})]
+    out = score_source_credibility("q", rows, judge=judge)
+    assert out[0].signals_cited == ["authority_score"]  # only the present, valid one survives
+
+
+# ── AC-6: malformed judge output ─────────────────────────────────────────────
+def test_out_of_range_clamped():
+    def judge(q, p):
+        return {"reliability_score": 1.7, "relevance_score": -0.2}
+
+    rows = [_row("e1", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1})]
+    out = score_source_credibility("q", rows, judge=judge)
+    assert out[0].reliability_score == 1.0 and out[0].relevance_score == 0.0
+
+
+@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
+def test_nan_inf_reliability_is_judge_error(bad):
+    def judge(q, p):
+        return {"reliability_score": bad, "relevance_score": 1.0}
+
+    rows = [_row("e1", authority_score=0.4, authority_confidence="HIGH", signal_scores={"x": 1})]
+    out = score_source_credibility("q", rows, judge=judge)
+    assert out[0].judge_error is True and out[0].reliability_score == 0.4  # priors fallback
+
+
+def test_malformed_non_dict_is_judge_error():
+    def judge(q, p):
+        return "not a dict"
+
+    rows = [_row("e1", authority_score=0.4, authority_confidence="HIGH", signal_scores={"x": 1})]
+    out = score_source_credibility("q", rows, judge=judge)
+    assert out[0].judge_error is True and out[0].reliability_score == 0.4
+
+
+# ── AC-7: judge error isolated per row ───────────────────────────────────────
+def test_judge_error_isolated_per_row():
+    def judge(q, p):
+        if p["evidence_id"] == "boom":
+            raise RuntimeError("nope")
+        return {"reliability_score": 0.6, "relevance_score": 1.0}
+
+    rows = [
+        _row("ok", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1}),
+        _row("boom", authority_score=0.2),
+    ]
+    out = score_source_credibility("q", rows, judge=judge)
+    assert out[0].judge_error is False and out[0].reliability_score == 0.6
+    assert out[1].judge_error is True and out[1].reliability_score == 0.2
+
+
+# ── AC-8: domain is a HINT, not a branch ─────────────────────────────────────
+def test_domain_is_hint_not_branch():
+    captured = []
+
+    def judge(q, p):
+        captured.append(p["domain_hint"])
+        return {"reliability_score": 0.5, "relevance_score": 0.5}
+
+    rows = [_row("e1", authority_score=0.6, authority_confidence="HIGH", signal_scores={"x": 1})]
+    a = score_source_credibility("q", rows, domain="clinical", judge=judge)
+    b = score_source_credibility("q", rows, domain="policy", judge=judge)
+    assert a[0].credibility_weight == b[0].credibility_weight  # identical control flow + result
+    assert a[0].reliability_score == b[0].reliability_score
+    assert captured == ["clinical", "policy"]  # only the hint string differs
+
+
+# ── AC-9: env knob scoped to the cap, product fixed ──────────────────────────
+def test_max_uplift_env_knob(monkeypatch):
+    def overclaim(q, p):
+        return {"reliability_score": 0.99, "relevance_score": 1.0}
+
+    monkeypatch.setenv("PG_CREDIBILITY_MAX_UPLIFT", "0.05")
+    low = [_row("low", authority_score=0.30, authority_confidence="LOW", signal_scores={"x": 1})]
+    assert abs(score_source_credibility("q", low, judge=overclaim)[0].reliability_score - 0.35) < 1e-9
+    hi = [_row("hi", authority_score=0.60, authority_confidence="HIGH", signal_scores={"x": 1})]
+    assert score_source_credibility("q", hi, judge=overclaim)[0].reliability_score == 0.99  # unaffected
+
+
+# ── AC-10: purity — no row mutation ──────────────────────────────────────────
+def test_no_row_mutation():
+    def judge(q, p):
+        p["mutated"] = True  # mutate the PAYLOAD, not the row
+        return {"reliability_score": 0.5, "relevance_score": 1.0}
+
+    row = _row("e1", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1},
+               direct_quote="hello")
+    before = copy.deepcopy(row)
+    score_source_credibility("q", [row], judge=judge)
+    assert row == before
+
+
+# ── AC-11: judge payload shape ───────────────────────────────────────────────
+def test_judge_payload_shape(monkeypatch):
+    monkeypatch.setenv("PG_CREDIBILITY_SNIPPET_CHARS", "10")
+    row = _row("e1", authority_score=0.5, source_class="PRIMARY_SCHOLARLY", corroboration_count=3,
+               authority_confidence="HIGH", signal_scores={"signal_a_scholarly": 0.9}, junk_class="",
+               predatory_oa=False, title="T", source_url="https://x", direct_quote="0123456789ABCDEF")
+    payload = _build_judge_payload("the question", row, "clinical")
+    for key in ("research_question", "evidence_id", "title", "url", "snippet", "authority_score",
+                "source_class", "corroboration_count", "authority_confidence", "signal_scores",
+                "junk_class", "predatory_oa", "domain_hint"):
+        assert key in payload
+    assert len(payload["snippet"]) == 10 and payload["domain_hint"] == "clinical"
+    assert "mutated" not in row
+    assert _build_judge_payload("q", row, None)["domain_hint"] == ""
```
