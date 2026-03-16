"""
Playwright UI audit — checks the live dashboard state without any API calls.
Takes a screenshot and evaluates UI state via injected JS.
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
SCREENSHOT_DIR = Path("outputs/ui_audit")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

UI_CHECK_JS = Path("scripts/ui_check.js").read_text(encoding="utf-8")

def run_audit():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        js_errors = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

        print(f"Navigating to {URL} ...")
        page.goto(URL, wait_until="domcontentloaded", timeout=15000)
        # Wait for SSE connection and hydration
        page.wait_for_timeout(4000)

        # Take screenshot
        ss_path = SCREENSHOT_DIR / "ui_audit.png"
        page.screenshot(path=str(ss_path), full_page=True)
        print(f"Screenshot saved: {ss_path}")

        # Evaluate UI state
        ui_state = page.evaluate(UI_CHECK_JS)
        print("\n=== UI STATE ===")
        for k, v in ui_state.items():
            print(f"  {k}: {v}")

        # Check for JS errors
        if js_errors:
            print(f"\n=== JS ERRORS ({len(js_errors)}) ===")
            for e in js_errors[:10]:
                print(f"  {e[:200]}")
        else:
            print("\n  0 JS errors")

        # Check key console messages
        sse_msgs = [m for m in console_msgs if "SSE" in m or "hydrat" in m.lower() or "pipeline" in m.lower() or "phase" in m.lower()]
        if sse_msgs:
            print(f"\n=== KEY CONSOLE MSGS ({len(sse_msgs)}) ===")
            for m in sse_msgs[:15]:
                print(f"  {m[:200]}")

        # Detect visible panels
        panels = page.evaluate("""() => {
            var r = {};
            var ws = document.getElementById('workspace-panel');
            r.workspaceVisible = ws ? (ws.offsetWidth > 0 && ws.offsetHeight > 0) : false;

            var landing = document.getElementById('landing-section');
            r.landingVisible = landing ? (landing.offsetWidth > 0 && landing.offsetHeight > 0) : false;

            var idle = document.getElementById('ws-idle-brief');
            r.idleBriefVisible = idle ? (idle.offsetWidth > 0 && idle.offsetHeight > 0) : false;

            var thread = document.getElementById('ws-thread');
            r.threadVisible = thread ? (thread.offsetWidth > 0 && thread.offsetHeight > 0) : false;

            var progress = document.getElementById('ws-active-progress');
            r.progressBlockVisible = progress ? (progress.offsetWidth > 0 && progress.offsetHeight > 0) : false;

            var report = document.getElementById('ws-report');
            r.reportVisible = report ? (report.offsetWidth > 0 && report.offsetHeight > 0) : false;

            var nav = document.getElementById('operator-nav');
            r.operatorNavVisible = nav ? (nav.offsetWidth > 0 && nav.offsetHeight > 0) : false;

            // Check what's showing in the source brief area
            var briefContent = document.getElementById('ws-idle-brief-content');
            r.briefHasContent = briefContent ? (briefContent.textContent.trim().length > 0) : false;

            // Check sidebar sections
            var sidebar = document.getElementById('ws-sidebar');
            r.sidebarVisible = sidebar ? (sidebar.offsetWidth > 0) : false;

            return r;
        }""")
        print("\n=== PANEL VISIBILITY ===")
        for k, v in panels.items():
            print(f"  {k}: {v}")

        # Overall assessment
        print("\n=== ASSESSMENT ===")
        if ui_state.get("pipelineActive"):
            if ui_state.get("wsPhase") == "running":
                print("  OK: Pipeline active, workspace in RUNNING phase")
                if ui_state.get("progressBlock"):
                    print("  OK: Progress block present")
                else:
                    print("  BUG: Progress block MISSING during active pipeline")
                if ui_state.get("metricsRow"):
                    print("  OK: Metrics row present (F07)")
                else:
                    print("  BUG: Metrics row MISSING (F07)")
            else:
                print(f"  BUG: Pipeline active but wsPhase={ui_state.get('wsPhase')} (should be 'running')")
        elif ui_state.get("pipelineComplete"):
            if ui_state.get("wsPhase") == "report":
                print("  OK: Pipeline complete, workspace in REPORT phase")
            else:
                print(f"  INFO: Pipeline complete, wsPhase={ui_state.get('wsPhase')}")
        else:
            print(f"  INFO: No pipeline active. wsPhase={ui_state.get('wsPhase')}, viewMode={ui_state.get('viewMode')}")

        if ui_state.get("hasSearchedZero"):
            print("  BUG: 'Searched 0 sources' still present (F01)")
        else:
            print("  OK: No 'Searched 0 sources' spam (F01)")

        browser.close()
        return ui_state, panels, js_errors

if __name__ == "__main__":
    run_audit()
