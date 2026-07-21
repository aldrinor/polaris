"""Lever 5 (cross-section fact consolidation) — no-rollback runtime guard.

The consolidation machinery itself lives in ``cross_section_repetition_guard`` and is covered by
``test_cross_section_repetition_guard*``. This file adds the Lever-5 contract test: the runtime
no-rollback guard must guarantee the citation multiset is NEVER changed by consolidation (coverage
can never regress), and OFF must stay byte-identical.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from src.polaris_graph.generator.cross_section_repetition_guard import (
    consolidate_cross_section_repetition,
)

_FLAG = "PG_CROSS_SECTION_REPETITION_GUARD"


@dataclass
class _FakeSection:
    title: str
    verified_text: str
    dropped_due_to_failure: bool = False
    is_gap_stub: bool = False


def _cite_multiset(sections: list[_FakeSection]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in sections:
        for mk in re.findall(r"\[\d+\]", s.verified_text):
            counts[mk] = counts.get(mk, 0) + 1
    return counts


def _restated_sections() -> list[_FakeSection]:
    # Same finding restated VERBATIM across two different sections; richest instance ([1][2]) first.
    finding = "Automation could displace 5% of tasks while augmenting many more"
    return [
        _FakeSection("Economic Impact", f"Intro sentence. {finding} [1][2]. Tail one."),
        _FakeSection("Sectoral View", f"Lead in. {finding} [3]. A distinct closing thought [4]."),
    ]


def test_off_is_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_FLAG, raising=False)
    sections = _restated_sections()
    before = [s.verified_text for s in sections]
    telemetry = consolidate_cross_section_repetition(sections)
    assert telemetry == {}
    assert [s.verified_text for s in sections] == before


def test_on_consolidates_and_preserves_every_citation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_FLAG, "1")
    sections = _restated_sections()
    pre = _cite_multiset(sections)
    telemetry = consolidate_cross_section_repetition(sections)
    # A cross-section cluster was consolidated (later instance -> back-reference).
    assert telemetry.get("consolidated", 0) >= 1
    assert not telemetry.get("reverted")
    # NO-ROLLBACK: the citation multiset is unchanged (every [N] still present exactly as often).
    assert _cite_multiset(sections) == pre
    # The distinct closing thought [4] and its citation survive untouched.
    assert "[4]" in sections[1].verified_text
    # The recycled body no longer repeats the finding verbatim (it became a back-reference).
    assert sections[1].verified_text.count("could displace 5% of tasks while augmenting") == 0


def test_no_rollback_guard_reverts_on_citation_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the back-reference ever dropped a citation, the runtime guard must revert to the originals
    rather than ship a coverage loss. We force the failure by monkeypatching the back-reference builder
    to emit a citation-less string, and assert the guard reverts (multiset preserved, output == input)."""
    monkeypatch.setenv(_FLAG, "1")
    import src.polaris_graph.generator.cross_section_repetition_guard as g

    monkeypatch.setattr(g, "_backref_sentence", lambda title, cites: "As noted above.")
    sections = _restated_sections()
    before = [s.verified_text for s in sections]
    pre = _cite_multiset(sections)
    telemetry = consolidate_cross_section_repetition(sections)
    # The guard tripped and reverted: no consolidation shipped, citations intact, text byte-identical.
    assert telemetry.get("reverted") is True
    assert telemetry.get("consolidated", 0) == 0
    assert _cite_multiset(sections) == pre
    assert [s.verified_text for s in sections] == before
