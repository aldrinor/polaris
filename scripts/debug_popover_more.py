"""Test more popovers - cards 5, 7, 10 for thorough coverage."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(12000)

    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Total cards: {total}")

    for card_idx in [4, 6, 9]:
        if card_idx >= total:
            print(f"\nCard [{card_idx+1}]: SKIP (only {total} cards)")
            continue

        # Clear existing
        page.mouse.move(10, 10)
        page.wait_for_timeout(300)
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        card = cards.nth(card_idx)
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        card.hover()
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() == 0:
            print(f"\nCard [{card_idx+1}]: NO POPOVER")
            continue

        iframe = popover.locator("iframe")
        if iframe.count() == 0:
            print(f"\nCard [{card_idx+1}]: No iframe")
            continue

        srcdoc = iframe.first.get_attribute("srcdoc") or ""
        has_verified = "Verified excerpt" in srcdoc
        has_no_cache = "No cached content" in srcdoc
        has_loading = "Loading preview" in srcdoc

        if has_verified:
            status = "VERIFIED_QUOTE"
        elif has_no_cache:
            status = "NO_CACHE"
        elif has_loading:
            status = "STILL_LOADING"
        elif len(srcdoc) > 500:
            status = "READABILITY_FALLBACK"
        else:
            status = f"UNKNOWN ({len(srcdoc)} chars)"

        print(f"\nCard [{card_idx+1}]: {status} ({len(srcdoc)} chars)")

        if has_verified:
            import re
            mark = re.search(r'<mark>(.*?)</mark>', srcdoc, re.DOTALL)
            if mark:
                print(f"  Quote: {mark.group(1)[:120]}...")

        page.screenshot(path=os.path.join(OUT, f"popover_card{card_idx+1}.png"))
        print(f"  Screenshot: {OUT}/popover_card{card_idx+1}.png")

    browser.close()
    print("\nDone.")
