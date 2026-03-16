"""Trace setWorkspacePhase calls to find what's overriding report."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")
OUT = "outputs/visual_audit"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    # Inject phase tracing before page loads
    page.add_init_script("""() => {
        window._phaseLog = [];
        var origSetWorkspacePhase = null;
        Object.defineProperty(window, '_interceptPhase', {
            get: function() { return true; }
        });
        // We'll monkey-patch after the function is defined
        var observer = new MutationObserver(function() {
            if (typeof setWorkspacePhase === 'function' && !origSetWorkspacePhase) {
                origSetWorkspacePhase = setWorkspacePhase;
                window.setWorkspacePhase = function(phase) {
                    var trace = new Error().stack.split('\\n').slice(1, 4).join(' <- ');
                    window._phaseLog.push({
                        time: Date.now(),
                        phase: phase,
                        trace: trace.substring(0, 200)
                    });
                    return origSetWorkspacePhase(phase);
                };
            }
        });
        observer.observe(document, {childList: true, subtree: true});
    }""")

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(15000)

    # Get phase log
    log = page.evaluate("() => window._phaseLog || []")
    print(f"Phase transitions ({len(log)}):")
    for entry in log:
        print(f"  +{entry['time']}ms: setWorkspacePhase('{entry['phase']}')")
        print(f"    Trace: {entry['trace'][:150]}")
        print()

    # Current state
    result = page.evaluate("""() => {
        return {
            phase: typeof _wsPhase !== 'undefined' ? _wsPhase : 'unknown',
            complete: state.pipelineComplete,
            active: state.pipelineActive,
            cards: document.querySelectorAll('.ws-cite-card').length
        };
    }""")
    print(f"Final state: {result}")

    browser.close()
