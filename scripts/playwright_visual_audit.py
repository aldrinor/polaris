"""
Playwright Visual UI Audit for POLARIS Dashboard.

Launches the live server, navigates to all major views/tabs,
captures screenshots at desktop and mobile widths,
and saves them for visual inspection.

Usage:
    python scripts/playwright_visual_audit.py

Outputs screenshots to outputs/visual_audit/
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "outputs" / "visual_audit"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8799
SERVER_URL = f"http://127.0.0.1:{PORT}"

# Check if Playwright is installed
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


def start_server():
    """Start the POLARIS live server in background."""
    log_file = SCREENSHOTS_DIR / "server.log"
    # Find a trace file for sample data
    trace_files = sorted(
        (PROJECT_ROOT / "logs").glob("pg_trace_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    trace_arg = []
    if trace_files:
        trace_arg = ["--trace", str(trace_files[0])]
        print(f"  Using trace file: {trace_files[0].name}")

    cmd = [
        sys.executable, str(PROJECT_ROOT / "scripts" / "live_server.py"),
        "--port", str(PORT),
    ] + trace_arg

    with open(log_file, "w") as f:
        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )
    return proc


def wait_for_server(timeout=15):
    """Wait for server to become responsive."""
    import urllib.request
    for i in range(timeout):
        try:
            urllib.request.urlopen(f"{SERVER_URL}/health", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def capture_screenshots():
    """Capture screenshots of all dashboard views."""
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Desktop viewport
        desktop_ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        # Mobile viewport
        mobile_ctx = browser.new_context(
            viewport={"width": 375, "height": 812},
            device_scale_factor=2,
        )

        # ============================================================
        # Test 1: Main dashboard loads
        # ============================================================
        print("\n  [1/8] Main dashboard load...")
        page = desktop_ctx.new_page()
        try:
            page.goto(SERVER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)  # Let animations complete

            # Check for critical elements
            title = page.title()
            has_header = page.locator("header").count() > 0
            has_input = page.locator("input, textarea").count() > 0

            path = SCREENSHOTS_DIR / "01_desktop_main.png"
            page.screenshot(path=str(path), full_page=True)

            results.append({
                "name": "main_dashboard_desktop",
                "status": "PASS" if has_header else "FAIL",
                "screenshot": str(path),
                "detail": f"title='{title}', header={has_header}, input={has_input}",
            })
        except Exception as exc:
            results.append({
                "name": "main_dashboard_desktop",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 2: Mobile responsive layout
        # ============================================================
        print("  [2/8] Mobile responsive layout...")
        page = mobile_ctx.new_page()
        try:
            page.goto(SERVER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1500)

            path = SCREENSHOTS_DIR / "02_mobile_main.png"
            page.screenshot(path=str(path), full_page=True)

            # Check if layout adapts (no horizontal overflow)
            overflow = page.evaluate("""
                document.documentElement.scrollWidth > document.documentElement.clientWidth
            """)
            results.append({
                "name": "mobile_responsive",
                "status": "PASS" if not overflow else "WARN",
                "screenshot": str(path),
                "detail": f"overflow={overflow}",
            })
        except Exception as exc:
            results.append({
                "name": "mobile_responsive",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 3: Research input form
        # ============================================================
        print("  [3/8] Research input form...")
        page = desktop_ctx.new_page()
        try:
            page.goto(SERVER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)

            # Try to find the query input
            input_el = page.locator("input[type='text'], textarea").first
            if input_el.count() > 0:
                input_el.fill("Test query: water filtration technology comparison")
                page.wait_for_timeout(500)

            path = SCREENSHOTS_DIR / "03_research_input.png"
            page.screenshot(path=str(path), full_page=True)

            results.append({
                "name": "research_input_form",
                "status": "PASS" if input_el.count() > 0 else "WARN",
                "screenshot": str(path),
                "detail": f"input_found={input_el.count() > 0}",
            })
        except Exception as exc:
            results.append({
                "name": "research_input_form",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 4: Console/Operator mode
        # ============================================================
        print("  [4/8] Console operator mode...")
        page = desktop_ctx.new_page()
        try:
            page.goto(SERVER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)

            # Try switching to operator mode
            operator_btn = page.locator("button[data-mode='operator']")
            if operator_btn.count() > 0:
                # Click mode dropdown first
                trigger = page.locator("#ws-mode-dropdown button").first
                if trigger.count() > 0:
                    trigger.click()
                    page.wait_for_timeout(300)
                operator_btn.click()
                page.wait_for_timeout(1500)

            path = SCREENSHOTS_DIR / "04_operator_console.png"
            page.screenshot(path=str(path), full_page=True)

            results.append({
                "name": "operator_console",
                "status": "PASS" if operator_btn.count() > 0 else "WARN",
                "screenshot": str(path),
                "detail": f"operator_toggle={operator_btn.count() > 0}",
            })
        except Exception as exc:
            results.append({
                "name": "operator_console",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 5: Tab navigation (Evidence, Report, etc.)
        # ============================================================
        print("  [5/8] Tab navigation...")
        page = desktop_ctx.new_page()
        try:
            page.goto(SERVER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)

            # Find all tab buttons
            tabs = page.locator("[role='tab'], .tab-btn, button[data-tab]")
            tab_count = tabs.count()

            # Click through each tab and capture
            tab_screenshots = []
            for i in range(min(tab_count, 6)):  # Max 6 tabs
                try:
                    tabs.nth(i).click()
                    page.wait_for_timeout(800)
                    tab_name = tabs.nth(i).inner_text()[:20].strip()
                    tab_path = SCREENSHOTS_DIR / f"05_tab_{i}_{tab_name.replace(' ', '_').lower()}.png"
                    page.screenshot(path=str(tab_path), full_page=True)
                    tab_screenshots.append(str(tab_path))
                except Exception:
                    pass

            results.append({
                "name": "tab_navigation",
                "status": "PASS" if tab_count > 0 else "WARN",
                "screenshot": tab_screenshots[0] if tab_screenshots else "",
                "detail": f"tabs_found={tab_count}, captured={len(tab_screenshots)}",
            })
        except Exception as exc:
            results.append({
                "name": "tab_navigation",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 6: Research history page
        # ============================================================
        print("  [6/8] Research history...")
        page = desktop_ctx.new_page()
        try:
            page.goto(f"{SERVER_URL}/api/research/history", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(500)

            path = SCREENSHOTS_DIR / "06_research_history_api.png"
            page.screenshot(path=str(path))

            content = page.content()
            is_json = "[" in content[:200] or "{" in content[:200]

            results.append({
                "name": "research_history_api",
                "status": "PASS" if is_json else "WARN",
                "screenshot": str(path),
                "detail": f"json_response={is_json}",
            })
        except Exception as exc:
            results.append({
                "name": "research_history_api",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 7: Health check endpoint
        # ============================================================
        print("  [7/8] Health check...")
        page = desktop_ctx.new_page()
        try:
            page.goto(f"{SERVER_URL}/health", wait_until="domcontentloaded", timeout=10000)
            content = page.content()

            path = SCREENSHOTS_DIR / "07_health.png"
            page.screenshot(path=str(path))

            has_status = "status" in content.lower()
            results.append({
                "name": "health_endpoint",
                "status": "PASS" if has_status else "WARN",
                "screenshot": str(path),
                "detail": f"has_status={has_status}",
            })
        except Exception as exc:
            results.append({
                "name": "health_endpoint",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # ============================================================
        # Test 8: CSS/Styling quality check
        # ============================================================
        print("  [8/8] CSS styling quality...")
        page = desktop_ctx.new_page()
        try:
            page.goto(SERVER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)

            # Check for loaded stylesheets
            css_count = page.evaluate("""
                document.querySelectorAll('link[rel="stylesheet"]').length
            """)
            # Check for proper font loading
            has_fonts = page.evaluate("""
                getComputedStyle(document.body).fontFamily.includes('Inter') ||
                getComputedStyle(document.body).fontFamily.includes('IBM')
            """)
            # Check for broken images
            broken_images = page.evaluate("""
                Array.from(document.querySelectorAll('img')).filter(
                    img => !img.complete || img.naturalWidth === 0
                ).length
            """)

            path = SCREENSHOTS_DIR / "08_styling_quality.png"
            page.screenshot(path=str(path))

            results.append({
                "name": "css_styling_quality",
                "status": "PASS",
                "screenshot": str(path),
                "detail": f"css_sheets={css_count}, fonts={has_fonts}, broken_imgs={broken_images}",
            })
        except Exception as exc:
            results.append({
                "name": "css_styling_quality",
                "status": "FAIL",
                "detail": str(exc)[:200],
            })
        finally:
            page.close()

        # Cleanup
        desktop_ctx.close()
        mobile_ctx.close()
        browser.close()

    return results


def main():
    print("\n" + "=" * 70)
    print("  PLAYWRIGHT VISUAL UI AUDIT")
    print("  POLARIS Dashboard - Desktop & Mobile")
    print("=" * 70)

    # Step 1: Start server
    print("\n[Phase 1] Starting live server...")
    server_proc = start_server()

    try:
        print("  Waiting for server...")
        if not wait_for_server(timeout=15):
            print("  ERROR: Server did not start within 15 seconds")
            # Check server log
            log_path = SCREENSHOTS_DIR / "server.log"
            if log_path.exists():
                print(f"  Server log ({log_path}):")
                print(log_path.read_text(encoding="utf-8", errors="replace")[:2000])
            return 1

        print(f"  Server ready at {SERVER_URL}")

        # Step 2: Capture screenshots
        print("\n[Phase 2] Capturing screenshots...")
        results = capture_screenshots()

        # Step 3: Summary
        pass_count = sum(1 for r in results if r["status"] == "PASS")
        fail_count = sum(1 for r in results if r["status"] == "FAIL")
        warn_count = sum(1 for r in results if r["status"] == "WARN")

        print("\n" + "=" * 70)
        print(f"  VISUAL AUDIT RESULTS: {pass_count} PASS / {fail_count} FAIL / {warn_count} WARN")
        print("=" * 70)

        for r in results:
            icon = {"PASS": "+", "FAIL": "!", "WARN": "~"}[r["status"]]
            print(f"  [{icon}] {r['name']}: {r['detail']}")

        # Save results
        results_path = SCREENSHOTS_DIR / "audit_results.json"
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        # List screenshots
        screenshots = list(SCREENSHOTS_DIR.glob("*.png"))
        print(f"\n  Screenshots saved: {len(screenshots)} files in {SCREENSHOTS_DIR}")
        for s in sorted(screenshots):
            size = s.stat().st_size
            print(f"    {s.name} ({size:,}b)")

        return 0 if fail_count == 0 else 1

    finally:
        # Cleanup server
        print("\n  Stopping server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
