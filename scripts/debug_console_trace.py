"""Trace console messages during hydration to see post-hydration path."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    msgs = []
    page.on("console", lambda msg: msgs.append(f"[{msg.type}] {msg.text}"))

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(15000)

    # Filter for snapshot messages
    snap_msgs = [m for m in msgs if "[snapshot]" in m or "setWorkspacePhase" in m.lower() or "post-hydration" in m.lower()]
    print(f"Snapshot-related messages ({len(snap_msgs)}):")
    for m in snap_msgs:
        safe = m.encode("ascii", "replace").decode()[:300]
        print(f"  {safe}")

    # Check state
    result = page.evaluate("""() => {
        return {
            phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown',
            complete: state.pipelineComplete,
            cards: document.querySelectorAll('.ws-cite-card').length,
            sectionClass: (function() {
                var sec = document.getElementById('ws-section-citations');
                return sec ? sec.className : 'NOT_FOUND';
            })()
        };
    }""")
    print(f"\nState: {result}")

    # Show all console messages
    print(f"\nAll messages ({len(msgs)}):")
    for m in msgs[:50]:
        safe = m.encode("ascii", "replace").decode()[:200]
        print(f"  {safe}")

    browser.close()
