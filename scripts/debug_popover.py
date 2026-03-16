"""Verify popover enrichment: bibliography entries should have evidence_ids + quotes after hydration."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(12000)

    result = page.evaluate("""() => {
        if (!state.bibliography) return {error: "no bibliography"};
        var enriched = 0;
        var total = state.bibliography.length;
        var samples = [];
        for (var i = 0; i < total; i++) {
            var b = state.bibliography[i];
            var hasEids = b.evidence_ids && b.evidence_ids.length > 0;
            var hasQuote = !!(b.quote || b.verification_quote);
            if (hasEids) enriched++;
            if (i < 5) {
                samples.push({
                    idx: i,
                    url: (b.url || "").substring(0, 60),
                    evidence_ids: hasEids ? b.evidence_ids.length : 0,
                    has_quote: hasQuote,
                    quote_preview: (b.quote || b.verification_quote || "").substring(0, 60)
                });
            }
        }
        return {total: total, enriched: enriched, samples: samples};
    }""")

    print("=== Bibliography Enrichment ===")
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Total entries: {result['total']}")
        print(f"  Enriched (have evidence_ids): {result['enriched']}/{result['total']}")
        for s in result.get("samples", []):
            eids = s["evidence_ids"]
            q = s["quote_preview"]
            print(f"  [{s['idx']}] {s['url']}")
            print(f"       evidence_ids: {eids}, has_quote: {s['has_quote']}")
            if q:
                print(f"       quote: {q}...")

    # Now test the popover by hovering a citation card
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(1000)

    # Expand citations section
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) {
            sec.classList.remove('collapsed');
            sec.classList.add('expanded');
        }
    }""")
    page.wait_for_timeout(500)

    # Hover the first citation card to trigger popover
    cards = page.locator(".ws-cite-card")
    if cards.count() > 0:
        cards.first.hover()
        page.wait_for_timeout(2000)

        # Check if popover appeared
        popover = page.locator(".ws-cite-popover")
        if popover.count() > 0:
            # Check content
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc = iframe.first.get_attribute("srcdoc") or ""
                has_loading = "Loading preview" in srcdoc
                has_no_cache = "No cached content" in srcdoc
                has_real_content = len(srcdoc) > 500 and "No cached" not in srcdoc
                print(f"\n=== Popover Content ===")
                print(f"  srcdoc length: {len(srcdoc)}")
                print(f"  Shows 'Loading preview': {has_loading}")
                print(f"  Shows 'No cached content': {has_no_cache}")
                print(f"  Has real content (>500 chars, no error): {has_real_content}")
                if has_real_content:
                    print(f"  Content preview: {srcdoc[:200]}...")
            else:
                print("\n  Popover has no iframe")
        else:
            print("\n  No popover appeared on hover")

        # Wait for async fetch and re-check
        page.wait_for_timeout(3000)
        if popover.count() > 0:
            iframe = popover.locator("iframe")
            if iframe.count() > 0:
                srcdoc2 = iframe.first.get_attribute("srcdoc") or ""
                print(f"\n=== After API fetch (3s later) ===")
                print(f"  srcdoc length: {len(srcdoc2)}")
                has_real = len(srcdoc2) > 1000
                print(f"  Has real content: {has_real}")
                if has_real:
                    # Take screenshot
                    page.screenshot(path="outputs/visual_audit/audit_popover.png")
                    print(f"  Screenshot: outputs/visual_audit/audit_popover.png")

    browser.close()
    print("\nDone.")
