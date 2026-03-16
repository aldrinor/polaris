"""
Integration tests for POLARIS Gemini-class features.

Tests cover:
- Cluster viability assessment (_assess_cluster_viability)
  - FULL_SECTION, MERGE, DROP decisions
  - Error fallback to FULL_SECTION default
- Structured data extraction (_extract_structured_data)
  - Basic extraction with evidence_id/source_url injection
  - Error returns empty list
- Chart generation (_generate_section_charts)
  - Disabled by default (env gate)
  - Enabled appends chart markdown
  - Error returns original content unchanged

All tests are fully mocked -- no real API calls or embedding model loads.
"""

import base64
import os
import struct
import zlib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.polaris_graph.schemas import (
    ClusterAssessment,
    StructuredDataExtraction,
    StructuredDataPoint,
)

# FIX-9: Valid 1x1 PNG for chart tests (format_chart_markdown validates magic bytes)
def _make_valid_png_b64() -> str:
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    raw = zlib.compress(b'\x00\xff\x00\x00')
    idat_crc = zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
    iend_crc = zlib.crc32(b'IEND') & 0xFFFFFFFF
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    return base64.b64encode(sig + ihdr + idat + iend).decode()

_VALID_PNG_B64 = _make_valid_png_b64()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cluster(
    theme: str = "Water Filtration Methods",
    description: str = "Evidence about water filtration techniques",
    key_claims: list[str] | None = None,
) -> dict:
    """Create a minimal cluster dict for testing."""
    return {
        "theme": theme,
        "description": description,
        "key_claims": key_claims or ["Activated carbon removes 95% PFAS"],
    }


def _make_evidence_piece(
    evidence_id: str = "ev_001",
    statement: str = "Activated carbon removes 95% of PFAS.",
    source_url: str = "https://example.com/study",
    quality_tier: str = "SILVER",
) -> dict:
    """Create a minimal evidence dict for testing."""
    return {
        "evidence_id": evidence_id,
        "statement": statement,
        "source_url": source_url,
        "quality_tier": quality_tier,
    }


def _make_structured_data_point(
    data_type: str = "comparison",
    label: str = "PFAS removal rate",
    value: str = "95%",
    year: str = "2024",
    unit: str = "percent",
    context: str = "Activated carbon vs. ion exchange",
) -> StructuredDataPoint:
    """Create a StructuredDataPoint for testing."""
    return StructuredDataPoint(
        data_type=data_type,
        label=label,
        value=value,
        year=year,
        unit=unit,
        context=context,
    )


# ---------------------------------------------------------------------------
# 1. _assess_cluster_viability tests
# ---------------------------------------------------------------------------

