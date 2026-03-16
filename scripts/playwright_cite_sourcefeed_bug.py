"""
Playwright bug reproduction: collapse/re-expand Citations shows #ws-source-feed
instead of #ws-citation-list.

Bug mechanism: After a running->report phase transition, inline display styles on
#ws-source-feed and #ws-citation-list can become stale. When the Citations section
is collapsed and re-expanded, the source feed (running-phase content showing
"Sources will appear here as they are discovered...") appears instead of the
citation list (report-phase citation cards).

The fix: _toggleRightSection("citations") now calls _updateCitationsSectionContent()
on expand, which resets inline styles based on the current _wsPhase.

Usage:
    python scripts/playwright_cite_sourcefeed_bug.py

Outputs screenshots to outputs/cite_sourcefeed_bug/
"""

import asyncio
import json
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
SCREENSHOT_DIR = PROJECT_ROOT / "outputs" / "cite_sourcefeed_bug"
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "live_server.py"
SERVER_LOG = PROJECT_ROOT / "logs" / "cite_sourcefeed_bug_server.log"
PAGE_LOAD_WAIT_MS = 3000
SETUP_WAIT_MS = 2000
COLLAPSE_SETTLE_MS = 300
EXPAND_SETTLE_MS = 500
PHASE_TRANSITION_WAIT_MS = 500


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

JS_SETUP_RUNNING_TO_REPORT = """
() => {
    // 1. Start in running phase (sets srcFeed.display="", citeList.display="none")
    setWorkspacePhase("running");

    // 2. Wait a beat, then transition to report (sets srcFeed.display="none", citeList.display="")
    setTimeout(function() {
        state.bibliography = [];
        for (var i = 1; i <= 20; i++) {
            state.bibliography.push({
                url: "https://source" + i + ".example.com/article",
                title: "Research Source " + i,
                domain: "source" + i + ".example.com",
                is_faithful: i <= 16,
                snippet: "Snippet for source " + i
            });
        }
        setWorkspacePhase("report");

        // Render report with citations
        var reportMd = "## Section 1\\n\\nContent with citations [1][2][3].\\n\\n" +
            "## Section 2\\n\\nMore content [4][5][6].\\n\\n" +
            "## Section 3\\n\\nAdditional findings [7][8][9][10].";
        appendReportBlock(reportMd, state.bibliography);
        _updateCitationsCount();
        renderCitationSidebar([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]);
    }, 500);

    return "setup_started";
}
"""

JS_DIAGNOSE_STATE = """
() => {
    var srcFeed = document.getElementById("ws-source-feed");
    var citeList = document.getElementById("ws-citation-list");
    var citeCards = document.querySelectorAll(".ws-cite-card");
    var badge = document.getElementById("ws-citations-count");
    var sectionEl = document.getElementById("ws-section-citations");

    return {
        phase: typeof _wsPhase !== "undefined" ? _wsPhase : "UNDEFINED",
        cite_card_count: citeCards.length,
        badge_text: badge ? badge.textContent.trim() : "NOT_FOUND",
        section_class: sectionEl ? (
            sectionEl.classList.contains("expanded") ? "expanded" :
            sectionEl.classList.contains("collapsed") ? "collapsed" :
            sectionEl.classList.contains("hidden") ? "hidden" : "unknown"
        ) : "NOT_FOUND",
        src_feed_inline_display: srcFeed ? srcFeed.style.display : "NOT_FOUND",
        cite_list_inline_display: citeList ? citeList.style.display : "NOT_FOUND",
        src_feed_computed_display: srcFeed ? getComputedStyle(srcFeed).display : "NOT_FOUND",
        cite_list_computed_display: citeList ? getComputedStyle(citeList).display : "NOT_FOUND",
        src_feed_inner_100: srcFeed ? srcFeed.innerHTML.substring(0, 100) : "NOT_FOUND",
        cite_list_inner_100: citeList ? citeList.innerHTML.substring(0, 100) : "NOT_FOUND"
    };
}
"""

JS_CORRUPT_INLINE_STYLES = """
() => {
    // Simulate stale inline styles from running-phase call
    document.getElementById("ws-source-feed").style.display = "";
    document.getElementById("ws-citation-list").style.display = "none";
    return "corrupted";
}
"""

