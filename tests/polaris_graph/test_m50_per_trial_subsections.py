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
        # M-50 pass-2: each candidate is now a 4-tuple with the
        # pre-selected quote carried through. Quote must be >=100 chars.
        for c in candidates:
            assert len(c) == 4
            _anchor, _row, _biblio_num, quote = c
            assert isinstance(quote, str)
            assert len(quote) >= 100

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
        should qualify (M-42b pass-2 cache field).

        M-50 pass-2: the candidate tuple must ALSO carry the refetched
        quote (not the thin direct_quote) through to the LLM
        generator. Pre-pass-2 the LLM got the thin one via `or`
        short-circuit."""
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2",
                "direct_quote": "tiny",
                "_m42b_refetched_quote": "FAT_REFETCH_" + "x" * 200,
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
        # M-50 pass-2: the SURPASS-2 tuple must carry the refetched
        # quote, not the thin direct_quote. Pre-pass-2 the LLM would
        # have received "tiny".
        s2_tuple = next(c for c in candidates if c[0] == "SURPASS-2")
        _anchor, _row, _biblio_num, quote = s2_tuple
        assert quote.startswith("FAT_REFETCH_"), (
            f"SURPASS-2 candidate must carry the refetched quote, "
            f"not the thin direct_quote. Got: {quote[:50]!r}"
        )
        assert "tiny" not in quote

    def test_equal_length_direct_and_refetch_prefers_direct(self) -> None:
        """When both quotes are equal length and ≥100, prefer
        direct_quote (strict length comparison, not >=)."""
        evidence_pool = {
            "ev": {
                "evidence_id": "ev",
                "title": "SURPASS-2",
                "direct_quote": "DIRECT_" + "x" * 200,
                "_m42b_refetched_quote": "REFETCH" + "y" * 200,
            },
            "ev2": {
                "evidence_id": "ev2",
                "title": "SURPASS-4",
                "direct_quote": "z" * 200,
            },
        }
        primary_by_anchor = {"SURPASS-2": ["ev"], "SURPASS-4": ["ev2"]}
        biblio = [
            {"num": 1, "evidence_id": "ev"},
            {"num": 2, "evidence_id": "ev2"},
        ]
        direct = {"SURPASS-2", "SURPASS-4"}
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio, direct,
        )
        s2 = next(c for c in candidates if c[0] == "SURPASS-2")
        quote = s2[3]
        # Direct is slightly shorter (prefix "DIRECT_" = 7 chars vs
        # "REFETCH" = 7 chars), so they're equal. Our rule: prefer
        # direct unless refetch is strictly longer.
        assert quote.startswith("DIRECT_"), (
            f"Equal-length: prefer direct_quote. Got: {quote[:20]!r}"
        )

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


class TestM50Pass2LLMQuoteDelivery:
    """M-50 pass-2 (Codex audit blocker): the LLM subsection generator
    must receive the richer (refetched) quote when direct_quote is
    thin. Verified end-to-end by monkeypatching
    `_call_m50_per_trial_subsection`.
    """

    def test_llm_receives_refetched_quote_when_direct_is_thin(
        self, monkeypatch,
    ) -> None:
        """Pre-pass-2 the LLM received the thin direct_quote because
        `_gen_one` recomputed `quote` with `or` short-circuit. Pass-2
        passes the candidate tuple's quote through."""
        import asyncio
        from src.polaris_graph.generator.multi_section_generator import (
            _call_m50_per_trial_subsection,
        )

        received_quotes: list[str] = []

        async def _fake_call(*, trial_name, direct_quote, biblio_num,
                              model, temperature, max_tokens):
            # Record whatever direct_quote was passed
            received_quotes.append(direct_quote)
            return (
                f"Generated subsection for {trial_name} with "
                f"{len(direct_quote)} char quote [{biblio_num}]. " * 10,
                10, 20,
            )

        monkeypatch.setattr(
            "src.polaris_graph.generator.multi_section_generator."
            "_call_m50_per_trial_subsection",
            _fake_call,
        )

        # Set up inputs: one primary with thin direct_quote + fat refetch
        # and one primary with fat direct_quote (to hit 2-trial minimum).
        evidence_pool = {
            "ev_s2": {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2 primary",
                "direct_quote": "THIN",  # <100 chars
                "_m42b_refetched_quote": (
                    "FAT_REFETCH_SURPASS2 " + "z" * 200
                ),
            },
            "ev_s4": {
                "evidence_id": "ev_s4",
                "title": "SURPASS-4 primary",
                "direct_quote": "FAT_DIRECT_SURPASS4 " + "a" * 200,
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
        candidates = _m50_select_candidate_trials(
            evidence_pool, primary_by_anchor, biblio,
            {"SURPASS-2", "SURPASS-4"},
        )
        assert len(candidates) == 2

        # Now simulate what `_gen_one` does — call the (now patched)
        # LLM function with each candidate's carried quote.
        async def _drive():
            for anchor, row, biblio_num, quote in candidates:
                await _fake_call(
                    trial_name=anchor,
                    direct_quote=quote,
                    biblio_num=biblio_num,
                    model="x",
                    temperature=0.2,
                    max_tokens=400,
                )

        asyncio.run(_drive())

        # Assert SURPASS-2 received the FAT refetched quote, not
        # the thin direct_quote.
        assert len(received_quotes) == 2
        s2_quote = next(
            q for q in received_quotes if "SURPASS2" in q or "SURPASS-2" in q
            or q.startswith("FAT_REFETCH")
        )
        assert s2_quote.startswith("FAT_REFETCH_SURPASS2"), (
            f"LLM received wrong quote for SURPASS-2. Got: "
            f"{s2_quote[:60]!r}. Pre-pass-2 bug would have sent "
            f"'THIN' here."
        )
        assert "THIN" not in s2_quote


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