class TestAssessClusterViability:
    """Tests for synthesizer._assess_cluster_viability."""

    @pytest.mark.asyncio
    async def test_assess_cluster_viability_full_section(self):
        """FULL_SECTION decision with structured data detection."""
        from src.polaris_graph.agents.synthesizer import _assess_cluster_viability

        client = AsyncMock()
        client.generate_structured = AsyncMock(return_value=ClusterAssessment(
            decision="FULL_SECTION",
            reasoning="Strong evidence cluster with 5 unique citable claims",
            merge_target="",
            key_claims=["Claim A", "Claim B", "Claim C"],
            has_structured_data=True,
            data_type="comparison",
        ))

        cluster = _make_cluster()
        evidence = [_make_evidence_piece(f"ev_{i}") for i in range(5)]
        all_themes = ["Water Filtration Methods", "Environmental Impact", "Cost Analysis"]

        result = await _assess_cluster_viability(client, cluster, evidence, all_themes)

        assert result["decision"] == "FULL_SECTION"
        assert result["reasoning"] == "Strong evidence cluster with 5 unique citable claims"
        assert result["merge_target"] == ""
        assert result["key_claims"] == ["Claim A", "Claim B", "Claim C"]
        assert result["has_structured_data"] is True
        assert result["data_type"] == "comparison"

        # Verify the LLM was called with the correct schema
        client.generate_structured.assert_awaited_once()
        call_kwargs = client.generate_structured.call_args
        assert call_kwargs.kwargs.get("schema") is ClusterAssessment

    @pytest.mark.asyncio
    async def test_assess_cluster_viability_merge(self):
        """MERGE decision with populated merge_target."""
        from src.polaris_graph.agents.synthesizer import _assess_cluster_viability

        client = AsyncMock()
        client.generate_structured = AsyncMock(return_value=ClusterAssessment(
            decision="MERGE",
            reasoning="Evidence overlaps significantly with Environmental Impact theme",
            merge_target="Environmental Impact",
            key_claims=["Overlapping claim"],
            has_structured_data=False,
            data_type="none",
        ))

        cluster = _make_cluster(theme="Pollution Effects")
        evidence = [_make_evidence_piece("ev_merge_1")]
        all_themes = ["Pollution Effects", "Environmental Impact", "Remediation"]

        result = await _assess_cluster_viability(client, cluster, evidence, all_themes)

        assert result["decision"] == "MERGE"
        assert result["merge_target"] == "Environmental Impact"
        assert result["has_structured_data"] is False

    @pytest.mark.asyncio
    async def test_assess_cluster_viability_drop(self):
        """DROP decision with reasoning explanation."""
        from src.polaris_graph.agents.synthesizer import _assess_cluster_viability

        client = AsyncMock()
        client.generate_structured = AsyncMock(return_value=ClusterAssessment(
            decision="DROP",
            reasoning="Off-topic evidence",
            merge_target="",
            key_claims=[],
            has_structured_data=False,
            data_type="none",
        ))

        cluster = _make_cluster(theme="Unrelated Topic")
        evidence = [_make_evidence_piece("ev_drop_1", statement="Irrelevant data")]
        all_themes = ["Unrelated Topic", "Water Filtration"]

        result = await _assess_cluster_viability(client, cluster, evidence, all_themes)

        assert result["decision"] == "DROP"
        assert result["reasoning"] == "Off-topic evidence"
        assert result["key_claims"] == []

    @pytest.mark.asyncio
    async def test_assess_cluster_viability_error_fallback(self):
        """On error, returns FULL_SECTION default (safe fallback)."""
        from src.polaris_graph.agents.synthesizer import _assess_cluster_viability

        client = AsyncMock()
        client.generate_structured = AsyncMock(
            side_effect=Exception("API timeout"),
        )

        cluster = _make_cluster(
            key_claims=["Claim X", "Claim Y"],
        )
        evidence = [_make_evidence_piece("ev_err_1")]
        all_themes = ["Water Filtration Methods"]

        result = await _assess_cluster_viability(client, cluster, evidence, all_themes)

        # Must default to FULL_SECTION on error (safe fallback)
        assert result["decision"] == "FULL_SECTION"
        assert "Assessment failed" in result["reasoning"]
        assert "API timeout" in result["reasoning"]
        assert result["merge_target"] == ""
        assert result["has_structured_data"] is False
        assert result["data_type"] == "none"
        # key_claims should be from the cluster input (capped at 5)
        assert result["key_claims"] == ["Claim X", "Claim Y"]


# ---------------------------------------------------------------------------
# 2. _extract_structured_data tests
# ---------------------------------------------------------------------------

