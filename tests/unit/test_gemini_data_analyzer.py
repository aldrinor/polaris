#!/usr/bin/env python3
"""
Unit tests for GEMINI-ARCH 2A data analyzer.

Tests:
- format_chart_markdown: basic, with citations, empty base64
- format_table_markdown: basic, empty, row padding
- _execute_analysis_script: real matplotlib, bad script, timeout

Run:
    pytest tests/unit/test_gemini_data_analyzer.py -v
"""

import asyncio
import base64
import os
import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.polaris_graph.tools.data_analyzer import (
    format_chart_markdown,
    format_table_markdown,
    _execute_analysis_script,
)

# Valid 1x1 PNG for chart tests (FIX-9 validates PNG magic bytes)
import struct
import zlib

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
# format_chart_markdown
# ---------------------------------------------------------------------------


class TestFormatChartMarkdown:
    """Tests for format_chart_markdown."""

    def test_format_chart_markdown_basic(self):
        """Basic chart markdown: embedded base64 image and captioned figure."""
        chart = {
            "title": "Test Chart",
            "image_base64": _VALID_PNG_B64,
            "description": "A test chart",
        }
        result = format_chart_markdown(chart, figure_number=1)
        assert f"![Test Chart](data:image/png;base64,{_VALID_PNG_B64})" in result
        assert "*Figure 1: A test chart*" in result

    def test_format_chart_markdown_with_citations(self):
        """Citation refs appended to figure caption."""
        chart = {
            "title": "Cited Chart",
            "image_base64": _VALID_PNG_B64,
            "description": "Chart with sources",
        }
        result = format_chart_markdown(chart, figure_number=2, citation_refs=["[1]", "[3]"])
        assert "Data from [1], [3]." in result
        assert "*Figure 2:" in result

    def test_format_chart_markdown_empty_base64(self):
        """Empty image_base64 returns empty string (no broken image tag)."""
        chart = {
            "title": "No Image",
            "image_base64": "",
            "description": "Missing image",
        }
        result = format_chart_markdown(chart, figure_number=1)
        assert result == ""

    def test_format_chart_markdown_missing_base64_key(self):
        """Missing image_base64 key returns empty string."""
        chart = {"title": "No Key", "description": "Missing key entirely"}
        result = format_chart_markdown(chart, figure_number=1)
        assert result == ""

    def test_format_chart_markdown_no_citations(self):
        """No citation_refs omits 'Data from' text."""
        chart = {
            "title": "Solo",
            "image_base64": _VALID_PNG_B64,
            "description": "Standalone",
        }
        result = format_chart_markdown(chart, figure_number=5)
        assert "Data from" not in result
        assert "*Figure 5: Standalone*" in result


# ---------------------------------------------------------------------------
# format_table_markdown
# ---------------------------------------------------------------------------


class TestFormatTableMarkdown:
    """Tests for format_table_markdown."""

    def test_format_table_markdown_basic(self):
        """Basic markdown table with headers, separator, rows, and caption."""
        table = {
            "headers": ["Name", "Value"],
            "rows": [["A", "1"], ["B", "2"]],
            "caption": "Test data",
        }
        result = format_table_markdown(table, table_number=1)
        assert "| Name | Value |" in result
        assert "| --- | --- |" in result
        assert "| A | 1 |" in result
        assert "| B | 2 |" in result
        assert "*Table 1: Test data*" in result

    def test_format_table_markdown_empty_headers(self):
        """Empty headers returns empty string."""
        table = {"headers": [], "rows": [["A", "1"]], "caption": "No headers"}
        result = format_table_markdown(table, table_number=1)
        assert result == ""

    def test_format_table_markdown_empty_rows(self):
        """Empty rows returns empty string."""
        table = {"headers": ["Name", "Value"], "rows": [], "caption": "No rows"}
        result = format_table_markdown(table, table_number=1)
        assert result == ""

    def test_format_table_markdown_row_padding(self):
        """Rows shorter than headers are padded with empty strings."""
        table = {
            "headers": ["A", "B", "C"],
            "rows": [["x"]],
            "caption": "Short row",
        }
        result = format_table_markdown(table, table_number=3)
        # Row should be padded to match 3 headers
        assert "| x |  |  |" in result
        assert "*Table 3: Short row*" in result

    def test_format_table_markdown_row_truncation(self):
        """Rows longer than headers are truncated to header count."""
        table = {
            "headers": ["A"],
            "rows": [["x", "y", "z"]],
            "caption": "Long row",
        }
        result = format_table_markdown(table, table_number=1)
        assert "| x |" in result
        # Extra columns should NOT appear
        assert "y" not in result
        assert "z" not in result


