"""Build a high-resolution PDF of all POLARIS frontend walkthrough screenshots.

Each page = 1 screenshot at full resolution, landscape A3 for maximum clarity.
Includes a title page and per-page captions.
"""

import os
import sys
from pathlib import Path

from fpdf import FPDF
from PIL import Image


OUTPUT_DIR = Path(os.getenv("POLARIS_OUTPUT_DIR", "outputs"))
PDF_PATH = OUTPUT_DIR / "polaris_frontend_walkthrough.pdf"

SCREENSHOTS = [
    ("walkthrough_01_landing_dark.png", "Page 1: Landing — Report View, Researcher Mode, Dark Theme",
     "Default landing state. Shows the POLARIS header bar with role selector (Researcher/Operator), "
     "Pipeline Console badge, theme toggle (moon icon), SSE status (Ready), event counter (105 events), "
     "cost tracker ($0.000), reconnect counter, tab count, memory status, and Sovereign badge. "
     "Below: the research query in a teal banner, 6 navigation tabs (Research, Evidence 126, Report, "
     "Memory, Pipelines, Advanced), and the Report view with verification banner, 5-metric stats dashboard, "
     "table of contents sidebar, and rendered report body."),

    ("walkthrough_02_landing_light.png", "Page 2: Landing — Report View, Researcher Mode, Light Theme",
     "Same view after clicking the theme toggle. All colors invert: dark header becomes white, "
     "dark body becomes light gray, text flips from white-on-dark to dark-on-light. "
     "Demonstrates full theme coverage — every component respects the data-theme attribute."),

    ("walkthrough_03_landing_operator.png", "Page 3: Landing — Report View, Operator Mode",
     "Same view after switching role to Operator. The role chip changes, and operator-specific "
     "UI elements appear. The RBAC system controls which components are visible per role."),

    ("walkthrough_04_research.png", "Page 4: Research View",
     "The Research tab shows the pipeline execution timeline. Left panel: phase blocks "
     "(Plan, Search, STORM Interviews, Analyze, Verify, Evaluate, Synthesize) each expandable "
     "with reasoning streams. Right panel: a live reasoning stream showing the AI's chain-of-thought "
     "during research. Phase blocks have colored status indicators and expand/collapse headers."),

    ("walkthrough_05_evidence.png", "Page 5: Evidence View",
     "Two-panel layout. Left: a force-directed evidence relationship graph (D3.js) showing "
     "connections between evidence pieces with tier-colored nodes (GOLD/SILVER/BRONZE). "
     "Right: scrollable evidence cards with tier badges, source URLs, relevance scores, "
     "and verification status. Filter chips at top for tier filtering. Evidence count badge on tab."),

    ("walkthrough_06_report.png", "Page 6: Report View (Detail)",
     "The main deliverable view. Green verification banner: '92 claims verified from 8 sources — "
     "82% verification rate across 8,400 words'. Stats dashboard: 82% Claims Verified, "
     "126 Evidence Pieces, 8 Sources Cited, 8,400 Words, 2 Verification Passes. "
     "Two-column layout: Table of Contents sidebar (sticky) + rendered report with H1 title, "
     "Conflicts(2) badge, numbered sections, and inline [1] citation markers."),

    ("walkthrough_07_memory.png", "Page 7: Memory View",
     "Tri-level knowledge management interface. Header: GOLD 0 / SILVER 0 / BRONZE 0 tier badges "
     "with Online status indicator and Refresh button. Two panels: Knowledge Clusters (left) "
     "for domain-grouped memories, and searchable Memory Items list (right). "
     "Bottom: collapsible Knowledge Timeline for chronological memory tracking. "
     "Empty state shown — populates during pipeline execution."),

    ("walkthrough_08_pipelines.png", "Page 8: Pipelines View (DAG Editor)",
     "Visual pipeline builder. Left sidebar: 5 pipeline templates (Academic Focus, Compliance Review, "
     "Multi-Vector Deep Analysis, Quick Scan, Standard Research) each with description and "
     "'Use Template' button. Main canvas: toolbar (Save, Validate, Run, Wizard, +, -, Fit) "
     "with empty canvas placeholder. Bottom: '+ New Pipeline' button. "
     "Canvas supports drag-and-drop node placement and edge drawing."),

    ("walkthrough_09_adv_queries.png", "Page 9: Advanced — Queries Sub-Tab",
     "Search strategy inspector. Shows: Search Strategy type (multi_perspective_storm), "
     "Key Concepts as teal chips (PFAS, activated carbon, ion exchange, reverse osmosis, "
     "nanofiltration, cost analysis), Search Engines horizontal bar chart (Serper 64, "
     "OpenAlex 5, Exa 4, S2 3, DuckDuckGo 3), and full list of 12 Planned Queries "
     "with actual search strings used by the pipeline."),

    ("walkthrough_10_adv_sources.png", "Page 10: Advanced — Sources Sub-Tab",
     "Source provenance dashboard. Fetch Pipeline card: 5 SUCCESS / 1 SNIPPET / 2 FAILED. "
     "Source Domains list (8): doi.org, epa.gov, waterworld.com, sciencedirect.com, pubs.acs.org, "
     "blocked-domain.example.com, awwa.org, nature.com. Perspective Distribution bar chart: "
     "technical(3), economic(2), regulatory(2), environmental(2), public_health(2), comparative(1). "
     "Missing Perspectives section flags coverage gaps."),

    ("walkthrough_11_adv_storm.png", "Page 11: Advanced — STORM Sub-Tab",
     "STORM (Synthesis of Topic Outlines through Retrieval and Multi-perspective questioning) "
     "persona interface. 6 AI personas in 3x2 card grid: Dr. Sarah Chen (Environmental Engineering), "
     "Michael Torres (Water Utility Finance), Jennifer Walsh (EPA Program Lead), "
     "Prof. Raj Patel (Environmental Toxicology), Dr. Lisa Kim (Public Health Epidemiology), "
     "Dr. James Wright (Environmental History). Each card: avatar, title, research focus, "
     "interview/findings counts. Below: full Interview Transcript with color-coded Q&A exchanges."),

    ("walkthrough_12_adv_trace.png", "Page 12: Advanced — Trace Sub-Tab",
     "Full JSONL observability timeline. Filter chips: All(105), node(0), llm_call(24), "
     "evidence(23), reasoning_capture(11), llm_detail(2), storm_transcript(6), pipeline_start(1), "
     "node_start(7), node_end(7), query(1), search_result(12), fetch(8), iteration_decision(1), "
     "quality_gate(2). Chronological event stream with timestamps, color-coded event type badges, "
     "and graph node labels. Shows full pipeline execution flow from start to finish."),

    ("walkthrough_13_adv_cost.png", "Page 13: Advanced — Cost Sub-Tab",
     "LLM cost transparency dashboard. Usage Summary 2x2 grid: 24 Total Calls, 93.0K Input Tokens, "
     "30.2K Output Tokens, $0.000 Total Cost. Model Distribution: moonshotai/kimi-k2-instruct "
     "at 2 calls (100%). Recent LLM Calls table: section_write (4200->2400 tokens), "
     "plan:query_generation (1250->2800 tokens). Full per-call cost breakdown for budget tracking."),
]


