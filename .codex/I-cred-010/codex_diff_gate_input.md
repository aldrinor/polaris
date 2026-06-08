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
## PHASE: P10 dissent-recall builder (#1159) — DIFF gate iter 1 (brief in parallel review). PURE builder only (saturation-loop wiring deferred to I-cred-010b). build_dissent_queries(contradiction_edges, claims, *, max_queries, query_fn): deterministic search-friendly dissent templates ('<subj pred> no effect/contrary evidence/criticism/disputed/limitations') that seek the MINORITY side; deduped, capped at max_queries (env PG_DISSENT_QUERIES_MAX); [] for no edges; optional injected query_fn (LLM seam, mirrors Phase-2) with fail-soft to templates on error. build_source_stratification_plan: ADVISORY per-backend quota hint (never a hard override that could starve consensus); empty for contested_count<=0. ADDITIVE/advisory ONLY — makes NO retrieval call; everything fetched with these queries still passes tier/authority/relevance/strict_verify gates UNCHANGED. default-OFF PG_SWEEP_DISSENT_RECALL; pure, no input mutation. SMOKE: 13 passed (incl. no-network-import assertion + fail-soft + cap).
```diff
diff --git a/src/polaris_graph/retrieval/dissent_recall_builder.py b/src/polaris_graph/retrieval/dissent_recall_builder.py
new file mode 100644
index 00000000..5106d72f
--- /dev/null
+++ b/src/polaris_graph/retrieval/dissent_recall_builder.py
@@ -0,0 +1,133 @@
+"""I-cred-010 (Phase 10, retrieval) — dissent-recall query + stratification builder (pure module).
+
+For a CONTESTED claim (one carrying a Phase-5 ``ContradictionEdge``), BUILD (a) dissent-SEEKING query
+strings that go looking for the MINORITY / contrary side, and (b) an advisory source-type stratification
+plan — so a contested claim ends with real evidence on EACH side, not just the majority view.
+
+POSTURE (binding):
+  * ADDITIVE / ADVISORY ONLY. This module BUILDS queries + a plan; it makes NO retrieval call. Everything
+    a flagged caller eventually fetches with these queries still passes the EXISTING gates — tier
+    classification, ``authority_model.score_source_authority``, ``evidence_selector`` (tier quotas +
+    ``PG_RELEVANCE_FLOOR``), and ``strict_verify`` (the only binding faithfulness gate). Dissent-recall
+    ADDS breadth for the minority side; it NEVER lowers adequacy thresholds, NEVER bypasses authority /
+    relevance scoring, NEVER changes ``strict_verify``.
+  * DEFAULT-OFF byte-identical: ``PG_SWEEP_DISSENT_RECALL`` (no production caller; the saturation-loop
+    wiring is the follow-up I-cred-010b). Empty inputs → empty outputs.
+  * PURE: no network in the builder, no input mutation, deterministic; LAW VI; snake_case. An optional
+    injected ``query_fn`` lets a flagged caller plug an LLM dissent-query generator later (mirrors the
+    Phase-2 injected-judge seam); the default builds NO network call.
+"""
+from __future__ import annotations
+
+import os
+from typing import Any, Callable, Optional
+
+_FLAG = "PG_SWEEP_DISSENT_RECALL"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+_ENV_MAX_QUERIES = "PG_DISSENT_QUERIES_MAX"
+_ENV_PER_BACKEND = "PG_DISSENT_PER_BACKEND"
+_DEFAULT_MAX_QUERIES = 8
+_DEFAULT_PER_BACKEND = 2
+
+
+def dissent_recall_enabled() -> bool:
+    """True unless ``PG_SWEEP_DISSENT_RECALL`` is unset/falsey (default OFF => byte-identical)."""
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _int_env(name: str, default: int) -> int:
+    try:
+        return int(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _default_dissent_queries(subject: str, predicate: str, text: str) -> list[str]:
+    """Deterministic, search-friendly dissent templates that seek the CONTRARY side of a claim."""
+    base = " ".join(part for part in (subject.strip(), predicate.strip()) if part.strip()).strip()
+    if not base:
+        base = (text or "").strip()[:80]
+    if not base:
+        return []
+    return [
+        f"{base} no effect",
+        f"{base} contrary evidence",
+        f"{base} criticism",
+        f"{base} disputed",
+        f"{base} limitations",
+    ]
+
+
+def build_dissent_queries(
+    contradiction_edges: list,
+    claims: list,
+    *,
+    max_queries: int | None = None,
+    query_fn: Optional[Callable[[str, str, str], list]] = None,
+) -> list[str]:
+    """Pure: emit deduped dissent-seeking query strings for the contested claims, capped at max_queries.
+
+    Returns ``[]`` for no edges (byte-identity when OFF). With an injected ``query_fn`` (subject, predicate,
+    text) -> list[str], a flagged caller can plug an LLM dissent generator; a ``query_fn`` that raises
+    falls back to the deterministic templates for that edge (fail-soft, no crash). NO retrieval call.
+    """
+    if max_queries is None:
+        max_queries = _int_env(_ENV_MAX_QUERIES, _DEFAULT_MAX_QUERIES)
+
+    text_by_sp: dict[tuple, str] = {}
+    for claim in (claims or []):
+        key = (
+            str(getattr(claim, "subject", "") or "").strip().lower(),
+            str(getattr(claim, "predicate", "") or "").strip().lower(),
+        )
+        if key not in text_by_sp:
+            text_by_sp[key] = str(getattr(claim, "text", "") or "").strip()
+
+    out: list[str] = []
+    seen: set[str] = set()
+    for edge in (contradiction_edges or []):
+        subject = str(getattr(edge, "subject", "") or "").strip()
+        predicate = str(getattr(edge, "predicate", "") or "").strip()
+        text = text_by_sp.get((subject.lower(), predicate.lower()), "")
+        if query_fn is not None:
+            try:
+                queries = list(query_fn(subject, predicate, text) or [])
+            except Exception:
+                queries = _default_dissent_queries(subject, predicate, text)
+        else:
+            queries = _default_dissent_queries(subject, predicate, text)
+        for query in queries:
+            normalized = str(query or "").strip()
+            key = normalized.lower()
+            if normalized and key not in seen:
+                seen.add(key)
+                out.append(normalized)
+                if len(out) >= max_queries:
+                    return out
+    return out
+
+
+def build_source_stratification_plan(
+    contested_count: int,
+    available_backends: list,
+    *,
+    per_type_quota: dict | None = None,
+) -> dict:
+    """Pure: an ADVISORY per-source-type quota hint so dissent retrieval is stratified across web /
+    academic / open-access / regulatory — never a hard override that could STARVE the consensus side.
+
+    Empty plan for ``contested_count <= 0`` or no backends (byte-identity). When ``per_type_quota`` is
+    given it is used (filtered to positive quotas on listed backends); otherwise a small even per-backend
+    floor is emitted so each available source type gets some dissent budget.
+    """
+    if contested_count <= 0:
+        return {}
+    backends = [str(b).strip() for b in (available_backends or []) if str(b).strip()]
+    if not backends:
+        return {}
+    if per_type_quota:
+        plan = {b: int(per_type_quota.get(b, 0)) for b in backends}
+        return {b: q for b, q in plan.items() if q > 0}
+    per_backend = max(1, _int_env(_ENV_PER_BACKEND, _DEFAULT_PER_BACKEND))
+    return {b: per_backend for b in backends}
diff --git a/tests/polaris_graph/retrieval/test_dissent_recall_builder_phase10.py b/tests/polaris_graph/retrieval/test_dissent_recall_builder_phase10.py
new file mode 100644
index 00000000..4b363091
--- /dev/null
+++ b/tests/polaris_graph/retrieval/test_dissent_recall_builder_phase10.py
@@ -0,0 +1,94 @@
+"""I-cred-010 (Phase 10) — dissent-recall builder. Offline, deterministic, no network."""
+from __future__ import annotations
+
+import pytest
+
+from src.polaris_graph.retrieval.dissent_recall_builder import (
+    build_dissent_queries,
+    build_source_stratification_plan,
+    dissent_recall_enabled,
+)
+
+
+def _edge(subject, predicate):
+    return type("E", (), {"subject": subject, "predicate": predicate,
+                          "claim_cluster_ids": ("a", "b"), "severity": "review"})()
+
+
+def _claim(subject, predicate, text=""):
+    return type("C", (), {"subject": subject, "predicate": predicate, "text": text})()
+
+
+# ── AC-1 ──────────────────────────────────────────────────────────────────────
+def test_flag_default_off(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_DISSENT_RECALL", raising=False)
+    assert dissent_recall_enabled() is False
+
+
+@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
+def test_flag_on(monkeypatch, on):
+    monkeypatch.setenv("PG_SWEEP_DISSENT_RECALL", on)
+    assert dissent_recall_enabled() is True
+
+
+# ── AC-2: no edges -> empty (byte-identity precondition) ─────────────────────
+def test_no_edges_empty():
+    assert build_dissent_queries([], []) == []
+    assert build_source_stratification_plan(0, ["serper", "s2"]) == {}
+
+
+# ── AC-3: queries target the CONTRARY side, deterministic + deduped ──────────
+def test_dissent_queries_target_contrary_side():
+    q = build_dissent_queries([_edge("vaccine", "reduces hospitalization")], [])
+    assert q
+    joined = " ".join(q).lower()
+    assert any(k in joined for k in ("no effect", "contrary", "criticism", "disputed", "limitation"))
+    assert q == build_dissent_queries([_edge("vaccine", "reduces hospitalization")], [])  # deterministic
+    assert len(q) == len(set(q))  # deduped
+
+
+# ── AC-4: max_queries cap + env knob ─────────────────────────────────────────
+def test_max_queries_cap(monkeypatch):
+    edges = [_edge(f"s{i}", "effect") for i in range(10)]
+    assert len(build_dissent_queries(edges, [], max_queries=3)) == 3
+    monkeypatch.setenv("PG_DISSENT_QUERIES_MAX", "2")
+    assert len(build_dissent_queries(edges, [])) == 2
+
+
+# ── AC-5: injected query_fn used; fail-soft to templates on error ────────────
+def test_injected_query_fn_used_and_fail_soft():
+    q = build_dissent_queries([_edge("vax", "x")], [], query_fn=lambda s, p, t: [f"custom {s}"])
+    assert q == ["custom vax"]
+
+    def boom(subject, predicate, text):
+        raise RuntimeError("nope")
+
+    fallback = build_dissent_queries([_edge("vax", "x")], [], query_fn=boom)
+    assert fallback and any("no effect" in x for x in fallback)
+
+
+# ── AC-6: stratification plan ────────────────────────────────────────────────
+def test_stratification_plan():
+    plan = build_source_stratification_plan(2, ["serper", "s2", "openalex"])
+    assert set(plan.keys()) == {"serper", "s2", "openalex"}
+    assert all(v >= 1 for v in plan.values())
+    override = build_source_stratification_plan(2, ["serper", "s2"],
+                                                per_type_quota={"serper": 5, "s2": 0, "x": 9})
+    assert override == {"serper": 5}  # s2=0 dropped; 'x' not a listed backend
+
+
+# ── AC-7 / AC-8: purity — inputs untouched; builder makes NO retrieval call ──
+def test_purity_no_mutation():
+    edges = [_edge("a", "b")]
+    claims = [_claim("a", "b", "text")]
+    build_dissent_queries(edges, claims)
+    assert edges[0].subject == "a" and claims[0].text == "text"
+
+
+def test_builder_imports_no_network_client():
+    """AC-8: the builder BUILDS queries only — it imports no http client, so it cannot fetch/score."""
+    import src.polaris_graph.retrieval.dissent_recall_builder as mod
+    source = mod.__file__
+    text = open(source, encoding="utf-8").read()
+    for forbidden in ("import httpx", "import requests", "openrouter", "run_live_retrieval"):
+        assert forbidden not in text, f"dissent builder must not {forbidden!r} — execution is the caller's"
```
