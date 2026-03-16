"""
Playwright-based comprehensive visual audit of the POLARIS live dashboard.

Launches the live server with injected test trace data, screenshots every tab
at multiple resolutions, captures key components, and runs 40 automated visual
checks covering layout, overview, queries, sources, STORM, evidence, graph,
report, and the right evidence panel.

Outputs:
    - Screenshots:    outputs/visual_overhaul/{round}/  (PNG per tab + component)
    - JSON report:    outputs/visual_overhaul/audit_report.json
    - Console:        Summary table of 40 checks with PASS/FAIL

Usage:
    python scripts/playwright_visual_overhaul.py
    python scripts/playwright_visual_overhaul.py --port 8765 --timeout 30

Zero POLARIS src imports. Uses subprocess for server lifecycle management.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration (LAW VI)
# ---------------------------------------------------------------------------
DEFAULT_PORT = int(os.getenv("PG_VISUAL_AUDIT_PORT", "8765"))
DEFAULT_TIMEOUT = int(os.getenv("PG_VISUAL_AUDIT_TIMEOUT", "30"))
INJECT_SCRIPT = "scripts/inject_test_trace.py"
SERVER_SCRIPT = "scripts/live_server.py"
TRACE_FILE = "logs/pg_trace_DASHBOARD_TEST.jsonl"
OUTPUT_DIR = Path("outputs/visual_overhaul")
DASHBOARD_URL_TEMPLATE = "http://localhost:{port}/"

# Resolutions for responsive testing
RESOLUTIONS = {
    "desktop": {"width": 1920, "height": 1080},
    "tablet_landscape": {"width": 1024, "height": 768},
    "tablet_portrait": {"width": 768, "height": 1024},
}

# All 9 tab identifiers matching data-tab attributes in the dashboard
TABS = [
    "overview", "queries", "sources", "storm",
    "evidence", "evgraph", "report", "trace", "fullreport",
]


# ---------------------------------------------------------------------------
# Check result accumulator
# ---------------------------------------------------------------------------
class AuditResult:
    """Accumulates check results and produces a structured report."""

    def __init__(self):
        self.checks = []
        self.screenshots = []
        self.start_time = datetime.now(timezone.utc)

    def add_check(
        self,
        check_num: int,
        name: str,
        passed: bool,
        detail: str = "",
        category: str = "",
    ) -> None:
        status = "PASS" if passed else "FAIL"
        icon = "[+]" if passed else "[-]"
        self.checks.append({
            "check": check_num,
            "name": name,
            "category": category,
            "passed": passed,
            "detail": detail,
        })
        print(f"  {icon} Check {check_num:2d}: {name} -- {status}"
              + (f" ({detail})" if detail else ""))

    def add_screenshot(self, path: str, description: str) -> None:
        self.screenshots.append({"path": path, "description": description})

    def to_dict(self) -> dict:
        end_time = datetime.now(timezone.utc)
        passed = sum(1 for c in self.checks if c["passed"])
        failed = sum(1 for c in self.checks if not c["passed"])
        return {
            "audit_tool": "playwright_visual_overhaul",
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - self.start_time).total_seconds(),
            "total_checks": len(self.checks),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / max(len(self.checks), 1) * 100, 1),
            "checks": self.checks,
            "screenshots": self.screenshots,
        }


# ---------------------------------------------------------------------------
# Server lifecycle helpers
# ---------------------------------------------------------------------------
def inject_test_trace() -> bool:
    """Run inject_test_trace.py to generate synthetic JSONL trace data."""
    print("[1/4] Injecting test trace data...")
    result = subprocess.run(
        [sys.executable, INJECT_SCRIPT],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"  ERROR: inject_test_trace.py failed:\n{result.stderr}")
        return False
    print(f"  OK: {result.stdout.strip().splitlines()[0] if result.stdout.strip() else 'done'}")
    return True


def kill_existing_server(port: int) -> None:
    """Kill any existing process on the given port (Windows-specific)."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
             f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"  Killed existing process on port {port}")
    except Exception:
        pass


