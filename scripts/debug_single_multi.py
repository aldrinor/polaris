"""Test both single-evidence and multi-evidence cards."""
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
    page.wait_for_timeout(25000)

    cards = page.locator(".ws-cite-card")
    total = cards.count()

    # Card 1 (1 evidence), Card 2 (5 evidence), Card 8 (3 evidence)
    for idx in [0, 1, 7]:
        if idx >= total:
            break

        page.mouse.move(10, 10)
        page.wait_for_timeout(300)
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        card = cards.nth(idx)
        card.hover(timeout=5000)
        page.wait_for_timeout(7000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                excerpts = srcdoc.count("EXCERPT")
                has_v = "Verified excerpt" in srcdoc
                has_stats = "evidence piece" in srcdoc
                print(f"Card [{idx+1}]: {excerpts} excerpts, verified={has_v}, stats={has_stats}, len={len(srcdoc)}")
            page.screenshot(path=os.path.join(OUT, f"final_card_{idx+1}.png"))
        else:
            print(f"Card [{idx+1}]: NO POPOVER")

    browser.close()
    print("Done.")
