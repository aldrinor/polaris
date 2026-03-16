#!/usr/bin/env python3
"""
Unit tests for Visual Generator.

Tests:
- ChartType and VisualType enums
- VisualConfig dataclass
- VisualGenerator class
- Chart generation methods
- Convenience functions

Run:
    pytest tests/unit/test_visual_generator.py -v
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.visual_generator import (
    VisualGenerator,
    VisualConfig,
    VisualOutput,
    ChartData,
    TimelineEvent,
    ComparisonItem,
    ChartType,
    VisualType,
    ColorScheme,
    COLOR_PALETTES,
    create_bar_chart,
    create_pie_chart,
    create_summary_card,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_chart_data():
    """Sample chart data for testing."""
    return ChartData(
        labels=["Category A", "Category B", "Category C", "Category D"],
        values=[25, 40, 15, 20],
        series_name="Test Data",
    )


@pytest.fixture
def sample_timeline_events():
    """Sample timeline events for testing."""
    return [
        TimelineEvent("2025-01", "Project Start", "Initial planning phase", "planning", 5),
        TimelineEvent("2025-03", "Development", "Core development begins", "dev", 4),
        TimelineEvent("2025-06", "Launch", "Product launch", "launch", 5),
    ]


@pytest.fixture
def sample_comparison_items():
    """Sample comparison items for testing."""
    return [
        ComparisonItem("Option A", {"Price": "$100", "Quality": "High"}, score=8.5),
        ComparisonItem("Option B", {"Price": "$80", "Quality": "Medium"}, score=7.0),
        ComparisonItem("Option C", {"Price": "$120", "Quality": "Premium"}, score=9.5),
    ]


@pytest.fixture
def default_generator():
    """Default visual generator instance."""
    return VisualGenerator()


@pytest.fixture
def custom_config():
    """Custom visual configuration."""
    return VisualConfig(
        default_width=1000,
        default_height=800,
        color_scheme=ColorScheme.BLUE,
    )


# =============================================================================
# ChartType Enum Tests
# =============================================================================

class TestChartType:
    """Tests for ChartType enum."""

    def test_all_types_defined(self):
        """Test all chart types are defined."""
        expected = ["bar", "line", "pie", "horizontal_bar", "scatter", "area", "donut"]
        for chart_type in expected:
            assert any(ct.value == chart_type for ct in ChartType)

    def test_chart_type_values(self):
        """Test enum values."""
        assert ChartType.BAR.value == "bar"
        assert ChartType.PIE.value == "pie"
        assert ChartType.LINE.value == "line"


# =============================================================================
# VisualType Enum Tests
# =============================================================================

class TestVisualType:
    """Tests for VisualType enum."""

    def test_all_types_defined(self):
        """Test all visual types are defined."""
        expected = ["chart", "summary_card", "timeline", "comparison_table", "infographic", "word_cloud"]
        for vtype in expected:
            assert any(vt.value == vtype for vt in VisualType)


# =============================================================================
# ColorScheme Tests
# =============================================================================

class TestColorScheme:
    """Tests for ColorScheme enum."""

    def test_all_schemes_defined(self):
        """Test all color schemes are defined."""
        expected = ["default", "blue", "green", "warm", "cool", "monochrome", "polaris"]
        for scheme in expected:
            assert any(cs.value == scheme for cs in ColorScheme)

    def test_palettes_exist(self):
        """Test color palettes exist for all schemes."""
        for scheme in ColorScheme:
            assert scheme in COLOR_PALETTES
            assert len(COLOR_PALETTES[scheme]) >= 6


# =============================================================================
# VisualConfig Tests
# =============================================================================

class TestVisualConfig:
    """Tests for VisualConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VisualConfig()
        assert config.default_width == 800
        assert config.default_height == 600
        assert config.color_scheme == ColorScheme.POLARIS
        assert config.show_legend is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = VisualConfig(
            default_width=1200,
            color_scheme=ColorScheme.BLUE,
        )
        assert config.default_width == 1200
        assert config.color_scheme == ColorScheme.BLUE


# =============================================================================
# ChartData Tests
# =============================================================================

class TestChartData:
    """Tests for ChartData dataclass."""

    def test_basic_data(self, sample_chart_data):
        """Test basic chart data."""
        assert len(sample_chart_data.labels) == 4
        assert len(sample_chart_data.values) == 4

    def test_validate_valid_data(self, sample_chart_data):
        """Test validation of valid data."""
        assert sample_chart_data.validate() is True

    def test_validate_mismatched_lengths(self):
        """Test validation of mismatched data."""
        data = ChartData(
            labels=["A", "B", "C"],
            values=[1, 2],  # Missing one value
        )
        assert data.validate() is False

    def test_secondary_values(self):
        """Test data with secondary values."""
        data = ChartData(
            labels=["A", "B"],
            values=[10, 20],
            secondary_values=[5, 15],
            secondary_name="Secondary",
        )
        assert data.validate() is True


