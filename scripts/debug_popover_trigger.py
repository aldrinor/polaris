"""Debug popover trigger mechanism."""
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

    # Inspect available functions and card structure
    debug = page.evaluate("""() => {
        var result = {
            has_showCitePopover: typeof _showCitePopover === 'function',
            cards_count: document.querySelectorAll('.ws-cite-card').length,
            card_details: []
        };
        var cards = document.querySelectorAll('.ws-cite-card');
        for (var i = 0; i < Math.min(5, cards.length); i++) {
            var card = cards[i];
            var numEl = card.querySelector('.ws-cite-num');
            result.card_details.push({
                idx: i,
                cite_num_attr: card.getAttribute('data-cite-num'),
                cite_num_text: numEl ? numEl.textContent.trim() : 'NO_NUM_EL',
                classes: card.className,
                has_mouseenter: card.onmouseenter !== null || card.onmouseenter !== undefined
            });
        }
        return result;
    }""")
    print("Debug info:")
    print(f"  _showCitePopover exists: {debug['has_showCitePopover']}")
    print(f"  Cards: {debug['cards_count']}")
    for cd in debug.get("card_details", []):
        print(f"  Card[{cd['idx']}]: attr={cd['cite_num_attr']} text={cd['cite_num_text']} class={cd['classes']}")

    # Try hover-based trigger instead
    cards = page.locator(".ws-cite-card")
    if cards.count() > 0:
        print("\nTrying hover on first card...")
        first_card = cards.first
        first_card.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        first_card.hover()
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        print(f"  Popover visible: {popover.count() > 0}")

        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_verified = "Verified excerpt" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                has_loading = "Loading preview" in srcdoc
                print(f"  Srcdoc length: {len(srcdoc)}")
                print(f"  Verified excerpt: {has_verified}")
                print(f"  No cache: {has_no_cache}")
                print(f"  Loading: {has_loading}")

            page.screenshot(path=os.path.join(OUT, "popover_hover1.png"))
            print(f"  Screenshot: {OUT}/popover_hover1.png")
        else:
            page.screenshot(path=os.path.join(OUT, "popover_nope.png"))
            print(f"  Screenshot (no popover): {OUT}/popover_nope.png")

        # Try second card
        page.mouse.move(10, 10)
        page.wait_for_timeout(500)
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        if cards.count() > 2:
            print("\nTrying hover on third card...")
            third_card = cards.nth(2)
            third_card.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            third_card.hover()
            page.wait_for_timeout(4000)

            popover = page.locator(".ws-cite-popover")
            print(f"  Popover visible: {popover.count() > 0}")

            if popover.count() > 0:
                iframe = popover.locator("iframe")
                if iframe.count() > 0:
                    srcdoc = iframe.first.get_attribute("srcdoc") or ""
                    has_verified = "Verified excerpt" in srcdoc
                    has_no_cache = "No cached content" in srcdoc
                    print(f"  Srcdoc length: {len(srcdoc)}")
                    print(f"  Verified excerpt: {has_verified}")
                    print(f"  No cache: {has_no_cache}")

                page.screenshot(path=os.path.join(OUT, "popover_hover3.png"))
                print(f"  Screenshot: {OUT}/popover_hover3.png")

    browser.close()
    print("\nDone.")
