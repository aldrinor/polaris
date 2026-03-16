"""Debug why bibliography is empty after hydration."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type in ("error", "warning") else None)

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)

    # Check at 3s, 8s, 15s
    for wait in [3, 5, 7]:
        page.wait_for_timeout(wait * 1000)
        total = wait * 1000 if wait == 3 else (3 + 5 + 7) * 1000
        result = page.evaluate("""() => {
            return {
                bib_length: state.bibliography ? state.bibliography.length : -1,
                has_evidence_ids: state.bibliography && state.bibliography.length > 0 && state.bibliography[0].evidence_ids ? true : false,
                first_keys: state.bibliography && state.bibliography.length > 0 ? Object.keys(state.bibliography[0]).join(',') : 'EMPTY',
                vectorId: state.vectorId || 'NONE',
                pipelineComplete: state.pipelineComplete
            };
        }""")
        elapsed = sum(range(1, wait+1)) if wait <= 3 else "?"
        print(f"  After {wait}s more: bib={result['bib_length']}, has_eids={result['has_evidence_ids']}, keys={result['first_keys']}, vid={result['vectorId']}")

    # Check console errors
    relevant = [e for e in errors if 'bibliography' in e.lower() or 'result' in e.lower() or 'fetch' in e.lower() or 'error' in e.lower() or '_renderCitation' in e]
    if relevant:
        print(f"\nRelevant console messages ({len(relevant)}):")
        for e in relevant[:10]:
            safe = e.encode('ascii', 'replace').decode()[:200]
            print(f"  {safe}")
    else:
        print(f"\nNo relevant console errors ({len(errors)} total messages)")

    browser.close()
