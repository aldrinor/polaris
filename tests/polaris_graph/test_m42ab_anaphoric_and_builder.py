"""M-42a+b tests.

M-42a: rule #12c extends M-38/M-41c claim-frame enforcement to
anaphoric ("This trial") and group ("the SURPASS trials")
references.

M-42b: deterministic trial-table + Trial Program Timeline builder
from EvidenceRow.direct_quote. Supersedes M-36 LLM-driven path
when primary-trial evidence is available.
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────
# M-42a: rule #12c in SECTION_SYSTEM_PROMPT_TEMPLATE
# ─────────────────────────────────────────────────────────────────────


class TestM42aRulePresent:
    def test_m42a_marker_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "M-42a" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_title_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "Anaphoric and group claim-frame enforcement" in \
               SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_12c_placed_between_12b_and_tier_discipline(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        i12b = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Claim-frame hard constraint (M-38"
        )
        i12c = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Anaphoric and group claim-frame"
        )
        itier = SECTION_SYSTEM_PROMPT_TEMPLATE.find("EVIDENCE TIER DISCIPLINE")
        assert 0 < i12b < i12c < itier

    def test_rule_names_anaphoric_and_group_bypass_patterns(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Anaphoric and group claim-frame"
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 4000]
        # Anaphoric examples
        assert "This trial" in body
        assert "The same trial" in body or "The study also reported" in body
        # Group examples
        assert "the SURPASS trials" in body or "the phase-3 program" in body

    def test_rule_provides_good_and_bad_examples(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Anaphoric and group claim-frame"
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 4000]
        assert "GOOD" in body
        assert "BAD" in body

    def test_rule_requires_enumeration_or_pooled_frame_for_group(
        self,
    ) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Anaphoric and group claim-frame"
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 4000].lower()
        # Must say "enumerate" or "pooled n"
        assert "enumerate" in body or "pooled n" in body

    def test_template_still_renders_under_format(self) -> None:
        """Non-regression: M-38 pass-2 fix ensured no literal `{...}`
        in the rule body. M-42a rule #12c must also render."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            title="Efficacy", focus="test"
        )
        assert "Efficacy" in prompt
        assert "M-42a" in prompt


# ─────────────────────────────────────────────────────────────────────
# M-42b: deterministic trial-table + timeline builder
# ─────────────────────────────────────────────────────────────────────


class TestM42bExtractFromQuote:
    def test_extract_full_frame(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _m42b_extract_from_quote,
        )
        quote = (
            "In SURPASS-2, 1879 patients with baseline HbA1c 8.28% "
            "were randomized to tirzepatide 15 mg once weekly versus "
            "semaglutide 1 mg. The primary endpoint was HbA1c change at "
            "week 40. Tirzepatide reduced HbA1c by -2.30% (95% CI, "
            "-2.45 to -2.15; p<0.001)."
        )
        cells = _m42b_extract_from_quote(quote)
        assert cells["n"] == "1879"
        assert "8.28" in cells["baseline"]
        assert "semaglutide" in cells["comparator"].lower()
        assert "15 mg" in cells["dose"]
        assert "HbA1c" in cells["endpoint"]
        assert cells["timepoint"] == "40"
        assert "2.30" in cells["effect"] or "-2.30" in cells["effect"]

    def test_extract_partial_frame(self) -> None:
        """Quote with only 3 frame elements → returns those 3, others
        empty."""
        from src.polaris_graph.generator.multi_section_generator import (
            _m42b_extract_from_quote,
        )
        quote = (
            "SURPASS-5 enrolled 475 adults with T2D. Tirzepatide 15 mg "
            "was studied at week 40."
        )
        cells = _m42b_extract_from_quote(quote)
        populated = sum(1 for v in cells.values() if v)
        # N=475, dose=15 mg, timepoint=40 → 3 populated
        assert populated >= 3
        assert cells["n"] == "475"
        assert "15 mg" in cells["dose"]

    def test_extract_empty_quote(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _m42b_extract_from_quote,
        )
        cells = _m42b_extract_from_quote("")
        assert all(v == "" for v in cells.values())


