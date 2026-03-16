"""
Playwright visual audit for NOVA Phase 1: Campaign Map + Planner.

Captures screenshots of:
1. Campaigns tab (empty state)
2. Planner view
3. Campaign Map (with existing campaign data if any)
4. Dark + Light theme variants
5. Tooltip and filter interactions

Screenshots saved to: tests/screenshots/campaigns/
"""

import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("AUDIT_URL", "http://localhost:8766")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots" / "campaigns"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def screenshot(page, name):
    """Save a full-page screenshot."""
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  [OK] {name}.png ({path})")
    return path


def audit_campaigns_tab(page):
    """Audit the Campaigns tab in dark and light themes."""
    print("\n=== CAMPAIGNS TAB AUDIT ===\n")

    # 1. Navigate to dashboard
    page.goto(BASE_URL, wait_until="load")
    page.wait_for_timeout(2000)
    screenshot(page, "01_dashboard_loaded_user_mode")

    # 1b. Switch to Pipeline Console (operator) mode to see nav tabs
    # Use JS evaluate since the toggle may be inside a hidden workspace view
    page.evaluate("if (typeof setViewMode === 'function') setViewMode('operator')")
    page.wait_for_timeout(1000)
    screenshot(page, "01b_operator_mode")

    # 2. Click Campaigns tab
    campaigns_tab = page.locator("#tab-campaigns")
    if not campaigns_tab.is_visible():
        print("  [FAIL] Campaigns tab not found in nav bar!")
        return False

    campaigns_tab.click()
    page.wait_for_timeout(1000)
    screenshot(page, "02_campaigns_tab_empty_state")

    # 3. Check empty state elements
    view_pane = page.locator("#view-campaigns")
    if not view_pane.is_visible():
        print("  [FAIL] view-campaigns pane not visible after tab click!")
        return False
    print("  [OK] Campaigns view pane is visible")

    # 4. Check for campaign selector dropdown
    selector = page.locator("#cm-campaign-select")
    if selector.count() > 0:
        print("  [OK] Campaign selector dropdown present")
    else:
        print("  [WARN] Campaign selector not rendered (may need re-render)")

    # 5. Check for Map/Planner toggle
    toggle_btns = view_pane.locator(".cm-toggle-btn")
    if toggle_btns.count() >= 2:
        print(f"  [OK] Toggle buttons present: {toggle_btns.count()}")
    else:
        print("  [WARN] Toggle buttons not found")

    # 6. Check empty state message
    empty_state = view_pane.locator(".cm-empty-state")
    if empty_state.count() > 0:
        print("  [OK] Empty state message displayed")
    else:
        print("  [INFO] No empty state (might have campaigns loaded)")

    # 7. Click Planner toggle
    planner_btn = view_pane.locator(".cm-toggle-btn", has_text="Planner")
    if planner_btn.count() > 0:
        planner_btn.click()
        page.wait_for_timeout(500)
        screenshot(page, "03_planner_view")

        # Check planner elements
        query_input = page.locator(".planner-query-input")
        if query_input.count() > 0:
            print("  [OK] Planner query input present")
        else:
            print("  [FAIL] Planner query input NOT found")

        depth_chips = page.locator(".planner-depth-chip")
        print(f"  [OK] Depth chips: {depth_chips.count()}")

        gen_btn = page.locator(".planner-generate-btn")
        if gen_btn.count() > 0:
            print("  [OK] Generate Plan button present")
        else:
            print("  [FAIL] Generate Plan button NOT found")

        # Type a query into the planner
        if query_input.count() > 0:
            query_input.fill("What are the health effects of microplastics in drinking water?")
            page.wait_for_timeout(300)
            screenshot(page, "04_planner_with_query")
    else:
        print("  [WARN] Planner toggle button not found")

    # 8. Switch back to Map view
    map_btn = view_pane.locator(".cm-toggle-btn", has_text="Map")
    if map_btn.count() > 0:
        map_btn.click()
        page.wait_for_timeout(500)
        screenshot(page, "05_map_view_no_campaign")

    # 9. Check sidebar
    sidebar = view_pane.locator(".cm-sidebar")
    if sidebar.count() > 0:
        print("  [OK] Sidebar present")
    else:
        print("  [INFO] Sidebar not visible (no campaign selected)")

    # 10. Check legend
    legend = view_pane.locator(".cm-legend")
    if legend.count() > 0:
        print("  [OK] Legend present")
    else:
        print("  [INFO] Legend not visible (no campaign selected)")

    # 11. Light theme test
    theme_btn = page.locator("#theme-toggle")
    if theme_btn.count() > 0:
        theme_btn.click()
        page.wait_for_timeout(500)
        screenshot(page, "06_campaigns_light_theme")

        # Switch to planner in light theme
        if planner_btn.count() > 0:
            planner_btn.click()
            page.wait_for_timeout(500)
            screenshot(page, "07_planner_light_theme")

        # Switch back to dark
        theme_btn.click()
        page.wait_for_timeout(300)

    # 12. Check badge element exists
    badge = page.locator("#badge-campaigns")
    if badge.count() > 0:
        print(f"  [OK] Campaign badge present (content: '{badge.text_content()}')")
    else:
        print("  [FAIL] Campaign badge NOT found")

    # 13. Check New Campaign button
    new_btn = view_pane.locator(".cm-new-btn")
    if new_btn.count() > 0:
        print("  [OK] New Campaign button present")
    else:
        print("  [WARN] New Campaign button not found")

    # 14. Test campaign API
    print("\n--- API Endpoint Tests ---")

    # Test /api/campaigns
    response = page.request.get(f"{BASE_URL}/api/campaigns")
    print(f"  [{'OK' if response.status == 200 else 'FAIL'}] GET /api/campaigns -> {response.status}")

    if response.status == 200:
        data = response.json()
        campaign_count = len(data.get("campaigns", []))
        print(f"  [INFO] Found {campaign_count} existing campaigns")

        # If there are campaigns, select the first one and screenshot the map
        if campaign_count > 0:
            first_id = data["campaigns"][0]["campaign_id"]

            # Test /api/campaigns/{id}/live
            live_resp = page.request.get(f"{BASE_URL}/api/campaigns/{first_id}/live")
            print(f"  [{'OK' if live_resp.status == 200 else 'FAIL'}] GET /api/campaigns/{first_id}/live -> {live_resp.status}")

            # Select it in the UI
            campaigns_tab.click()
            page.wait_for_timeout(500)
            map_btn = view_pane.locator(".cm-toggle-btn", has_text="Map")
            if map_btn.count() > 0:
                map_btn.click()
                page.wait_for_timeout(500)

            sel = page.locator("#cm-campaign-select")
            if sel.count() > 0:
                sel.select_option(first_id)
                page.wait_for_timeout(2000)
                screenshot(page, "08_map_with_campaign")

                # Check for matrix table
                matrix = view_pane.locator(".cm-matrix-table")
                if matrix.count() > 0:
                    print(f"  [OK] Matrix table rendered")
                    rows = matrix.locator("tbody tr")
                    print(f"  [OK] Matrix rows: {rows.count()}")

                    cells = matrix.locator(".cm-cell")
                    print(f"  [OK] Matrix cells: {cells.count()}")
                else:
                    print("  [WARN] Matrix table not rendered")

                # Check filter chips
                filter_chips = view_pane.locator(".cm-filter-chip")
                print(f"  [OK] Filter chips: {filter_chips.count()}")

                # Test filter interaction
                if filter_chips.count() > 1:
                    filter_chips.nth(1).click()
                    page.wait_for_timeout(500)
                    screenshot(page, "09_map_filtered")

                    # Reset to All
                    filter_chips.nth(0).click()
                    page.wait_for_timeout(300)

                # Test search
                search_input = view_pane.locator(".cm-search-input")
                if search_input.count() > 0:
                    search_input.fill("test")
                    page.wait_for_timeout(500)
                    screenshot(page, "10_map_searched")
                    search_input.fill("")
                    page.wait_for_timeout(300)

                # Check sidebar
                active_cards = view_pane.locator(".cm-active-card")
                print(f"  [INFO] Active vector cards: {active_cards.count()}")

                # Light theme with data
                if theme_btn.count() > 0:
                    theme_btn.click()
                    page.wait_for_timeout(500)
                    screenshot(page, "11_map_with_data_light")
                    theme_btn.click()
                    page.wait_for_timeout(300)

    # 15. Test plan endpoint (non-destructive - just check it responds)
    plan_resp = page.request.post(
        f"{BASE_URL}/api/campaigns/plan",
        data='{"query": "test", "depth": "quick"}',
        headers={"Content-Type": "application/json"},
    )
    # 503 is expected if OpenRouter client not available
    print(f"  [{'OK' if plan_resp.status in (200, 503) else 'FAIL'}] POST /api/campaigns/plan -> {plan_resp.status}")

    print("\n=== AUDIT COMPLETE ===")
    return True


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = context.new_page()

        try:
            audit_campaigns_tab(page)
        except Exception as exc:
            print(f"\n[ERROR] Audit failed: {exc}")
            import traceback
            traceback.print_exc()
            screenshot(page, "error_state")
        finally:
            browser.close()

    # List all screenshots
    print(f"\nScreenshots saved to: {SCREENSHOT_DIR}")
    for f in sorted(SCREENSHOT_DIR.glob("*.png")):
        size = f.stat().st_size
        print(f"  {f.name} ({size:,} bytes)")


if __name__ == "__main__":
    main()
