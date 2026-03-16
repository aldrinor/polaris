"""
POLARIS Visual Output Generator
===============================
Generates visual outputs from research data.

Features:
- Chart generation (bar, line, pie)
- Summary infographics
- Timeline visualizations
- Comparison tables as images
- Export to PNG/SVG

Note: This module provides visualization specifications.
Actual rendering uses matplotlib when available,
or generates SVG/HTML for fallback rendering.

Usage:
    from src.tools.visual_generator import VisualGenerator

    generator = VisualGenerator()

    # Generate a bar chart
    chart = generator.create_bar_chart(data, title="Results")

    # Generate summary card
    card = generator.create_summary_card(stats)
"""

import logging
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class ChartType(str, Enum):
    """Available chart types."""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    HORIZONTAL_BAR = "horizontal_bar"
    SCATTER = "scatter"
    AREA = "area"
    DONUT = "donut"


class VisualType(str, Enum):
    """Types of visual outputs."""
    CHART = "chart"
    SUMMARY_CARD = "summary_card"
    TIMELINE = "timeline"
    COMPARISON_TABLE = "comparison_table"
    INFOGRAPHIC = "infographic"
    WORD_CLOUD = "word_cloud"


class ColorScheme(str, Enum):
    """Predefined color schemes."""
    DEFAULT = "default"
    BLUE = "blue"
    GREEN = "green"
    WARM = "warm"
    COOL = "cool"
    MONOCHROME = "monochrome"
    POLARIS = "polaris"


# Color palettes
COLOR_PALETTES = {
    ColorScheme.DEFAULT: ["#3498db", "#2ecc71", "#e74c3c", "#f39c12", "#9b59b6", "#1abc9c"],
    ColorScheme.BLUE: ["#1a5276", "#2980b9", "#3498db", "#5dade2", "#85c1e9", "#aed6f1"],
    ColorScheme.GREEN: ["#145a32", "#1e8449", "#27ae60", "#52be80", "#82e0aa", "#abebc6"],
    ColorScheme.WARM: ["#922b21", "#c0392b", "#e74c3c", "#f39c12", "#f5b041", "#f7dc6f"],
    ColorScheme.COOL: ["#1a5276", "#2471a3", "#5499c7", "#17a589", "#45b39d", "#76d7c4"],
    ColorScheme.MONOCHROME: ["#1c2833", "#2c3e50", "#566573", "#808b96", "#aeb6bf", "#d5d8dc"],
    ColorScheme.POLARIS: ["#0052cc", "#36b37e", "#ff5630", "#6554c0", "#00b8d9", "#ffab00"],
}


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class VisualConfig:
    """Configuration for visual generation."""

    # Sizing
    default_width: int = 800
    default_height: int = 600
    card_width: int = 400
    card_height: int = 300

    # Styling
    color_scheme: ColorScheme = ColorScheme.POLARIS
    font_family: str = "Arial, sans-serif"
    background_color: str = "#ffffff"
    text_color: str = "#333333"

    # Chart options
    show_legend: bool = True
    show_grid: bool = True
    show_values: bool = True
    animation: bool = False

    # Export
    default_format: str = "svg"
    dpi: int = 150


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ChartData:
    """Data for chart generation."""
    labels: List[str]
    values: List[Union[int, float]]
    series_name: str = "Data"
    secondary_values: Optional[List[Union[int, float]]] = None
    secondary_name: Optional[str] = None

    def validate(self) -> bool:
        """Validate chart data."""
        if len(self.labels) != len(self.values):
            return False
        if self.secondary_values and len(self.secondary_values) != len(self.labels):
            return False
        return True


@dataclass
class TimelineEvent:
    """Event for timeline visualization."""
    date: str
    title: str
    description: str = ""
    category: str = ""
    importance: int = 1  # 1-5 scale


@dataclass
class ComparisonItem:
    """Item for comparison table."""
    name: str
    attributes: Dict[str, Any]
    score: Optional[float] = None


