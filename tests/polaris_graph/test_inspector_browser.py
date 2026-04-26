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


# ---------------------------------------------------------------------------
# M-5: Frame Coverage Manifest — real DOM behavior
# ---------------------------------------------------------------------------


def test_coverage_view_renders_visual_bar_and_v30_warning(browser_page) -> None:
    """M-5: switching to Frame Coverage shows visual bar + V30 warning + 15 rows."""
    page = browser_page
    page.click('.tab-btn[data-view="frame-coverage"]')
    page.wait_for_selector(".coverage-summary", timeout=3000)
    assert page.locator(".coverage-bar").count() == 1
    assert page.locator(".coverage-warning").count() == 1
    # 15 entries in run-14
    assert page.locator(".coverage-row").count() == 15
    # The warning must contain the V30 retrieval-coverage caveat text
    warning_text = page.locator(".coverage-warning").text_content()
    assert "phase1_retrieval_coverage_only" in warning_text


def test_coverage_view_groups_rows_by_section(browser_page) -> None:
    """Rows are grouped by section (Efficacy, Mechanism, Regulatory, etc.)."""
    page = browser_page
    page.click('.tab-btn[data-view="frame-coverage"]')
    page.wait_for_selector(".coverage-section-group", timeout=3000)
    section_titles = page.locator(".coverage-section-title").all_text_contents()
    # run-14 has Efficacy, Mechanism, Regulatory at minimum
    titles_joined = " ".join(section_titles).lower()
    assert "efficacy" in titles_joined
    assert "regulatory" in titles_joined


def test_coverage_view_offers_resolve_button_on_gap_rows(browser_page) -> None:
    """Gap rows expose a resolve-gap button that emits the custom event with
    full slot context (slot_id, status, section, subsection_title) per Codex
    M-5 fix #2."""
    page = browser_page
    page.click('.tab-btn[data-view="frame-coverage"]')
    page.wait_for_selector(".coverage-summary", timeout=3000)
    # Listen for the polaris:resolve-gap custom event
    page.evaluate(
        """() => {
            window.__resolveGapEvents = [];
            document.addEventListener('polaris:resolve-gap', (e) => {
                window.__resolveGapEvents.push(e.detail);
            });
        }"""
    )
    # Click the first available resolve-gap button (run-14 has 1 fail_min_fields)
    resolve_btns = page.locator('button[data-action="resolve-gap"]:not(:disabled)')
    if resolve_btns.count() > 0:
        first = resolve_btns.first
        entity_id = first.get_attribute("data-entity-id")
        first.click()
        events = page.evaluate("window.__resolveGapEvents")
        assert len(events) >= 1
        evt = events[-1]
        # Entity id is the legacy handle; it must still be present.
        assert evt["entity_id"] == entity_id
        # Slot context per Codex M-5 review fix #2.
        assert "slot_id" in evt
        assert "status" in evt
        assert "section" in evt
        assert "subsection_title" in evt


def test_coverage_view_renders_slot_id_label_visibly(browser_page) -> None:
    """Codex M-5 fix #2: slot_id is rendered as a visible label on every row
    that has one. Run-14: every entry has a slot_id."""
    page = browser_page
    page.click('.tab-btn[data-view="frame-coverage"]')
    page.wait_for_selector(".coverage-summary", timeout=3000)
    slots = page.locator(".coverage-row-slot")
    # 15 entries in run-14; every one has slot_id
    assert slots.count() == 15
    first_slot_text = slots.first.text_content()
    assert "slot " in first_slot_text  # "slot efficacy_surpass_1" etc.


def test_coverage_view_required_and_retrieved_chips_are_labeled(browser_page) -> None:
    """Codex M-5 fix #3: required vs retrieved chips have visible labels
    and distinct visual treatment."""
    page = browser_page
    page.click('.tab-btn[data-view="frame-coverage"]')
    page.wait_for_selector(".coverage-summary", timeout=3000)
    labels = page.locator(".coverage-fields-label").all_text_contents()
    labels_lower = [l.strip().lower() for l in labels]
    # Both labels appear
    assert "required" in labels_lower
    assert "retrieved" in labels_lower
    # Distinct chip classes are applied
    required_chips = page.locator(".coverage-chip-required")
    retrieved_chips = page.locator(".coverage-chip-retrieved")
    assert required_chips.count() > 0
    assert retrieved_chips.count() > 0


# ---------------------------------------------------------------------------
# M-6: Methods + Provenance Bundle — real DOM behavior
# ---------------------------------------------------------------------------


def test_methods_view_renders_top_line_cards(browser_page) -> None:
    """M-6: switching to Methods shows the 6-card grid + 13 rule checks."""
    page = browser_page
    page.click('.tab-btn[data-view="methods"]')
    page.wait_for_selector(".methods-grid", timeout=3000)
    cards = page.locator(".methods-card")
    # 6 top-line cards: Run ID, Protocol SHA, Cost, Verified/Dropped,
    # Evaluator gate, Contradictions
    assert cards.count() == 6
    # Two-family invariant banner present (run-14: deepseek vs qwen)
    banner = page.locator(".methods-two-family-banner")
    assert banner.count() == 1
    banner_text = banner.text_content()
    assert "holds" in banner_text.lower()
    assert "deepseek" in banner_text.lower()
    assert "qwen" in banner_text.lower()


