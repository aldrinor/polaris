"""
Regression tests for Gap-4 multi-section generator — deterministic parts only.
LLM calls are exercised by the live run, not these tests.
"""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    SectionResult,
    _merge_bibliographies,
    _parse_outline,
    _remap_section_markers_to_global,
    _ALLOWED_SECTIONS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Outline parser
# ─────────────────────────────────────────────────────────────────────────────


def test_gap4_parse_outline_basic() -> None:
    """BUG-M-203 R4: _parse_outline now returns OutlineParseResult.
    Access .plans for the SectionPlan list."""
    raw = """
    {
      "sections": [
        {"title": "Efficacy",   "focus": "Weight loss results",
         "ev_ids": ["ev_001", "ev_002", "ev_003"]},
        {"title": "Safety",     "focus": "Adverse events",
         "ev_ids": ["ev_004", "ev_005"]},
        {"title": "Regulatory", "focus": "FDA/EMA status",
         "ev_ids": ["ev_006", "ev_007"]}
      ]
    }
    """
    result = _parse_outline(raw)
    assert result.ok is True
    assert len(result.plans) == 3
    assert result.plans[0].title == "Efficacy"
    assert result.plans[0].ev_ids == ["ev_001", "ev_002", "ev_003"]
    assert result.plans[2].title == "Regulatory"


def test_gap4_parse_outline_with_markdown_fence() -> None:
    """Markdown fence stripped; single-section outline is parsed but
    flagged as invalid (section_count_below_min)."""
    raw = """```json
    {"sections": [{"title": "Efficacy", "focus": "x",
                   "ev_ids": ["ev_a", "ev_b"]}]}
    ```"""
    result = _parse_outline(raw)
    assert len(result.plans) == 1
    assert result.plans[0].title == "Efficacy"
    # Only one section → fails validation, caller decides fallback/retry
    assert result.ok is False
    assert "section_count_below_min" in result.reason_codes


def test_gap4_parse_outline_rejects_off_list_title() -> None:
    raw = """
    {"sections": [
        {"title": "Efficacy",  "focus": "x", "ev_ids": ["a", "b"]},
        {"title": "Marketing", "focus": "y", "ev_ids": ["c", "d"]}
    ]}
    """
    result = _parse_outline(raw)
    titles = [p.title for p in result.plans]
    assert "Efficacy" in titles
    assert "Marketing" not in titles


def test_gap4_parse_outline_rejects_singleton_evidence() -> None:
    raw = """
    {"sections": [
        {"title": "Efficacy", "focus": "x", "ev_ids": ["ev_001"]}
    ]}
    """
    result = _parse_outline(raw)
    # Dropped because only 1 ev_id (need >= 2); no plans survive
    assert result.plans == []
    assert result.ok is False


def test_gap4_parse_outline_malformed_returns_empty() -> None:
    assert _parse_outline("").plans == []
    assert _parse_outline("not json").plans == []
    assert _parse_outline("{} no sections").plans == []


# ─────────────────────────────────────────────────────────────────────────────
# Bibliography merge
# ─────────────────────────────────────────────────────────────────────────────


def test_gap4_merge_bibliographies_dedupes_and_renumbers() -> None:
    sec1 = [
        {"num": 1, "evidence_id": "ev_001", "url": "u1",
         "tier": "T1", "statement": "s1"},
        {"num": 2, "evidence_id": "ev_002", "url": "u2",
         "tier": "T2", "statement": "s2"},
    ]
    sec2 = [
        {"num": 1, "evidence_id": "ev_002", "url": "u2",
         "tier": "T2", "statement": "s2"},   # duplicate
        {"num": 2, "evidence_id": "ev_003", "url": "u3",
         "tier": "T1", "statement": "s3"},
    ]
    merged = _merge_bibliographies([sec1, sec2])
    assert len(merged) == 3  # ev_001, ev_002 (deduped), ev_003
    assert merged[0]["num"] == 1
    assert merged[0]["evidence_id"] == "ev_001"
    assert merged[1]["evidence_id"] == "ev_002"
    assert merged[2]["evidence_id"] == "ev_003"


# ─────────────────────────────────────────────────────────────────────────────
# Marker remapping
# ─────────────────────────────────────────────────────────────────────────────


def test_gap4_remap_markers_section_local_to_global() -> None:
    sec = SectionResult(
        title="Efficacy", focus="f", ev_ids_assigned=["ev_a", "ev_b"],
        raw_draft="", rewritten_draft="",
        verified_text="Result was 14.9%[1] and 17.4%[2].",
        biblio_slice=[
            {"num": 1, "evidence_id": "ev_a", "url": "u_a",
             "tier": "T1", "statement": "sa"},
            {"num": 2, "evidence_id": "ev_b", "url": "u_b",
             "tier": "T1", "statement": "sb"},
        ],
        sentences_verified=1, sentences_dropped=0,
        regen_attempted=False, dropped_due_to_failure=False,
    )
    global_biblio = [
        {"num": 1, "evidence_id": "ev_root", "url": "u_r",
         "tier": "T3", "statement": "sr"},
        {"num": 2, "evidence_id": "ev_a",    "url": "u_a",
         "tier": "T1", "statement": "sa"},
        {"num": 3, "evidence_id": "ev_b",    "url": "u_b",
         "tier": "T1", "statement": "sb"},
    ]
    remapped = _remap_section_markers_to_global([sec], global_biblio)
    assert len(remapped) == 1
    # [1] (local = ev_a) should remap to [2] (global);
    # [2] (local = ev_b) should remap to [3] (global)
    assert "[2]" in remapped[0]
    assert "[3]" in remapped[0]
    # The original section-local [1] must be gone
    # (but [2] is both old local and new global → check content)
    assert remapped[0] == "Result was 14.9%[2] and 17.4%[3]."


def test_gap4_remap_skips_unmapped_markers() -> None:
    """If a section references an ev_id not in the global biblio, the
    marker is left unchanged rather than silently remapped wrong."""
    sec = SectionResult(
        title="Efficacy", focus="f", ev_ids_assigned=["ev_x"],
        raw_draft="", rewritten_draft="",
        verified_text="Claim[1].",
        biblio_slice=[
            {"num": 1, "evidence_id": "ev_x", "url": "u_x",
             "tier": "T1", "statement": "sx"},
        ],
        sentences_verified=1, sentences_dropped=0,
        regen_attempted=False, dropped_due_to_failure=False,
    )
    # global biblio does NOT contain ev_x
    global_biblio = [
        {"num": 1, "evidence_id": "ev_other", "url": "u_o",
         "tier": "T1", "statement": "so"},
    ]
    remapped = _remap_section_markers_to_global([sec], global_biblio)
    assert remapped[0] == "Claim[1]."  # unchanged


def test_gap4_allowed_sections_non_empty() -> None:
    assert "Efficacy" in _ALLOWED_SECTIONS
    assert "Safety" in _ALLOWED_SECTIONS
    assert "Regulatory" in _ALLOWED_SECTIONS
    assert len(_ALLOWED_SECTIONS) >= 5