def start_server(port: int) -> subprocess.Popen:
    """Launch live_server.py as a background subprocess."""
    kill_existing_server(port)
    print(f"[2/4] Starting live server on port {port}...")
    proc = subprocess.Popen(
        [
            sys.executable, SERVER_SCRIPT,
            "--trace", TRACE_FILE,
            "--port", str(port),
            "--no-tunnel",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # On Windows, CREATE_NEW_PROCESS_GROUP allows clean termination
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    """Gracefully stop the server subprocess."""
    if proc is None:
        return
    print("\n[CLEANUP] Stopping live server...")
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    except Exception as exc:
        print(f"  Warning: cleanup error: {exc}")
    print("  Server stopped.")


def wait_for_server(url: str, timeout: int) -> bool:
    """Poll the server until it responds or timeout expires."""
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                print(f"  Server ready at {url}")
                return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.5)
    print(f"  ERROR: Server did not respond within {timeout}s")
    return False


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------
def screenshot_tab(page, tab_name: str, output_path: Path, description: str, audit: AuditResult) -> str:
    """Click a tab and take a full-page screenshot."""
    # Click the tab button
    tab_btn = page.locator(f'button.tab-btn[data-tab="{tab_name}"]')
    if tab_btn.count() > 0:
        tab_btn.click()
        page.wait_for_timeout(400)

    file_path = str(output_path / f"tab_{tab_name}.png")
    page.screenshot(path=file_path, full_page=False)
    audit.add_screenshot(file_path, description)
    return file_path


def screenshot_element(page, selector: str, output_path: Path, filename: str, description: str, audit: AuditResult) -> Optional[str]:
    """Screenshot a specific element if it exists."""
    el = page.locator(selector).first
    if el.count() == 0 or not el.is_visible():
        return None
    file_path = str(output_path / filename)
    try:
        el.screenshot(path=file_path)
        audit.add_screenshot(file_path, description)
        return file_path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The 40 visual checks
# ---------------------------------------------------------------------------
def run_visual_checks(page, audit: AuditResult) -> None:
    """Execute all 40 automated visual checks against the live dashboard."""

    # ===================================================================
    # Layout & Structure (checks 1-6)
    # ===================================================================
    print("\n--- Layout & Structure ---")

    # Check 1: Three-panel layout widths
    sidebar = page.locator("#status-panel")
    evidence_panel = page.locator("#evidence-panel")
    main_area = page.locator("#main")

    sidebar_visible = sidebar.count() > 0 and sidebar.is_visible()
    ep_visible = evidence_panel.count() > 0 and evidence_panel.is_visible()
    main_visible = main_area.count() > 0 and main_area.is_visible()

    sidebar_width = 0
    ep_width = 0
    if sidebar_visible:
        sidebar_box = sidebar.bounding_box()
        sidebar_width = sidebar_box["width"] if sidebar_box else 0
    if ep_visible:
        ep_box = evidence_panel.bounding_box()
        ep_width = ep_box["width"] if ep_box else 0

    sidebar_ok = 180 <= sidebar_width <= 260
    ep_ok = 280 <= ep_width <= 380
    layout_ok = sidebar_visible and ep_visible and main_visible and sidebar_ok and ep_ok
    audit.add_check(
        1, "Three-panel layout: sidebar ~220px, center flexible, right ~320px",
        layout_ok,
        f"sidebar={sidebar_width:.0f}px, right={ep_width:.0f}px, all_visible={sidebar_visible and ep_visible and main_visible}",
        "Layout & Structure",
    )

    # Check 2: Right evidence panel has evidence cards
    ep_cards = page.locator(".ep-card")
    ep_card_count = ep_cards.count()
    audit.add_check(
        2, "Right evidence panel has >=1 evidence card (.ep-card)",
        ep_card_count >= 1,
        f"found {ep_card_count} .ep-card elements",
        "Layout & Structure",
    )

    # Check 3: Sidebar pipeline phase dots visible and colored
    done_dots = page.locator(".step-item.done .step-dot")
    done_dot_count = done_dots.count()
    active_dots = page.locator(".step-item.active .step-dot")
    active_dot_count = active_dots.count()
    total_dots = done_dot_count + active_dot_count
    audit.add_check(
        3, "Sidebar pipeline phase dots visible and colored",
        total_dots >= 1,
        f"done={done_dot_count}, active={active_dot_count}",
        "Layout & Structure",
    )

    # Check 4: Sidebar live metrics show non-zero values
    metric_ids = ["pm-evidence", "pm-sources", "pm-faith", "pm-words", "pm-citations", "pm-cost"]
    non_zero_metrics = 0
    metric_details = {}
    for mid in metric_ids:
        el = page.locator(f"#{mid}")
        if el.count() > 0:
            text = el.text_content().strip()
            metric_details[mid] = text
            if text and text not in ("0", "--", "$0.00"):
                non_zero_metrics += 1
    audit.add_check(
        4, "Sidebar live metrics section shows non-zero values",
        non_zero_metrics >= 2,
        f"{non_zero_metrics}/6 non-zero: {metric_details}",
        "Layout & Structure",
    )

    # Check 5: Header shows POLARIS branding + connection status + event count
    header = page.locator("#header")
    header_visible = header.count() > 0 and header.is_visible()
    header_h1 = page.locator("#header h1")
    branding_ok = header_h1.count() > 0 and "POLARIS" in (header_h1.text_content() or "")
    status_dot = page.locator("#status-dot")
    status_dot_visible = status_dot.count() > 0 and status_dot.is_visible()
    event_counter = page.locator("#event-counter")
    event_text = event_counter.text_content().strip() if event_counter.count() > 0 else ""
    event_count_ok = event_text and event_text != "0 events"
    audit.add_check(
        5, "Header shows POLARIS branding + connection status + event count",
        header_visible and branding_ok and status_dot_visible and event_count_ok,
        f"branding={branding_ok}, status_dot={status_dot_visible}, events='{event_text}'",
        "Layout & Structure",
    )

    # Check 6: Anomaly bar at bottom visible
    anomaly_bar = page.locator("#anomaly-bar")
    anomaly_visible = anomaly_bar.count() > 0 and anomaly_bar.is_visible()
    anomaly_box = anomaly_bar.bounding_box() if anomaly_visible else None
    anomaly_has_size = anomaly_box is not None and anomaly_box["height"] > 0
    audit.add_check(
        6, "Anomaly bar at bottom visible",
        anomaly_visible and anomaly_has_size,
        f"visible={anomaly_visible}, height={anomaly_box['height']:.0f}px" if anomaly_box else "not found",
        "Layout & Structure",
    )

    # ===================================================================
    # Overview Tab (checks 7-14)
    # ===================================================================
    print("\n--- Overview Tab ---")
    # Switch to overview tab
    page.locator('button.tab-btn[data-tab="overview"]').click()
    page.wait_for_timeout(300)

    # Check 7: Faithfulness SVG gauge rendered
    faith_gauge = page.locator("#ov-faith-gauge")
    faith_gauge_visible = faith_gauge.count() > 0 and faith_gauge.is_visible()
    svg_circles = page.locator("#ov-faith-gauge svg circle")
    svg_circle_count = svg_circles.count()
    has_dasharray = False
    if svg_circle_count > 0:
        for i in range(svg_circle_count):
            circle = svg_circles.nth(i)
            dasharray = circle.get_attribute("stroke-dasharray")
            if dasharray and dasharray.strip():
                has_dasharray = True
                break
    audit.add_check(
        7, "Faithfulness SVG gauge rendered (svg circle with stroke-dasharray)",
        faith_gauge_visible and svg_circle_count > 0 and has_dasharray,
        f"visible={faith_gauge_visible}, circles={svg_circle_count}, dasharray={has_dasharray}",
        "Overview Tab",
    )

    # Check 8: KPI cards show labels + values
    kpi_values = page.locator(".summary-card .value")
    kpi_count = kpi_values.count()
    non_placeholder_kpi = 0
    for i in range(kpi_count):
        text = kpi_values.nth(i).text_content().strip()
        if text and text not in ("0", "--", "$0.00"):
            non_placeholder_kpi += 1
    audit.add_check(
        8, "KPI cards show labels + values (not '0' or '--')",
        non_placeholder_kpi >= 2,
        f"{non_placeholder_kpi}/{kpi_count} non-placeholder values",
        "Overview Tab",
    )

    # Check 9: Evidence Strength meter shows segments
    strength_segments = page.locator(".strength-segment")
    segment_count = strength_segments.count()
    audit.add_check(
        9, "Evidence Strength meter shows segments (.strength-segment)",
        segment_count >= 1,
        f"found {segment_count} segments",
        "Overview Tab",
    )

    # Check 10: Pipeline Gantt shows >=3 colored bars
    gantt_bars = page.locator(".gantt-bar")
    gantt_count = gantt_bars.count()
    gantt_colored = 0
    for i in range(min(gantt_count, 20)):
        bar = gantt_bars.nth(i)
        box = bar.bounding_box()
        if box and box["width"] > 2:
            gantt_colored += 1
    audit.add_check(
        10, "Pipeline Gantt shows >=3 colored bars (.gantt-bar)",
        gantt_colored >= 3,
        f"found {gantt_colored} bars with width > 2px (total={gantt_count})",
        "Overview Tab",
    )

    # Check 11: Quality Gate grid shows cards with progress bars
    gate_cards = page.locator(".gate-card")
    gate_card_count = gate_cards.count()
    gate_with_bars = 0
    for i in range(min(gate_card_count, 10)):
        card = gate_cards.nth(i)
        bar_fill = card.locator(".gate-bar-fill")
        if bar_fill.count() > 0:
            gate_with_bars += 1
    audit.add_check(
        11, "Quality Gate grid shows cards with progress bars (.gate-card)",
        gate_card_count >= 1 and gate_with_bars >= 1,
        f"cards={gate_card_count}, with_bars={gate_with_bars}",
        "Overview Tab",
    )

    # Check 12: Evidence Funnel shows gradient bars
    # The overview funnel is in #ov-funnel
    ov_funnel_fills = page.locator("#ov-funnel .funnel-fill")
    ov_funnel_count = ov_funnel_fills.count()
    audit.add_check(
        12, "Evidence Funnel shows gradient bars (.funnel-fill)",
        ov_funnel_count >= 1,
        f"found {ov_funnel_count} funnel bars in #ov-funnel",
        "Overview Tab",
    )

    # Check 13: Activity log has >=5 entries
    activity_items = page.locator(".activity-item")
    activity_count = activity_items.count()
    audit.add_check(
        13, "Activity log has >=5 entries (.activity-item)",
        activity_count >= 5,
        f"found {activity_count} activity items",
        "Overview Tab",
    )

    # Check 14: Cost visible in overview (not $0.00)
    ov_cost = page.locator("#ov-cost")
    cost_text = ov_cost.text_content().strip() if ov_cost.count() > 0 else ""
    cost_non_zero = cost_text and cost_text != "$0.00"
    audit.add_check(
        14, "Cost visible in overview (ov-cost not '$0.00')",
        cost_non_zero,
        f"ov-cost='{cost_text}'",
        "Overview Tab",
    )

    # ===================================================================
    # Queries Tab (checks 15-17)
    # ===================================================================
    print("\n--- Queries Tab ---")
    page.locator('button.tab-btn[data-tab="queries"]').click()
    page.wait_for_timeout(300)

    # Check 15: Engine bars visible with colored fills
    engine_fills = page.locator(".engine-bar-fill")
    engine_fill_count = engine_fills.count()
    engine_colored = 0
    for i in range(min(engine_fill_count, 10)):
        fill = engine_fills.nth(i)
        box = fill.bounding_box()
        if box and box["width"] > 0:
            engine_colored += 1
    audit.add_check(
        15, "Engine bars visible with colored fills (.engine-bar-fill)",
        engine_colored >= 1,
        f"{engine_colored}/{engine_fill_count} engine bars with width > 0",
        "Queries Tab",
    )

    # Check 16: Agentic search rounds visible
    agentic_rounds = page.locator("#q-agentic-rounds")
    agentic_visible = agentic_rounds.count() > 0 and agentic_rounds.is_visible()
    agentic_content = agentic_rounds.text_content().strip() if agentic_visible else ""
    # Also check for research plan card
    research_plan = page.locator("#q-research-plan")
    research_plan_content = research_plan.text_content().strip() if research_plan.count() > 0 else ""
    has_query_context = len(agentic_content) > 0 or len(research_plan_content) > 0
    audit.add_check(
        16, "Agentic search rounds or research plan visible",
        has_query_context,
        f"agentic_content={len(agentic_content)} chars, research_plan={len(research_plan_content)} chars",
        "Queries Tab",
    )

    # Check 17: Query list with engine badges
    engine_badges = page.locator(".engine-badge")
    badge_count = engine_badges.count()
    query_items = page.locator("#query-list .query-item, #query-list [class*='query']")
    query_item_count = query_items.count()
    audit.add_check(
        17, "Query list with engine badges (.engine-badge)",
        badge_count >= 1,
        f"badges={badge_count}, query_items={query_item_count}",
        "Queries Tab",
    )

    # ===================================================================
    # Sources Tab (checks 18-20)
    # ===================================================================
    print("\n--- Sources Tab ---")
    page.locator('button.tab-btn[data-tab="sources"]').click()
    page.wait_for_timeout(300)

    # Check 18: Top domains bars visible
    domain_fills = page.locator(".domain-bar-fill")
    domain_fill_count = domain_fills.count()
    domain_colored = 0
    for i in range(min(domain_fill_count, 10)):
        fill = domain_fills.nth(i)
        box = fill.bounding_box()
        if box and box["width"] > 0:
            domain_colored += 1
    audit.add_check(
        18, "Top domains bars visible (.domain-bar-fill)",
        domain_colored >= 1,
        f"{domain_colored}/{domain_fill_count} domain bars with width > 0",
        "Sources Tab",
    )

    # Check 19: Source rows with status badges
    source_statuses = page.locator(".source-status")
    status_count = source_statuses.count()
    audit.add_check(
        19, "Source rows with status badges (.source-status)",
        status_count >= 1,
        f"found {status_count} source status badges",
        "Sources Tab",
    )

    # Check 20: Fetch pipeline stats (src-fetched, src-success)
    src_fetched_el = page.locator("#src-fetched")
    src_success_el = page.locator("#src-success")
    src_fetched = src_fetched_el.text_content().strip() if src_fetched_el.count() > 0 else "0"
    src_success = src_success_el.text_content().strip() if src_success_el.count() > 0 else "0"
    fetch_stats_ok = src_fetched != "0" or src_success != "0"
    audit.add_check(
        20, "Fetch pipeline stats (src-fetched, src-success)",
        fetch_stats_ok,
        f"fetched={src_fetched}, success={src_success}",
        "Sources Tab",
    )

    # ===================================================================
    # STORM Tab (checks 21-25)
    # ===================================================================
    print("\n--- STORM Tab ---")
    page.locator('button.tab-btn[data-tab="storm"]').click()
    page.wait_for_timeout(500)

    # Check 21: Perspective cards visible
    persona_cards = page.locator(".persona-card")
    persp_tabs = page.locator(".persp-tab")
    persona_count = persona_cards.count()
    persp_tab_count = persp_tabs.count()
    audit.add_check(
        21, "Perspective cards visible (.persona-card or .persp-tab)",
        persona_count >= 1 or persp_tab_count >= 1,
        f"persona_cards={persona_count}, persp_tabs={persp_tab_count}",
        "STORM Tab",
    )

    # Click first perspective tab to ensure chat content renders
    first_persp = page.locator(".persp-tab").first
    if first_persp.count() > 0:
        first_persp.click()
        page.wait_for_timeout(300)

    # Check 22: Q bubble styled
    storm_q = page.locator("#storm-chat .storm-q-improved, .storm-q")
    storm_q_count = storm_q.count()
    audit.add_check(
        22, "Q bubble styled (.storm-q or .storm-q-improved)",
        storm_q_count >= 1,
        f"found {storm_q_count} question bubbles",
        "STORM Tab",
    )

    # Check 23: A bubble styled
    storm_a = page.locator(".storm-a-improved, .storm-a")
    storm_a_count = storm_a.count()
    audit.add_check(
        23, "A bubble styled (.storm-a or .storm-a-improved)",
        storm_a_count >= 1,
        f"found {storm_a_count} answer bubbles",
        "STORM Tab",
    )

    # Check 24: Failed interviews marked
    storm_failed = page.locator(".storm-failed-overlay")
    failed_count = storm_failed.count()
    # Also check for failed perspective tabs (class .failed) or strikethrough text
    failed_persp = page.locator(".persp-tab.failed")
    failed_persp_count = failed_persp.count()
    # Also check for <s> strikethrough in persp tabs (another marker for failed)
    failed_strikethrough = page.locator(".persp-tab s")
    failed_strike_count = failed_strikethrough.count()
    # Click the failed persona tab to trigger the failed overlay
    if failed_persp_count > 0:
        failed_persp.first.click()
        page.wait_for_timeout(300)
        storm_failed = page.locator(".storm-failed-overlay")
        failed_count = storm_failed.count()
    any_failed = failed_count >= 1 or failed_persp_count >= 1 or failed_strike_count >= 1
    audit.add_check(
        24, "Failed interviews marked (.storm-failed-overlay)",
        any_failed,
        f"failed_overlays={failed_count}, failed_persp_tabs={failed_persp_count}, strikethrough={failed_strike_count}",
        "STORM Tab",
    )

    # Check 25: STORM chat has content (not empty state)
    storm_empty = page.locator("#storm-empty")
    storm_empty_visible = storm_empty.count() > 0 and storm_empty.is_visible()
    storm_chat = page.locator("#storm-chat")
    storm_chat_content = storm_chat.text_content().strip() if storm_chat.count() > 0 else ""
    has_storm_content = len(storm_chat_content) > 20 and not storm_empty_visible
    audit.add_check(
        25, "STORM chat has content (not empty state)",
        has_storm_content,
        f"chat_content={len(storm_chat_content)} chars, empty_visible={storm_empty_visible}",
        "STORM Tab",
    )

    # ===================================================================
    # Evidence Tab (checks 26-30)
    # ===================================================================
    print("\n--- Evidence Tab ---")
    page.locator('button.tab-btn[data-tab="evidence"]').click()
    page.wait_for_timeout(300)

    # Check 26: Evidence funnel with gradient bars
    ev_funnel_fills = page.locator("#evidence-funnel .funnel-fill")
    ev_funnel_count = ev_funnel_fills.count()
    audit.add_check(
        26, "Evidence funnel with gradient bars (#evidence-funnel .funnel-fill)",
        ev_funnel_count >= 1,
        f"found {ev_funnel_count} funnel bars in #evidence-funnel",
        "Evidence Tab",
    )

    # Check 27: Tier filter chips visible and styled
    tier_chips = page.locator(".tier-chip")
    tier_chip_count = tier_chips.count()
    tier_chip_visible = 0
    for i in range(min(tier_chip_count, 10)):
        chip = tier_chips.nth(i)
        if chip.is_visible():
            tier_chip_visible += 1
    audit.add_check(
        27, "Tier filter chips visible and styled (.tier-chip)",
        tier_chip_visible >= 3,
        f"{tier_chip_visible}/{tier_chip_count} visible tier chips",
        "Evidence Tab",
    )

    # Check 28: 5-signal scoring bars visible
    signal_bars = page.locator(".signal-bars .signal-bar")
    signal_bar_count = signal_bars.count()
    audit.add_check(
        28, "5-signal scoring bars visible (.signal-bars .signal-bar)",
        signal_bar_count >= 1,
        f"found {signal_bar_count} signal bars",
        "Evidence Tab",
    )

    # Check 29: Evidence cards with tier badges
    ev_detail_cards = page.locator(".evidence-detail-card")
    ev_detail_count = ev_detail_cards.count()
    tier_badges_in_cards = page.locator(".evidence-detail-card .tier-badge")
    tier_badge_count = tier_badges_in_cards.count()
    audit.add_check(
        29, "Evidence cards with tier badges (.evidence-detail-card .tier-badge)",
        ev_detail_count >= 1 and tier_badge_count >= 1,
        f"detail_cards={ev_detail_count}, tier_badges={tier_badge_count}",
        "Evidence Tab",
    )

    # Check 30: Evidence detail list has entries
    ev_detail_list = page.locator("#evidence-detail-list")
    ev_detail_children = page.locator("#evidence-detail-list > *")
    ev_list_count = ev_detail_children.count()
    audit.add_check(
        30, "Evidence detail list has entries",
        ev_list_count >= 1,
        f"found {ev_list_count} children in #evidence-detail-list",
        "Evidence Tab",
    )

    # ===================================================================
    # Evidence Graph Tab (checks 31-33)
    # ===================================================================
    print("\n--- Evidence Graph Tab ---")
    page.locator('button.tab-btn[data-tab="evgraph"]').click()
    page.wait_for_timeout(500)

    # Check 31: SVG canvas with circle nodes
    svg_circles_graph = page.locator("#graph-svg circle")
    circle_count = svg_circles_graph.count()
    audit.add_check(
        31, "SVG canvas with >=3 circle nodes (#graph-svg circle)",
        circle_count >= 3,
        f"found {circle_count} circles in #graph-svg",
        "Evidence Graph Tab",
    )

    # Check 32: Edges (lines) connecting nodes
    # Force re-render the evidence graph to ensure edges are drawn
    page.evaluate("if (typeof renderEvidenceGraph === 'function') renderEvidenceGraph();")
    page.wait_for_timeout(500)
    svg_lines = page.locator("#graph-svg line")
    line_count = svg_lines.count()
    audit.add_check(
        32, "Edges (lines) connecting nodes (#graph-svg line)",
        line_count >= 1,
        f"found {line_count} lines in #graph-svg",
        "Evidence Graph Tab",
    )

    # Check 33: Filter controls visible
    graph_color_mode = page.locator("#graph-color-mode")
    graph_tier_filter = page.locator("#graph-tier-filter")
    color_visible = graph_color_mode.count() > 0 and graph_color_mode.is_visible()
    tier_filter_visible = graph_tier_filter.count() > 0 and graph_tier_filter.is_visible()
    audit.add_check(
        33, "Filter controls visible (graph-color-mode, graph-tier-filter)",
        color_visible and tier_filter_visible,
        f"color_mode={color_visible}, tier_filter={tier_filter_visible}",
        "Evidence Graph Tab",
    )

    # ===================================================================
    # Report Tab (checks 34-38)
    # ===================================================================
    print("\n--- Report Tab ---")
    page.locator('button.tab-btn[data-tab="report"]').click()
    page.wait_for_timeout(300)

    # Check 34: Gate grid cards in report area
    rpt_gate_cards = page.locator("#rpt-gate-grid .gate-card")
    rpt_gate_count = rpt_gate_cards.count()
    # Also check the overview gate cards as fallback
    all_gate_cards = page.locator("#pane-report .gate-card")
    all_gate_count = all_gate_cards.count()
    audit.add_check(
        34, "Gate grid cards (.gate-card) in report area",
        rpt_gate_count >= 1 or all_gate_count >= 1,
        f"rpt-gate-grid={rpt_gate_count}, pane-report={all_gate_count}",
        "Report Tab",
    )

    # Check 35: Iteration timeline or decisions visible
    iter_timeline = page.locator("#rpt-iter-timeline")
    iter_visible = iter_timeline.count() > 0 and iter_timeline.is_visible()
    iter_content = iter_timeline.text_content().strip() if iter_visible else ""
    iter_pills = page.locator(".iter-pill")
    iter_pill_count = iter_pills.count()
    iteration_cards = page.locator(".iteration-card")
    iter_card_count = iteration_cards.count()
    audit.add_check(
        35, "Iteration timeline or iteration decisions visible",
        iter_pill_count >= 1 or iter_card_count >= 1 or len(iter_content) > 10,
        f"iter_pills={iter_pill_count}, iter_cards={iter_card_count}, timeline_chars={len(iter_content)}",
        "Report Tab",
    )

    # Check 36: Verdict bar segments
    verdict_segs = page.locator(".verdict-seg")
    verdict_seg_count = verdict_segs.count()
    audit.add_check(
        36, "Verdict bar segments (.verdict-seg)",
        verdict_seg_count >= 1,
        f"found {verdict_seg_count} verdict segments",
        "Report Tab",
    )

    # Check 37: Section rows with expandable items
    section_rows = page.locator(".section-row")
    section_count = section_rows.count()
    audit.add_check(
        37, "Section rows (.section-row) with expandable items",
        section_count >= 1,
        f"found {section_count} section rows",
        "Report Tab",
    )

    # Check 38: Cluster themes as styled chips
    theme_chips = page.locator(".theme-chip")
    theme_count = theme_chips.count()
    audit.add_check(
        38, "Cluster themes as styled chips (.theme-chip)",
        theme_count >= 1,
        f"found {theme_count} theme chips",
        "Report Tab",
    )

    # ===================================================================
    # Right Evidence Panel (checks 39-40)
    # ===================================================================
    print("\n--- Right Evidence Panel ---")

    # Check 39: Panel shows evidence cards with tier badge + signal bars
    panel_ep_cards = page.locator("#evidence-panel .ep-card")
    panel_ep_count = panel_ep_cards.count()
    panel_tier_badges = page.locator("#evidence-panel .ep-card .tier-badge")
    panel_tier_count = panel_tier_badges.count()
    panel_signal_bars = page.locator("#evidence-panel .ep-card .signal-bars")
    panel_signal_count = panel_signal_bars.count()
    audit.add_check(
        39, "Panel shows evidence cards with tier badge + signal bars",
        panel_ep_count >= 1 and (panel_tier_count >= 1 or panel_signal_count >= 1),
        f"ep_cards={panel_ep_count}, tier_badges={panel_tier_count}, signal_bars={panel_signal_count}",
        "Right Evidence Panel",
    )

    # Check 40: Panel count shows non-zero value
    ep_count_el = page.locator("#ep-count")
    ep_count_text = ep_count_el.text_content().strip() if ep_count_el.count() > 0 else "0"
    ep_count_nonzero = ep_count_text and ep_count_text != "0"
    audit.add_check(
        40, "Panel count shows non-zero value (#ep-count)",
        ep_count_nonzero,
        f"ep-count='{ep_count_text}'",
        "Right Evidence Panel",
    )


# ---------------------------------------------------------------------------
# Screenshot rounds: tabs + components + responsive
# ---------------------------------------------------------------------------
def take_all_screenshots(page, audit: AuditResult) -> None:
    """Capture screenshots for all tabs, key components, and responsive sizes."""

    # Round 1: All tabs at 1920x1080
    print("\n[SCREENSHOTS] Round 1: Desktop 1920x1080 — all tabs")
    round_dir = OUTPUT_DIR / "desktop_1920x1080"
    round_dir.mkdir(parents=True, exist_ok=True)

    page.set_viewport_size(RESOLUTIONS["desktop"])
    page.wait_for_timeout(300)

    for tab in TABS:
        screenshot_tab(page, tab, round_dir, f"Tab '{tab}' at 1920x1080", audit)
        print(f"    captured: tab_{tab}.png")

    # Evidence panel standalone screenshot
    screenshot_element(
        page, "#evidence-panel", round_dir,
        "component_evidence_panel.png",
        "Right evidence panel at 1920x1080", audit,
    )
    print("    captured: component_evidence_panel.png")

    # Sidebar standalone screenshot
    screenshot_element(
        page, "#status-panel", round_dir,
        "component_sidebar.png",
        "Left sidebar panel at 1920x1080", audit,
    )
    print("    captured: component_sidebar.png")

    # Round 2: Key components (switch to overview for most)
    print("\n[SCREENSHOTS] Round 2: Key components at 1920x1080")
    comp_dir = OUTPUT_DIR / "components"
    comp_dir.mkdir(parents=True, exist_ok=True)

    # Overview tab components
    page.locator('button.tab-btn[data-tab="overview"]').click()
    page.wait_for_timeout(300)

    component_selectors = [
        ("#ov-faith-gauge", "component_faith_gauge.png", "Faithfulness SVG gauge"),
        ("#overview-kpi-top", "component_hero_kpis.png", "Hero KPI cards (top row)"),
        ("#overview-kpi-bottom", "component_secondary_kpis.png", "Secondary KPI cards"),
        ("#ov-strength-meter", "component_strength_meter.png", "Evidence strength meter"),
        ("#ov-funnel", "component_funnel.png", "Evidence funnel"),
        ("#ov-gantt", "component_gantt.png", "Pipeline Gantt chart"),
        ("#ov-gate-grid", "component_gate_grid.png", "Quality gate grid"),
    ]
    for selector, filename, desc in component_selectors:
        result = screenshot_element(page, selector, comp_dir, filename, desc, audit)
        status = "captured" if result else "MISSING"
        print(f"    {status}: {filename}")

    # Evidence tab components
    page.locator('button.tab-btn[data-tab="evidence"]').click()
    page.wait_for_timeout(300)
    evidence_components = [
        ("#evidence-funnel", "component_evidence_funnel.png", "Evidence funnel (evidence tab)"),
        ("#evidence-detail-list", "component_evidence_cards.png", "Evidence detail cards"),
    ]
    for selector, filename, desc in evidence_components:
        result = screenshot_element(page, selector, comp_dir, filename, desc, audit)
        status = "captured" if result else "MISSING"
        print(f"    {status}: {filename}")

    # Graph tab
    page.locator('button.tab-btn[data-tab="evgraph"]').click()
    page.wait_for_timeout(500)
    result = screenshot_element(
        page, "#graph-canvas", comp_dir,
        "component_graph.png", "Evidence constellation graph", audit,
    )
    status = "captured" if result else "MISSING"
    print(f"    {status}: component_graph.png")

    # Round 3: Tablet landscape 1024x768
    print("\n[SCREENSHOTS] Round 3: Tablet landscape 1024x768 — all tabs")
    tablet_l_dir = OUTPUT_DIR / "tablet_landscape_1024x768"
    tablet_l_dir.mkdir(parents=True, exist_ok=True)

    page.set_viewport_size(RESOLUTIONS["tablet_landscape"])
    page.wait_for_timeout(300)

    for tab in TABS:
        screenshot_tab(page, tab, tablet_l_dir, f"Tab '{tab}' at 1024x768", audit)
        print(f"    captured: tab_{tab}.png")

    # Round 4: Tablet portrait 768x1024
    print("\n[SCREENSHOTS] Round 4: Tablet portrait 768x1024 — all tabs")
    tablet_p_dir = OUTPUT_DIR / "tablet_portrait_768x1024"
    tablet_p_dir.mkdir(parents=True, exist_ok=True)

    page.set_viewport_size(RESOLUTIONS["tablet_portrait"])
    page.wait_for_timeout(300)

    for tab in TABS:
        screenshot_tab(page, tab, tablet_p_dir, f"Tab '{tab}' at 768x1024", audit)
        print(f"    captured: tab_{tab}.png")

    # Restore desktop viewport for checks
    page.set_viewport_size(RESOLUTIONS["desktop"])
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------
def print_summary(audit: AuditResult) -> None:
    """Print a formatted summary table of all check results."""
    report = audit.to_dict()
    passed = report["passed"]
    failed = report["failed"]
    total = report["total_checks"]

    print("\n" + "=" * 72)
    print("  POLARIS VISUAL AUDIT SUMMARY")
    print("=" * 72)

    # Group by category
    categories = {}
    for check in report["checks"]:
        cat = check.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(check)

    for cat, checks in categories.items():
        cat_passed = sum(1 for c in checks if c["passed"])
        cat_total = len(checks)
        print(f"\n  {cat} ({cat_passed}/{cat_total})")
        print("  " + "-" * 68)
        for c in checks:
            icon = "PASS" if c["passed"] else "FAIL"
            marker = " " if c["passed"] else "*"
            print(f"  {marker} [{icon}] {c['check']:2d}. {c['name']}")
            if c["detail"]:
                print(f"             {c['detail']}")

    print("\n" + "=" * 72)
    result_label = "ALL PASSED" if failed == 0 else f"{failed} FAILED"
    print(f"  RESULT: {passed}/{total} passed, {failed}/{total} failed -- {result_label}")
    print(f"  Pass rate: {report['pass_rate']}%")
    print(f"  Duration: {report['duration_seconds']:.1f}s")
    print(f"  Screenshots: {len(report['screenshots'])} files")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Live Dashboard — Playwright Visual Overhaul Audit"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Server startup timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Run browser in headed mode (visible window)",
    )
    parser.add_argument(
        "--skip-inject", action="store_true",
        help="Skip trace injection (use existing trace file)",
    )
    args = parser.parse_args()

    # Verify playwright is installed
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright is not installed.")
        print("  pip install playwright && playwright install chromium")
        sys.exit(1)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    audit = AuditResult()
    server_proc = None
    dashboard_url = DASHBOARD_URL_TEMPLATE.format(port=args.port)

    try:
        # Step 1: Inject test trace data
        if not args.skip_inject:
            if not inject_test_trace():
                print("FATAL: Could not inject test trace. Aborting.")
                sys.exit(1)
        else:
            print("[1/4] Skipping trace injection (--skip-inject)")

        # Step 2: Start live server
        server_proc = start_server(args.port)
        if not wait_for_server(dashboard_url, args.timeout):
            print("FATAL: Server did not start. Aborting.")
            stop_server(server_proc)
            sys.exit(1)

        # Step 3: Run Playwright audit
        print(f"\n[3/4] Running Playwright visual audit against {dashboard_url}")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            context = browser.new_context(
                viewport=RESOLUTIONS["desktop"],
                device_scale_factor=1,
            )
            page = context.new_page()

            # Navigate to dashboard
            page.goto(dashboard_url, wait_until="domcontentloaded")
            print("  Page loaded. Waiting for SSE connection and events...")

            # Wait for connection indicator
            try:
                page.wait_for_selector(
                    "#status-dot.connected",
                    timeout=15000,
                )
                print("  SSE connected.")
            except Exception:
                print("  WARNING: Connection indicator not found, continuing anyway.")

            # Wait for event count to be > 0
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.getElementById('event-counter');
                        if (!el) return false;
                        const text = el.textContent.trim();
                        const num = parseInt(text);
                        return num > 0;
                    }""",
                    timeout=15000,
                )
                event_text = page.locator("#event-counter").text_content().strip()
                print(f"  Events loaded: {event_text}")
            except Exception:
                print("  WARNING: Event counter did not update, continuing anyway.")

            # Extra settle time for all renderers to fire
            page.wait_for_timeout(2000)
            # Force re-render of overview tab and evidence panel
            page.evaluate("if (typeof renderOverviewExtras === 'function') renderOverviewExtras();")
            page.wait_for_timeout(500)

            # Run the 40 visual checks
            print("\n[3/4] Running 40 visual checks...")
            run_visual_checks(page, audit)

            # Take all screenshots
            print("\n[3/4] Capturing screenshots across resolutions...")
            take_all_screenshots(page, audit)

            browser.close()

        # Step 4: Write report and summary
        print("\n[4/4] Writing audit report...")
        report = audit.to_dict()
        report_path = OUTPUT_DIR / "audit_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  Report written to {report_path}")

        # Print summary
        print_summary(audit)

        # Exit code based on results
        if report["failed"] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    finally:
        stop_server(server_proc)


if __name__ == "__main__":
    main()
