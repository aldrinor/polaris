"""Full visual verification with cache bypass."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # Disable browser cache
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()

    # Bypass cache via CDP
    client = page.context.new_cdp_session(page)
    client.send("Network.setCacheDisabled", {"cacheDisabled": True})

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(15000)

    result = page.evaluate("""() => {
        return {
            phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown',
            complete: state.pipelineComplete,
            bib: state.bibliography ? state.bibliography.length : 0,
            cards: document.querySelectorAll('.ws-cite-card').length,
            sectionState: (function() {
                var sec = document.getElementById('ws-section-citations');
                return sec ? (sec.classList.contains('expanded') ? 'expanded' : 'collapsed') : 'NOT_FOUND';
            })()
        };
    }""")
    print(f"State: phase={result['phase']} complete={result['complete']} bib={result['bib']} cards={result['cards']} section={result['sectionState']}")

    # Screenshot: full page
    page.screenshot(path=os.path.join(OUT, "fresh_full.png"))
    print(f"Screenshot: {OUT}/fresh_full.png")

    if result["cards"] > 0 and result["sectionState"] == "expanded":
        # Test popover
        cards = page.locator(".ws-cite-card")
        cards.first.hover()
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_verified = "Verified excerpt" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                print(f"Popover: verified={has_verified} no_cache={has_no_cache} len={len(srcdoc)}")
            page.screenshot(path=os.path.join(OUT, "fresh_popover.png"))
            print(f"Screenshot: {OUT}/fresh_popover.png")
        else:
            print("No popover appeared after hover")
    elif result["cards"] == 0:
        print("NO CARDS - checking DOM...")
        dom_check = page.evaluate("""() => {
            var list = document.getElementById('ws-citations-list');
            return {
                listExists: !!list,
                listHTML: list ? list.innerHTML.substring(0, 300) : 'NOT_FOUND',
                rightPanel: document.getElementById('ws-right') ? 'exists' : 'NOT_FOUND'
            };
        }""")
        print(f"  {dom_check}")

    browser.close()
    print("Done.")
