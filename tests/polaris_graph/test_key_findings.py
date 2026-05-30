"""Verified-only extractive Key Findings block (I-meta-002-q1d #949b). NO spend.

Asserts: extractive-only (sentences appear verbatim in section verified_text; citations preserved), dropped
sections excluded, empty input → "" (no heading), bullet cap, default-ON kill-switch.
"""

from __future__ import annotations

from dataclasses import dataclass

import src.polaris_graph.generator.key_findings as kf
from src.polaris_graph.generator.key_findings import build_key_findings, key_findings_enabled


@dataclass
class _Section:
    title: str
    verified_text: str
    dropped_due_to_failure: bool = False


def test_extractive_first_sentence_with_citation_preserved():
    secs = [
        _Section("Efficacy", "Tirzepatide reduced HbA1c by 2.1 percent versus placebo [3]. More prose here [4]."),
        _Section("Safety", "Nausea was the most common adverse event at 12 percent [7]. Second sentence [8]."),
    ]
    out = build_key_findings(secs)
    assert "## Key Findings" in out
    # first verified sentence of each section, verbatim, with its [N] citation
    assert "Tirzepatide reduced HbA1c by 2.1 percent versus placebo [3]." in out
    assert "Nausea was the most common adverse event at 12 percent [7]." in out
    # bold section label
    assert "**Efficacy.**" in out and "**Safety.**" in out
    # only the FIRST sentence per section is lifted (extractive headline, not the whole section)
    assert "More prose here [4]." not in out
    assert "Second sentence [8]." not in out


def test_dropped_and_empty_sections_excluded():
    secs = [
        _Section("Efficacy", "Kept finding [1].", dropped_due_to_failure=False),
        _Section("Safety", "This was dropped [2].", dropped_due_to_failure=True),
        _Section("Regulatory", "   "),  # empty verified_text
    ]
    out = build_key_findings(secs)
    assert "Kept finding [1]." in out
    assert "This was dropped [2]." not in out
    assert "Regulatory" not in out


def test_no_verified_sections_returns_empty_no_heading():
    assert build_key_findings([]) == ""
    assert build_key_findings([_Section("Efficacy", "", dropped_due_to_failure=True)]) == ""
    assert "## Key Findings" not in build_key_findings([_Section("X", "  ")])


def test_bullet_cap():
    secs = [_Section(f"S{i}", f"Finding number {i} here [{i}].") for i in range(12)]
    out = build_key_findings(secs)
    assert out.count("\n- ") == kf._MAX_BULLETS


def test_trailing_citation_form_stays_attached():
    """Codex diff-gate iter-1 P2: a trailing-citation sentence `claim. [1]` keeps its citation with the
    lifted finding (not split into a bare `[1]` second 'sentence')."""
    secs = [_Section("Efficacy", "Tirzepatide reduced HbA1c by 2.1 percent. [3] Follow-on sentence here.")]
    out = build_key_findings(secs)
    assert "Tirzepatide reduced HbA1c by 2.1 percent. [3]" in out
    assert "Follow-on sentence here." not in out


def test_kill_switch(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_KEY_FINDINGS", raising=False)
    assert key_findings_enabled() is True
    secs = [_Section("Efficacy", "Kept finding [1].")]
    assert build_key_findings(secs) != ""
    monkeypatch.setenv("PG_SWEEP_KEY_FINDINGS", "0")
    assert key_findings_enabled() is False
    assert build_key_findings(secs) == ""


def test_extractive_property_every_bullet_sentence_in_some_section():
    """Hard extractive guarantee: every bulleted sentence must appear verbatim in some section's
    verified_text (no synthesized/new claim)."""
    secs = [
        _Section("Efficacy", "Alpha finding [1]. beta."),
        _Section("Safety", "Gamma finding [2]. delta."),
    ]
    out = build_key_findings(secs)
    bodies = " ".join(s.verified_text for s in secs)
    for line in out.splitlines():
        if not line.startswith("- "):
            continue
        # strip the "- **Title.** " prefix → the lifted sentence
        sentence = line.split("** ", 1)[-1] if "**" in line else line[2:]
        assert sentence in bodies, f"non-extractive bullet: {sentence!r} not in any section body"
