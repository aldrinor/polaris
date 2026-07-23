"""M-42d compatibility tests for evidence-derived jurisdiction coverage."""
from __future__ import annotations


def _row(evidence_id: str, jurisdiction: str, relevance: str) -> dict:
    return {
        "evidence_id": evidence_id,
        "url": f"https://{jurisdiction}.example/{evidence_id}",
        "tier": "T3",
        "jurisdiction": jurisdiction,
        "title": f"Authority record {evidence_id}",
        "statement": f"{relevance} authority record",
    }


class TestPriorityJurisdictionConfiguration:
    def test_default_priority_is_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("PG_M41D_PRIORITY_JURISDICTION", raising=False)
        from src.polaris_graph.retrieval.evidence_selector import (
            _priority_jurisdiction,
        )

        assert _priority_jurisdiction() == ""

    def test_priority_is_normalized(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_M41D_PRIORITY_JURISDICTION", " North ")
        from src.polaris_graph.retrieval.evidence_selector import (
            _priority_jurisdiction,
        )

        assert _priority_jurisdiction() == "north"

    def test_quota_is_inert_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv(
            "PG_M41D_PRIORITY_JURISDICTION_QUOTA", raising=False,
        )
        from src.polaris_graph.retrieval.evidence_selector import (
            _priority_jurisdiction_quota,
        )

        assert _priority_jurisdiction_quota() == 0

    def test_quota_override_and_validation(self, monkeypatch) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _priority_jurisdiction_quota,
        )

        monkeypatch.setenv("PG_M41D_PRIORITY_JURISDICTION_QUOTA", "3")
        assert _priority_jurisdiction_quota() == 3
        monkeypatch.setenv("PG_M41D_PRIORITY_JURISDICTION_QUOTA", "0")
        assert _priority_jurisdiction_quota() == 0
        monkeypatch.setenv("PG_M41D_PRIORITY_JURISDICTION_QUOTA", "invalid")
        assert _priority_jurisdiction_quota() == 0


class TestEvidenceDerivedJurisdiction:
    def test_metadata_precedes_host_fallback(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )

        row = {
            "url": "https://host-label.example/item",
            "jurisdiction": "Evidence Label",
        }
        assert _row_jurisdiction(row) == "evidence label"

    def test_host_fallback_is_structural(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _row_jurisdiction,
        )

        assert _row_jurisdiction({
            "url": "https://records.north.gov/item",
        }) == "north"
        assert _row_jurisdiction({
            "url": "https://www.delta.example.eu/item",
        }) == "delta"


class TestPriorityJurisdictionSelection:
    def test_every_present_jurisdiction_gets_first_slot(
        self, monkeypatch,
    ) -> None:
        monkeypatch.delenv("PG_M41D_PRIORITY_JURISDICTION", raising=False)
        rows = [
            _row("n1", "north", "high"),
            _row("n2", "north", "high"),
            _row("n3", "north", "high"),
            _row("s1", "south", "low"),
            _row("e1", "east", "low"),
        ]
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )

        result = select_evidence_for_generation(
            research_question="high authority record",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
        )
        assert {
            row["jurisdiction"] for row in result.selected_rows
        } == {"north", "south", "east"}

    def test_configured_priority_uses_remaining_capacity(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("PG_M41D_PRIORITY_JURISDICTION", "north")
        monkeypatch.setenv("PG_M41D_PRIORITY_JURISDICTION_QUOTA", "2")
        rows = [
            _row("n1", "north", "high"),
            _row("n2", "north", "high"),
            _row("n3", "north", "high"),
            _row("s1", "south", "low"),
            _row("e1", "east", "low"),
        ]
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )

        result = select_evidence_for_generation(
            research_question="high authority record",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=4,
        )
        counts = {
            jurisdiction: sum(
                row["jurisdiction"] == jurisdiction
                for row in result.selected_rows
            )
            for jurisdiction in {"north", "south", "east"}
        }
        assert counts == {"north": 2, "south": 1, "east": 1}
        note = next(
            note for note in result.notes
            if "m42d_priority_jurisdiction_expand" in note
        )
        assert "jurisdiction=north" in note
        assert "reserved=2" in note
        assert "extras_added=1" in note

    def test_no_priority_means_no_expansion_telemetry(
        self, monkeypatch,
    ) -> None:
        monkeypatch.delenv("PG_M41D_PRIORITY_JURISDICTION", raising=False)
        rows = [
            _row("n1", "north", "high"),
            _row("n2", "north", "high"),
            _row("s1", "south", "low"),
        ]
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )

        result = select_evidence_for_generation(
            research_question="authority record",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=2,
        )
        assert not any(
            "m42d_priority_jurisdiction_expand" in note
            for note in result.notes
        )
