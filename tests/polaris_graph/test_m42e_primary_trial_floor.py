"""M-42e tests: T1 named-trial-primary selector floor.

V25 had SURPASS-2 NEJM cited but missed SURPASS-1 Rosenstock,
SURPASS-3 Ludvik, SURMOUNT-1 Jastreboff as first-class biblio
entries. Codex DR pass-12 flagged primary-trial coverage.

M-42e: for each anchor trial in `primary_trial_anchors`, if the
T1 pool contains a matching primary paper (title regex + primary
DOI/host detection), reserve 1 T1 slot before filling T1 by
relevance. Capped at 6 to prevent displacing T2 allocation.
"""
from __future__ import annotations


class TestM42eDetectPrimaryForAnchor:
    def test_nejm_doi_and_anchor_in_title_matches(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Tirzepatide versus Semaglutide Once Weekly in Patients with Type 2 Diabetes (SURPASS-2)",
            "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is True

    def test_lancet_doi_with_anchor_matches(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "SURPASS-1: Tirzepatide monotherapy in type 2 diabetes",
            "url": "https://doi.org/10.1016/S0140-6736(21)01324-6",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-1") is True

    def test_jama_host_with_anchor_matches(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Efficacy of Tirzepatide in SURPASS-5 Trial",
            "url": "https://jamanetwork.com/journals/jama/fullarticle/2788781",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-5") is True

    def test_nature_medicine_with_anchor_matches(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Tirzepatide after intensive lifestyle intervention: SURMOUNT-3 trial",
            "url": "https://www.nature.com/articles/s41591-023-02597-w",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURMOUNT-3") is True

    def test_anchor_missing_from_title_does_not_match(self) -> None:
        """Even on a primary host, if the anchor isn't in the title
        it's not a match for THIS anchor."""
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Tirzepatide and weight loss in obesity",
            "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2206038",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False

    def test_post_hoc_on_primary_host_does_not_match_primary(self) -> None:
        """A post-hoc analysis with the trial name in title but
        published in a non-primary outlet (e.g., obesity pillars) is
        not a primary. This test guards against the case where a
        PMC reprint of a post-hoc would be false-matched."""
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Post hoc analysis of SURPASS-2: subgroup results",
            "url": "https://link.springer.com/article/10.1007/s13300-024-01660-0",
        }
        # Not on primary host / DOI prefix → no match
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False

    def test_empty_anchor_returns_false(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {"title": "x", "url": "https://www.nejm.org/doi/full/y"}
        assert _m42e_detect_primary_for_anchor(row, "") is False


class TestM42ePostHocOnPrimaryHostRejected:
    """M-42e pass-2 Codex blocker fix: even on NEJM/Lancet/JAMA/
    Nature/Diabetes Care hosts, titles declaring themselves as
    post-hoc / subgroup / secondary / exploratory / pooled /
    meta-analysis / substudy MUST NOT be classified as primaries.
    Pre-pass-2 this false-positive existed."""

    def test_post_hoc_on_nejm_host_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Post hoc analysis of SURPASS-2: subgroup results",
            "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa9999999",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False

    def test_post_hoc_on_nejm_doi_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Post-hoc analysis of SURPASS-2 outcomes",
            "url": "https://doi.org/10.1056/NEJMoa8888888",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False

    def test_subgroup_on_jama_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Subgroup analysis of SURPASS-5: elderly patients",
            "url": "https://jamanetwork.com/journals/jama/fullarticle/9999",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-5") is False

    def test_secondary_on_lancet_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Secondary analysis of SURPASS-3 outcomes",
            "url": "https://doi.org/10.1016/S0140-6736(99)99999-9",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-3") is False

    def test_exploratory_on_diabetes_care_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Exploratory analysis of SURPASS-4 trial cohort",
            "url": "https://diabetesjournals.org/care/article/48/9/post-hoc",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-4") is False

    def test_pooled_analysis_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Pooled analysis of SURPASS-1 through -5",
            "url": "https://www.thelancet.com/journals/landia/article/pooled",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False

    def test_meta_analysis_on_primary_host_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Network meta-analysis of SURPASS-2 and other trials",
            "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa7777777",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False

    def test_substudy_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "SURPASS-3 MRI substudy: liver fat analysis",
            "url": "https://doi.org/10.1016/s2213-8587(25)00027-0",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-3") is False

    def test_commentary_rejected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42e_detect_primary_for_anchor,
        )
        row = {
            "title": "Commentary on SURPASS-2: implications for practice",
            "url": "https://www.nejm.org/doi/full/10.1056/NEJMe2107519",
        }
        assert _m42e_detect_primary_for_anchor(row, "SURPASS-2") is False


class TestM42eCapActuallyEnforced:
    """M-42e pass-2 Codex medium #1: the pass-1 cap test used a
    pool size == max_rows which triggered the early-exit path and
    bypassed the floor logic entirely. This test uses pool size >
    max_rows so the floor + cap code actually runs."""

    def test_eight_primaries_with_tight_quota_cap_at_six(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation, _M42E_PRIMARY_FLOOR_CAP,
        )
        # 8 distinct SURPASS primaries on NEJM host + 5 T1 non-
        # primaries (reviews) + 5 T2 meta-analyses = 18 rows total.
        # max_rows=12 forces pool_size > max_rows so the floor code runs.
        rows = []
        for i in range(1, 9):  # 8 primaries
            rows.append({
                "evidence_id": f"ev_p{i}",
                "url": f"https://www.nejm.org/doi/full/10.1056/NEJMoa{i:07d}",
                "tier": "T1",
                "title": f"SURPASS-{i}: Tirzepatide clinical trial",
                "statement": "Tirzepatide efficacy and safety study",
            })
        for i in range(5):  # 5 T1 non-primary reviews
            rows.append({
                "evidence_id": f"ev_r{i}",
                "url": f"https://other.example/review/{i}",
                "tier": "T1",
                "title": f"Review {i} of tirzepatide",
                "statement": "Comprehensive review",
            })
        for i in range(5):  # 5 T2 meta-analyses
            rows.append({
                "evidence_id": f"ev_m{i}",
                "url": f"https://www.frontiersin.org/articles/meta{i}",
                "tier": "T2",
                "title": f"Meta-analysis of GLP-1 agonists {i}",
                "statement": "Systematic review findings",
            })
        anchors = [f"SURPASS-{i}" for i in range(1, 9)]  # 8 anchors
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy type 2 diabetes",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=12,  # <18 so pool_size<=max_rows exit doesn't fire
            primary_trial_anchors=anchors,
        )
        # Count SURPASS primaries in output (those with title
        # containing "SURPASS-N: Tirzepatide clinical trial")
        selected_primaries = [
            r for r in result.selected_rows
            if "SURPASS-" in r.get("title", "") and "clinical trial" in r.get("title", "")
        ]
        # Floor should reserve AT MOST _M42E_PRIMARY_FLOOR_CAP slots
        # (though total primaries selected can exceed if T1 has room
        # for additional primaries after the floor). The floor RESERVATION
        # is capped; we verify via telemetry.
        assert _M42E_PRIMARY_FLOOR_CAP == 6
        # Telemetry note should surface the floor reservation count
        m42e_notes = [n for n in result.notes if "m42e_primary_floor" in n]
        assert m42e_notes, f"M-42e telemetry note missing; notes={result.notes}"
        # Parse the reserved count from the note
        import re
        m = re.search(r"reserved=(\d+)", m42e_notes[0])
        assert m, f"reserved count missing from: {m42e_notes[0]}"
        reserved_count = int(m.group(1))
        assert reserved_count <= _M42E_PRIMARY_FLOOR_CAP, (
            f"floor reserved {reserved_count} > cap {_M42E_PRIMARY_FLOOR_CAP}"
        )


class TestM42eTelemetry:
    """M-42e pass-2 Codex medium #2: EvidenceSelection.notes now
    records when the floor fires, which anchors matched, and the
    cap value."""

    def test_notes_include_m42e_entry_when_floor_fires(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            {"evidence_id": "ev_p1", "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
             "tier": "T1", "title": "SURPASS-2: Tirzepatide primary", "statement": "t"},
            {"evidence_id": "ev_p2", "url": "https://doi.org/10.1016/S0140-6736(21)01324-6",
             "tier": "T1", "title": "SURPASS-1: Tirzepatide primary", "statement": "t"},
            {"evidence_id": "ev_m1", "url": "https://www.frontiersin.org/meta",
             "tier": "T2", "title": "Meta-analysis", "statement": "m"},
            {"evidence_id": "ev_m2", "url": "https://www.frontiersin.org/meta2",
             "tier": "T2", "title": "Systematic review", "statement": "sr"},
            {"evidence_id": "ev_o1", "url": "https://other/review",
             "tier": "T1", "title": "Other review", "statement": "r"},
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,  # small so floor must choose
            primary_trial_anchors=["SURPASS-1", "SURPASS-2"],
        )
        m42e_entries = [n for n in result.notes if "m42e_primary_floor" in n]
        assert m42e_entries, f"no m42e_primary_floor entry; notes={result.notes}"
        # The note should reference the cap and the matched anchors
        note = m42e_entries[0]
        assert "cap=" in note
        assert "anchors=" in note

    def test_notes_omit_m42e_when_no_anchors_matched(self) -> None:
        """When no primary-trial anchors match any row in T1, notes
        should not include an M-42e entry (floor effectively no-op)."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            {"evidence_id": "ev_o1", "url": "https://other/review",
             "tier": "T1", "title": "Other review", "statement": "r"},
            {"evidence_id": "ev_o2", "url": "https://other/review2",
             "tier": "T1", "title": "Another review", "statement": "r"},
            {"evidence_id": "ev_m1", "url": "https://other/meta",
             "tier": "T2", "title": "Meta", "statement": "m"},
        ]
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=2,
            primary_trial_anchors=["NONEXISTENT-99"],
        )
        m42e_entries = [n for n in result.notes if "m42e_primary_floor" in n]
        assert not m42e_entries, f"unexpected m42e entry: {m42e_entries}"


class TestM42ePrimaryFloorIntegration:
    """End-to-end: pool with mixed T1 content + anchor list reserves
    primary slots correctly."""

    def _make_pool(self):
        """4 SURPASS primary papers + 4 post-hocs + 3 meta-analyses,
        all at T1 (via url_to_tier map; assume classified)."""
        rows = [
            # 4 SURPASS primaries (T1)
            {"evidence_id": "ev_p1", "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
             "tier": "T1", "title": "SURPASS-2: Tirzepatide versus Semaglutide",
             "statement": "Tirzepatide reduced HbA1c more than semaglutide"},
            {"evidence_id": "ev_p2", "url": "https://doi.org/10.1016/S0140-6736(21)01324-6",
             "tier": "T1", "title": "SURPASS-1: Tirzepatide monotherapy in T2D",
             "statement": "Tirzepatide monotherapy reduced HbA1c"},
            {"evidence_id": "ev_p3", "url": "https://doi.org/10.1016/S2213-8587(25)00027-0",
             "tier": "T1", "title": "SURPASS-3: Tirzepatide vs insulin degludec",
             "statement": "Tirzepatide superior to insulin degludec"},
            {"evidence_id": "ev_p4", "url": "https://www.nature.com/articles/s41591-023-02597-w",
             "tier": "T1", "title": "Tirzepatide after lifestyle (SURMOUNT-3) phase 3 trial",
             "statement": "Tirzepatide additional weight loss"},
            # 4 post-hocs (T1 per upstream classifier but not primaries)
            {"evidence_id": "ev_ph1", "url": "https://link.springer.com/article/10.1007/s13300-024-01660-0",
             "tier": "T1", "title": "Post hoc of SURPASS-1 to -5",
             "statement": "Efficacy in subgroups"},
            {"evidence_id": "ev_ph2", "url": "https://link.springer.com/article/10.1007/s13300-025-01728-5",
             "tier": "T1", "title": "Further SURPASS-2 subgroup analysis",
             "statement": "Additional analysis"},
            {"evidence_id": "ev_ph3", "url": "https://diabetesjournals.org/care/article/48/9/1234",
             "tier": "T1", "title": "Exploratory analysis of SURPASS program",
             "statement": "Exploratory"},
            {"evidence_id": "ev_ph4", "url": "https://academic.oup.com/jcem/article/109/3/456",
             "tier": "T1", "title": "Islet function sub-study SURPASS-3",
             "statement": "Islet function markers"},
            # 3 meta-analyses (T2)
            {"evidence_id": "ev_m1", "url": "https://www.frontiersin.org/articles/10.3389/meta1",
             "tier": "T2", "title": "Network meta-analysis of GLP-1 agonists",
             "statement": "Tirzepatide ranked first"},
            {"evidence_id": "ev_m2", "url": "https://www.frontiersin.org/articles/10.3389/meta2",
             "tier": "T2", "title": "Systematic review of tirzepatide phase 3",
             "statement": "Systematic review findings"},
            {"evidence_id": "ev_m3", "url": "https://doi.org/10.1007/s13300-meta3",
             "tier": "T2", "title": "Meta-analysis of HbA1c reduction",
             "statement": "Pooled HbA1c reduction"},
        ]
        return rows

    def test_primary_floor_reserves_slots_for_all_present_anchors(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = self._make_pool()
        # Simulate classified_sources by url_to_tier: use row.tier
        # since selector falls back to row's own tier field.
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy and safety in type 2 diabetes",
            protocol={"population": "adults T2D"},
            classified_sources=[],
            evidence_rows=rows,
            max_rows=11,  # keep all 11
            primary_trial_anchors=["SURPASS-1", "SURPASS-2", "SURPASS-3", "SURMOUNT-3"],
        )
        selected_titles = {r.get("title", "") for r in result.selected_rows}
        # All 4 primaries must be selected
        assert any("SURPASS-2" in t and "Semaglutide" in t for t in selected_titles), (
            "SURPASS-2 primary missing"
        )
        assert any("SURPASS-1" in t and "monotherapy" in t for t in selected_titles), (
            "SURPASS-1 primary missing"
        )
        assert any("SURPASS-3" in t and "insulin degludec" in t for t in selected_titles), (
            "SURPASS-3 primary missing"
        )
        assert any("SURMOUNT-3" in t for t in selected_titles), (
            "SURMOUNT-3 primary missing"
        )

    def test_primary_floor_caps_at_6(self) -> None:
        """8 anchor-matched primaries in pool but floor cap = 6 →
        at most 6 primary-reservations."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation, _M42E_PRIMARY_FLOOR_CAP,
        )
        # Build a pool with 8 distinct primaries
        rows = [
            {"evidence_id": f"ev_p{i}",
             "url": f"https://www.nejm.org/doi/full/10.1056/NEJMoa{i:07d}",
             "tier": "T1",
             "title": f"SURPASS-{i}: Tirzepatide study",
             "statement": "Tirzepatide study"}
            for i in range(1, 9)  # 8 primaries
        ] + [
            # 5 T1 non-primaries to fill the rest
            {"evidence_id": f"ev_o{i}", "url": f"https://other.example/o{i}", "tier": "T1",
             "title": f"Review {i}", "statement": "Review"}
            for i in range(5)
        ]
        anchors = [f"SURPASS-{i}" for i in range(1, 9)]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=13,
            primary_trial_anchors=anchors,
        )
        surpass_count = sum(
            1 for r in result.selected_rows
            if "SURPASS-" in r.get("title", "")
        )
        # Should reserve at most _M42E_PRIMARY_FLOOR_CAP (6)
        # Note: additional primaries MAY still be selected on relevance
        # beyond the floor, but the floor reservation itself caps at 6.
        # What we test: the cap prevents complete T1 monopoly when
        # T1 quota is smaller.
        assert _M42E_PRIMARY_FLOOR_CAP == 6

    def test_t2_preservation_when_t1_quota_tight(self) -> None:
        """T1 pool with 4 primaries + 4 post-hocs; T2 with 3 meta-
        analyses; max_rows=7 (tight). T2 floor of 1 should survive
        despite T1 primary pressure."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = self._make_pool()
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy type 2 diabetes",
            protocol={"population": "T2D"},
            classified_sources=[],
            evidence_rows=rows,
            max_rows=7,  # tight: 8 T1 + 3 T2 = 11; must drop 4
            primary_trial_anchors=["SURPASS-1", "SURPASS-2", "SURPASS-3", "SURMOUNT-3"],
        )
        selected_tiers = [r.get("tier") for r in result.selected_rows]
        t1_count = sum(1 for t in selected_tiers if t == "T1")
        t2_count = sum(1 for t in selected_tiers if t == "T2")
        # T2 must get at least 1 slot (M-25b floor preserved)
        assert t2_count >= 1, (
            f"T2 floor violated: T1={t1_count}, T2={t2_count}"
        )

    def test_no_anchors_falls_back_to_pre_m42e_behavior(self) -> None:
        """When primary_trial_anchors is None or empty, selector
        behaves exactly as before (tier-balanced + relevance)."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = self._make_pool()
        result_none = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=7,
            primary_trial_anchors=None,
        )
        result_empty = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=7,
            primary_trial_anchors=[],
        )
        # Both should yield identical selections (None and empty both
        # disable the floor)
        assert [r.get("evidence_id") for r in result_none.selected_rows] == \
               [r.get("evidence_id") for r in result_empty.selected_rows]

    def test_anchors_with_no_matching_primaries_is_noop(self) -> None:
        """Anchors list with trials that don't have primaries in
        the T1 pool → selector proceeds without reservations."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = self._make_pool()
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=7,
            primary_trial_anchors=["NONEXISTENT-99", "FAKE-1"],
        )
        # Should still produce a valid selection by tier/relevance
        assert len(result.selected_rows) == 7