class TestExtractStructuredData:
    """Tests for analyzer._extract_structured_data."""

    @pytest.mark.asyncio
    async def test_extract_structured_data_basic(self):
        """Basic extraction returns data points with injected evidence_id and source_url."""
        from src.polaris_graph.agents.analyzer import _extract_structured_data

        dp1 = _make_structured_data_point(
            data_type="comparison",
            label="PFAS removal rate",
            value="95%",
            year="2024",
            unit="percent",
            context="Activated carbon vs ion exchange",
        )
        dp2 = _make_structured_data_point(
            data_type="measurement",
            label="Treatment cost",
            value="$2.50",
            year="2023",
            unit="USD per gallon",
            context="Pilot-scale system operating cost",
        )

        client = AsyncMock()
        client.generate_structured = AsyncMock(
            return_value=StructuredDataExtraction(
                data_points=[dp1, dp2],
                has_comparison_data=True,
                has_time_series=False,
                comparison_entities=["activated carbon", "ion exchange"],
            ),
        )

        result = await _extract_structured_data(
            client=client,
            content="Activated carbon filtration achieves 95% PFAS removal at $2.50/gallon.",
            source_url="https://example.com/pfas-study",
            evidence_id="ev_structured_001",
        )

        assert len(result) == 2

        # Verify evidence_id and source_url injected into each data point
        for dp_dict in result:
            assert dp_dict["evidence_id"] == "ev_structured_001"
            assert dp_dict["source_url"] == "https://example.com/pfas-study"

        # Verify first point fields
        assert result[0]["data_type"] == "comparison"
        assert result[0]["label"] == "PFAS removal rate"
        assert result[0]["value"] == "95%"
        assert result[0]["year"] == "2024"
        assert result[0]["unit"] == "percent"

        # Verify second point fields
        assert result[1]["data_type"] == "measurement"
        assert result[1]["label"] == "Treatment cost"
        assert result[1]["value"] == "$2.50"

        # Verify LLM was called with correct schema
        client.generate_structured.assert_awaited_once()
        call_kwargs = client.generate_structured.call_args
        assert call_kwargs.kwargs.get("schema") is StructuredDataExtraction

    @pytest.mark.asyncio
    async def test_extract_structured_data_error_returns_empty(self):
        """On error, returns empty list."""
        from src.polaris_graph.agents.analyzer import _extract_structured_data

        client = AsyncMock()
        client.generate_structured = AsyncMock(
            side_effect=Exception("Schema validation failed"),
        )

        result = await _extract_structured_data(
            client=client,
            content="Some content with numbers and data.",
            source_url="https://example.com/broken",
            evidence_id="ev_err_002",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_extract_structured_data_empty_content_returns_empty(self):
        """Empty or whitespace-only content returns empty list immediately."""
        from src.polaris_graph.agents.analyzer import _extract_structured_data

        client = AsyncMock()

        result = await _extract_structured_data(
            client=client,
            content="   ",
            source_url="https://example.com",
            evidence_id="ev_empty",
        )

        assert result == []
        # LLM should NOT be called for empty content
        client.generate_structured.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. _generate_section_charts tests
# ---------------------------------------------------------------------------

class TestGenerateSectionCharts:
    """Tests for synthesizer._generate_section_charts."""

    @pytest.mark.asyncio
    async def test_generate_section_charts_disabled_by_default(self, monkeypatch):
        """When PG_CHART_GENERATION_ENABLED is unset/0, returns content unchanged."""
        from src.polaris_graph.agents.synthesizer import _generate_section_charts

        monkeypatch.setenv("PG_CHART_GENERATION_ENABLED", "0")

        client = AsyncMock()
        section_content = "## Water Filtration\n\nActivated carbon removes PFAS effectively."
        structured_data = [{"data_type": "comparison", "label": "test", "value": "1"}]

        result = await _generate_section_charts(
            client=client,
            section_content=section_content,
            structured_data=structured_data,
            research_context="PFAS removal from drinking water",
        )

        assert result == section_content
        # No LLM call should have been made
        client.generate_structured.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_section_charts_enabled_appends_charts(self, monkeypatch):
        """When enabled, appends chart markdown to section content."""
        from src.polaris_graph.agents.synthesizer import _generate_section_charts

        monkeypatch.setenv("PG_CHART_GENERATION_ENABLED", "1")

        client = AsyncMock()
        section_content = "## Water Filtration\n\nActivated carbon removes PFAS effectively."
        structured_data = [
            {"data_type": "comparison", "label": "PFAS removal", "value": "95%"},
        ]

        mock_result = {
            "charts": [
                {
                    "title": "PFAS Removal Comparison",
                    "image_base64": _VALID_PNG_B64,
                    "description": "Comparison of filtration methods",
                },
            ],
            "tables": [],
            "insights": ["Activated carbon outperforms ion exchange"],
        }

        with patch(
            "src.polaris_graph.agents.synthesizer.analyze_structured_data",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_analyze:
            result = await _generate_section_charts(
                client=client,
                section_content=section_content,
                structured_data=structured_data,
                research_context="PFAS removal from drinking water",
            )

            # analyze_structured_data should have been called
            mock_analyze.assert_awaited_once()

        # Result should contain original content
        assert result.startswith(section_content)
        # Result should contain chart markdown (format_chart_markdown output)
        assert "PFAS Removal Comparison" in result
        assert _VALID_PNG_B64 in result
        assert "data:image/png;base64," in result
        assert "Figure 1:" in result
        assert "Comparison of filtration methods" in result

    @pytest.mark.asyncio
    async def test_generate_section_charts_error_returns_original(self, monkeypatch):
        """When enabled but analyze_structured_data raises, returns content unchanged."""
        from src.polaris_graph.agents.synthesizer import _generate_section_charts

        monkeypatch.setenv("PG_CHART_GENERATION_ENABLED", "1")

        client = AsyncMock()
        section_content = "## Results\n\nKey findings from analysis."
        structured_data = [
            {"data_type": "time_series", "label": "trend", "value": "42"},
        ]

        with patch(
            "src.polaris_graph.agents.synthesizer.analyze_structured_data",
            new_callable=AsyncMock,
            side_effect=Exception("Matplotlib rendering failed"),
        ):
            result = await _generate_section_charts(
                client=client,
                section_content=section_content,
                structured_data=structured_data,
                research_context="Trend analysis",
            )

        # Must return original content unchanged (non-blocking error)
        assert result == section_content

    @pytest.mark.asyncio
    async def test_generate_section_charts_empty_data_returns_original(self, monkeypatch):
        """When structured_data is empty, returns content unchanged without LLM call."""
        from src.polaris_graph.agents.synthesizer import _generate_section_charts

        monkeypatch.setenv("PG_CHART_GENERATION_ENABLED", "1")

        client = AsyncMock()
        section_content = "## Results\n\nNo structured data available."

        result = await _generate_section_charts(
            client=client,
            section_content=section_content,
            structured_data=[],
            research_context="Empty data test",
        )

        assert result == section_content
