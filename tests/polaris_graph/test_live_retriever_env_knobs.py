"""Regression tests for the env-knob helpers in live_retriever (I-bug-116 / #556).

`_env_float` must reject non-finite overrides (``inf`` / ``-inf`` / ``nan``)
and fall back to the finite default — ``float("inf")`` parses fine and is
``> 0``, but feeding it to ``threading.Thread.join(timeout=...)`` raises
``OverflowError: timestamp out of range for platform time_t`` on Windows.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.live_retriever import _env_float, _env_int

_FLOAT_KNOB = "PG_OPENALEX_ENRICH_DEADLINE"
_INT_KNOB = "PG_OPENALEX_ENRICH_FAILFAST"


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "Infinity", "+inf", "-Infinity"])
def test_env_float_rejects_non_finite(monkeypatch, raw):
    """The #556 bug: a non-finite override must fall back to the default."""
    monkeypatch.setenv(_FLOAT_KNOB, raw)
    assert _env_float(_FLOAT_KNOB, 45.0) == 45.0


@pytest.mark.parametrize("raw,expected", [("30.5", 30.5), ("1", 1.0), ("999.0", 999.0)])
def test_env_float_accepts_finite_positive(monkeypatch, raw, expected):
    monkeypatch.setenv(_FLOAT_KNOB, raw)
    assert _env_float(_FLOAT_KNOB, 45.0) == expected


@pytest.mark.parametrize("raw", ["abc", "", "0", "0.0", "-5", "-0.1"])
def test_env_float_falls_back_on_garbage_or_non_positive(monkeypatch, raw):
    monkeypatch.setenv(_FLOAT_KNOB, raw)
    assert _env_float(_FLOAT_KNOB, 45.0) == 45.0


def test_env_float_default_when_unset(monkeypatch):
    monkeypatch.delenv(_FLOAT_KNOB, raising=False)
    assert _env_float(_FLOAT_KNOB, 45.0) == 45.0


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "abc", "3.5", ""])
def test_env_int_rejects_non_finite_and_non_int(monkeypatch, raw):
    """`_env_int` needs no finiteness guard — ``int("inf")`` / ``int("nan")`` /
    ``int("3.5")`` all raise ``ValueError``, already caught -> default. Pins
    issue #556's claim that ``_env_int`` is unaffected."""
    monkeypatch.setenv(_INT_KNOB, raw)
    assert _env_int(_INT_KNOB, 3) == 3


@pytest.mark.parametrize("raw,expected", [("5", 5), ("1", 1)])
def test_env_int_accepts_finite_positive(monkeypatch, raw, expected):
    monkeypatch.setenv(_INT_KNOB, raw)
    assert _env_int(_INT_KNOB, 3) == expected
