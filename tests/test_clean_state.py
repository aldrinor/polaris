"""Quick check: verify clean page state."""
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:8765", wait_until="domcontentloaded", timeout=10000)
    time.sleep(3)

    # Clear localStorage
    page.evaluate("localStorage.clear()")

    # Navigate fresh
    page.goto("http://localhost:8765", wait_until="domcontentloaded", timeout=10000)
    time.sleep(4)

    page.evaluate('selectHeaderMode("research")')
    time.sleep(2)

    phase = page.evaluate("(function(){ return typeof _wsPhase !== 'undefined' ? _wsPhase : 'N/A'; })()")
    print(f"_wsPhase: {phase}")

    island = page.evaluate("(function(){ var el = document.getElementById('ws-island-text'); return el ? el.textContent : 'N/A'; })()")
    print(f"Island text: '{island}'")

    status = page.evaluate("(function(){ var el = document.getElementById('current-status-text'); return el ? el.textContent : 'N/A'; })()")
    print(f"Status text: '{status}'")

    bc = page.evaluate("(function(){ var el = document.getElementById('ws-breadcrumb-active'); return el ? el.textContent : 'N/A'; })()")
    print(f"Breadcrumb: '{bc}'")

    # Check for "Searching" text anywhere visible
    searching = page.evaluate("""(function(){
        var all = document.body.innerText;
        var lines = all.split('\\n').filter(function(l) { return l.indexOf('Searching') >= 0 || l.indexOf('sources') >= 0; });
        return lines;
    })()""")
    print(f"Lines with 'Searching' or 'sources': {searching}")

    # Check visible nav tabs
    tabs = page.evaluate("""(function(){
        var tabs = [];
        document.querySelectorAll('.nav-tab, .ws-right-tab, [class*=tab]').forEach(function(el) {
            if (el.textContent.trim()) tabs.push(el.textContent.trim().substring(0,40));
        });
        return tabs;
    })()""")
    print(f"Visible tabs: {tabs}")

    # Check island visibility
    island_info = page.evaluate("""(function(){
        var el = document.getElementById('ws-dynamic-island');
        if (el === null) return 'not found';
        var cs = getComputedStyle(el);
        return 'display=' + cs.display + ' class=' + el.className;
    })()""")
    print(f"Island: {island_info}")

    # Header bar text
    header_text = page.evaluate("""(function(){
        var h = document.querySelector('.ws-header');
        if (h === null) return 'N/A';
        return h.innerText.substring(0, 200);
    })()""")
    print(f"WS Header text: {repr(header_text)}")

    # Nav bar text (operator view)
    nav_text = page.evaluate("""(function(){
        var n = document.getElementById('main-nav-bar');
        if (n === null) return 'N/A';
        return n.innerText.substring(0, 200);
    })()""")
    print(f"Nav bar text: {repr(nav_text)}")

    browser.close()
    print("DONE")
