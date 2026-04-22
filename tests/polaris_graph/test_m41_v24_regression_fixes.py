"""M-41 tests: post-V24 Codex pass-12 regression fixes.

V24 DR audit (Codex pass 12) verdict: REGRESSED. V24 lost
Regulatory BEAT_ONE -> LOSE_BOTH and Jurisdictional BEAT_ONE ->
LOSE_BOTH because M-40 Mechanism displaced Regulatory in the
5-section outline. M-41 addresses 4 failure modes:

  M-41a: raise outline cap to 6 sections when Mechanism + Regulatory
         both trigger, so Mechanism is additive not substitutive.
  M-41b: drop Trial Summary table rows with >2 dash cells (Codex
         pass-12: "3 rows, 2 mostly empty").
  M-41c: code-level enforcement of the M-38 claim-frame rule —
         drop verified sentences that name a trial by short name
         but carry <3 frame elements.
  M-41d: evidence-selector jurisdictional floor for T3 — reserve one
         slot per present jurisdiction (FDA, EMA, NICE, HC, etc.)
         before filling rest by relevance.
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────
# M-41a: outline cap 5 → 6 when Mechanism + Regulatory trigger
# ─────────────────────────────────────────────────────────────────────


class TestM41aOutlineCap:
    def test_m41a_marker_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "M-41a" in OUTLINE_SYSTEM_PROMPT

    def test_rule_allows_6_sections(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        # Rule must mention 6 explicitly
        assert "6 sections" in OUTLINE_SYSTEM_PROMPT or (
            "6 when" in OUTLINE_SYSTEM_PROMPT
        )

    def test_rule_states_mechanism_is_additive(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        text = OUTLINE_SYSTEM_PROMPT.lower()
        # Must use "additive" or "must not displace" to communicate
        # the structural intent.
        assert "additive" in text or "must not displace" in text

    def test_parser_accepts_6_sections(self) -> None:
        """Parser validation: a 6-section plan (each with >=2 ev_ids)
        must be ok=True."""
        from src.polaris_graph.generator.multi_section_generator import (
            _parse_outline,
        )
        raw = """
        {
            "sections": [
                {"title": "Efficacy", "focus": "f", "ev_ids": ["ev_001","ev_002"]},
                {"title": "Safety", "focus": "f", "ev_ids": ["ev_003","ev_004"]},
                {"title": "Mechanism", "focus": "f", "ev_ids": ["ev_005","ev_006"]},
                {"title": "Comparative", "focus": "f", "ev_ids": ["ev_007","ev_008"]},
                {"title": "Regulatory", "focus": "f", "ev_ids": ["ev_009","ev_010"]},
                {"title": "Dose Response", "focus": "f", "ev_ids": ["ev_011","ev_012"]}
            ]
        }
        """
        result = _parse_outline(raw)
        assert result.ok, f"reasons: {result.reason_codes}"
        assert len(result.plans) == 6

    def test_parser_truncates_7th_section(self) -> None:
        """Parser still enforces the 6-cap — a 7-section plan truncates
        to 6 and flags the violation."""
        from src.polaris_graph.generator.multi_section_generator import (
            _parse_outline,
        )
        raw = """
        {
            "sections": [
                {"title": "Efficacy", "focus": "f", "ev_ids": ["e1","e2"]},
                {"title": "Safety", "focus": "f", "ev_ids": ["e3","e4"]},
                {"title": "Mechanism", "focus": "f", "ev_ids": ["e5","e6"]},
                {"title": "Comparative", "focus": "f", "ev_ids": ["e7","e8"]},
                {"title": "Regulatory", "focus": "f", "ev_ids": ["e9","e10"]},
                {"title": "Dose Response", "focus": "f", "ev_ids": ["e11","e12"]},
                {"title": "Population Subgroups", "focus": "f", "ev_ids": ["e13","e14"]}
            ]
        }
        """
        result = _parse_outline(raw)
        assert len(result.plans) == 6
        assert "section_count_above_max" in result.reason_codes


# ─────────────────────────────────────────────────────────────────────
# M-41b: drop Trial Summary table rows with >2 dashes
# ─────────────────────────────────────────────────────────────────────


class TestM41bThinRowDrop:
    HDR = (
        "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
        "|---|---|---|---|---|---|---|\n"
    )

    def test_row_with_exactly_2_dashes_kept(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _extract_trial_summary_table,
        )
        # Row: 2 dash cells (N and Baseline), 5 real cells.
        raw = (
            self.HDR
            + "| TRIAL-A | — | — | placebo | HbA1c change | −1.5 pp | [1] |"
        )
        table = _extract_trial_summary_table(raw, {1})
        assert "TRIAL-A" in table

    def test_row_with_3_dashes_dropped(self) -> None:
        """V24-style dead row: 'SURPASS-3 | — | — | insulin degludec
        | — | — | [15]' has 4 dash cells. Must be dropped."""
        from src.polaris_graph.generator.multi_section_generator import (
            _extract_trial_summary_table,
        )
        raw = (
            self.HDR
            + "| TRIAL-A | — | — | insulin degludec | — | — | [1] |"
        )
        table = _extract_trial_summary_table(raw, {1})
        # Row dropped → parser collapses to empty (no data rows).
        assert table == ""

    def test_mixed_rows_thin_dropped_rich_kept(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _extract_trial_summary_table,
        )
        raw = (
            self.HDR
            + "| TRIAL-A | 1879 | HbA1c 8.28% | placebo | HbA1c change | −1.5 pp | [1] |\n"
            + "| TRIAL-B | — | — | insulin degludec | — | — | [2] |\n"
            + "| TRIAL-C | 670 | BMI 38 | placebo | weight | −12% | [3] |"
        )
        table = _extract_trial_summary_table(raw, {1, 2, 3})
        assert "TRIAL-A" in table
        assert "TRIAL-B" not in table  # 4-dash row dropped
        assert "TRIAL-C" in table

    def test_row_with_n_a_placeholder_dropped(self) -> None:
        """'N/A' counts as a dash marker for the row-thinness check."""
        from src.polaris_graph.generator.multi_section_generator import (
            _extract_trial_summary_table,
        )
        raw = (
            self.HDR
            + "| TRIAL-A | N/A | N/A | N/A | endpoint | result | [1] |"
        )
        table = _extract_trial_summary_table(raw, {1})
        assert table == ""