class TestM42bYearExtraction:
    def test_year_from_url(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _m42b_year_from_row,
        )
        row = {"url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2021"}
        # The /2021 at the end is inside the DOI, not the URL year;
        # test both URL and DOI fallback paths separately.
        row_with_year = {"url": "https://example.com/2021/article"}
        assert _m42b_year_from_row(row_with_year) == "2021"

    def test_year_from_quote(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _m42b_year_from_row,
        )
        row = {"url": "https://nonyear.example/path",
               "direct_quote": "Rosenstock et al., 2021, reported..."}
        assert _m42b_year_from_row(row) == "2021"

    def test_no_year_returns_empty(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            _m42b_year_from_row,
        )
        row = {"url": "https://example.com/article",
               "direct_quote": "No date available"}
        assert _m42b_year_from_row(row) == ""


class TestM42bBuilder:
    def test_yields_table_and_timeline_with_2_rows(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )
        selected = [
            {
                "evidence_id": "ev_s2",
                "url": "https://nejm.org/doi/2021/NEJMoa2107519",
                "title": "SURPASS-2: Tirzepatide versus Semaglutide",
                "direct_quote": (
                    "In SURPASS-2, 1879 patients with baseline HbA1c 8.28% "
                    "were randomized to tirzepatide 15 mg once weekly versus "
                    "semaglutide 1 mg. Primary endpoint was HbA1c change at "
                    "week 40. Tirzepatide reduced HbA1c by -2.30% "
                    "(95% CI, -2.45 to -2.15; p<0.001)."
                ),
            },
            {
                "evidence_id": "ev_s3",
                "url": "https://lancet.com/article/2022/surpass3",
                "title": "SURPASS-3: Tirzepatide vs insulin degludec",
                "direct_quote": (
                    "SURPASS-3 enrolled 1444 patients with baseline HbA1c 8.17% "
                    "and randomized to tirzepatide 15 mg once weekly versus "
                    "insulin degludec. Primary endpoint was HbA1c change at "
                    "week 52. Tirzepatide reduced HbA1c by -1.93% "
                    "(95% CI, -2.05 to -1.81; p<0.001)."
                ),
            },
        ]
        biblio = [
            {"num": 1, "evidence_id": "ev_s2",
             "url": "https://nejm.org/doi/2021/NEJMoa2107519"},
            {"num": 2, "evidence_id": "ev_s3",
             "url": "https://lancet.com/article/2022/surpass3"},
        ]
        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=selected,
            primary_trial_anchors=["SURPASS-2", "SURPASS-3"],
            bibliography=biblio,
        )
        # Table: header + separator + 2 data rows = 4 lines
        table_lines = [l for l in table.splitlines() if l.strip()]
        assert len(table_lines) == 4
        assert "SURPASS-2" in table_lines[2]
        assert "SURPASS-3" in table_lines[3]
        # Each row has at least 4 populated cells (not all dashes)
        for row_line in table_lines[2:]:
            cells = [c.strip() for c in row_line.split("|") if c.strip()]
            populated = sum(1 for c in cells if c and c != "—")
            assert populated >= 4, f"row too thin: {row_line}"
        # Timeline present
        timeline_lines = [l for l in timeline.splitlines() if l.strip()]
        assert len(timeline_lines) == 4  # hdr + sep + 2 rows
        assert "2021" in timeline and "2022" in timeline

    def test_thin_quote_without_refetch_returns_empty(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )
        selected = [
            {
                "evidence_id": "ev_s2",
                "url": "https://nejm.org/doi/2021/NEJMoa2107519",
                "title": "SURPASS-2: Tirzepatide versus Semaglutide",
                "direct_quote": "Short.",  # < 100 chars
                "statement": "Also short.",
            }
        ]
        biblio = [{"num": 1, "evidence_id": "ev_s2"}]
        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=selected,
            primary_trial_anchors=["SURPASS-2"],
            bibliography=biblio,
            refetch_fn=None,  # no refetch available
        )
        # Only 1 eligible row but <4 frame elements → table has <2 rows →
        # builder returns empty (LLM fallback expected)
        assert table == ""
        assert timeline == ""

    def test_thin_quote_with_refetch_populates(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )
        selected = [
            {
                "evidence_id": "ev_s2",
                "url": "https://nejm.org/doi/2021/NEJMoa2107519",
                "title": "SURPASS-2: Tirzepatide versus Semaglutide",
                "direct_quote": "Short.",  # thin
            },
            {
                "evidence_id": "ev_s3",
                "url": "https://lancet.com/article/2022/surpass3",
                "title": "SURPASS-3: Tirzepatide vs insulin degludec",
                "direct_quote": (
                    "SURPASS-3 enrolled 1444 patients with baseline HbA1c 8.17% "
                    "and randomized to tirzepatide 15 mg versus insulin "
                    "degludec. Primary endpoint was HbA1c change at week 52. "
                    "Tirzepatide reduced HbA1c by -1.93% (p<0.001)."
                ),
            },
        ]
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            {"num": 2, "evidence_id": "ev_s3"},
        ]

        def fake_refetch(url, max_chars=2000):
            if "2107519" in url:
                return (
                    "In SURPASS-2, 1879 patients with baseline HbA1c 8.28% "
                    "were randomized to tirzepatide 15 mg once weekly versus "
                    "semaglutide 1 mg. Primary endpoint was HbA1c change at "
                    "week 40. Tirzepatide reduced HbA1c by -2.30% "
                    "(95% CI, -2.45 to -2.15; p<0.001)."
                )
            return ""

        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=selected,
            primary_trial_anchors=["SURPASS-2", "SURPASS-3"],
            bibliography=biblio,
            refetch_fn=fake_refetch,
        )
        # Both rows should make it (SURPASS-2 via refetch, SURPASS-3
        # via existing quote)
        assert "SURPASS-2" in table
        assert "SURPASS-3" in table

    def test_invalid_citation_row_dropped(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )
        selected = [
            {
                "evidence_id": "ev_unknown",  # not in biblio
                "url": "https://example.com/unknown",
                "title": "SURPASS-2: Tirzepatide",
                "direct_quote": (
                    "SURPASS-2 had 1879 patients with baseline 8.28% HbA1c "
                    "randomized vs semaglutide 15 mg at week 40 "
                    "(p<0.001)."
                ),
            }
        ]
        biblio = [{"num": 1, "evidence_id": "ev_other"}]
        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=selected,
            primary_trial_anchors=["SURPASS-2"],
            bibliography=biblio,
        )
        # Row has no valid bibliography match → dropped → <2 rows →
        # returns empty
        assert table == ""

    def test_builder_no_anchors_returns_empty(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )
        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=[{"evidence_id": "x"}],
            primary_trial_anchors=[],
            bibliography=[{"num": 1}],
        )
        assert table == ""
        assert timeline == ""


