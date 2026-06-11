"""Offline tests for the distill-replay proof harness (I-perm-019 / #1209).

NO live LLM calls: the orchestration test monkeypatches the production
``_run_section`` so the A/B logic + counting + report are exercised
deterministically. The pure helpers are tested directly.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

import scripts.dr_benchmark.offline_distill_replay as harness


class _FakeResult:
    """Lightweight stand-in for a production SectionResult."""

    def __init__(self, verified, dropped, text, *, regen=False, fail=False,
                 in_tok=10, out_tok=20):
        self.sentences_verified = verified
        self.sentences_dropped = dropped
        self.verified_text = text
        self.regen_attempted = regen
        self.dropped_due_to_failure = fail
        self.input_tokens = in_tok
        self.output_tokens = out_tok
        self.error = ""


def _write_pool(tmp_path):
    pool_file = tmp_path / "pool.json"
    pool_file.write_text(json.dumps([
        {"evidence_id": f"ev_{i}", "direct_quote": f"quote {i}", "tier": "T1"}
        for i in range(6)
    ]), encoding="utf-8")
    return pool_file


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def test_load_pool_list_to_dict(tmp_path):
    pool = harness.load_pool(_write_pool(tmp_path))
    assert set(pool) == {f"ev_{i}" for i in range(6)}
    assert pool["ev_0"]["direct_quote"] == "quote 0"


def test_load_pool_fails_loud_on_missing_id(tmp_path):
    pool_file = tmp_path / "bad.json"
    pool_file.write_text(json.dumps([{"direct_quote": "no id"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        harness.load_pool(pool_file)


def test_load_pool_fails_loud_on_empty(tmp_path):
    pool_file = tmp_path / "empty.json"
    pool_file.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(ValueError):
        harness.load_pool(pool_file)


def test_result_metrics_counts():
    m = harness.result_metrics(_FakeResult(40, 41, "one two three four five"))
    assert m["sentences_verified"] == 40
    assert m["sentences_dropped"] == 41
    assert m["total_sentences"] == 81
    assert abs(m["drop_rate"] - 41 / 81) < 1e-9
    assert m["body_words"] == 5


def test_compare_raises_and_lowers():
    legacy = harness.result_metrics(_FakeResult(40, 41, "x"))
    distill = harness.result_metrics(_FakeResult(60, 21, "y"))
    c = harness.compare(legacy, distill)
    assert c["delta_verified"] == 20
    assert c["distill_raises_verified"] is True
    assert c["distill_lowers_drop_rate"] is True


def test_compare_regression_flagged():
    legacy = harness.result_metrics(_FakeResult(40, 41, "x"))
    distill = harness.result_metrics(_FakeResult(30, 51, "y"))
    c = harness.compare(legacy, distill)
    assert c["distill_raises_verified"] is False


# --------------------------------------------------------------------------
# CLI guard: without --live, NEVER touch the live path
# --------------------------------------------------------------------------

def test_main_without_live_makes_no_calls(capsys, monkeypatch):
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("must not run the live A/B without --live")

    monkeypatch.setattr(harness, "run_live_ab", _boom)
    rc = harness.main([])
    assert rc == 0
    assert called["n"] == 0
    assert "--live" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Orchestration: A/B over a mocked _run_section (no LLM), both pass + regression
# --------------------------------------------------------------------------

def _patch_run_section(monkeypatch, *, distill_verified, legacy_verified):
    import src.polaris_graph.generator.multi_section_generator as msg

    def _fake_run_section(section, pool, *, model, temperature,
                          max_tokens_per_section, min_kept_fraction):
        async def _coro():
            on = os.environ.get("PG_SECTION_DISTILL") == "1"
            if on:
                return _FakeResult(distill_verified, 81 - distill_verified,
                                   "distilled verified prose " * distill_verified)
            return _FakeResult(legacy_verified, 81 - legacy_verified,
                               "legacy verified prose " * legacy_verified)
        return _coro()

    monkeypatch.setattr(msg, "_run_section", _fake_run_section, raising=True)


def test_orchestration_pass_when_distill_raises(tmp_path, monkeypatch):
    _patch_run_section(monkeypatch, distill_verified=60, legacy_verified=40)
    args = harness.build_arg_parser().parse_args([
        "--live", "--pool", str(_write_pool(tmp_path)),
        "--max-ev", "5", "--ts", "testts", "--out", str(tmp_path / "out"),
    ])
    rc = asyncio.run(harness.run_live_ab(args))
    assert rc == 0
    report = json.loads((tmp_path / "out" / "replay_testts.json").read_text(encoding="utf-8"))
    assert report["comparison"]["delta_verified"] == 20
    assert report["comparison"]["distill_raises_verified"] is True
    assert report["distill_on"]["sentences_verified"] == 60
    # per-arm verified text dumped for the §-1.1 audit
    assert (tmp_path / "out" / "distill_testts.txt").exists()
    assert (tmp_path / "out" / "legacy_testts.txt").exists()


def test_orchestration_fails_loud_on_regression(tmp_path, monkeypatch):
    _patch_run_section(monkeypatch, distill_verified=30, legacy_verified=40)
    args = harness.build_arg_parser().parse_args([
        "--live", "--pool", str(_write_pool(tmp_path)),
        "--max-ev", "5", "--ts", "regts", "--out", str(tmp_path / "out"),
    ])
    rc = asyncio.run(harness.run_live_ab(args))
    assert rc == 1  # distill LOWERED verified count -> fail loud, nonzero exit


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