def _sanitize(text):
    """Replace Unicode chars that latin-1 core fonts cannot render."""
    return (text
            .replace("\u2014", " - ")   # em-dash
            .replace("\u2013", " - ")   # en-dash
            .replace("\u2018", "'")     # left single quote
            .replace("\u2019", "'")     # right single quote
            .replace("\u201c", '"')     # left double quote
            .replace("\u201d", '"')     # right double quote
            .replace("\u2026", "...")   # ellipsis
            .replace("\u2192", "->")   # arrow
            )


def build_pdf():
    """Build landscape PDF with one screenshot per page at maximum resolution."""
    pdf = FPDF(orientation="L", unit="mm", format="A3")
    pdf.set_auto_page_break(auto=False)

    page_w = 420  # A3 landscape width mm
    page_h = 297  # A3 landscape height mm
    margin = 10

    # ── Title Page ──────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 36)
    pdf.set_y(60)
    pdf.cell(page_w - 2 * margin, 20, _sanitize("POLARIS"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 20)
    pdf.cell(page_w - 2 * margin, 14, _sanitize("Autonomous Research Pipeline & Intelligence Dashboard"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(page_w - 2 * margin, 12, _sanitize("Frontend UI Walkthrough - 13 Pages, All Views & Modes"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)

    pdf.set_font("Helvetica", "", 12)
    lines = [
        "This document contains pixel-perfect screenshots of every view, theme, and mode",
        "in the POLARIS frontend dashboard. Each page shows one full-viewport capture at",
        "1440x900 resolution (desktop). The screenshots are taken from a live running instance",
        "with real mock data injected to show all UI components in their populated states.",
        "",
        "Views covered: Landing (3 variants), Research, Evidence, Report, Memory,",
        "Pipelines, Advanced (Queries, Sources, STORM, Trace, Cost).",
        "",
        "Prepared for external UI/UX design review.",
        f"Total screenshots: {len(SCREENSHOTS)}",
    ]
    for line in lines:
        pdf.cell(page_w - 2 * margin, 8, _sanitize(line), align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Screenshot Pages ────────────────────────────────────────
    for filename, title, description in SCREENSHOTS:
        img_path = OUTPUT_DIR / filename
        if not img_path.exists():
            print(f"WARNING: Missing {img_path}, skipping")
            continue

        with Image.open(img_path) as img:
            img_w, img_h = img.size

        pdf.add_page()

        # Title bar
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_xy(margin, margin)
        pdf.cell(page_w - 2 * margin, 8, _sanitize(title), new_x="LMARGIN", new_y="NEXT")

        # Image — maximize area below title, above description
        title_h = 12
        desc_h = 32
        avail_w = page_w - 2 * margin
        avail_h = page_h - 2 * margin - title_h - desc_h

        # Scale image to fit available area while preserving aspect ratio
        scale_w = avail_w / (img_w * 0.264583)  # px to mm at 96dpi: 1px = 0.264583mm
        scale_h = avail_h / (img_h * 0.264583)
        scale = min(scale_w, scale_h, 1.5)  # cap upscale at 1.5x

        render_w = img_w * 0.264583 * scale
        render_h = img_h * 0.264583 * scale

        # Center horizontally
        x_offset = margin + (avail_w - render_w) / 2
        y_offset = margin + title_h

        pdf.image(str(img_path), x=x_offset, y=y_offset, w=render_w, h=render_h)

        # Description below image
        desc_y = y_offset + render_h + 2
        pdf.set_xy(margin, desc_y)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(page_w - 2 * margin, 4.5, _sanitize(description))

    pdf.output(str(PDF_PATH))
    file_size = PDF_PATH.stat().st_size
    print(f"PDF saved: {PDF_PATH}")
    print(f"Size: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")
    print(f"Pages: {len(SCREENSHOTS) + 1} (1 title + {len(SCREENSHOTS)} screenshots)")


if __name__ == "__main__":
    build_pdf()
