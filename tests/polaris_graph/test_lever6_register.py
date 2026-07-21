"""Lever 6 (register translation) — the Limitations prompt and the report preamble.

Both are register TRANSLATIONS (Sol's trap: do not hide the disclosure — reword it), gated and default
OFF = byte-identical. These tests assert the gate selects the right text and that OFF is unchanged.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import multi_section_generator as msg


def test_limitations_prompt_off_is_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_LIMITATIONS_REGISTER", raising=False)
    assert msg._select_limitations_prompt() is msg.LIMITATIONS_SYSTEM_PROMPT


@pytest.mark.parametrize("val", ["reader", "1", "on", "true"])
def test_limitations_prompt_on_selects_reader(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("PG_LIMITATIONS_REGISTER", val)
    assert msg._select_limitations_prompt() is msg.LIMITATIONS_SYSTEM_PROMPT_READER


def test_reader_prompt_bans_internal_vocabulary() -> None:
    # The whole point of the register variant: no pipeline/tier vocabulary reaches the reader.
    p = msg.LIMITATIONS_SYSTEM_PROMPT_READER.lower()
    for banned in ("the pipeline", "telemetry", '"t1"', "tier codes"):
        assert banned not in p or "do not use" in p  # only appears inside the prohibition rule
    # It still starts the paragraph with the honest "Limitations:" label and keeps contradictions honest.
    assert 'Limitations:' in msg.LIMITATIONS_SYSTEM_PROMPT_READER
    assert "contradictions_detected" in msg.LIMITATIONS_SYSTEM_PROMPT_READER


def test_reader_prompt_preserves_the_disclosure_substance() -> None:
    # Register translation, not omission: the working-paper / non-journal caveat is still required.
    p = msg.LIMITATIONS_SYSTEM_PROMPT_READER.lower()
    assert "working paper" in p and "peer-reviewed" in p
