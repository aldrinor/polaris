"""Unit tests for the GH #1258 PART 1 raw launch-log tailer in the run console.

The console (``scripts/run_console/run_console.py``) tails STRUCTURED files. During the long
CPU embedding-rerank + agentic phases the pipeline writes progress ONLY to raw stdout (the
per-run launch log), which the console previously did NOT tail -> the stream went quiet for
minutes. PART 1 adds an incremental byte-offset tailer that emits each NEW line as a
``type:"log"`` SSE event. These tests assert: incremental new-only emission, no dupes, the
per-poll cap, partial-line buffering until newline, and shrink/rotate reset — all on a REAL
fixture file (no mocks of the file IO).
"""
from __future__ import annotations

import asyncio
import importlib
import json

# scripts/ is importable as a namespace package (used the same way by the dr_benchmark suite).
rc = importlib.import_module("scripts.run_console.run_console")


# -- pure tailer: _tail_launch_log ------------------------------------------------------------
def test_tail_emits_only_complete_lines_and_buffers_partial(tmp_path):
    """Complete lines emit; a trailing line with no newline is held in carry until it lands."""
    log = tmp_path / "launch_x.log"
    log.write_text("alpha\nbeta\npartial-no-newline", encoding="utf-8")

    lines, offset, carry = rc._tail_launch_log(log, 0, b"")
    assert lines == ["alpha", "beta"]            # only the two COMPLETE lines
    assert carry == b"partial-no-newline"         # partial held as raw bytes, not emitted
    assert offset == log.stat().st_size

    # The partial line's newline now arrives along with a new line.
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("-now-complete\ngamma\n")
    lines2, offset2, carry2 = rc._tail_launch_log(log, offset, carry)
    assert lines2 == ["partial-no-newline-now-complete", "gamma"]
    assert carry2 == b""
    assert offset2 == log.stat().st_size


def test_tail_no_dupes_across_polls(tmp_path):
    """A second poll with no new bytes emits nothing; only NEW bytes are ever read."""
    log = tmp_path / "launch_x.log"
    log.write_text("one\ntwo\n", encoding="utf-8")
    lines, offset, carry = rc._tail_launch_log(log, 0, b"")
    assert lines == ["one", "two"]

    # No new bytes -> no lines, offset unchanged.
    lines2, offset2, carry2 = rc._tail_launch_log(log, offset, carry)
    assert lines2 == []
    assert offset2 == offset

    # Append one more line -> only that NEW line is emitted (no re-read of one/two).
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("three\n")
    lines3, _, _ = rc._tail_launch_log(log, offset2, carry2)
    assert lines3 == ["three"]


def test_tail_resets_on_shrink_or_rotate(tmp_path):
    """If the file shrinks below the saved offset (rotated/truncated), re-read from the start."""
    log = tmp_path / "launch_x.log"
    log.write_text("aaaa\nbbbb\ncccc\n", encoding="utf-8")
    _, offset, _ = rc._tail_launch_log(log, 0, b"")
    assert offset > 0

    # Rotate: file replaced with a smaller one.
    log.write_text("fresh\n", encoding="utf-8")
    lines, offset2, carry = rc._tail_launch_log(log, offset, b"stale-carry")
    assert lines == ["fresh"]            # re-read from byte 0
    assert offset2 == log.stat().st_size  # offset reset then advanced
    assert carry == b""


def test_tail_strips_cr_for_crlf_lines(tmp_path):
    """Windows CRLF lines emit without the trailing carriage return."""
    log = tmp_path / "launch_x.log"
    log.write_bytes(b"win-line\r\nunix-line\n")
    lines, _, _ = rc._tail_launch_log(log, 0, b"")
    assert lines == ["win-line", "unix-line"]


def test_tail_buffers_multibyte_char_split_across_polls(tmp_path):
    """A UTF-8 char split across a poll boundary is reassembled, not garbled into U+FFFD.

    'é' is 0xC3 0xA9. We write the first byte without its newline, poll (the half-char must be
    held as raw bytes, NOT decoded), then write the second byte + newline and poll again — the
    complete 'café' line must decode correctly with no replacement character.
    """
    log = tmp_path / "launch_x.log"
    log.write_bytes(b"caf\xc3")          # 'caf' + first byte of 'é', no newline
    lines, offset, carry = rc._tail_launch_log(log, 0, b"")
    assert lines == []                    # nothing complete yet
    assert carry == b"caf\xc3"            # raw bytes held (NOT decoded to a U+FFFD)
    assert "�" not in carry.decode("latin-1")  # sanity: no replacement char baked in

    with open(log, "ab") as fh:
        fh.write(b"\xa9\n")               # second byte of 'é' + newline
    lines2, _, carry2 = rc._tail_launch_log(log, offset, carry)
    assert lines2 == ["café"]        # 'café' reassembled cleanly
    assert "�" not in lines2[0]
    assert carry2 == b""


def test_tail_missing_file_is_noop(tmp_path):
    log = tmp_path / "does_not_exist.log"
    lines, offset, carry = rc._tail_launch_log(log, 0, b"")
    assert lines == [] and offset == 0 and carry == b""


# -- launch-log path resolution: _resolve_launch_log ------------------------------------------
def test_resolve_launch_log_primary_sibling(tmp_path, monkeypatch):
    """<root>/launch_<slug>.log is the primary location (sibling of <domain>/<slug>)."""
    root = tmp_path / "runs"
    run_dir = root / "clinical" / "drb_72"
    run_dir.mkdir(parents=True)
    launch = root / "launch_drb_72.log"
    launch.write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(rc, "_RUN_ROOT", root)

    resolved = rc._resolve_launch_log(run_dir)
    assert resolved == launch.resolve()


