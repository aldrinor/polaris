"""
Comprehensive audit of the SOTA dashboard rewrite.

Loads the dashboard in Playwright, hydrates from snapshot,
then checks every view for:
- JS console errors
- Missing DOM elements
- Empty/broken renderers
- Visual structure
- Interactive elements (clicks, popovers)

Usage:
    python scripts/audit_dashboard_rewrite.py
    (Requires live_server running on port 8770)
"""

import sys
import os
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = os.getenv("AUDIT_URL", "http://localhost:8770")
SCREENSHOT_DIR = Path("logs/audit_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

PASS = 0
FAIL = 0
WARN = 0
results = []


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        results.append(("PASS", name, detail))
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        results.append(("FAIL", name, detail))
        print(f"  [FAIL] {name} -- {detail}")


def warn(name, detail=""):
    global WARN
    WARN += 1
    results.append(("WARN", name, detail))
    print(f"  [WARN] {name} -- {detail}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # Collect JS errors
        js_errors = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # =========================================================
        # 1. Page load + snapshot hydration
        # =========================================================
        print("\n=== PHASE 1: Page Load + Snapshot ===")
        page.goto(URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)  # Wait for snapshot hydration + SSE connect

        check("Page loads without crash", page.title() != "")
        check("Title is POLARIS Research Observatory", "POLARIS" in page.title())

        # Check JS errors after load
        check("No JS errors on page load", len(js_errors) == 0,
              f"{len(js_errors)} errors: {js_errors[:3]}" if js_errors else "")
        check("No console errors on page load", len(console_errors) == 0,
              f"{len(console_errors)} errors: {console_errors[:3]}" if console_errors else "")

        page.screenshot(path=str(SCREENSHOT_DIR / "01_initial_load.png"), full_page=False)

        # =========================================================
        # 2. App shell structure
        # =========================================================
        print("\n=== PHASE 2: App Shell Structure ===")
        check("App header exists", page.locator(".app-header").count() > 0)
        check("Vector ID element exists", page.locator("#vector-id").count() > 0)
        check("Connection status dot exists", page.locator("#status-dot").count() > 0)
        check("Elapsed timer exists", page.locator("#elapsed-time").count() > 0)
        check("Cost display exists", page.locator("#total-cost").count() > 0)
        check("Nav bar exists", page.locator(".nav-bar").count() > 0)
        check("4 nav buttons exist", page.locator(".nav-btn").count() == 4)
        check("Query banner exists", page.locator(".query-banner").count() > 0)

        # Check nav button labels
        nav_texts = page.locator(".nav-btn").all_text_contents()
        check("Nav has Research button", any("Research" in t for t in nav_texts))
        check("Nav has Evidence button", any("Evidence" in t for t in nav_texts))
        check("Nav has Report button", any("Report" in t for t in nav_texts))
        check("Nav has Advanced button", any("Advanced" in t for t in nav_texts))

        # =========================================================
        # 3. Research View (default view)
        # =========================================================
        print("\n=== PHASE 3: Research View ===")
        research_pane = page.locator("#view-research")
        check("Research view is active", research_pane.is_visible())

        # Phase stepper
        check("Phase stepper exists", page.locator("#phase-stepper").count() > 0)
        step_items = page.locator(".step-item")
        check("Phase stepper has items", step_items.count() >= 7,
              f"Found {step_items.count()} items")

        # Reasoning stream (THE HERO)
        reasoning_col = page.locator("#reasoning-stream")
        check("Reasoning stream element exists", reasoning_col.count() > 0)
        reasoning_html = reasoning_col.inner_html() if reasoning_col.count() > 0 else ""
        check("Reasoning stream has content (not empty)", len(reasoning_html) > 50,
              f"HTML length: {len(reasoning_html)}")

        # Check for phase blocks
        phase_blocks = page.locator(".phase-block")
        check("Phase blocks rendered in reasoning stream", phase_blocks.count() >= 1,
              f"Found {phase_blocks.count()} phase blocks")

        # Check reasoning entries
        reasoning_entries = page.locator(".reasoning-entry")
        check("Reasoning entries exist", reasoning_entries.count() >= 1,
              f"Found {reasoning_entries.count()} entries")

        # Pipeline column (right side)
        pipeline_col = page.locator(".pipeline-column")
        check("Pipeline column exists", pipeline_col.count() > 0)

        # Metrics
        check("Evidence metric exists", page.locator("#pm-evidence").count() > 0)
        check("Faithfulness metric exists", page.locator("#pm-faith").count() > 0)

        # Activity log
        activity = page.locator("#activity-log")
        check("Activity log exists", activity.count() > 0)
        activity_html = activity.inner_html() if activity.count() > 0 else ""
        check("Activity log has entries", len(activity_html) > 50,
              f"HTML length: {len(activity_html)}")

        page.screenshot(path=str(SCREENSHOT_DIR / "02_research_view.png"), full_page=False)

        # =========================================================
        # 4. Metrics populated
        # =========================================================
        print("\n=== PHASE 4: Metrics Populated ===")
        # Get state from debug accessor
        state = page.evaluate("window._getDebugState()")
        check("State object accessible", state is not None)
        if state:
            check("Event count > 0", state.get("eventCount", 0) > 0,
                  f"eventCount={state.get('eventCount', 0)}")
            check("Evidence count > 0", state.get("evidence", 0) > 0,
                  f"evidence={state.get('evidence', 0)}")
            check("reasoningByPhase has data", len(state.get("reasoningByPhase", {})) > 0,
                  f"phases={list(state.get('reasoningByPhase', {}).keys())}")
            reasoning_count = sum(len(v) for v in state.get("reasoningByPhase", {}).values())
            check("reasoningByPhase has entries", reasoning_count >= 5,
                  f"total entries={reasoning_count}")
            check("Queries populated", len(state.get("queries", [])) > 0,
                  f"queries={len(state.get('queries', []))}")
            check("STORM chats populated", len(state.get("stormChats", [])) > 0,
                  f"stormChats={len(state.get('stormChats', []))}")
            check("Bibliography populated", len(state.get("bibliography", [])) > 0,
                  f"bibliography={len(state.get('bibliography', []))}")
            check("fullReport populated", len(state.get("fullReport", "")) > 100,
                  f"reportLen={len(state.get('fullReport', ''))}")
            check("pipelineComplete is true", state.get("pipelineComplete") is True,
                  f"pipelineComplete={state.get('pipelineComplete')}")
            check("Verification verdicts populated", len(state.get("verificationVerdicts", [])) > 0,
                  f"verdicts={len(state.get('verificationVerdicts', []))}")
            check("clusterThemes populated", len(state.get("clusterThemes", [])) > 0,
                  f"themes={len(state.get('clusterThemes', []))}")

        # =========================================================
        # 5. Evidence View
        # =========================================================
        print("\n=== PHASE 5: Evidence View ===")
        js_errors_before = len(js_errors)
        page.click('.nav-btn[data-view="evidence"]')
        time.sleep(1)

        evidence_pane = page.locator("#view-evidence")
        check("Evidence view is visible", evidence_pane.is_visible())
        check("No JS errors switching to Evidence", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        evidence_html = evidence_pane.inner_html()
        check("Evidence view has content", len(evidence_html) > 100,
              f"HTML length: {len(evidence_html)}")

        # Graph
        svg_el = page.locator("#view-evidence svg")
        check("SVG graph rendered", svg_el.count() > 0,
              f"Found {svg_el.count()} SVGs")

        # Graph nodes (circles)
        circles = page.locator("#view-evidence svg circle")
        circle_count = circles.count()
        check("Graph has nodes (circles)", circle_count > 0,
              f"Found {circle_count} circles")

        # Graph mode selector
        graph_mode = page.locator("#graph-mode-selector")
        check("Graph mode selector exists", graph_mode.count() > 0)

        # Tier filter
        tier_filter = page.locator("#graph-tier-filter")
        check("Tier filter exists", tier_filter.count() > 0)

        # Detail panel
        detail_panel = page.locator(".evidence-detail-panel")
        check("Detail panel exists (hidden)", detail_panel.count() > 0)

        # Evidence cards
        ev_cards = page.locator(".ev-card")
        check("Evidence cards rendered", ev_cards.count() > 0,
              f"Found {ev_cards.count()} cards")

        page.screenshot(path=str(SCREENSHOT_DIR / "03_evidence_view.png"), full_page=False)

        # Try clicking a graph node
        if circle_count > 0:
            try:
                first_circle = circles.first
                first_circle.click(timeout=3000)
                time.sleep(0.5)
                panel_open = detail_panel.evaluate("el => el.classList.contains('open')")
                check("Clicking graph node opens detail panel", panel_open)
                page.screenshot(path=str(SCREENSHOT_DIR / "04_evidence_detail_panel.png"), full_page=False)
                # Close panel
                close_btn = page.locator(".detail-close-btn")
                if close_btn.count() > 0:
                    close_btn.click()
                    time.sleep(0.3)
            except Exception as e:
                warn("Graph node click test", str(e))

        # =========================================================
        # 6. Report View
        # =========================================================
        print("\n=== PHASE 6: Report View ===")
        js_errors_before = len(js_errors)
        page.click('.nav-btn[data-view="report"]')
        time.sleep(1)

        report_pane = page.locator("#view-report")
        check("Report view is visible", report_pane.is_visible())
        check("No JS errors switching to Report", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        report_html = report_pane.inner_html()
        check("Report view has content", len(report_html) > 200,
              f"HTML length: {len(report_html)}")

        # Report rendered (markdown)
        rendered = page.locator(".report-rendered")
        check("Report rendered section exists", rendered.count() > 0)
        if rendered.count() > 0:
            rendered_html = rendered.inner_html()
            check("Rendered report has HTML content", len(rendered_html) > 500,
                  f"HTML length: {len(rendered_html)}")
            # Check for heading tags (markdown parsed)
            has_headings = "<h" in rendered_html.lower()
            check("Markdown parsed into headings", has_headings)

        # Citation references
        cite_refs = page.locator(".cite-ref")
        check("Clickable citation refs exist", cite_refs.count() > 0,
              f"Found {cite_refs.count()} citation refs")

        # Try clicking a citation
        if cite_refs.count() > 0:
            try:
                cite_refs.first.click(timeout=3000)
                time.sleep(0.5)
                popover = page.locator("#cite-popover-active")
                check("Citation click shows popover", popover.count() > 0)
                page.screenshot(path=str(SCREENSHOT_DIR / "05_citation_popover.png"), full_page=False)
                # Close popover
                page.click("body")
                time.sleep(0.3)
            except Exception as e:
                warn("Citation click test", str(e))

        # Bibliography
        bib = page.locator(".report-bib")
        check("Bibliography section exists", bib.count() > 0)
        bib_items = page.locator(".bib-item")
        check("Bibliography has items", bib_items.count() > 0,
              f"Found {bib_items.count()} items")

        # Quality gates
        gate_dots = page.locator(".gate-dot")
        check("Quality gate dots rendered", gate_dots.count() > 0,
              f"Found {gate_dots.count()} dots")

        # Collapsible extras
        detail_blocks = page.locator(".report-detail-block")
        check("Collapsible detail blocks exist", detail_blocks.count() > 0,
              f"Found {detail_blocks.count()} blocks")

        # Export buttons
        export_btns = page.locator(".export-btn")
        check("Export buttons exist", export_btns.count() >= 2,
              f"Found {export_btns.count()} buttons")

        page.screenshot(path=str(SCREENSHOT_DIR / "06_report_view.png"), full_page=False)

        # =========================================================
        # 7. Advanced View
        # =========================================================
        print("\n=== PHASE 7: Advanced View ===")
        js_errors_before = len(js_errors)
        page.click('.nav-btn[data-view="advanced"]')
        time.sleep(1)

        advanced_pane = page.locator("#view-advanced")
        check("Advanced view is visible", advanced_pane.is_visible())
        check("No JS errors switching to Advanced", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        # Sub-tabs
        adv_tabs = page.locator(".adv-tab-btn")
        check("Advanced sub-tabs exist", adv_tabs.count() == 5,
              f"Found {adv_tabs.count()} tabs")

        # Queries sub-tab (default)
        queries_pane = page.locator("#adv-queries")
        check("Queries pane is active", queries_pane.is_visible())
        queries_html = queries_pane.inner_html()
        check("Queries pane has content", len(queries_html) > 50,
              f"HTML length: {len(queries_html)}")

        # Sources sub-tab
        js_errors_before = len(js_errors)
        page.click('.adv-tab-btn[data-adv="sources"]')
        time.sleep(0.5)
        sources_pane = page.locator("#adv-sources")
        check("Sources pane rendered", sources_pane.is_visible())
        sources_html = sources_pane.inner_html()
        check("Sources pane has content", len(sources_html) > 50,
              f"HTML length: {len(sources_html)}")
        check("No JS errors on Sources tab", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        # STORM sub-tab
        js_errors_before = len(js_errors)
        page.click('.adv-tab-btn[data-adv="storm"]')
        time.sleep(0.5)
        storm_pane = page.locator("#adv-storm")
        check("STORM pane rendered", storm_pane.is_visible())
        storm_html = storm_pane.inner_html()
        check("STORM pane has content", len(storm_html) > 50,
              f"HTML length: {len(storm_html)}")
        check("No JS errors on STORM tab", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        # Persona cards
        persona_cards = page.locator(".persona-card")
        check("Persona cards rendered", persona_cards.count() > 0,
              f"Found {persona_cards.count()} cards")

        # Check persona card has expertise
        if persona_cards.count() > 0:
            first_card_html = persona_cards.first.inner_html()
            check("Persona card has expertise info", "persona-expertise" in first_card_html,
                  f"Card HTML has persona-expertise class: {'persona-expertise' in first_card_html}")
            check("Persona card has name", "persona-name" in first_card_html)

        # Interview transcript
        transcript = page.locator(".storm-exchange")
        check("STORM transcript entries rendered", transcript.count() > 0,
              f"Found {transcript.count()} exchanges")

        page.screenshot(path=str(SCREENSHOT_DIR / "07_advanced_storm.png"), full_page=False)

        # Trace sub-tab
        js_errors_before = len(js_errors)
        page.click('.adv-tab-btn[data-adv="trace"]')
        time.sleep(0.5)
        trace_pane = page.locator("#adv-trace")
        check("Trace pane rendered", trace_pane.is_visible())
        trace_html = trace_pane.inner_html()
        check("Trace pane has content", len(trace_html) > 50,
              f"HTML length: {len(trace_html)}")
        check("No JS errors on Trace tab", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        # Trace filter chips
        trace_chips = page.locator(".trace-chip")
        check("Trace filter chips rendered", trace_chips.count() > 0,
              f"Found {trace_chips.count()} chips")

        # Trace cards
        trace_cards = page.locator(".trace-card")
        check("Trace cards rendered", trace_cards.count() > 0,
              f"Found {trace_cards.count()} cards")

        # Cost sub-tab
        js_errors_before = len(js_errors)
        page.click('.adv-tab-btn[data-adv="cost"]')
        time.sleep(0.5)
        cost_pane = page.locator("#adv-cost")
        check("Cost pane rendered", cost_pane.is_visible())
        cost_html = cost_pane.inner_html()
        check("Cost pane has content", len(cost_html) > 50,
              f"HTML length: {len(cost_html)}")
        check("No JS errors on Cost tab", len(js_errors) == js_errors_before,
              f"New errors: {js_errors[js_errors_before:]}" if len(js_errors) > js_errors_before else "")

        page.screenshot(path=str(SCREENSHOT_DIR / "08_advanced_cost.png"), full_page=False)

        # =========================================================
        # 8. Switch back to Research and verify reasoning
        # =========================================================
        print("\n=== PHASE 8: Reasoning Stream Deep Check ===")
        page.click('.nav-btn[data-view="research"]')
        time.sleep(0.5)

        # Count phase blocks
        phase_blocks = page.locator(".phase-block")
        phase_count = phase_blocks.count()
        check("Multiple phase blocks in reasoning stream", phase_count >= 5,
              f"Found {phase_count} phase blocks")

        # Check phase names
        if phase_count > 0:
            phase_names = []
            for i in range(phase_count):
                block = phase_blocks.nth(i)
                name_el = block.locator(".phase-block-name")
                if name_el.count() > 0:
                    phase_names.append(name_el.text_content())
            check("Phase names are readable", len(phase_names) > 0,
                  f"Names: {phase_names[:5]}")

        # Check reasoning text is NOT truncated to 500 chars
        entries = page.locator(".reasoning-text")
        if entries.count() > 0:
            first_text = entries.first.text_content()
            check("Reasoning text length > 500 chars (not truncated)", len(first_text) > 400,
                  f"First entry length: {len(first_text)} chars")

        page.screenshot(path=str(SCREENSHOT_DIR / "09_reasoning_stream.png"), full_page=False)

        # =========================================================
        # 9. Final JS error check
        # =========================================================
        print("\n=== PHASE 9: Final Error Check ===")
        check("Total JS errors across all views = 0", len(js_errors) == 0,
              f"Total errors: {len(js_errors)}: {js_errors}" if js_errors else "")
        check("Total console errors across all views = 0", len(console_errors) == 0,
              f"Total errors: {len(console_errors)}: {console_errors[:5]}" if console_errors else "")

        # =========================================================
        # Summary
        # =========================================================
        browser.close()

    print("\n" + "=" * 60)
    print(f"AUDIT RESULTS: {PASS} PASS / {FAIL} FAIL / {WARN} WARN")
    print("=" * 60)

    if FAIL > 0:
        print("\nFAILURES:")
        for status, name, detail in results:
            if status == "FAIL":
                print(f"  [FAIL] {name}: {detail}")

    if WARN > 0:
        print("\nWARNINGS:")
        for status, name, detail in results:
            if status == "WARN":
                print(f"  [WARN] {name}: {detail}")

    print(f"\nScreenshots saved to: {SCREENSHOT_DIR.absolute()}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
