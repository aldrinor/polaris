"""Check if citations are visible after hydration fix."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(15000)

    result = page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        return {
            bib: state.bibliography ? state.bibliography.length : -1,
            complete: state.pipelineComplete,
            phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown',
            cards: document.querySelectorAll('.ws-cite-card').length,
            sectionClass: sec ? sec.className : 'NOT_FOUND',
            viewMode: typeof _currentViewMode !== 'undefined' ? _currentViewMode : 'unknown',
            rightPanelDisplay: (function() {
                var rp = document.getElementById('ws-right');
                return rp ? getComputedStyle(rp).display : 'NOT_FOUND';
            })()
        };
    }""")
    print("State:", result)

    # Take screenshot of current state
    page.screenshot(path=os.path.join(OUT, "citations_after_fix.png"))
    print(f"Screenshot: {OUT}/citations_after_fix.png")

    # If citations section exists and is expanded, great. If not, try to expand.
    if result['cards'] == 0:
        # Maybe we need user mode
        page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
        page.wait_for_timeout(2000)
        after = page.evaluate("""() => {
            var sec = document.getElementById('ws-section-citations');
            return {
                cards: document.querySelectorAll('.ws-cite-card').length,
                sectionClass: sec ? sec.className : 'NOT_FOUND',
                phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown'
            };
        }""")
        print(f"After setViewMode('user'): {after}")
        page.screenshot(path=os.path.join(OUT, "citations_user_mode.png"))

    browser.close()
