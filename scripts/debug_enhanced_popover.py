"""Test enhanced popover with quote + source context."""
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
    page.wait_for_timeout(20000)

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Cards: {total}")

    for idx in [0, 2, 9]:
        if idx >= total:
            break

        # Clear popover
        page.mouse.move(10, 10)
        page.wait_for_timeout(300)
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        card = cards.nth(idx)
        card.hover(timeout=5000)
        page.wait_for_timeout(5000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_quote = "Verified excerpt" in srcdoc
                has_context = "Source context" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                print(f"Card [{idx+1}]: quote={has_quote} context={has_context} no_cache={has_no_cache} len={len(srcdoc)}")
            page.screenshot(path=os.path.join(OUT, f"enhanced_popover_{idx+1}.png"))
            print(f"  Screenshot: {OUT}/enhanced_popover_{idx+1}.png")

            # Also scroll down in the iframe to show context section
            if has_context:
                page.evaluate("""(fIdx) => {
                    var iframes = document.querySelectorAll('.ws-popover-iframe');
                    if (iframes[0]) {
                        var doc = iframes[0].contentDocument || iframes[0].contentWindow.document;
                        var ctx = doc.querySelector('.ctx-label');
                        if (ctx) ctx.scrollIntoView({behavior: 'instant'});
                    }
                }""", idx)
                page.wait_for_timeout(500)
                page.screenshot(path=os.path.join(OUT, f"enhanced_context_{idx+1}.png"))
                print(f"  Context screenshot: {OUT}/enhanced_context_{idx+1}.png")
        else:
            print(f"Card [{idx+1}]: NO POPOVER")

    browser.close()
    print("Done.")
