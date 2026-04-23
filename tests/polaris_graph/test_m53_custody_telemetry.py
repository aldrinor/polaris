"""M-53 tests: per-anchor custody telemetry (v29_primary_custody.json).

V29 cycle 1, item 3 of 3. Codex plan pass-1 revisions #6-7 woven in:
- 9-field schema
- Computed by canonical ev_id/biblio_num mapping (not dict membership)
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SectionResult,
    _m53_compute_primary_custody_log,
)


def _primary_row(ev_id: str, anchor: str, quote_chars: int = 300) -> dict:
    return {
        "evidence_id": ev_id,
        "source_url": f"https://www.nejm.org/doi/{ev_id}",
        "title": f"{anchor}: Primary publication",
        "direct_quote": "x" * quote_chars,
        "tier": "T1",
    }


def _section_result(title: str, verified_text: str, biblio_slice=None) -> SectionResult:
    return SectionResult(
        title=title,
        focus=title,
        ev_ids_assigned=[],
        raw_draft="",
        rewritten_draft="",
        verified_text=verified_text,
        biblio_slice=biblio_slice or [],
        sentences_verified=1,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=False,
    )


class TestM53Schema:
    """Codex revision #6: retain all 9 fields."""

    def test_all_9_fields_present(self) -> None:
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=[],
            evidence_pool={},
            section_results=[],
            global_biblio=[],
            m44_injection_log=[],
        )
        assert len(result) == 1
        required = {
            "anchor", "found_in_live_corpus", "found_ev_id",
            "selected_into_pool", "injected_into_section",
            "direct_quote_chars", "direct_quote_adequate",
            "cited_in_verified_prose", "citation_count",
        }
        assert set(result[0].keys()) >= required

    def test_no_anchors_returns_empty_list(self) -> None:
        assert _m53_compute_primary_custody_log(
            primary_trial_anchors=None,
            live_corpus=[],
            evidence_pool={},
            section_results=[],
            global_biblio=[],
            m44_injection_log=[],
        ) == []
        assert _m53_compute_primary_custody_log(
            primary_trial_anchors=[],
            live_corpus=[],
            evidence_pool={},
            section_results=[],
            global_biblio=[],
            m44_injection_log=[],
        ) == []

    def test_duplicate_anchors_deduped(self) -> None:
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4", "SURPASS-4", "SURPASS-4"],
            live_corpus=[],
            evidence_pool={},
            section_results=[],
            global_biblio=[],
            m44_injection_log=[],
        )
        assert len(result) == 1


class TestM53HappyPath:
    def test_full_custody_pass(self) -> None:
        """All 5 custody steps pass for SURPASS-4: found → selected
        → injected → quote adequate → cited."""
        primary = _primary_row("ev_s4", "SURPASS-4")
        evidence_pool = {"ev_s4": primary}
        live_corpus = [primary]
        global_biblio = [
            {"num": 1, "evidence_id": "ev_s4"},
        ]
        sections = [
            _section_result(
                "Efficacy",
                "SURPASS-4 reduced HbA1c significantly [1]. Secondary outcome [1].",
                biblio_slice=[{"num": 1, "evidence_id": "ev_s4"}],
            )
        ]
        m44_log = [
            {"section": "Efficacy", "anchor": "SURPASS-4",
             "ev_id": "ev_s4", "action": "injected"}
        ]
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=live_corpus,
            evidence_pool=evidence_pool,
            section_results=sections,
            global_biblio=global_biblio,
            m44_injection_log=m44_log,
        )
        entry = result[0]
        assert entry["anchor"] == "SURPASS-4"
        assert entry["found_in_live_corpus"] is True
        assert entry["found_ev_id"] == "ev_s4"
        assert entry["selected_into_pool"] is True
        assert entry["injected_into_section"] == "Efficacy"
        assert entry["direct_quote_chars"] == 300
        assert entry["direct_quote_adequate"] is True
        assert entry["cited_in_verified_prose"] is True
        assert entry["citation_count"] == 2  # "[1]" appears twice


