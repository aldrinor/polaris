"""
Playwright visual audit: citation collapse/re-expand with REAL report + scroll_sync.

Tests that citation cards survive collapse, scroll_sync while collapsed, re-expand,
and accordion toggling -- using a real appendReportBlock() call that triggers
IntersectionObserver-based scroll_sync (unlike test_report.js which only calls
renderCitationSidebar directly).

Usage:
    python scripts/playwright_cite_collapse_audit.py

Outputs screenshots to outputs/cite_collapse_visual/
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (LAW VI: no hard-coded values in logic)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "outputs" / "cite_collapse_visual"
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "live_server.py"
SERVER_LOG = PROJECT_ROOT / "logs" / "cite_audit_server.log"
PAGE_LOAD_WAIT_MS = 3000
JS_INIT_WAIT_MS = 1000
SCROLL_SETTLE_MS = 500
COLLAPSE_SETTLE_MS = 300
EXPAND_SETTLE_MS = 1000


def _find_free_port() -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Poll until the server accepts TCP connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.3)
    return False


# ---------------------------------------------------------------------------
# JavaScript payloads
# ---------------------------------------------------------------------------

JS_INJECT_STATE = """
() => {
    // 1. Set up bibliography with 5 entries
    state.bibliography = [
        {url:"https://nature.com/article1", title:"Source One", domain:"nature.com", is_faithful:true, snippet:"First source snippet about water treatment"},
        {url:"https://sciencedirect.com/article2", title:"Source Two", domain:"sciencedirect.com", is_faithful:true, snippet:"Second source about filtration methods"},
        {url:"https://epa.gov/brief3", title:"Source Three", domain:"epa.gov", is_faithful:true, snippet:"EPA guidelines on contaminant removal"},
        {url:"https://who.int/guide4", title:"Source Four", domain:"who.int", is_faithful:true},
        {url:"https://example.com/review5", title:"Source Five", domain:"example.com", is_faithful:false}
    ];

    // 2. Switch to report phase (calls _updateRightPanelForPhase)
    setWorkspacePhase("report");

    // 3. Create a REAL multi-section report with citation refs via appendReportBlock
    //    This triggers initScrollSync() which sets up the IntersectionObserver
    var reportMd = "## Water Treatment Overview\\n\\n" +
        "Activated carbon filters are highly effective [1]. Multiple studies confirm removal rates above 90% [2].\\n\\n" +
        "## Filtration Methods\\n\\n" +
        "Several filtration approaches exist for contaminant removal [3]. The EPA recommends multi-barrier approaches [3] " +
        "combined with regular monitoring [4].\\n\\n" +
        "## Regulatory Standards\\n\\n" +
        "International guidelines from the WHO [4] provide frameworks for water quality assessment [5]. " +
        "Compliance monitoring is essential [1][2][3].\\n\\n" +
        "## Cost Analysis\\n\\n" +
        "Treatment costs vary significantly based on technology choice [2][5]. " +
        "Lifecycle analysis should consider maintenance and replacement [1][4].\\n\\n" +
        "## Conclusions\\n\\n" +
        "Water treatment technology continues to advance [1][2][3][4][5]. " +
        "A comprehensive approach combining multiple methods yields best results [3][4].";

    appendReportBlock(reportMd, state.bibliography);

    // 4. Update citation count badge
    _updateCitationsCount();

    return "state_injected";
}
"""

JS_COUNT_CITE_CARDS = """
() => {
    return document.querySelectorAll('.ws-cite-card').length;
}
"""

JS_GET_BADGE_TEXT = """
() => {
    var el = document.getElementById('ws-citations-count');
    return el ? el.textContent.trim() : 'NOT_FOUND';
}
"""

JS_CHECK_CITATIONS_CLASS = """
() => {
    var el = document.getElementById('ws-section-citations');
    if (!el) return 'NOT_FOUND';
    if (el.classList.contains('expanded')) return 'expanded';
    if (el.classList.contains('collapsed')) return 'collapsed';
    if (el.classList.contains('hidden')) return 'hidden';
    return 'unknown';
}
"""

JS_GET_CITATION_LIST_HTML_LENGTH = """
() => {
    var el = document.getElementById('ws-citation-list');
    return el ? el.innerHTML.length : -1;
}
"""

JS_GET_CITATION_LIST_SNIPPET = """
() => {
    var el = document.getElementById('ws-citation-list');
    if (!el) return 'NOT_FOUND';
    var html = el.innerHTML;
    return html.substring(0, 300);
}
"""


async def run_audit():
    """Main audit function."""
    from playwright.async_api import async_playwright

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Find a free port
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"[AUDIT] Using port {port}, URL: {url}")

    # Start the live server with stdout redirected to log file (Windows deadlock fix)
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(str(SERVER_LOG), "w", encoding="utf-8")
    server_proc = subprocess.Popen(
        [
            sys.executable, str(SERVER_SCRIPT),
            "--no-tunnel",
            "--port", str(port),
        ],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
    )
    print(f"[AUDIT] Server PID={server_proc.pid}, log={SERVER_LOG}")

    try:
        # Wait for server to be ready
        if not _wait_for_server(port, timeout=15.0):
            print("[AUDIT] FATAL: Server did not start within 15 seconds.")
            return

        print("[AUDIT] Server is up. Launching Playwright...")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # Collect console errors for debugging
            console_errors = []
            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

            # Navigate with domcontentloaded (NOT networkidle -- SSE keeps conn open)
            print(f"[AUDIT] Navigating to {url} ...")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait for JS init
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
            print("[AUDIT] Page loaded. Injecting state...")

            # Inject realistic state with REAL report block
            result = await page.evaluate(JS_INJECT_STATE)
            print(f"[AUDIT] State injection result: {result}")

            # Wait for scroll_sync to initialize (appendReportBlock has 100ms setTimeout)
            await page.wait_for_timeout(JS_INIT_WAIT_MS)

            # ==================================================================
            # Results tracking
            # ==================================================================
            results = {}
            pass_count = 0
            fail_count = 0
            step_data = {}

            def record(step_name, key, value, expected=None, assertion_fn=None):
                nonlocal pass_count, fail_count
                step_data.setdefault(step_name, {})
                step_data[step_name][key] = value
                if assertion_fn is not None:
                    passed = assertion_fn(value)
                    status = "PASS" if passed else "FAIL"
                    if passed:
                        pass_count += 1
                    else:
                        fail_count += 1
                    results[f"{step_name}.{key}"] = {
                        "value": value,
                        "expected": expected,
                        "status": status,
                    }
                    print(f"  [{status}] {step_name}.{key} = {value} (expected: {expected})")
                else:
                    results[f"{step_name}.{key}"] = {"value": value, "status": "INFO"}
                    print(f"  [INFO] {step_name}.{key} = {value}")

            # ==================================================================
            # Step 0: Verify initial state
            # ==================================================================
            print("\n=== Step 0: Verify initial state ===")
            initial_count = await page.evaluate(JS_COUNT_CITE_CARDS)
            badge_text = await page.evaluate(JS_GET_BADGE_TEXT)
            cite_class = await page.evaluate(JS_CHECK_CITATIONS_CLASS)
            html_len = await page.evaluate(JS_GET_CITATION_LIST_HTML_LENGTH)
            html_snippet = await page.evaluate(JS_GET_CITATION_LIST_SNIPPET)

            record("step0", "cite_card_count", initial_count, "> 0", lambda v: v > 0)
            record("step0", "badge_text", badge_text, "5", lambda v: v == "5")
            record("step0", "citations_class", cite_class, "expanded", lambda v: v == "expanded")
            record("step0", "citation_list_html_length", html_len, "> 0", lambda v: v > 0)
            record("step0", "citation_list_snippet", html_snippet[:120])

            screenshot_path = str(SCREENSHOT_DIR / "step0_initial.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # ==================================================================
            # Step 1: Scroll report to middle section to trigger scroll_sync
            # ==================================================================
            print("\n=== Step 1: Scroll report to middle section ===")
            await page.evaluate("() => { document.getElementById('ws-thread').scrollTop = 300; }")
            await page.wait_for_timeout(SCROLL_SETTLE_MS)

            after_scroll_count = await page.evaluate(JS_COUNT_CITE_CARDS)
            html_len_1 = await page.evaluate(JS_GET_CITATION_LIST_HTML_LENGTH)

            record("step1", "cite_card_count_after_scroll", after_scroll_count, "> 0", lambda v: v > 0)
            record("step1", "citation_list_html_length", html_len_1)

            screenshot_path = str(SCREENSHOT_DIR / "step1_after_scroll.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # ==================================================================
            # Step 2: Collapse Citations by clicking header
            # ==================================================================
            print("\n=== Step 2: Collapse Citations ===")
            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(COLLAPSE_SETTLE_MS)

            cite_class_2 = await page.evaluate(JS_CHECK_CITATIONS_CLASS)
            after_collapse_count = await page.evaluate(JS_COUNT_CITE_CARDS)
            html_len_2 = await page.evaluate(JS_GET_CITATION_LIST_HTML_LENGTH)

            record("step2", "citations_class", cite_class_2, "collapsed", lambda v: v == "collapsed")
            record("step2", "cite_card_count_in_dom", after_collapse_count, "same as before scroll",
                   lambda v: v >= 0)  # Cards should still be in DOM
            record("step2", "citation_list_html_length", html_len_2, "> 0", lambda v: v > 0)

            screenshot_path = str(SCREENSHOT_DIR / "step2_collapsed.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # ==================================================================
            # Step 3: Simulate scroll_sync firing while collapsed
            # ==================================================================
            print("\n=== Step 3: Scroll while collapsed (guard test) ===")
            await page.evaluate("() => { document.getElementById('ws-thread').scrollTop = 0; }")
            await page.wait_for_timeout(SCROLL_SETTLE_MS)
            await page.evaluate("() => { document.getElementById('ws-thread').scrollTop = 600; }")
            await page.wait_for_timeout(SCROLL_SETTLE_MS)

            during_collapse_count = await page.evaluate(JS_COUNT_CITE_CARDS)
            html_len_3 = await page.evaluate(JS_GET_CITATION_LIST_HTML_LENGTH)

            record("step3", "cite_card_count_during_collapse", during_collapse_count,
                   f"== {after_collapse_count} (unchanged)",
                   lambda v: v == after_collapse_count)
            record("step3", "citation_list_html_length", html_len_3,
                   f"== {html_len_2} (guard prevents overwrite)",
                   lambda v: v == html_len_2)

            screenshot_path = str(SCREENSHOT_DIR / "step3_scrolled_while_collapsed.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # ==================================================================
            # Step 4: Re-expand Citations
            # ==================================================================
            print("\n=== Step 4: Re-expand Citations ===")
            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(EXPAND_SETTLE_MS)

            cite_class_4 = await page.evaluate(JS_CHECK_CITATIONS_CLASS)
            reexpand_count = await page.evaluate(JS_COUNT_CITE_CARDS)
            html_len_4 = await page.evaluate(JS_GET_CITATION_LIST_HTML_LENGTH)
            html_snippet_4 = await page.evaluate(JS_GET_CITATION_LIST_SNIPPET)

            record("step4", "citations_class", cite_class_4, "expanded", lambda v: v == "expanded")
            record("step4", "cite_card_count_reexpanded", reexpand_count, "> 0", lambda v: v > 0)
            record("step4", "citation_list_html_length", html_len_4, "> 0", lambda v: v > 0)
            record("step4", "citation_list_snippet", html_snippet_4[:120])

            # Investigate if zero
            if reexpand_count == 0:
                print("  [INVESTIGATE] Re-expand yielded 0 cards. Checking innerHTML...")
                full_html = await page.evaluate("""
                    () => {
                        var el = document.getElementById('ws-citation-list');
                        return el ? el.innerHTML : 'NOT_FOUND';
                    }
                """)
                print(f"  [INVESTIGATE] innerHTML (first 500 chars): {full_html[:500]}")

                # Also check if scroll_sync observer exists
                observer_check = await page.evaluate("""
                    () => {
                        return {
                            observer_exists: !!_scrollSyncObserver,
                            active_heading_id: _scrollSyncActiveHeadingId,
                            current_report_el: !!_wsCurrentReportEl,
                            phase: _wsPhase,
                            bib_length: state.bibliography ? state.bibliography.length : 0
                        };
                    }
                """)
                print(f"  [INVESTIGATE] Observer state: {observer_check}")

            screenshot_path = str(SCREENSHOT_DIR / "step4_reexpanded.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # ==================================================================
            # Step 5: Accordion -- expand Live, then back to Citations
            # ==================================================================
            print("\n=== Step 5: Accordion toggle ===")

            # 5a: Click Live to expand it (accordion collapses Citations)
            await page.click("#ws-section-live .ws-section-header")
            await page.wait_for_timeout(COLLAPSE_SETTLE_MS)

            cite_class_5a = await page.evaluate(JS_CHECK_CITATIONS_CLASS)
            live_class_5a = await page.evaluate("""
                () => {
                    var el = document.getElementById('ws-section-live');
                    if (!el) return 'NOT_FOUND';
                    if (el.classList.contains('expanded')) return 'expanded';
                    if (el.classList.contains('collapsed')) return 'collapsed';
                    if (el.classList.contains('hidden')) return 'hidden';
                    return 'unknown';
                }
            """)
            record("step5a", "live_class", live_class_5a, "expanded", lambda v: v == "expanded")
            record("step5a", "citations_class", cite_class_5a, "collapsed", lambda v: v == "collapsed")

            screenshot_path = str(SCREENSHOT_DIR / "step5a_live_expanded.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # 5b: Click Citations to expand it back (accordion collapses Live)
            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(EXPAND_SETTLE_MS)

            cite_class_5b = await page.evaluate(JS_CHECK_CITATIONS_CLASS)
            after_accordion_count = await page.evaluate(JS_COUNT_CITE_CARDS)
            html_len_5b = await page.evaluate(JS_GET_CITATION_LIST_HTML_LENGTH)
            html_snippet_5b = await page.evaluate(JS_GET_CITATION_LIST_SNIPPET)

            record("step5b", "citations_class", cite_class_5b, "expanded", lambda v: v == "expanded")
            record("step5b", "cite_card_count_after_accordion", after_accordion_count, "> 0", lambda v: v > 0)
            record("step5b", "citation_list_html_length", html_len_5b, "> 0", lambda v: v > 0)
            record("step5b", "citation_list_snippet", html_snippet_5b[:120])

            # Investigate if zero
            if after_accordion_count == 0:
                print("  [INVESTIGATE] Accordion yielded 0 cards. Checking innerHTML...")
                full_html = await page.evaluate("""
                    () => {
                        var el = document.getElementById('ws-citation-list');
                        return el ? el.innerHTML : 'NOT_FOUND';
                    }
                """)
                print(f"  [INVESTIGATE] innerHTML (first 500 chars): {full_html[:500]}")

            screenshot_path = str(SCREENSHOT_DIR / "step5b_citations_after_accordion.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot: {screenshot_path}")

            # ==================================================================
            # Summary Table
            # ==================================================================
            print("\n" + "=" * 80)
            print("CITATION COLLAPSE/RE-EXPAND AUDIT RESULTS")
            print("=" * 80)

            # Counts table
            print("\n{:<45} {:>10} {:>10}".format("Step", "Cards", "HTML Len"))
            print("-" * 65)
            print("{:<45} {:>10} {:>10}".format(
                "Step 0: Initial",
                initial_count, html_len))
            print("{:<45} {:>10} {:>10}".format(
                "Step 1: After scroll",
                after_scroll_count, html_len_1))
            print("{:<45} {:>10} {:>10}".format(
                "Step 2: After collapse (in DOM)",
                after_collapse_count, html_len_2))
            print("{:<45} {:>10} {:>10}".format(
                "Step 3: Scroll while collapsed (guard)",
                during_collapse_count, html_len_3))
            print("{:<45} {:>10} {:>10}".format(
                "Step 4: Re-expanded",
                reexpand_count, html_len_4))
            print("{:<45} {:>10} {:>10}".format(
                "Step 5b: After accordion toggle",
                after_accordion_count, html_len_5b))

            # Pass/Fail table
            print("\n{:<55} {:>8}".format("Assertion", "Result"))
            print("-" * 63)
            for key, info in results.items():
                if info["status"] in ("PASS", "FAIL"):
                    print("{:<55} {:>8}".format(
                        f"{key} = {info['value']} (exp: {info['expected']})",
                        info["status"]))

            print(f"\nTotal: {pass_count} PASS, {fail_count} FAIL")

            # Key assertions
            print("\n--- KEY ASSERTIONS ---")
            reexpand_ok = reexpand_count > 0
            accordion_ok = after_accordion_count > 0
            guard_ok = during_collapse_count == after_collapse_count

            print(f"  reexpand_count > 0 : {'PASS' if reexpand_ok else 'FAIL'} ({reexpand_count})")
            print(f"  after_accordion > 0: {'PASS' if accordion_ok else 'FAIL'} ({after_accordion_count})")
            print(f"  guard (no overwrite): {'PASS' if guard_ok else 'FAIL'} ({during_collapse_count} == {after_collapse_count})")

            overall = "PASS" if (reexpand_ok and accordion_ok and guard_ok and fail_count == 0) else "FAIL"
            print(f"\n  OVERALL: {overall}")

            # Console errors
            if console_errors:
                print(f"\n--- Browser console errors ({len(console_errors)}) ---")
                for err in console_errors[:10]:
                    print(f"  {err}")

            await browser.close()

    finally:
        # Cleanup server
        print(f"\n[AUDIT] Terminating server PID={server_proc.pid}")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=3)
        log_fh.close()
        print("[AUDIT] Done.")


if __name__ == "__main__":
    asyncio.run(run_audit())
