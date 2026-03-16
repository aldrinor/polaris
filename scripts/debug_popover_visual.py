"""Visually verify popover content after quote_text preference fix."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    # Collect console messages
    console_msgs = []
    page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)  # Full hydration

    # Switch to user mode
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(1000)

    # Expand citations section
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    # Check bibliography enrichment status
    bib_info = page.evaluate("""() => {
        if (!state.bibliography || !state.bibliography.length) return {count: 0, enriched: 0};
        var enriched = 0;
        for (var i = 0; i < state.bibliography.length; i++) {
            if (state.bibliography[i].evidence_ids && state.bibliography[i].evidence_ids.length > 0) enriched++;
        }
        return {
            count: state.bibliography.length,
            enriched: enriched,
            sample: state.bibliography.slice(0, 3).map(function(b) {
                return {
                    title: (b.title || '').substring(0, 60),
                    url: (b.url || '').substring(0, 60),
                    eids: (b.evidence_ids || []).slice(0, 3),
                    has_quote: !!(b.quote || b.verification_quote)
                };
            })
        };
    }""")
    print(f"Bibliography: {bib_info['count']} total, {bib_info['enriched']} enriched with evidence_ids")
    for s in bib_info.get('sample', []):
        print(f"  Title: {s['title']}")
        print(f"  URL: {s['url']}")
        print(f"  Evidence IDs: {s['eids']}")
        print(f"  Has quote: {s['has_quote']}")
        print()

    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Total citation cards: {total}")

    # Test popovers on cards 1, 3, 5
    for idx in [0, 2, 4]:
        if idx >= total:
            break

        cite_num = idx + 1
        print(f"\n--- Testing card [{cite_num}] ---")

        # Remove any existing popover
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        # Trigger popover via JS (more reliable than hover)
        triggered = page.evaluate("""(num) => {
            var card = null;
            var cards = document.querySelectorAll('.ws-cite-card');
            for (var i = 0; i < cards.length; i++) {
                var numEl = cards[i].querySelector('.ws-cite-num');
                if (numEl && parseInt(numEl.textContent) === num) { card = cards[i]; break; }
            }
            if (card && typeof _showCitePopover === 'function') {
                _showCitePopover(num, card);
                return true;
            }
            return false;
        }""", cite_num)
        print(f"  Triggered: {triggered}")

        if not triggered:
            print(f"  SKIP: Could not trigger popover for card {cite_num}")
            continue

        # Wait for async API fetch
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() == 0:
            print(f"  NO POPOVER visible")
            continue

        # Check iframe content
        iframe = popover.locator("iframe")
        if iframe.count() > 0:
            srcdoc = iframe.first.get_attribute("srcdoc") or ""
            length = len(srcdoc)

            # Classify content
            has_no_cache = "No cached content" in srcdoc
            has_loading = "Loading preview" in srcdoc
            has_verified_excerpt = "Verified excerpt" in srcdoc
            has_mark_tag = "<mark>" in srcdoc
            has_readability = length > 500 and not has_no_cache and not has_loading and not has_verified_excerpt

            if has_verified_excerpt:
                status = "VERIFIED_QUOTE"
            elif has_readability:
                status = "READABILITY_HTML"
            elif has_no_cache:
                status = "NO_CACHE"
            elif has_loading:
                status = "STILL_LOADING"
            else:
                status = "UNKNOWN"

            print(f"  Status: {status}")
            print(f"  Srcdoc length: {length}")
            print(f"  Has <mark> tag: {has_mark_tag}")

            if has_verified_excerpt:
                # Extract the quote text for display
                import re
                mark_match = re.search(r'<mark>(.*?)</mark>', srcdoc)
                if mark_match:
                    quote = mark_match.group(1)[:150]
                    print(f"  Quote preview: {quote}...")

            if has_no_cache:
                print(f"  PROBLEM: Still showing 'No cached content'!")

            # Take screenshot
            page.screenshot(path=os.path.join(OUT, f"popover_card{cite_num}.png"))
            print(f"  Screenshot: {OUT}/popover_card{cite_num}.png")
        else:
            print(f"  No iframe in popover")

    # Check for relevant console errors
    fetch_errors = [m for m in console_msgs if 'source-preview' in m.lower() or 'error' in m.lower() and 'fetch' in m.lower()]
    if fetch_errors:
        print(f"\nRelevant console messages:")
        for m in fetch_errors[:5]:
            safe = m.encode('ascii', 'replace').decode()[:200]
            print(f"  {safe}")

    # Also check the API directly for one evidence item
    if bib_info['enriched'] > 0 and bib_info['sample'][0]['eids']:
        first_eid = bib_info['sample'][0]['eids'][0]
        api_result = page.evaluate("""(eid) => {
            return fetch('/api/research/source-preview/' + encodeURIComponent(state.vectorId) + '/' + encodeURIComponent(eid))
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    return {
                        has_preview: d.has_preview || false,
                        has_quote: !!(d.quote_text),
                        quote_len: (d.quote_text || '').length,
                        quote_preview: (d.quote_text || '').substring(0, 100),
                        has_readability: !!(d.readability_html),
                        readability_len: (d.readability_html || '').length
                    };
                })
                .catch(function(e) { return {error: e.message}; });
        }""", first_eid)
        print(f"\nDirect API check for eid={first_eid}:")
        for k, v in api_result.items():
            print(f"  {k}: {v}")

    browser.close()
    print("\nDone.")
