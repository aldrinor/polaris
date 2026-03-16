"""Test popovers by hovering multiple citation cards."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)

    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(1000)

    # Expand citations
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Total citation cards: {total}")

    for idx in [0, 2, 4]:
        if idx >= total:
            break

        # Move mouse away first to close any existing popover
        page.mouse.move(400, 400)
        page.wait_for_timeout(500)

        # Hover the card
        cards.nth(idx).hover()
        page.wait_for_timeout(3000)  # Wait for popover + API fetch

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_no_cache = "No cached content" in srcdoc
                has_loading = "Loading preview" in srcdoc
                is_real = len(srcdoc) > 500 and not has_no_cache and not has_loading
                status = "REAL_CONTENT" if is_real else ("NO_CACHE" if has_no_cache else "LOADING")
                print(f"  Card [{idx+1}]: {status} ({len(srcdoc)} chars)")
            # Screenshot
            page.screenshot(path=os.path.join(OUT, f"audit_popover_card{idx+1}.png"))
        else:
            print(f"  Card [{idx+1}]: NO POPOVER")

    browser.close()
    print("Done.")