# =============================================================================
# TimelineEvent Tests
# =============================================================================

class TestTimelineEvent:
    """Tests for TimelineEvent dataclass."""

    def test_basic_event(self):
        """Test basic timeline event."""
        event = TimelineEvent(
            date="2025-01",
            title="Test Event",
            description="Test description",
        )
        assert event.date == "2025-01"
        assert event.importance == 1  # Default


# =============================================================================
# ComparisonItem Tests
# =============================================================================

class TestComparisonItem:
    """Tests for ComparisonItem dataclass."""

    def test_basic_item(self):
        """Test basic comparison item."""
        item = ComparisonItem(
            name="Test Item",
            attributes={"Key": "Value"},
        )
        assert item.name == "Test Item"
        assert item.score is None  # Default

    def test_item_with_score(self):
        """Test item with score."""
        item = ComparisonItem(
            name="Scored Item",
            attributes={"A": 1},
            score=8.5,
        )
        assert item.score == 8.5


# =============================================================================
# VisualOutput Tests
# =============================================================================

class TestVisualOutput:
    """Tests for VisualOutput dataclass."""

    def test_to_dict(self):
        """Test dictionary conversion."""
        output = VisualOutput(
            visual_type=VisualType.CHART,
            title="Test Chart",
            content="<svg>...</svg>",
            format="svg",
            width=800,
            height=600,
        )
        data = output.to_dict()
        assert data["visual_type"] == "chart"
        assert data["title"] == "Test Chart"
        assert data["format"] == "svg"


# =============================================================================
# VisualGenerator Tests
# =============================================================================

class TestVisualGenerator:
    """Tests for VisualGenerator class."""

    def test_initialization_default(self, default_generator):
        """Test default initialization."""
        assert default_generator.config is not None
        assert len(default_generator._colors) >= 6

    def test_initialization_custom(self, custom_config):
        """Test initialization with custom config."""
        generator = VisualGenerator(config=custom_config)
        assert generator.config.default_width == 1000


# =============================================================================
# Bar Chart Tests
# =============================================================================

class TestBarChart:
    """Tests for bar chart generation."""

    def test_create_bar_chart(self, default_generator, sample_chart_data):
        """Test creating bar chart."""
        chart = default_generator.create_bar_chart(sample_chart_data, "Test Bar")
        assert chart.visual_type == VisualType.CHART
        assert chart.format == "svg"
        assert "<svg" in chart.content

    def test_bar_chart_contains_data(self, default_generator, sample_chart_data):
        """Test bar chart contains data elements."""
        chart = default_generator.create_bar_chart(sample_chart_data, "Test")
        # Should contain rect elements for bars
        assert "<rect" in chart.content

    def test_horizontal_bar_chart(self, default_generator, sample_chart_data):
        """Test horizontal bar chart."""
        chart = default_generator.create_bar_chart(
            sample_chart_data,
            "Horizontal",
            horizontal=True,
        )
        assert chart.metadata["chart_type"] == "horizontal_bar"

    def test_bar_chart_invalid_data(self, default_generator):
        """Test bar chart with invalid data."""
        invalid_data = ChartData(labels=["A"], values=[1, 2])  # Mismatched
        with pytest.raises(ValueError):
            default_generator.create_bar_chart(invalid_data, "Test")


# =============================================================================
# Pie Chart Tests
# =============================================================================

class TestPieChart:
    """Tests for pie chart generation."""

    def test_create_pie_chart(self, default_generator, sample_chart_data):
        """Test creating pie chart."""
        chart = default_generator.create_pie_chart(sample_chart_data, "Test Pie")
        assert chart.visual_type == VisualType.CHART
        assert "<svg" in chart.content

    def test_pie_chart_contains_paths(self, default_generator, sample_chart_data):
        """Test pie chart contains path elements."""
        chart = default_generator.create_pie_chart(sample_chart_data, "Test")
        assert "<path" in chart.content

    def test_donut_chart(self, default_generator, sample_chart_data):
        """Test donut chart."""
        chart = default_generator.create_pie_chart(
            sample_chart_data,
            "Donut",
            donut=True,
        )
        assert chart.metadata["chart_type"] == "donut"


# =============================================================================
# Line Chart Tests
# =============================================================================

class TestLineChart:
    """Tests for line chart generation."""

    def test_create_line_chart(self, default_generator, sample_chart_data):
        """Test creating line chart."""
        chart = default_generator.create_line_chart(sample_chart_data, "Test Line")
        assert chart.visual_type == VisualType.CHART
        assert "<svg" in chart.content

    def test_line_chart_contains_elements(self, default_generator, sample_chart_data):
        """Test line chart contains path and circles."""
        chart = default_generator.create_line_chart(sample_chart_data, "Test")
        assert "<path" in chart.content
        assert "<circle" in chart.content


