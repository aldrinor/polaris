"""Test multi-quote popover - shows all verified excerpts from source."""
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

    # Check enrichment
    bib_info = page.evaluate("""() => {
        if (!state.bibliography) return [];
        return state.bibliography.slice(0, 10).map(function(b, i) {
            return {
                idx: i + 1,
                eids: b.evidence_ids ? b.evidence_ids.length : 0,
                title: (b.title || '').substring(0, 40)
            };
        });
    }""")
    print("Bibliography evidence counts:")
    for b in bib_info:
        print(f"  [{b['idx']}] {b['eids']} evidence | {b['title']}")

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"\nCards: {total}")

    # Test card 2 (5 evidence pieces) and card 5 (5 evidence pieces) for multi-quote
    for idx in [1, 4, 0]:
        if idx >= total:
            break

        page.mouse.move(10, 10)
        page.wait_for_timeout(300)
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        card = cards.nth(idx)
        card.hover(timeout=5000)
        page.wait_for_timeout(6000)  # Longer wait for multiple API calls

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                excerpt_count = srcdoc.count("EXCERPT")
                has_verified = "Verified excerpts" in srcdoc
                has_stats = "evidence piece" in srcdoc
                print(f"\nCard [{idx+1}]: {excerpt_count} excerpts, verified_label={has_verified}, stats={has_stats}, len={len(srcdoc)}")
            page.screenshot(path=os.path.join(OUT, f"multi_quote_{idx+1}.png"))
            print(f"  Screenshot: {OUT}/multi_quote_{idx+1}.png")
        else:
            print(f"\nCard [{idx+1}]: NO POPOVER")

    browser.close()
    print("\nDone.")
