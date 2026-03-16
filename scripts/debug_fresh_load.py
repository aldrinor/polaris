"""Debug fresh page load - why are citations empty?"""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    console_msgs = []
    page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)

    # Check at 2s, 5s, 10s, 15s
    for wait in [2, 3, 5, 5]:
        page.wait_for_timeout(wait * 1000)
        result = page.evaluate("""() => {
            return {
                bib_length: state.bibliography ? state.bibliography.length : -1,
                vectorId: state.vectorId || 'NONE',
                pipelineComplete: state.pipelineComplete,
                viewMode: typeof currentViewMode !== 'undefined' ? currentViewMode : 'unknown',
                citationCards: document.querySelectorAll('.ws-cite-card').length,
                citeSectionVisible: (function() {
                    var sec = document.getElementById('ws-section-citations');
                    if (!sec) return 'NOT_FOUND';
                    if (sec.classList.contains('expanded')) return 'expanded';
                    if (sec.classList.contains('collapsed')) return 'collapsed';
                    return sec.className;
                })(),
                citeCountBadge: (function() {
                    var el = document.getElementById('ws-citations-count-val');
                    return el ? el.textContent : 'NOT_FOUND';
                })(),
                wsPhase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown'
            };
        }""")
        print(f"After +{wait}s: bib={result['bib_length']} cards={result['citationCards']} section={result['citeSectionVisible']} badge={result['citeCountBadge']} phase={result['wsPhase']} view={result['viewMode']}")

    # Check if _renderCitationCards exists and try calling it
    render_check = page.evaluate("""() => {
        var hasFn = typeof _renderCitationCards === 'function';
        if (hasFn && state.bibliography && state.bibliography.length > 0) {
            _renderCitationCards();
            return {hasFn: true, called: true, cardsAfter: document.querySelectorAll('.ws-cite-card').length};
        }
        return {hasFn: hasFn, called: false, bibLen: state.bibliography ? state.bibliography.length : 0};
    }""")
    print(f"\n_renderCitationCards: {render_check}")

    # Check what view mode we're in and if user mode shows citations
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(2000)

    after_mode = page.evaluate("""() => {
        return {
            cards: document.querySelectorAll('.ws-cite-card').length,
            sectionState: (function() {
                var sec = document.getElementById('ws-section-citations');
                return sec ? sec.className : 'NOT_FOUND';
            })(),
            rightPanelVisible: (function() {
                var rp = document.getElementById('ws-right');
                return rp ? rp.style.display || getComputedStyle(rp).display : 'NOT_FOUND';
            })()
        };
    }""")
    print(f"After setViewMode('user'): {after_mode}")

    # Expand citations and check
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-citations');
        if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(1000)

    final = page.evaluate("""() => {
        return {
            cards: document.querySelectorAll('.ws-cite-card').length,
            sectionState: (function() {
                var sec = document.getElementById('ws-section-citations');
                return sec ? sec.className : 'NOT_FOUND';
            })(),
            listHTML: (function() {
                var list = document.getElementById('ws-citations-list');
                return list ? list.innerHTML.substring(0, 200) : 'NOT_FOUND';
            })()
        };
    }""")
    print(f"After expand: cards={final['cards']} section={final['sectionState']}")
    print(f"  List HTML: {final['listHTML']}")

    # Screenshot
    page.screenshot(path=os.path.join(OUT, "debug_fresh_load.png"))

    # Console errors
    errors = [m for m in console_msgs if '[error]' in m.lower() or '[warning]' in m.lower()]
    if errors:
        print(f"\nConsole errors ({len(errors)}):")
        for e in errors[:10]:
            safe = e.encode('ascii', 'replace').decode()[:200]
            print(f"  {safe}")

    browser.close()