@dataclass
class VisualOutput:
    """Generated visual output."""
    visual_type: VisualType
    title: str
    content: str  # SVG, HTML, or base64 image data
    format: str  # svg, html, png
    width: int
    height: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "visual_type": self.visual_type.value,
            "title": self.title,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "metadata": self.metadata,
            "content_length": len(self.content),
        }


# =============================================================================
# Visual Generator
# =============================================================================

class VisualGenerator:
    """
    Generates visual outputs from research data.

    Creates charts, summary cards, timelines, and other
    visualizations for research reports.
    """

    def __init__(self, config: Optional[VisualConfig] = None):
        """
        Initialize the visual generator.

        Args:
            config: Visual generation configuration
        """
        self.config = config or VisualConfig()
        self._colors = COLOR_PALETTES[self.config.color_scheme]

    def create_bar_chart(
        self,
        data: ChartData,
        title: str = "Bar Chart",
        horizontal: bool = False,
    ) -> VisualOutput:
        """
        Create a bar chart.

        Args:
            data: Chart data
            title: Chart title
            horizontal: Use horizontal bars

        Returns:
            VisualOutput with SVG chart
        """
        if not data.validate():
            raise ValueError("Invalid chart data")

        chart_type = ChartType.HORIZONTAL_BAR if horizontal else ChartType.BAR
        svg = self._generate_bar_chart_svg(data, title, horizontal)

        return VisualOutput(
            visual_type=VisualType.CHART,
            title=title,
            content=svg,
            format="svg",
            width=self.config.default_width,
            height=self.config.default_height,
            metadata={"chart_type": chart_type.value, "data_points": len(data.labels)},
        )

    def create_pie_chart(
        self,
        data: ChartData,
        title: str = "Pie Chart",
        donut: bool = False,
    ) -> VisualOutput:
        """
        Create a pie or donut chart.

        Args:
            data: Chart data
            title: Chart title
            donut: Create donut chart instead

        Returns:
            VisualOutput with SVG chart
        """
        if not data.validate():
            raise ValueError("Invalid chart data")

        chart_type = ChartType.DONUT if donut else ChartType.PIE
        svg = self._generate_pie_chart_svg(data, title, donut)

        return VisualOutput(
            visual_type=VisualType.CHART,
            title=title,
            content=svg,
            format="svg",
            width=self.config.default_height,  # Square
            height=self.config.default_height,
            metadata={"chart_type": chart_type.value, "data_points": len(data.labels)},
        )

    def create_line_chart(
        self,
        data: ChartData,
        title: str = "Line Chart",
    ) -> VisualOutput:
        """
        Create a line chart.

        Args:
            data: Chart data
            title: Chart title

        Returns:
            VisualOutput with SVG chart
        """
        if not data.validate():
            raise ValueError("Invalid chart data")

        svg = self._generate_line_chart_svg(data, title)

        return VisualOutput(
            visual_type=VisualType.CHART,
            title=title,
            content=svg,
            format="svg",
            width=self.config.default_width,
            height=self.config.default_height,
            metadata={"chart_type": ChartType.LINE.value, "data_points": len(data.labels)},
        )

    def create_summary_card(
        self,
        stats: Dict[str, Any],
        title: str = "Summary",
    ) -> VisualOutput:
        """
        Create a summary statistics card.

        Args:
            stats: Dictionary of stat names to values
            title: Card title

        Returns:
            VisualOutput with HTML card
        """
        html = self._generate_summary_card_html(stats, title)

        return VisualOutput(
            visual_type=VisualType.SUMMARY_CARD,
            title=title,
            content=html,
            format="html",
            width=self.config.card_width,
            height=self.config.card_height,
            metadata={"stat_count": len(stats)},
        )

    def create_timeline(
        self,
        events: List[TimelineEvent],
        title: str = "Timeline",
    ) -> VisualOutput:
        """
        Create a timeline visualization.

        Args:
            events: List of timeline events
            title: Timeline title

        Returns:
            VisualOutput with SVG timeline
        """
        svg = self._generate_timeline_svg(events, title)

        return VisualOutput(
            visual_type=VisualType.TIMELINE,
            title=title,
            content=svg,
            format="svg",
            width=self.config.default_width,
            height=max(400, len(events) * 80),
            metadata={"event_count": len(events)},
        )

    def create_comparison_table(
        self,
        items: List[ComparisonItem],
        title: str = "Comparison",
    ) -> VisualOutput:
        """
        Create a comparison table visualization.

        Args:
            items: Items to compare
            title: Table title

        Returns:
            VisualOutput with HTML table
        """
        html = self._generate_comparison_table_html(items, title)

        return VisualOutput(
            visual_type=VisualType.COMPARISON_TABLE,
            title=title,
            content=html,
            format="html",
            width=self.config.default_width,
            height=100 + len(items) * 50,
            metadata={"item_count": len(items)},
        )

    # =========================================================================
    # SVG Generation Methods
    # =========================================================================

    def _generate_bar_chart_svg(
        self,
        data: ChartData,
        title: str,
        horizontal: bool,
    ) -> str:
        """Generate SVG for bar chart."""
        width = self.config.default_width
        height = self.config.default_height
        margin = {"top": 60, "right": 40, "bottom": 80, "left": 60}

        chart_width = width - margin["left"] - margin["right"]
        chart_height = height - margin["top"] - margin["bottom"]

        max_val = max(data.values) if data.values else 1
        n_bars = len(data.labels)
        bar_width = chart_width / n_bars * 0.7
        bar_gap = chart_width / n_bars * 0.3

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
            f'<rect width="{width}" height="{height}" fill="{self.config.background_color}"/>',
            f'<text x="{width/2}" y="35" text-anchor="middle" font-family="{self.config.font_family}" font-size="18" font-weight="bold" fill="{self.config.text_color}">{title}</text>',
        ]

        # Draw bars
        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            bar_height = (value / max_val) * chart_height
            x = margin["left"] + i * (bar_width + bar_gap) + bar_gap / 2
            y = margin["top"] + chart_height - bar_height
            color = self._colors[i % len(self._colors)]

            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" fill="{color}" rx="2"/>'
            )

            # Value label
            if self.config.show_values:
                svg_parts.append(
                    f'<text x="{x + bar_width/2}" y="{y - 5}" text-anchor="middle" font-family="{self.config.font_family}" font-size="12" fill="{self.config.text_color}">{value}</text>'
                )

            # X-axis label
            svg_parts.append(
                f'<text x="{x + bar_width/2}" y="{height - margin["bottom"] + 20}" text-anchor="middle" font-family="{self.config.font_family}" font-size="11" fill="{self.config.text_color}">{label[:15]}</text>'
            )

        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)

    def _generate_pie_chart_svg(
        self,
        data: ChartData,
        title: str,
        donut: bool,
    ) -> str:
        """Generate SVG for pie/donut chart."""
        size = self.config.default_height
        cx, cy = size / 2, size / 2
        radius = size / 3
        inner_radius = radius * 0.6 if donut else 0

        total = sum(data.values) if data.values else 1
        angles = [v / total * 360 for v in data.values]

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">',
            f'<rect width="{size}" height="{size}" fill="{self.config.background_color}"/>',
            f'<text x="{size/2}" y="30" text-anchor="middle" font-family="{self.config.font_family}" font-size="18" font-weight="bold" fill="{self.config.text_color}">{title}</text>',
        ]

        import math
        current_angle = -90

        for i, (label, value, angle) in enumerate(zip(data.labels, data.values, angles)):
            color = self._colors[i % len(self._colors)]
            start_angle = current_angle
            end_angle = current_angle + angle

            # Convert to radians
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)

            # Calculate arc points
            x1 = cx + radius * math.cos(start_rad)
            y1 = cy + radius * math.sin(start_rad)
            x2 = cx + radius * math.cos(end_rad)
            y2 = cy + radius * math.sin(end_rad)

            large_arc = 1 if angle > 180 else 0

            if donut:
                ix1 = cx + inner_radius * math.cos(start_rad)
                iy1 = cy + inner_radius * math.sin(start_rad)
                ix2 = cx + inner_radius * math.cos(end_rad)
                iy2 = cy + inner_radius * math.sin(end_rad)

                path = f'M {x1} {y1} A {radius} {radius} 0 {large_arc} 1 {x2} {y2} L {ix2} {iy2} A {inner_radius} {inner_radius} 0 {large_arc} 0 {ix1} {iy1} Z'
            else:
                path = f'M {cx} {cy} L {x1} {y1} A {radius} {radius} 0 {large_arc} 1 {x2} {y2} Z'

            svg_parts.append(f'<path d="{path}" fill="{color}"/>')

            current_angle = end_angle

        # Legend
        legend_y = size - 60
        for i, label in enumerate(data.labels[:6]):  # Max 6 legend items
            color = self._colors[i % len(self._colors)]
            x = 40 + (i % 3) * 150
            y = legend_y + (i // 3) * 20
            svg_parts.append(f'<rect x="{x}" y="{y}" width="12" height="12" fill="{color}"/>')
            svg_parts.append(f'<text x="{x + 16}" y="{y + 10}" font-family="{self.config.font_family}" font-size="11" fill="{self.config.text_color}">{label[:20]}</text>')

        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)

    def _generate_line_chart_svg(
        self,
        data: ChartData,
        title: str,
    ) -> str:
        """Generate SVG for line chart."""
        width = self.config.default_width
        height = self.config.default_height
        margin = {"top": 60, "right": 40, "bottom": 80, "left": 60}

        chart_width = width - margin["left"] - margin["right"]
        chart_height = height - margin["top"] - margin["bottom"]

        max_val = max(data.values) if data.values else 1
        min_val = min(data.values) if data.values else 0
        val_range = max_val - min_val or 1

        n_points = len(data.labels)
        x_step = chart_width / (n_points - 1) if n_points > 1 else chart_width

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
            f'<rect width="{width}" height="{height}" fill="{self.config.background_color}"/>',
            f'<text x="{width/2}" y="35" text-anchor="middle" font-family="{self.config.font_family}" font-size="18" font-weight="bold" fill="{self.config.text_color}">{title}</text>',
        ]

        # Grid lines
        if self.config.show_grid:
            for i in range(5):
                y = margin["top"] + (chart_height / 4) * i
                svg_parts.append(f'<line x1="{margin["left"]}" y1="{y}" x2="{width - margin["right"]}" y2="{y}" stroke="#eee" stroke-width="1"/>')

        # Build line path
        points = []
        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            x = margin["left"] + i * x_step
            y = margin["top"] + chart_height - ((value - min_val) / val_range) * chart_height
            points.append(f"{x},{y}")

        color = self._colors[0]
        path = ' '.join([f"{'M' if i == 0 else 'L'} {p}" for i, p in enumerate(points)])
        svg_parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>')

        # Data points
        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            x = margin["left"] + i * x_step
            y = margin["top"] + chart_height - ((value - min_val) / val_range) * chart_height
            svg_parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')

            # X-axis labels (every nth)
            if i % max(1, n_points // 6) == 0:
                svg_parts.append(
                    f'<text x="{x}" y="{height - margin["bottom"] + 20}" text-anchor="middle" font-family="{self.config.font_family}" font-size="10" fill="{self.config.text_color}">{label[:10]}</text>'
                )

        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)

    def _generate_timeline_svg(
        self,
        events: List[TimelineEvent],
        title: str,
    ) -> str:
        """Generate SVG for timeline."""
        width = self.config.default_width
        height = max(400, len(events) * 80)
        margin = 40

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
            f'<rect width="{width}" height="{height}" fill="{self.config.background_color}"/>',
            f'<text x="{width/2}" y="30" text-anchor="middle" font-family="{self.config.font_family}" font-size="18" font-weight="bold" fill="{self.config.text_color}">{title}</text>',
        ]

        # Timeline line
        line_x = 150
        svg_parts.append(f'<line x1="{line_x}" y1="60" x2="{line_x}" y2="{height - 20}" stroke="{self._colors[0]}" stroke-width="3"/>')

        # Events
        for i, event in enumerate(events):
            y = 100 + i * 70
            color = self._colors[i % len(self._colors)]

            # Circle marker
            svg_parts.append(f'<circle cx="{line_x}" cy="{y}" r="8" fill="{color}"/>')

            # Date
            svg_parts.append(f'<text x="{line_x - 20}" y="{y + 5}" text-anchor="end" font-family="{self.config.font_family}" font-size="12" fill="{self.config.text_color}">{event.date}</text>')

            # Title
            svg_parts.append(f'<text x="{line_x + 20}" y="{y}" font-family="{self.config.font_family}" font-size="14" font-weight="bold" fill="{self.config.text_color}">{event.title[:40]}</text>')

            # Description
            if event.description:
                svg_parts.append(f'<text x="{line_x + 20}" y="{y + 18}" font-family="{self.config.font_family}" font-size="11" fill="#666">{event.description[:60]}</text>')

        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)

    # =========================================================================
    # HTML Generation Methods
    # =========================================================================

    def _generate_summary_card_html(
        self,
        stats: Dict[str, Any],
        title: str,
    ) -> str:
        """Generate HTML for summary card."""
        items_html = []
        for i, (key, value) in enumerate(stats.items()):
            color = self._colors[i % len(self._colors)]
            items_html.append(f'''
                <div style="padding: 15px; border-bottom: 1px solid #eee;">
                    <div style="color: #666; font-size: 12px;">{key}</div>
                    <div style="color: {color}; font-size: 24px; font-weight: bold;">{value}</div>
                </div>
            ''')

        return f'''
        <div style="font-family: {self.config.font_family}; background: {self.config.background_color}; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; width: {self.config.card_width}px;">
            <div style="background: {self._colors[0]}; color: white; padding: 15px; font-size: 16px; font-weight: bold;">
                {title}
            </div>
            {''.join(items_html)}
        </div>
        '''

    def _generate_comparison_table_html(
        self,
        items: List[ComparisonItem],
        title: str,
    ) -> str:
        """Generate HTML for comparison table."""
        if not items:
            return '<div>No data</div>'

        # Get all attribute keys
        all_keys = set()
        for item in items:
            all_keys.update(item.attributes.keys())
        keys = sorted(all_keys)

        # Build header
        header = f'<th style="padding: 10px; text-align: left;">Item</th>'
        for key in keys:
            header += f'<th style="padding: 10px; text-align: left;">{key}</th>'
        if any(item.score is not None for item in items):
            header += '<th style="padding: 10px; text-align: left;">Score</th>'

        # Build rows
        rows = []
        for i, item in enumerate(items):
            row_color = "#f9f9f9" if i % 2 == 0 else "white"
            cells = f'<td style="padding: 10px; font-weight: bold;">{item.name}</td>'
            for key in keys:
                cells += f'<td style="padding: 10px;">{item.attributes.get(key, "-")}</td>'
            if item.score is not None:
                cells += f'<td style="padding: 10px; color: {self._colors[0]}; font-weight: bold;">{item.score}</td>'
            rows.append(f'<tr style="background: {row_color};">{cells}</tr>')

        return f'''
        <div style="font-family: {self.config.font_family}; overflow: auto;">
            <h3 style="color: {self.config.text_color}; margin-bottom: 15px;">{title}</h3>
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd;">
                <thead style="background: {self._colors[0]}; color: white;">
                    <tr>{header}</tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </div>
        '''


