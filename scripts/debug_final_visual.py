"""Final visual verification: fresh load + citations + popover."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    client = ctx.new_cdp_session(page)
    client.send("Network.setCacheDisabled", {"cacheDisabled": True})

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(15000)

    result = page.evaluate("""() => {
        return {
            phase: typeof _wsPhase !== 'undefined' ? _wsPhase : '?',
            complete: state.pipelineComplete,
            bib: state.bibliography ? state.bibliography.length : 0,
            cards: document.querySelectorAll('.ws-cite-card').length,
            section: (function() {
                var sec = document.getElementById('ws-section-citations');
                return sec ? (sec.classList.contains('expanded') ? 'expanded' : 'collapsed') : '?';
            })()
        };
    }""")
    print(f"State: {result}")

    # Screenshot 1: full page with citations expanded
    page.screenshot(path=os.path.join(OUT, "final_fresh_load.png"))
    print(f"Screenshot: {OUT}/final_fresh_load.png")

    # Test popovers on 3 cards
    cards = page.locator(".ws-cite-card")
    total = cards.count()

    for idx in [0, 4, 9]:
        if idx >= total:
            break

        # Clear popover
        page.mouse.move(10, 10)
        page.wait_for_timeout(300)
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        card = cards.nth(idx)
        card.hover(timeout=5000)
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_verified = "Verified excerpt" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                status = "VERIFIED" if has_verified else ("NO_CACHE" if has_no_cache else f"OTHER({len(srcdoc)})")
                print(f"Card [{idx+1}]: {status}")
            page.screenshot(path=os.path.join(OUT, f"final_popover_{idx+1}.png"))
        else:
            print(f"Card [{idx+1}]: NO POPOVER")

    browser.close()
    print("Done.")
