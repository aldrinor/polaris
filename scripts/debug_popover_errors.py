"""Check for JS errors when popover loads."""
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

    all_msgs = []
    page.on("console", lambda msg: all_msgs.append(f"[{msg.type}] {msg.text}"))

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(20000)

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Cards: {total}")

    if total > 0:
        # Clear console
        all_msgs.clear()

        # Hover card 2 (has 3 evidence)
        cards.nth(1).hover(timeout=5000)
        page.wait_for_timeout(8000)

        # Check errors after hover
        errors = [m for m in all_msgs if "[error]" in m or "Error" in m or "TypeError" in m or "fetch" in m.lower()]
        print(f"\nConsole after hover ({len(all_msgs)} total, {len(errors)} errors):")
        for m in all_msgs[:20]:
            safe = m.encode("ascii", "replace").decode()[:200]
            print(f"  {safe}")

        # Check iframe state
        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                print(f"\nIframe srcdoc len: {len(srcdoc)}")
                print(f"Contains 'Loading': {'Loading' in srcdoc}")
                print(f"Contains 'Verified': {'Verified' in srcdoc}")
                print(f"Contains 'EXCERPT': {'EXCERPT' in srcdoc}")
                # Show first 500 chars
                print(f"First 300 chars: {srcdoc[:300]}")

            # Check iframe ID
            iframe_id = iframe.first.get_attribute("id") or ""
            print(f"Iframe ID: {iframe_id}")

        page.screenshot(path=os.path.join(OUT, "popover_debug_errors.png"))

    browser.close()