# =============================================================================
# Convenience Functions
# =============================================================================

def create_bar_chart(
    labels: List[str],
    values: List[Union[int, float]],
    title: str = "Bar Chart",
) -> VisualOutput:
    """
    Create a bar chart.

    Args:
        labels: Bar labels
        values: Bar values
        title: Chart title

    Returns:
        VisualOutput with chart
    """
    generator = VisualGenerator()
    data = ChartData(labels=labels, values=values)
    return generator.create_bar_chart(data, title)


def create_pie_chart(
    labels: List[str],
    values: List[Union[int, float]],
    title: str = "Pie Chart",
) -> VisualOutput:
    """
    Create a pie chart.

    Args:
        labels: Slice labels
        values: Slice values
        title: Chart title

    Returns:
        VisualOutput with chart
    """
    generator = VisualGenerator()
    data = ChartData(labels=labels, values=values)
    return generator.create_pie_chart(data, title)


def create_summary_card(
    stats: Dict[str, Any],
    title: str = "Summary",
) -> VisualOutput:
    """
    Create a summary statistics card.

    Args:
        stats: Statistics dictionary
        title: Card title

    Returns:
        VisualOutput with card
    """
    generator = VisualGenerator()
    return generator.create_summary_card(stats, title)


# =============================================================================
# Self-Test
# =============================================================================

