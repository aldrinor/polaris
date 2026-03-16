"""Trace all setWorkspacePhase calls to find what resets it to idle."""
import os
from playwright.sync_api import sync_playwright

OUT = "outputs/debug_audit"
os.makedirs(OUT, exist_ok=True)
URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    # Inject monkey-patch BEFORE any scripts run
    page.add_init_script("""
        window.__phaseLog = [];
        // Wait for setWorkspacePhase to be defined, then wrap it
        var _origInterval = setInterval(function() {
            if (typeof setWorkspacePhase === 'function' && !setWorkspacePhase.__wrapped) {
                var _orig = setWorkspacePhase;
                setWorkspacePhase = function(phase) {
                    var stack = new Error().stack.split('\\n').slice(1, 4).map(function(s) { return s.trim(); });
                    window.__phaseLog.push({
                        phase: phase,
                        time: Date.now(),
                        callers: stack
                    });
                    return _orig(phase);
                };
                setWorkspacePhase.__wrapped = true;
                clearInterval(_origInterval);
            }
        }, 10);
    """)

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(15000)

    # Get the phase transition log
    log = page.evaluate("() => window.__phaseLog || []")
    print(f"=== Phase Transitions ({len(log)} total) ===")
    for i, entry in enumerate(log):
        phase = entry.get("phase", "?")
        callers = entry.get("callers", [])
        t = entry.get("time", 0)
        caller_str = " <- ".join(c[:80] for c in callers[:2])
        safe = caller_str.encode("ascii", "replace").decode()
        print(f"  [{i:2d}] phase={phase:10s} t={t}  {safe}")

    final_phase = page.evaluate("() => typeof _wsPhase !== 'undefined' ? _wsPhase : 'UNDEF'")
    print(f"\nFinal _wsPhase: {final_phase}")

    browser.close()