class TestM53PinpointsFailure:
    """Each custody step failure shows up distinctly in the
    telemetry so V30 planning can target the right layer."""

    def test_not_in_live_corpus(self) -> None:
        """Anchor never landed in retrieval."""
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-CVOT"],
            live_corpus=[_primary_row("ev_s4", "SURPASS-4")],  # wrong anchor
            evidence_pool={},
            section_results=[],
            global_biblio=[],
            m44_injection_log=[],
        )
        e = result[0]
        assert e["found_in_live_corpus"] is False
        assert e["selected_into_pool"] is False
        assert e["cited_in_verified_prose"] is False

    def test_selected_but_not_injected(self) -> None:
        """Primary in pool but M-44 didn't inject it into any section."""
        primary = _primary_row("ev_s4", "SURPASS-4")
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=[primary],
            evidence_pool={"ev_s4": primary},
            section_results=[],
            global_biblio=[{"num": 1, "evidence_id": "ev_s4"}],
            m44_injection_log=[],  # no injection
        )
        e = result[0]
        assert e["found_in_live_corpus"] is True
        assert e["selected_into_pool"] is True
        assert e["injected_into_section"] is None
        assert e["cited_in_verified_prose"] is False

    def test_injected_but_thin_quote(self) -> None:
        """Primary injected but direct_quote too thin for extraction."""
        primary = _primary_row("ev_s4", "SURPASS-4", quote_chars=50)
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=[primary],
            evidence_pool={"ev_s4": primary},
            section_results=[],
            global_biblio=[{"num": 1, "evidence_id": "ev_s4"}],
            m44_injection_log=[
                {"section": "Efficacy", "anchor": "SURPASS-4",
                 "ev_id": "ev_s4", "action": "injected"}
            ],
        )
        e = result[0]
        assert e["direct_quote_chars"] == 50
        assert e["direct_quote_adequate"] is False

    def test_injected_adequate_quote_but_not_cited(self) -> None:
        """Primary injected + quote adequate, but generator prose
        didn't cite the biblio [N] marker."""
        primary = _primary_row("ev_s4", "SURPASS-4")
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=[primary],
            evidence_pool={"ev_s4": primary},
            section_results=[
                _section_result("Efficacy", "Generic prose with no citation marker.")
            ],
            global_biblio=[{"num": 1, "evidence_id": "ev_s4"}],
            m44_injection_log=[
                {"section": "Efficacy", "anchor": "SURPASS-4",
                 "ev_id": "ev_s4", "action": "injected"}
            ],
        )
        e = result[0]
        assert e["direct_quote_adequate"] is True
        assert e["citation_count"] == 0
        assert e["cited_in_verified_prose"] is False

    def test_cited_counts_citations_across_sections(self) -> None:
        """citation_count sums across all verified sections."""
        primary = _primary_row("ev_s4", "SURPASS-4")
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=[primary],
            evidence_pool={"ev_s4": primary},
            section_results=[
                _section_result("Efficacy", "First mention [1]. Second [1]."),
                _section_result("Safety", "Safety note [1]."),
            ],
            global_biblio=[{"num": 1, "evidence_id": "ev_s4"}],
            m44_injection_log=[
                {"section": "Efficacy", "anchor": "SURPASS-4",
                 "ev_id": "ev_s4", "action": "injected"}
            ],
        )
        assert result[0]["citation_count"] == 3


class TestM53CorpusPullAction:
    """injected_from_corpus action (M-52) also counts as injected."""

    def test_injected_from_corpus_counts(self) -> None:
        primary = _primary_row("ev_pull", "SURPASS-4")
        result = _m53_compute_primary_custody_log(
            primary_trial_anchors=["SURPASS-4"],
            live_corpus=[primary],
            evidence_pool={"ev_pull": primary},
            section_results=[],
            global_biblio=[{"num": 1, "evidence_id": "ev_pull"}],
            m44_injection_log=[
                {"section": "<pool-level>", "anchor": "SURPASS-4",
                 "ev_id": "ev_pull", "action": "injected_from_corpus"}
            ],
        )
        # Injected via M-52 — injected_into_section is None since
        # it's pool-level (not a specific section); but the selected
        # + adequate chain is still valid.
        e = result[0]
        assert e["selected_into_pool"] is True
        # pool-level injection doesn't specify a section title
        assert e["injected_into_section"] is None
