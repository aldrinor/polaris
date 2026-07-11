"""Tests for scripts/cp3_to_cp4_corpus.py — the deterministic cp3->cp4 sweep-corpus converter.

Covers the three properties the mission names: (1) id resolution / fail-closed on a miss,
(2) cluster reconstruction (member_evidence_ids -> positional member_indices), (3) total basket
count. Synthetic fixtures make the logic portable; a final real-data test asserts the canonical
329-basket total when the on-disk snapshots are present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.cp3_to_cp4_corpus import (  # noqa: E402
    build_cp4_corpus,
    build_pool,
    convert,
    referenced_evidence_ids,
)


def _mini_cp3() -> dict:
    """A tiny cp3 snapshot: 3 baskets (one multi-member, two singletons), one same-work group.

    ev_only_in_retrieval is referenced by a basket but NOT in evidence_for_gen — it must be
    supplemented from the retrieval pool (mirrors the real ev_621 case).
    """
    return {
        "run_id": "test",
        "stage": "cp3",
        "question": "What is the impact of X on Y?",
        "domain": "workforce",
        "payload": {
            "baskets": [
                {
                    "claim_group_id": "cg_1",
                    "corroboration_count": 2,
                    "member_evidence_ids": ["ev_b", "ev_a"],
                    "representative_evidence_id": "ev_a",
                    "member_hosts": ["a.org", "b.org"],
                    "member_count": 2,
                },
                {
                    "claim_group_id": "cg_2",
                    "corroboration_count": 1,
                    "member_evidence_ids": ["ev_c"],
                    "representative_evidence_id": "ev_c",
                    "member_hosts": ["c.org"],
                    "member_count": 1,
                },
                {
                    "claim_group_id": "cg_3",
                    "corroboration_count": 1,
                    "member_evidence_ids": ["ev_only_in_retrieval"],
                    "representative_evidence_id": "ev_only_in_retrieval",
                    "member_hosts": ["r.org"],
                    "member_count": 1,
                },
            ],
            "same_work_groups": [
                {
                    "same_work_id": "title:some work",
                    "canonical_index": 0,
                    "member_evidence_ids": ["ev_a", "ev_swg_only"],
                },
            ],
        },
    }


def _mini_cp2() -> dict:
    return {
        "evidence_for_gen": [
            {"evidence_id": "ev_a", "tier": "T1", "title": "A", "statement": "sa", "source_url": "https://a.org"},
            {"evidence_id": "ev_b", "tier": "T2", "title": "B", "statement": "sb", "source_url": "https://b.org"},
            {"evidence_id": "ev_c", "tier": "T1", "title": "C", "statement": "sc", "source_url": "https://c.org"},
            {"evidence_id": "ev_swg_only", "tier": "T2", "title": "S", "statement": "ss", "source_url": "https://s.org"},
            {"evidence_id": "ev_unused", "tier": "T3", "title": "U", "statement": "su", "source_url": "https://u.org"},
        ],
        "retrieval": {
            "evidence_rows": [
                {"evidence_id": "ev_only_in_retrieval", "tier": "T3", "title": "R",
                 "statement": "sr", "source_url": "https://r.org"},
            ],
        },
    }


def test_referenced_ids_include_baskets_and_same_work():
    ref = referenced_evidence_ids(_mini_cp3())
    assert ref == {"ev_a", "ev_b", "ev_c", "ev_only_in_retrieval", "ev_swg_only"}


def test_build_pool_supplements_from_retrieval():
    ref = referenced_evidence_ids(_mini_cp3())
    pool, missing = build_pool(_mini_cp2(), ref)
    assert missing == []
    ids = [r["evidence_id"] for r in pool]
    # for-gen pool preserved in native order, then the retrieval-only id appended at the tail
    assert ids[:5] == ["ev_a", "ev_b", "ev_c", "ev_swg_only", "ev_unused"]
    assert ids[-1] == "ev_only_in_retrieval"
    assert set(ref) <= set(ids)


def test_cluster_reconstruction_indices_point_at_pool():
    cp3 = _mini_cp3()
    pool, _ = build_pool(_mini_cp2(), referenced_evidence_ids(cp3))
    corpus = build_cp4_corpus(cp3, pool)
    id2idx = {r["evidence_id"]: i for i, r in enumerate(pool)}

    clusters = corpus["finding_clusters"]
    assert len(clusters) == 3
    assert corpus["basket_total"] == 3

    # basket cg_1: member_evidence_ids ["ev_b","ev_a"] -> the SAME positions, order preserved
    c0 = clusters[0]
    assert c0["member_indices"] == [id2idx["ev_b"], id2idx["ev_a"]]
    assert c0["representative_index"] == id2idx["ev_a"]
    assert c0["corroboration_count"] == 2
    assert c0["member_hosts"] == ["a.org", "b.org"]
    # every dereferenced index resolves back to the right evidence id
    for c in clusters:
        for i in c["member_indices"]:
            assert 0 <= i < len(pool)
        assert 0 <= c["representative_index"] < len(pool)
    # research_question mapped from cp3.question; same_work_groups passed through untouched
    assert corpus["research_question"] == cp3["question"]
    assert corpus["same_work_groups"] == cp3["payload"]["same_work_groups"]


def test_fail_closed_on_unresolvable_reference():
    cp3 = _mini_cp3()
    # a pool that is MISSING a referenced id must raise, never write a partial corpus
    bad_pool = [{"evidence_id": "ev_a"}, {"evidence_id": "ev_b"}, {"evidence_id": "ev_c"}]
    with pytest.raises(ValueError, match="do not resolve"):
        build_cp4_corpus(cp3, bad_pool)


def test_build_pool_reports_missing_when_id_absent_everywhere():
    cp3 = _mini_cp3()
    cp2 = _mini_cp2()
    # drop the retrieval supplement so ev_only_in_retrieval cannot be found anywhere
    cp2["retrieval"]["evidence_rows"] = []
    _pool, missing = build_pool(cp2, referenced_evidence_ids(cp3))
    assert "ev_only_in_retrieval" in missing


def test_convert_end_to_end_writes_corpus(tmp_path):
    cp3_p = tmp_path / "cp3.json"
    cp2_p = tmp_path / "cp2.json"
    out_p = tmp_path / "cp4.json"
    snap_p = tmp_path / "pool_snap.json"
    cp3_p.write_text(json.dumps(_mini_cp3()))
    cp2_p.write_text(json.dumps(_mini_cp2()))

    corpus = convert(cp3_p, cp2_p, out_p, snap_p)
    assert out_p.exists() and snap_p.exists()
    assert corpus["basket_total"] == 3
    on_disk = json.loads(out_p.read_text())
    assert on_disk["research_question"] == _mini_cp3()["question"]

    # durability: external cp2 gone -> rebuild from the pool snapshot, identical corpus
    out2 = tmp_path / "cp4_again.json"
    corpus2 = convert(cp3_p, tmp_path / "does_not_exist.json", out2, snap_p)
    assert corpus2["finding_clusters"] == corpus["finding_clusters"]
    assert corpus2["evidence"] == corpus["evidence"]


# ── real-data canary: the canonical s3gear full corpus is 329 baskets / 425 referenced ids ──
_REAL_CP3 = REPO_ROOT / "data" / "cp3_s3gear_329basket_snapshot.json"
_REAL_CP2 = Path("/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json")
_REAL_POOL_SNAP = REPO_ROOT / "data" / "cp2_evidence_pool_snapshot.json"


@pytest.mark.skipif(
    not _REAL_CP3.exists() or not (_REAL_CP2.exists() or _REAL_POOL_SNAP.exists()),
    reason="real cp3/cp2 snapshots not present in this environment",
)
def test_real_corpus_total_is_329_and_all_ids_resolve(tmp_path):
    out_p = tmp_path / "cp4_real.json"
    corpus = convert(_REAL_CP3, _REAL_CP2, out_p, _REAL_POOL_SNAP)
    assert corpus["basket_total"] == 329
    assert corpus["_provenance"]["referenced_ids"] == 425
    # build_cp4_corpus already fail-closed on any unresolved id, so reaching here proves 425/425
    id2idx = {r["evidence_id"]: i for i, r in enumerate(corpus["evidence"])}
    for c in corpus["finding_clusters"]:
        for i in c["member_indices"]:
            assert 0 <= i < len(corpus["evidence"])
        assert c["representative_index"] in id2idx.values()
