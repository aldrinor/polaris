"""I-cred-010 (Phase 10) — dissent-recall builder. Offline, deterministic, no network."""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.dissent_recall_builder import (
    build_dissent_queries,
    build_source_stratification_plan,
    dissent_recall_enabled,
)


def _edge(cids, subject="vaccine", predicate="hospitalization"):
    return type("E", (), {"subject": subject, "predicate": predicate,
                          "claim_cluster_ids": tuple(cids), "severity": "review"})()


def _claim(cid, text, subject="vaccine", predicate="hospitalization"):
    return type("C", (), {"claim_cluster_id": cid, "text": text,
                          "subject": subject, "predicate": predicate})()


# ── AC-1 ──────────────────────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_DISSENT_RECALL", raising=False)
    assert dissent_recall_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on(monkeypatch, on):
    monkeypatch.setenv("PG_SWEEP_DISSENT_RECALL", on)
    assert dissent_recall_enabled() is True


# ── AC-2: no edges -> empty (byte-identity precondition) ─────────────────────
def test_no_edges_empty():
    assert build_dissent_queries([], [], {}) == []
    assert build_source_stratification_plan(0, ["serper", "s2"]) == {}


# ── AC-3 (core): targets the MINORITY (lowest-weight) cluster's assertion ────
def test_targets_minority_side_assertion():
    edges = [_edge(["cMaj", "cMin"])]
    claims = [
        _claim("cMaj", "vaccine reduced hospitalization substantially"),
        _claim("cMin", "vaccine showed no effect on hospitalization"),
    ]
    weights = {"cMaj": 0.9, "cMin": 0.1}  # cMin is the minority (lowest weight)
    q = build_dissent_queries(edges, claims, weights)
    joined = " ".join(q).lower()
    assert "no effect on hospitalization" in joined     # seeks the MINORITY assertion
    assert "reduced hospitalization" not in joined       # NOT the majority's
    assert q == build_dissent_queries(edges, claims, weights)  # deterministic
    assert len(q) == len(set(q))                              # deduped


def test_minority_flips_when_weights_flip():
    edges = [_edge(["cA", "cB"])]
    claims = [_claim("cA", "claim A text alpha"), _claim("cB", "claim B text beta")]
    qa = build_dissent_queries(edges, claims, {"cA": 0.1, "cB": 0.9})  # A is minority
    assert any("alpha" in x for x in qa) and not any("beta" in x for x in qa)
    qb = build_dissent_queries(edges, claims, {"cA": 0.9, "cB": 0.1})  # B is minority
    assert any("beta" in x for x in qb) and not any("alpha" in x for x in qb)


# ── AC-4: cap + zero/negative cap emits nothing ──────────────────────────────
def test_max_queries_cap_and_zero(monkeypatch):
    edges = [_edge([f"c{i}a", f"c{i}b"]) for i in range(10)]
    claims = ([_claim(f"c{i}a", f"major {i}") for i in range(10)]
              + [_claim(f"c{i}b", f"assertion {i}") for i in range(10)])
    weights = {f"c{i}a": 0.9 for i in range(10)}
    weights.update({f"c{i}b": 0.1 for i in range(10)})  # every 'b' cluster is the minority
    assert len(build_dissent_queries(edges, claims, weights, max_queries=3)) == 3
    assert build_dissent_queries(edges, claims, weights, max_queries=0) == []
    monkeypatch.setenv("PG_DISSENT_QUERIES_MAX", "0")
    assert build_dissent_queries(edges, claims, weights) == []


# ── AC-5: injected query_fn (cluster_id, assertion); fail-soft to templates ──
def test_injected_query_fn_used_and_fail_soft():
    edges = [_edge(["cMaj", "cMin"])]
    claims = [_claim("cMaj", "majority"), _claim("cMin", "minority assertion")]
    weights = {"cMaj": 0.9, "cMin": 0.1}
    q = build_dissent_queries(edges, claims, weights, query_fn=lambda cid, a: [f"custom {a}"])
    assert q == ["custom minority assertion"]

    def boom(cluster_id, assertion):
        raise RuntimeError("nope")

    fallback = build_dissent_queries(edges, claims, weights, query_fn=boom)
    assert fallback and any("minority assertion" in x for x in fallback)


# ── AC-6: weight_by_cluster also accepts a list of ClaimWeightMass ───────────
def test_weight_accepts_claimweightmass_list():
    edges = [_edge(["cMaj", "cMin"])]
    claims = [_claim("cMaj", "majority"), _claim("cMin", "minority text")]
    cwm = [type("W", (), {"claim_cluster_id": "cMaj", "weight_mass": 0.9})(),
           type("W", (), {"claim_cluster_id": "cMin", "weight_mass": 0.1})()]
    assert any("minority text" in x for x in build_dissent_queries(edges, claims, cwm))


# ── AC-7: stratification plan ────────────────────────────────────────────────
def test_stratification_plan():
    plan = build_source_stratification_plan(2, ["serper", "s2", "openalex"])
    assert set(plan.keys()) == {"serper", "s2", "openalex"} and all(v >= 1 for v in plan.values())
    override = build_source_stratification_plan(2, ["serper", "s2"],
                                                per_type_quota={"serper": 5, "s2": 0, "x": 9})
    assert override == {"serper": 5}


# ── AC-8: purity — inputs untouched; no network client ───────────────────────
def test_purity_no_mutation():
    edges = [_edge(["cA", "cB"])]
    claims = [_claim("cB", "text")]
    build_dissent_queries(edges, claims, {"cB": 0.1})
    assert edges[0].subject == "vaccine" and claims[0].text == "text"


def test_builder_imports_no_network_client():
    import src.polaris_graph.retrieval.dissent_recall_builder as mod
    text = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ("import httpx", "import requests", "openrouter", "run_live_retrieval"):
        assert forbidden not in text, f"dissent builder must not {forbidden!r} — execution is the caller's"
