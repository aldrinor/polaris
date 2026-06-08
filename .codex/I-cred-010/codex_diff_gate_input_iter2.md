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
## PHASE: P10 dissent-recall builder (#1159) — DIFF gate ITER 2. Iter-1 brief P1 + diff P1/P2 all addressed: (BRIEF P1, core) build_dissent_queries now takes weight_by_cluster (Phase-6 weight_mass; dict OR ClaimWeightMass list) and TARGETS THE MINORITY = the edge's lowest-weight cluster, seeking evidence FOR its assertion (claim text) — NOT generic contrary queries that could reinforce the majority (regressions test_targets_minority_side_assertion + test_minority_flips_when_weights_flip). (DIFF P1) max_queries<=0 / PG_DISSENT_QUERIES_MAX=0 now returns [] before any append. (DIFF P2) assertion truncation is PG_DISSENT_ASSERTION_CHARS (default 120), Any import used. Additive/advisory only, NO retrieval call, default-OFF PG_SWEEP_DISSENT_RECALL, pure. SMOKE: 15 passed.
```diff
diff --git a/src/polaris_graph/retrieval/dissent_recall_builder.py b/src/polaris_graph/retrieval/dissent_recall_builder.py
new file mode 100644
index 00000000..7411d360
--- /dev/null
+++ b/src/polaris_graph/retrieval/dissent_recall_builder.py
@@ -0,0 +1,177 @@
+"""I-cred-010 (Phase 10, retrieval) — dissent-recall query + stratification builder (pure module).
+
+For a CONTESTED claim (one carrying a Phase-5 ``ContradictionEdge``), BUILD (a) query strings that seek
+MORE EVIDENCE FOR THE MINORITY (under-evidenced) side, and (b) an advisory source-type stratification
+plan — so a contested claim ends with real evidence on EACH side, not just the majority view.
+
+WHY a side signal is required (Codex #1159 iter-1): a ``ContradictionEdge`` carries only subject /
+predicate / SORTED claim_cluster_ids — it does NOT say which side is the minority. So the builder takes
+the Phase-6 ``weight_mass`` per cluster and targets the LOWEST-weight cluster's assertion (the
+under-evidenced minority). Without that signal, generic "contrary" queries could just reinforce the
+majority — exactly the failure this phase exists to prevent.
+
+POSTURE (binding):
+  * ADDITIVE / ADVISORY ONLY. This module BUILDS queries + a plan; it makes NO retrieval call. Everything
+    a flagged caller fetches with these queries still passes the EXISTING gates — tier classification,
+    ``authority_model.score_source_authority``, ``evidence_selector`` (tier quotas + ``PG_RELEVANCE_FLOOR``),
+    and ``strict_verify`` (the only binding faithfulness gate). Dissent-recall ADDS breadth for the
+    minority side; it NEVER lowers adequacy thresholds, NEVER bypasses authority / relevance scoring,
+    NEVER changes ``strict_verify``.
+  * DEFAULT-OFF byte-identical: ``PG_SWEEP_DISSENT_RECALL`` (no production caller; the saturation-loop
+    wiring is the follow-up I-cred-010b). Empty inputs → empty outputs.
+  * PURE: no network in the builder, no input mutation, deterministic; LAW VI; snake_case. An optional
+    injected ``query_fn`` lets a flagged caller plug an LLM minority-query generator later (mirrors the
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
+_ENV_ASSERTION_CHARS = "PG_DISSENT_ASSERTION_CHARS"
+_DEFAULT_MAX_QUERIES = 8
+_DEFAULT_PER_BACKEND = 2
+_DEFAULT_ASSERTION_CHARS = 120
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
+def _coerce_weight_map(weight_by_cluster: Any) -> dict[str, float]:
+    """Accept either a ``{claim_cluster_id: weight_mass}`` dict or a list of Phase-6 ClaimWeightMass
+    objects, and return a normalized ``{cluster_id: float}`` map."""
+    out: dict[str, float] = {}
+    if isinstance(weight_by_cluster, dict):
+        for key, value in weight_by_cluster.items():
+            try:
+                out[str(key)] = float(value)
+            except (TypeError, ValueError):
+                continue
+        return out
+    for item in (weight_by_cluster or []):
+        cid = str(getattr(item, "claim_cluster_id", "") or "")
+        if not cid:
+            continue
+        try:
+            out[cid] = float(getattr(item, "weight_mass", 0.0))
+        except (TypeError, ValueError):
+            out[cid] = 0.0
+    return out
+
+
+def _minority_queries(assertion: str) -> list[str]:
+    """Deterministic, search-friendly queries that seek MORE EVIDENCE FOR the minority assertion."""
+    base = (assertion or "").strip()[:_int_env(_ENV_ASSERTION_CHARS, _DEFAULT_ASSERTION_CHARS)]
+    if not base:
+        return []
+    return [
+        base,                       # the minority assertion itself
+        f"{base} evidence",
+        f"{base} studies",
+        f"{base} supporting research",
+    ]
+
+
+def build_dissent_queries(
+    contradiction_edges: list,
+    claims: list,
+    weight_by_cluster: Any,
+    *,
+    max_queries: int | None = None,
+    query_fn: Optional[Callable[[str, str], list]] = None,
+) -> list[str]:
+    """Pure: emit deduped queries that seek evidence FOR the MINORITY side of each contested claim.
+
+    ``weight_by_cluster``: ``{claim_cluster_id: Phase-6 weight_mass}`` (dict) or a list of ClaimWeightMass.
+    For each edge, the minority is the cluster with the LOWEST weight_mass (ties -> the
+    lexicographically smaller cluster_id; an UNKNOWN weight is treated as 0.0 = under-evidenced); its
+    claim TEXT becomes the assertion to seek evidence for. Returns ``[]`` for no edges (byte-identity).
+    An injected ``query_fn`` (minority_cluster_id, minority_assertion) -> list[str] plugs an LLM
+    generator; a ``query_fn`` that raises falls back to the templates for that edge. NO retrieval call.
+    """
+    if max_queries is None:
+        max_queries = _int_env(_ENV_MAX_QUERIES, _DEFAULT_MAX_QUERIES)
+    if max_queries <= 0:
+        return []  # a zero/negative cap emits NOTHING (spend/recall control — Codex #1159 diff P1)
+
+    text_by_cluster: dict[str, str] = {}
+    sp_by_cluster: dict[str, tuple] = {}
+    for claim in (claims or []):
+        cid = str(getattr(claim, "claim_cluster_id", "") or "")
+        if not cid or cid in text_by_cluster:
+            continue
+        text_by_cluster[cid] = str(getattr(claim, "text", "") or "").strip()
+        sp_by_cluster[cid] = (
+            str(getattr(claim, "subject", "") or "").strip(),
+            str(getattr(claim, "predicate", "") or "").strip(),
+        )
+
+    weight_map = _coerce_weight_map(weight_by_cluster)
+
+    out: list[str] = []
+    seen: set[str] = set()
+    for edge in (contradiction_edges or []):
+        cids = [str(c) for c in (getattr(edge, "claim_cluster_ids", ()) or ())]
+        if len(cids) < 2:
+            continue
+        # Minority = lowest weight_mass; ties + unknown-weight broken deterministically by cluster_id.
+        minority_cid = min(cids, key=lambda c: (weight_map.get(c, 0.0), c))
+        assertion = text_by_cluster.get(minority_cid, "")
+        if not assertion:
+            subject, predicate = sp_by_cluster.get(minority_cid, ("", ""))
+            assertion = " ".join(part for part in (subject, predicate) if part).strip()
+        if query_fn is not None:
+            try:
+                queries = list(query_fn(minority_cid, assertion) or [])
+            except Exception:
+                queries = _minority_queries(assertion)
+        else:
+            queries = _minority_queries(assertion)
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
index 00000000..187ff74a
--- /dev/null
+++ b/tests/polaris_graph/retrieval/test_dissent_recall_builder_phase10.py
@@ -0,0 +1,124 @@
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
+def _edge(cids, subject="vaccine", predicate="hospitalization"):
+    return type("E", (), {"subject": subject, "predicate": predicate,
+                          "claim_cluster_ids": tuple(cids), "severity": "review"})()
+
+
+def _claim(cid, text, subject="vaccine", predicate="hospitalization"):
+    return type("C", (), {"claim_cluster_id": cid, "text": text,
+                          "subject": subject, "predicate": predicate})()
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
+    assert build_dissent_queries([], [], {}) == []
+    assert build_source_stratification_plan(0, ["serper", "s2"]) == {}
+
+
+# ── AC-3 (core): targets the MINORITY (lowest-weight) cluster's assertion ────
+def test_targets_minority_side_assertion():
+    edges = [_edge(["cMaj", "cMin"])]
+    claims = [
+        _claim("cMaj", "vaccine reduced hospitalization substantially"),
+        _claim("cMin", "vaccine showed no effect on hospitalization"),
+    ]
+    weights = {"cMaj": 0.9, "cMin": 0.1}  # cMin is the minority (lowest weight)
+    q = build_dissent_queries(edges, claims, weights)
+    joined = " ".join(q).lower()
+    assert "no effect on hospitalization" in joined     # seeks the MINORITY assertion
+    assert "reduced hospitalization" not in joined       # NOT the majority's
+    assert q == build_dissent_queries(edges, claims, weights)  # deterministic
+    assert len(q) == len(set(q))                              # deduped
+
+
+def test_minority_flips_when_weights_flip():
+    edges = [_edge(["cA", "cB"])]
+    claims = [_claim("cA", "claim A text alpha"), _claim("cB", "claim B text beta")]
+    qa = build_dissent_queries(edges, claims, {"cA": 0.1, "cB": 0.9})  # A is minority
+    assert any("alpha" in x for x in qa) and not any("beta" in x for x in qa)
+    qb = build_dissent_queries(edges, claims, {"cA": 0.9, "cB": 0.1})  # B is minority
+    assert any("beta" in x for x in qb) and not any("alpha" in x for x in qb)
+
+
+# ── AC-4: cap + zero/negative cap emits nothing ──────────────────────────────
+def test_max_queries_cap_and_zero(monkeypatch):
+    edges = [_edge([f"c{i}a", f"c{i}b"]) for i in range(10)]
+    claims = ([_claim(f"c{i}a", f"major {i}") for i in range(10)]
+              + [_claim(f"c{i}b", f"assertion {i}") for i in range(10)])
+    weights = {f"c{i}a": 0.9 for i in range(10)}
+    weights.update({f"c{i}b": 0.1 for i in range(10)})  # every 'b' cluster is the minority
+    assert len(build_dissent_queries(edges, claims, weights, max_queries=3)) == 3
+    assert build_dissent_queries(edges, claims, weights, max_queries=0) == []
+    monkeypatch.setenv("PG_DISSENT_QUERIES_MAX", "0")
+    assert build_dissent_queries(edges, claims, weights) == []
+
+
+# ── AC-5: injected query_fn (cluster_id, assertion); fail-soft to templates ──
+def test_injected_query_fn_used_and_fail_soft():
+    edges = [_edge(["cMaj", "cMin"])]
+    claims = [_claim("cMaj", "majority"), _claim("cMin", "minority assertion")]
+    weights = {"cMaj": 0.9, "cMin": 0.1}
+    q = build_dissent_queries(edges, claims, weights, query_fn=lambda cid, a: [f"custom {a}"])
+    assert q == ["custom minority assertion"]
+
+    def boom(cluster_id, assertion):
+        raise RuntimeError("nope")
+
+    fallback = build_dissent_queries(edges, claims, weights, query_fn=boom)
+    assert fallback and any("minority assertion" in x for x in fallback)
+
+
+# ── AC-6: weight_by_cluster also accepts a list of ClaimWeightMass ───────────
+def test_weight_accepts_claimweightmass_list():
+    edges = [_edge(["cMaj", "cMin"])]
+    claims = [_claim("cMaj", "majority"), _claim("cMin", "minority text")]
+    cwm = [type("W", (), {"claim_cluster_id": "cMaj", "weight_mass": 0.9})(),
+           type("W", (), {"claim_cluster_id": "cMin", "weight_mass": 0.1})()]
+    assert any("minority text" in x for x in build_dissent_queries(edges, claims, cwm))
+
+
+# ── AC-7: stratification plan ────────────────────────────────────────────────
+def test_stratification_plan():
+    plan = build_source_stratification_plan(2, ["serper", "s2", "openalex"])
+    assert set(plan.keys()) == {"serper", "s2", "openalex"} and all(v >= 1 for v in plan.values())
+    override = build_source_stratification_plan(2, ["serper", "s2"],
+                                                per_type_quota={"serper": 5, "s2": 0, "x": 9})
+    assert override == {"serper": 5}
+
+
+# ── AC-8: purity — inputs untouched; no network client ───────────────────────
+def test_purity_no_mutation():
+    edges = [_edge(["cA", "cB"])]
+    claims = [_claim("cB", "text")]
+    build_dissent_queries(edges, claims, {"cB": 0.1})
+    assert edges[0].subject == "vaccine" and claims[0].text == "text"
+
+
+def test_builder_imports_no_network_client():
+    import src.polaris_graph.retrieval.dissent_recall_builder as mod
+    text = open(mod.__file__, encoding="utf-8").read()
+    for forbidden in ("import httpx", "import requests", "openrouter", "run_live_retrieval"):
+        assert forbidden not in text, f"dissent builder must not {forbidden!r} — execution is the caller's"
```