# ─────────────────────────────────────────────────────────────────────
# refetch_for_extraction helper signature
# ─────────────────────────────────────────────────────────────────────


class TestRefetchHelper:
    def test_refetch_exists_in_live_retriever(self) -> None:
        from src.polaris_graph.retrieval.live_retriever import (
            refetch_for_extraction,
        )
        assert callable(refetch_for_extraction)

    def test_refetch_signature(self) -> None:
        """M-42b contract: refetch_for_extraction(url: str,
        max_chars: int = 2000) -> str."""
        import inspect
        from src.polaris_graph.retrieval.live_retriever import (
            refetch_for_extraction,
        )
        sig = inspect.signature(refetch_for_extraction)
        params = list(sig.parameters.keys())
        assert params[0] == "url"
        assert len(params) == 2  # url + max_chars
        assert sig.parameters["max_chars"].default == 2000


# ─────────────────────────────────────────────────────────────────────
# MultiSectionResult schema extension
# ─────────────────────────────────────────────────────────────────────


class TestResultSchemaExtension:
    def test_result_has_trial_timeline_text_field(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            MultiSectionResult,
        )
        r = MultiSectionResult(
            sections=[], outline=[], bibliography=[],
            total_words=0, total_sentences_verified=0,
            total_sentences_dropped=0,
            total_input_tokens=0, total_output_tokens=0,
        )
        assert r.trial_timeline_text == ""

    def test_generate_multi_section_report_accepts_primary_anchors(self) -> None:
        """Signature check: generate_multi_section_report has a
        primary_trial_anchors kwarg with None default."""
        import inspect
        from src.polaris_graph.generator.multi_section_generator import (
            generate_multi_section_report,
        )
        sig = inspect.signature(generate_multi_section_report)
        assert "primary_trial_anchors" in sig.parameters
        assert sig.parameters["primary_trial_anchors"].default is None