# ─────────────────────────────────────────────────────────────────────
# M-41c: claim-frame post-check
# ─────────────────────────────────────────────────────────────────────


class _FakeSentence:
    """Minimal SentenceVerification-shaped object for test."""
    def __init__(self, sentence: str) -> None:
        self.sentence = sentence
        self.is_verified = True


class TestM41cUnderFramedDrop:
    def test_fully_framed_sentence_kept(self) -> None:
        """Sentence with 7/7 frame elements must be kept."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence(
            "In SURPASS-2 (N=1879, baseline HbA1c 8.28%), tirzepatide "
            "15 mg reduced HbA1c by 2.30 pp versus semaglutide 1 mg at "
            "week 40 (p<0.001). [1]"
        )
        kept, dropped = filter_underframed_trial_sentences([s])
        assert len(kept) == 1
        assert len(dropped) == 0

    def test_under_framed_trial_sentence_dropped(self) -> None:
        """Sentence names SURPASS-2 with only effect-direction (1 frame
        element). Must be dropped."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence("SURPASS-2 showed that tirzepatide reduced HbA1c more than semaglutide [1].")
        kept, dropped = filter_underframed_trial_sentences([s])
        assert len(kept) == 0
        assert len(dropped) == 1

    def test_non_trial_sentence_always_kept(self) -> None:
        """Sentences that don't name a trial are kept regardless of
        frame-element count — the rule is scoped to short-name
        attributions."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence("Tirzepatide reduced HbA1c more than placebo [1].")
        kept, dropped = filter_underframed_trial_sentences([s])
        assert len(kept) == 1
        assert len(dropped) == 0

    def test_preceding_sentence_provides_context(self) -> None:
        """Frame elements in the preceding sentence count. A two-
        sentence paragraph where sentence 1 sets up N + baseline and
        sentence 2 names SURPASS-2 + effect at week 40 + p<0.001 is
        valid."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        context = _FakeSentence(
            "A phase-3 trial enrolled N=1879 participants with baseline HbA1c 8.28%."
        )
        named = _FakeSentence(
            "SURPASS-2 at week 40 showed tirzepatide superior versus semaglutide (p<0.001) [1]."
        )
        kept, dropped = filter_underframed_trial_sentences([context, named])
        assert len(kept) == 2

    def test_surmount_variant_dropped_when_thin(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence("SURMOUNT-4 reported maintained weight loss [3].")
        kept, dropped = filter_underframed_trial_sentences([s])
        assert len(kept) == 0
        assert len(dropped) == 1

    def test_all_letter_trial_name_detected(self) -> None:
        """SELECT, LEADER, etc. — all-letters famous names."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence("LEADER showed benefit [5].")
        kept, dropped = filter_underframed_trial_sentences([s])
        assert len(dropped) == 1

    def test_materials_study_pattern_dropped_when_thin(self) -> None:
        """M-41c generalizes beyond clinical. STUDY-A with no framing
        should also drop. (Uses the same regex which matches any
        ALL-CAPS-digit pattern)."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence("TEST-2 reported good performance [2].")
        kept, dropped = filter_underframed_trial_sentences([s])
        # TEST-2 matches the short-name pattern; no frame elements → dropped
        assert len(dropped) == 1

    def test_pass2_standards_codes_not_treated_as_trials(self) -> None:
        """M-41c pass-2 Codex medium #1: standards-body identifiers
        (ISO-9001, IEC-62109, ASTM-D412, IEEE-754) match the hyphen-
        digit pattern but MUST NOT be treated as named trials. Their
        sentences should be kept regardless of frame-element count
        because the rule is scoped to named clinical trials, not
        technical standards."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        cases = [
            "The device was tested per ISO-9001 [1].",
            "Compliance with IEC-62109 was verified [2].",
            "Material properties followed ASTM-D412 [3].",
            "Encoded per IEEE-754 floating-point spec [4].",
            "Per DIN-17100 structural steel standard [5].",
            "ICH-E6 guidelines were followed [6].",
            "NCT-12345678 registered on clinicaltrials.gov [7].",
        ]
        sentences = [_FakeSentence(s) for s in cases]
        kept, dropped = filter_underframed_trial_sentences(sentences)
        # All standards-identifier sentences should be KEPT (not
        # dropped) because they're not named trials.
        assert len(kept) == len(cases), (
            f"Expected {len(cases)} kept, got {len(kept)}; "
            f"wrongly-dropped: {[d.sentence for d in dropped]}"
        )
        assert len(dropped) == 0

    def test_pass2_trial_name_still_detected_alongside_standard(
        self,
    ) -> None:
        """Mixed sentence: contains both a standards code and a trial
        name. The trial name detection should still fire, so the
        under-framed sentence is dropped."""
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence(
            "Following ISO-9001 standards, SURPASS-2 reported benefit [1]."
        )
        kept, dropped = filter_underframed_trial_sentences([s])
        # SURPASS-2 is present + under-framed → drop
        assert len(dropped) == 1

    def test_empty_sentence_passed_through(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            filter_underframed_trial_sentences,
        )
        s = _FakeSentence("")
        kept, dropped = filter_underframed_trial_sentences([s])
        assert len(kept) == 1

    def test_frame_element_count_function(self) -> None:
        """Direct test of the counter — 7 classes max."""
        from src.polaris_graph.generator.multi_section_generator import (
            _m41c_frame_element_count,
        )
        # Sentence with all 7 classes
        all7 = (
            "In SURPASS-2 (N=1879, baseline HbA1c 8.28%), tirzepatide "
            "15 mg reduced HbA1c by 2.30 pp versus semaglutide 1 mg at "
            "week 40 (p<0.001)."
        )
        assert _m41c_frame_element_count(all7) >= 6  # expect 6-7 classes

        empty = "Something happened."
        assert _m41c_frame_element_count(empty) == 0


# ─────────────────────────────────────────────────────────────────────
# M-41d: evidence-selector jurisdictional floor
# ─────────────────────────────────────────────────────────────────────


class TestM41dJurisdictionDetection:
    def test_fda_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({"url": "https://accessdata.fda.gov/labels/foo.pdf"}) == "FDA"
        assert _row_jurisdiction({"url": "https://www.fda.gov/drugs/bar"}) == "FDA"

    def test_ema_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({"url": "https://www.ema.europa.eu/en/documents/assessment"}) == "EMA"

    def test_nice_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({"url": "https://www.nice.org.uk/guidance/ta924"}) == "NICE"

    def test_health_canada_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({"url": "https://pdf.hres.ca/dpd_pm/00073189.pdf"}) == "HC"
        assert _row_jurisdiction({"url": "https://www.canada.ca/health-canada"}) == "HC"

    def test_non_regulatory_host_returns_none(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({"url": "https://nejm.org/article"}) is None
        assert _row_jurisdiction({"url": "https://doi.org/10.1056/NEJMoa123"}) is None

    def test_empty_url_returns_none(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({}) is None
        assert _row_jurisdiction({"url": ""}) is None


class TestM41dJurisdictionalFloor:
    """End-to-end: a T3 pool with mixed jurisdictions + low-scoring HC
    should still yield at least one HC pick in the selection."""

    def _make_rows(self):
        # 12 T3 rows: 6 FDA (high score), 4 EMA (medium), 1 NICE, 1 HC.
        # Relevance: FDA rows are most token-overlapping with query.
        rows = []
        for i in range(6):
            rows.append({
                "evidence_id": f"ev_f{i}",
                "url": f"https://accessdata.fda.gov/lbl/{i}.pdf",
                "tier": "T3",
                "statement": "tirzepatide efficacy safety type 2 diabetes glycemic control weight",
            })
        for i in range(4):
            rows.append({
                "evidence_id": f"ev_e{i}",
                "url": f"https://ema.europa.eu/smpc/{i}",
                "tier": "T3",
                "statement": "tirzepatide efficacy safety type 2 diabetes",
            })
        rows.append({
            "evidence_id": "ev_n0",
            "url": "https://nice.org.uk/ta924",
            "tier": "T3",
            "statement": "tirzepatide NICE appraisal",
        })
        rows.append({
            "evidence_id": "ev_h0",
            "url": "https://pdf.hres.ca/dpd_pm/00073189.pdf",
            "tier": "T3",
            "statement": "product monograph",  # low relevance to query
        })
        return rows

    def test_hc_slot_reserved_when_t3_quota_has_room(self) -> None:
        """T3 quota = 8; jurisdictions present = 4 (FDA/EMA/NICE/HC);
        selector should reserve 1 each before filling by score."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = self._make_rows()
        result = select_evidence_for_generation(
            research_question=(
                "What is the efficacy and safety of tirzepatide for "
                "glycemic control and weight loss in adults with type 2 diabetes?"
            ),
            protocol={"population": "adults T2D"},
            classified_sources=[],
            evidence_rows=rows,
            max_rows=8,  # all 12 won't fit; quota compression forced
        )
        selected_urls = [r.get("url", "") for r in result.selected_rows]
        # Must include at least one from each jurisdiction present
        assert any("fda.gov" in u for u in selected_urls), (
            f"FDA missing from selection: {selected_urls}"
        )
        assert any("ema.europa" in u for u in selected_urls), (
            f"EMA missing from selection: {selected_urls}"
        )
        assert any("nice.org" in u for u in selected_urls), (
            f"NICE missing from selection: {selected_urls}"
        )
        assert any("hres.ca" in u for u in selected_urls), (
            f"Health Canada missing from selection — M-41d intent: {selected_urls}"
        )

    def test_pass2_host_suffix_match_rejects_substring_trick(self) -> None:
        """M-41d pass-2: proper host matching — a URL whose path
        contains `fda.gov` but whose actual host is something else
        must NOT classify as FDA."""
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        # Path contains 'fda.gov' but host is 'not-fda.gov.example'
        assert _row_jurisdiction({
            "url": "https://not-fda.gov.example/some/path/to/fda.gov.pdf"
        }) != "FDA"
        # Malicious lookalike: 'fda-gov.com' host should NOT be FDA
        assert _row_jurisdiction({
            "url": "https://fda-gov.com/label"
        }) != "FDA"

    def test_pass2_proper_subdomain_still_matches(self) -> None:
        """M-41d pass-2: host-suffix match allows real subdomains
        (accessdata.fda.gov is a real FDA subdomain)."""
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        assert _row_jurisdiction({
            "url": "https://accessdata.fda.gov/drugsatfda_docs/label/foo"
        }) == "FDA"
        assert _row_jurisdiction({
            "url": "https://pdf.hres.ca/dpd_pm/00073189.pdf"
        }) == "HC"

    def test_pass2_bare_europa_eu_no_longer_collapses_to_ema(self) -> None:
        """M-41d pass-2: `europa.eu` bare parent was removed; only
        `ema.europa.eu` specifically classifies as EMA."""
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        # Different europa.eu subdomain (e.g. EFSA) should not be EMA
        assert _row_jurisdiction({
            "url": "https://www.efsa.europa.eu/en/opinion/123"
        }) is None
        # EMA itself still classifies
        assert _row_jurisdiction({
            "url": "https://www.ema.europa.eu/en/documents/assessment"
        }) == "EMA"

    def test_no_regression_without_multiple_jurisdictions(self) -> None:
        """If T3 pool has only one jurisdiction, selector behavior
        should match pre-M-41d (pick by relevance). Smoke check."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            {"evidence_id": f"ev_{i}", "url": f"https://accessdata.fda.gov/{i}",
             "tier": "T3", "statement": "tirzepatide efficacy"}
            for i in range(5)
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
        )
        assert len(result.selected_rows) == 3
        assert all("fda.gov" in r.get("url", "") for r in result.selected_rows)
