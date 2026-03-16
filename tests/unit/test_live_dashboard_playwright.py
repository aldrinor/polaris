"""
Playwright browser audit for the POLARIS Live Dashboard.

Validates:
- Page loads without JS errors
- All 7 tabs switch and render
- Slate color scheme (no green #10A37F)
- Phase stepper, metrics panel, anomaly bar present
- Enriched data: evidence details, section content, verification verdicts,
  cluster themes, bibliography, citation mapping, STORM expertise
- Event processing works (injects synthetic events via JS)

Run: python -m pytest tests/unit/test_live_dashboard_playwright.py -v
Requires: playwright, uvicorn, fastapi running on a free port
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Skip entire module if POLARIS_SKIP_PLAYWRIGHT is set or if not on CI-friendly env
pytestmark = pytest.mark.skipif(
    os.getenv("POLARIS_SKIP_PLAYWRIGHT", "0") == "1",
    reason="POLARIS_SKIP_PLAYWRIGHT=1",
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url():
    """Start live_server.py on a free port for the test session."""
    port = _find_free_port()
    # Create a dummy trace file so the server has something to tail
    trace_dir = Path("logs")
    trace_dir.mkdir(exist_ok=True)
    dummy_trace = trace_dir / "pg_trace_DASHBOARD_TEST.jsonl"
    dummy_trace.write_text("", encoding="utf-8")

    proc = subprocess.Popen(
        [
            sys.executable, "scripts/live_server.py",
            "--port", str(port),
            "--no-tunnel",
            "--trace", str(dummy_trace),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(Path(__file__).resolve().parents[2]),
    )

    url = f"http://localhost:{port}"

    # Wait for server to be ready (max 10s)
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        out = proc.stdout.read().decode(errors="replace")
        pytest.fail(f"Server failed to start on port {port}. Output:\n{out[:2000]}")

    yield url

    proc.kill()
    proc.wait(timeout=5)
    # Clean up dummy trace
    if dummy_trace.exists():
        dummy_trace.unlink()


@pytest.fixture(scope="module")
def browser_page(server_url):
    """Launch Chromium and navigate to the dashboard."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture JS console errors
    js_errors = []
    page.on("console", lambda msg: js_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    # SSE keeps connection open indefinitely, so "networkidle" will always timeout.
    # Use "domcontentloaded" and wait for JS to initialize.
    page.goto(server_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)  # Let snapshot load + SSE connect

    yield page, js_errors

    browser.close()
    pw.stop()


# ---- Synthetic events to inject via browser JS ----
SYNTHETIC_EVENTS = [
    {"type": "node_start", "node": "plan", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:00Z"},
    {"type": "node_end", "node": "plan", "duration_ms": 5200, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:05Z"},
    {"type": "node_start", "node": "search", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:06Z"},
    {"type": "search_result", "engine": "serper", "query": "PFAS treatment activated carbon efficiency", "result_count": 10, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:07Z"},
    {"type": "search_result", "engine": "s2", "query": "granular activated carbon PFAS removal", "result_count": 5, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:08Z"},
    {"type": "fetch", "url": "https://nature.com/articles/s12345", "status": "success", "content_len": 30000, "method": "jina", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:10Z"},
    {"type": "fetch", "url": "https://epa.gov/water/pfas-treatment", "status": "snippet_fallback", "content_len": 800, "method": "trafilatura", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:11Z"},
    {"type": "node_end", "node": "search", "duration_ms": 15000, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:21Z"},
    {"type": "node_start", "node": "storm_interviews", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:22Z"},
    {"type": "llm_call", "call_type": "perspective_discovery", "perspectives": ["Environmental Chemist", "Water Engineer", "Public Health Expert"], "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:23Z"},
    {"type": "storm_transcript", "persona": "Environmental Chemist", "round": 1, "question": "What are the primary mechanisms by which GAC removes PFAS?", "answer": "Granular activated carbon adsorbs PFAS through hydrophobic interactions.", "sources": ["nature.com"], "key_findings": ["GAC removes >90% PFOS", "Short-chain PFAS less effectively removed"], "expertise": "PFAS remediation specialist", "question_focus": "Adsorption mechanisms and efficiency", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:30Z"},
    {"type": "node_end", "node": "storm_interviews", "duration_ms": 30000, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:52Z"},
    {"type": "node_start", "node": "analyze", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:00:53Z"},
    {"type": "evidence", "action": "extracted", "count": 45, "gold": 8, "silver": 25, "bronze": 12, "sources_fetched": 5, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:01:00Z"},
    {"type": "evidence", "action": "evidence_detail", "count": 3, "items": [
        {"id": "ev_001", "statement": "GAC removes over 90% of PFOS from contaminated water", "quote": "Our results demonstrate >90% removal of PFOS using GAC at standard flow rates", "source_url": "https://nature.com/articles/s12345", "source_title": "PFAS Removal by GAC", "tier": "GOLD", "relevance": 0.92, "perspective": "Environmental Chemist"},
        {"id": "ev_002", "statement": "Ion exchange resins outperform GAC for short-chain PFAS", "quote": "IX resins achieved 95% removal vs 40% for GAC on short-chain compounds", "source_url": "https://epa.gov/water/pfas-treatment", "source_title": "EPA PFAS Treatment Guide", "tier": "SILVER", "relevance": 0.85, "perspective": "Water Engineer"},
        {"id": "ev_003", "statement": "Regeneration costs are significant factor in GAC lifecycle", "quote": "", "source_url": "https://example.com/costs", "source_title": "Treatment Costs", "tier": "BRONZE", "relevance": 0.65, "perspective": "Public Health Expert"},
    ], "vid": "DASH_TEST_001", "ts": "2026-02-26T10:01:01Z"},
    {"type": "node_end", "node": "analyze", "duration_ms": 45000, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:01:38Z"},
    {"type": "node_start", "node": "verify", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:01:39Z"},
    {"type": "llm_call", "call_type": "verification_batch", "batch_size": 5, "supported": 4, "partial": 0, "not_supported": 1, "claims": [
        {"id": "ev_001", "verdict": "SUPPORTED", "confidence": 0.95, "faithful": True, "statement": "GAC removes over 90% of PFOS from contaminated water"},
        {"id": "ev_002", "verdict": "SUPPORTED", "confidence": 0.88, "faithful": True, "statement": "Ion exchange resins outperform GAC for short-chain PFAS"},
        {"id": "ev_003", "verdict": "NOT_SUPPORTED", "confidence": 0.3, "faithful": False, "statement": "Regeneration costs are significant factor"},
    ], "vid": "DASH_TEST_001", "ts": "2026-02-26T10:02:00Z"},
    {"type": "node_end", "node": "verify", "duration_ms": 20000, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:01:59Z"},
    {"type": "node_start", "node": "synthesize", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:02:00Z"},
    {"type": "evidence", "action": "clustering", "count": 4, "evidence_count": 45, "themes": [
        {"theme": "PFAS adsorption mechanisms", "count": 12},
        {"theme": "Treatment technology comparison", "count": 10},
        {"theme": "Cost and lifecycle analysis", "count": 8},
        {"theme": "Regulatory standards and health impacts", "count": 15},
    ], "vid": "DASH_TEST_001", "ts": "2026-02-26T10:02:05Z"},
    {"type": "llm_call", "call_type": "section_write", "section_id": "s1", "word_count": 850, "evidence_count": 8, "title": "PFAS Adsorption Mechanisms", "content": "## PFAS Adsorption Mechanisms\n\nGranular activated carbon (GAC) removes PFAS through **hydrophobic interactions** between the carbon surface and PFAS molecules [CITE:ev_001]. The removal efficiency depends on chain length, with longer-chain PFAS being more effectively adsorbed.\n\nStudies demonstrate >90% removal of PFOS at standard flow rates [CITE:ev_001], while short-chain compounds show reduced adsorption (40% vs 95% for IX resins) [CITE:ev_002].", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:02:30Z"},
    {"type": "llm_call", "call_type": "section_write", "section_id": "s2", "word_count": 620, "evidence_count": 5, "title": "Treatment Technology Comparison", "content": "## Treatment Technology Comparison\n\nMultiple treatment approaches exist for PFAS remediation, including GAC, ion exchange resins, and high-pressure membranes.", "vid": "DASH_TEST_001", "ts": "2026-02-26T10:02:45Z"},
    {"type": "evidence", "action": "citation_audit", "count": 15, "grounded": 13, "stripped": 2, "unique_sources": 5, "mapping": [
        {"num": 1, "url": "https://nature.com/articles/s12345", "title": "PFAS Removal by GAC"},
        {"num": 2, "url": "https://epa.gov/water/pfas-treatment", "title": "EPA PFAS Treatment Guide"},
        {"num": 3, "url": "https://example.com/costs", "title": "Treatment Cost Analysis"},
    ], "vid": "DASH_TEST_001", "ts": "2026-02-26T10:03:00Z"},
    {"type": "evidence", "action": "report_assembled", "count": 3200, "sections": 4, "total_citations": 15, "bibliography_entries": 5, "bibliography": [
        {"key": "nature_2025", "url": "https://nature.com/articles/s12345", "source_type": "academic", "formatted": "Chen et al. (2025) PFAS Removal by GAC. Nature Water."},
        {"key": "epa_2024", "url": "https://epa.gov/water/pfas-treatment", "source_type": "government", "formatted": "US EPA (2024) PFAS Treatment Technologies Guide."},
    ], "section_titles": [
        {"id": "s1", "title": "PFAS Adsorption Mechanisms", "words": 850},
        {"id": "s2", "title": "Treatment Technology Comparison", "words": 620},
    ], "vid": "DASH_TEST_001", "ts": "2026-02-26T10:03:05Z"},
    {"type": "quality_gate", "gate": "faithfulness", "passed": True, "actual": 0.867, "threshold": 0.80, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:03:10Z"},
    {"type": "quality_gate", "gate": "post_synthesis", "passed": True, "total_words": 3200, "total_citations": 15, "unique_sources": 5, "expansion_pass": 1, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:03:15Z"},
    {"type": "node_end", "node": "synthesize", "duration_ms": 75000, "vid": "DASH_TEST_001", "ts": "2026-02-26T10:03:15Z"},
]


def _inject_events(page, events):
    """Inject synthetic events into the dashboard via processEvent()."""
    for ev in events:
        page.evaluate(f"processEvent({json.dumps(ev)})")
    page.wait_for_timeout(500)


class TestDashboardLoads:
    """Basic page load and structure checks."""

    def test_page_loads(self, browser_page):
        page, _ = browser_page
        assert page.title() == "POLARIS Research Monitor"

    def test_no_js_errors_on_load(self, browser_page):
        page, js_errors = browser_page
        # Filter out non-critical errors (e.g., failed fetch to /api/snapshot is OK if no data)
        critical = [e for e in js_errors if "processEvent" in e or "TypeError" in e or "ReferenceError" in e or "SyntaxError" in e]
        assert len(critical) == 0, f"JS errors on load: {critical}"

    def test_slate_colors_no_green(self, browser_page):
        page, _ = browser_page
        html_source = page.content()
        assert "#10A37F" not in html_source, "Found green #10A37F in rendered page"
        assert "#10a37f" not in html_source, "Found green #10a37f in rendered page"

    def test_header_present(self, browser_page):
        page, _ = browser_page
        assert page.is_visible("#header")
        header_text = page.inner_text("#header")
        assert "POLARIS" in header_text

    def test_status_panel_present(self, browser_page):
        page, _ = browser_page
        assert page.is_visible("#status-panel")
        assert page.is_visible("#phase-stepper")

    def test_phase_bar_present(self, browser_page):
        page, _ = browser_page
        assert page.is_visible("#phase-bar")
        pills = page.query_selector_all(".phase-pill")
        assert len(pills) == 8  # 8 pipeline nodes

    def test_anomaly_bar_present(self, browser_page):
        page, _ = browser_page
        assert page.is_visible("#anomaly-bar")

    def test_all_8_tabs_exist(self, browser_page):
        page, _ = browser_page
        tabs = page.query_selector_all(".tab-btn")
        assert len(tabs) == 8
        # Tab text includes badge counts (e.g., "Queries 0"), so use startswith
        tab_names = [t.inner_text().strip().split("\n")[0].strip() for t in tabs]
        expected = ["Overview", "Queries", "Sources", "STORM", "Evidence", "Report", "Trace", "Full Report"]
        for exp in expected:
            assert any(name.startswith(exp) for name in tab_names), f"Tab '{exp}' not found in {tab_names}"


class TestTabSwitching:
    """Verify all tabs switch correctly."""

    def test_overview_tab_default(self, browser_page):
        page, _ = browser_page
        assert page.is_visible("#pane-overview")

    def test_switch_to_queries(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-queries")

    def test_switch_to_sources(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="sources"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-sources")

    def test_switch_to_storm(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="storm"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-storm")

    def test_switch_to_evidence(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-evidence")

    def test_switch_to_report(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="report"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-report")

    def test_switch_to_trace(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="trace"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-trace")

    def test_switch_back_to_overview(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(200)
        assert page.is_visible("#pane-overview")


class TestEventProcessing:
    """Inject synthetic events and verify all enriched data renders."""

    def test_inject_events_no_errors(self, browser_page):
        page, js_errors = browser_page
        js_errors.clear()
        _inject_events(page, SYNTHETIC_EVENTS)
        critical = [e for e in js_errors if "TypeError" in e or "ReferenceError" in e or "SyntaxError" in e]
        assert len(critical) == 0, f"JS errors during event injection: {critical}"

    def test_vector_id_updated(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        vid = page.inner_text("#vector-id")
        assert "DASH_TEST_001" in vid

    def test_phase_stepper_updates(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        # Plan should be "done"
        plan_step = page.query_selector("#step-plan")
        assert "done" in plan_step.get_attribute("class")

    def test_metrics_update(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        evidence_text = page.inner_text("#pm-evidence")
        assert evidence_text != "0"

    def test_faithfulness_updates(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        faith_text = page.inner_text("#pm-faith")
        assert "86.7%" in faith_text

    def test_queries_tab_populated(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(300)
        query_items = page.query_selector_all(".query-item")
        assert len(query_items) >= 2
        # Check actual query text is visible
        text = page.inner_text("#pane-queries")
        assert "PFAS" in text

    def test_sources_tab_populated(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="sources"]')
        page.wait_for_timeout(300)
        source_cards = page.query_selector_all(".source-card")
        assert len(source_cards) >= 2
        text = page.inner_text("#pane-sources")
        assert "nature.com" in text

    def test_storm_tab_shows_persona_expertise(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="storm"]')
        page.wait_for_timeout(300)
        text = page.inner_text("#pane-storm")
        assert "Environmental Chemist" in text
        # Check expertise is shown
        assert "PFAS remediation" in text or "remediation specialist" in text
        # Check Q&A is shown
        assert "What are the primary mechanisms" in text
        assert "hydrophobic interactions" in text

    def test_evidence_tab_shows_detail_cards(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(300)
        detail_cards = page.query_selector_all(".evidence-detail-card")
        assert len(detail_cards) >= 3, f"Expected 3+ evidence detail cards, got {len(detail_cards)}"
        text = page.inner_text("#pane-evidence")
        # Check actual content is shown
        assert "GAC removes over 90%" in text
        assert "GOLD" in text
        assert "nature.com" in text

    def test_evidence_tier_filter(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(300)
        # Click GOLD filter
        page.click('[data-tier="gold"]')
        page.wait_for_timeout(300)
        text = page.inner_text("#evidence-detail-list")
        assert "GOLD" in text
        # BRONZE items should be filtered out
        detail_cards = page.query_selector_all(".evidence-detail-card")
        for card in detail_cards:
            card_text = card.inner_text()
            assert "BRONZE" not in card_text
        # Reset filter
        page.click('[data-tier="all"]')

    def test_report_tab_shows_section_content(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(300)
        text = page.inner_text("#pane-report")
        # Section titles visible
        assert "PFAS Adsorption Mechanisms" in text
        assert "Treatment Technology Comparison" in text

    def test_report_tab_expandable_section(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(300)
        # Click first section row to expand
        section_rows = page.query_selector_all(".section-row")
        if len(section_rows) > 0:
            section_rows[0].click()
            page.wait_for_timeout(300)
            preview = page.query_selector("#section-preview-0")
            if preview:
                assert "open" in preview.get_attribute("class")

    def test_report_tab_shows_cluster_themes(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(300)
        themes = page.query_selector_all(".theme-chip")
        assert len(themes) >= 4
        text = page.inner_text("#report-themes")
        assert "PFAS adsorption" in text

    def test_report_tab_shows_verification_verdicts(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(300)
        verdicts = page.query_selector_all(".verdict-card")
        assert len(verdicts) >= 3
        text = page.inner_text("#report-verdicts")
        assert "supported" in text.lower() or "2/3" in text

    def test_report_tab_shows_bibliography(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(300)
        bib_entries = page.query_selector_all(".bib-entry")
        assert len(bib_entries) >= 2
        text = page.inner_text("#report-bibliography")
        assert "Chen et al" in text or "nature.com" in text

    def test_report_tab_shows_quality_gate_pass(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(300)
        text = page.inner_text("#report-gates")
        assert "PASS" in text
        # Final stats card should appear
        final = page.query_selector("#report-final")
        assert final is not None
        assert final.is_visible()

    def test_trace_tab_shows_events(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="trace"]')
        page.wait_for_timeout(300)
        trace_lines = page.query_selector_all(".trace-line, .expandable-card")
        assert len(trace_lines) >= 10
        # Section title shows in trace for llm_call
        text = page.inner_text("#trace-stream")
        assert "PFAS Adsorption" in text or "section_write" in text

    def test_trace_filter_chips(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="trace"]')
        page.wait_for_timeout(300)
        # Filter to search only
        page.click('[data-ttype="search_result"]')
        page.wait_for_timeout(300)
        text = page.inner_text("#trace-stream")
        assert "serper" in text
        # Reset
        page.click('[data-ttype="all"]')

    def test_overview_activity_log(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(300)
        activity = page.query_selector_all(".activity-item")
        assert len(activity) >= 5
        text = page.inner_text("#activity-log")
        # Should show meaningful content, not just metadata
        assert "PFAS" in text or "nature.com" in text or "Extracted" in text

    def test_gate_dots_update(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS)
        faith_gate = page.query_selector("#gate-faith")
        assert "pass" in faith_gate.get_attribute("class")


class TestColorScheme:
    """Verify slate color scheme is applied correctly."""

    def test_background_is_slate(self, browser_page):
        page, _ = browser_page
        bg_color = page.evaluate("getComputedStyle(document.body).backgroundColor")
        # #0f172a = rgb(15, 23, 42)
        assert "15" in bg_color and "23" in bg_color and "42" in bg_color, f"Body bg not slate: {bg_color}"

    def test_header_title_not_green(self, browser_page):
        page, _ = browser_page
        h1_color = page.evaluate("getComputedStyle(document.querySelector('#header h1')).color")
        # Should NOT be #10A37F = rgb(16, 163, 127)
        assert "163" not in h1_color or "127" not in h1_color, f"Header still green: {h1_color}"


# ---- Synthetic events for 100% Pipeline Visibility features ----
VISIBILITY_EVENTS = [
    # Query Plan
    {"type": "evidence", "action": "query_plan", "count": 15,
     "search_strategy": "broad_then_deep",
     "key_concepts": ["PFAS removal", "activated carbon", "water treatment", "ion exchange", "remediation"],
     "queries": [
         {"query": "PFAS removal activated carbon efficiency studies", "perspective": "Environmental Chemist", "intent": "primary mechanisms", "source_preference": "academic"},
         {"query": "ion exchange resin PFAS treatment comparison", "perspective": "Water Engineer", "intent": "technology comparison", "source_preference": "web"},
         {"query": "PFAS health effects drinking water standards", "perspective": "Public Health", "intent": "regulatory context", "source_preference": "government"},
     ],
     "perspective_distribution": {"Environmental Chemist": 5, "Water Engineer": 4, "Public Health": 3, "Regulatory": 2, "Industry": 1},
     "missing_perspectives": ["Community Advocate", "Toxicologist"],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:00:00Z"},

    # Tier Signal Distribution
    {"type": "evidence", "action": "tier_signal_distribution", "count": 200,
     "signal_stats": {
         "semantic_relevance": {"min": 0.12, "median": 0.65, "max": 0.98, "count": 200},
         "source_authority": {"min": 0.05, "median": 0.55, "max": 0.95, "count": 200},
         "content_density": {"min": 0.20, "median": 0.60, "max": 0.90, "count": 200},
         "freshness": {"min": 0.10, "median": 0.70, "max": 1.00, "count": 200},
         "nli_grounding": {"min": 0.00, "median": 0.50, "max": 0.92, "count": 180}
     },
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:01:00Z"},

    # Dedup Summary
    {"type": "evidence", "action": "dedup_summary", "count": 180,
     "pre_dedup": 200, "post_dedup": 180,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:01:30Z"},

    # Fetch Summary
    {"type": "evidence", "action": "fetch_summary", "count": 45,
     "total_attempted": 60, "success": 42, "snippet_fallback": 8, "failed": 10,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:02:00Z"},

    # NLI Verification Detail
    {"type": "evidence", "action": "nli_verification_detail", "count": 150,
     "faithful_count": 128, "faithfulness_pct": 85.3, "disputed_count": 22,
     "claims_detail": [
         {"statement": "GAC removes over 90% of PFOS from contaminated water sources", "is_faithful": True, "nli_score": 0.95},
         {"statement": "Ion exchange resins are more effective for short-chain PFAS", "is_faithful": True, "nli_score": 0.88},
         {"statement": "PFAS bioaccumulates in human tissue over decades", "is_faithful": False, "nli_score": 0.32},
         {"statement": "Reverse osmosis achieves 99% PFAS removal", "is_faithful": True, "nli_score": 0.91},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:03:00Z"},

    # Cross-Reference Groups
    {"type": "evidence", "action": "cross_reference_groups", "count": 5,
     "groups": [
         {"similarity": 0.92, "evidence_ids": ["ev_001", "ev_015", "ev_042"]},
         {"similarity": 0.87, "evidence_ids": ["ev_008", "ev_023"]},
         {"similarity": 0.83, "evidence_ids": ["ev_005", "ev_011", "ev_033", "ev_044"]},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:03:30Z"},

    # Report Outline
    {"type": "evidence", "action": "report_outline", "count": 5,
     "title": "Comprehensive Analysis of PFAS Treatment Technologies",
     "sections": [
         {"title": "PFAS Adsorption Mechanisms", "evidence_count": 12, "target_words": 800, "description": "Analysis of GAC adsorption pathways"},
         {"title": "Treatment Technology Comparison", "evidence_count": 10, "target_words": 700, "description": "Comparing GAC, IX resins, and membranes"},
         {"title": "Regulatory Standards and Health Effects", "evidence_count": 8, "target_words": 600, "description": "EPA and state-level PFAS regulations"},
         {"title": "Cost-Benefit Analysis", "evidence_count": 6, "target_words": 500, "description": "Economic analysis of treatment options"},
         {"title": "Future Research Directions", "evidence_count": 5, "target_words": 400, "description": "Emerging technologies and knowledge gaps"},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:04:00Z"},

    # Section-Evidence Map
    {"type": "evidence", "action": "section_evidence_map", "count": 5,
     "mapping": [
         {"section_id": "section_0", "evidence_count": 12},
         {"section_id": "section_1", "evidence_count": 10},
         {"section_id": "section_2", "evidence_count": 8},
         {"section_id": "section_3", "evidence_count": 6},
         {"section_id": "section_4", "evidence_count": 5},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:04:30Z"},

    # Hallucination Audit
    {"type": "evidence", "action": "hallucination_audit", "count": 5,
     "sections": [
         {"section_id": "section_0", "title": "PFAS Adsorption Mechanisms", "hallucination_ratio": 0.08, "needs_rewrite": False, "flagged_spans": 1},
         {"section_id": "section_1", "title": "Treatment Technology Comparison", "hallucination_ratio": 0.35, "needs_rewrite": False, "flagged_spans": 5},
         {"section_id": "section_2", "title": "Regulatory Standards", "hallucination_ratio": 0.52, "needs_rewrite": True, "flagged_spans": 8},
         {"section_id": "section_3", "title": "Cost-Benefit Analysis", "hallucination_ratio": 0.15, "needs_rewrite": False, "flagged_spans": 2},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:05:00Z"},

    # Evidence Conflicts
    {"type": "evidence", "action": "evidence_conflicts", "count": 2,
     "conflicts": [
         {"type": "contradiction", "score": 0.89, "statement_a": "GAC is the most cost-effective PFAS treatment", "statement_b": "Ion exchange is more economical for large-scale treatment"},
         {"type": "contradiction", "score": 0.76, "statement_a": "PFAS half-life in groundwater exceeds 100 years", "statement_b": "Natural degradation of some PFAS occurs within decades"},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:05:30Z"},

    # Expansion Pass (two passes)
    {"type": "evidence", "action": "expansion_pass", "count": 1,
     "total_words": 3200, "total_citations": 28,
     "thin_sections": ["Cost-Benefit Analysis", "Future Research"],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:06:00Z"},
    {"type": "evidence", "action": "expansion_pass", "count": 2,
     "total_words": 4800, "total_citations": 42,
     "thin_sections": [],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:06:30Z"},

    # Gap Analysis Detail
    {"type": "evidence", "action": "gap_analysis_detail", "count": 150,
     "total_evidence": 150, "gold_count": 45, "faithfulness": 0.853,
     "needs_iteration": False,
     "gaps": ["Limited data on PFAS in agricultural runoff", "No long-term GAC regeneration studies", "Insufficient cost data for emerging technologies"],
     "gap_queries": ["PFAS agricultural runoff treatment data", "GAC regeneration long-term efficacy"],
     "perspective_coverage": {"Environmental Chemist": 35, "Water Engineer": 28, "Public Health": 22, "Regulatory": 15, "Industry": 10, "Academic": 40},
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:07:00Z"},

    # Agentic Round Summary (3 rounds)
    {"type": "evidence", "action": "agentic_round_summary", "count": 1,
     "queries": 8, "web_results": 45, "academic_results": 12,
     "new_urls": 38, "total_urls": 38,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:08:00Z"},
    {"type": "evidence", "action": "agentic_round_summary", "count": 2,
     "queries": 6, "web_results": 30, "academic_results": 8,
     "new_urls": 22, "total_urls": 60,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:08:30Z"},
    {"type": "evidence", "action": "agentic_round_summary", "count": 3,
     "queries": 4, "web_results": 15, "academic_results": 5,
     "new_urls": 8, "total_urls": 68,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:09:00Z"},

    # Agentic Search Complete
    {"type": "evidence", "action": "agentic_search_complete", "count": 3,
     "total_queries": 18, "total_urls": 68,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:09:30Z"},

    # Section Evidence Filtered
    {"type": "evidence", "action": "section_evidence_filtered", "count": 12,
     "section_id": "section_0", "title": "PFAS Adsorption Mechanisms",
     "total_available": 150, "after_filter": 12,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:10:00Z"},

    # Report Assembled with full_report
    {"type": "evidence", "action": "report_assembled", "count": 4800,
     "sections": 5, "total_citations": 42, "bibliography_entries": 15,
     "full_report": "# Comprehensive Analysis of PFAS Treatment Technologies\n\n## 1. PFAS Adsorption Mechanisms\n\nGranular activated carbon (GAC) removes PFAS through **hydrophobic interactions** between the carbon surface and PFAS molecules [1]. The removal efficiency depends on chain length, with longer-chain PFAS being more effectively adsorbed.\n\n## 2. Treatment Technology Comparison\n\nMultiple treatment approaches exist for PFAS remediation, including GAC, ion exchange resins, and high-pressure membranes [2].\n\n## 3. Regulatory Standards and Health Effects\n\nThe EPA has established advisory levels for PFAS in drinking water [3].\n\n## 4. Cost-Benefit Analysis\n\nTreatment costs vary significantly by technology and scale [4].\n\n## 5. Future Research Directions\n\nEmerging technologies including electrochemical oxidation show promise [5].",
     "bibliography": [
         {"key": "nature_2025", "url": "https://nature.com/articles/s12345", "source_type": "academic", "formatted": "Chen et al. (2025) PFAS Removal by GAC. Nature Water."},
         {"key": "epa_2024", "url": "https://epa.gov/water/pfas-treatment", "source_type": "government", "formatted": "US EPA (2024) PFAS Treatment Technologies Guide."},
     ],
     "section_titles": [
         {"id": "s1", "title": "PFAS Adsorption Mechanisms", "words": 800},
         {"id": "s2", "title": "Treatment Technology Comparison", "words": 700},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:11:00Z"},

    # LLM Calls with model tracking (3 calls)
    {"type": "llm_call", "call_type": "plan", "model": "moonshotai/kimi-k2-instruct",
     "input_tokens": 2500, "output_tokens": 800, "cost_usd": 0.05,
     "prompt_excerpt": "Generate research plan for...",
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:00:01Z"},
    {"type": "llm_call", "call_type": "section_write", "section_id": "s1", "model": "moonshotai/kimi-k2-instruct",
     "input_tokens": 8000, "output_tokens": 2000, "cost_usd": 0.15,
     "title": "PFAS Adsorption Mechanisms",
     "content": "## PFAS Adsorption\n\nContent here.",
     "word_count": 800, "evidence_count": 12,
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:04:10Z"},
    {"type": "llm_call", "call_type": "verification_batch", "batch_size": 5, "model": "moonshotai/kimi-k2-instruct",
     "input_tokens": 5000, "output_tokens": 1500, "cost_usd": 0.10,
     "supported": 4, "partial": 0, "not_supported": 1,
     "claims": [
         {"id": "ev_001", "verdict": "SUPPORTED", "confidence": 0.95, "faithful": True, "statement": "GAC removes 90% of PFOS"},
     ],
     "vid": "VIS_TEST_001", "ts": "2026-02-26T12:03:10Z"},
]


# =====================================================================
# 100% Pipeline Visibility - Test Classes
# =====================================================================


class TestQueryPlanRendering:
    """Verify query plan card renders research plan details."""

    def test_research_plan_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-research-plan")
        # CSS text-transform:uppercase renders title as "RESEARCH PLAN"
        assert "research plan" in text.lower()

    def test_search_strategy_badge(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-research-plan")
        assert "broad_then_deep" in text

    def test_key_concepts_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-research-plan")
        assert "PFAS removal" in text
        assert "activated carbon" in text

    def test_perspective_bars_rendered(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-research-plan")
        assert "Environmental Chemist" in text
        assert "Water Engineer" in text
        # Check count values are rendered
        assert "5" in text
        assert "4" in text

    def test_missing_perspectives_highlighted(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-research-plan")
        assert "Community Advocate" in text
        assert "Toxicologist" in text
        assert "Missing:" in text

    def test_query_search_filter(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        # Clear any previous filter first
        page.fill("#q-search", "")
        page.wait_for_timeout(300)
        # Get full list count
        full_items = page.query_selector_all(".query-item")
        full_count = len(full_items)
        assert full_count > 0, "Query list should have items after event injection"
        # Filter with a term that exists in SYNTHETIC_EVENTS queries
        page.fill("#q-search", "activated carbon")
        page.wait_for_timeout(500)
        filtered_items = page.query_selector_all(".query-item")
        filtered_count = len(filtered_items)
        assert 0 < filtered_count <= full_count
        # The filtered list should contain the search term
        list_text = page.inner_text("#query-list")
        assert "activated carbon" in list_text.lower()
        # Restore filter
        page.fill("#q-search", "")
        page.wait_for_timeout(300)

    def test_query_search_clear(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        # Clear any previous filter first
        page.fill("#q-search", "")
        page.wait_for_timeout(300)
        # Get full list count
        full_items = page.query_selector_all(".query-item")
        full_count = len(full_items)
        assert full_count > 0, "Query list should have items"
        # Type filter, then clear
        page.fill("#q-search", "activated carbon")
        page.wait_for_timeout(500)
        page.fill("#q-search", "")
        page.wait_for_timeout(500)
        restored_items = page.query_selector_all(".query-item")
        assert len(restored_items) == full_count


class TestAgenticRounds:
    """Verify agentic search rounds card renders."""

    def test_agentic_rounds_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-agentic-rounds")
        # CSS text-transform:uppercase renders title as "AGENTIC SEARCH ROUNDS"
        assert "agentic search rounds" in text.lower()

    def test_rounds_count_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-agentic-rounds")
        # State accumulates across module-scoped tests, so check >= 3 via JS
        round_count = page.evaluate("state.agenticRounds.length")
        assert round_count >= 3
        assert "rounds" in text.lower()

    def test_total_urls_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="queries"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#q-agentic-rounds")
        assert "68 total URLs" in text


class TestFetchPipeline:
    """Verify fetch pipeline summary card renders on sources tab."""

    def test_fetch_pipeline_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="sources"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#src-fetch-pipeline")
        assert "fetch pipeline" in text.lower()

    def test_fetch_counts_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="sources"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#src-fetch-pipeline")
        assert "60" in text  # total_attempted
        assert "42" in text  # success

    def test_fetch_failed_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="sources"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#src-fetch-pipeline")
        assert "10" in text  # failed


class TestSignalDistribution:
    """Verify 5-signal distribution card renders on evidence tab."""

    def test_signal_dist_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-signal-dist")
        assert "5-signal distribution" in text.lower()

    def test_all_five_signals_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-signal-dist")
        assert "Semantic Relevance" in text
        assert "Source Authority" in text
        assert "Content Density" in text
        assert "Freshness" in text
        assert "NLI Grounding" in text

    def test_signal_values_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-signal-dist")
        # Check at least one min/median/max value appears
        assert "0.12" in text or "0.65" in text or "0.98" in text


class TestDedupPipeline:
    """Verify dedup pipeline card renders on evidence tab."""

    def test_dedup_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-dedup-pipeline")
        assert "dedup pipeline" in text.lower()

    def test_dedup_pre_count(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-dedup-pipeline")
        assert "200" in text  # pre-dedup

    def test_dedup_final_count(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-dedup-pipeline")
        assert "180" in text  # final (post-dedup)
        assert "20" in text   # removed


class TestNLIVerification:
    """Verify NLI verification detail card renders on evidence tab."""

    def test_nli_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-nli-verification")
        assert "nli verification" in text.lower()

    def test_nli_faithful_count(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-nli-verification")
        assert "128" in text
        assert "85.3%" in text

    def test_nli_disputed_count(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-nli-verification")
        assert "22" in text

    def test_nli_claims_list(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-nli-verification")
        assert "GAC removes over 90%" in text

    def test_nli_unfaithful_claim_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-nli-verification")
        assert "PFAS bioaccumulates" in text


class TestCrossReference:
    """Verify cross-reference corroboration card renders on evidence tab."""

    def test_cross_ref_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-cross-ref")
        assert "cross-reference" in text.lower()
        assert "3 groups" in text.lower()

    def test_cross_ref_similarity_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="evidence"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ev-cross-ref")
        assert "0.92" in text
        assert "ev_001" in text


class TestReportOutline:
    """Verify report outline card renders on report tab."""

    def test_outline_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-outline")
        assert "report outline" in text.lower()

    def test_outline_title_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-outline")
        # CSS text-transform:uppercase may be applied to the title section
        assert "comprehensive analysis of pfas treatment technologies" in text.lower()

    def test_outline_sections_listed(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-outline")
        assert "PFAS Adsorption Mechanisms" in text
        assert "Treatment Technology Comparison" in text
        assert "Regulatory Standards" in text
        assert "Cost-Benefit Analysis" in text
        assert "Future Research Directions" in text

    def test_outline_evidence_counts(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-outline")
        assert "12 ev" in text


class TestSectionEvidenceMap:
    """Verify section-evidence mapping card renders on report tab."""

    def test_section_evidence_map_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-section-evidence-map")
        assert "section-evidence mapping" in text.lower()

    def test_section_evidence_counts(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-section-evidence-map")
        assert "section_0" in text
        assert "12 ev" in text


class TestHallucinationAudit:
    """Verify hallucination audit card renders on report tab."""

    def test_hallucination_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-hallucination-audit")
        assert "hallucination audit" in text.lower()

    def test_hallucination_sections_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-hallucination-audit")
        assert "PFAS Adsorption Mechanisms" in text
        assert "Regulatory Standards" in text

    def test_hallucination_rewrite_badge(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-hallucination-audit")
        assert "REWRITE" in text

    def test_hallucination_percentages(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-hallucination-audit")
        assert "8%" in text
        assert "52%" in text


class TestEvidenceConflicts:
    """Verify evidence conflicts card renders on report tab."""

    def test_conflicts_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-evidence-conflicts")
        assert "evidence conflicts" in text.lower()
        assert "2" in text

    def test_conflict_statements_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-evidence-conflicts")
        assert "GAC is the most cost-effective" in text
        assert "Ion exchange is more economical" in text

    def test_conflict_score_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-evidence-conflicts")
        assert "0.89" in text


class TestExpansionHistory:
    """Verify expansion history card renders on report tab."""

    def test_expansion_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-expansion-history")
        assert "expansion history" in text.lower()

    def test_two_passes_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-expansion-history")
        assert "Pass 1" in text
        assert "Pass 2" in text

    def test_expansion_word_counts(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="report"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#rpt-expansion-history")
        # toLocaleString() formats 3200 as "3,200" on most locales
        assert "3,200" in text or "3200" in text
        assert "4,800" in text or "4800" in text


class TestGapAnalysis:
    """Verify gap analysis card renders on overview tab."""

    def test_gap_analysis_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-gap-analysis")
        assert "gap analysis" in text.lower()

    def test_gap_evidence_counts(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-gap-analysis")
        assert "150" in text  # total_evidence
        assert "45" in text   # gold_count

    def test_gap_faithfulness_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-gap-analysis")
        assert "85.3%" in text

    def test_gap_iterate_decision(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-gap-analysis")
        assert "NO" in text

    def test_gap_list_shown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-gap-analysis")
        assert "Limited data on PFAS" in text

    def test_perspective_coverage_bars(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-gap-analysis")
        assert "Environmental Chemist" in text
        assert "Academic" in text


class TestLLMUsage:
    """Verify LLM usage card renders on overview tab."""

    def test_llm_usage_card_visible(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-llm-usage")
        assert "llm usage" in text.lower()

    def test_llm_call_count(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        # SYNTHETIC_EVENTS has 4 llm_call events + VISIBILITY_EVENTS has 3 = 7 total
        # But module-scoped fixture means state accumulates; use state check
        call_count = page.evaluate("state.llmCallCount")
        assert call_count >= 3

    def test_llm_token_counts(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-llm-usage")
        # VISIBILITY_EVENTS llm_call input tokens: 2500 + 8000 + 5000 = 15500
        # Text should show some token count from the LLM usage card
        input_tokens = page.evaluate("state.llmInputTokens")
        assert input_tokens >= 15500
        output_tokens = page.evaluate("state.llmOutputTokens")
        assert output_tokens >= 4300

    def test_llm_model_distribution(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="overview"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#ov-llm-usage")
        assert "moonshotai/kimi-k2-instruct" in text
        # At least the 3 VISIBILITY calls should show
        assert "calls" in text


class TestFullReportTab:
    """Verify full report tab renders markdown content."""

    def test_fullreport_tab_switches(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="fullreport"]')
        page.wait_for_timeout(300)
        assert page.is_visible("#pane-fullreport")

    def test_fullreport_empty_state(self, browser_page):
        page, _ = browser_page
        # Reset state by reloading page then only injecting SYNTHETIC_EVENTS
        # (which have a report_assembled WITHOUT full_report)
        # Since browser_page is module-scoped and state accumulates,
        # we check the empty state by evaluating JS directly
        page.evaluate("state.fullReport = ''")
        page.evaluate("renderFullReport()")
        page.click('[data-tab="fullreport"]')
        page.wait_for_timeout(300)
        assert page.is_visible("#fullreport-empty")
        text = page.inner_text("#fullreport-empty")
        assert "not yet assembled" in text.lower()

    def test_fullreport_renders_markdown(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="fullreport"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#fullreport-content")
        assert "PFAS Adsorption Mechanisms" in text

    def test_fullreport_has_multiple_sections(self, browser_page):
        page, _ = browser_page
        _inject_events(page, SYNTHETIC_EVENTS + VISIBILITY_EVENTS)
        page.click('[data-tab="fullreport"]')
        page.wait_for_timeout(500)
        text = page.inner_text("#fullreport-content")
        # Check at least 3 section headings from the full_report markdown
        section_count = 0
        for title in ["PFAS Adsorption Mechanisms", "Treatment Technology Comparison",
                       "Regulatory Standards", "Cost-Benefit Analysis", "Future Research"]:
            if title in text:
                section_count += 1
        assert section_count >= 3, f"Found only {section_count} section headings in full report"

    def test_fullreport_export_button_exists(self, browser_page):
        page, _ = browser_page
        page.click('[data-tab="fullreport"]')
        page.wait_for_timeout(300)
        assert page.is_visible("#btn-export-report")


class TestProcessEventNoErrors:
    """Verify all visibility events process without JS errors."""

    def test_all_visibility_events_no_js_errors(self, browser_page):
        page, js_errors = browser_page
        js_errors.clear()
        _inject_events(page, VISIBILITY_EVENTS)
        critical = [e for e in js_errors if "TypeError" in e or "ReferenceError" in e or "SyntaxError" in e]
        assert len(critical) == 0, f"JS errors during visibility event injection: {critical}"
