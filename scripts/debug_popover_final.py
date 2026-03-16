"""Final visual popover verification - captures screenshots of popovers."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(12000)  # Full hydration + API fetch

    # Check state
    state_check = page.evaluate("""() => {
        return {
            bib_count: state.bibliography ? state.bibliography.length : 0,
            vectorId: state.vectorId || 'NONE',
            pipelineComplete: state.pipelineComplete
        };
    }""")
    print("State:", state_check)

    # Switch to user mode
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(2000)

    # Expand citations section
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    # Count cards after mode switch
    cards = page.locator(".ws-cite-card")
    total = cards.count()
    print(f"Citation cards visible: {total}")

    if total == 0:
        # Try rendering citations manually
        page.evaluate("() => { if (typeof _renderCitationCards === 'function') _renderCitationCards(); }")
        page.wait_for_timeout(1000)
        total = cards.count()
        print(f"After manual render: {total}")

    # Check bibliography enrichment
    bib_detail = page.evaluate("""() => {
        if (!state.bibliography) return [];
        return state.bibliography.slice(0, 5).map(function(b, i) {
            return {
                idx: i + 1,
                title: (b.title || '').substring(0, 50),
                eids: b.evidence_ids ? b.evidence_ids.length : 0,
                first_eid: (b.evidence_ids || [])[0] || 'NONE',
                has_quote: !!(b.quote || b.verification_quote)
            };
        });
    }""")
    print("\nBibliography enrichment:")
    for b in bib_detail:
        print(f"  [{b['idx']}] eids={b['eids']} first={b['first_eid']} quote={b['has_quote']} | {b['title']}")

    # Take a pre-popover screenshot
    page.screenshot(path=os.path.join(OUT, "popover_pre.png"))

    # Test popover on cards with evidence_ids
    for cite_idx in [0, 2, 4]:
        if cite_idx >= total:
            break

        cite_num = cite_idx + 1

        # Remove existing popover
        page.evaluate("() => { var p = document.querySelector('.ws-cite-popover'); if (p) p.remove(); }")
        page.wait_for_timeout(300)

        # Trigger via JS
        triggered = page.evaluate("""(num) => {
            var card = null;
            var cards = document.querySelectorAll('.ws-cite-card');
            for (var i = 0; i < cards.length; i++) {
                var numEl = cards[i].querySelector('.ws-cite-num');
                if (numEl && parseInt(numEl.textContent) === num) {
                    card = cards[i];
                    break;
                }
            }
            if (card && typeof _showCitePopover === 'function') {
                _showCitePopover(num, card);
                return {ok: true, card_text: card.textContent.substring(0, 80)};
            }
            return {ok: false};
        }""", cite_num)

        if not triggered.get("ok"):
            print(f"\n  Card [{cite_num}]: Could not trigger popover")
            continue

        print(f"\n  Card [{cite_num}]: Triggered. Card text: {triggered.get('card_text', '')[:60]}")

        # Wait for API fetch
        page.wait_for_timeout(4000)

        popover = page.locator(".ws-cite-popover")
        if popover.count() == 0:
            print(f"    NO POPOVER visible")
            continue

        # Check iframe content
        iframe = popover.locator("iframe")
        if iframe.count() == 0:
            print(f"    No iframe in popover")
            continue

        srcdoc = iframe.first.get_attribute("srcdoc") or ""
        length = len(srcdoc)

        has_no_cache = "No cached content" in srcdoc
        has_loading = "Loading preview" in srcdoc
        has_verified = "Verified excerpt" in srcdoc
        has_mark = "<mark>" in srcdoc

        if has_verified and has_mark:
            status = "VERIFIED_QUOTE"
        elif has_no_cache:
            status = "NO_CACHE"
        elif has_loading:
            status = "STILL_LOADING"
        elif length > 500:
            status = "READABILITY_HTML"
        else:
            status = f"UNKNOWN ({length} chars)"

        print(f"    Status: {status}")
        print(f"    Srcdoc length: {length}")

        if has_verified:
            import re
            mark_match = re.search(r'<mark>(.*?)</mark>', srcdoc, re.DOTALL)
            if mark_match:
                quote = mark_match.group(1)[:120]
                print(f"    Quote: {quote}...")

        if has_no_cache:
            # Check why - does the bib entry have evidence_ids?
            bib_info = page.evaluate("""(num) => {
                var bib = state.bibliography[num - 1];
                if (!bib) return {exists: false};
                return {
                    exists: true,
                    eids: bib.evidence_ids || [],
                    url: (bib.url || '').substring(0, 60)
                };
            }""", cite_num)
            print(f"    Bib entry: {bib_info}")

        # Screenshot
        page.screenshot(path=os.path.join(OUT, f"popover_card{cite_num}.png"))
        print(f"    Screenshot: {OUT}/popover_card{cite_num}.png")

    # Direct API test for first enriched entry
    first_enriched = next((b for b in bib_detail if b["eids"] > 0), None)
    if first_enriched:
        eid = first_enriched["first_eid"]
        api_check = page.evaluate("""(args) => {
            var vid = args[0], eid = args[1];
            return fetch('/api/research/source-preview/' + encodeURIComponent(vid) + '/' + encodeURIComponent(eid))
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    return {
                        has_preview: !!d.has_preview,
                        quote_text_len: (d.quote_text || '').length,
                        quote_preview: (d.quote_text || '').substring(0, 120),
                        readability_len: (d.readability_html || '').length,
                        keys: Object.keys(d).join(',')
                    };
                })
                .catch(function(e) { return {error: e.message}; });
        }""", [state_check["vectorId"], eid])
        print(f"\nDirect API for eid={eid}:")
        for k, v in api_check.items():
            print(f"  {k}: {v}")

    browser.close()
    print("\nDone.")
