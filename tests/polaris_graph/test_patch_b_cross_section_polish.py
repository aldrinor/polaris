"""PATCH-B: STORM cross-section polish pass tests.

Closes PG_LB_SA_01 §Risks-line-91 contradiction where a section disclaimed
six safety signals as "not characterized here" while other sections
characterized each of them.

Source pattern: stanford-oval/storm PolishPageModule with
remove_duplicate=True — one LLM call over the full report acting as a
"faithful text editor".
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.polaris_graph.wiki.wiki_composer import _polish_cross_section


def _make_sections_with_contradiction() -> list[dict]:
    """§Risks disclaims DVT; §Pharmacology cites DVT with [15]."""
    return [
        {
            "section_id": "s01",
            "title": "Pharmacology",
            "content": (
                "Semaglutide mechanism [7]. "
                "A reported 266% increase in deep vein thrombosis risk [15]. "
                "Class comparison [8]."
            ),
            "evidence_ids": ["ev_01", "ev_02"],
        },
        {
            "section_id": "s02",
            "title": "Risks",
            "content": (
                "Gastrointestinal events [23]. "
                "Nausea 17% [21]. "
                "Several topics including deep vein thrombosis signals "
                "are not substantiated by the claims available for this "
                "section and are therefore not characterized here."
            ),
            "evidence_ids": ["ev_03"],
        },
    ]


def _make_client_returning(text: str) -> MagicMock:
    client = MagicMock()
    client.generate = AsyncMock(return_value=text)
    return client


# ── Test 1: disclaimer-removal path ───────────────────────────────

def test_polish_removes_contradiction_when_polish_lm_returns_repaired():
    """LLM returns polished text with disclaimer removed; citations preserved."""
    sections = _make_sections_with_contradiction()
    polished_text = (
        "## Pharmacology\n\n"
        "Semaglutide mechanism [7]. "
        "A reported 266% increase in deep vein thrombosis risk [15]. "
        "Class comparison [8].\n\n"
        "## Risks\n\n"
        "Gastrointestinal events [23]. "
        "Nausea 17% [21]."
    )
    client = _make_client_returning(polished_text)
    out = asyncio.run(_polish_cross_section(
        client=client, query="semaglutide risks", sections=sections,
    ))

    # Disclaimer removed from §Risks
    risks_out = next(s for s in out if s["title"] == "Risks")
    assert "not characterized here" not in risks_out["content"]
    # Pharmacology DVT cite preserved
    pharm_out = next(s for s in out if s["title"] == "Pharmacology")
    assert "[15]" in pharm_out["content"]


# ── Test 2: no-defects input is unchanged ─────────────────────────

def test_polish_preserves_sections_when_lm_returns_same_content():
    """LLM returns the exact input → content unchanged, no harm done."""
    sections = [
        {
            "section_id": "s01",
            "title": "A",
            "content": "Claim one [1]. Claim two [2].",
            "evidence_ids": ["ev_a"],
        },
        {
            "section_id": "s02",
            "title": "B",
            "content": "Claim three [3]. Claim four [4].",
            "evidence_ids": ["ev_b"],
        },
    ]
    # LM returns the concatenated input verbatim
    lm_return = "## A\n\nClaim one [1]. Claim two [2].\n\n## B\n\nClaim three [3]. Claim four [4]."
    client = _make_client_returning(lm_return)
    out = asyncio.run(_polish_cross_section(
        client=client, query="x", sections=sections,
    ))
    for orig, polished in zip(sections, out):
        assert polished["content"] == orig["content"]
        # evidence_ids preserved through polish
        assert polished["evidence_ids"] == orig["evidence_ids"]


# ── Test 3: truncated LM output triggers fallback ─────────────────

def test_polish_rejects_truncated_output():
    """If LM output < 50% of input length, fallback to unpolished."""
    sections = [
        {
            "section_id": "s01", "title": "A",
            "content": "Claim " * 100 + "[1].",
            "evidence_ids": [],
        },
        {
            "section_id": "s02", "title": "B",
            "content": "Claim " * 100 + "[2].",
            "evidence_ids": [],
        },
    ]
    client = _make_client_returning("## A\n\n[1]")  # way too short
    out = asyncio.run(_polish_cross_section(
        client=client, query="x", sections=sections,
    ))
    # Original preserved
    assert out == sections


# ── Test 4: dropped citations trigger fallback ────────────────────

def test_polish_rejects_output_that_drops_citations():
    """If LM drops citations that were in the input, reject polish."""
    sections = [
        {
            "section_id": "s01", "title": "A",
            "content": "Claim one [1]. Claim two [2]. Claim three [3].",
            "evidence_ids": [],
        },
        {
            "section_id": "s02", "title": "B",
            "content": "Claim four [4]. Claim five [5].",
            "evidence_ids": [],
        },
    ]
    # LM drops [2] and [5]
    lm_return = "## A\n\nClaim one [1]. Claim three [3].\n\n## B\n\nClaim four [4]."
    client = _make_client_returning(lm_return)
    out = asyncio.run(_polish_cross_section(
        client=client, query="x", sections=sections,
    ))
    # Reject polish → return original
    assert out == sections


# ── Test 5: LM exception triggers fallback ────────────────────────

def test_polish_handles_lm_exception():
    """If the polish LM call raises, return unpolished sections."""
    sections = _make_sections_with_contradiction()
    client = MagicMock()
    client.generate = AsyncMock(side_effect=RuntimeError("LLM down"))
    out = asyncio.run(_polish_cross_section(
        client=client, query="x", sections=sections,
    ))
    assert out == sections


# ── Test 6: single-section input is passed through unchanged ──────

def test_polish_skips_single_section_reports():
    """With only 1 section there's no cross-section defect class — skip."""
    sections = [
        {"section_id": "s01", "title": "A", "content": "Text [1].", "evidence_ids": []},
    ]
    client = MagicMock()
    client.generate = AsyncMock(return_value="should never be called")
    out = asyncio.run(_polish_cross_section(
        client=client, query="x", sections=sections,
    ))
    assert out == sections
    assert client.generate.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