# =============================================================================
# Summary Card Tests
# =============================================================================

class TestSummaryCard:
    """Tests for summary card generation."""

    def test_create_summary_card(self, default_generator):
        """Test creating summary card."""
        stats = {"Total": 100, "Average": 50}
        card = default_generator.create_summary_card(stats, "Stats")
        assert card.visual_type == VisualType.SUMMARY_CARD
        assert card.format == "html"

    def test_summary_card_contains_data(self, default_generator):
        """Test summary card contains stat data."""
        stats = {"Users": 1000, "Revenue": "$5000"}
        card = default_generator.create_summary_card(stats, "Metrics")
        assert "Users" in card.content
        assert "1000" in card.content


# =============================================================================
# Timeline Tests
# =============================================================================

class TestTimeline:
    """Tests for timeline generation."""

    def test_create_timeline(self, default_generator, sample_timeline_events):
        """Test creating timeline."""
        timeline = default_generator.create_timeline(sample_timeline_events, "Timeline")
        assert timeline.visual_type == VisualType.TIMELINE
        assert "<svg" in timeline.content

    def test_timeline_contains_events(self, default_generator, sample_timeline_events):
        """Test timeline contains event data."""
        timeline = default_generator.create_timeline(sample_timeline_events, "Test")
        assert "Project Start" in timeline.content
        assert "2025-01" in timeline.content

    def test_timeline_height_scales(self, default_generator):
        """Test timeline height scales with events."""
        events = [TimelineEvent(f"2025-{i:02d}", f"Event {i}") for i in range(1, 11)]
        timeline = default_generator.create_timeline(events, "Long Timeline")
        assert timeline.height > 400  # Should be taller


# =============================================================================
# Comparison Table Tests
# =============================================================================

class TestComparisonTable:
    """Tests for comparison table generation."""

    def test_create_comparison_table(self, default_generator, sample_comparison_items):
        """Test creating comparison table."""
        table = default_generator.create_comparison_table(sample_comparison_items, "Compare")
        assert table.visual_type == VisualType.COMPARISON_TABLE
        assert table.format == "html"

    def test_table_contains_items(self, default_generator, sample_comparison_items):
        """Test table contains item data."""
        table = default_generator.create_comparison_table(sample_comparison_items, "Test")
        assert "Option A" in table.content
        assert "$100" in table.content

    def test_table_empty_items(self, default_generator):
        """Test table with empty items."""
        table = default_generator.create_comparison_table([], "Empty")
        assert "No data" in table.content


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_bar_chart_function(self):
        """Test create_bar_chart convenience function."""
        chart = create_bar_chart(["A", "B", "C"], [10, 20, 30], "Quick Bar")
        assert chart.visual_type == VisualType.CHART
        assert "<svg" in chart.content

    def test_create_pie_chart_function(self):
        """Test create_pie_chart convenience function."""
        chart = create_pie_chart(["X", "Y", "Z"], [30, 40, 30], "Quick Pie")
        assert "<svg" in chart.content

    def test_create_summary_card_function(self):
        """Test create_summary_card convenience function."""
        card = create_summary_card({"Key": "Value"}, "Quick Card")
        assert "Key" in card.content
        assert "Value" in card.content


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_data_point(self, default_generator):
        """Test chart with single data point."""
        data = ChartData(labels=["Only"], values=[100])
        chart = default_generator.create_bar_chart(data, "Single")
        assert "<svg" in chart.content

    def test_large_values(self, default_generator):
        """Test chart with large values."""
        data = ChartData(
            labels=["Big", "Huge"],
            values=[1000000, 5000000],
        )
        chart = default_generator.create_bar_chart(data, "Large")
        assert "<svg" in chart.content

    def test_zero_values(self, default_generator):
        """Test chart with zero values."""
        data = ChartData(
            labels=["Zero", "One"],
            values=[0, 1],
        )
        chart = default_generator.create_bar_chart(data, "Zeros")
        assert "<svg" in chart.content

    def test_long_labels(self, default_generator):
        """Test chart with long labels."""
        data = ChartData(
            labels=["This is a very long label that should be truncated", "Short"],
            values=[50, 50],
        )
        chart = default_generator.create_bar_chart(data, "Long Labels")
        # Labels should be truncated
        assert "This is a" in chart.content

    def test_many_data_points(self, default_generator):
        """Test chart with many data points."""
        data = ChartData(
            labels=[f"Item {i}" for i in range(20)],
            values=[i * 5 for i in range(20)],
        )
        chart = default_generator.create_line_chart(data, "Many Points")
        assert "<svg" in chart.content


# =============================================================================
# Self-Test Function
# =============================================================================

class TestSelfTest:
    """Tests for self_test function."""

    def test_self_test_passes(self):
        """Test that self-test function passes."""
        from src.tools.visual_generator import self_test
        assert self_test() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
