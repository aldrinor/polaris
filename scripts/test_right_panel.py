"""Playwright visual test: right panel in idle, running (simulated), and report states."""
from playwright.sync_api import sync_playwright
import time

URL = "http://localhost:8765"
OUT = "C:/POLARIS/outputs/"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(URL, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_selector("#ws-right", timeout=10000)
    time.sleep(1)

    # --- Screenshot 1: IDLE state (full page) ---
    page.screenshot(path=OUT + "right_panel_idle_full.png", full_page=False)
    print("[1] Idle full page captured")

    # --- Screenshot 2: Right panel only (idle) ---
    right = page.query_selector("#ws-right")
    if right:
        right.screenshot(path=OUT + "right_panel_idle.png")
        print("[2] Idle right panel captured")
    else:
        print("[2] WARN: #ws-right not found")

    # --- Simulate RUNNING state ---
    page.evaluate("""() => {
        // Set phase to running
        if (typeof setWorkspacePhase === 'function') setWorkspacePhase('running');

        // Populate metrics
        var ev = document.getElementById('ws-metric-evidence');
        var sr = document.getElementById('ws-metric-sources');
        var fa = document.getElementById('ws-metric-faith');
        var co = document.getElementById('ws-metric-cost');
        var ti = document.getElementById('ws-metric-time');
        if (ev) ev.textContent = '142';
        if (sr) sr.textContent = '23';
        if (fa) fa.textContent = '80%';
        if (co) co.textContent = '$0.47';
        if (ti) ti.textContent = '2m 34s';

        // Add task feed items
        if (typeof _addTaskFeedItem === 'function') {
            _addTaskFeedItem('Searched 12 sources (47 results)', 'done', '3s');
            _addTaskFeedItem('Interviewed Domain Expert', 'done', '8s');
            _addTaskFeedItem('Verified 89 claims', 'done', '45s');
            _addTaskFeedItem('Analyzing evidence quality...', 'active');
        }

        // Add discovered sources
        if (typeof _addDiscoveredSource === 'function') {
            _addDiscoveredSource({url: 'https://www.nature.com/articles/microplastics-water', title: 'Microplastics in Municipal Water Treatment'});
            _addDiscoveredSource({url: 'https://www.sciencedirect.com/pfas-removal', title: 'PFAS Removal via Activated Carbon Filtration'});
            _addDiscoveredSource({url: 'https://www.epa.gov/water-research/technical-brief', title: 'Technical Brief on Water Contaminants'});
            _addDiscoveredSource({url: 'https://www.who.int/guidelines-drinking-water', title: 'Guidelines for Drinking Water Quality'});
            _addDiscoveredSource({url: 'https://pubs.acs.org/doi/10.1021/water-treatment', title: 'Advanced Water Treatment Technologies Review'});
        }
    }""")
    time.sleep(1)

    # Screenshot 3: Running state full page
    page.screenshot(path=OUT + "right_panel_running_full.png", full_page=False)
    print("[3] Running full page captured")

    # Screenshot 4: Right panel (running)
    right = page.query_selector("#ws-right")
    if right:
        right.screenshot(path=OUT + "right_panel_running.png")
        print("[4] Running right panel captured")

    # --- Click Citations section to see source cards ---
    page.evaluate("""() => {
        // Make sure citations section is expanded
        if (typeof _setRightSection === 'function') {
            _setRightSection('citations', 'expanded');
        }
    }""")
    time.sleep(0.5)
    right = page.query_selector("#ws-right")
    if right:
        right.screenshot(path=OUT + "right_panel_running_citations.png")
        print("[5] Running citations section captured")

    # --- Simulate REPORT state with bibliography ---
    page.evaluate("""() => {
        // Mock bibliography
        state.bibliography = [
            {url: 'https://www.nature.com/articles/microplastics-water', title: 'Microplastics in Municipal Water Treatment', domain: 'nature.com', is_faithful: true, snippet: 'Recent studies have demonstrated that conventional water treatment plants show varying effectiveness in removing microplastic particles. Activated carbon filters removed 99.4% of microplastic particles from source water samples during controlled laboratory testing. However, field performance varies significantly based on filter age and maintenance schedules.', verification_quote: 'Activated carbon filters removed 99.4% of microplastic particles from source water samples'},
            {url: 'https://www.sciencedirect.com/pfas-removal', title: 'PFAS Removal via Activated Carbon Filtration', domain: 'sciencedirect.com', is_faithful: true, snippet: 'Granular activated carbon (GAC) has emerged as the primary technology for per- and polyfluoroalkyl substances removal from drinking water sources.', verification_quote: 'Granular activated carbon has emerged as the primary technology'},
            {url: 'https://www.epa.gov/water-research/technical-brief', title: 'Technical Brief on Water Contaminants', domain: 'epa.gov', is_faithful: true, snippet: 'The EPA recommends multi-barrier approaches combining physical filtration, chemical treatment, and biological processes for comprehensive water purification.'},
            {url: 'https://www.who.int/guidelines-drinking-water', title: 'Guidelines for Drinking Water Quality', domain: 'who.int', is_faithful: true},
            {url: 'https://waterfilterreview.com/best-2024', title: 'Best Water Filters 2024', domain: 'waterfilterreview.com', is_faithful: false},
        ];
        state.evidence = 142;
        state.faithfulness = 0.805;
        state.cost = 1.31;
        state.words = 11583;

        if (typeof setWorkspacePhase === 'function') setWorkspacePhase('report');

        // Render citations
        if (typeof renderCitationSidebar === 'function') {
            renderCitationSidebar([1, 2, 3, 4, 5]);
        }
    }""")
    time.sleep(1)

    # Screenshot 6: Report state
    right = page.query_selector("#ws-right")
    if right:
        right.screenshot(path=OUT + "right_panel_report.png")
        print("[6] Report right panel captured")

    # Screenshot 7: Full page report
    page.screenshot(path=OUT + "right_panel_report_full.png", full_page=False)
    print("[7] Report full page captured")

    # --- Hover over first citation to trigger popover ---
    card_count = page.evaluate("document.querySelectorAll('.ws-cite-card').length")
    cite_list_html = page.evaluate("document.getElementById('ws-citation-list') ? document.getElementById('ws-citation-list').innerHTML.substring(0,200) : 'MISSING'")
    js_errors = page.evaluate("""() => {
        try { renderCitationSidebar([1, 2, 3, 4, 5]); return 'OK'; }
        catch(e) { return e.message; }
    }""")
    card_count2 = page.evaluate("document.querySelectorAll('.ws-cite-card').length")
    print(f"[DBG] cards={card_count}, after retry={card_count2}, renderResult={js_errors}")
    print(f"[DBG] citation-list html: {cite_list_html[:150]}")
    cite_card = page.query_selector('.ws-cite-card[data-cite-num="1"]')
    if cite_card:
        cite_card.hover()
        time.sleep(1)  # Wait for popover timer (200ms delay + render)
        page.screenshot(path=OUT + "right_panel_popover.png", full_page=False)
        print("[8] Popover captured (loading state)")

        # Wait for iframe timeout (4s) to see "blocked" fallback
        time.sleep(4)
        page.screenshot(path=OUT + "right_panel_popover_blocked.png", full_page=False)
        print("[8b] Popover captured (blocked state)")

        # Also capture just the right panel area + popover
        right = page.query_selector("#ws-right")
        if right:
            right.screenshot(path=OUT + "right_panel_popover_detail.png")
            print("[9] Popover detail captured")
    else:
        print("[8] WARN: No citation card found to hover")

    browser.close()
    print("\nAll screenshots saved to outputs/")