def self_test() -> bool:
    """Run self-tests for visual generator."""
    print("Running Visual Generator self-tests...")

    generator = VisualGenerator()

    # Test bar chart
    data = ChartData(
        labels=["A", "B", "C", "D"],
        values=[10, 25, 15, 30],
    )
    chart = generator.create_bar_chart(data, "Test Bar Chart")
    assert chart.visual_type == VisualType.CHART
    assert "<svg" in chart.content
    print("  [PASS] Bar chart")

    # Test pie chart
    chart = generator.create_pie_chart(data, "Test Pie Chart")
    assert "<svg" in chart.content
    print("  [PASS] Pie chart")

    # Test donut chart
    chart = generator.create_pie_chart(data, "Test Donut", donut=True)
    assert "<svg" in chart.content
    print("  [PASS] Donut chart")

    # Test line chart
    chart = generator.create_line_chart(data, "Test Line Chart")
    assert "<svg" in chart.content
    print("  [PASS] Line chart")

    # Test summary card
    stats = {"Total": 100, "Average": 25.5, "Max": 50}
    card = generator.create_summary_card(stats, "Statistics")
    assert card.visual_type == VisualType.SUMMARY_CARD
    assert "Statistics" in card.content
    print("  [PASS] Summary card")

    # Test timeline
    events = [
        TimelineEvent("2025-01", "Event A", "Description A"),
        TimelineEvent("2025-03", "Event B", "Description B"),
    ]
    timeline = generator.create_timeline(events, "Project Timeline")
    assert "<svg" in timeline.content
    print("  [PASS] Timeline")

    # Test comparison table
    items = [
        ComparisonItem("Item A", {"Price": "$10", "Rating": 4}, score=8.5),
        ComparisonItem("Item B", {"Price": "$15", "Rating": 5}, score=9.0),
    ]
    table = generator.create_comparison_table(items, "Comparison")
    assert "<table" in table.content
    print("  [PASS] Comparison table")

    # Test convenience functions
    chart = create_bar_chart(["X", "Y"], [5, 10], "Quick Chart")
    assert chart.content
    print("  [PASS] create_bar_chart convenience")

    chart = create_pie_chart(["X", "Y"], [60, 40], "Quick Pie")
    assert chart.content
    print("  [PASS] create_pie_chart convenience")

    card = create_summary_card({"Key": "Value"}, "Quick Card")
    assert card.content
    print("  [PASS] create_summary_card convenience")

    # Test output serialization
    data = chart.to_dict()
    assert "visual_type" in data
    print("  [PASS] Output serialization")

    print("\nAll Visual Generator self-tests PASSED!")
    return True


if __name__ == "__main__":
    self_test()
