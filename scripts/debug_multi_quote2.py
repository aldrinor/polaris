"""Test multi-quote popover with proper timing and error capture."""
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
    page.wait_for_timeout(25000)  # Long wait for full hydration + result API

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Cards: {total}")

    # Check bib evidence_ids for card 2 (should have multiple)
    bib_check = page.evaluate("""() => {
        var b = state.bibliography[1];
        if (!b) return {exists: false};
        return {
            exists: true,
            title: (b.title || '').substring(0, 50),
            eids: b.evidence_ids || [],
            snippet: (b.snippet || '').substring(0, 30),
            quote: (b.quote || b.verification_quote || '').substring(0, 30)
        };
    }""")
    print(f"Bib[2]: {bib_check}")

    if total > 1:
        all_msgs.clear()

        # Hover card 2
        cards.nth(1).hover(timeout=5000)
        page.wait_for_timeout(8000)

        # Check iframe content
        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                excerpt_count = srcdoc.count("EXCERPT")
                has_verified = "Verified excerpt" in srcdoc
                has_stats = "evidence piece" in srcdoc
                has_loading = "Loading preview" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                iframe_id = iframe.first.get_attribute("id") or ""
                print(f"\nPopover card 2:")
                print(f"  Iframe ID: {iframe_id}")
                print(f"  Srcdoc len: {len(srcdoc)}")
                print(f"  Excerpts: {excerpt_count}")
                print(f"  Verified: {has_verified}")
                print(f"  Stats: {has_stats}")
                print(f"  Loading: {has_loading}")
                print(f"  No cache: {has_no_cache}")
                if len(srcdoc) < 2000:
                    print(f"  Full srcdoc: {srcdoc[:500]}")

            page.screenshot(path=os.path.join(OUT, "multi_quote2_card2.png"))

        # Console messages
        relevant = [m for m in all_msgs if "error" in m.lower() or "404" in m or "fetch" in m.lower() or "preview" in m.lower()]
        print(f"\nConsole ({len(all_msgs)} msgs, {len(relevant)} relevant):")
        for m in relevant[:10]:
            safe = m.encode("ascii", "replace").decode()[:200]
            print(f"  {safe}")

    browser.close()
