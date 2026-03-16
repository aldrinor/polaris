"""Deep debug: check hydration sequence and state at each stage."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    all_msgs = []
    page.on("console", lambda msg: all_msgs.append(f"[{msg.type}] {msg.text}"))

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    for wait in [3, 5, 7, 5]:
        page.wait_for_timeout(wait * 1000)
        result = page.evaluate("""() => {
            return {
                bib: state.bibliography ? state.bibliography.length : -1,
                vid: state.vectorId || 'NONE',
                complete: state.pipelineComplete,
                active: state.pipelineActive,
                report: state.fullReport ? state.fullReport.length : 0,
                endTime: state.endTime || 0,
                evidence: state.evidence || 0,
                sources: state.sources ? state.sources.size : 0
            };
        }""")
        print(f"+{wait}s: {result}")

    # Check all console messages
    print(f"\nConsole messages ({len(all_msgs)} total):")
    for m in all_msgs[:30]:
        safe = m.encode('ascii', 'replace').decode()[:200]
        print(f"  {safe}")

    # Check if there are JS errors
    errors = [m for m in all_msgs if '[error]' in m]
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            safe = e.encode('ascii', 'replace').decode()[:300]
            print(f"  {safe}")

    page.screenshot(path=os.path.join(OUT, "debug_hydration_deep.png"))
    browser.close()
