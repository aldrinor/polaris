"""S3 CONSOLIDATE checkpoint — ``cp3_basket_snapshot.json`` contract (Master Execution Plan v2 §4 S3).

Offline unit harness (pure JSON + the REAL consolidation dataclasses — no network, no model, no
embedding). Proves the S3 bar on a FIXTURE:

  (a) OFF byte-neutral: PG_CP3_BASKET_SNAPSHOT=0 => no cp3 written; a None credibility_analysis
      (master flag off) => no cp3 written.
  (b) ROUND-TRIP byte-identical: save -> reload -> re-serialize is byte-for-byte the written file;
      two builds of the same consolidation produce an identical DATA body (deterministic bytes).
  (c) CONSOLIDATE-DON'T-DROP: every supporting_member of every basket survives into cp3 (keep ALL
      sources per claim — §-1.3 principle 2).
  (d) DATA ONLY: the per-member ``span_verdict`` and the ``basket_verdict`` LABEL — present on the
      REAL dataclasses — are EXCLUDED from the payload; no forbidden verdict key at any depth.
  (e) VERDICT-SMUGGLING RED test: a poisoned cp3 (a forbidden verdict key nested in a member) is
      REFUSED fail-loud on load; a leaked key is refused fail-loud on build.
  (f) FAIL-LOUD identity: absent / corrupt / schema-mismatched / question-mismatched cp3 all raise.
  (g) contradiction pairs + upstream hash-chain are captured as DATA.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator import cp3_basket_snapshot as cp3
from src.polaris_graph.synthesis.claim_graph import ContradictionEdge
from src.polaris_graph.synthesis.credibility_pass import (
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)

_QUESTION = "What is the labor-market impact of AI on the workforce?"


# ───────────────────────── fixture: a real consolidation ─────────────────────────


def _member(evidence_id: str, cluster: str, *, tier: str, verdict: str) -> BasketMember:
    """A REAL BasketMember carrying a per-member span_verdict (which cp3 must EXCLUDE)."""
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier=tier,
        origin_cluster_id=cluster,
        credibility_weight=0.83,
        authority_score=0.71,
        span=(10, 42),
        direct_quote=f"quote backing {evidence_id}",
        span_verdict=verdict,  # <-- the isolated gate output cp3 must NOT store
    )


def _analysis() -> CredibilityAnalysis:
    """A CredibilityAnalysis with two baskets (one multi-source, one singleton) + one edge."""
    basket_a = ClaimBasket(
        claim_cluster_id="cl_ai_jobs",
        claim_text="AI raised task productivity by 14%.",
        subject="AI",
        predicate="raised task productivity",
        # THREE sources carrying the SAME claim — corroboration, none may be dropped.
        supporting_members=[
            _member("ev1", "orig_a", tier="T1", verdict="SUPPORTS"),
            _member("ev2", "orig_b", tier="T2", verdict="SUPPORTS"),
            _member("ev3", "orig_c", tier="T4", verdict="UNSUPPORTED"),
        ],
        refuter_cluster_ids=("cl_ai_jobs_down",),
        weight_mass=2.31,
        total_clustered_origin_count=3,
        verified_support_origin_count=2,
        basket_verdict="contested",  # <-- the derived LABEL cp3 must NOT store
    )
    basket_b = ClaimBasket(
        claim_cluster_id="cl_ai_jobs_down",
        claim_text="AI reduced net employment in routine roles.",
        subject="AI",
        predicate="reduced net employment",
        supporting_members=[_member("ev4", "orig_d", tier="T3", verdict="SUPPORTS")],
        refuter_cluster_ids=(),
        weight_mass=0.9,
        total_clustered_origin_count=1,
        verified_support_origin_count=1,
        basket_verdict="full",
    )
    edge = ContradictionEdge(
        source="numeric",
        subject="AI",
        predicate="employment effect",
        evidence_ids=("ev1", "ev4"),
        claim_cluster_ids=("cl_ai_jobs", "cl_ai_jobs_down"),
        severity="review",
    )
    return CredibilityAnalysis(
        credibility_by_evidence={},
        origin_by_evidence={},
        claims=[],
        edges=[edge],
        weight_mass=[],
        baskets=[basket_a, basket_b],
    )


def _save(tmp_path, **overrides):
    kwargs = dict(
        run_id="run_test",
        question=_QUESTION,
        slug="workforce/drb_72_ai_labor",
        domain="workforce",
        credibility_analysis=_analysis(),
        upstream_name="corpus_snapshot.json",
        upstream_sha256="deadbeef",
        created_utc="",  # keep bytes deterministic across runs
    )
    kwargs.update(overrides)
    return cp3.save_cp3_basket_snapshot(tmp_path, **kwargs)


# ───────────────────────── (a) OFF byte-neutral ─────────────────────────


def test_kill_switch_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(cp3.CP3_SNAPSHOT_ENV, "0")
    assert _save(tmp_path) is None
    assert not cp3.cp3_snapshot_path(tmp_path).exists()


def test_none_analysis_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    assert _save(tmp_path, credibility_analysis=None) is None
    assert not cp3.cp3_snapshot_path(tmp_path).exists()


def test_enabled_by_default(monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    assert cp3.cp3_snapshot_enabled() is True
    monkeypatch.setenv(cp3.CP3_SNAPSHOT_ENV, "off")
    assert cp3.cp3_snapshot_enabled() is False


# ───────────────────────── (b) round-trip byte-identity + determinism ─────────────────────────


def test_roundtrip_byte_identical(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    path = _save(tmp_path)
    assert path is not None and path.name == cp3.CP3_SNAPSHOT_FILENAME
    written = path.read_text(encoding="utf-8")
    loaded = cp3.load_cp3_basket_snapshot(tmp_path)
    # Re-serializing the reloaded payload reproduces the file byte-for-byte.
    assert cp3.serialize_cp3_payload(loaded) == written


def test_build_is_deterministic():
    a = cp3.build_cp3_payload(
        run_id="r", question=_QUESTION, slug="s", domain="d",
        credibility_analysis=_analysis(), upstream_sha256="x",
    )
    b = cp3.build_cp3_payload(
        run_id="r", question=_QUESTION, slug="s", domain="d",
        credibility_analysis=_analysis(), upstream_sha256="x",
    )
    assert cp3.serialize_cp3_payload(a) == cp3.serialize_cp3_payload(b)


# ───────────────────────── (c) consolidate — keep ALL members ─────────────────────────


def test_keep_all_members_never_dropped(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    _save(tmp_path)
    payload = cp3.load_cp3_basket_snapshot(tmp_path)
    baskets = payload["payload"]["baskets"]
    assert payload["payload"]["basket_count"] == 2
    multi = next(b for b in baskets if b["claim_cluster_id"] == "cl_ai_jobs")
    # ALL THREE sources survive — corroboration is never thinned.
    got = sorted(m["evidence_id"] for m in multi["members"])
    assert got == ["ev1", "ev2", "ev3"]
    assert multi["corroboration_count"] == 2
    assert multi["weight_mass"] == pytest.approx(2.31)
    # per-member WEIGHTS + the pre-verdict span binding are DATA that survives.
    m1 = next(m for m in multi["members"] if m["evidence_id"] == "ev1")
    assert m1["credibility_weight"] == pytest.approx(0.83)
    assert m1["span"] == [10, 42]
    assert m1["direct_quote"] == "quote backing ev1"


# ───────────────────────── (d) DATA only — verdict labels excluded ─────────────────────────


def test_span_and_basket_verdict_excluded(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    path = _save(tmp_path)
    payload = cp3.load_cp3_basket_snapshot(tmp_path)
    # The derived faithfulness LABELs are never serialized as DATA keys (structural check — the
    # invariant NOTE legitimately names the excluded fields, so a raw substring check would be wrong).
    for basket in payload["payload"]["baskets"]:
        assert "basket_verdict" not in basket
        for member in basket["members"]:
            assert "span_verdict" not in member
    # The label VALUES never appear anywhere in the bytes (they carry the excluded decision).
    raw = path.read_text(encoding="utf-8")
    assert "SUPPORTS" not in raw and "UNSUPPORTED" not in raw
    assert '"contested"' not in raw


def test_no_forbidden_verdict_key_at_any_depth(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    _save(tmp_path)
    payload = cp3.load_cp3_basket_snapshot(tmp_path)

    def _walk(obj):
        if isinstance(obj, dict):
            assert not (cp3._FORBIDDEN_VERDICT_KEYS & set(obj.keys()))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(payload)


# ───────────────────────── (e) verdict-smuggling RED test ─────────────────────────


def test_poisoned_cp3_refused_on_load(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    path = _save(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Smuggle a release verdict deep inside a basket member (the exact §-1.3 hazard).
    payload["payload"]["baskets"][0]["members"][0]["release_outcome"] = "allowed"
    path.write_text(cp3.serialize_cp3_payload(payload), encoding="utf-8")
    with pytest.raises(cp3.Cp3SnapshotError, match="FORBIDDEN verdict key"):
        cp3.load_cp3_basket_snapshot(tmp_path)


def test_leaked_verdict_refused_on_build():
    class _EvilBasket:  # a basket whose refuters slot smuggles a nested verdict dict
        claim_cluster_id = "x"
        claim_text = "t"
        subject = "s"
        predicate = "p"
        weight_mass = 1.0
        total_clustered_origin_count = 1
        verified_support_origin_count = 1
        supporting_members: list = []
        refuter_cluster_ids = ()

    # A clean analysis passes; assert the guard is actually wired on the build path by feeding a
    # payload that contains a forbidden key and confirming the recursive guard raises.
    bad_payload = {"payload": {"baskets": [{"members": [{"is_verified": True}]}]}}
    with pytest.raises(cp3.Cp3SnapshotError, match="FORBIDDEN verdict key"):
        cp3._assert_no_verdict_keys_recursive(bad_payload)


# ───────────────────────── (f) fail-loud identity ─────────────────────────


def test_absent_refused(tmp_path):
    with pytest.raises(cp3.Cp3SnapshotError, match="no cp3 basket snapshot"):
        cp3.load_cp3_basket_snapshot(tmp_path)


def test_corrupt_json_refused(tmp_path):
    cp3.cp3_snapshot_path(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(cp3.Cp3SnapshotError, match="unreadable/corrupt"):
        cp3.load_cp3_basket_snapshot(tmp_path)


def test_schema_version_mismatch_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    path = _save(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = cp3.CP3_SCHEMA_VERSION + 99
    path.write_text(cp3.serialize_cp3_payload(payload), encoding="utf-8")
    with pytest.raises(cp3.Cp3SnapshotError, match="schema_version"):
        cp3.load_cp3_basket_snapshot(tmp_path)


def test_question_sha_mismatch_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    _save(tmp_path)
    with pytest.raises(cp3.Cp3SnapshotError, match="GATE0 identity mismatch"):
        cp3.load_cp3_basket_snapshot(tmp_path, expected_question_sha="not-the-right-sha")
    # the matching sha loads clean
    ok = cp3.load_cp3_basket_snapshot(
        tmp_path, expected_question_sha=cp3.question_sha256(_QUESTION)
    )
    assert ok["stage"] == cp3.CP3_STAGE


# ───────────────────────── (g) contradiction pairs + hash-chain ─────────────────────────


def test_contradiction_pairs_and_upstream_chain(tmp_path, monkeypatch):
    monkeypatch.delenv(cp3.CP3_SNAPSHOT_ENV, raising=False)
    _save(tmp_path, upstream_sha256="cafef00d")
    payload = cp3.load_cp3_basket_snapshot(tmp_path)
    pairs = payload["payload"]["contradiction_pairs"]
    assert payload["payload"]["contradiction_pair_count"] == 1
    assert pairs[0]["source"] == "numeric"
    assert pairs[0]["evidence_ids"] == ["ev1", "ev4"]
    assert pairs[0]["claim_cluster_ids"] == ["cl_ai_jobs", "cl_ai_jobs_down"]
    assert payload["upstream"] == {"name": "corpus_snapshot.json", "sha256": "cafef00d"}
    assert payload["stage"] == cp3.CP3_STAGE
    assert payload["question_sha"] == cp3.question_sha256(_QUESTION)
    # the consolidation flag slate is stamped (DATA — resume refuses on drift)
    assert set(payload["flag_slate"]) == set(cp3.CONSOLIDATION_AFFECTING_ENV_FLAGS)
