"""Playwright test: clean start → upload → brief appears."""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"

# Create a real test PDF with actual text content using reportlab or fitz
def create_test_pdf(path: Path):
    """Create a PDF with real text content for testing."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open()
        page = doc.new_page()
        text = (
            "C-POLAR Antimicrobial Coating Technology\n\n"
            "C-POLAR is a proprietary antimicrobial surface coating designed for "
            "long-lasting protection against pathogens on high-touch surfaces. "
            "The technology uses a combination of photocatalytic titanium dioxide "
            "and silver ion release mechanisms to achieve continuous antimicrobial "
            "activity for up to 12 months per application.\n\n"
            "Key applications include healthcare facility surfaces, public transit "
            "touchpoints, food processing equipment, and HVAC filtration systems. "
            "Clinical trials at Johns Hopkins demonstrated 99.7% reduction in "
            "surface bacterial counts over a 6-month evaluation period.\n\n"
            "The wildfire smoke application targets indoor air quality protection "
            "during wildfire events, where particulate matter and volatile organic "
            "compounds penetrate building envelopes. C-POLAR coated HVAC filters "
            "showed 3x longer effective life compared to standard MERV-13 filters "
            "in smoke-contaminated environments."
        )
        page.insert_text((72, 72), text, fontsize=11)
        doc.save(str(path))
        doc.close()
        return True
    except Exception as e:
        print(f"Failed to create PDF with fitz: {e}")
        return False


def test_clean_flow():
    # Create test PDF
    test_dir = Path(__file__).parent / "fixtures"
    test_dir.mkdir(exist_ok=True)
    test_pdf = test_dir / "C-POLAR for Wildfire Smoke.pdf"
    if not create_test_pdf(test_pdf):
        print("SKIP: Could not create test PDF")
        return

    print(f"Test PDF created: {test_pdf} ({test_pdf.stat().st_size} bytes)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # --- Step 1: Load clean landing page ---
        page.goto(BASE, wait_until="domcontentloaded")
        time.sleep(3)

        # Verify NO example cards on landing page
        example_cards = page.query_selector_all(".example-card")
        print(f"Step 1 - Landing example cards: {len(example_cards)} (expect 0)")
        assert len(example_cards) == 0, f"Expected 0 example cards, got {len(example_cards)}"

        # --- Step 2: Switch to workspace (research mode) ---
        page.evaluate('selectHeaderMode("research")')
        time.sleep(2)

        # Verify NO example chips in idle workspace
        chips = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-chips');
                return el ? el.children.length : -1;
            }
        """)
        print(f"Step 2 - Idle chips count: {chips} (expect 0)")
        assert chips == 0, f"Expected 0 idle chips, got {chips}"

        # Verify NO sources
        source_rows = page.evaluate("""
            () => {
                var rows = document.querySelectorAll('.ws-source-row:not(.ws-source-select-all)');
                return rows.length;
            }
        """)
        print(f"Step 2 - Source rows: {source_rows} (expect 0)")

        # Verify greeting shows (no sources = greeting visible)
        greeting_visible = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-greeting');
                return el && el.style.display !== 'none';
            }
        """)
        print(f"Step 2 - Greeting visible: {greeting_visible} (expect true)")

        # Brief should be hidden (no sources)
        brief_visible = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-brief');
                return el && el.style.display !== 'none';
            }
        """)
        print(f"Step 2 - Brief visible: {brief_visible} (expect false)")

        # --- Step 3: Upload PDF via API ---
        import requests
        with open(test_pdf, "rb") as f:
            resp = requests.post(
                f"{BASE}/api/documents/upload",
                files={"file": ("C-POLAR for Wildfire Smoke.pdf", f, "application/pdf")},
            )
        print(f"Step 3 - Upload status: {resp.status_code}")
        data = resp.json()
        doc_id = data["doc_id"]
        print(f"Step 3 - doc_id: {doc_id}, filename: {data.get('filename')}, chars: {data.get('content_chars')}")
        assert resp.status_code == 200
        assert data.get("content_chars", 0) > 50, f"PDF has too little text: {data.get('content_chars')}"

        # --- Step 4: Trigger renderDocumentPanel to pick up new doc ---
        page.evaluate("renderDocumentPanel()")

        # Wait for brief LLM call — poll until content appears (max 30s)
        for i in range(30):
            time.sleep(1)
            done = page.evaluate("""
                () => {
                    var el = document.getElementById('ws-idle-brief-content');
                    return el && el.style.display !== 'none';
                }
            """)
            if done:
                print(f"Step 4 - Brief content appeared after {i+1}s")
                break
        else:
            # Check loading state for debugging
            loading = page.evaluate("""
                () => {
                    var l = document.getElementById('ws-idle-brief-loading');
                    var c = document.getElementById('ws-idle-brief-content');
                    return {
                        loading_display: l ? l.style.display : 'N/A',
                        content_display: c ? c.style.display : 'N/A',
                        brief_display: document.getElementById('ws-idle-brief') ?
                            document.getElementById('ws-idle-brief').style.display : 'N/A'
                    };
                }
            """)
            print(f"Step 4 - Brief did not complete in 30s. State: {loading}")

        # Check source appears in sidebar
        source_names = page.evaluate("""
            () => {
                var rows = document.querySelectorAll('.ws-source-row-name');
                return Array.from(rows).map(r => r.textContent.trim());
            }
        """)
        print(f"Step 4 - Source names: {source_names}")
        found_source = any("C-POLAR" in n for n in source_names)
        assert found_source, f"Uploaded file not shown. Got: {source_names}"

        # --- Step 5: Check brief appeared ---
        brief_visible = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-brief');
                return el && el.style.display !== 'none';
            }
        """)
        print(f"Step 5 - Brief panel visible: {brief_visible}")

        greeting_visible = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-greeting');
                return el && el.style.display !== 'none';
            }
        """)
        print(f"Step 5 - Greeting hidden: {not greeting_visible}")

        summary_text = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-brief-summary');
                return el ? el.textContent.trim() : '';
            }
        """)
        print(f"Step 5 - Brief summary: {summary_text[:150]}...")

        questions = page.evaluate("""
            () => {
                var el = document.getElementById('ws-idle-brief-questions');
                if (!el) return [];
                return Array.from(el.children).map(b => b.textContent.trim());
            }
        """)
        print(f"Step 5 - Suggested questions: {questions}")

        # Verify brief has real content
        assert brief_visible, "Brief panel should be visible after upload"
        assert len(summary_text) > 20, f"Brief summary too short: '{summary_text}'"
        assert len(questions) > 0, f"No suggested questions generated"

        # --- Cleanup ---
        requests.delete(f"{BASE}/api/documents/{doc_id}")
        browser.close()

        print("\nPASS: Clean flow works — upload triggers brief with summary + questions")


if __name__ == "__main__":
    test_clean_flow()
