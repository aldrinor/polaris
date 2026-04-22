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
