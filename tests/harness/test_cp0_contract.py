"""Offline oracle for the cp0_run_config.json contract — the pinned RunConfig checkpoint every
downstream section + the resume resolver reads (MASTER_EXECUTION_PLAN §1.4 / §5).

Pure on-disk round-trip over tmp_path: build a RunConfig from prompt-parsed + panel layers, write
cp0 through the SHARED checkpoint envelope (block 1), reload + validate it, and prove:
  * cp0 is the hash-chain ROOT (no upstream) and is registered in checkpoint_index.json;
  * the frozen payload shape carries every block + provenance + question_sha + run_config_sha;
  * the envelope pins run_config_sha and refuses on RunConfig drift for an already-run stage;
  * a poisoned payload (a smuggled verdict key) is REFUSED on save (DATA-only, §-1.3);
  * a panel override that beats a parsed value survives the round-trip (precedence disclosure).
No LLM, no network, no production predicate imports beyond the envelope + run_config it exercises.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph import run_config as rc
from src.polaris_graph.generator import checkpoint_envelope as ce


_Q = "What is the evidence base for tirzepatide in adults with type 2 diabetes?"


def _build_cfg():
    # A realistic mix: prompt asked "comprehensive" (WIDE) but the panel pinned an explicit number,
    # and a deliverable tone was parsed from the prompt. Panel must beat parsed (precedence).
    return rc.build_run_config(
        registry=rc.default_registry(),
        env={},
        parsed={"breadth_class": ("WIDE", "comprehensive review"), "query_budget": (60, "at least 60 queries"),
                "tone": ("clinical", "for clinicians")},
        panel={"query_budget": 80},
    )


def test_cp0_round_trip_and_chain_root(tmp_path):
    cfg = _build_cfg()
    path, sha = rc.write_cp0(
        tmp_path, cfg, run_id="run-1", slug="workforce/drb_72", domain="clinical", question=_Q,
    )
    assert path.name == "cp0_run_config.json"

    env = ce.load_checkpoint(tmp_path, ce.STAGE_S0_INTAKE, expected_question_sha=ce.question_sha(_Q))
    assert env["stage"] == ce.STAGE_S0_INTAKE
    assert env["upstream"] is None, "cp0 is the hash-chain root — no upstream"
    assert env["run_config_sha"] == cfg.sha()

    payload = env["payload"]
    assert payload["question_sha"] == ce.question_sha(_Q)
    assert payload["run_config_sha"] == cfg.sha()
    assert set(payload["blocks"]) == rc.ALLOWED_BLOCKS
    assert set(payload["structured"]) == rc.ALLOWED_BLOCKS
    # panel beat parsed for query_budget; provenance discloses the winning layer.
    assert payload["blocks"]["breadth"]["query_budget"] == 80
    assert payload["provenance"]["query_budget"]["source"] == rc.SOURCE_PANEL
    assert payload["provenance"]["breadth_class"]["source"] == rc.SOURCE_PARSED
    assert payload["provenance"]["breadth_class"]["span"] == "comprehensive review"

    # cp0 is in the traceability ledger, as a chain root (upstream_sha None), and the chain validates.
    idx = ce.load_index(tmp_path)
    cp0_rows = [e for e in idx if e["stage"] == ce.STAGE_S0_INTAKE]
    assert len(cp0_rows) == 1 and cp0_rows[0]["upstream_sha"] is None and cp0_rows[0]["sha256"] == sha
    ce.validate_hash_chain(tmp_path)  # does not raise


def test_cp0_pins_run_config_sha_and_refuses_drift(tmp_path):
    cfg = _build_cfg()
    rc.write_cp0(tmp_path, cfg, run_id="run-1", slug="s", domain="d", question=_Q)
    # Resuming a stage under a DIFFERENT run_config_sha must fail loud (drift refusal).
    with pytest.raises(ce.CheckpointEnvelopeError, match="run_config_sha"):
        ce.load_checkpoint(
            tmp_path, ce.STAGE_S0_INTAKE,
            expected_question_sha=ce.question_sha(_Q),
            expected_run_config_sha="deadbeef",
        )


def test_cp0_is_data_only_verdict_key_refused(tmp_path, monkeypatch):
    cfg = _build_cfg()
    # Poison the payload builder to smuggle a verdict key; the envelope must REFUSE on save.
    real_payload = rc.cp0_payload(cfg, _Q)
    real_payload["provenance"]["_leak"] = {"released": True}
    monkeypatch.setattr(rc, "cp0_payload", lambda *_a, **_k: real_payload)
    with pytest.raises(ce.CheckpointEnvelopeError, match="FORBIDDEN verdict key"):
        rc.write_cp0(tmp_path, cfg, run_id="run-1", slug="s", domain="d", question=_Q)


def test_cp0_deterministic_bytes(tmp_path):
    # Same config + pinned timestamp → byte-identical cp0 (cross-core determinism, §5).
    cfg = _build_cfg()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _, sha_a = rc.write_cp0(a, cfg, run_id="r", slug="s", domain="d", question=_Q, created_utc="2026-07-10T00:00:00+00:00")
    _, sha_b = rc.write_cp0(b, cfg, run_id="r", slug="s", domain="d", question=_Q, created_utc="2026-07-10T00:00:00+00:00")
    assert sha_a == sha_b
    assert (a / "cp0_run_config.json").read_bytes() == (b / "cp0_run_config.json").read_bytes()
