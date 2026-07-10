"""Unit tests for the S4 cp4 outline-snapshot checkpoint (Design 5 §4 + master §5).

DATA-ONLY contract: round-trips deterministically, and fail-loud refuses any forbidden verdict
key (top-level OR nested) and corrupt JSON — never a silent load (§-1.3 ABSOLUTE / LAW II).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.generator.outline_checkpoint import (
    CP4_OUTLINE_SNAPSHOT_FILENAME,
    build_cp4_payload,
    load_cp4_outline_snapshot,
    write_cp4_outline_snapshot,
)


def _good_payload() -> dict:
    return build_cp4_payload(
        question_sha="q_sha_abc",
        upstream=[{"name": "cp3_basket_snapshot.json", "sha256": "deadbeef"}],
        run_config_sha="rc_sha_123",
        flag_slate={"PG_OUTLINE_BASKET_DIGEST": "1", "PG_OUTLINE_REVISE": "1"},
        adjustments_applied=[],
        final_plans=[{"title": "Efficacy", "ev_ids": ["ev01"], "basket_ids": ["B00"]}],
        revision_audit={"rounds": 1, "applied_ops": [{"op": "keep", "title": "Efficacy"}],
                        "recompose_titles": [], "rejected_ops": []},
        digest_stats={"baskets": 2, "singletons": 4, "total_chars": 1234, "degraded": False},
    )


def test_round_trip(tmp_path: Path) -> None:
    payload = _good_payload()
    written = write_cp4_outline_snapshot(tmp_path, payload)
    assert written is not None and written.name == CP4_OUTLINE_SNAPSHOT_FILENAME
    loaded = load_cp4_outline_snapshot(tmp_path)
    assert loaded == payload
    assert loaded["stage"] == "outline" and loaded["schema_version"] == 1
    assert loaded["payload"]["final_plans"][0]["title"] == "Efficacy"


def test_absent_returns_none(tmp_path: Path) -> None:
    assert load_cp4_outline_snapshot(tmp_path) is None


def test_deterministic_sorted_bytes(tmp_path: Path) -> None:
    write_cp4_outline_snapshot(tmp_path, _good_payload())
    first = (tmp_path / CP4_OUTLINE_SNAPSHOT_FILENAME).read_text(encoding="utf-8")
    write_cp4_outline_snapshot(tmp_path, _good_payload())
    second = (tmp_path / CP4_OUTLINE_SNAPSHOT_FILENAME).read_text(encoding="utf-8")
    assert first == second
    # sorted keys => "faithfulness_invariant" precedes "flag_slate" precedes "payload"
    assert first.index('"faithfulness_invariant"') < first.index('"flag_slate"') < first.index('"payload"')


def test_build_rejects_top_level_verdict_key() -> None:
    with pytest.raises(ValueError, match="FORBIDDEN verdict key"):
        # inject a verdict key by hand-rolling a payload the builder would refuse
        from src.polaris_graph.generator.outline_checkpoint import _assert_no_verdict_keys
        _assert_no_verdict_keys({"stage": "outline", "release_outcome": "allow"})


def test_load_fail_loud_on_nested_verdict_key(tmp_path: Path) -> None:
    poisoned = _good_payload()
    poisoned["payload"]["revision_audit"]["d8_decision"] = "release"  # verdict smuggled deep
    path = tmp_path / CP4_OUTLINE_SNAPSHOT_FILENAME
    path.write_text(json.dumps(poisoned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="FORBIDDEN verdict key"):
        load_cp4_outline_snapshot(tmp_path)


def test_load_fail_loud_on_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / CP4_OUTLINE_SNAPSHOT_FILENAME).write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_cp4_outline_snapshot(tmp_path)


def test_write_is_best_effort_no_raise_on_bad_dir() -> None:
    # a non-existent parent directory => write returns None, never raises (never a run blocker)
    result = write_cp4_outline_snapshot(Path("/nonexistent_dir_xyz_123/deeper"), _good_payload())
    assert result is None
