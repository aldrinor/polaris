"""
E2E Playwright visual audit for NOVA Phase 1.
Tests: Generate Plan -> render plan card -> launch campaign -> view matrix.
"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("AUDIT_URL", "http://localhost:8766")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots" / "campaigns"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

ISSUES = []


def screenshot(page, name):
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  [SCREENSHOT] {name}.png")
    return path


def flag(severity, msg):
    ISSUES.append((severity, msg))
    print(f"  [{severity}] {msg}")


def run(page):
    print("\n=== E2E CAMPAIGN AUDIT ===\n")

    # --- Navigate & switch to operator mode ---
    page.goto(BASE_URL, wait_until="load")
    page.wait_for_timeout(2000)
    page.evaluate("if (typeof setViewMode === 'function') setViewMode('operator')")
    page.wait_for_timeout(1000)

    # Detect starting theme
    starting_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    print(f"  Starting theme: {starting_theme}")

    # --- Switch to Campaigns tab ---
    page.locator("#tab-campaigns").click()
    page.wait_for_timeout(800)

    # --- DARK THEME screenshots ---
    if starting_theme != "dark":
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(500)

    screenshot(page, "e2e_01_dark_empty_state")

    # --- Switch to Planner ---
    page.locator(".cm-toggle-btn", has_text="Planner").click()
    page.wait_for_timeout(500)
    screenshot(page, "e2e_02_dark_planner")

    # --- Type query and generate plan ---
    textarea = page.locator(".planner-query-input")
    textarea.fill("What are the environmental and health impacts of PFAS contamination in groundwater?")
    page.wait_for_timeout(200)
    screenshot(page, "e2e_03_dark_planner_with_query")

    # Click Generate Plan
    page.locator(".planner-generate-btn").click()
    page.wait_for_timeout(500)
    screenshot(page, "e2e_04_dark_planner_loading")

    # Wait for plan to load (up to 30s)
    try:
        page.wait_for_selector(".planner-plan-card", timeout=30000)
        page.wait_for_timeout(500)
        screenshot(page, "e2e_05_dark_plan_card")

        # Check plan card structure
        plan_title = page.locator(".planner-plan-title")
        if plan_title.count() > 0:
            print(f"  [OK] Plan title: {plan_title.text_content()[:80]}")
        else:
            flag("FAIL", "Plan title not found")

        plan_meta = page.locator(".planner-plan-meta")
        if plan_meta.count() > 0:
            print(f"  [OK] Plan meta: {plan_meta.text_content()[:100]}")
        else:
            flag("WARN", "Plan meta not found")

        domain_groups = page.locator(".planner-domain-group")
        domain_count = domain_groups.count()
        print(f"  [OK] Domain groups: {domain_count}")

        if domain_count == 0:
            flag("FAIL", "No domain groups in plan card")

        vector_items = page.locator(".planner-vector-item")
        vector_count = vector_items.count()
        print(f"  [OK] Vector items: {vector_count}")

        vector_badges = page.locator(".planner-vector-badge")
        print(f"  [OK] Vector badges: {vector_badges.count()}")

        # Check Launch button
        launch_btn = page.locator(".planner-launch-btn")
        if launch_btn.count() > 0:
            launch_text = launch_btn.text_content()
            print(f"  [OK] Launch button: '{launch_text}'")
            if "0 queries" in launch_text:
                flag("FAIL", "Launch button shows 0 queries")
        else:
            flag("FAIL", "Launch button not found")

        # Check Cancel button
        cancel_btn = page.locator(".planner-cancel-btn")
        if cancel_btn.count() > 0:
            print("  [OK] Cancel button present")

        # --- Collapse/expand a domain group ---
        if domain_count > 0:
            first_header = page.locator(".planner-domain-header").first
            first_header.click()
            page.wait_for_timeout(300)
            screenshot(page, "e2e_06_dark_domain_collapsed")
            first_header.click()
            page.wait_for_timeout(300)

        # --- LIGHT THEME plan card ---
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(500)
        screenshot(page, "e2e_07_light_plan_card")

        # Verify light theme contrasts
        bg = page.evaluate("""
            getComputedStyle(document.querySelector('.planner-plan-card')).backgroundColor
        """)
        print(f"  [INFO] Light theme plan card bg: {bg}")

        # Switch back to dark
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(300)

        # --- Remove a vector (test editability) ---
        remove_btns = page.locator(".planner-vector-remove")
        if remove_btns.count() > 0:
            initial_count = vector_items.count()
            remove_btns.first.click()
            page.wait_for_timeout(500)
            new_count = page.locator(".planner-vector-item").count()
            print(f"  [OK] Remove vector: {initial_count} -> {new_count}")
            if new_count >= initial_count:
                flag("WARN", "Remove button didn't reduce vector count")
            screenshot(page, "e2e_08_dark_after_remove")

        # --- Launch as campaign ---
        launch_btn = page.locator(".planner-launch-btn")
        if launch_btn.count() > 0 and launch_btn.is_enabled():
            launch_btn.click()
            page.wait_for_timeout(3000)
            screenshot(page, "e2e_09_dark_campaign_launched")

            # Check if we switched to map view
            matrix = page.locator(".cm-matrix-table")
            if matrix.count() > 0:
                print("  [OK] Matrix table rendered after launch")

                rows = matrix.locator("tbody tr")
                print(f"  [OK] Matrix rows: {rows.count()}")

                cells = matrix.locator(".cm-cell")
                print(f"  [OK] Matrix cells: {cells.count()}")

                # Check cell states
                running_cells = matrix.locator(".cm-cell.running")
                passed_cells = matrix.locator(".cm-cell.passed")
                idle_cells = matrix.locator(".cm-cell.idle")
                print(f"  [INFO] Cell states - running:{running_cells.count()} passed:{passed_cells.count()} idle:{idle_cells.count()}")

                screenshot(page, "e2e_10_dark_matrix_grid")

                # Check filter bar
                filter_chips = page.locator(".cm-filter-chip")
                print(f"  [OK] Filter chips: {filter_chips.count()}")

                # Check legend
                legend = page.locator(".cm-legend")
                if legend.count() > 0:
                    print("  [OK] Legend visible")
                else:
                    flag("WARN", "Legend not visible with campaign data")

                # Check sidebar
                sidebar_title = page.locator(".cm-sidebar-title")
                if sidebar_title.count() > 0:
                    print(f"  [OK] Sidebar title: {sidebar_title.text_content()}")

                active_cards = page.locator(".cm-active-card")
                print(f"  [INFO] Active vector cards: {active_cards.count()}")

                # Wait a bit for pipeline to start, then re-screenshot
                page.wait_for_timeout(5000)
                screenshot(page, "e2e_11_dark_matrix_after_5s")

                running_cells2 = page.locator(".cm-cell.running")
                print(f"  [INFO] Running cells after 5s: {running_cells2.count()}")

                # LIGHT theme with data
                page.locator("#theme-toggle").click()
                page.wait_for_timeout(500)
                screenshot(page, "e2e_12_light_matrix_grid")

                # Check light theme cell backgrounds
                if idle_cells.count() > 0:
                    cell_bg = page.evaluate("""
                        getComputedStyle(document.querySelector('.cm-cell.idle')).backgroundColor
                    """)
                    print(f"  [INFO] Light theme idle cell bg: {cell_bg}")

                page.locator("#theme-toggle").click()
                page.wait_for_timeout(300)

                # Test search filter
                search = page.locator(".cm-search-input")
                if search.count() > 0:
                    search.fill("PFAS")
                    page.wait_for_timeout(500)
                    filtered_rows = page.locator(".cm-matrix-table tbody tr").count()
                    print(f"  [OK] Search filter 'PFAS': {filtered_rows} rows")
                    screenshot(page, "e2e_13_dark_search_filtered")
                    search.fill("")
                    page.wait_for_timeout(300)

                # Test cell hover tooltip
                if cells.count() > 0:
                    cells.first.hover()
                    page.wait_for_timeout(500)
                    tooltip = page.locator(".cm-tooltip")
                    if tooltip.count() > 0 and tooltip.is_visible():
                        print("  [OK] Cell tooltip visible on hover")
                        screenshot(page, "e2e_14_dark_cell_tooltip")
                    else:
                        flag("WARN", "Tooltip not visible on cell hover")

            else:
                # Might still be in map view but with empty state (campaign loading)
                flag("INFO", "Matrix not rendered yet (campaign may be loading)")
                screenshot(page, "e2e_09b_map_after_launch")
        else:
            flag("WARN", "Launch button not enabled or not found")

    except Exception as exc:
        flag("FAIL", f"Plan generation failed or timed out: {exc}")
        screenshot(page, "e2e_error_plan")

    # --- Campaign selector test ---
    print("\n--- Campaign Selector ---")
    selector = page.locator("#cm-campaign-select")
    if selector.count() > 0:
        options = selector.locator("option")
        print(f"  [OK] Campaign options: {options.count()}")

    # --- Summary ---
    print("\n=== AUDIT SUMMARY ===")
    print(f"  Total issues: {len(ISSUES)}")
    for sev, msg in ISSUES:
        print(f"    [{sev}] {msg}")

    fail_count = sum(1 for s, _ in ISSUES if s == "FAIL")
    if fail_count == 0:
        print("  RESULT: PASS")
    else:
        print(f"  RESULT: FAIL ({fail_count} failures)")

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
            screenshot(page, "e2e_fatal")
            success = False
        finally:
            browser.close()

    print(f"\nScreenshots: {SCREENSHOT_DIR}")
    for f in sorted(SCREENSHOT_DIR.glob("e2e_*.png")):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
