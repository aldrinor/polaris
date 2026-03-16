"""Check hydration state after server restart."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    errors = []
    page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(12000)

    result = page.evaluate("""() => {
        return {
            bib_length: state.bibliography ? state.bibliography.length : -1,
            vectorId: state.vectorId || 'NONE',
            pipelineComplete: state.pipelineComplete,
            hasReport: !!(state.fullReport && state.fullReport.length > 100),
            reportLen: state.fullReport ? state.fullReport.length : 0,
            viewMode: typeof currentViewMode !== 'undefined' ? currentViewMode : 'unknown',
            endTime: state.endTime || 0
        };
    }""")
    print("State:", result)

    # Check snapshot API directly
    snap = page.evaluate("""() => {
        return fetch('/api/snapshot')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var events = d.events || [];
                var types = {};
                for (var i = 0; i < events.length; i++) {
                    var a = events[i].action || 'unknown';
                    types[a] = (types[a] || 0) + 1;
                }
                return { total_events: events.length, types: types };
            })
            .catch(function(e) { return {error: e.message}; });
    }""")
    print("Snapshot:", snap)

    # Check result API
    if result["vectorId"] != "NONE":
        res = page.evaluate("""(vid) => {
            return fetch('/api/research/result/' + encodeURIComponent(vid))
                .then(function(r) { return r.ok ? r.json() : {status: r.status}; })
                .then(function(d) {
                    return {
                        has_bib: !!(d.bibliography && d.bibliography.length),
                        bib_count: d.bibliography ? d.bibliography.length : 0,
                        has_report: !!(d.final_report),
                        first_bib_keys: d.bibliography && d.bibliography.length ? Object.keys(d.bibliography[0]).join(',') : 'NONE'
                    };
                })
                .catch(function(e) { return {error: e.message}; });
        }""", result["vectorId"])
        print("Result API:", res)

    for e in errors[:15]:
        safe = e.encode("ascii", "replace").decode()[:200]
        print(f"  {safe}")

    browser.close()
