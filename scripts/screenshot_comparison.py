"""
Screenshot all 4 dashboard views for visual comparison against SOTA plan spec.
Captures: Research, Evidence, Report, Advanced (all sub-tabs).
Outputs screenshots to logs/screenshots/
"""
import os
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

URL = "http://localhost:8770"
VIEWPORT = {"width": 1440, "height": 900}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()

        # Collect JS errors
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))

        print(f"[1] Loading {URL}...")
        page.goto(URL, wait_until="domcontentloaded")
        # Wait for snapshot hydration
        page.wait_for_timeout(3000)

        # Screenshot 1: Research View (default)
        print("[2] Capturing Research View...")
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01_research_view.png"), full_page=False)

        # Screenshot 2: Evidence View
        print("[3] Capturing Evidence View...")
        page.click('button.nav-btn[data-view="evidence"]')
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_evidence_view.png"), full_page=False)

        # Screenshot 3: Report View
        print("[4] Capturing Report View...")
        page.click('button.nav-btn[data-view="report"]')
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_report_view.png"), full_page=False)

        # Screenshot 4: Advanced - Queries
        print("[5] Capturing Advanced/Queries...")
        page.click('button.nav-btn[data-view="advanced"]')
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_advanced_queries.png"), full_page=False)

        # Screenshot 5: Advanced - Sources
        print("[6] Capturing Advanced/Sources...")
        sources_btn = page.query_selector('button.adv-tab-btn[data-adv="sources"]')
        if sources_btn:
            sources_btn.click()
            page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05_advanced_sources.png"), full_page=False)

        # Screenshot 6: Advanced - STORM
        print("[7] Capturing Advanced/STORM...")
        storm_btn = page.query_selector('button.adv-tab-btn[data-adv="storm"]')
        if storm_btn:
            storm_btn.click()
            page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06_advanced_storm.png"), full_page=False)

        # Screenshot 7: Advanced - Trace
        print("[8] Capturing Advanced/Trace...")
        trace_btn = page.query_selector('button.adv-tab-btn[data-adv="trace"]')
        if trace_btn:
            trace_btn.click()
            page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "07_advanced_trace.png"), full_page=False)

        # Screenshot 8: Advanced - Cost
        print("[9] Capturing Advanced/Cost...")
        cost_btn = page.query_selector('button.adv-tab-btn[data-adv="cost"]')
        if cost_btn:
            cost_btn.click()
            page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "08_advanced_cost.png"), full_page=False)

        # Screenshot 9: Go back to Research and click a phase block if available
        print("[10] Capturing Research View with expanded phase...")
        page.click('button.nav-btn[data-view="research"]')
        page.wait_for_timeout(500)
        phase_header = page.query_selector('.phase-block-header')
        if phase_header:
            phase_header.click()
            page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "09_research_expanded.png"), full_page=False)

        # Screenshot 10: Evidence view with a node clicked
        print("[11] Capturing Evidence View with detail panel...")
        page.click('button.nav-btn[data-view="evidence"]')
        page.wait_for_timeout(500)
        try:
            circle = page.query_selector('svg circle')
            if circle:
                circle.click(timeout=3000)
                page.wait_for_timeout(500)
        except Exception:
            # If circle click fails (covered by cards), try force click
            try:
                circle = page.query_selector('svg circle')
                if circle:
                    circle.click(force=True, timeout=3000)
                    page.wait_for_timeout(500)
            except Exception:
                print("  (Could not click graph node, skipping)")
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "10_evidence_detail.png"), full_page=False)

        # JS errors summary
        if js_errors:
            print(f"\n[!] {len(js_errors)} JS errors:")
            for e in js_errors[:5]:
                print(f"  - {e[:120]}")
        else:
            print("\n[OK] 0 JS errors")

        print(f"\n[DONE] {10} screenshots saved to {SCREENSHOTS_DIR}")
        for f in sorted(os.listdir(SCREENSHOTS_DIR)):
            if f.endswith('.png'):
                fpath = os.path.join(SCREENSHOTS_DIR, f)
                size_kb = os.path.getsize(fpath) / 1024
                print(f"  {f} ({size_kb:.0f} KB)")

        browser.close()


if __name__ == "__main__":
    main()
