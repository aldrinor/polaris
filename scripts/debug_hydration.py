"""Debug script: check hydration state and take screenshots."""
import os
import json
from playwright.sync_api import sync_playwright

OUT = "outputs/debug_audit"
os.makedirs(OUT, exist_ok=True)
URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    logs = []
    page.on("console", lambda msg: logs.append(msg.text))

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(12000)

    # 1. State diagnostic
    diag = page.evaluate("""() => {
        var r = {};
        r.wsPhase = (typeof _wsPhase !== 'undefined') ? _wsPhase : 'UNDEF';
        r.workspacePhase = (typeof state !== 'undefined' && state.workspacePhase) ? state.workspacePhase : 'UNDEF';
        r.pipelineComplete = (typeof state !== 'undefined') ? !!state.pipelineComplete : false;
        r.pipelineActive = (typeof state !== 'undefined') ? !!state.pipelineActive : false;
        r.eventCount = (typeof state !== 'undefined') ? (state.eventCount || 0) : 0;
        r.viewMode = (typeof _currentViewMode !== 'undefined') ? _currentViewMode : 'UNDEF';
        r.taskFeedCount = (typeof _wsTaskFeedItems !== 'undefined') ? _wsTaskFeedItems.length : -1;
        var dot = document.getElementById('status-dot');
        r.dotClass = dot ? dot.className : 'NONE';
        var st = document.getElementById('current-status-text');
        r.statusText = st ? st.textContent : 'NONE';
        r.fullReport = (typeof state !== 'undefined' && state.fullReport) ? state.fullReport.length : 0;
        r.bibliography = (typeof state !== 'undefined' && state.bibliography) ? state.bibliography.length : 0;
        return r;
    }""")
    print("=== State Diagnostic ===")
    for k, v in diag.items():
        print(f"  {k}: {v}")

    # 2. Check report_assembled in snapshot
    snap = page.evaluate("""() => {
        return fetch('/api/snapshot').then(function(r) { return r.json(); }).then(function(d) {
            var ebt = d.events_by_type || {};
            var types = Object.keys(ebt);
            var raCount = 0;
            types.forEach(function(t) {
                ebt[t].forEach(function(e) { if (e.action === 'report_assembled') raCount++; });
            });
            return {
                total: d.total_event_count,
                pipeline_running: d.pipeline_running,
                report_assembled_count: raCount,
                event_types: types.join(', ')
            };
        });
    }""")
    print(f"\n=== Snapshot ===")
    for k, v in snap.items():
        print(f"  {k}: {v}")

    # 3. Check if workspace DOM exists
    ws_check = page.evaluate("""() => {
        var ws = document.getElementById('workspace');
        return {
            exists: !!ws,
            className: ws ? ws.className : 'NONE',
            dataPhase: ws ? ws.getAttribute('data-phase') : 'NONE',
            visible: ws ? (getComputedStyle(ws).display !== 'none') : false
        };
    }""")
    print(f"\n=== Workspace DOM ===")
    for k, v in ws_check.items():
        print(f"  {k}: {v}")

    # 4. Right sidebar sections
    sections = page.evaluate("""() => {
        var ids = ['live', 'citations', 'memory'];
        var r = {};
        ids.forEach(function(id) {
            var el = document.getElementById('ws-section-' + id);
            r[id] = el ? el.className : 'NOT_FOUND';
        });
        return r;
    }""")
    print(f"\n=== Sidebar Sections ===")
    for k, v in sections.items():
        print(f"  {k}: {v}")

    # 5. Task feed items detail
    feed = page.evaluate("""() => {
        if (typeof _wsTaskFeedItems === 'undefined') return [];
        return _wsTaskFeedItems.slice(0, 10).map(function(t) {
            return { label: t.label, status: t.status, ts: t.ts };
        });
    }""")
    print(f"\n=== Task Feed (first 10) ===")
    for i, item in enumerate(feed):
        print(f"  [{i}] {item.get('status','?')}: {item.get('label','?')[:60]}  ts={item.get('ts','?')}")

    # 6. Dynamic island
    island = page.evaluate("""() => {
        var el = document.getElementById('ws-dynamic-island');
        if (!el) return {exists: false};
        return {
            exists: true,
            className: el.className,
            opacity: getComputedStyle(el).opacity,
            text: el.innerText.substring(0, 100)
        };
    }""")
    print(f"\n=== Dynamic Island ===")
    for k, v in island.items():
        print(f"  {k}: {v}")

    # 7. Screenshots
    page.screenshot(path=os.path.join(OUT, "01_default_view.png"))

    # Force user mode
    page.evaluate("() => { if (typeof setViewMode === 'function') setViewMode('user'); }")
    page.wait_for_timeout(1000)
    page.screenshot(path=os.path.join(OUT, "02_user_mode.png"))

    # Manually set workspace to report phase if stuck
    stuck_phase = page.evaluate("() => typeof _wsPhase !== 'undefined' ? _wsPhase : 'UNDEF'")
    print(f"\n  Phase after setViewMode('user'): {stuck_phase}")

    if stuck_phase != "report":
        print("  ** PHASE IS WRONG - forcing to report **")
        page.evaluate("() => { if (typeof setWorkspacePhase === 'function') setWorkspacePhase('report'); }")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            if (typeof appendReportBlock === 'function' && state.fullReport) {
                appendReportBlock(state.fullReport, state.bibliography);
            }
        }""")
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(OUT, "03_forced_report.png"))

    # Expand live section and screenshot
    page.evaluate("""() => {
        var sec = document.getElementById('ws-section-live');
        if (sec) { sec.classList.remove('collapsed','hidden'); sec.classList.add('expanded'); }
    }""")
    page.wait_for_timeout(500)
    page.screenshot(path=os.path.join(OUT, "04_live_expanded.png"))

    # Relevant console logs
    relevant = [l for l in logs if any(kw in l.lower() for kw in ['phase', 'workspace', 'snapshot', 'hydrat', 'report_assembled'])]
    if relevant:
        print(f"\n=== Relevant Console Logs ({len(relevant)}) ===")
        for l in relevant[:15]:
            safe = l.encode('ascii', 'replace').decode()
            print(f"  {safe[:200]}")

    browser.close()
    print("\nDone.")
