"""M-42d tests: Health Canada T3 quota expansion + preservation guard.

Codex pass-3 approved plan: HC jurisdiction quota expands from 1 slot
(M-41d baseline) to 2 slots (M-42d default). Preservation guard: HC's
2nd slot ONLY fires after every present jurisdiction has its 1st slot
reservation, so FDA/EMA/NICE/MHRA are never displaced.

Env override: `PG_M41D_HC_QUOTA` (default 2). Setting to 1 restores
exact M-41d behavior. Setting to N reserves up to N HC slots when the
pool has >=N HC rows.
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────
# Quota helper
# ─────────────────────────────────────────────────────────────────────


class TestHcQuotaHelper:
    def test_default_hc_quota_is_2(self, monkeypatch) -> None:
        monkeypatch.delenv("PG_M41D_HC_QUOTA", raising=False)
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42d_hc_quota,
        )
        assert _m42d_hc_quota() == 2

    def test_env_override_raises_quota(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "3")
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42d_hc_quota,
        )
        assert _m42d_hc_quota() == 3

    def test_env_override_clamps_below_1(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "0")
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42d_hc_quota,
        )
        assert _m42d_hc_quota() == 1

    def test_invalid_env_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "abc")
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42d_hc_quota,
        )
        assert _m42d_hc_quota() == 2


# ─────────────────────────────────────────────────────────────────────
# HC jurisdiction detection via hpfb-dgpsa.ca (new suffix)
# ─────────────────────────────────────────────────────────────────────


class TestHcHostSuffixDhpp:
    def test_hpfb_dgpsa_ca_maps_to_hc(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        row = {"url": "https://dhpp.hpfb-dgpsa.ca/db/product_search/"}
        assert _row_jurisdiction(row) == "HC"

    def test_hpfb_dgpsa_ca_apex_maps_to_hc(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        row = {"url": "https://hpfb-dgpsa.ca/some/path"}
        assert _row_jurisdiction(row) == "HC"

    def test_canada_subdomains_still_match(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        for url in (
            "https://recalls-rappels.canada.ca/en/alert/2024-05",
            "https://health-products.canada.ca/dpd-bdpp/info.do",
            "https://pdf.hres.ca/dpd_pm/00012345.PDF",
        ):
            assert _row_jurisdiction({"url": url}) == "HC"


# ─────────────────────────────────────────────────────────────────────
# Quota expansion behavior
# ─────────────────────────────────────────────────────────────────────


def _make_t3_row(evidence_id: str, url: str, score_hint: str) -> dict:
    """Create a T3 evidence row for testing. score_hint seeds title for
    deterministic ordering."""
    return {
        "evidence_id": evidence_id,
        "url": url,
        "source_url": url,
        "tier": "T3",
        "title": f"Regulatory monograph {score_hint}",
        "statement": (
            f"Indication and safety labeling for tirzepatide; "
            f"regulatory content {score_hint}"
        ),
    }


class TestHcQuotaExpansion:
    def test_hc_expands_to_2_when_pool_has_3_hc(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "2")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            # 3 HC + 2 FDA + 2 EMA. Pool = 7, all T3.
            _make_t3_row("hc1", "https://pdf.hres.ca/dpd/00001.pdf", "hc1"),
            _make_t3_row("hc2", "https://recalls-rappels.canada.ca/1", "hc2"),
            _make_t3_row("hc3", "https://dhpp.hpfb-dgpsa.ca/db/1", "hc3"),
            _make_t3_row("fda1", "https://accessdata.fda.gov/drugsatfda/1", "f1"),
            _make_t3_row("fda2", "https://www.fda.gov/safety/notice/1", "f2"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/en/doc/1", "e1"),
            _make_t3_row("ema2", "https://www.ema.europa.eu/en/doc/2", "e2"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory labeling t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            # max_rows < pool to force T3 floor block (avoid
            # pool_size<=max_rows short-circuit).
            max_rows=5,
        )
        # 5 slots; expected: 1 HC + 1 FDA + 1 EMA reserved +
        # 1 HC expansion + 1 fill-by-relevance = 5.
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )
        jur_counts: dict = {}
        for r in result.selected_rows:
            j = _row_jurisdiction(r)
            if j:
                jur_counts[j] = jur_counts.get(j, 0) + 1
        assert jur_counts.get("HC", 0) >= 2, (
            f"HC did not expand to 2. jur_counts={jur_counts}"
        )

    def test_hc_stays_at_1_when_pool_has_1_hc(self, monkeypatch) -> None:
        """Expansion cannot exceed pool size."""
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "2")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation, _row_jurisdiction,
        )
        rows = [
            _make_t3_row("hc1", "https://pdf.hres.ca/dpd/1.pdf", "h1"),
            _make_t3_row("fda1", "https://accessdata.fda.gov/1", "f1"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/doc/1", "e1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
        )
        jur_counts: dict = {}
        for r in result.selected_rows:
            j = _row_jurisdiction(r)
            if j:
                jur_counts[j] = jur_counts.get(j, 0) + 1
        assert jur_counts.get("HC", 0) == 1

    def test_fda_ema_nice_first_slots_preserved(self, monkeypatch) -> None:
        """Preservation guard: every present jurisdiction gets its 1st
        slot before HC's 2nd slot is reserved."""
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "2")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation, _row_jurisdiction,
        )
        rows = [
            # 3 HC + 1 FDA + 1 EMA + 1 NICE.
            # With quota 4: even if HC ranks high, FDA/EMA/NICE each get 1
            # BEFORE HC's 2nd slot. Outcome: 1 FDA + 1 EMA + 1 NICE + 1 HC
            # (HC 2nd can't fit since all 4 slots consumed by 4 present juris).
            _make_t3_row("hc1", "https://pdf.hres.ca/1.pdf", "hc1"),
            _make_t3_row("hc2", "https://canada.ca/en/recall/2", "hc2"),
            _make_t3_row("hc3", "https://dhpp.hpfb-dgpsa.ca/3", "hc3"),
            _make_t3_row("fda1", "https://accessdata.fda.gov/1", "f1"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/1", "e1"),
            _make_t3_row("nice1", "https://www.nice.org.uk/ta/1", "n1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=4,
        )
        jur_counts: dict = {}
        for r in result.selected_rows:
            j = _row_jurisdiction(r)
            if j:
                jur_counts[j] = jur_counts.get(j, 0) + 1
        # All 4 jurisdictions get >=1 slot. HC 2nd slot can't fit.
        assert jur_counts.get("FDA", 0) >= 1, jur_counts
        assert jur_counts.get("EMA", 0) >= 1, jur_counts
        assert jur_counts.get("NICE", 0) >= 1, jur_counts
        assert jur_counts.get("HC", 0) >= 1, jur_counts
        # Total = quota = 4. HC should be 1, not 2.
        assert jur_counts.get("HC", 0) == 1, (
            f"HC 2nd slot stole from FDA/EMA/NICE: {jur_counts}"
        )

    def test_hc_expansion_fires_when_quota_permits(
        self, monkeypatch,
    ) -> None:
        """Plan acceptance: HC expands to 2 when pool has >=2 HC AND
        quota has room beyond the 4-juris first-slot pass. Guard
        already covered by test_fda_ema_nice_first_slots_preserved.

        Pool: 3 HC + 1 FDA + 1 EMA + 1 NICE = 6 rows.
        max_rows=5 → T3 quota=5, forces the floor block.

        Expected: reservations = 1 per juris (4) + 1 HC extra (1) = 5.
        All 5 slots consumed by reservations — fill pass no-op.
        HC=2, FDA=1, EMA=1, NICE=1. Dropped: 1 HC (3rd).
        """
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "2")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation, _row_jurisdiction,
        )
        rows = [
            _make_t3_row("hc1", "https://pdf.hres.ca/1.pdf", "h1"),
            _make_t3_row("hc2", "https://canada.ca/recall/2", "h2"),
            _make_t3_row("hc3", "https://dhpp.hpfb-dgpsa.ca/3", "h3"),
            _make_t3_row("fda1", "https://accessdata.fda.gov/1", "f1"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/1", "e1"),
            _make_t3_row("nice1", "https://www.nice.org.uk/ta/1", "n1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=5,
        )
        jur_counts: dict = {}
        for r in result.selected_rows:
            j = _row_jurisdiction(r)
            if j:
                jur_counts[j] = jur_counts.get(j, 0) + 1
        assert jur_counts.get("HC", 0) == 2, (
            f"HC expansion should reserve 2 slots; jur_counts={jur_counts}"
        )
        assert jur_counts.get("FDA", 0) == 1, jur_counts
        assert jur_counts.get("EMA", 0) == 1, jur_counts
        assert jur_counts.get("NICE", 0) == 1, jur_counts

    def test_env_disables_expansion(self, monkeypatch) -> None:
        """PG_M41D_HC_QUOTA=1 restores M-41d behavior exactly."""
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "1")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation, _row_jurisdiction,
        )
        rows = [
            _make_t3_row("hc1", "https://pdf.hres.ca/1.pdf", "h1"),
            _make_t3_row("hc2", "https://canada.ca/en/recall/2", "h2"),
            _make_t3_row("hc3", "https://dhpp.hpfb-dgpsa.ca/3", "h3"),
            _make_t3_row("fda1", "https://accessdata.fda.gov/1", "f1"),
            _make_t3_row("fda2", "https://www.fda.gov/safety/2", "f2"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/1", "e1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=6,
        )
        jur_counts: dict = {}
        for r in result.selected_rows:
            j = _row_jurisdiction(r)
            if j:
                jur_counts[j] = jur_counts.get(j, 0) + 1
        # HC should get at most 1 via the M-41d floor; the 2 extras are
        # added via relevance fill only if they outscore FDA/EMA. Since
        # our rows have equal scores, the rank is by insertion order and
        # the 1 HC reserved + naturally high HC count by pool means HC
        # can still reach 2-3 via fill-by-relevance. The key check is
        # that the telemetry note is NOT emitted (expansion gate off).
        notes = " ".join(result.notes)
        assert "m42d_hc_quota_expand" not in notes, (
            f"PG_M41D_HC_QUOTA=1 should disable expansion. notes={notes}"
        )


# ─────────────────────────────────────────────────────────────────────
# Telemetry
# ─────────────────────────────────────────────────────────────────────


class TestHcExpansionTelemetry:
    def test_telemetry_emitted_when_expansion_fires(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "2")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            _make_t3_row("hc1", "https://pdf.hres.ca/1.pdf", "h1"),
            _make_t3_row("hc2", "https://canada.ca/en/recall/2", "h2"),
            _make_t3_row("hc3", "https://dhpp.hpfb-dgpsa.ca/3", "h3"),
            _make_t3_row("fda1", "https://accessdata.fda.gov/1", "f1"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/1", "e1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            # max_rows < pool to force the T3 tier block (avoid
            # pool_size<=max_rows short-circuit).
            max_rows=4,
        )
        telemetry = [n for n in result.notes if "m42d_hc_quota_expand" in n]
        assert telemetry, f"M-42d telemetry missing. notes={result.notes}"
        note = telemetry[0]
        assert "hc_pool=3" in note, note
        # M-42d pass-2 (Codex MEDIUM): `reserved` reports actual slots
        # taken = 1 (1-per-juris) + extras_added.
        assert "reserved=2" in note, note
        assert "extras_added=1" in note, note
        assert "quota=2" in note, note

    def test_telemetry_not_emitted_when_hc_absent(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("PG_M41D_HC_QUOTA", "2")
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            _make_t3_row("fda1", "https://accessdata.fda.gov/1", "f1"),
            _make_t3_row("ema1", "https://www.ema.europa.eu/1", "e1"),
            _make_t3_row("nice1", "https://www.nice.org.uk/ta/1", "n1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory t2dm",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
        )
        telemetry = [n for n in result.notes if "m42d_hc_quota_expand" in n]
        assert not telemetry, (
            f"M-42d fired without HC. notes={result.notes}"
        )


# ─────────────────────────────────────────────────────────────────────
# YAML integration — new anchor loads
# ─────────────────────────────────────────────────────────────────────


class TestClinicalYamlHcAnchors:
    def test_clinical_yaml_has_hpfb_dgpsa_anchor(self) -> None:
        import yaml
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "config" / "scope_templates" / "clinical.yaml"
        text = p.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        anchors = data.get("regulatory_anchors") or []
        assert "hpfb-dgpsa.ca" in anchors, (
            f"M-42d HC anchor missing from clinical.yaml; "
            f"anchors={anchors}"
        )

    def test_existing_hc_anchors_preserved(self) -> None:
        """Preservation: M-37 HC anchors still present."""
        import yaml
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "config" / "scope_templates" / "clinical.yaml"
        text = p.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        anchors = data.get("regulatory_anchors") or []
        for required in (
            "hres.ca", "pdf.hres.ca", "canada.ca",
            "recalls-rappels.canada.ca", "health-products.canada.ca",
        ):
            assert required in anchors, (
                f"M-37 HC anchor {required} removed; anchors={anchors}"
            )
