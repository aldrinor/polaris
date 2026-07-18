"""Prove the deterministic-oracle cassette core in isolation (no live pipeline, no network)."""

from __future__ import annotations

import pytest

from tests.oracle.cassette import Cassette, CassetteError


def _fake_provider(seq):
    """A non-deterministic 'provider': returns the next value each call, ignoring args."""
    it = iter(seq)
    return lambda: next(it)


def test_record_then_replay_is_byte_identical(tmp_path):
    tape = tmp_path / "t.jsonl"
    # RECORD: a run that issues 3 calls (two identical requests + one different).
    prov = _fake_provider(["A1", "A2", "B1"])
    with Cassette(tape, "record") as c:
        r = [c.call("llm", {"p": "same"}, prov),
             c.call("llm", {"p": "same"}, prov),   # identical request -> 2nd response
             c.call("llm", {"p": "other"}, prov)]
    assert r == ["A1", "A2", "B1"]

    # REPLAY: identical request sequence must return identical responses, from tape, no provider.
    boom = _fake_provider([])  # provider must NEVER be called in replay
    with Cassette(tape, "replay") as c:
        r2 = [c.call("llm", {"p": "same"}, boom),
              c.call("llm", {"p": "same"}, boom),
              c.call("llm", {"p": "other"}, boom)]
    assert r2 == ["A1", "A2", "B1"], "replay must reproduce recorded responses in order"


def test_replay_miss_is_a_hard_error(tmp_path):
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake_provider(["X"]))
    # A refactor issues a request the recording never saw -> MISS -> behaviour change.
    # (No context manager here: an in-scenario MISS aborts the run; we don't also want the
    # clean-exit finalize's unused-entry check to fire and mask the MISS under test.)
    c = Cassette(tape, "replay")
    with pytest.raises(CassetteError, match="MISS"):
        c.call("llm", {"p": "NEW"}, _fake_provider(["?"]))


def test_unused_entry_is_a_hard_error(tmp_path):
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake_provider(["X"]))
        c.call("llm", {"p": "y"}, _fake_provider(["Y"]))
    # A refactor that skips the 2nd request -> unused entry at finalize -> behaviour change.
    c = Cassette(tape, "replay")
    c.call("llm", {"p": "x"}, _fake_provider(["?"]))
    with pytest.raises(CassetteError, match="never replayed"):
        c.finalize()


def test_missing_cassette_is_an_error(tmp_path):
    with pytest.raises(CassetteError, match="not found"):
        Cassette(tmp_path / "nope.jsonl", "replay")


def test_invalid_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        Cassette(tmp_path / "t.jsonl", "playback")
