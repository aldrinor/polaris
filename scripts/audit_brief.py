"""Playwright audit: diagnose why source brief doesn't generate in the browser."""

import sys
import time
from playwright.sync_api import sync_playwright

URL = "https://identifier-strain-farmer-likelihood.trycloudflare.com"
TIMEOUT = 60_000  # 60s page load timeout


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # Collect ALL console messages
        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(
            f"[{msg.type}] {msg.text}"
        ))

        # Collect JS errors
        js_errors = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        # Collect network requests/responses for /api/ endpoints
        api_requests = []
        def on_request(req):
            if "/api/" in req.url:
                api_requests.append({
                    "method": req.method,
                    "url": req.url,
                    "status": None,
                })
        def on_response(resp):
            if "/api/" in resp.url:
                for r in api_requests:
                    if r["url"] == resp.url and r["status"] is None:
                        r["status"] = resp.status
                        break

        page.on("request", on_request)
        page.on("response", on_response)

        # ---- Step 1: Load page ----
        print(f"[1] Loading {URL} ...")
        try:
            page.goto(URL, timeout=TIMEOUT, wait_until="networkidle")
        except Exception as e:
            print(f"    WARN: page.goto raised: {e}")

        print(f"    Page title: {page.title()}")
        print(f"    URL: {page.url}")

        # ---- Step 2: Check workspace phase ----
        ws_phase = page.evaluate("typeof _wsPhase !== 'undefined' ? _wsPhase : 'UNDEFINED'")
        print(f"\n[2] _wsPhase = {ws_phase}")

        # ---- Step 3: Check doc panel state ----
        doc_count = page.evaluate(
            "typeof _docPanelDocs !== 'undefined' ? _docPanelDocs.length : -1"
        )
        print(f"[3] _docPanelDocs.length = {doc_count}")

        if doc_count > 0:
            doc_ids = page.evaluate(
                "_docPanelDocs.map(function(d){ return d.doc_id || d.id || '?' })"
            )
            print(f"    doc_ids: {doc_ids}")

        # ---- Step 4: Check brief state ----
        brief_pending = page.evaluate(
            "typeof _briefPending !== 'undefined' ? _briefPending : 'UNDEFINED'"
        )
        brief_cache_keys = page.evaluate(
            "typeof _briefCache !== 'undefined' ? Object.keys(_briefCache).length : -1"
        )
        print(f"[4] _briefPending = {brief_pending}")
        print(f"    _briefCache keys = {brief_cache_keys}")

        # ---- Step 5: Check DOM element visibility ----
        elements_to_check = [
            "ws-idle",
            "ws-idle-brief",
            "ws-idle-brief-loading",
            "ws-idle-brief-content",
            "ws-idle-brief-summary",
            "ws-idle-greeting",
            "ws-idle-chips",
            "ws-thread",
        ]
        print(f"\n[5] DOM element visibility:")
        for eid in elements_to_check:
            info = page.evaluate(f"""(function() {{
                var el = document.getElementById('{eid}');
                if (!el) return 'NOT FOUND';
                var s = window.getComputedStyle(el);
                return 'display=' + s.display + ' visibility=' + s.visibility
                    + ' offsetH=' + el.offsetHeight + ' parent_display='
                    + (el.parentElement ? window.getComputedStyle(el.parentElement).display : 'N/A');
            }})()""")
            print(f"    #{eid}: {info}")

        # ---- Step 6: Check _wsThread ----
        thread_len = page.evaluate(
            "typeof _wsThread !== 'undefined' ? _wsThread.length : -1"
        )
        print(f"\n[6] _wsThread.length = {thread_len}")

        # ---- Step 7: Manually trigger generateSourceBrief and observe ----
        print(f"\n[7] Manually calling generateSourceBrief() ...")
        page.evaluate("if (typeof generateSourceBrief === 'function') generateSourceBrief()")

        # Wait a moment for async effects
        time.sleep(3)

        # Check brief pending after manual trigger
        brief_pending_2 = page.evaluate(
            "typeof _briefPending !== 'undefined' ? _briefPending : 'UNDEFINED'"
        )
        print(f"    _briefPending after trigger = {brief_pending_2}")

        # ---- Step 8: Wait for brief to potentially complete ----
        print(f"\n[8] Waiting up to 30s for brief to complete ...")
        for i in range(30):
            time.sleep(1)
            bp = page.evaluate("_briefPending")
            bc = page.evaluate("Object.keys(_briefCache).length")
            summary_text = page.evaluate("""
                (function() {
                    var el = document.getElementById('ws-idle-brief-summary');
                    return el ? el.textContent.substring(0, 100) : 'NOT FOUND';
                })()
            """)
            if not bp and bc > 0:
                print(f"    Brief completed at {i+1}s!")
                print(f"    Summary: {summary_text}")
                break
            if i % 5 == 4:
                print(f"    {i+1}s: pending={bp}, cache_keys={bc}")
        else:
            print(f"    Timed out. pending={bp}, cache_keys={bc}")

        # ---- Step 9: Console messages ----
        print(f"\n[9] Console messages ({len(console_msgs)} total):")
        for msg in console_msgs:
            # Show all brief-related and error messages
            if "[brief]" in msg or "error" in msg.lower() or "warn" in msg.lower():
                print(f"    {msg}")

        # Show ALL console messages if few
        if len(console_msgs) <= 30:
            print(f"\n    --- All console messages ---")
            for msg in console_msgs:
                print(f"    {msg}")

        # ---- Step 10: JS errors ----
        print(f"\n[10] JS errors ({len(js_errors)}):")
        for err in js_errors:
            print(f"    {err}")

        # ---- Step 11: API requests ----
        print(f"\n[11] API requests ({len(api_requests)}):")
        for r in api_requests:
            print(f"    {r['method']} {r['url']} -> {r['status']}")

        # ---- Step 12: Screenshot ----
        screenshot_path = "logs/brief_audit_screenshot.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n[12] Screenshot saved: {screenshot_path}")

        browser.close()


if __name__ == "__main__":
    main()