def test_resolve_launch_log_in_run_fallback(tmp_path, monkeypatch):
    """Falls back to a log redirected INTO the run dir (run.log / stdout.log)."""
    root = tmp_path / "runs"
    run_dir = root / "clinical" / "drb_72"
    run_dir.mkdir(parents=True)
    fallback = run_dir / "run.log"
    fallback.write_text("hi\n", encoding="utf-8")
    monkeypatch.setattr(rc, "_RUN_ROOT", root)

    resolved = rc._resolve_launch_log(run_dir)
    assert resolved == fallback.resolve()


def test_resolve_launch_log_absent_returns_none(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    run_dir = root / "clinical" / "drb_72"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(rc, "_RUN_ROOT", root)
    assert rc._resolve_launch_log(run_dir) is None


# -- end-to-end SSE: _event_stream emits type:"log" events incrementally ----------------------
class _StopDrain(Exception):
    """Sentinel raised from the patched asyncio.sleep to end the infinite poll loop cleanly."""


def _parse_sse(frame: bytes) -> dict:
    return json.loads(frame.decode("utf-8")[len("data: "):].strip())


def _drain(run_dir, monkeypatch, *, polls, append_steps):
    """Drive _event_stream for exactly `polls` poll iterations, returning all emitted events.

    _event_stream emits its FULL batch of frames each poll, THEN ``await asyncio.sleep(...)``.
    We patch that sleep so that on its i-th call we (a) run the next ``append_steps`` mutation
    (so the NEXT poll sees the new bytes) and (b) after the requested number of polls raise a
    sentinel to break the otherwise-infinite loop. Frame-complete + deterministic (no timeouts).
    """
    state = {"i": 0}

    async def _patched_sleep(_secs):
        idx = state["i"]
        state["i"] += 1
        if idx + 1 >= polls:
            raise _StopDrain
        step = append_steps[idx + 1] if (idx + 1) < len(append_steps) else None
        if step is not None:
            step()

    monkeypatch.setattr(rc.asyncio, "sleep", _patched_sleep)

    async def _run():
        events = []
        if append_steps and append_steps[0] is not None:
            append_steps[0]()  # mutate before the FIRST poll
        gen = rc._event_stream(run_dir)
        try:
            async for frame in gen:
                events.append(_parse_sse(frame))
        except _StopDrain:
            pass
        finally:
            await gen.aclose()
        return events

    return asyncio.run(_run())


def test_event_stream_emits_log_events_incrementally(tmp_path, monkeypatch):
    """The SSE stream emits type:"log" events for NEW launch-log lines, with no dupes."""
    monkeypatch.setattr(rc, "POLL_INTERVAL_S", 0.01)
    root = tmp_path / "runs"
    run_dir = root / "clinical" / "drb_72"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(rc, "_RUN_ROOT", root)
    launch = root / "launch_drb_72.log"
    launch.write_text("", encoding="utf-8")

    def append(text):
        with open(launch, "a", encoding="utf-8") as fh:
            fh.write(text)

    events = _drain(
        run_dir,
        monkeypatch,
        polls=3,
        append_steps=[
            lambda: append("STORM round 1/3\nfetching url 1\n"),  # before poll 0
            lambda: append("fetching url 2\nrerank batch 3\n"),    # before poll 1 (mid-stream)
            None,                                                   # before poll 2: nothing new
        ],
    )
    log_texts = [e["text"] for e in events if e.get("type") == "log"]
    # All four lines appear, in order, exactly once (no dupes across polls).
    assert log_texts == [
        "STORM round 1/3",
        "fetching url 1",
        "fetching url 2",
        "rerank batch 3",
    ]


def test_event_stream_caps_log_lines_per_poll(tmp_path, monkeypatch):
    """A burst beyond PG_CONSOLE_MAX_LOG_LINES_PER_POLL is capped + coalesced into one notice."""
    monkeypatch.setattr(rc, "POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(rc, "_MAX_LOG_LINES_PER_POLL", 5)
    root = tmp_path / "runs"
    run_dir = root / "policy" / "burst"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(rc, "_RUN_ROOT", root)
    launch = root / "launch_burst.log"
    launch.write_text("", encoding="utf-8")

    def append_burst():
        with open(launch, "a", encoding="utf-8") as fh:
            fh.write("".join("line %d\n" % i for i in range(20)))

    events = _drain(run_dir, monkeypatch, polls=1, append_steps=[append_burst])
    log_events = [e for e in events if e.get("type") == "log"]
    # 5 capped lines + 1 overflow-notice line = 6 emitted (NOT all 20).
    assert len(log_events) == 6
    assert log_events[-1]["text"].startswith("(+15 more log lines this poll")
    assert log_events[0]["text"] == "line 0"
    assert log_events[4]["text"] == "line 4"


def test_event_stream_no_log_file_no_log_events(tmp_path, monkeypatch):
    """With no launch log present, the stream emits zero type:"log" events (no crash)."""
    monkeypatch.setattr(rc, "POLL_INTERVAL_S", 0.01)
    root = tmp_path / "runs"
    run_dir = root / "tech" / "nolog"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(rc, "_RUN_ROOT", root)

    events = _drain(run_dir, monkeypatch, polls=2, append_steps=[None, None])
    assert [e for e in events if e.get("type") == "log"] == []
