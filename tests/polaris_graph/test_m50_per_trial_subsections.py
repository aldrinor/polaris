"""M-50 tests: per-trial subsection generator.

Codex V28 plan pass-2 APPROVED as the 4th BEAT_BOTH target.
Addresses V27 Structural depth LOSE_BOTH: ChatGPT wins via trial
table, Gemini wins via per-trial subsections. M-42b adds the table;
M-50 adds named subsections for T2D-direct primary trials.

Strict gating:
  - ≥2 qualifying primaries (else no subsections emitted)
  - population_scope == "direct" (SURMOUNT-1/3/4 excluded)
  - direct_quote ≥100 chars OR refetched ≥100 chars
  - matching bibliography entry
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    _M50_MIN_PRIMARIES_FOR_SUBSECTIONS,
    _m50_select_candidate_trials,
)


class TestM50CandidateSelection:
    """Unit tests for the candidate-selection helper."""

    def test_two_direct_primaries_with_fat_quotes_qualify(self) -> None:
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2 primary",
                "direct_quote": "x" * 200,
            },
            "ev_s4": {
                "evidence_id": "ev_s4",
                "title": "SURPASS-4 primary",
                "direct_quote": "y" * 200,
            },
        }
        primary_by_anchor = {
            "SURPASS-2": ["ev_s2"],
            "SURPASS-4": ["ev_s4"],
        }
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            {"num": 2, "evidence_id": "ev_s4"},
        ]
        direct = {"SURPASS-2", "SURPASS-4"}
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, direct,
        )
        assert len(candidates) == 2
        anchors = [c[0] for c in candidates]
        assert "SURPASS-2" in anchors
        assert "SURPASS-4" in anchors

    def test_one_primary_below_threshold_returns_empty(self) -> None:
        """Strict gating: 1 primary < 2 minimum → no subsections."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2 primary",
                "direct_quote": "x" * 200,
            },
        }
        primary_by_anchor = {"SURPASS-2": ["ev_s2"]}
        biblio = [{"num": 1, "evidence_id": "ev_s2"}]
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio,
            {"SURPASS-2"},
        )
        assert candidates == []

    def test_indirect_anchor_excluded(self) -> None:
        """SURMOUNT-1 (indirect_for_t2d) must not appear in candidates
        even if it has a fat direct_quote."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2 primary",
                "direct_quote": "x" * 200,
            },
            "ev_sm1": {
                "evidence_id": "ev_sm1",
                "title": "SURMOUNT-1 obesity primary",
                "direct_quote": "y" * 200,
            },
            "ev_sm2": {
                "evidence_id": "ev_sm2",
                "title": "SURMOUNT-2 T2D+obesity primary",
                "direct_quote": "z" * 200,
            },
        }
        primary_by_anchor = {
            "SURPASS-2": ["ev_s2"],
            "SURMOUNT-1": ["ev_sm1"],  # indirect_for_t2d
            "SURMOUNT-2": ["ev_sm2"],  # direct
        }
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            {"num": 2, "evidence_id": "ev_sm1"},
            {"num": 3, "evidence_id": "ev_sm2"},
        ]
        direct = {"SURPASS-2", "SURMOUNT-2"}  # SURMOUNT-1 NOT in direct
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, direct,
        )
        anchors = [c[0] for c in candidates]
        assert "SURPASS-2" in anchors
        assert "SURMOUNT-2" in anchors
        assert "SURMOUNT-1" not in anchors

    def test_thin_quote_excluded(self) -> None:
        """Direct quote <100 chars → row skipped (no subsection)."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2",
                "direct_quote": "short",  # <100
            },
            "ev_s4": {
                "evidence_id": "ev_s4",
                "title": "SURPASS-4",
                "direct_quote": "x" * 200,
            },
        }
        primary_by_anchor = {
            "SURPASS-2": ["ev_s2"],
            "SURPASS-4": ["ev_s4"],
        }
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            {"num": 2, "evidence_id": "ev_s4"},
        ]
        direct = {"SURPASS-2", "SURPASS-4"}
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, direct,
        )
        # Only SURPASS-4 qualifies (fat quote) → 1 candidate <
        # threshold of 2 → empty
        assert candidates == []

    def test_refetched_quote_qualifies(self) -> None:
        """Row with thin direct_quote but fat _m42b_refetched_quote
        should qualify (M-42b pass-2 cache field)."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2",
                "direct_quote": "tiny",
                "_m42b_refetched_quote": "x" * 200,
            },
            "ev_s4": {
                "evidence_id": "ev_s4",
                "title": "SURPASS-4",
                "direct_quote": "y" * 200,
            },
        }
        primary_by_anchor = {
            "SURPASS-2": ["ev_s2"],
            "SURPASS-4": ["ev_s4"],
        }
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            {"num": 2, "evidence_id": "ev_s4"},
        ]
        direct = {"SURPASS-2", "SURPASS-4"}
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, direct,
        )
        anchors = [c[0] for c in candidates]
        assert "SURPASS-2" in anchors
        assert "SURPASS-4" in anchors

    def test_missing_bibliography_entry_excluded(self) -> None:
        """Primary with valid quote but no bibliography entry → not
        included (no valid [N] marker to cite)."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2",
                "direct_quote": "x" * 200,
            },
            "ev_s4": {
                "evidence_id": "ev_s4",
                "title": "SURPASS-4",
                "direct_quote": "y" * 200,
            },
        }
        primary_by_anchor = {
            "SURPASS-2": ["ev_s2"],
            "SURPASS-4": ["ev_s4"],
        }
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            # ev_s4 missing from biblio
        ]
        direct = {"SURPASS-2", "SURPASS-4"}
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, direct,
        )
        # Only SURPASS-2 qualifies → below threshold → empty
        assert candidates == []

    def test_empty_direct_set_returns_empty(self) -> None:
        """No direct anchors configured → no subsections."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2",
                "direct_quote": "x" * 200,
            },
        }
        primary_by_anchor = {"SURPASS-2": ["ev_s2"]}
        biblio = [{"num": 1, "evidence_id": "ev_s2"}]
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, set(),
        )
        assert candidates == []


class TestM50Constants:
    def test_min_primaries_is_2(self) -> None:
        assert _M50_MIN_PRIMARIES_FOR_SUBSECTIONS == 2


class TestM50SubsectionPrompt:
    def test_subsection_prompt_mentions_7_elements(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _M50_SUBSECTION_SYSTEM_PROMPT,
        )
        # All 7 elements named per plan
        for keyword in (
            "sample size", "population", "comparator",
            "primary endpoint", "timepoint", "effect estimate",
            "safety",
        ):
            assert keyword in _M50_SUBSECTION_SYSTEM_PROMPT.lower(), (
                f"{keyword!r} missing from M-50 subsection prompt"
            )

    def test_prompt_enforces_citation_per_claim(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _M50_SUBSECTION_SYSTEM_PROMPT,
        )
        assert "[n] citation" in _M50_SUBSECTION_SYSTEM_PROMPT.lower() or (
            "citation" in _M50_SUBSECTION_SYSTEM_PROMPT.lower()
        )
        assert "no extrapolation" in _M50_SUBSECTION_SYSTEM_PROMPT.lower()

    def test_prompt_uses_placeholders_not_drug_names(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _M50_SUBSECTION_SYSTEM_PROMPT,
        )
        body = _M50_SUBSECTION_SYSTEM_PROMPT.lower()
        # No drug names in the prompt
        banned = ["tirzepatide", "semaglutide", "liraglutide",
                  "dulaglutide", "mounjaro", "zepbound"]
        for b in banned:
            assert b not in body, f"{b!r} leaks into M-50 prompt"
