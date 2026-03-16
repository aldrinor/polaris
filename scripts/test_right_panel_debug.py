"""Debug test: capture console errors and dark theme state."""
from playwright.sync_api import sync_playwright
import time

URL = "http://localhost:8765"
OUT = "C:/POLARIS/outputs/"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    # Capture console errors
    errors = []
    page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
    page.on("pageerror", lambda exc: errors.append(f"[PAGEERROR] {exc.message}"))

    page.goto(URL, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_selector("#ws-right", timeout=10000)
    time.sleep(2)

    # Screenshot: whatever state the server is in (no simulation)
    page.screenshot(path=OUT + "debug_initial.png", full_page=False)
    print("[1] Initial state captured")

    # Check dark theme
    theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    print(f"[2] Current theme: {theme}")

    # Switch to dark theme if not already
    page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    time.sleep(0.5)
    page.screenshot(path=OUT + "debug_dark.png", full_page=False)
    print("[3] Dark theme captured")

    # Try hovering a source card in the citations section (real data)
    src_card = page.query_selector('.ws-source-item')
    if src_card:
        src_card.hover()
        time.sleep(1)
        page.screenshot(path=OUT + "debug_source_hover.png", full_page=False)
        print("[4] Source card hover captured")
    else:
        print("[4] No .ws-source-item found")

    # Try hovering a cite card (real data)
    cite_card = page.query_selector('.ws-cite-card')
    if cite_card:
        cite_card.hover()
        time.sleep(1)
        page.screenshot(path=OUT + "debug_cite_hover.png", full_page=False)
        print("[5] Cite card hover captured")
    else:
        print("[5] No .ws-cite-card found")

    # Check for JS errors
    print(f"\n--- Console errors/warnings ({len(errors)}) ---")
    for e in errors[:20]:
        print(e)

    # Check key functions exist
    fns = page.evaluate("""() => {
        return {
            setWorkspacePhase: typeof setWorkspacePhase,
            renderCitationSidebar: typeof renderCitationSidebar,
            showCitePopoverCard: typeof showCitePopoverCard,
            _showSourcePreview: typeof _showSourcePreview,
            _addDiscoveredSource: typeof _addDiscoveredSource,
            _toggleRightSection: typeof _toggleRightSection,
            _escHtml: typeof _escHtml,
            hideCitePopoverCard: typeof hideCitePopoverCard,
        }
    }""")
    print(f"\n--- Function availability ---")
    for k, v in fns.items():
        status = "OK" if v == "function" else f"MISSING ({v})"
        print(f"  {k}: {status}")

    browser.close()
