"""Prove the deterministic-oracle cassette core in isolation (no live pipeline, no network)."""

from __future__ import annotations

import pytest

from tests.oracle.cassette import Cassette, CassetteError


def _fake(seq):
    """A non-deterministic 'provider': returns the next value each call, ignoring args."""
    it = iter(seq)
    return lambda: next(it)


def test_record_then_replay_is_byte_identical(tmp_path):
    tape = tmp_path / "t.jsonl"
    prov = _fake(["A1", "A2", "B1"])
    with Cassette(tape, "record") as c:
        r = [c.call("llm", {"p": "same"}, prov, call_id="s0"),
             c.call("llm", {"p": "same"}, prov, call_id="s1"),   # identical request, distinct id
             c.call("llm", {"p": "other"}, prov, call_id="s2")]
    assert r == ["A1", "A2", "B1"]

    boom = _fake([])  # provider must NEVER be called in replay
    with Cassette(tape, "replay") as c:
        r2 = [c.call("llm", {"p": "same"}, boom, call_id="s0"),
              c.call("llm", {"p": "same"}, boom, call_id="s1"),
              c.call("llm", {"p": "other"}, boom, call_id="s2")]
    assert r2 == ["A1", "A2", "B1"], "replay reproduces recorded responses by stable call_id"


def test_stable_id_survives_reordered_replay(tmp_path):
    """The whole point: identical requests replay correctly even if the replay order differs."""
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake(["FIRST"]), call_id="a")
        c.call("llm", {"p": "x"}, _fake(["SECOND"]), call_id="b")
    with Cassette(tape, "replay") as c:  # replay b THEN a — must still map by id, not order
        assert c.call("llm", {"p": "x"}, _fake([]), call_id="b") == "SECOND"
        assert c.call("llm", {"p": "x"}, _fake([]), call_id="a") == "FIRST"


def test_replay_miss_is_a_hard_error(tmp_path):
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake(["X"]), call_id="a")
    c = Cassette(tape, "replay")
    with pytest.raises(CassetteError, match="MISS"):
        c.call("llm", {"p": "NEW"}, _fake(["?"]), call_id="a")


def test_unused_entry_is_a_hard_error(tmp_path):
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake(["X"]), call_id="a")
        c.call("llm", {"p": "y"}, _fake(["Y"]), call_id="b")
    c = Cassette(tape, "replay")
    c.call("llm", {"p": "x"}, _fake(["?"]), call_id="a")
    with pytest.raises(CassetteError, match="never replayed"):
        c.finalize()


def test_duplicate_call_id_rejected_on_record(tmp_path):
    tape = tmp_path / "t.jsonl"
    c = Cassette(tape, "record")
    c.call("llm", {"p": "x"}, _fake(["X"]), call_id="dup")
    with pytest.raises(CassetteError, match="duplicate call_id"):
        c.call("llm", {"p": "x"}, _fake(["Y"]), call_id="dup")


def test_non_native_types_rejected(tmp_path):
    c = Cassette(tmp_path / "t.jsonl", "record")
    with pytest.raises(CassetteError, match="unsupported type"):
        c.call("llm", {"bad": ("a", "tuple")}, _fake(["X"]), call_id="a")  # tuple in args
    with pytest.raises(CassetteError, match="unsupported type"):
        c.call("llm", {"ok": 1}, lambda: {"obj": object()}, call_id="b")   # object in response


def test_call_id_required(tmp_path):
    c = Cassette(tmp_path / "t.jsonl", "record")
    with pytest.raises(CassetteError, match="call_id"):
        c.call("llm", {"p": "x"}, _fake(["X"]), call_id="")


def test_tampered_request_field_detected_on_load(tmp_path):
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake(["X"]), call_id="a")
    # corrupt a REQUEST field (call_id) without recomputing the key -> key mismatch on load.
    # (The key identifies the request; a stored request field that disagrees with the key = corrupt.)
    lines = tape.read_text().splitlines()
    lines[1] = lines[1].replace('"call_id":"a"', '"call_id":"b"')
    tape.write_text("\n".join(lines) + "\n")
    with pytest.raises(CassetteError, match="key mismatch"):
        Cassette(tape, "replay")


def test_replay_is_exactly_once(tmp_path):
    tape = tmp_path / "t.jsonl"
    with Cassette(tape, "record") as c:
        c.call("llm", {"p": "x"}, _fake(["X"]), call_id="a")
    c = Cassette(tape, "replay")
    assert c.call("llm", {"p": "x"}, _fake([]), call_id="a") == "X"
    with pytest.raises(CassetteError, match="REUSE"):  # a 2nd identical call = an extra request
        c.call("llm", {"p": "x"}, _fake([]), call_id="a")


def test_finalize_is_terminal(tmp_path):
    tape = tmp_path / "t.jsonl"
    c = Cassette(tape, "record")
    c.call("llm", {"p": "x"}, _fake(["X"]), call_id="a")
    c.finalize()
    with pytest.raises(CassetteError, match="finalized"):
        c.call("llm", {"p": "y"}, _fake(["Y"]), call_id="b")


def test_missing_cassette_is_an_error(tmp_path):
    with pytest.raises(CassetteError, match="not found"):
        Cassette(tmp_path / "nope.jsonl", "replay")


def test_record_returns_canonical_copy_symmetric_with_replay(tmp_path):
    tape = tmp_path / "t.jsonl"
    live_obj = {"content": "hi", "n": 1}
    with Cassette(tape, "record") as c:
        got = c.call("llm", {"p": "x"}, lambda: live_obj, call_id="a")
    assert got == live_obj and got is not live_obj, "record returns a fresh copy, not the live object"
    got["content"] = "MUT"  # mutating the returned value must not corrupt the tape
    with Cassette(tape, "replay") as c:
        rep = c.call("llm", {"p": "x"}, _fake([]), call_id="a")
    assert rep == {"content": "hi", "n": 1}, "replay unaffected by mutation of record's return"
