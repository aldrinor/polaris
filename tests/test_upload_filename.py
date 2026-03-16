"""Playwright test: verify uploaded file retains original filename."""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"

# Create a small test PDF-like file with a recognizable name
TEST_DIR = Path(__file__).parent / "fixtures"
TEST_DIR.mkdir(exist_ok=True)
TEST_FILE = TEST_DIR / "C-POLAR for Wildfire Smoke.pdf"
if not TEST_FILE.exists():
    # Minimal PDF (valid header, enough for ingester to accept)
    TEST_FILE.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td "
        b"(Test) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n"
        b"0000000115 00000 n \n0000000210 00000 n \n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n310\n%%EOF"
    )


def test_upload_preserves_filename():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE, wait_until="domcontentloaded")
        time.sleep(3)

        # Upload via API directly, then check list
        import requests
        with open(TEST_FILE, "rb") as f:
            resp = requests.post(
                f"{BASE}/api/documents/upload",
                files={"file": ("C-POLAR for Wildfire Smoke.pdf", f, "application/pdf")},
            )
        print(f"Upload response: {resp.status_code}")
        data = resp.json()
        print(f"Upload data: {data}")
        assert resp.status_code == 200, f"Upload failed: {resp.text}"

        doc_id = data["doc_id"]

        # Check metadata via API
        list_resp = requests.get(f"{BASE}/api/documents/list")
        docs = list_resp.json()["documents"]
        print(f"Documents: {docs}")

        uploaded = [d for d in docs if d["doc_id"] == doc_id]
        assert len(uploaded) == 1, f"Document not found in list"
        meta = uploaded[0]
        print(f"original_filename in metadata: {meta.get('original_filename')}")
        assert meta["original_filename"] == "C-POLAR for Wildfire Smoke.pdf", (
            f"Expected 'C-POLAR for Wildfire Smoke.pdf', got '{meta.get('original_filename')}'"
        )

        # Now check the UI renders it correctly
        page.reload(wait_until="domcontentloaded")
        time.sleep(3)

        # Get the source row text
        source_names = page.evaluate("""
            () => {
                var rows = document.querySelectorAll('.ws-source-row-name');
                return Array.from(rows).map(r => r.textContent.trim());
            }
        """)
        print(f"Source names in UI: {source_names}")

        # Should contain our filename (possibly truncated)
        found = any("C-POLAR" in n for n in source_names)
        assert found, f"Filename not found in UI. Got: {source_names}"

        # Cleanup: delete the test doc
        requests.delete(f"{BASE}/api/documents/{doc_id}")

        browser.close()
        print("PASS: Upload filename preserved correctly")


if __name__ == "__main__":
    test_upload_preserves_filename()
