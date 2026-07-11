"""Unit tests for the FULL-CORPUS cp4_used=agentic sweep invariant (scripts/outline_agentic_sweep.py).

The sweep is credential-gated end-to-end (needs GLM-5.2), but its ASSERTION machinery — the mission
invariant 'cp4_used must be agentic; seed fallback ONLY on GLM-5.2 truncation' — is pure and must be
locked so it cannot silently drift into accepting a fallback-plain downgrade.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "outline_agentic_sweep",
    Path(__file__).resolve().parents[3] / "scripts" / "outline_agentic_sweep.py",
)
sweep = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sweep)


def test_clean_agentic_passes():
    passed, _ = sweep._classify("agentic", "")
    assert passed is True


def test_sanctioned_truncation_degrade_passes():
    passed, reason = sweep._classify(
        "agentic-degraded-seed",
        "ReasoningFirstTruncationError: reasoning prelude exceeded completion budget",
    )
    assert passed is True and "truncation" in reason


def test_non_truncation_degrade_fails():
    passed, reason = sweep._classify("agentic-degraded-seed", "TimeoutError: wall exceeded")
    assert passed is False and "NON-truncation" in reason


def test_fallback_plain_fails():
    passed, reason = sweep._classify("plain", "")
    assert passed is False and "fallback-plain is forbidden" in reason


def test_missing_cp4_block_fails():
    passed, _ = sweep._classify("MISSING", "")
    assert passed is False


def test_count_baskets_counts_total_clusters_including_singletons():
    # TOTAL baskets = every cp3 claim-group cluster (singletons INCLUDED). The canonical s3gear
    # full corpus is 329 baskets (38 multi-member + 291 singletons); counting only >=2-member
    # clusters undercounts to 38 and made --min-baskets 328 unsatisfiable.
    clusters = [{"member_indices": [1, 2]}, {"member_indices": [3]}, {"member_indices": [4, 5, 6]}]
    assert sweep._count_baskets(clusters) == 3
    # duck-typed over objects too
    from types import SimpleNamespace
    objs = [SimpleNamespace(member_indices=[1, 2]), SimpleNamespace(member_indices=[3])]
    assert sweep._count_baskets(objs) == 2


def test_dry_run_selfcheck_passes():
    # the offline self-check the operator runs to confirm the machinery before keys land.
    assert sweep._dry_run_selfcheck() == 0


def test_preflight_corpus_loadable_and_index_bounds(tmp_path):
    import json
    from pathlib import Path as _P
    # a corpus whose member/representative indices all resolve into a 3-row pool
    good = {
        "research_question": "q?",
        "evidence": [{"evidence_id": "e0"}, {"evidence_id": "e1"}, {"evidence_id": "e2"}],
        "finding_clusters": [
            {"representative_index": 0, "member_indices": [0, 1]},
            {"representative_index": 2, "member_indices": [2]},
        ],
    }
    gp = tmp_path / "good.json"
    gp.write_text(json.dumps(good))
    ok, msg = sweep.preflight_corpus(_P(gp), min_baskets=2)
    assert ok, msg
    assert "2 baskets" in msg
    # below the basket floor -> not ok
    ok2, _ = sweep.preflight_corpus(_P(gp), min_baskets=3)
    assert not ok2
    # an out-of-range index -> fail closed
    bad = dict(good)
    bad["finding_clusters"] = [{"representative_index": 9, "member_indices": [9]}]
    bp = tmp_path / "bad.json"
    bp.write_text(json.dumps(bad))
    ok3, msg3 = sweep.preflight_corpus(_P(bp), min_baskets=1)
    assert not ok3 and "out of range" in msg3
