"""
GEMINI-ARCH 2A: Python data analysis and chart generation.

Full Python execution for data analysis. Uses subprocess to run
analysis scripts that import Pandas, NumPy, Matplotlib.
Generates real charts from real data — not LLM-described chart text.

This is the Gemini approach: code generates charts from evidence data.
"""

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

# LAW VI: Configuration from env
PG_ANALYSIS_SCRIPT_TIMEOUT = int(resolve("PG_ANALYSIS_SCRIPT_TIMEOUT"))
PG_CHART_DPI = int(resolve("PG_CHART_DPI"))
PG_CHART_MAX_WIDTH = int(resolve("PG_CHART_MAX_WIDTH"))


async def analyze_structured_data(
    client: OpenRouterClient,
    data_points: list[dict],
    analysis_type: str,
    research_context: str = "",
) -> dict:
    """Run Python data analysis on structured evidence data.

    Asks Qwen to write a Python script tailored to the data, then
    executes it via subprocess. The script generates Matplotlib charts
    as base64 PNG images and computes summary statistics.

    Args:
        client: OpenRouter LLM client for script generation.
        data_points: Structured data points from evidence analysis.
        analysis_type: One of "comparison", "time_series", "distribution", "ranking".
        research_context: Brief description of the research topic for chart titles.

    Returns:
        {"charts": [...], "tables": [...], "insights": [...]}
        charts: [{"title": str, "image_base64": str, "description": str, "citations": [str]}]
        tables: [{"headers": [str], "rows": [[str]], "caption": str}]
        insights: [str]
    """
    if not data_points:
        logger.warning(
            "[polaris graph] GEMINI-ARCH 2A: analyze_structured_data() called "
            "with empty data_points list — returning empty result"
        )
        return {"charts": [], "tables": [], "insights": []}

    # Generate analysis script via LLM
    script = await _generate_analysis_script(
        client=client,
        data_points=data_points,
        analysis_type=analysis_type,
        research_context=research_context,
    )

    if not script or len(script.strip()) < 50:
        logger.warning(
            "[polaris graph] GEMINI-ARCH 2A: Script generation returned empty/short output"
        )
        return {"charts": [], "tables": [], "insights": []}

    # Execute the script
    result = await _execute_analysis_script(script)

    return result


async def _generate_analysis_script(
    client: OpenRouterClient,
    data_points: list[dict],
    analysis_type: str,
    research_context: str = "",
) -> str:
    """Ask Qwen to write a Python analysis script for the data.

    The script must output JSON to stdout with charts as base64 images.
    """
    # Limit data preview to prevent prompt overflow
    preview = json.dumps(data_points[:20], indent=2, default=str)
    if len(preview) > 5000:
        preview = preview[:5000] + "\n... (truncated)"

    prompt = f"""Write a Python script that analyzes this data and outputs JSON results.

Data ({len(data_points)} points):
{preview}

Analysis type: {analysis_type}
Context: {research_context}

Requirements:
- Import json, sys, io, base64
- Import pandas as pd, numpy as np, matplotlib
- Set matplotlib.use('Agg') BEFORE importing pyplot
- Import matplotlib.pyplot as plt
- Parse the data from a JSON string embedded in the script
- Analyze the data: compute statistics, identify trends, rank entities, detect outliers
- Generate 1-2 matplotlib charts as base64 PNG images:
  - Use white background, clear labels, readable font sizes
  - Add proper axis labels and a descriptive title
  - Use {PG_CHART_DPI} DPI, max width {PG_CHART_MAX_WIDTH}px
  - Save to BytesIO, encode as base64
- Output ONLY valid JSON to stdout (no other print statements):
  {{"charts": [{{"title": "...", "image_base64": "...", "description": "..."}}],
   "tables": [{{"headers": ["col1", "col2"], "rows": [["val1", "val2"]], "caption": "..."}}],
   "insights": ["key finding 1", "key finding 2"]}}
- Handle missing/inconsistent data gracefully with try/except
- Do NOT use plt.show() — only save to buffer
"""
    system = (
        "You are a data analyst writing clean Python scripts. "
        "Output ONLY the Python code, no markdown fences, no explanations. "
        "The script must be self-contained and executable."
    )

    response = await client.generate(
        prompt=prompt,
        system=system,
        max_tokens=4096,
        temperature=0.3,
    )

    script = response.content.strip()

    # Strip markdown code fences if present (handles ```python, ```py, whitespace)
    lines = script.split("\n")
    if lines and re.match(r'^\s*```', lines[0]):
        lines = lines[1:]  # Remove opening fence
        # Remove closing fence if present
        if lines and re.match(r'^\s*```\s*$', lines[-1]):
            lines = lines[:-1]
        script = "\n".join(lines)

    # FIX-3B: Strip markdown-formatted lines that LLM may inject as comments.
    # These look like: "* **Label:** text", "*   Configure..." or "- **Note:**"
    # which are not valid Python and cause SyntaxError.
    cleaned_lines = []
    in_string = False
    for line in script.split("\n"):
        stripped = line.strip()
        # Track triple-quote strings to avoid false positives
        tq_count = stripped.count('"""') + stripped.count("'''")
        if tq_count % 2 == 1:
            in_string = not in_string
        if in_string:
            cleaned_lines.append(line)
            continue
        # Skip markdown bullet lines: * text, - **text**, etc.
        # But NOT valid Python like `*args` or `-value`
        if re.match(r'^\*\s{2,}', stripped):  # "* " with 2+ spaces = markdown bullet
            continue
        if re.match(r'^[*\-]\s+\*\*', stripped):  # "* **Bold**" or "- **Bold**"
            continue
        if re.match(r'^\*\*\w+', stripped):  # "**Bold" at line start
            continue
        if re.match(r'^[*\-]\s+[A-Z]', stripped) and '=' not in stripped and '(' not in stripped:
            # Markdown bullet with Capital letter start, no assignment or call
            continue
        cleaned_lines.append(line)
    script = "\n".join(cleaned_lines)

    return script


