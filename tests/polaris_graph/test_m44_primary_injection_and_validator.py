"""M-44 tests: scorer/subset primary boost + same-sentence validator.

Codex V28 plan pass-2 APPROVED. V27 failure: primary ev_ids in the
pool but outline planner picked T4 post-hocs / T2 meta-analyses over
T1 primaries for Efficacy/Comparative/Safety/Weight sections.

M-44 implements:
  1. Injection: ensure primary-trial ev_ids appear in every primary-
     eligible section's ev_ids list (Codex acceptance test: "pool has
     SURPASS-2 primary + SURPASS-2 post-hoc + meta-analysis; selected
     subset includes the primary ahead of derivatives").
  2. Same-sentence validator: named-trial tokens in verified prose
     must cite a matching M-42e primary ev_id in the same or
     immediately adjacent sentence.

No LLM calls. Pure logic + fixture data.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _m44_detect_primary_ev_ids,
    _m44_find_trial_mentions,
    _m44_inject_primaries_into_outline,
    _m44_section_is_primary_eligible,
    _m44_sentence_spans,
    _m44_validate_primary_same_sentence,
)


class TestM44SectionEligibility:
    def test_efficacy_eligible(self) -> None:
        assert _m44_section_is_primary_eligible("Efficacy")

    def test_comparative_eligible(self) -> None:
        assert _m44_section_is_primary_eligible("Comparative")

    def test_safety_eligible(self) -> None:
        assert _m44_section_is_primary_eligible("Safety")

    def test_regulatory_not_eligible(self) -> None:
        assert not _m44_section_is_primary_eligible("Regulatory")

    def test_mechanism_not_eligible(self) -> None:
        # Mechanism excluded per plan (M-47 handles mechanism cites)
        assert not _m44_section_is_primary_eligible("Mechanism")

    def test_limitations_not_eligible(self) -> None:
        assert not _m44_section_is_primary_eligible("Limitations")

    def test_weight_loss_eligible_by_token(self) -> None:
        # Custom title with "weight" in name
        assert _m44_section_is_primary_eligible("Weight Loss Outcomes")

    def test_case_insensitive(self) -> None:
        assert _m44_section_is_primary_eligible("efficacy")
        assert _m44_section_is_primary_eligible("EFFICACY")


class TestM44PrimaryDetection:
    def test_detects_primaries_in_pool(self) -> None:
        evidence_pool = {
            "ev_s1": {
                "evidence_id": "ev_s1",
                "source_url": "https://www.nejm.org/doi/10.1056/NEJMoa2107019",
                "title": "SURPASS-1: Tirzepatide monotherapy",
            },
            "ev_s2": {
                "evidence_id": "ev_s2",
                "source_url": "https://www.nejm.org/doi/10.1056/NEJMoa2107519",
                "title": "SURPASS-2: Tirzepatide vs semaglutide",
            },
            "ev_review": {
                "evidence_id": "ev_review",
                "url": "https://example.com/review",
                "title": "Narrative review of GLP-1s",
            },
        }
        result = _m44_detect_primary_ev_ids(
            evidence_pool, ["SURPASS-1", "SURPASS-2", "SURPASS-3"],
        )
        assert result["SURPASS-1"] == ["ev_s1"]
        assert result["SURPASS-2"] == ["ev_s2"]
        # SURPASS-3 has no match — not in dict
        assert "SURPASS-3" not in result

    def test_empty_anchors_returns_empty(self) -> None:
        pool = {"ev_1": {"evidence_id": "ev_1", "title": "x"}}
        assert _m44_detect_primary_ev_ids(pool, []) == {}
        assert _m44_detect_primary_ev_ids(pool, None) == {}


class TestM44InjectionCodexAcceptance:
    """Codex pass-2 verbatim acceptance test."""

    def test_codex_acceptance_primary_prepended_over_derivatives(self) -> None:
        """Pool has SURPASS-2 primary + SURPASS-2 post-hoc + meta-
        analysis. Efficacy section's ev_ids [post-hoc, meta] should
        become [primary, post-hoc, meta] after injection."""
        plans = [
            SectionPlan(
                title="Efficacy",
                focus="tirzepatide HbA1c efficacy",
                ev_ids=["ev_post_hoc", "ev_meta"],
            ),
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_primary"]}
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor,
        )
        assert updated[0].ev_ids[0] == "ev_primary", (
            f"primary not prepended: {updated[0].ev_ids}"
        )
        assert updated[0].ev_ids == ["ev_primary", "ev_post_hoc", "ev_meta"]
        # Injection telemetry recorded
        assert any(
            e["action"] == "injected" and e["ev_id"] == "ev_primary"
            for e in log
        )

    def test_primary_already_present_skipped(self) -> None:
        plans = [
            SectionPlan(
                title="Efficacy", focus="f",
                ev_ids=["ev_primary", "ev_other"],
            ),
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_primary"]}
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor,
        )
        assert updated[0].ev_ids == ["ev_primary", "ev_other"]
        assert any(e["action"] == "already_present" for e in log)

    def test_regulatory_section_not_injected(self) -> None:
        """Regulatory is primary-excluded per plan."""
        plans = [
            SectionPlan(title="Regulatory", focus="f", ev_ids=["ev_fda"]),
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_primary"]}
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor,
        )
        assert updated[0].ev_ids == ["ev_fda"]
        assert not log  # no injection for ineligible section

    def test_mechanism_section_not_injected(self) -> None:
        plans = [
            SectionPlan(title="Mechanism", focus="f", ev_ids=["ev_clamp"]),
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_primary"]}
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor,
        )
        assert updated[0].ev_ids == ["ev_clamp"]
        assert not log

    def test_swap_at_cap(self) -> None:
        """Section at cap must swap lowest-priority for primary."""
        plans = [
            SectionPlan(
                title="Efficacy", focus="f",
                ev_ids=[f"ev_{i}" for i in range(20)],
            ),
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_primary"]}
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor, max_ev_per_section=20,
        )
        # Length unchanged
        assert len(updated[0].ev_ids) == 20
        # Primary in front
        assert updated[0].ev_ids[0] == "ev_primary"
        # ev_19 (last) was swapped
        assert "ev_19" not in updated[0].ev_ids
        assert any(
            e["action"].startswith("swap_in_for_") for e in log
        )

    def test_multi_anchor_multi_section(self) -> None:
        plans = [
            SectionPlan(title="Efficacy", focus="f", ev_ids=["ev_a", "ev_b"]),
            SectionPlan(title="Safety", focus="f", ev_ids=["ev_c", "ev_d"]),
            SectionPlan(title="Regulatory", focus="f", ev_ids=["ev_fda"]),
        ]
        primary_by_anchor = {
            "SURPASS-2": ["ev_s2"],
            "SURPASS-CVOT": ["ev_cvot"],
        }
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor,
        )
        # Efficacy + Safety: both primaries prepended
        assert "ev_s2" in updated[0].ev_ids
        assert "ev_cvot" in updated[0].ev_ids
        assert "ev_s2" in updated[1].ev_ids
        # Regulatory: unchanged
        assert updated[2].ev_ids == ["ev_fda"]


class TestM44TrialMentionDetection:
    def test_finds_named_trial(self) -> None:
        text = "In SURPASS-2, tirzepatide reduced HbA1c."
        matches = _m44_find_trial_mentions(text, ["SURPASS-2"])
        assert len(matches) == 1
        assert matches[0][0] == "SURPASS-2"

    def test_word_boundary_prevents_substring_match(self) -> None:
        # "SURPASS-10" should NOT match "SURPASS-1" anchor — the anchor
        # regex uses lookbehind to require punctuation or whitespace
        # AFTER the anchor.
        text = "SURPASS-10 was a hypothetical trial."
        matches = _m44_find_trial_mentions(text, ["SURPASS-1"])
        assert matches == []

    def test_multi_trial_mentions_detected(self) -> None:
        text = "SURPASS-2 and SURMOUNT-1 were both pivotal."
        matches = _m44_find_trial_mentions(
            text, ["SURPASS-2", "SURMOUNT-1"],
        )
        assert len(matches) == 2

    def test_trial_with_trailing_punctuation(self) -> None:
        text = "SURPASS-2: tirzepatide trial."
        matches = _m44_find_trial_mentions(text, ["SURPASS-2"])
        assert len(matches) == 1


class TestM44SentenceSpans:
    def test_basic_sentences(self) -> None:
        text = "First sentence. Second sentence! Third?"
        spans = _m44_sentence_spans(text)
        assert len(spans) == 3

    def test_no_trailing_punctuation(self) -> None:
        text = "Sentence without terminal punctuation"
        spans = _m44_sentence_spans(text)
        assert len(spans) == 1
        assert spans[0] == (0, len(text))

    def test_empty_text(self) -> None:
        assert _m44_sentence_spans("") == []


class TestM44SameSentenceValidator:
    def test_primary_cited_in_same_sentence_passes(self) -> None:
        text = "In SURPASS-2, tirzepatide reduced HbA1c by 2.30 pp [1]."
        biblio = [
            {"num": 1, "evidence_id": "ev_s2_primary"},
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_s2_primary"]}
        violations = _m44_validate_primary_same_sentence(
            text, primary_by_anchor, biblio,
        )
        assert violations == []

    def test_primary_cited_in_adjacent_sentence_passes(self) -> None:
        text = ("In SURPASS-2, tirzepatide was more effective than "
                "semaglutide. The primary endpoint was HbA1c [1].")
        biblio = [{"num": 1, "evidence_id": "ev_s2_primary"}]
        primary_by_anchor = {"SURPASS-2": ["ev_s2_primary"]}
        violations = _m44_validate_primary_same_sentence(
            text, primary_by_anchor, biblio,
        )
        assert violations == [], (
            f"adjacent-sentence citation should pass: {violations}"
        )

    def test_primary_cited_two_sentences_away_fails(self) -> None:
        text = ("In SURPASS-2, tirzepatide was effective. "
                "Semaglutide was the comparator. "
                "HbA1c was the endpoint [1].")
        biblio = [{"num": 1, "evidence_id": "ev_s2_primary"}]
        primary_by_anchor = {"SURPASS-2": ["ev_s2_primary"]}
        violations = _m44_validate_primary_same_sentence(
            text, primary_by_anchor, biblio,
        )
        assert len(violations) == 1
        assert violations[0]["anchor"] == "SURPASS-2"

    def test_wrong_ev_id_cited_fails(self) -> None:
        text = "In SURPASS-2, tirzepatide reduced HbA1c [5]."
        biblio = [
            {"num": 1, "evidence_id": "ev_s2_primary"},
            {"num": 5, "evidence_id": "ev_post_hoc"},
        ]
        primary_by_anchor = {"SURPASS-2": ["ev_s2_primary"]}
        violations = _m44_validate_primary_same_sentence(
            text, primary_by_anchor, biblio,
        )
        assert len(violations) == 1
        assert "ev_post_hoc" in violations[0]["citations_found"]

    def test_no_trial_mention_no_violation(self) -> None:
        text = "Tirzepatide is an incretin analog [1]."
        biblio = [{"num": 1, "evidence_id": "ev_anything"}]
        primary_by_anchor = {"SURPASS-2": ["ev_s2_primary"]}
        violations = _m44_validate_primary_same_sentence(
            text, primary_by_anchor, biblio,
        )
        assert violations == []

    def test_anchor_with_no_primary_in_pool_skipped(self) -> None:
        """If SURPASS-3 is mentioned but no primary in the pool,
        validator has nothing to enforce."""
        text = "SURPASS-3 was a comparator trial."
        biblio = []
        primary_by_anchor = {"SURPASS-2": ["ev_s2_primary"]}  # no SURPASS-3
        violations = _m44_validate_primary_same_sentence(
            text, primary_by_anchor, biblio,
        )
        assert violations == []
