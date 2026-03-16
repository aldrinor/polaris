"""Test popovers on multiple citation cards to assess content quality."""
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

    # Switch to user mode
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(1000)

    # Expand citations
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    # Check bibliography entries for content type
    bib_info = page.evaluate("""() => {
        return state.bibliography.slice(0, 8).map(function(b, i) {
            return {
                idx: i + 1,
                url: (b.url || '').substring(0, 50),
                has_eids: !!(b.evidence_ids && b.evidence_ids.length),
                has_quote: !!(b.quote || b.verification_quote),
                has_snippet: !!(b.snippet || b.text || b.content_preview),
                title: (b.title || '').substring(0, 40)
            };
        });
    }""")
    print("Bibliography entries:")
    for b in bib_info:
        print(f"  [{b['idx']}] eids={b['has_eids']} quote={b['has_quote']} snippet={b['has_snippet']} | {b['title']}")

    # Test popovers on cards 1, 3, 5 (different sources)
    for cite_num in [1, 3, 5]:
        # Close any existing popover
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        # Trigger popover via JS
        page.evaluate("""(num) => {
            var card = document.querySelector('.ws-cite-card[data-cite-num="' + num + '"]');
            if (!card) {
                // Find by cite number text
                var cards = document.querySelectorAll('.ws-cite-card');
                for (var i = 0; i < cards.length; i++) {
                    var numEl = cards[i].querySelector('.ws-cite-num');
                    if (numEl && parseInt(numEl.textContent) === num) { card = cards[i]; break; }
                }
            }
            if (card && typeof _showCitePopover === 'function') {
                _showCitePopover(num, card);
            }
        }""", cite_num)
        page.wait_for_timeout(3000)  # Wait for API fetch

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_no_cache = "No cached content" in srcdoc
                has_loading = "Loading preview" in srcdoc
                is_real = len(srcdoc) > 500 and not has_no_cache and not has_loading

                # Check if content is clean article text or raw HTML junk
                is_clean = is_real and "Toll Free" not in srcdoc and "accets/frontend" not in srcdoc

                status = "CLEAN" if is_clean else ("RAW" if is_real else ("NO_CACHE" if has_no_cache else "LOADING"))
                print(f"\n  Citation [{cite_num}]: {status} ({len(srcdoc)} chars)")

                # Take screenshot
                page.screenshot(path=os.path.join(OUT, f"audit_popover_{cite_num}.png"))
        else:
            print(f"\n  Citation [{cite_num}]: NO POPOVER")

    browser.close()
    print("\nDone.")
