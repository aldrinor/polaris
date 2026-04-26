"""Real browser-level tests for the Evidence Inspector via Playwright.

Spins up the actual FastAPI live_server in a background thread and
drives chromium against it. These tests verify behavior that string-
presence assertions can't prove — DOM identity, focus retention,
caret position, event-driven re-rendering.

Codex M-4 v2 review fix: the focus-retention test was previously a
structural string assertion. This module replaces it with the real
DOM behavior check.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False


def _check_chromium_available() -> bool:
    if not _PLAYWRIGHT_OK:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


_CHROMIUM_AVAILABLE = _check_chromium_available()
pytestmark = pytest.mark.skipif(
    not _CHROMIUM_AVAILABLE, reason="Playwright chromium not installed"
)


def _free_port() -> int:
    """Find a free localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url():
    """Run the FastAPI live_server on a background thread for the module."""
    import uvicorn

    port = _free_port()
    config = uvicorn.Config(
        "scripts.live_server:app",
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server to be ready (poll /health for up to 10s)
    import urllib.request
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=0.5) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("live_server did not boot within 10 seconds")

    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser_page(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{server_url}/inspector/clinical_tirzepatide_t2dm")
        page.wait_for_load_state("networkidle")
        # Switch to the Contradictions view so the matrix is rendered
        page.click('.tab-btn[data-view="contradictions"]')
        page.wait_for_selector('input[data-matrix-filter="query"]', timeout=5000)
        try:
            yield page
        finally:
            browser.close()


def test_inspector_page_loads_in_real_browser(browser_page) -> None:
    """Sanity check: the page actually renders the matrix toolbar."""
    title = browser_page.title()
    assert "Evidence Inspector" in title
    assert browser_page.locator(".matrix-toolbar").count() == 1
    assert browser_page.locator('input[data-matrix-filter="query"]').count() == 1


def test_matrix_query_input_preserves_focus_on_typing(browser_page) -> None:
    """Codex M-4 v2 review fix: typing into the search box must not destroy
    the focused input element. Live re-rendering rebuilds matrix-results,
    NOT the toolbar."""
    page = browser_page
    query = page.locator('input[data-matrix-filter="query"]')
    query.click()  # focus the input
    # Type a multi-character string with delay so each keystroke triggers
    # an `input` event and the result re-renders between keystrokes.
    query.type("body", delay=30)

    # 1. Value reflects what was typed.
    assert query.input_value() == "body"

    # 2. The input element still has focus.
    focused_tag = page.evaluate("document.activeElement.tagName")
    assert focused_tag == "INPUT"

    # 3. The focused input is the SAME element (not a re-rendered replacement).
    focused_filter = page.evaluate(
        "document.activeElement.getAttribute('data-matrix-filter')"
    )
    assert focused_filter == "query"

    # 4. Caret is at the end of the typed text (typing did not reset it).
    selection_start = page.evaluate("document.activeElement.selectionStart")
    assert selection_start == 4


def test_matrix_dom_identity_preserved_across_filter_changes(browser_page) -> None:
    """The toolbar <input> node identity must persist across multiple filter
    keystrokes. Tag the element with a marker before typing and verify the
    marker survives."""
    page = browser_page
    query = page.locator('input[data-matrix-filter="query"]')
    # Clear any previous test value
    query.fill("")
    # Tag the input element directly via JS to track DOM identity
    page.evaluate(
        "document.querySelector('input[data-matrix-filter=\"query\"]').dataset.testMarker = 'abc123'"
    )
    query.click()
    query.type("hi", delay=30)
    # Re-query and verify the marker is still on the SAME element
    marker = page.evaluate(
        "document.querySelector('input[data-matrix-filter=\"query\"]').dataset.testMarker"
    )
    assert marker == "abc123"


def test_matrix_results_update_on_filter_change(browser_page) -> None:
    """Filter typing must actually update the displayed results."""
    page = browser_page
    query = page.locator('input[data-matrix-filter="query"]')
    query.fill("")
    # Wait for the initial results count
    page.wait_for_selector("#matrix-summary")

    initial_summary = page.locator("#matrix-summary").text_content()
    assert "/ 14" in initial_summary  # all 14 clusters visible

    # Type a query that should match only some clusters
    query.click()
    query.type("body weight", delay=10)

    # Summary should have updated to a smaller filtered count
    page.wait_for_function(
        """() => {
            const t = document.getElementById('matrix-summary')?.textContent || '';
            return /^\\d+ \\/ 14 clusters$/.test(t.trim());
        }""",
        timeout=3000,
    )
    new_summary = page.locator("#matrix-summary").text_content()
    assert new_summary != initial_summary


def test_matrix_clear_button_resets_query(browser_page) -> None:
    """The clear button resets all filters to 'all' / ''."""
    page = browser_page
    query = page.locator('input[data-matrix-filter="query"]')
    query.fill("nonsense_xyz")
    page.wait_for_function(
        """() => {
            const t = document.getElementById('matrix-summary')?.textContent || '';
            return t.startsWith('0 /');
        }""",
        timeout=3000,
    )
    page.click(".matrix-clear")
    page.wait_for_function(
        """() => {
            const t = document.getElementById('matrix-summary')?.textContent || '';
            return /^\\d+ \\/ 14/.test(t.trim()) && parseInt(t) === 14;
        }""",
        timeout=3000,
    )
    assert query.input_value() == ""
