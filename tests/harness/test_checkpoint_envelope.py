"""Offline oracle tests for the shared checkpoint envelope + traceability ledger.

No production predicate imports, no LLM, no network — pure on-disk envelope round-trips over
tmp_path fixtures (I-wire-013 independence lesson: the oracle must not import the code path it
is meant to catch). Proves: DATA-only round-trip, recursive verdict-key refusal on save AND
load, GATE0 identity refusal, flag-slate / run_config drift refusal, hash-chain validation +
break detection, nearest / explicit resume resolution, and byte-determinism.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator import checkpoint_envelope as ce


def _save(run_dir, stage, question="Q?", upstream_stage=None, payload=None, **kw):
    return ce.save_checkpoint(
        run_dir,
        stage=stage,
        run_id="run-1",
        slug="drb_72_ai_labor",
        domain="workforce",
        question=question,
        payload=payload if payload is not None else {"rows": [1, 2, 3]},
        upstream_stage=upstream_stage,
        **kw,
    )


def test_round_trip_data_only(tmp_path):
    path, sha = _save(tmp_path, ce.STAGE_S3_CONSOLIDATE, payload={"baskets": [{"members": ["a"]}]})
    assert path.name == "cp3_basket_snapshot.json"
    env = ce.load_checkpoint(tmp_path, ce.STAGE_S3_CONSOLIDATE)
    assert env["payload"] == {"baskets": [{"members": ["a"]}]}
    assert env["question_sha"] == ce.question_sha("Q?")
    assert env["faithfulness_invariant"].startswith("DATA ONLY")
    # ledger recorded it with the content sha
    entries = ce.load_index(tmp_path)
    assert entries[-1]["sha256"] == sha
    assert entries[-1]["stage"] == ce.STAGE_S3_CONSOLIDATE


def test_save_refuses_verdict_key_nested(tmp_path):
    with pytest.raises(ce.CheckpointEnvelopeError, match="FORBIDDEN verdict key"):
        _save(tmp_path, ce.STAGE_S4_OUTLINE, payload={"plans": [{"is_verified": True}]})
    # nothing was written
    assert not (tmp_path / "cp4_outline_snapshot.json").exists()


def test_load_refuses_verdict_key_smuggled_on_disk(tmp_path):
    _save(tmp_path, ce.STAGE_S3_CONSOLIDATE)
    path = tmp_path / "cp3_basket_snapshot.json"
    env = json.loads(path.read_text(encoding="utf-8"))
    env["payload"]["baskets"] = [{"d8_decision": "release"}]  # smuggle a decision post-write
    path.write_text(json.dumps(env), encoding="utf-8")
    with pytest.raises(ce.CheckpointEnvelopeError, match="FORBIDDEN verdict key"):
        ce.load_checkpoint(tmp_path, ce.STAGE_S3_CONSOLIDATE)


def test_gate0_identity_mismatch_refused(tmp_path):
    _save(tmp_path, ce.STAGE_S3_CONSOLIDATE, question="original question")
    with pytest.raises(ce.CheckpointEnvelopeError, match="GATE0 identity mismatch"):
        ce.load_checkpoint(
            tmp_path,
            ce.STAGE_S3_CONSOLIDATE,
            expected_question_sha=ce.question_sha("a DIFFERENT question"),
        )


def test_flag_slate_drift_refused(tmp_path):
    _save(tmp_path, ce.STAGE_S3_CONSOLIDATE, flag_slate={"PG_OUTLINE_BASKET_DIGEST": "1"})
    # same flag matches
    ce.load_checkpoint(
        tmp_path, ce.STAGE_S3_CONSOLIDATE,
        expected_flag_slate={"PG_OUTLINE_BASKET_DIGEST": "1"},
    )
    with pytest.raises(ce.CheckpointEnvelopeError, match="flag slate differs"):
        ce.load_checkpoint(
            tmp_path, ce.STAGE_S3_CONSOLIDATE,
            expected_flag_slate={"PG_OUTLINE_BASKET_DIGEST": "0"},
        )


def test_run_config_drift_refused(tmp_path):
    _save(tmp_path, ce.STAGE_S3_CONSOLIDATE, run_config_sha="abc123")
    with pytest.raises(ce.CheckpointEnvelopeError, match="run_config_sha"):
        ce.load_checkpoint(
            tmp_path, ce.STAGE_S3_CONSOLIDATE, expected_run_config_sha="deadbeef"
        )


def test_hash_chain_valid_then_broken(tmp_path):
    _save(tmp_path, ce.STAGE_S1_FETCH)
    _save(tmp_path, ce.STAGE_S2_SELECT, upstream_stage=ce.STAGE_S1_FETCH)
    _save(tmp_path, ce.STAGE_S3_CONSOLIDATE, upstream_stage=ce.STAGE_S2_SELECT)
    validated = ce.validate_hash_chain(tmp_path)
    assert [e["stage"] for e in validated] == [
        ce.STAGE_S1_FETCH, ce.STAGE_S2_SELECT, ce.STAGE_S3_CONSOLIDATE,
    ]
    # tamper with cp1's bytes so cp2's pinned upstream_sha no longer matches
    p1 = tmp_path / "cp1_fetch_snapshot.json"
    p1.write_text(p1.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    # re-register the tampered cp1 into the ledger so its recorded sha changes
    ce.register_legacy_snapshot(tmp_path, ce.STAGE_S1_FETCH)
    with pytest.raises(ce.CheckpointEnvelopeError, match="hash-chain BROKEN"):
        ce.validate_hash_chain(tmp_path)


def test_resume_nearest_and_explicit(tmp_path):
    _save(tmp_path, ce.STAGE_S1_FETCH)
    _save(tmp_path, ce.STAGE_S2_SELECT, upstream_stage=ce.STAGE_S1_FETCH)
    _save(tmp_path, ce.STAGE_S4_OUTLINE, upstream_stage=ce.STAGE_S2_SELECT)
    # nearest = latest present in ladder order
    assert ce.resolve_resume_stage(tmp_path) == ce.STAGE_S4_OUTLINE
    # explicit by cp alias
    assert ce.resolve_resume_stage(tmp_path, "cp2") == ce.STAGE_S2_SELECT
    assert ce.resolve_resume_stage(tmp_path, "s1_fetch") == ce.STAGE_S1_FETCH
    with pytest.raises(ce.CheckpointEnvelopeError, match="not present"):
        ce.resolve_resume_stage(tmp_path, "cp3")


def test_byte_determinism_pinned_timestamp(tmp_path):
    # same payload + pinned created_utc -> byte-identical envelope -> identical content sha
    e1 = ce.build_envelope(
        stage=ce.STAGE_S3_CONSOLIDATE, run_id="r", slug="s", domain="d",
        question="Q", payload={"b": [3, 1, 2]}, created_utc="2026-07-10T00:00:00+00:00",
    )
    e2 = ce.build_envelope(
        stage=ce.STAGE_S3_CONSOLIDATE, run_id="r", slug="s", domain="d",
        question="Q", payload={"b": [3, 1, 2]}, created_utc="2026-07-10T00:00:00+00:00",
    )
    assert ce.sha256_of_bytes(ce._canonical_bytes(e1)) == ce.sha256_of_bytes(ce._canonical_bytes(e2))


def test_legacy_snapshot_registered_and_walkable(tmp_path):
    # a run that only wrote the LEGACY corpus_snapshot.json is still resumable
    (tmp_path / "corpus_snapshot.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
    sha = ce.register_legacy_snapshot(tmp_path, ce.STAGE_S2_SELECT)
    assert len(sha) == 64
    assert ce.present_checkpoint_stages(tmp_path) == [ce.STAGE_S2_SELECT]
    assert ce.resolve_resume_stage(tmp_path) == ce.STAGE_S2_SELECT
