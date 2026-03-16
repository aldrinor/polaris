"""Run 3 independent page loads to test consistency."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    for run in range(3):
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        # Disable cache
        client = ctx.new_cdp_session(page)
        client.send("Network.setCacheDisabled", {"cacheDisabled": True})

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000)

        result = page.evaluate("""() => {
            return {
                phase: typeof _wsPhase !== 'undefined' ? _wsPhase : '?',
                complete: state.pipelineComplete,
                cards: document.querySelectorAll('.ws-cite-card').length,
                section: (function() {
                    var sec = document.getElementById('ws-section-citations');
                    return sec ? (sec.classList.contains('expanded') ? 'expanded' : sec.classList.contains('collapsed') ? 'collapsed' : sec.className) : '?';
                })()
            };
        }""")
        print(f"Run {run+1}: phase={result['phase']} complete={result['complete']} cards={result['cards']} section={result['section']}")
        ctx.close()

    browser.close()
