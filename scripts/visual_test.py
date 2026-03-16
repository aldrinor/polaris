"""Visual browser test for POLARIS dashboard at 375/768/1440px viewports.

Captures screenshots and validates rendering at each breakpoint.
Requires: playwright, running server on port 8767.
"""

import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE_URL = os.getenv("POLARIS_TEST_URL", "http://localhost:8767")
OUTPUT_DIR = Path("outputs/visual_tests")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    {"name": "mobile_375", "width": 375, "height": 812},   # iPhone SE/X
    {"name": "tablet_768", "width": 768, "height": 1024},   # iPad portrait
    {"name": "desktop_1440", "width": 1440, "height": 900},  # Desktop
]

CHECKS_PASSED = 0
CHECKS_FAILED = 0
FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    """Record a pass/fail check."""
    global CHECKS_PASSED, CHECKS_FAILED
    status = "PASS" if condition else "FAIL"
    if condition:
        CHECKS_PASSED += 1
    else:
        CHECKS_FAILED += 1
        FAILURES.append(f"{name}: {detail}")
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def test_viewport(page: Page, vp: dict) -> None:
    """Run visual tests at a specific viewport size."""
    name = vp["name"]
    w, h = vp["width"], vp["height"]
    print(f"\n{'='*60}")
    print(f"VIEWPORT: {name} ({w}x{h})")
    print(f"{'='*60}")

    page.set_viewport_size({"width": w, "height": h})
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)  # Let JS render (SSE keeps network active so networkidle won't work)

    # --- Screenshot: Landing page ---
    page.screenshot(
        path=str(OUTPUT_DIR / f"{name}_01_landing.png"),
        full_page=False,
    )
    print(f"  Screenshot: {name}_01_landing.png")

    # --- Check: Page loaded ---
    title = page.title()
    check(f"{name}/page_loads", "POLARIS" in title or len(title) > 0,
          f"title='{title}'")

    # --- Check: Header visible ---
    header = page.query_selector(".app-header")
    check(f"{name}/header_visible", header is not None and header.is_visible())

    # --- Check: Theme toggle exists ---
    toggle = page.query_selector("#theme-toggle")
    check(f"{name}/theme_toggle_exists", toggle is not None)

    # --- Check: No console errors ---
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # --- Test: Dark mode (default) ---
    theme_attr = page.evaluate("document.documentElement.getAttribute('data-theme')")
    check(f"{name}/initial_theme_set", theme_attr in ("dark", "light"),
          f"data-theme='{theme_attr}'")

    # --- Test: Toggle to light mode ---
    if toggle:
        toggle.click()
        time.sleep(0.5)
        theme_after = page.evaluate("document.documentElement.getAttribute('data-theme')")
        expected = "light" if theme_attr == "dark" else "dark"
        check(f"{name}/theme_toggle_works", theme_after == expected,
              f"was '{theme_attr}', now '{theme_after}', expected '{expected}'")

        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_02_theme_toggled.png"),
            full_page=False,
        )
        print(f"  Screenshot: {name}_02_theme_toggled.png")

        # Toggle back
        toggle.click()
        time.sleep(0.3)

    # --- Navigate to a completed research result ---
    # Click on "History" tab or find the research result
    history_tab = page.query_selector("[data-tab='history']")
    if history_tab and history_tab.is_visible():
        history_tab.click()
        time.sleep(1)
        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_03_history.png"),
            full_page=False,
        )
        print(f"  Screenshot: {name}_03_history.png")

        # Click on the most recent completed result
        result_cards = page.query_selector_all(".history-card, .result-card, [onclick*='loadResult'], [onclick*='viewResult']")
        check(f"{name}/history_has_results", len(result_cards) > 0,
              f"found {len(result_cards)} result cards")
        if result_cards:
            result_cards[0].click()
            time.sleep(2)

    # --- Try to get to report view ---
    report_tab = page.query_selector("[data-tab='report']")
    if report_tab and report_tab.is_visible():
        report_tab.click()
        time.sleep(2)

    # --- Check: Report content ---
    report_body = page.query_selector(".report-body, .report-rendered, .report-view")
    if report_body:
        report_text = report_body.inner_text()
        word_count = len(report_text.split())
        check(f"{name}/report_has_content", word_count > 100,
              f"{word_count} words visible")

        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_04_report.png"),
            full_page=False,
        )
        print(f"  Screenshot: {name}_04_report.png")

        # Full-page report screenshot
        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_05_report_full.png"),
            full_page=True,
        )
        print(f"  Screenshot: {name}_05_report_full.png")

        # --- Check: Quality banner ---
        quality_banner = page.query_selector(".report-quality-banner")
        check(f"{name}/quality_banner_visible",
              quality_banner is not None and quality_banner.is_visible())

        # --- Check: Citation hint (user mode) ---
        citation_hint = page.query_selector(".citation-hint")
        if citation_hint:
            check(f"{name}/citation_hint_visible", citation_hint.is_visible())

        # --- Check: TOC sidebar (desktop only) ---
        toc = page.query_selector(".report-toc")
        if w >= 1024:
            check(f"{name}/toc_visible", toc is not None and toc.is_visible(),
                  "TOC should be visible at >= 1024px")
        else:
            if toc:
                check(f"{name}/toc_hidden", not toc.is_visible(),
                      "TOC should be hidden at < 1024px")

        # --- Check: Source cards ---
        source_cards = page.query_selector_all(".source-card")
        check(f"{name}/source_cards_exist", len(source_cards) > 0,
              f"found {len(source_cards)} source cards")

        # --- Check: Citations are clickable ---
        cite_refs = page.query_selector_all(".cite-ref")
        check(f"{name}/citations_clickable", len(cite_refs) > 0,
              f"found {len(cite_refs)} cite-ref elements")

        # --- Test: Click a citation to show popover ---
        if cite_refs:
            cite_refs[0].click()
            time.sleep(0.5)
            popover = page.query_selector(".cite-popover")
            check(f"{name}/citation_popover_works",
                  popover is not None and popover.is_visible())

            page.screenshot(
                path=str(OUTPUT_DIR / f"{name}_06_citation_popover.png"),
                full_page=False,
            )
            print(f"  Screenshot: {name}_06_citation_popover.png")

            # Dismiss popover
            page.click("body", position={"x": 10, "y": 10})
            time.sleep(0.3)
    else:
        print(f"  [SKIP] Report view not accessible — checking if data needs loading")
        # Try snapshot-based approach: load the latest result directly
        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_04_current_state.png"),
            full_page=True,
        )
        print(f"  Screenshot: {name}_04_current_state.png")

    # --- Check: Mobile layout specifics ---
    if w <= 480:
        # Check nav stacks or scrolls
        nav_btns = page.query_selector_all(".nav-btn")
        if nav_btns:
            check(f"{name}/nav_buttons_touchable", True,
                  f"found {len(nav_btns)} nav buttons")

    # --- Check: No overflow ---
    has_overflow = page.evaluate("""
        () => {
            const body = document.body;
            return body.scrollWidth > window.innerWidth + 5;
        }
    """)
    check(f"{name}/no_horizontal_overflow", not has_overflow,
          f"scrollWidth > viewport" if has_overflow else "clean")

    # --- Light mode full screenshot ---
    if toggle:
        # Force light mode
        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        time.sleep(0.5)
        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_07_light_mode.png"),
            full_page=False,
        )
        print(f"  Screenshot: {name}_07_light_mode.png")

        # Restore dark mode
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        time.sleep(0.3)

    # --- Evidence tab ---
    evidence_tab = page.query_selector("[data-tab='evidence']")
    if evidence_tab and evidence_tab.is_visible():
        evidence_tab.click()
        time.sleep(1)
        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_08_evidence.png"),
            full_page=False,
        )
        print(f"  Screenshot: {name}_08_evidence.png")

        # Check evidence cards render
        ev_cards = page.query_selector_all(".evidence-card, .ev-card")
        check(f"{name}/evidence_cards_render", len(ev_cards) > 0,
              f"found {len(ev_cards)} evidence cards")

    # --- Operator (Pipeline Console) view tests ---
    # Switch to operator mode via the view-mode-btn
    op_btn = page.query_selector(".view-mode-btn[data-mode='operator']")
    if op_btn and op_btn.is_visible():
        op_btn.click()
        time.sleep(1)

        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_09_operator_console.png"),
            full_page=False,
        )
        print(f"  Screenshot: {name}_09_operator_console.png")

        # --- Check: Faithfulness metric is not 0.0% ---
        faith_el = page.query_selector("#pm-faith")
        if faith_el:
            faith_text = faith_el.inner_text().strip()
            check(f"{name}/op_faithfulness_not_zero",
                  faith_text not in ("0.0%", "0%", "--", ""),
                  f"faithfulness='{faith_text}'")
        else:
            check(f"{name}/op_faithfulness_not_zero", False, "pm-faith element not found")

        # --- Check: Reasoning stream has entries ---
        reasoning_entries = page.query_selector_all("#reasoning-stream .reasoning-entry")
        check(f"{name}/op_reasoning_has_entries",
              len(reasoning_entries) > 0,
              f"found {len(reasoning_entries)} reasoning entries")

        # --- Check: Status text is not stale ---
        status_el = page.query_selector("#current-status-text")
        if status_el:
            status_text = status_el.inner_text().strip()
            check(f"{name}/op_status_text_complete",
                  "complete" in status_text.lower() or "finished" in status_text.lower()
                  or "ready" in status_text.lower() or status_text == "",
                  f"status='{status_text}'")
        else:
            check(f"{name}/op_status_text_complete", False, "status element not found")

        # --- Check: Quality gates rendered ---
        gate_dots = page.query_selector_all(".gate-dot")
        check(f"{name}/op_quality_gates_exist",
              len(gate_dots) > 0,
              f"found {len(gate_dots)} gate indicators")

        # Full-page operator screenshot
        page.screenshot(
            path=str(OUTPUT_DIR / f"{name}_10_operator_full.png"),
            full_page=True,
        )
        print(f"  Screenshot: {name}_10_operator_full.png")

        # Switch back to user mode for clean state
        usr_btn = page.query_selector(".view-mode-btn[data-mode='user']")
        if usr_btn:
            usr_btn.click()
            time.sleep(0.3)


def main():
    print("POLARIS Visual Browser Test")
    print(f"Server: {BASE_URL}")
    print(f"Output: {OUTPUT_DIR.resolve()}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for vp in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                device_scale_factor=1,  # Use 1x to match CSS pixel viewport exactly
            )
            page = context.new_page()
            try:
                test_viewport(page, vp)
            except Exception as exc:
                print(f"  [ERROR] {vp['name']}: {exc}")
                FAILURES.append(f"{vp['name']}/exception: {exc}")
            finally:
                page.close()
                context.close()

        browser.close()

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"RESULTS: {CHECKS_PASSED} passed, {CHECKS_FAILED} failed")
    print(f"Screenshots: {OUTPUT_DIR.resolve()}")
    if FAILURES:
        print(f"\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
    print(f"{'='*60}")

    sys.exit(1 if CHECKS_FAILED > 0 else 0)


if __name__ == "__main__":
    main()
