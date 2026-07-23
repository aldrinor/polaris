"""Lever 6 (register translation) — the Limitations prompt and the report preamble.

Both are register translations, with reader-facing prose as the production default.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import multi_section_generator as msg


def test_limitations_prompt_default_is_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_LIMITATIONS_REGISTER", raising=False)
    assert msg._select_limitations_prompt() is msg.LIMITATIONS_SYSTEM_PROMPT_READER


def test_limitations_prompt_pipeline_override_is_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_LIMITATIONS_REGISTER", "pipeline")
    assert msg._select_limitations_prompt() is msg.LIMITATIONS_SYSTEM_PROMPT


@pytest.mark.parametrize("val", ["reader", "1", "on", "true"])
def test_limitations_prompt_on_selects_reader(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("PG_LIMITATIONS_REGISTER", val)
    assert msg._select_limitations_prompt() is msg.LIMITATIONS_SYSTEM_PROMPT_READER


def test_reader_prompt_bans_internal_vocabulary() -> None:
    p = msg.LIMITATIONS_SYSTEM_PROMPT_READER.lower()
    assert "never mention pipeline stages, telemetry, tier labels" in p
    assert "missing internal fields, or corpus percentages" in p
    assert 'Limitations:' in msg.LIMITATIONS_SYSTEM_PROMPT_READER
    assert "contradictions_detected" in msg.LIMITATIONS_SYSTEM_PROMPT_READER


def test_reader_prompt_preserves_the_disclosure_substance() -> None:
    # Register translation, not omission: the working-paper / non-journal caveat is still required.
    p = msg.LIMITATIONS_SYSTEM_PROMPT_READER.lower()
    assert "working paper" in p and "peer-reviewed" in p
