"""Check timing of snapshot load and state changes."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    for run in range(5):
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        client = ctx.new_cdp_session(page)
        client.send("Network.setCacheDisabled", {"cacheDisabled": True})

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Check at 5s, 10s, 15s, 20s
        results = []
        for wait in [5, 5, 5, 5]:
            page.wait_for_timeout(wait * 1000)
            r = page.evaluate("""() => {
                return {
                    phase: typeof _wsPhase !== 'undefined' ? _wsPhase : '?',
                    complete: state.pipelineComplete,
                    bib: state.bibliography ? state.bibliography.length : 0,
                    cards: document.querySelectorAll('.ws-cite-card').length
                };
            }""")
            results.append(r)

        line = f"Run {run+1}:"
        for i, r in enumerate(results):
            t = (i + 1) * 5
            line += f" {t}s=[{r['phase']}/{r['complete']}/{r['bib']}bib/{r['cards']}cards]"
        print(line)
        ctx.close()

    browser.close()
