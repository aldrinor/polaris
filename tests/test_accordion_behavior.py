"""
Playwright test: Accordion behavior of the right-panel sections in POLARIS workspace.

Validates the 3-section accordion (Live, Citations, Memory) across 6 scenarios:
  S1: Report-phase defaults after test_report.js injection
  S2: Click Live -> Live expands, others collapse
  S3: Click Citations -> Citations expands, others collapse
  S4: Click Memory -> Memory expands, others collapse
  S5: Click expanded section -> it collapses (all collapsed)
  S6: Height measurement: expanded section >= 3x collapsed section

Usage: python tests/test_accordion_behavior.py
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "accordion_audit"
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "live_server.py"
TEST_REPORT_JS = PROJECT_ROOT / "scripts" / "static" / "js" / "test_report.js"
SERVER_LOG = OUTPUTS_DIR / "server.log"
MAX_WAIT_SECONDS = 15
SECTION_IDS = ["live", "citations", "memory"]


def find_free_port() -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> subprocess.Popen:
    """Start the live_server.py on the given port, redirecting stdout to log file."""
    log_handle = open(SERVER_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable, str(SERVER_SCRIPT),
            "--no-tunnel",
            "--port", str(port),
        ],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
    )
    return proc


async def wait_for_server(port: int, timeout: float = MAX_WAIT_SECONDS) -> bool:
    """Poll the server until it responds or timeout."""
    import aiohttp

    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Helpers for Playwright assertions
# ---------------------------------------------------------------------------
async def has_class(page, selector: str, cls: str) -> bool:
    """Check if an element has a specific CSS class."""
    return await page.evaluate(
        f"document.querySelector('{selector}').classList.contains('{cls}')"
    )


async def get_display(page, selector: str) -> str:
    """Get the computed display value of an element."""
    return await page.evaluate(
        f"window.getComputedStyle(document.querySelector('{selector}')).display"
    )


async def get_height(page, selector: str) -> float:
    """Get the bounding rect height of an element."""
    return await page.evaluate(
        f"document.querySelector('{selector}').getBoundingClientRect().height"
    )


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------
class CheckResult:
    def __init__(self, scenario: str, check: str, passed: bool, detail: str = ""):
        self.scenario = scenario
        self.check = check
        self.passed = passed
        self.detail = detail

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        detail_str = f"  ({self.detail})" if self.detail else ""
        return f"  [{status}] {self.scenario} / {self.check}{detail_str}"


results: list = []


def check(scenario: str, name: str, condition: bool, detail: str = ""):
    r = CheckResult(scenario, name, condition, detail)
    results.append(r)
    print(str(r))


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------
async def run_tests():
    from playwright.async_api import async_playwright

    port = find_free_port()
    print(f"[INFO] Using port {port}")
    print(f"[INFO] Starting server...")
    server_proc = start_server(port)

    try:
        ready = await wait_for_server(port)
        if not ready:
            print("[FATAL] Server did not become ready within 15s. Check outputs/accordion_audit/server.log")
            return False

        print(f"[INFO] Server ready on http://127.0.0.1:{port}")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # Navigate to dashboard -- use domcontentloaded (NOT networkidle)
            # because the SSE /api/events stream keeps the connection open forever.
            await page.goto(
                f"http://127.0.0.1:{port}/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            # Wait for the workspace container to be present in DOM
            await page.wait_for_selector("#workspace", state="attached", timeout=10000)
            # Extra settle time for JS initialization
            await page.wait_for_timeout(3000)

            # Read and inject test_report.js
            test_report_code = TEST_REPORT_JS.read_text(encoding="utf-8")
            await page.evaluate(test_report_code)
            await page.wait_for_timeout(500)

            # =================================================================
            # S1: Report phase defaults
            # =================================================================
            scenario = "S1"
            print(f"\n--- {scenario}: Report phase defaults ---")

            live_collapsed = await has_class(page, "#ws-section-live", "collapsed")
            check(scenario, "Live is collapsed", live_collapsed)

            cite_expanded = await has_class(page, "#ws-section-citations", "expanded")
            check(scenario, "Citations is expanded", cite_expanded)

            mem_collapsed = await has_class(page, "#ws-section-memory", "collapsed")
            check(scenario, "Memory is collapsed", mem_collapsed)

            cite_body_display = await get_display(page, "#ws-section-citations .ws-section-body")
            check(scenario, "Citations body visible", cite_body_display != "none",
                  f"display={cite_body_display}")

            live_body_display = await get_display(page, "#ws-section-live .ws-section-body")
            check(scenario, "Live body hidden", live_body_display == "none",
                  f"display={live_body_display}")

            # =================================================================
            # S2: Click Live -> Live expands, others collapse
            # =================================================================
            scenario = "S2"
            print(f"\n--- {scenario}: Click Live header ---")

            await page.click("#ws-section-live .ws-section-header")
            await page.wait_for_timeout(300)

            live_exp = await has_class(page, "#ws-section-live", "expanded")
            check(scenario, "Live is expanded", live_exp)

            cite_col = await has_class(page, "#ws-section-citations", "collapsed")
            check(scenario, "Citations is collapsed", cite_col)

            mem_col = await has_class(page, "#ws-section-memory", "collapsed")
            check(scenario, "Memory is collapsed", mem_col)

            live_body_vis = await get_display(page, "#ws-section-live .ws-section-body")
            check(scenario, "Live body visible", live_body_vis != "none",
                  f"display={live_body_vis}")

            cite_body_hid = await get_display(page, "#ws-section-citations .ws-section-body")
            check(scenario, "Citations body hidden", cite_body_hid == "none",
                  f"display={cite_body_hid}")

            await page.screenshot(
                path=str(OUTPUTS_DIR / "accordion_live_expanded.png"),
                full_page=False,
            )
            print(f"  [SCREENSHOT] accordion_live_expanded.png")

            # =================================================================
            # S3: Click Citations -> Citations expands, others collapse
            # =================================================================
            scenario = "S3"
            print(f"\n--- {scenario}: Click Citations header ---")

            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(300)

            cite_exp = await has_class(page, "#ws-section-citations", "expanded")
            check(scenario, "Citations is expanded", cite_exp)

            live_col = await has_class(page, "#ws-section-live", "collapsed")
            check(scenario, "Live is collapsed", live_col)

            mem_col2 = await has_class(page, "#ws-section-memory", "collapsed")
            check(scenario, "Memory is collapsed", mem_col2)

            await page.screenshot(
                path=str(OUTPUTS_DIR / "accordion_citations_expanded.png"),
                full_page=False,
            )
            print(f"  [SCREENSHOT] accordion_citations_expanded.png")

            # =================================================================
            # S4: Click Memory -> Memory expands, others collapse
            # =================================================================
            scenario = "S4"
            print(f"\n--- {scenario}: Click Memory header ---")

            await page.click("#ws-section-memory .ws-section-header")
            await page.wait_for_timeout(300)

            mem_exp = await has_class(page, "#ws-section-memory", "expanded")
            check(scenario, "Memory is expanded", mem_exp)

            live_col3 = await has_class(page, "#ws-section-live", "collapsed")
            check(scenario, "Live is collapsed", live_col3)

            cite_col3 = await has_class(page, "#ws-section-citations", "collapsed")
            check(scenario, "Citations is collapsed", cite_col3)

            await page.screenshot(
                path=str(OUTPUTS_DIR / "accordion_memory_expanded.png"),
                full_page=False,
            )
            print(f"  [SCREENSHOT] accordion_memory_expanded.png")

            # =================================================================
            # S5: Click expanded Memory -> all collapse
            # =================================================================
            scenario = "S5"
            print(f"\n--- {scenario}: Click expanded Memory (toggle off) ---")

            await page.click("#ws-section-memory .ws-section-header")
            await page.wait_for_timeout(300)

            mem_now_col = await has_class(page, "#ws-section-memory", "collapsed")
            check(scenario, "Memory is collapsed", mem_now_col)

            live_still_col = await has_class(page, "#ws-section-live", "collapsed")
            check(scenario, "Live is collapsed", live_still_col)

            cite_still_col = await has_class(page, "#ws-section-citations", "collapsed")
            check(scenario, "Citations is collapsed", cite_still_col)

            all_collapsed = mem_now_col and live_still_col and cite_still_col
            check(scenario, "All three are collapsed", all_collapsed)

            # =================================================================
            # S6: Height measurement
            # =================================================================
            scenario = "S6"
            print(f"\n--- {scenario}: Height measurement ---")

            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(300)

            cite_height = await get_height(page, "#ws-section-citations")
            live_height = await get_height(page, "#ws-section-live")

            ratio = cite_height / live_height if live_height > 0 else 0
            check(scenario, "Citations height >= 3x Live height",
                  ratio >= 3.0,
                  f"citations={cite_height:.1f}px, live={live_height:.1f}px, ratio={ratio:.1f}x")

            await browser.close()

    finally:
        # Clean up server
        print("\n[INFO] Shutting down server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=3)
        print("[INFO] Server stopped.")

    # =================================================================
    # Summary
    # =================================================================
    print("\n" + "=" * 60)
    print("ACCORDION BEHAVIOR TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    for r in results:
        print(str(r))

    print(f"\n  Total: {total}  |  PASS: {passed}  |  FAIL: {failed}")

    if failed == 0:
        print("\n  ALL CHECKS PASSED")
    else:
        print(f"\n  {failed} CHECK(S) FAILED")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
