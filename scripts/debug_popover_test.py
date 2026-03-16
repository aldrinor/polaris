"""Test popover shows real content, not 'No cached content available'."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)  # Wait for full hydration + API backfill

    # Verify bibliography is enriched
    bib_check = page.evaluate("""() => {
        if (!state.bibliography || !state.bibliography.length) return {ok: false, reason: 'empty'};
        var b = state.bibliography[0];
        return {
            ok: true,
            count: state.bibliography.length,
            has_eids: !!(b.evidence_ids && b.evidence_ids.length),
            first_eid: (b.evidence_ids || [])[0] || 'NONE',
            url: (b.url || '').substring(0, 50)
        };
    }""")
    print(f"Bibliography: {bib_check}")

    # Switch to user mode
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(1000)

    # Expand citations section
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    # Find citation cards
    cards = page.locator(".ws-cite-card")
    card_count = cards.count()
    print(f"Citation cards: {card_count}")

    if card_count > 0:
        # Hover first card to trigger popover
        cards.first.hover()
        page.wait_for_timeout(1000)

        # Check popover
        popover = page.locator(".ws-cite-popover")
        print(f"Popover visible: {popover.count() > 0}")

        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                print(f"  Initial srcdoc length: {len(srcdoc)}")
                print(f"  Contains 'No cached content': {'No cached content' in srcdoc}")
                print(f"  Contains 'Loading preview': {'Loading preview' in srcdoc}")

                # Wait for async API fetch
                page.wait_for_timeout(3000)
                srcdoc2 = iframe.first.get_attribute("srcdoc") or ""
                print(f"  After 3s srcdoc length: {len(srcdoc2)}")
                print(f"  Has real content (>1000 chars): {len(srcdoc2) > 1000}")

                if "No cached content" in srcdoc2:
                    print("  FAIL: Still showing 'No cached content'")
                elif len(srcdoc2) > 1000:
                    print("  PASS: Real content loaded!")

            # Take screenshot with popover visible
            page.screenshot(path=os.path.join(OUT, "audit_popover.png"))
            print(f"  Screenshot: {OUT}/audit_popover.png")
        else:
            # Popover may need explicit trigger via JS
            print("  Trying JS trigger...")
            page.evaluate("""() => {
                var card = document.querySelector('.ws-cite-card');
                if (card && typeof _showCitePopover === 'function') {
                    var num = parseInt(card.getAttribute('data-cite-num') || card.querySelector('.ws-cite-num').textContent);
                    _showCitePopover(num, card);
                }
            }""")
            page.wait_for_timeout(4000)
            popover2 = page.locator(".ws-cite-popover")
            if popover2.count() > 0:
                iframe = popover2.locator("iframe")
                if iframe.count() > 0:
                    srcdoc = iframe.first.get_attribute("srcdoc") or ""
                    print(f"  JS-triggered srcdoc length: {len(srcdoc)}")
                    print(f"  Contains 'No cached content': {'No cached content' in srcdoc}")
                    print(f"  Has real content: {len(srcdoc) > 1000}")
                page.screenshot(path=os.path.join(OUT, "audit_popover.png"))
                print(f"  Screenshot: {OUT}/audit_popover.png")

    browser.close()
    print("Done.")
