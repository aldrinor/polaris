"""
Playwright visual audit: citation collapse/re-expand with a LONG scrollable report.

Previous tests used short reports that fit in the viewport. scroll_sync's
IntersectionObserver never fired because all headings were visible at once.
This test injects a 69-citation, 8-section report spanning many viewports so
that scroll_sync actively swaps citation cards as the user scrolls -- exposing
the real bug path.

Usage:
    python scripts/playwright_cite_collapse_long.py

Outputs screenshots to outputs/cite_collapse_long/
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
SCREENSHOT_DIR = PROJECT_ROOT / "outputs" / "cite_collapse_long"
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "live_server.py"
SERVER_LOG = PROJECT_ROOT / "logs" / "cite_collapse_long_server.log"

PAGE_LOAD_WAIT_MS = 3000
JS_INIT_WAIT_MS = 1500
SCROLL_SETTLE_MS = 800
COLLAPSE_SETTLE_MS = 300
EXPAND_SETTLE_MS = 800
ACCORDION_SETTLE_MS = 300


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
# JavaScript: inject a LONG multi-section report with 20 bibliography entries
# ---------------------------------------------------------------------------

JS_INJECT_LONG_REPORT = """
() => {
    // 1. Build bibliography with 20 entries
    state.bibliography = [];
    for (var i = 1; i <= 20; i++) {
        state.bibliography.push({
            url: "https://source" + i + ".example.com/article",
            title: "Research Source " + i + " — Long Title About Water Treatment Technology and Filtration Methods",
            domain: "source" + i + ".example.com",
            is_faithful: i <= 16,
            snippet: "This is the snippet for source " + i + " discussing findings about water treatment."
        });
    }

    // 2. Switch to report phase
    setWorkspacePhase("report");

    // 3. Build a LONG report with 8 sections, each with different citations
    //    and lots of filler text to force scrolling past viewport
    var sections = [];
    for (var s = 1; s <= 8; s++) {
        var sec = "## Section " + s + ": Research Area " + s + "\\n\\n";
        // 6 paragraphs per section to make it long enough to scroll
        for (var p = 0; p < 6; p++) {
            sec += "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " +
                "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " +
                "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. " +
                "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum. ";
            // Sprinkle citations from this section's range
            var citeA = ((s - 1) * 2 + 1);
            var citeB = ((s - 1) * 2 + 2);
            if (citeB > 20) citeB = 20;
            sec += "[" + citeA + "] and [" + citeB + "]. ";
            sec += "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum. ";
        }
        sec += "\\n\\n";
        sections.push(sec);
    }

    var fullReport = sections.join("");
    appendReportBlock(fullReport, state.bibliography);
    _updateCitationsCount();

    return {
        bib_length: state.bibliography.length,
        report_length: fullReport.length,
        sections_count: sections.length
    };
}
"""

# ---------------------------------------------------------------------------
# JavaScript: comprehensive DOM inspection at each step
# ---------------------------------------------------------------------------

JS_INSPECT_DOM = """
() => {
    var cards = document.querySelectorAll('.ws-cite-card');
    var citeNums = [];
    cards.forEach(function(c) {
        var n = c.getAttribute('data-cite-num');
        if (n) citeNums.push(parseInt(n));
    });

    var citeList = document.getElementById('ws-citation-list');
    var citeSec = document.getElementById('ws-section-citations');
    var sectionBody = citeSec ? citeSec.querySelector('.ws-section-body') : null;
    var badge = document.getElementById('ws-citations-count');

    // Compute section classes
    var sectionClasses = '';
    if (citeSec) {
        sectionClasses = citeSec.className;
    }

    // Computed styles
    var citeListDisplay = 'N/A';
    var sectionBodyDisplay = 'N/A';
    if (citeList) {
        citeListDisplay = window.getComputedStyle(citeList).display;
    }
    if (sectionBody) {
        sectionBodyDisplay = window.getComputedStyle(sectionBody).display;
    }

    return {
        card_count: cards.length,
        cite_nums: citeNums,
        inner_html_length: citeList ? citeList.innerHTML.length : -1,
        inner_html_first200: citeList ? citeList.innerHTML.substring(0, 200) : 'NOT_FOUND',
        badge_text: badge ? badge.textContent.trim() : 'NOT_FOUND',
        section_classes: sectionClasses,
        cite_list_display: citeListDisplay,
        section_body_display: sectionBodyDisplay,
        phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown',
        observer_exists: typeof _scrollSyncObserver !== 'undefined' && _scrollSyncObserver !== null,
        active_heading_id: typeof _scrollSyncActiveHeadingId !== 'undefined' ? _scrollSyncActiveHeadingId : null
    };
}
"""


def _print_dom_state(label: str, data: dict) -> None:
    """Pretty-print DOM inspection data."""
    print(f"\n  --- DOM State: {label} ---")
    print(f"  card_count:          {data['card_count']}")
    print(f"  cite_nums:           {data['cite_nums']}")
    print(f"  innerHTML length:    {data['inner_html_length']}")
    print(f"  innerHTML[0:200]:    {data['inner_html_first200'][:200]}")
    print(f"  badge_text:          {data['badge_text']}")
    print(f"  section_classes:     {data['section_classes']}")
    print(f"  cite_list_display:   {data['cite_list_display']}")
    print(f"  section_body_display:{data['section_body_display']}")
    print(f"  phase:               {data['phase']}")
    print(f"  observer_exists:     {data['observer_exists']}")
    print(f"  active_heading_id:   {data['active_heading_id']}")
    print(f"  ---")


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

            # Collect console messages for debugging
            console_errors = []
            page.on(
                "console",
                lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
                if msg.type in ("error", "warning")
                else None,
            )

            # Navigate with domcontentloaded (NOT networkidle -- SSE keeps conn open)
            print(f"[AUDIT] Navigating to {url} ...")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait for JS init
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
            print("[AUDIT] Page loaded. Injecting LONG report state...")

            # Inject state with LONG report
            inject_result = await page.evaluate(JS_INJECT_LONG_REPORT)
            print(f"[AUDIT] Injection result: {inject_result}")

            # Wait for scroll_sync to initialize (appendReportBlock has 100ms setTimeout)
            await page.wait_for_timeout(JS_INIT_WAIT_MS)

            # ==================================================================
            # Results tracking
            # ==================================================================
            all_steps = {}
            pass_count = 0
            fail_count = 0

            def check(step_name: str, key: str, value, expected_desc: str,
                       ok: bool) -> None:
                nonlocal pass_count, fail_count
                status = "PASS" if ok else "FAIL"
                if ok:
                    pass_count += 1
                else:
                    fail_count += 1
                all_steps.setdefault(step_name, [])
                all_steps[step_name].append({
                    "key": key, "value": value,
                    "expected": expected_desc, "status": status,
                })
                print(f"  [{status}] {step_name}.{key} = {value}  (expected: {expected_desc})")

            # ==================================================================
            # Step 0: Initial state -- report at top, section 1 citations show
            # ==================================================================
            print("\n" + "=" * 70)
            print("STEP 0: Initial state")
            print("=" * 70)

            dom0 = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step0", dom0)

            check("step0", "card_count", dom0["card_count"], "> 0",
                  dom0["card_count"] > 0)
            check("step0", "badge_text", dom0["badge_text"], "20",
                  dom0["badge_text"] == "20")
            check("step0", "section_expanded", "expanded" in dom0["section_classes"],
                  "True (expanded)", "expanded" in dom0["section_classes"])
            check("step0", "phase", dom0["phase"], "report",
                  dom0["phase"] == "report")
            check("step0", "observer_exists", dom0["observer_exists"], "True",
                  dom0["observer_exists"] is True)

            # Save step0 card data for later comparison
            step0_cite_nums = dom0["cite_nums"]
            step0_card_count = dom0["card_count"]

            screenshot_path = str(SCREENSHOT_DIR / "step0_initial.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot saved: {screenshot_path}")

            # ==================================================================
            # Step 1: Scroll to middle of report (section 4-5 area)
            #   scroll_sync should fire and change citation sidebar to different nums
            # ==================================================================
            print("\n" + "=" * 70)
            print("STEP 1: Scroll to middle of report (section 4)")
            print("=" * 70)

            await page.evaluate("""
                () => {
                    var thread = document.getElementById('ws-thread');
                    thread.scrollTop = Math.floor(thread.scrollHeight / 2);
                }
            """)
            await page.wait_for_timeout(SCROLL_SETTLE_MS)

            dom1 = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step1", dom1)

            check("step1", "card_count", dom1["card_count"], "> 0",
                  dom1["card_count"] > 0)
            # The cite_nums should be DIFFERENT from step0 (scroll_sync is active)
            nums_changed = set(dom1["cite_nums"]) != set(step0_cite_nums)
            check("step1", "cite_nums_changed", nums_changed,
                  "True (different from step0, proving scroll_sync active)",
                  nums_changed)
            check("step1", "active_heading_changed",
                  dom1["active_heading_id"] is not None
                  and dom1["active_heading_id"] != dom0.get("active_heading_id"),
                  "True (heading tracker changed)",
                  dom1["active_heading_id"] is not None
                  and dom1["active_heading_id"] != dom0.get("active_heading_id"))

            step1_cite_nums = dom1["cite_nums"]
            step1_card_count = dom1["card_count"]
            step1_html_len = dom1["inner_html_length"]

            screenshot_path = str(SCREENSHOT_DIR / "step1_scrolled_to_middle.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot saved: {screenshot_path}")

            # ==================================================================
            # Step 2: Collapse Citations
            # ==================================================================
            print("\n" + "=" * 70)
            print("STEP 2: Collapse Citations")
            print("=" * 70)

            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(COLLAPSE_SETTLE_MS)

            dom2 = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step2", dom2)

            check("step2", "section_collapsed", "collapsed" in dom2["section_classes"],
                  "True (collapsed)", "collapsed" in dom2["section_classes"])
            # Cards should still be in DOM (just hidden by CSS)
            check("step2", "card_count_in_dom", dom2["card_count"],
                  f"== {step1_card_count} (cards preserved in DOM)",
                  dom2["card_count"] == step1_card_count)
            check("step2", "html_preserved", dom2["inner_html_length"],
                  f"== {step1_html_len} (innerHTML unchanged)",
                  dom2["inner_html_length"] == step1_html_len)

            step2_html_len = dom2["inner_html_length"]
            step2_card_count = dom2["card_count"]

            screenshot_path = str(SCREENSHOT_DIR / "step2_collapsed.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot saved: {screenshot_path}")

            # ==================================================================
            # Step 3: Scroll report while Citations is collapsed
            #   Guard in renderCitationSidebar should prevent any changes
            # ==================================================================
            print("\n" + "=" * 70)
            print("STEP 3: Scroll report while Citations is collapsed")
            print("=" * 70)

            # Scroll to top
            await page.evaluate(
                "() => { document.getElementById('ws-thread').scrollTop = 0; }"
            )
            await page.wait_for_timeout(SCROLL_SETTLE_MS)

            dom3a = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step3a (scrolled to top while collapsed)", dom3a)

            check("step3a", "card_count_unchanged", dom3a["card_count"],
                  f"== {step2_card_count} (guard prevents overwrite)",
                  dom3a["card_count"] == step2_card_count)
            check("step3a", "html_unchanged", dom3a["inner_html_length"],
                  f"== {step2_html_len} (guard prevents overwrite)",
                  dom3a["inner_html_length"] == step2_html_len)

            # Scroll to bottom
            await page.evaluate(
                "() => { document.getElementById('ws-thread').scrollTop = 999999; }"
            )
            await page.wait_for_timeout(SCROLL_SETTLE_MS)

            dom3b = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step3b (scrolled to bottom while collapsed)", dom3b)

            check("step3b", "card_count_unchanged", dom3b["card_count"],
                  f"== {step2_card_count} (guard prevents overwrite)",
                  dom3b["card_count"] == step2_card_count)
            check("step3b", "html_unchanged", dom3b["inner_html_length"],
                  f"== {step2_html_len} (guard prevents overwrite)",
                  dom3b["inner_html_length"] == step2_html_len)

            screenshot_path = str(SCREENSHOT_DIR / "step3_scrolled_while_collapsed.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot saved: {screenshot_path}")

            # ==================================================================
            # Step 4: Re-expand Citations -- THE CRITICAL CHECK
            # ==================================================================
            print("\n" + "=" * 70)
            print("STEP 4: Re-expand Citations (CRITICAL)")
            print("=" * 70)

            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(EXPAND_SETTLE_MS)

            dom4 = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step4", dom4)

            check("step4", "section_expanded", "expanded" in dom4["section_classes"],
                  "True (expanded)", "expanded" in dom4["section_classes"])
            check("step4", "card_count_gt_0", dom4["card_count"],
                  "> 0 (CRITICAL: cards must be visible after re-expand)",
                  dom4["card_count"] > 0)
            check("step4", "html_length_gt_0", dom4["inner_html_length"],
                  "> 0", dom4["inner_html_length"] > 0)
            check("step4", "cite_list_display", dom4["cite_list_display"],
                  "not 'none'", dom4["cite_list_display"] != "none")

            # If re-expand yielded 0 cards, dump full innerHTML for debugging
            if dom4["card_count"] == 0:
                print("\n  [BUG DETECTED] Re-expand yielded 0 cards!")
                full_html = await page.evaluate("""
                    () => {
                        var el = document.getElementById('ws-citation-list');
                        return el ? el.innerHTML : 'NOT_FOUND';
                    }
                """)
                print(f"  [DEBUG] Full innerHTML of #ws-citation-list:\n{full_html}")

                observer_state = await page.evaluate("""
                    () => {
                        return {
                            observer_exists: typeof _scrollSyncObserver !== 'undefined' && _scrollSyncObserver !== null,
                            active_heading_id: typeof _scrollSyncActiveHeadingId !== 'undefined' ? _scrollSyncActiveHeadingId : null,
                            current_report_el: typeof _wsCurrentReportEl !== 'undefined' && _wsCurrentReportEl !== null,
                            phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown',
                            bib_length: state.bibliography ? state.bibliography.length : 0,
                            thread_scroll_top: document.getElementById('ws-thread') ? document.getElementById('ws-thread').scrollTop : -1,
                            thread_scroll_height: document.getElementById('ws-thread') ? document.getElementById('ws-thread').scrollHeight : -1
                        };
                    }
                """)
                print(f"  [DEBUG] Observer state: {json.dumps(observer_state, indent=2)}")

            screenshot_path = str(SCREENSHOT_DIR / "step4_reexpanded.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot saved: {screenshot_path}")

            # ==================================================================
            # Step 5: Accordion cycle (Live then back to Citations)
            # ==================================================================
            print("\n" + "=" * 70)
            print("STEP 5: Accordion cycle (Live -> Citations)")
            print("=" * 70)

            # Click Live section to expand it (accordion collapses Citations)
            await page.click("#ws-section-live .ws-section-header")
            await page.wait_for_timeout(ACCORDION_SETTLE_MS)

            dom5a = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step5a (Live expanded)", dom5a)

            check("step5a", "citations_collapsed", "collapsed" in dom5a["section_classes"],
                  "True (accordion collapsed citations)",
                  "collapsed" in dom5a["section_classes"])

            # Click Citations to expand it back
            await page.click("#ws-section-citations .ws-section-header")
            await page.wait_for_timeout(EXPAND_SETTLE_MS)

            dom5 = await page.evaluate(JS_INSPECT_DOM)
            _print_dom_state("step5", dom5)

            check("step5", "section_expanded", "expanded" in dom5["section_classes"],
                  "True (expanded)", "expanded" in dom5["section_classes"])
            check("step5", "card_count_gt_0", dom5["card_count"],
                  "> 0 (cards must show after accordion cycle)",
                  dom5["card_count"] > 0)
            check("step5", "html_length_gt_0", dom5["inner_html_length"],
                  "> 0", dom5["inner_html_length"] > 0)

            # If accordion yielded 0 cards, dump full innerHTML
            if dom5["card_count"] == 0:
                print("\n  [BUG DETECTED] Accordion cycle yielded 0 cards!")
                full_html = await page.evaluate("""
                    () => {
                        var el = document.getElementById('ws-citation-list');
                        return el ? el.innerHTML : 'NOT_FOUND';
                    }
                """)
                print(f"  [DEBUG] Full innerHTML of #ws-citation-list:\n{full_html}")

            screenshot_path = str(SCREENSHOT_DIR / "step5_after_accordion.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"  Screenshot saved: {screenshot_path}")

            # ==================================================================
            # Summary
            # ==================================================================
            print("\n" + "=" * 80)
            print("LONG REPORT CITATION COLLAPSE/RE-EXPAND AUDIT RESULTS")
            print("=" * 80)

            # Summary table of card counts at each step
            print("\n{:<55} {:>8} {:>10} {:>12}".format(
                "Step", "Cards", "HTML Len", "Cite Nums"))
            print("-" * 85)
            for label, dom_data in [
                ("Step 0: Initial (top of report)", dom0),
                ("Step 1: Scrolled to middle (scroll_sync active)", dom1),
                ("Step 2: After collapse", dom2),
                ("Step 3a: Scroll top while collapsed", dom3a),
                ("Step 3b: Scroll bottom while collapsed", dom3b),
                ("Step 4: Re-expanded (CRITICAL)", dom4),
                ("Step 5: After accordion cycle", dom5),
            ]:
                nums_str = str(dom_data["cite_nums"][:6])
                if len(dom_data["cite_nums"]) > 6:
                    nums_str = nums_str[:-1] + ", ...]"
                print("{:<55} {:>8} {:>10} {:>12}".format(
                    label, dom_data["card_count"],
                    dom_data["inner_html_length"], nums_str))

            # Individual check results
            print("\n{:<50} {:>8}".format("Check", "Result"))
            print("-" * 58)
            for step_name, checks in all_steps.items():
                for c in checks:
                    print("{:<50} {:>8}".format(
                        f"{step_name}.{c['key']}", c["status"]))

            # Overall verdict
            total = pass_count + fail_count
            print(f"\n{'=' * 58}")
            print(f"TOTAL: {pass_count}/{total} PASS, {fail_count}/{total} FAIL")
            if fail_count == 0:
                print("VERDICT: ALL PASS")
            else:
                print("VERDICT: FAILURES DETECTED")
            print(f"{'=' * 58}")

            # Print any console errors
            if console_errors:
                print(f"\n[AUDIT] Console errors/warnings ({len(console_errors)}):")
                for err in console_errors[:20]:
                    print(f"  {err}")

            # Screenshots listing
            print(f"\n[AUDIT] Screenshots saved to: {SCREENSHOT_DIR}")
            for f in sorted(SCREENSHOT_DIR.glob("*.png")):
                print(f"  {f.name}")

            await browser.close()

    finally:
        # Terminate server
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        log_fh.close()
        print(f"[AUDIT] Server terminated. Log: {SERVER_LOG}")


if __name__ == "__main__":
    asyncio.run(run_audit())