JS_RESET_RUNNING = """
() => {
    setWorkspacePhase("running");
    return "reset_to_running";
}
"""

JS_NATURAL_REPORT_TRANSITION = """
() => {
    setWorkspacePhase("report");
    _updateCitationsCount();
    renderCitationSidebar([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]);
    return "natural_report_transition";
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_diagnosis(label: str, diag: dict) -> None:
    """Print a structured diagnosis block."""
    print(f"\n  --- {label} ---")
    print(f"  _wsPhase:                   {diag['phase']}")
    print(f"  .ws-cite-card count:        {diag['cite_card_count']}")
    print(f"  #ws-citations-count badge:  {diag['badge_text']}")
    print(f"  section class:              {diag['section_class']}")
    print(f"  #ws-source-feed inline:     '{diag['src_feed_inline_display']}'")
    print(f"  #ws-citation-list inline:   '{diag['cite_list_inline_display']}'")
    print(f"  #ws-source-feed computed:   '{diag['src_feed_computed_display']}'")
    print(f"  #ws-citation-list computed: '{diag['cite_list_computed_display']}'")
    print(f"  #ws-source-feed HTML[:100]: {diag['src_feed_inner_100'][:80]}")
    print(f"  #ws-citation-list HTML[:100]: {diag['cite_list_inner_100'][:80]}")


def _check(
    results: dict,
    step: str,
    key: str,
    actual,
    expected,
    assertion_fn,
) -> bool:
    """Record a PASS/FAIL check and return the boolean."""
    passed = assertion_fn(actual)
    status = "PASS" if passed else "FAIL"
    results.setdefault(step, [])
    results[step].append({
        "key": key,
        "actual": actual,
        "expected": expected,
        "status": status,
    })
    print(f"  [{status}] {step}.{key} = {repr(actual)} (expected: {expected})")
    return passed


async def run_test():
    """Main test function."""
    from playwright.async_api import async_playwright

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Find a free port
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"[TEST] Using port {port}, URL: {url}")

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
    print(f"[TEST] Server PID={server_proc.pid}, log={SERVER_LOG}")

    results = {}
    total_pass = 0
    total_fail = 0
    screenshots = []

    try:
        # Wait for server to be ready
        if not _wait_for_server(port, timeout=15.0):
            print("[TEST] FATAL: Server did not start within 15 seconds.")
            return

        print("[TEST] Server is up. Launching Playwright...")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # Collect console errors for debugging
            console_errors = []
            page.on(
                "console",
                lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
                if msg.type == "error"
                else None,
            )

            # Navigate with domcontentloaded (NOT networkidle -- SSE keeps conn open)
            print(f"[TEST] Navigating to {url} ...")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait for JS init
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
            print("[TEST] Page loaded. Setting up running->report transition...")

            # ================================================================
            # SETUP: Simulate running->report transition
            # ================================================================
            result = await page.evaluate(JS_SETUP_RUNNING_TO_REPORT)
            print(f"[TEST] Setup injection result: {result}")

            # Wait for setTimeout(500) + rendering
            await page.wait_for_timeout(SETUP_WAIT_MS)
            print("[TEST] Setup complete. Beginning test steps.")

            # ================================================================
            # STEP 0: Verify report phase setup
            # ================================================================
            print("\n" + "=" * 60)
            print("STEP 0: Verify report phase setup")
            print("=" * 60)

            diag0 = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 0 Diagnosis", diag0)

            p = _check(results, "step0", "phase", diag0["phase"], "report", lambda v: v == "report")
            total_pass += int(p); total_fail += int(not p)

            # Note: appendReportBlock triggers initScrollSync() whose
            # IntersectionObserver may re-render the sidebar with only the
            # citations visible in the current viewport (e.g. 3 instead of 20).
            # The key assertion is that at least SOME cite cards exist,
            # proving the citation list has rendered content.
            p = _check(
                results, "step0", "cite_card_count",
                diag0["cite_card_count"],
                ">= 1 (scroll_sync may limit visible cards)",
                lambda v: v >= 1,
            )
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step0", "src_feed_computed_none", diag0["src_feed_computed_display"], "none", lambda v: v == "none")
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step0", "cite_list_computed_visible", diag0["cite_list_computed_display"], "NOT none", lambda v: v != "none")
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step0", "badge_text", diag0["badge_text"], "20", lambda v: v == "20")
            total_pass += int(p); total_fail += int(not p)

            ss_path = str(SCREENSHOT_DIR / "step0_report_ok.png")
            await page.screenshot(path=ss_path, full_page=False)
            screenshots.append(ss_path)
            print(f"  Screenshot saved: {ss_path}")

            # ================================================================
            # STEP 1: DELIBERATELY corrupt the inline styles (simulate the bug)
            # ================================================================
            print("\n" + "=" * 60)
            print("STEP 1: Corrupt inline styles to simulate the bug")
            print("=" * 60)

            corrupt_result = await page.evaluate(JS_CORRUPT_INLINE_STYLES)
            print(f"  Corruption result: {corrupt_result}")

            diag1 = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 1 Diagnosis (after corruption)", diag1)

            # After corruption, source feed should be visible (the bug!)
            p = _check(results, "step1", "src_feed_computed_visible", diag1["src_feed_computed_display"], "NOT none (bug shows feed)", lambda v: v != "none")
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step1", "cite_list_computed_none", diag1["cite_list_computed_display"], "none (bug hides list)", lambda v: v == "none")
            total_pass += int(p); total_fail += int(not p)

            # Source feed should contain the placeholder text
            p = _check(
                results, "step1", "src_feed_shows_placeholder",
                "Sources will appear" in diag1["src_feed_inner_100"],
                "True (placeholder text visible)",
                lambda v: v is True,
            )
            total_pass += int(p); total_fail += int(not p)

            ss_path = str(SCREENSHOT_DIR / "step1_corrupted.png")
            await page.screenshot(path=ss_path, full_page=False)
            screenshots.append(ss_path)
            print(f"  Screenshot saved: {ss_path}")

            # ================================================================
            # STEP 2: Collapse Citations
            # ================================================================
            print("\n" + "=" * 60)
            print("STEP 2: Collapse Citations section")
            print("=" * 60)

            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(COLLAPSE_SETTLE_MS)

            diag2 = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 2 Diagnosis (collapsed)", diag2)

            p = _check(results, "step2", "section_collapsed", diag2["section_class"], "collapsed", lambda v: v == "collapsed")
            total_pass += int(p); total_fail += int(not p)

            ss_path = str(SCREENSHOT_DIR / "step2_collapsed.png")
            await page.screenshot(path=ss_path, full_page=False)
            screenshots.append(ss_path)
            print(f"  Screenshot saved: {ss_path}")

            # ================================================================
            # STEP 3: Re-expand Citations (THE FIX)
            # ================================================================
            print("\n" + "=" * 60)
            print("STEP 3: Re-expand Citations (the fix should reset styles)")
            print("=" * 60)

            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(EXPAND_SETTLE_MS)

            diag3 = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 3 Diagnosis (re-expanded, FIXED)", diag3)

            # The fix: _toggleRightSection calls _updateCitationsSectionContent
            # on expand, which resets inline styles based on _wsPhase (report).
            # This is THE critical assertion proving the fix works.
            p = _check(results, "step3", "src_feed_computed_none_FIXED", diag3["src_feed_computed_display"], "none (fixed!)", lambda v: v == "none")
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step3", "cite_list_computed_visible_FIXED", diag3["cite_list_computed_display"], "NOT none (fixed!)", lambda v: v != "none")
            total_pass += int(p); total_fail += int(not p)

            # Cite cards survive collapse/re-expand (scroll_sync may limit count)
            p = _check(
                results, "step3", "cite_card_count",
                diag3["cite_card_count"],
                ">= 1 (cards survive collapse/re-expand)",
                lambda v: v >= 1,
            )
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step3", "section_expanded", diag3["section_class"], "expanded", lambda v: v == "expanded")
            total_pass += int(p); total_fail += int(not p)

            # Verify cite_list inner HTML has card content, NOT source feed text
            p = _check(
                results, "step3", "cite_list_has_cards_not_placeholder",
                "ws-cite-card" in diag3["cite_list_inner_100"],
                "True (cite-card elements present in #ws-citation-list)",
                lambda v: v is True,
            )
            total_pass += int(p); total_fail += int(not p)

            ss_path = str(SCREENSHOT_DIR / "step3_reexpanded_fixed.png")
            await page.screenshot(path=ss_path, full_page=False)
            screenshots.append(ss_path)
            print(f"  Screenshot saved: {ss_path}")

            # ================================================================
            # STEP 4: Natural flow (no manual corruption)
            # ================================================================
            print("\n" + "=" * 60)
            print("STEP 4: Natural flow -- running->report, collapse, re-expand")
            print("=" * 60)

            # Reset to running
            reset_result = await page.evaluate(JS_RESET_RUNNING)
            print(f"  Reset result: {reset_result}")
            await page.wait_for_timeout(PHASE_TRANSITION_WAIT_MS)

            # Transition to report with citations (direct render, no appendReportBlock)
            nat_result = await page.evaluate(JS_NATURAL_REPORT_TRANSITION)
            print(f"  Natural report transition result: {nat_result}")
            await page.wait_for_timeout(PHASE_TRANSITION_WAIT_MS)

            diag4a = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 4a: After natural transition", diag4a)

            # Collapse Citations
            print("  Collapsing Citations...")
            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(COLLAPSE_SETTLE_MS)

            diag4b = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 4b: After collapse", diag4b)

            p = _check(results, "step4", "collapsed_class", diag4b["section_class"], "collapsed", lambda v: v == "collapsed")
            total_pass += int(p); total_fail += int(not p)

            # Re-expand Citations
            print("  Re-expanding Citations...")
            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(EXPAND_SETTLE_MS)

            diag4c = await page.evaluate(JS_DIAGNOSE_STATE)
            _print_diagnosis("Step 4c: After re-expand", diag4c)

            p = _check(results, "step4", "src_feed_display_after_reexpand", diag4c["src_feed_computed_display"], "none", lambda v: v == "none")
            total_pass += int(p); total_fail += int(not p)

            p = _check(results, "step4", "cite_list_display_after_reexpand", diag4c["cite_list_computed_display"], "NOT none", lambda v: v != "none")
            total_pass += int(p); total_fail += int(not p)

            # Step 4 uses direct renderCitationSidebar (no scroll_sync), so all 20 cards
            p = _check(results, "step4", "cite_card_count_after_reexpand", diag4c["cite_card_count"], "20", lambda v: v == 20)
            total_pass += int(p); total_fail += int(not p)

            ss_path = str(SCREENSHOT_DIR / "step4_natural_flow.png")
            await page.screenshot(path=ss_path, full_page=False)
            screenshots.append(ss_path)
            print(f"  Screenshot saved: {ss_path}")

            # ================================================================
            # Console errors (filter out favicon 404s which are expected)
            # ================================================================
            real_errors = [e for e in console_errors if "favicon" not in e.lower() and "404" not in e]
            if real_errors:
                print(f"\n[TEST] Non-favicon console errors ({len(real_errors)}):")
                for err in real_errors[:10]:
                    print(f"  {err}")
            elif console_errors:
                print(f"\n[TEST] {len(console_errors)} console errors (all favicon 404s, expected)")

            await browser.close()

    finally:
        # Terminate server
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        log_fh.close()
        print(f"\n[TEST] Server terminated. Log at: {SERVER_LOG}")

    # ================================================================
    # Summary
    # ================================================================
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"  Total PASS: {total_pass}")
    print(f"  Total FAIL: {total_fail}")
    print(f"  Overall:    {'ALL PASS' if total_fail == 0 else 'FAILURES DETECTED'}")
    print(f"\n  Screenshots ({len(screenshots)}):")
    for ss in screenshots:
        print(f"    {ss}")

    # Write results JSON
    summary_path = str(SCREENSHOT_DIR / "test_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_pass": total_pass,
                "total_fail": total_fail,
                "overall": "PASS" if total_fail == 0 else "FAIL",
                "screenshots": screenshots,
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"  Results JSON: {summary_path}")

    return total_fail == 0


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
