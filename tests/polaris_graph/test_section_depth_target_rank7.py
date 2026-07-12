"""Rank7: the section-writer DEPTH TARGET lever (PG_SECTION_SENTENCE_TARGET / _DISTINCT_SOURCES).

Report length on the multi_section_generator path is EMERGENT, not governed: PG_TARGET_TOTAL_WORDS
and the expansion machinery live in agents/synthesizer.py + synthesis/section_writer.py, which this
module never imports. Length = n_sections x rule-#8's sentence target x ~30 w/sentence. These tests
lock the two properties that make the lever trustworthy:

  1. UNSET => the original template OBJECT is returned (byte-identical; the locked benchmark moves
     only when someone opts in).
  2. SET => the rewrite fires on BOTH templates and leaves NO stale "10-18" anywhere. Editing only
     one of the two templates, or leaving the Mechanism rule's back-reference to rule #8 pointing at
     the old band, is a silent no-op / self-contradicting prompt — the exact failure that killed the
     previous cycle's fix.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import multi_section_generator as M

TARGET_ENV = "PG_SECTION_SENTENCE_TARGET"
SOURCES_ENV = "PG_SECTION_DISTINCT_SOURCES"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TARGET_ENV, raising=False)
    monkeypatch.delenv(SOURCES_ENV, raising=False)


@pytest.mark.parametrize("field_agnostic", [False, True])
def test_unset_is_byte_identical(field_agnostic: bool) -> None:
    """Default OFF must return the SAME OBJECT, not an equal copy."""
    expected = (
        M.SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC
        if field_agnostic
        else M.SECTION_SYSTEM_PROMPT_TEMPLATE
    )
    assert M._select_section_system_prompt(field_agnostic) is expected


@pytest.mark.parametrize("field_agnostic", [False, True])
def test_target_fires_on_both_templates(
    monkeypatch: pytest.MonkeyPatch, field_agnostic: bool
) -> None:
    """The 50%-no-op trap: the rewrite must fire on the clinical AND field-agnostic template."""
    monkeypatch.setenv(TARGET_ENV, "28-36")
    monkeypatch.setenv(SOURCES_ENV, "15")
    out = M._select_section_system_prompt(field_agnostic)
    assert "Target 28-36 sentences" in out
    assert "at least 15 DISTINCT sources" in out


@pytest.mark.parametrize("field_agnostic", [False, True])
def test_no_stale_band_survives(monkeypatch: pytest.MonkeyPatch, field_agnostic: bool) -> None:
    """A surviving '10-18' would contradict the new target (the Mechanism rule back-references it)."""
    monkeypatch.setenv(TARGET_ENV, "28-36")
    assert "10-18" not in M._select_section_system_prompt(field_agnostic)


def test_either_knob_alone_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SOURCES_ENV, "15")
    out = M._select_section_system_prompt(True)
    assert "at least 15 DISTINCT sources" in out
    assert "Target 10-18 sentences" in out  # untouched knob keeps its default band


def test_drifted_anchor_fails_loud() -> None:
    """A template edit must BREAK this lever, never silently disable it."""
    import os

    os.environ[TARGET_ENV] = "28-36"
    try:
        with pytest.raises(RuntimeError, match="anchor"):
            M._apply_depth_targets("a template with no rule #8 anchor at all")
    finally:
        os.environ.pop(TARGET_ENV, None)


def test_anti_verbosity_and_depth_target_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The concise variant STRIPS rule #8's target; the depth target RAISES it. Refuse both."""
    monkeypatch.setenv(TARGET_ENV, "28-36")
    with pytest.raises(RuntimeError, match="mutually exclusive"):
        M._select_section_system_prompt(True, anti_verbosity=True)
