"""Full visual verification: fresh page load + citations + popover."""
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

    # Check state
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

    # Screenshot 1: Full page after fresh load
    page.screenshot(path=os.path.join(OUT, "fresh_load_full.png"))
    print(f"Screenshot: {OUT}/fresh_load_full.png")

    # Now test popover on first card
    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"\nCards visible: {total}")

    if total > 0:
        # Hover first card
        cards.first.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        cards.first.hover()
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_verified = "Verified excerpt" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                print(f"Popover card 1: verified={has_verified} no_cache={has_no_cache} len={len(srcdoc)}")

            page.screenshot(path=os.path.join(OUT, "fresh_popover_card1.png"))
            print(f"Screenshot: {OUT}/fresh_popover_card1.png")
        else:
            print("No popover appeared")
            page.screenshot(path=os.path.join(OUT, "fresh_no_popover.png"))

    browser.close()
    print("\nDone.")