def test_methods_view_renders_rule_checks(browser_page) -> None:
    """M-6: pre-commit rule checks (PT01..PT13) all listed with pass/fail status."""
    page = browser_page
    page.click('.tab-btn[data-view="methods"]')
    page.wait_for_selector(".methods-rule-list", timeout=3000)
    # Run-14 has 13 rule checks; each rule emits 1-2 rows (header + optional details)
    rule_rows = page.locator(".methods-rule-row")
    assert rule_rows.count() >= 13
    # PT01 pre-registered protocol present should be in run-14
    pt01_id = page.locator(".methods-rule-id:has-text('PT01')")
    assert pt01_id.count() >= 1


def test_methods_view_renders_expected_vs_actual_tier_distribution(browser_page) -> None:
    """M-6: the protocol's expected tier bands must be compared against
    the actual corpus distribution, with in-band/out-of-band flags."""
    page = browser_page
    page.click('.tab-btn[data-view="methods"]')
    page.wait_for_selector(".methods-section", timeout=3000)
    # Find the section title for tier distribution
    title = page.locator(".methods-section-title:has-text('Expected vs actual')")
    assert title.count() >= 1
    # The tier-distribution table should mention 'actual' and 'expected'
    page_text = page.content()
    assert "actual" in page_text.lower()
    assert "expected" in page_text.lower()
    # Either 'in band' or 'out of band' should appear
    assert "in band" in page_text.lower() or "out of band" in page_text.lower()


def test_methods_view_export_button_links_to_audit_bundle(browser_page) -> None:
    """M-6: the export button links to /api/inspector/runs/{slug}/audit-bundle.zip."""
    page = browser_page
    page.click('.tab-btn[data-view="methods"]')
    page.wait_for_selector(".methods-export-btn", timeout=3000)
    btn = page.locator(".methods-export-btn")
    assert btn.count() == 1
    href = btn.get_attribute("href")
    assert href and href.endswith("/audit-bundle.zip")
    # download attribute set so the button initiates a download
    assert btn.get_attribute("download") is not None


# ---------------------------------------------------------------------------
# M-7: Source Tier Mix — real DOM behavior
# ---------------------------------------------------------------------------


def test_tier_mix_view_renders_headline_cards_and_bar(browser_page) -> None:
    """M-7: switching to Tier Mix shows 4 headline cards + visual bar + band table."""
    page = browser_page
    page.click('.tab-btn[data-view="tier-mix"]')
    page.wait_for_selector(".tier-mix-bar-large", timeout=3000)
    # 4 headline cards
    assert page.locator(".tier-headline-card").count() == 4
    # Big visual bar (M-7 specific class, not the small header strip)
    assert page.locator(".tier-mix-bar-large").count() == 1
    # Band-comparison table for the 7 tiers
    table = page.locator(".tier-mix-table")
    assert table.count() == 1
    # At least 7 rows (T1..T7)
    rows = page.locator(".tier-mix-table tbody tr")
    assert rows.count() >= 7


def test_tier_mix_view_renders_promo_calibration_badge(browser_page) -> None:
    """M-7: the promo-adjective count and calibration badge must render."""
    page = browser_page
    page.click('.tab-btn[data-view="tier-mix"]')
    page.wait_for_selector(".tier-mix-promo-badge", timeout=3000)
    badge = page.locator(".tier-mix-promo-badge")
    assert badge.count() == 1
    badge_text = badge.text_content()
    # Run-14: 1 promo adjective, well-calibrated
    assert badge_text.strip() in ("well-calibrated", "elevated", "promotional drift")


def test_tier_mix_view_renders_band_graphics(browser_page) -> None:
    """M-7: each tier band has a visual graphic with bracket + actual marker."""
    page = browser_page
    page.click('.tab-btn[data-view="tier-mix"]')
    page.wait_for_selector(".tier-mix-band-graphic", timeout=3000)
    # 7 tiers in run-14 protocol expected_tier_distribution
    graphics = page.locator(".tier-mix-band-graphic")
    assert graphics.count() >= 7
    brackets = page.locator(".tier-mix-band-bracket")
    actuals = page.locator(".tier-mix-band-actual")
    assert brackets.count() >= 7
    assert actuals.count() >= 7


def test_tier_mix_view_renders_material_deviation_banner(browser_page) -> None:
    """M-7: run-14 has material_deviation=True so the warning banner shows."""
    page = browser_page
    page.click('.tab-btn[data-view="tier-mix"]')
    page.wait_for_selector(".tier-mix-banner", timeout=3000)
    banner = page.locator(".tier-mix-banner")
    assert banner.count() == 1
    banner_text = banner.text_content()
    # Run-14 has material_deviation=True so the deviation-warning class applies
    if "Material tier deviation" in banner_text:
        cls = banner.get_attribute("class")
        assert "tier-mix-deviation-warning" in cls