async def _execute_analysis_script(script: str) -> dict:
    """Execute a Python analysis script and parse its JSON output.

    Uses subprocess for isolation. The script writes JSON to stdout.

    Args:
        script: Complete Python script as a string.

    Returns:
        Parsed JSON output from the script, or empty result on failure.
    """
    empty_result = {"charts": [], "tables": [], "insights": []}

    # FIX-1: Unconditionally enforce Agg backend — LLM may omit it,
    # causing Windows subprocess hangs when Tk tries to open a display.
    agg_preamble = "import matplotlib\nmatplotlib.use('Agg')\n"
    if "matplotlib.use(" not in script:
        script = agg_preamble + script

    # Write script to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(script)
            script_path = f.name
    except Exception as exc:
        logger.error(
            "[polaris graph] GEMINI-ARCH 2A: Failed to write temp script: %s",
            str(exc)[:200],
        )
        return empty_result

    try:
        # Run in subprocess with timeout
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=PG_ANALYSIS_SCRIPT_TIMEOUT,
            cwd=tempfile.gettempdir(),
        )

        if proc.returncode != 0:
            logger.warning(
                "[polaris graph] GEMINI-ARCH 2A: Analysis script failed "
                "(exit=%d): stderr=%s",
                proc.returncode,
                proc.stderr[:500] if proc.stderr else "no stderr",
            )
            return empty_result

        # Parse JSON output
        stdout = proc.stdout.strip()
        if not stdout:
            logger.warning(
                "[polaris graph] GEMINI-ARCH 2A: Script produced no stdout output"
            )
            return empty_result

        result = json.loads(stdout)

        # Validate structure
        charts = result.get("charts", [])
        tables = result.get("tables", [])
        insights = result.get("insights", [])

        logger.info(
            "[polaris graph] GEMINI-ARCH 2A: Analysis complete: "
            "%d charts, %d tables, %d insights",
            len(charts), len(tables), len(insights),
        )

        return {
            "charts": charts,
            "tables": tables,
            "insights": insights,
        }

    except subprocess.TimeoutExpired:
        logger.warning(
            "[polaris graph] GEMINI-ARCH 2A: Script timed out after %ds",
            PG_ANALYSIS_SCRIPT_TIMEOUT,
        )
        return empty_result

    except json.JSONDecodeError as exc:
        logger.warning(
            "[polaris graph] GEMINI-ARCH 2A: Script output is not valid JSON: %s",
            str(exc)[:200],
        )
        return empty_result

    except Exception as exc:
        logger.warning(
            "[polaris graph] GEMINI-ARCH 2A: Script execution failed: %s",
            str(exc)[:200],
        )
        return empty_result

    finally:
        # Clean up temp file
        try:
            os.unlink(script_path)
        except OSError:
            pass


def format_chart_markdown(
    chart: dict,
    figure_number: int,
    citation_refs: list[str] | None = None,
) -> str:
    """Format a chart as markdown with base64 image and caption.

    Args:
        chart: {"title": str, "image_base64": str, "description": str}
        figure_number: Sequential figure number.
        citation_refs: Optional list of citation references for the caption.

    Returns:
        Markdown string with embedded image and caption.
    """
    title = chart.get("title", f"Figure {figure_number}")
    image_b64 = chart.get("image_base64", "")
    description = chart.get("description", "")

    if not image_b64:
        return ""

    # FIX-9: Validate PNG magic bytes before embedding — malformed base64
    # breaks rendering and DOCX export.
    try:
        decoded = base64.b64decode(image_b64)
        if not decoded[:4] == b'\x89PNG':
            logger.warning(
                "[polaris graph] GEMINI-ARCH 2A: Chart '%s' has invalid PNG "
                "magic bytes — skipping",
                title,
            )
            return ""
    except Exception:
        logger.warning(
            "[polaris graph] GEMINI-ARCH 2A: Chart '%s' base64 decode failed "
            "— skipping",
            title,
        )
        return ""

    cite_str = ""
    if citation_refs:
        cite_str = " Data from " + ", ".join(citation_refs) + "."

    return (
        f"\n\n![{title}](data:image/png;base64,{image_b64})\n"
        f"*Figure {figure_number}: {description}{cite_str}*\n\n"
    )


def format_table_markdown(
    table: dict,
    table_number: int,
) -> str:
    """Format structured data as a markdown table.

    Args:
        table: {"headers": [str], "rows": [[str]], "caption": str}
        table_number: Sequential table number.

    Returns:
        Markdown table string.
    """
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    caption = table.get("caption", f"Table {table_number}")

    if not headers or not rows:
        return ""

    # Build markdown table
    lines = []
    lines.append("| " + " | ".join(str(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        # Pad or truncate row to match header count
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(str(v) for v in padded[:len(headers)]) + " |")

    lines.append(f"\n*Table {table_number}: {caption}*\n")

    return "\n".join(lines)
