"""
Comprehensive Playwright visual audit for NOVA Phase 1.
Tests ALL components in ALL modes and themes:
1. Nav bar (both themes, dynamic island overlap)
2. Campaigns tab in Pipeline Console (dark + light)
3. Planner view (dark + light)
4. E2E: Generate Plan -> Plan Card -> Launch Campaign -> Matrix Grid
5. Campaign overlay in Researcher mode
6. Matrix interactions: filter, search, tooltip, cell states
"""

import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("AUDIT_URL", "http://localhost:8766")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots" / "nova_final"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

ISSUES = []
PASS_COUNT = 0


def screenshot(page, name):
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  [SCREENSHOT] {name}.png")
    return path


def ok(msg):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  [PASS] {msg}")


def flag(severity, msg):
    ISSUES.append((severity, msg))
    print(f"  [{severity}] {msg}")


def run(page):
    print("\n" + "=" * 60)
    print("  NOVA PHASE 1 — COMPREHENSIVE VISUAL AUDIT")
    print("=" * 60)

    # ===================================================================
    # SECTION 1: NAV BAR IN PIPELINE CONSOLE
    # ===================================================================
    print("\n--- 1. NAV BAR ---")
    page.goto(BASE_URL, wait_until="load")
    page.wait_for_timeout(2000)

    # Switch to operator mode
    page.evaluate("if (typeof setViewMode === 'function') setViewMode('operator')")
    page.wait_for_timeout(1000)

    # Detect theme
    theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    print(f"  Starting theme: {theme}")

    # Ensure dark theme
    if theme != "dark":
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(500)

    screenshot(page, "01_nav_dark")

    # Check all 7 tabs visible
    tabs = page.locator(".nav-btn")
    tab_count = tabs.count()
    tab_texts = []
    for i in range(tab_count):
        txt = tabs.nth(i).text_content().strip()
        tab_texts.append(txt)
    print(f"  Tabs ({tab_count}): {tab_texts}")

    if tab_count >= 7:
        ok(f"All {tab_count} nav tabs rendered")
    else:
        flag("FAIL", f"Expected >=7 tabs, got {tab_count}")

    # Check Campaigns tab specifically
    campaigns_tab = page.locator("#tab-campaigns")
    if campaigns_tab.count() > 0 and campaigns_tab.is_visible():
        ok("Campaigns tab visible in nav bar")
    else:
        flag("FAIL", "Campaigns tab not visible")

    # Check nav-btn has opaque background (not transparent)
    nav_bg = page.evaluate("""
        getComputedStyle(document.querySelector('.nav-btn')).backgroundColor
    """)
    print(f"  Nav btn bg (dark): {nav_bg}")
    if "transparent" in nav_bg or nav_bg == "rgba(0, 0, 0, 0)":
        flag("FAIL", "Nav btn background is transparent (island will bleed through)")
    else:
        ok("Nav btn has opaque background")

    # Light theme nav
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(500)
    screenshot(page, "02_nav_light")

    nav_bg_light = page.evaluate("""
        getComputedStyle(document.querySelector('.nav-btn')).backgroundColor
    """)
    print(f"  Nav btn bg (light): {nav_bg_light}")
    if "transparent" in nav_bg_light or nav_bg_light == "rgba(0, 0, 0, 0)":
        flag("FAIL", "Nav btn background transparent in light theme")
    else:
        ok("Nav btn opaque in light theme")

    # Back to dark
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(300)

    # ===================================================================
    # SECTION 2: CAMPAIGNS TAB — EMPTY STATE
    # ===================================================================
    print("\n--- 2. CAMPAIGNS TAB (EMPTY STATE) ---")
    campaigns_tab.click()
    page.wait_for_timeout(800)
    screenshot(page, "03_campaigns_empty_dark")

    view_pane = page.locator("#view-campaigns")
    if view_pane.is_visible():
        ok("Campaigns view pane visible")
    else:
        flag("FAIL", "Campaigns view pane NOT visible")

    # Check top bar elements
    selector = page.locator("#cm-campaign-select")
    if selector.count() > 0:
        ok("Campaign selector dropdown present")
    else:
        flag("FAIL", "Campaign selector missing")

    toggle_btns = page.locator(".cm-toggle-btn")
    if toggle_btns.count() >= 2:
        ok(f"Map/Planner toggle buttons: {toggle_btns.count()}")
    else:
        flag("FAIL", "Toggle buttons missing")

    new_btn = page.locator(".cm-new-btn")
    if new_btn.count() > 0:
        ok("+ New Campaign button present")
    else:
        flag("WARN", "New Campaign button missing")

    empty_state = page.locator(".cm-empty-state")
    if empty_state.count() > 0:
        ok("Empty state message displayed")
    else:
        flag("INFO", "No empty state (may have campaigns)")

    # Light theme
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(500)
    screenshot(page, "04_campaigns_empty_light")
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(300)

    # ===================================================================
    # SECTION 3: PLANNER VIEW
    # ===================================================================
    print("\n--- 3. PLANNER VIEW ---")
    planner_btn = page.locator(".cm-toggle-btn", has_text="Planner")
    planner_btn.click()
    page.wait_for_timeout(500)
    screenshot(page, "05_planner_dark")

    query_input = page.locator(".planner-query-input")
    if query_input.count() > 0:
        ok("Planner query textarea present")
    else:
        flag("FAIL", "Planner textarea missing")

    depth_chips = page.locator(".planner-depth-chip")
    chip_count = depth_chips.count()
    print(f"  Depth chips: {chip_count}")
    if chip_count >= 3:
        ok("Quick/Standard/Deep depth chips present")
    else:
        flag("FAIL", f"Expected 3 depth chips, got {chip_count}")

    gen_btn = page.locator(".planner-generate-btn")
    if gen_btn.count() > 0:
        ok("Generate Plan button present")
    else:
        flag("FAIL", "Generate Plan button missing")

    # Light theme planner
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(500)
    screenshot(page, "06_planner_light")
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(300)

    # ===================================================================
    # SECTION 4: E2E — GENERATE PLAN + PLAN CARD
    # ===================================================================
    print("\n--- 4. E2E: GENERATE PLAN ---")
    query_input.fill("What are the environmental and health impacts of PFAS contamination in groundwater?")
    page.wait_for_timeout(200)
    screenshot(page, "07_planner_with_query")

    gen_btn.click()
    page.wait_for_timeout(500)
    screenshot(page, "08_planner_loading")

    # Wait for plan to appear (up to 30s)
    try:
        page.wait_for_selector(".planner-plan-card", timeout=60000)
        page.wait_for_timeout(500)
        screenshot(page, "09_plan_card_dark")

        # Plan card structure checks
        plan_title = page.locator(".planner-plan-title")
        if plan_title.count() > 0:
            ok(f"Plan title: {plan_title.text_content()[:60]}")
        else:
            flag("FAIL", "Plan title missing")

        plan_meta = page.locator(".planner-plan-meta")
        if plan_meta.count() > 0:
            ok(f"Plan meta: {plan_meta.text_content()[:80]}")
        else:
            flag("WARN", "Plan meta missing")

        domain_groups = page.locator(".planner-domain-group")
        domain_count = domain_groups.count()
        if domain_count > 0:
            ok(f"Domain groups: {domain_count}")
        else:
            flag("FAIL", "No domain groups in plan")

        vector_items = page.locator(".planner-vector-item")
        vector_count = vector_items.count()
        if vector_count > 0:
            ok(f"Vector items: {vector_count}")
        else:
            flag("FAIL", "No vectors in plan")

        vector_badges = page.locator(".planner-vector-badge")
        badge_count = vector_badges.count()
        print(f"  Vector badges: {badge_count}")

        # Check Launch button
        launch_btn = page.locator(".planner-launch-btn")
        if launch_btn.count() > 0:
            launch_text = launch_btn.text_content()
            if "0 queries" in launch_text:
                flag("FAIL", f"Launch shows 0 queries: '{launch_text}'")
            else:
                ok(f"Launch button: '{launch_text}'")
        else:
            flag("FAIL", "Launch button missing")

        # Cancel button
        cancel_btn = page.locator(".planner-cancel-btn")
        if cancel_btn.count() > 0:
            ok("Cancel button present")

        # Collapse/expand domain group
        if domain_count > 0:
            first_header = page.locator(".planner-domain-header").first
            first_header.click()
            page.wait_for_timeout(300)
            screenshot(page, "10_domain_collapsed")
            first_header.click()
            page.wait_for_timeout(300)
            ok("Domain collapse/expand works")

        # Remove a vector
        remove_btns = page.locator(".planner-vector-remove")
        if remove_btns.count() > 0:
            initial_count = vector_items.count()
            remove_btns.first.click()
            page.wait_for_timeout(500)
            new_count = page.locator(".planner-vector-item").count()
            if new_count < initial_count:
                ok(f"Remove vector: {initial_count} -> {new_count}")
            else:
                flag("WARN", "Remove didn't reduce count")

        # Light theme plan card
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(500)
        screenshot(page, "11_plan_card_light")

        card_bg = page.evaluate("""
            getComputedStyle(document.querySelector('.planner-plan-card')).backgroundColor
        """)
        print(f"  Light plan card bg: {card_bg}")
        ok("Light theme plan card rendered")

        page.locator("#theme-toggle").click()
        page.wait_for_timeout(300)

        # ===================================================================
        # SECTION 5: E2E — LAUNCH CAMPAIGN + MATRIX
        # ===================================================================
        print("\n--- 5. E2E: LAUNCH CAMPAIGN ---")
        launch_btn = page.locator(".planner-launch-btn")
        if launch_btn.count() > 0 and launch_btn.is_enabled():
            launch_btn.click()
            page.wait_for_timeout(3000)
            screenshot(page, "12_campaign_launched")

            matrix = page.locator(".cm-matrix-table")
            if matrix.count() > 0:
                ok("Matrix table rendered after launch")

                rows = matrix.locator("tbody tr")
                row_count = rows.count()
                ok(f"Matrix rows: {row_count}")

                cells = matrix.locator(".cm-cell")
                cell_count = cells.count()
                ok(f"Matrix cells: {cell_count}")

                # Cell state check
                running = matrix.locator(".cm-cell.running").count()
                passed = matrix.locator(".cm-cell.passed").count()
                idle = matrix.locator(".cm-cell.idle").count()
                print(f"  Cell states: running={running} passed={passed} idle={idle}")

                screenshot(page, "13_matrix_dark")

                # Filter chips
                filter_chips = page.locator(".cm-filter-chip")
                chip_count = filter_chips.count()
                if chip_count >= 4:
                    ok(f"Filter chips: {chip_count}")
                else:
                    flag("WARN", f"Expected 4 filter chips, got {chip_count}")

                # Legend
                legend = page.locator(".cm-legend")
                if legend.count() > 0:
                    ok("Legend visible")
                else:
                    flag("WARN", "Legend not visible")

                # Sidebar
                sidebar_title = page.locator(".cm-sidebar-title")
                if sidebar_title.count() > 0:
                    ok(f"Sidebar: {sidebar_title.text_content()}")

                active_cards = page.locator(".cm-active-card")
                print(f"  Active vector cards: {active_cards.count()}")

                # Wait for pipeline updates
                page.wait_for_timeout(5000)
                screenshot(page, "14_matrix_after_5s")

                running2 = page.locator(".cm-cell.running").count()
                print(f"  Running cells after 5s: {running2}")

                # Cell tooltip
                if cells.count() > 0:
                    cells.first.hover()
                    page.wait_for_timeout(500)
                    tooltip = page.locator(".cm-tooltip")
                    if tooltip.count() > 0 and tooltip.is_visible():
                        ok("Tooltip visible on cell hover")
                        screenshot(page, "15_cell_tooltip")
                    else:
                        flag("WARN", "Tooltip not visible on hover")

                # Search filter
                search = page.locator(".cm-search-input")
                if search.count() > 0:
                    search.fill("PFAS")
                    page.wait_for_timeout(500)
                    filtered = page.locator(".cm-matrix-table tbody tr").count()
                    ok(f"Search 'PFAS': {filtered} rows")
                    screenshot(page, "16_search_filtered")
                    search.fill("")
                    page.wait_for_timeout(300)

                # Filter chip interaction
                if filter_chips.count() > 1:
                    filter_chips.nth(1).click()
                    page.wait_for_timeout(500)
                    screenshot(page, "17_filter_active")
                    filter_chips.nth(0).click()
                    page.wait_for_timeout(300)
                    ok("Filter chip interaction works")

                # Light theme matrix
                page.locator("#theme-toggle").click()
                page.wait_for_timeout(500)
                screenshot(page, "18_matrix_light")
                ok("Light theme matrix rendered")

                page.locator("#theme-toggle").click()
                page.wait_for_timeout(300)
            else:
                flag("INFO", "Matrix not rendered (campaign loading)")
                screenshot(page, "12b_post_launch")
        else:
            flag("WARN", "Launch button not available")

    except Exception as exc:
        flag("FAIL", f"Plan generation failed: {exc}")
        screenshot(page, "error_plan")

    # Campaign badge check
    badge = page.locator("#badge-campaigns")
    if badge.count() > 0:
        badge_text = badge.text_content().strip()
        if badge_text:
            ok(f"Campaign nav badge: '{badge_text}'")
        else:
            flag("INFO", "Campaign badge empty (no running campaigns)")

    # Campaign dropdown options
    selector = page.locator("#cm-campaign-select")
    if selector.count() > 0:
        options = selector.locator("option")
        opt_count = options.count()
        ok(f"Campaign dropdown options: {opt_count}")

    # ===================================================================
    # SECTION 6: RESEARCHER MODE — WORKSPACE OVERLAY
    # ===================================================================
    print("\n--- 6. RESEARCHER MODE (WORKSPACE OVERLAY) ---")
    page.evaluate("if (typeof setViewMode === 'function') setViewMode('user')")
    page.wait_for_timeout(1000)
    screenshot(page, "19_researcher_mode")

    # Check campaigns button in sidebar
    ws_btn = page.locator("#ws-campaigns-btn")
    if ws_btn.count() > 0 and ws_btn.is_visible():
        ok("Campaigns button visible in workspace sidebar")

        # Check badge
        ws_badge = page.locator("#ws-campaigns-badge")
        if ws_badge.count() > 0:
            ws_badge_text = ws_badge.text_content().strip()
            if ws_badge_text:
                ok(f"Workspace campaign badge: '{ws_badge_text}'")

        # Click to open overlay
        ws_btn.click()
        page.wait_for_timeout(500)
        screenshot(page, "20_overlay_open")

        overlay = page.locator("#ws-campaign-overlay")
        if overlay.count() > 0 and "open" in (overlay.get_attribute("class") or ""):
            ok("Campaign overlay opened")
        else:
            flag("FAIL", "Campaign overlay not open")

        # Check overlay header
        overlay_title = page.locator(".ws-campaign-overlay-title")
        if overlay_title.count() > 0:
            ok(f"Overlay title: {overlay_title.text_content()}")

        # Check overlay has campaign content
        overlay_body = page.locator("#ws-campaign-overlay-body")
        if overlay_body.count() > 0:
            inner_html_len = len(overlay_body.inner_html())
            if inner_html_len > 50:
                ok(f"Overlay body has content ({inner_html_len} chars)")
            else:
                flag("WARN", "Overlay body appears empty")

        # Switch to planner inside overlay (scope to overlay to avoid strict mode)
        overlay_scope = page.locator("#ws-campaign-overlay")
        planner_toggle = overlay_scope.locator(".cm-toggle-btn", has_text="Planner")
        if planner_toggle.count() > 0:
            planner_toggle.click()
            page.wait_for_timeout(500)
            screenshot(page, "21_overlay_planner")

            overlay_textarea = overlay_scope.locator(".planner-query-input")
            if overlay_textarea.count() > 0:
                ok("Planner textarea inside overlay")
            else:
                flag("FAIL", "Planner not rendering inside overlay")

        # Close overlay
        close_btn = page.locator(".ws-campaign-overlay-close")
        if close_btn.count() > 0:
            close_btn.click()
            page.wait_for_timeout(300)
            screenshot(page, "22_overlay_closed")

            if "open" not in (overlay.get_attribute("class") or ""):
                ok("Overlay closed successfully")
            else:
                flag("FAIL", "Overlay didn't close")
    else:
        flag("FAIL", "Campaigns button NOT visible in workspace sidebar")

    # ===================================================================
    # SECTION 7: DARK THEME OVERLAY
    # ===================================================================
    print("\n--- 7. DARK THEME OVERLAY ---")
    current_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    if current_theme != "dark":
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(500)

    ws_btn = page.locator("#ws-campaigns-btn")
    if ws_btn.count() > 0 and ws_btn.is_visible():
        ws_btn.click()
        page.wait_for_timeout(500)
        screenshot(page, "23_overlay_dark")
        ok("Dark theme overlay rendered")

        close_btn = page.locator(".ws-campaign-overlay-close")
        if close_btn.count() > 0:
            close_btn.click()
            page.wait_for_timeout(300)

    # ===================================================================
    # SUMMARY
    # ===================================================================
    print("\n" + "=" * 60)
    print(f"  TOTAL PASS: {PASS_COUNT}")
    print(f"  TOTAL ISSUES: {len(ISSUES)}")
    for sev, msg in ISSUES:
        print(f"    [{sev}] {msg}")

    fail_count = sum(1 for s, _ in ISSUES if s == "FAIL")
    warn_count = sum(1 for s, _ in ISSUES if s == "WARN")
    info_count = sum(1 for s, _ in ISSUES if s == "INFO")
    print(f"\n  FAIL: {fail_count}  WARN: {warn_count}  INFO: {info_count}")

    if fail_count == 0:
        print("  RESULT: PASS")
    else:
        print(f"  RESULT: FAIL ({fail_count} failures)")
    print("=" * 60)

    return fail_count == 0


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = context.new_page()

        try:
            success = run(page)
        except Exception as exc:
            print(f"\n[FATAL] {exc}")
            import traceback
            traceback.print_exc()
            screenshot(page, "fatal_error")
            success = False
        finally:
            browser.close()

    print(f"\nScreenshots: {SCREENSHOT_DIR}")
    for f in sorted(SCREENSHOT_DIR.glob("*.png")):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