# ---------------------------------------------------------------------------
# _execute_analysis_script (async)
# ---------------------------------------------------------------------------


class TestExecuteAnalysisScript:
    """Tests for _execute_analysis_script (subprocess execution)."""

    @pytest.mark.asyncio
    async def test_execute_analysis_script_real_matplotlib(self):
        """Real matplotlib script produces valid base64 PNG and structured JSON."""
        script = (
            "import json, sys, io, base64\n"
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "fig, ax = plt.subplots()\n"
            "ax.bar(['A', 'B', 'C'], [3, 7, 5])\n"
            "ax.set_title('Test Chart')\n"
            "buf = io.BytesIO()\n"
            "fig.savefig(buf, format='png', dpi=72)\n"
            "buf.seek(0)\n"
            "img_b64 = base64.b64encode(buf.read()).decode()\n"
            "plt.close()\n"
            "\n"
            "result = {\n"
            '    "charts": [{"title": "Test Chart", "image_base64": img_b64, "description": "Bar chart"}],\n'
            '    "tables": [{"headers": ["Item", "Count"], "rows": [["A", "3"], ["B", "7"]], "caption": "Data"}],\n'
            '    "insights": ["B has the highest count"]\n'
            "}\n"
            "print(json.dumps(result))\n"
        )

        result = await _execute_analysis_script(script)

        # Structure checks
        assert "charts" in result
        assert "tables" in result
        assert "insights" in result

        # Charts
        assert len(result["charts"]) == 1
        chart = result["charts"][0]
        assert chart["title"] == "Test Chart"
        assert chart["description"] == "Bar chart"

        # Validate base64 is decodable and starts with PNG header
        raw = base64.b64decode(chart["image_base64"])
        png_header = b"\x89PNG\r\n\x1a\n"
        assert raw[:8] == png_header, "Decoded image does not start with PNG header"

        # Tables
        assert len(result["tables"]) == 1
        assert result["tables"][0]["headers"] == ["Item", "Count"]

        # Insights
        assert len(result["insights"]) == 1
        assert "highest" in result["insights"][0].lower()

    @pytest.mark.asyncio
    async def test_execute_analysis_script_bad_script(self):
        """Script with syntax error returns empty result dict."""
        bad_script = "def broken(\n  this is not valid python"

        result = await _execute_analysis_script(bad_script)

        assert result == {"charts": [], "tables": [], "insights": []}

    @pytest.mark.asyncio
    async def test_execute_analysis_script_no_output(self):
        """Script that produces no stdout returns empty result."""
        silent_script = "x = 1 + 1\n"

        result = await _execute_analysis_script(silent_script)

        assert result == {"charts": [], "tables": [], "insights": []}

    @pytest.mark.asyncio
    async def test_execute_analysis_script_invalid_json(self):
        """Script that prints non-JSON returns empty result."""
        non_json_script = 'print("this is not json")\n'

        result = await _execute_analysis_script(non_json_script)

        assert result == {"charts": [], "tables": [], "insights": []}

    @pytest.mark.asyncio
    async def test_execute_analysis_script_timeout(self):
        """Script that exceeds timeout returns empty result."""
        # Override timeout to 2s for a fast test
        original_timeout = os.environ.get("PG_ANALYSIS_SCRIPT_TIMEOUT")
        os.environ["PG_ANALYSIS_SCRIPT_TIMEOUT"] = "2"

        # Reload the module-level constant by importing the module and patching
        import src.polaris_graph.tools.data_analyzer as analyzer_mod
        saved_timeout = analyzer_mod.PG_ANALYSIS_SCRIPT_TIMEOUT
        analyzer_mod.PG_ANALYSIS_SCRIPT_TIMEOUT = 2

        try:
            sleep_script = "import time\ntime.sleep(60)\nprint('{}')\n"
            result = await _execute_analysis_script(sleep_script)
            assert result == {"charts": [], "tables": [], "insights": []}
        finally:
            # Restore
            analyzer_mod.PG_ANALYSIS_SCRIPT_TIMEOUT = saved_timeout
            if original_timeout is None:
                os.environ.pop("PG_ANALYSIS_SCRIPT_TIMEOUT", None)
            else:
                os.environ["PG_ANALYSIS_SCRIPT_TIMEOUT"] = original_timeout

    @pytest.mark.asyncio
    async def test_execute_analysis_script_partial_keys(self):
        """Script returning partial JSON (missing keys) still works via .get() defaults."""
        partial_script = 'import json\nprint(json.dumps({"charts": []}))\n'

        result = await _execute_analysis_script(partial_script)

        assert result["charts"] == []
        assert result["tables"] == []
        assert result["insights"] == []
