"""Monitor POLARIS frontend via Playwright — screenshots every 45s through tunnel."""
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("C:/POLARIS/outputs/monitor_screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Use tunnel URL if provided, otherwise localhost
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
INTERVAL = 45


LOCAL_URL = "http://localhost:8765"


def fetch_status():
    try:
        with urllib.request.urlopen(LOCAL_URL + "/api/research/status", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {"running": False, "error": "unreachable"}


def main():
    print("=" * 70)
    print("  POLARIS Frontend Monitor — Playwright screenshots every %ds" % INTERVAL)
    print("  URL: %s" % BASE_URL)
    print("  Screenshots: %s" % SCREENSHOTS_DIR)
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Collect JS errors
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))

        # Initial load
        print("[INIT] Loading dashboard...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)  # Let hydration + SSE connect

        shot_num = 0
        while True:
            now = datetime.now().strftime("%H%M%S")
            status = fetch_status()
            running = status.get("running", False)

            # Grab frontend state
            try:
                fe_state = page.evaluate("""() => {
                    if (typeof state === 'undefined') return {error: 'no state'};
                    return {
                        connected: state.connected,
                        eventCount: state.eventCount,
                        evidence: state.evidence,
                        sources: state.sources ? state.sources.size : 0,
                        faithfulness: state.faithfulness,
                        words: state.words,
                        citations: state.citations,
                        cost: state.cost,
                        iteration: state.iteration,
                        pipelineActive: state.pipelineActive,
                        pipelineComplete: state.pipelineComplete,
                        currentNode: state.currentNode,
                        bibliography: state.bibliography ? state.bibliography.length : 0,
                    };
                }""")
            except Exception as e:
                fe_state = {"error": str(e)[:100]}

            # Screenshot
            shot_name = "monitor_%03d_%s.png" % (shot_num, now)
            shot_path = SCREENSHOTS_DIR / shot_name
            page.screenshot(path=str(shot_path), full_page=False)

            # Report
            be_running = "RUN" if running else "DONE"
            fe_conn = fe_state.get("connected", "?")
            fe_ev = fe_state.get("eventCount", "?")
            fe_evidence = fe_state.get("evidence", "?")
            fe_sources = fe_state.get("sources", "?")
            fe_faith = fe_state.get("faithfulness", "?")
            fe_words = fe_state.get("words", "?")
            fe_cite = fe_state.get("citations", "?")
            fe_active = fe_state.get("pipelineActive", "?")
            fe_complete = fe_state.get("pipelineComplete", "?")
            fe_node = fe_state.get("currentNode", "?")

            new_errors = len(js_errors)

            print(
                "[%s] #%d | BE=%s | FE: conn=%s active=%s node=%s | "
                "events=%s ev=%s src=%s faith=%s words=%s cite=%s | "
                "js_errors=%d | %s"
                % (
                    now, shot_num, be_running, fe_conn, fe_active, fe_node,
                    fe_ev, fe_evidence, fe_sources, fe_faith, fe_words, fe_cite,
                    new_errors, shot_name,
                )
            )

            if new_errors > 0:
                for err in js_errors[-3:]:
                    print("  JS ERROR: %s" % err[:200])

            shot_num += 1

            # Check if done
            if not running:
                # Take final screenshot
                page.wait_for_timeout(3000)
                final_name = "monitor_FINAL_%s.png" % now
                page.screenshot(path=str(SCREENSHOTS_DIR / final_name), full_page=False)
                print("\n  PIPELINE FINISHED — final screenshot: %s" % final_name)

                # Check frontend state matches
                if fe_state.get("pipelineComplete"):
                    print("  Frontend: pipelineComplete=True (GOOD)")
                elif fe_state.get("pipelineActive"):
                    print("  WARNING: Frontend still shows pipelineActive=True (stale)")
                break

            time.sleep(INTERVAL)

        browser.close()

    print("=" * 70)
    print("  Frontend monitor stopped. %d screenshots saved." % (shot_num + 1))
    print("=" * 70)


if __name__ == "__main__":
    main()
