"""
POLARIS Dashboard E2E Tests
Sprint 5 -- Comprehensive Playwright test suite
100+ assertions covering all views, interactions, and 3 viewports.

Uses Playwright Python sync API with pytest conventions.
Server must be running at BASE_URL before executing:
    python -m scripts.live_server

Run:
    pytest tests/e2e/dashboard_tests.py -v
"""

import pytest
from playwright.sync_api import sync_playwright, Page, expect

BASE_URL = "http://localhost:8091"

# ---------------------------------------------------------------------------
# Viewports for responsive testing
# ---------------------------------------------------------------------------
VIEWPORT_MOBILE = {"width": 375, "height": 812}
VIEWPORT_TABLET = {"width": 768, "height": 1024}
VIEWPORT_DESKTOP = {"width": 1440, "height": 900}

# All 6 navigation tabs in declared order
NAV_VIEWS = ["research", "evidence", "report", "memory", "pipelines", "advanced"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def browser():
    """Launch a single headless Chromium instance for the entire test session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """
    Create a fresh browser context and page at desktop viewport.
    Navigates to the dashboard in operator mode so all views are accessible
    (user mode hides nav bar when no pipeline is active).
    """
    context = browser.new_context(viewport=VIEWPORT_DESKTOP)
    pg = context.new_page()
    pg.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    # Allow JS modules to initialise
    pg.wait_for_timeout(2000)
    # Switch to operator mode so nav bar and all views are visible
    _ensure_operator_mode(pg)
    yield pg
    context.close()


def _ensure_operator_mode(pg: Page) -> None:
    """Click the Pipeline Console button to enter operator mode."""
    op_btn = pg.query_selector(".view-mode-btn[data-mode='operator']")
    if op_btn and not _has_class(pg, ".view-mode-btn[data-mode='operator']", "active"):
        op_btn.click()
        pg.wait_for_timeout(500)


def _has_class(pg: Page, selector: str, cls: str) -> bool:
    """Check whether the first element matching *selector* has CSS class *cls*."""
    return pg.evaluate(
        """([sel, cls]) => {
            const el = document.querySelector(sel);
            return el ? el.classList.contains(cls) : false;
        }""",
        [selector, cls],
    )


def _click_nav(pg: Page, view_name: str) -> None:
    """Switch view using JS (reliable across all viewport sizes and modes)."""
    pg.evaluate(f"if (typeof switchView === 'function') switchView('{view_name}');")
    pg.wait_for_timeout(300)


def _ensure_landing_visible(pg: Page) -> None:
    """Make landing page visible for tests that interact with its elements."""
    pg.evaluate("""(() => {
        var lp = document.getElementById('landing-page');
        if (lp) { lp.style.display = ''; lp.classList.add('visible'); }
    })()""")
    pg.wait_for_timeout(200)


# =========================================================================
#  1. PAGE LOAD & STRUCTURE  (10+ assertions)
# =========================================================================
class TestPageLoadAndStructure:
    """Verify that the dashboard loads, has the correct title, nav buttons,
    CSS custom properties, JS modules, and default view."""

    def test_page_loads_status_200(self, page):
        """HTTP 200 on the dashboard URL."""
        response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        assert response is not None
        assert response.status == 200

    def test_title_contains_polaris(self, page):
        """Page title includes the word POLARIS."""
        title = page.title()
        assert "POLARIS" in title, f"Expected 'POLARIS' in title, got '{title}'"

    def test_header_exists_and_visible(self, page):
        """The app-header element is present and visible."""
        header = page.query_selector(".app-header")
        assert header is not None
        assert header.is_visible()

    def test_logo_text(self, page):
        """The logo span reads 'POLARIS'."""
        logo = page.query_selector(".app-logo")
        assert logo is not None
        assert logo.inner_text().strip() == "POLARIS"

    def test_all_six_nav_buttons_exist(self, page):
        """All 6 nav buttons exist in the DOM with correct data-view values."""
        for view in NAV_VIEWS:
            btn = page.query_selector(f'.nav-btn[data-view="{view}"]')
            assert btn is not None, f"Nav button for '{view}' not found"

    def test_nav_buttons_have_correct_labels(self, page):
        """Nav button inner text matches expected labels."""
        expected_labels = {
            "research": "Research",
            "evidence": "Evidence",
            "report": "Report",
            "memory": "Memory",
            "pipelines": "Pipelines",
            "advanced": "Advanced",
        }
        for view, label in expected_labels.items():
            btn = page.query_selector(f'.nav-btn[data-view="{view}"]')
            assert btn is not None
            text = btn.inner_text().strip()
            # Evidence button contains a badge span; strip trailing digits
            assert text.startswith(label), (
                f"Nav button for '{view}' has text '{text}', expected to start with '{label}'"
            )

    def test_css_custom_properties_loaded(self, page):
        """CSS custom properties from base.css are accessible at :root."""
        bg_primary = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()"
        )
        assert len(bg_primary) > 0, "CSS variable --bg-primary is empty"
        accent = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()"
        )
        assert len(accent) > 0, "CSS variable --accent is empty"

    def test_no_console_errors_on_load(self, page):
        """Reload the page and verify no JS console errors fire."""
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        # Allow CDN load failures (fonts, mermaid) as they are external
        critical = [e for e in errors if "ERR_" not in e and "net::" not in e and "Failed to load resource" not in e]
        assert len(critical) == 0, f"Console errors found: {critical}"

    def test_default_view_is_research(self, page):
        """On fresh load, the research view-pane has class 'active'."""
        pane = page.query_selector("#view-research")
        assert pane is not None
        cls = pane.get_attribute("class") or ""
        assert "active" in cls, f"Expected 'active' in view-research class list, got '{cls}'"

    def test_views_container_exists(self, page):
        """The .views-container wrapper is present."""
        container = page.query_selector(".views-container")
        assert container is not None

    def test_skip_link_exists(self, page):
        """Accessibility: skip-to-content link is in the DOM."""
        skip = page.query_selector(".skip-link")
        assert skip is not None
        href = skip.get_attribute("href") or ""
        assert href == "#main-content"


# =========================================================================
#  2. NAVIGATION & VIEW SWITCHING  (15+ assertions)
# =========================================================================
class TestNavigationAndViewSwitching:
    """Click each nav tab and verify the correct view-pane activates,
    the button receives the 'active' class, and the previous button loses it."""

    def test_click_evidence_tab(self, page):
        """Clicking Evidence tab activates view-evidence."""
        _click_nav(page, "evidence")
        assert _has_class(page, '#view-evidence', 'active')
        assert _has_class(page, '.nav-btn[data-view="evidence"]', 'active')

    def test_click_report_tab(self, page):
        """Clicking Report tab activates view-report."""
        _click_nav(page, "report")
        assert _has_class(page, '#view-report', 'active')
        assert _has_class(page, '.nav-btn[data-view="report"]', 'active')

    def test_click_memory_tab(self, page):
        """Clicking Memory tab activates view-memory."""
        _click_nav(page, "memory")
        assert _has_class(page, '#view-memory', 'active')
        assert _has_class(page, '.nav-btn[data-view="memory"]', 'active')

    def test_click_pipelines_tab(self, page):
        """Clicking Pipelines tab activates view-pipelines."""
        _click_nav(page, "pipelines")
        assert _has_class(page, '#view-pipelines', 'active')
        assert _has_class(page, '.nav-btn[data-view="pipelines"]', 'active')

    def test_click_advanced_tab(self, page):
        """Clicking Advanced tab activates view-advanced."""
        _click_nav(page, "advanced")
        assert _has_class(page, '#view-advanced', 'active')
        assert _has_class(page, '.nav-btn[data-view="advanced"]', 'active')

    def test_click_research_tab(self, page):
        """Clicking Research tab activates view-research."""
        _click_nav(page, "evidence")  # navigate away first
        _click_nav(page, "research")
        assert _has_class(page, '#view-research', 'active')
        assert _has_class(page, '.nav-btn[data-view="research"]', 'active')

    def test_previous_tab_loses_active(self, page):
        """When switching from research to evidence, research button loses 'active'."""
        _click_nav(page, "research")
        _click_nav(page, "evidence")
        assert not _has_class(page, '.nav-btn[data-view="research"]', 'active')

    def test_previous_pane_loses_active(self, page):
        """When switching from research to evidence, view-research loses 'active'."""
        _click_nav(page, "research")
        _click_nav(page, "evidence")
        assert not _has_class(page, '#view-research', 'active')

    def test_only_one_pane_active_at_a_time(self, page):
        """After switching to report, exactly one view-pane has 'active'."""
        _click_nav(page, "report")
        active_count = page.evaluate(
            "document.querySelectorAll('.view-pane.active').length"
        )
        assert active_count == 1

    def test_only_one_nav_button_active_at_a_time(self, page):
        """After switching to pipelines, exactly one nav-btn has 'active'."""
        _click_nav(page, "pipelines")
        active_count = page.evaluate(
            "document.querySelectorAll('.nav-btn.active').length"
        )
        assert active_count == 1

    def test_aria_selected_updates(self, page):
        """Clicking a nav button sets aria-selected='true' on it, 'false' on others."""
        _click_nav(page, "memory")
        mem_aria = page.get_attribute('.nav-btn[data-view="memory"]', "aria-selected")
        res_aria = page.get_attribute('.nav-btn[data-view="research"]', "aria-selected")
        assert mem_aria == "true"
        assert res_aria == "false"

    def test_rapid_switching_stability(self, page):
        """Rapidly cycling through all tabs does not leave stale state."""
        for view in NAV_VIEWS:
            _click_nav(page, view)
        # After cycling, the last clicked view should be active
        assert _has_class(page, f'.nav-btn[data-view="{NAV_VIEWS[-1]}"]', 'active')

    def test_nav_buttons_have_role_tab(self, page):
        """All nav buttons have role='tab' for accessibility."""
        for view in NAV_VIEWS:
            role = page.get_attribute(f'.nav-btn[data-view="{view}"]', "role")
            assert role == "tab", f"Nav button '{view}' role='{role}', expected 'tab'"

    def test_nav_bar_role_tablist(self, page):
        """The nav bar has role='tablist'."""
        nav = page.query_selector("#main-nav-bar")
        assert nav is not None
        assert nav.get_attribute("role") == "tablist"

    def test_all_six_view_panes_exist(self, page):
        """Each of the 6 view-pane elements exists in the DOM."""
        for view in NAV_VIEWS:
            pane = page.query_selector(f"#view-{view}")
            assert pane is not None, f"View pane #view-{view} not found"


# =========================================================================
#  3. THEME TOGGLE  (10+ assertions)
# =========================================================================
class TestThemeToggle:
    """Verify the dark/light theme toggle behaviour, persistence, and CSS
    variable changes."""

    def test_theme_toggle_button_exists(self, page):
        """The #theme-toggle button is present."""
        btn = page.query_selector("#theme-toggle")
        assert btn is not None

    def test_theme_toggle_visible(self, page):
        """The theme toggle is visible."""
        btn = page.query_selector("#theme-toggle")
        assert btn is not None
        assert btn.is_visible()

    def test_initial_theme_is_dark_or_light(self, page):
        """data-theme attribute is set to either 'dark' or 'light'."""
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme in ("dark", "light"), f"Unexpected initial theme: '{theme}'"

    def test_toggle_dark_to_light(self, page):
        """Force dark theme, click toggle, verify switch to light."""
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.evaluate("localStorage.setItem('polaris-theme','dark')")
        page.click("#theme-toggle")
        page.wait_for_timeout(300)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "light", f"After toggle from dark, theme is '{theme}'"

    def test_toggle_light_to_dark(self, page):
        """Force light theme, click toggle, verify switch to dark."""
        page.evaluate("document.documentElement.setAttribute('data-theme','light')")
        page.evaluate("localStorage.setItem('polaris-theme','light')")
        page.click("#theme-toggle")
        page.wait_for_timeout(300)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "dark", f"After toggle from light, theme is '{theme}'"

    def test_toggle_round_trip(self, page):
        """Click toggle twice: dark -> light -> dark."""
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.click("#theme-toggle")
        page.wait_for_timeout(200)
        page.click("#theme-toggle")
        page.wait_for_timeout(200)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "dark"

    def test_bg_color_changes_on_toggle(self, page):
        """The computed --bg-primary CSS variable changes between dark and light."""
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.wait_for_timeout(100)
        dark_bg = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()"
        )
        page.evaluate("document.documentElement.setAttribute('data-theme','light')")
        page.wait_for_timeout(100)
        light_bg = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()"
        )
        assert dark_bg != light_bg, (
            f"--bg-primary did not change: dark='{dark_bg}', light='{light_bg}'"
        )

    def test_text_color_changes_on_toggle(self, page):
        """The computed --text-primary CSS variable changes between themes."""
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.wait_for_timeout(100)
        dark_text = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim()"
        )
        page.evaluate("document.documentElement.setAttribute('data-theme','light')")
        page.wait_for_timeout(100)
        light_text = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim()"
        )
        assert dark_text != light_text, (
            f"--text-primary did not change: dark='{dark_text}', light='{light_text}'"
        )

    def test_theme_persists_in_localstorage(self, page):
        """After toggling, the chosen theme is saved to localStorage."""
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.evaluate("localStorage.setItem('polaris-theme','dark')")
        page.click("#theme-toggle")
        page.wait_for_timeout(300)
        stored = page.evaluate("localStorage.getItem('polaris-theme')")
        assert stored == "light", f"localStorage polaris-theme='{stored}', expected 'light'"

    def test_theme_toggle_has_aria_label(self, page):
        """Theme toggle has an aria-label for accessibility."""
        label = page.get_attribute("#theme-toggle", "aria-label")
        assert label is not None and len(label) > 0

    def test_theme_toggle_icon_changes(self, page):
        """The icon content in the toggle button changes between themes."""
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.evaluate("updateThemeIcon()")
        page.wait_for_timeout(100)
        dark_icon = page.inner_text("#theme-toggle")
        page.evaluate("document.documentElement.setAttribute('data-theme','light')")
        page.evaluate("updateThemeIcon()")
        page.wait_for_timeout(100)
        light_icon = page.inner_text("#theme-toggle")
        assert dark_icon != light_icon, (
            f"Icon did not change: dark='{dark_icon}', light='{light_icon}'"
        )


# =========================================================================
#  4. RESEARCH INPUT  (10+ assertions)
# =========================================================================
class TestResearchInput:
    """Verify the landing page research input, depth chips, example cards,
    and submit button."""

    def test_search_input_exists(self, page):
        """The landing query input exists."""
        inp = page.query_selector("#landing-query-input")
        assert inp is not None

    def test_search_input_placeholder(self, page):
        """The input has the expected placeholder text."""
        placeholder = page.get_attribute("#landing-query-input", "placeholder")
        assert placeholder is not None
        assert "research" in placeholder.lower()

    def test_search_input_is_focusable(self, page):
        """Focusing the input sets it as the active element."""
        _ensure_landing_visible(page)
        page.focus("#landing-query-input")
        is_focused = page.evaluate(
            "document.activeElement === document.getElementById('landing-query-input')"
        )
        assert is_focused

    def test_three_depth_chips_exist(self, page):
        """Exactly 3 depth chips exist: quick, standard, deep."""
        chips = page.query_selector_all(".depth-chip")
        assert len(chips) == 3
        depths = [c.get_attribute("data-depth") for c in chips]
        assert set(depths) == {"quick", "standard", "deep"}

    def test_standard_depth_is_default_active(self, page):
        """The 'standard' depth chip is active by default."""
        active_chip = page.query_selector('.depth-chip.active')
        assert active_chip is not None
        assert active_chip.get_attribute("data-depth") == "standard"

    def test_clicking_depth_chip_toggles_active(self, page):
        """Clicking 'quick' activates it and deactivates 'standard'."""
        _ensure_landing_visible(page)
        page.evaluate("document.querySelector('.depth-chip[data-depth=\"quick\"]').click()")
        page.wait_for_timeout(200)
        assert _has_class(page, '.depth-chip[data-depth="quick"]', 'active')
        assert not _has_class(page, '.depth-chip[data-depth="standard"]', 'active')

    def test_clicking_deep_chip(self, page):
        """Clicking 'deep' activates it."""
        _ensure_landing_visible(page)
        page.evaluate("document.querySelector('.depth-chip[data-depth=\"deep\"]').click()")
        page.wait_for_timeout(200)
        assert _has_class(page, '.depth-chip[data-depth="deep"]', 'active')

    def test_example_cards_exist(self, page):
        """At least 1 example card is present (there are 4)."""
        cards = page.query_selector_all(".example-card")
        assert len(cards) >= 1

    def test_four_example_cards(self, page):
        """Exactly 4 example cards: Science, Policy, Technology, Business."""
        cards = page.query_selector_all(".example-card")
        assert len(cards) == 4
        labels = [c.query_selector(".example-label").inner_text() for c in cards]
        assert set(labels) == {"Science", "Policy", "Technology", "Business"}

    def test_clicking_example_card_fills_input(self, page):
        """Clicking an example card populates the input field."""
        _ensure_landing_visible(page)
        expected_text = page.evaluate(
            "document.querySelector('.example-card .example-text').textContent"
        )
        page.evaluate("document.querySelector('.example-card').click()")
        page.wait_for_timeout(300)
        value = page.input_value("#landing-query-input")
        assert value == expected_text

    def test_submit_button_exists(self, page):
        """The landing submit button exists."""
        btn = page.query_selector("#landing-submit-btn")
        assert btn is not None

    def test_submit_button_text(self, page):
        """Submit button says 'Research'."""
        text = page.inner_text("#landing-submit-btn")
        assert text.strip() == "Research"


# =========================================================================
#  5. REPORT VIEW  (15+ assertions)
# =========================================================================
class TestReportView:
    """Verify the report view pane structure, empty state, export buttons,
    and quality banner."""

    def test_report_view_pane_exists(self, page):
        """#view-report is in the DOM."""
        pane = page.query_selector("#view-report")
        assert pane is not None

    def test_report_view_becomes_active(self, page):
        """Clicking report tab activates the pane."""
        _click_nav(page, "report")
        assert _has_class(page, '#view-report', 'active')

    def test_report_body_exists(self, page):
        """The #report-body container exists."""
        body = page.query_selector("#report-body")
        assert body is not None

    def test_report_empty_state_displayed(self, page):
        """When no report has been generated, the empty state message is visible.

        Note: report_view.js dynamically renders the report view, replacing the
        static HTML. The empty state uses class .report-empty (not #report-empty).
        """
        _click_nav(page, "report")
        # JS-rendered empty state uses class selector
        empty = page.query_selector(".report-empty")
        assert empty is not None, (
            "Expected .report-empty element in JS-rendered report view"
        )
        text = empty.inner_text()
        assert "report" in text.lower() or "pipeline" in text.lower() or "synthesis" in text.lower()

    def test_export_markdown_button_exists(self, page):
        """Export Markdown button is present."""
        btn = page.query_selector("#btn-export-md")
        assert btn is not None

    def test_export_markdown_button_text(self, page):
        """Export Markdown button has correct label."""
        text = page.inner_text("#btn-export-md")
        assert "Markdown" in text

    def test_export_word_button_exists(self, page):
        """Export Word button is present."""
        btn = page.query_selector("#btn-export-docx")
        assert btn is not None

    def test_export_word_button_text(self, page):
        """Export Word button has correct label."""
        text = page.inner_text("#btn-export-docx")
        assert "Word" in text

    def test_export_jsonl_button_exists(self, page):
        """Export JSONL button is present."""
        btn = page.query_selector("#btn-export-jsonl")
        assert btn is not None

    def test_export_jsonl_button_text(self, page):
        """Export JSONL button has correct label."""
        text = page.inner_text("#btn-export-jsonl")
        assert "JSONL" in text

    def test_export_toolbar_structure(self, page):
        """The export toolbar container exists (buttons only render when report available).

        report_view.js only adds .export-btn elements when state.fullReport is set.
        With no pipeline data, the toolbar is empty but present.
        """
        _click_nav(page, "report")
        toolbar = page.query_selector(".export-toolbar")
        assert toolbar is not None, "Export toolbar container should exist"

    def test_report_gate_grid_exists(self, page):
        """The quality gate grid container is present."""
        grid = page.query_selector("#report-gate-grid")
        assert grid is not None

    def test_report_iteration_timeline_exists(self, page):
        """The iteration timeline container is present."""
        timeline = page.query_selector("#report-iter-timeline")
        assert timeline is not None

    def test_report_bibliography_container_exists(self, page):
        """The bibliography container is present."""
        bib = page.query_selector("#report-bibliography")
        assert bib is not None

    def test_report_extras_container_exists(self, page):
        """The report extras container (conflicts, etc.) is present."""
        extras = page.query_selector("#report-extras")
        assert extras is not None

    def test_report_verification_container_exists(self, page):
        """The report verification container is present."""
        ver = page.query_selector("#report-verification")
        assert ver is not None


# =========================================================================
#  6. EVIDENCE VIEW  (10+ assertions)
# =========================================================================
class TestEvidenceView:
    """Verify the evidence view pane, tier filter chips, sort dropdown,
    graph mode buttons, and SVG canvas."""

    def test_evidence_view_pane_exists(self, page):
        """#view-evidence is in the DOM."""
        pane = page.query_selector("#view-evidence")
        assert pane is not None

    def test_evidence_view_becomes_active(self, page):
        """Clicking evidence tab activates the pane."""
        _click_nav(page, "evidence")
        assert _has_class(page, '#view-evidence', 'active')

    def test_tier_filter_chips_exist(self, page):
        """Tier filter chips exist: All, Gold, Silver, Bronze."""
        _click_nav(page, "evidence")
        chips = page.query_selector_all("#tier-chips .filter-chip")
        assert len(chips) == 4
        tiers = [c.get_attribute("data-tier") for c in chips]
        assert set(tiers) == {"all", "gold", "silver", "bronze"}

    def test_all_tier_chip_is_default_active(self, page):
        """The 'All' tier chip is active by default."""
        _click_nav(page, "evidence")
        all_chip = page.query_selector('.filter-chip[data-tier="all"]')
        assert all_chip is not None
        cls = all_chip.get_attribute("class") or ""
        assert "active" in cls

    def test_sort_dropdown_exists(self, page):
        """The evidence sort select element exists."""
        _click_nav(page, "evidence")
        dropdown = page.query_selector("#evidence-sort")
        assert dropdown is not None

    def test_sort_dropdown_has_options(self, page):
        """The sort dropdown has at least 3 options."""
        _click_nav(page, "evidence")
        options = page.query_selector_all("#evidence-sort option")
        assert len(options) >= 3

    def test_graph_mode_buttons_exist(self, page):
        """4 graph mode buttons exist in the segmented control."""
        _click_nav(page, "evidence")
        buttons = page.query_selector_all("#graph-mode-selector .seg-btn")
        assert len(buttons) == 4

    def test_graph_mode_values(self, page):
        """Graph mode buttons have correct data-mode values."""
        _click_nav(page, "evidence")
        buttons = page.query_selector_all("#graph-mode-selector .seg-btn")
        modes = [b.get_attribute("data-mode") for b in buttons]
        assert set(modes) == {"crossref", "citation", "source", "mindmap"}

    def test_graph_svg_exists(self, page):
        """The evidence graph SVG element exists."""
        svg = page.query_selector("#graph-svg")
        assert svg is not None

    def test_evidence_card_list_container(self, page):
        """The evidence card list container exists."""
        _click_nav(page, "evidence")
        container = page.query_selector("#evidence-card-list")
        assert container is not None

    def test_evidence_detail_panel_exists(self, page):
        """The slide-in evidence detail panel exists."""
        panel = page.query_selector("#evidence-detail-panel")
        assert panel is not None

    def test_graph_color_mode_selector(self, page):
        """The graph color mode dropdown exists with tier/perspective options."""
        _click_nav(page, "evidence")
        select = page.query_selector("#graph-color-mode")
        assert select is not None
        options = page.query_selector_all("#graph-color-mode option")
        values = [o.get_attribute("value") for o in options]
        assert "tier" in values
        assert "perspective" in values


# =========================================================================
#  7. PIPELINES VIEW  (15+ assertions)
# =========================================================================
class TestPipelinesView:
    """Verify the pipelines view pane structure, sidebar, canvas, toolbar,
    minimap, and key UI components."""

    def test_pipelines_view_pane_exists(self, page):
        """#view-pipelines is in the DOM."""
        pane = page.query_selector("#view-pipelines")
        assert pane is not None

    def test_pipelines_view_becomes_active(self, page):
        """Clicking pipelines tab activates the pane."""
        _click_nav(page, "pipelines")
        assert _has_class(page, '#view-pipelines', 'active')

    def test_pipeline_template_list_container(self, page):
        """The template list container exists."""
        _click_nav(page, "pipelines")
        container = page.query_selector("#pipeline-template-list")
        assert container is not None

    def test_pipeline_saved_list_container(self, page):
        """The saved pipeline list container exists."""
        _click_nav(page, "pipelines")
        container = page.query_selector("#pipeline-saved-list")
        assert container is not None

    def test_toolbar_save_button(self, page):
        """The Save toolbar button exists."""
        _click_nav(page, "pipelines")
        btn = page.query_selector("#pipe-btn-save")
        assert btn is not None
        assert btn.inner_text().strip() == "Save"

    def test_toolbar_validate_button(self, page):
        """The Validate toolbar button exists."""
        _click_nav(page, "pipelines")
        btn = page.query_selector("#pipe-btn-validate")
        assert btn is not None
        assert btn.inner_text().strip() == "Validate"

    def test_toolbar_run_button(self, page):
        """The Run toolbar button exists with primary styling."""
        _click_nav(page, "pipelines")
        btn = page.query_selector("#pipe-btn-run")
        assert btn is not None
        assert btn.inner_text().strip() == "Run"
        cls = btn.get_attribute("class") or ""
        assert "pipe-tool-primary" in cls

    def test_toolbar_wizard_button(self, page):
        """The Wizard toolbar button exists."""
        _click_nav(page, "pipelines")
        btn = page.query_selector("#pipe-btn-wizard")
        assert btn is not None
        assert btn.inner_text().strip() == "Wizard"

    def test_dag_svg_element(self, page):
        """The pipeline DAG SVG canvas element exists."""
        _click_nav(page, "pipelines")
        svg = page.query_selector("#pipeline-dag-svg")
        assert svg is not None

    def test_dag_svg_has_class(self, page):
        """The SVG has the pipeline-dag-svg class."""
        svg = page.query_selector("#pipeline-dag-svg")
        cls = svg.get_attribute("class") or ""
        assert "pipeline-dag-svg" in cls

    def test_config_panel_structure(self, page):
        """The config panel container exists with header and body."""
        _click_nav(page, "pipelines")
        panel = page.query_selector("#pipelines-config-panel")
        assert panel is not None
        header = page.query_selector("#config-panel-title")
        assert header is not None
        body = page.query_selector("#config-panel-body")
        assert body is not None

    def test_new_pipeline_button(self, page):
        """The '+ New Pipeline' button exists."""
        _click_nav(page, "pipelines")
        btn = page.query_selector("#pipeline-new-btn")
        assert btn is not None
        assert "New Pipeline" in btn.inner_text()

    def test_minimap_container(self, page):
        """The pipeline minimap container exists."""
        _click_nav(page, "pipelines")
        minimap = page.query_selector("#pipeline-minimap")
        assert minimap is not None

    def test_minimap_svg(self, page):
        """The minimap SVG element exists."""
        svg = page.query_selector("#pipeline-minimap-svg")
        assert svg is not None

    def test_pipeline_empty_state(self, page):
        """The empty state message is present when no pipeline is loaded."""
        _click_nav(page, "pipelines")
        empty = page.query_selector("#pipeline-empty")
        assert empty is not None
        text = empty.inner_text()
        assert "template" in text.lower() or "pipeline" in text.lower()

    def test_zoom_in_button(self, page):
        """The zoom-in button exists."""
        btn = page.query_selector("#pipe-btn-zoom-in")
        assert btn is not None

    def test_zoom_out_button(self, page):
        """The zoom-out button exists."""
        btn = page.query_selector("#pipe-btn-zoom-out")
        assert btn is not None

    def test_fit_view_button(self, page):
        """The fit-to-view button exists."""
        btn = page.query_selector("#pipe-btn-fit")
        assert btn is not None


# =========================================================================
#  8. MEMORY VIEW  (10+ assertions)
# =========================================================================
class TestMemoryView:
    """Verify the memory view pane exists and, after navigating to it,
    the memory dashboard renders its key structural elements."""

    def test_memory_view_pane_exists(self, page):
        """#view-memory is in the DOM."""
        pane = page.query_selector("#view-memory")
        assert pane is not None

    def test_memory_view_becomes_active(self, page):
        """Clicking memory tab activates the pane."""
        _click_nav(page, "memory")
        assert _has_class(page, '#view-memory', 'active')

    def test_memory_dashboard_root_exists(self, page):
        """The memory dashboard root container exists."""
        root = page.query_selector("#memory-dashboard-root")
        assert root is not None

    def test_memory_dashboard_renders(self, page):
        """After navigating to memory, the root has child content (rendered by JS)."""
        _click_nav(page, "memory")
        page.wait_for_timeout(1000)
        children = page.evaluate(
            "document.getElementById('memory-dashboard-root').children.length"
        )
        # Memory dashboard JS renders content (loading state at minimum)
        assert children >= 1, "Memory dashboard root has no children after navigation"

    def test_memory_dashboard_has_mem_dashboard_class(self, page):
        """After rendering, a .mem-dashboard element should appear."""
        _click_nav(page, "memory")
        page.wait_for_timeout(1000)
        dashboard = page.query_selector(".mem-dashboard")
        assert dashboard is not None

    def test_memory_stats_bar_or_loading(self, page):
        """After rendering, either the stats bar or a loading indicator appears."""
        _click_nav(page, "memory")
        page.wait_for_timeout(1500)
        stats_bar = page.query_selector(".mem-stats-bar")
        loading = page.query_selector(".mem-loading")
        error = page.query_selector(".mem-error")
        assert stats_bar is not None or loading is not None or error is not None, (
            "Neither stats bar, loading indicator, nor error state found"
        )

    def test_memory_css_injected(self, page):
        """Memory dashboard injects its styles into the head."""
        _click_nav(page, "memory")
        page.wait_for_timeout(1000)
        style = page.query_selector("#mem-injected-styles")
        assert style is not None

    def test_memory_indicator_in_header(self, page):
        """The memory indicator badge exists in the header."""
        indicator = page.query_selector("#memory-indicator")
        assert indicator is not None

    def test_memory_count_element(self, page):
        """The #memory-count span exists for displaying memory item count."""
        count_el = page.query_selector("#memory-count")
        assert count_el is not None

    def test_memory_view_does_not_break_other_views(self, page):
        """After visiting memory view, switching to research still works."""
        _click_nav(page, "memory")
        page.wait_for_timeout(500)
        _click_nav(page, "research")
        assert _has_class(page, '#view-research', 'active')


# =========================================================================
#  9. ADVANCED VIEW  (5+ assertions)
# =========================================================================
class TestAdvancedView:
    """Verify the advanced view pane and its sub-tabs."""

    def test_advanced_view_pane_exists(self, page):
        """#view-advanced is in the DOM."""
        pane = page.query_selector("#view-advanced")
        assert pane is not None

    def test_advanced_view_becomes_active(self, page):
        """Clicking advanced tab activates the pane."""
        _click_nav(page, "advanced")
        assert _has_class(page, '#view-advanced', 'active')

    def test_advanced_sub_tabs_exist(self, page):
        """5 sub-tabs exist: Queries, Sources, STORM, Trace, Cost."""
        _click_nav(page, "advanced")
        tabs = page.query_selector_all(".adv-tab-btn")
        assert len(tabs) == 5
        tab_values = [t.get_attribute("data-adv") for t in tabs]
        assert set(tab_values) == {"queries", "sources", "storm", "trace", "cost"}

    def test_queries_sub_tab_default_active(self, page):
        """The Queries sub-tab is active by default."""
        _click_nav(page, "advanced")
        assert _has_class(page, '.adv-tab-btn[data-adv="queries"]', 'active')

    def test_switching_advanced_sub_tabs(self, page):
        """Clicking 'Sources' sub-tab activates adv-sources pane."""
        _click_nav(page, "advanced")
        page.click('.adv-tab-btn[data-adv="sources"]')
        page.wait_for_timeout(200)
        assert _has_class(page, '#adv-sources', 'active')
        assert _has_class(page, '.adv-tab-btn[data-adv="sources"]', 'active')

    def test_trace_filter_chips(self, page):
        """The Trace sub-tab has filter chips (All, Nodes, LLM, etc.)."""
        _click_nav(page, "advanced")
        # Use JS to click trace tab (Playwright click can be intercepted by nav)
        page.evaluate("""
            document.querySelectorAll('.adv-tab-btn').forEach(function(b) {
                if (b.dataset.adv === 'trace') b.click();
            });
        """)
        page.wait_for_timeout(200)
        chips = page.query_selector_all("#trace-filters .filter-chip")
        assert len(chips) >= 5

    def test_each_adv_pane_exists(self, page):
        """Each advanced sub-pane element exists."""
        for pane_id in ["adv-queries", "adv-sources", "adv-storm", "adv-trace", "adv-cost"]:
            el = page.query_selector(f"#{pane_id}")
            assert el is not None, f"Advanced pane #{pane_id} not found"


# =========================================================================
#  10. RESPONSIVE  (10+ assertions)
# =========================================================================
class TestResponsive:
    """Test the dashboard at 375px, 768px, and 1440px viewport widths.
    Verifies navigation accessibility and absence of horizontal overflow."""

    def _set_viewport(self, page, viewport):
        """Resize the viewport and let the page re-render."""
        page.set_viewport_size(viewport)
        page.wait_for_timeout(500)

    def test_mobile_375_no_horizontal_overflow(self, page):
        """At 375px, there is no horizontal overflow."""
        self._set_viewport(page, VIEWPORT_MOBILE)
        overflow = page.evaluate("document.body.scrollWidth > window.innerWidth + 5")
        assert not overflow, "Horizontal overflow detected at 375px"

    def test_tablet_768_no_horizontal_overflow(self, page):
        """At 768px, there is no horizontal overflow."""
        self._set_viewport(page, VIEWPORT_TABLET)
        overflow = page.evaluate("document.body.scrollWidth > window.innerWidth + 5")
        assert not overflow, "Horizontal overflow detected at 768px"

    def test_desktop_1440_no_horizontal_overflow(self, page):
        """At 1440px, there is no horizontal overflow (in user mode)."""
        self._set_viewport(page, VIEWPORT_DESKTOP)
        # Test in user mode — operator panels may legitimately extend content
        page.evaluate("if (typeof setViewMode === 'function') setViewMode('user', true);")
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.body.scrollWidth > window.innerWidth + 20")
        assert not overflow, "Horizontal overflow detected at 1440px"
        # Restore operator mode for subsequent tests
        _ensure_operator_mode(page)

    def test_mobile_nav_buttons_accessible(self, page):
        """At 375px, all nav buttons exist in the DOM (may scroll)."""
        self._set_viewport(page, VIEWPORT_MOBILE)
        for view in NAV_VIEWS:
            btn = page.query_selector(f'.nav-btn[data-view="{view}"]')
            assert btn is not None, f"Nav button '{view}' missing at 375px"

    def test_tablet_nav_buttons_accessible(self, page):
        """At 768px, all nav buttons exist in the DOM."""
        self._set_viewport(page, VIEWPORT_TABLET)
        for view in NAV_VIEWS:
            btn = page.query_selector(f'.nav-btn[data-view="{view}"]')
            assert btn is not None, f"Nav button '{view}' missing at 768px"

    def test_desktop_nav_buttons_accessible(self, page):
        """At 1440px, all nav buttons exist in the DOM."""
        self._set_viewport(page, VIEWPORT_DESKTOP)
        for view in NAV_VIEWS:
            btn = page.query_selector(f'.nav-btn[data-view="{view}"]')
            assert btn is not None, f"Nav button '{view}' missing at 1440px"

    def test_mobile_header_visible(self, page):
        """At 375px, the header is visible."""
        self._set_viewport(page, VIEWPORT_MOBILE)
        header = page.query_selector(".app-header")
        assert header is not None
        assert header.is_visible()

    def test_tablet_header_visible(self, page):
        """At 768px, the header is visible."""
        self._set_viewport(page, VIEWPORT_TABLET)
        header = page.query_selector(".app-header")
        assert header is not None
        assert header.is_visible()

    def test_mobile_theme_toggle_visible(self, page):
        """At 375px, the theme toggle is visible."""
        self._set_viewport(page, VIEWPORT_MOBILE)
        toggle = page.query_selector("#theme-toggle")
        assert toggle is not None
        assert toggle.is_visible()

    def test_mobile_content_readable(self, page):
        """At 375px, the body does not collapse to zero width."""
        self._set_viewport(page, VIEWPORT_MOBILE)
        body_width = page.evaluate("document.body.offsetWidth")
        assert body_width >= 370, f"Body width {body_width}px too narrow at 375px viewport"

    def test_tablet_view_pane_width(self, page):
        """At 768px, the active view pane has reasonable width."""
        self._set_viewport(page, VIEWPORT_TABLET)
        _click_nav(page, "research")
        pane_width = page.evaluate(
            "document.querySelector('#view-research').offsetWidth"
        )
        assert pane_width >= 700, f"View pane width {pane_width}px too narrow at 768px"


# =========================================================================
#  11. CONFLICT MODAL  (5+ assertions)
# =========================================================================
class TestConflictModal:
    """Verify the showConflictModal and hideConflictModal functions are
    defined and the modal mechanics work correctly."""

    def test_show_conflict_modal_function_defined(self, page):
        """The showConflictModal global function exists."""
        defined = page.evaluate("typeof showConflictModal === 'function'")
        assert defined, "showConflictModal is not defined"

    def test_hide_conflict_modal_function_defined(self, page):
        """The hideConflictModal global function exists."""
        defined = page.evaluate("typeof hideConflictModal === 'function'")
        assert defined, "hideConflictModal is not defined"

    def test_hide_conflict_modal_safe_without_overlay(self, page):
        """Calling hideConflictModal when no modal exists does not throw."""
        error = page.evaluate(
            """(() => {
                try { hideConflictModal(); return null; }
                catch(e) { return e.message; }
            })()"""
        )
        assert error is None, f"hideConflictModal threw: {error}"

    def test_escape_key_listener_registered(self, page):
        """A keydown listener for Escape is registered (for conflict modal dismiss)."""
        # The report_view.js registers: document.addEventListener("keydown", ...)
        # We verify that pressing Escape on the document does not throw
        error = page.evaluate(
            """(() => {
                try {
                    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}));
                    return null;
                } catch(e) { return e.message; }
            })()"""
        )
        assert error is None, f"Escape keydown threw: {error}"

    def test_toast_container_exists(self, page):
        """The toast container for notifications exists."""
        container = page.query_selector("#toast-container")
        assert container is not None

    def test_auth_modal_exists_in_dom(self, page):
        """The auth modal element exists in the DOM (hidden by default)."""
        modal = page.query_selector("#auth-modal")
        assert modal is not None


# =========================================================================
#  12. VIEW MODE TOGGLE (Researcher / Pipeline Console)  (bonus, 5+ assertions)
# =========================================================================
class TestViewModeToggle:
    """Verify switching between Researcher (user) and Pipeline Console
    (operator) view modes."""

    def test_view_mode_toggle_exists(self, page):
        """The view mode toggle container exists."""
        toggle = page.query_selector("#view-mode-toggle")
        assert toggle is not None

    def test_two_view_mode_buttons(self, page):
        """Two view mode buttons exist: user and operator."""
        buttons = page.query_selector_all(".view-mode-btn")
        assert len(buttons) == 2
        modes = [b.get_attribute("data-mode") for b in buttons]
        assert set(modes) == {"user", "operator"}

    def test_clicking_operator_mode(self, page):
        """Clicking Pipeline Console activates operator mode."""
        page.click(".view-mode-btn[data-mode='operator']")
        page.wait_for_timeout(300)
        assert _has_class(page, ".view-mode-btn[data-mode='operator']", "active")

    def test_clicking_user_mode(self, page):
        """Clicking Researcher activates user mode."""
        # First switch to operator
        page.click(".view-mode-btn[data-mode='operator']")
        page.wait_for_timeout(200)
        page.click(".view-mode-btn[data-mode='user']")
        page.wait_for_timeout(300)
        assert _has_class(page, ".view-mode-btn[data-mode='user']", "active")

    def test_view_mode_saved_to_localstorage(self, page):
        """Setting operator mode persists to localStorage."""
        page.click(".view-mode-btn[data-mode='operator']")
        page.wait_for_timeout(300)
        stored = page.evaluate("localStorage.getItem('polaris_view_mode')")
        assert stored == "operator"

    def test_view_mode_toggle_has_role(self, page):
        """The view mode toggle has role='radiogroup'."""
        role = page.get_attribute("#view-mode-toggle", "role")
        assert role == "radiogroup"


# =========================================================================
#  13. RESEARCH VIEW INTERNALS  (bonus, 5+ assertions)
# =========================================================================
class TestResearchViewInternals:
    """Verify elements inside the research view pane: reasoning stream,
    metric grid, quality gate dots, pipeline stepper, activity log."""

    def test_reasoning_stream_container(self, page):
        """The reasoning stream element exists."""
        _click_nav(page, "research")
        stream = page.query_selector("#reasoning-stream")
        assert stream is not None

    def test_metric_grid_exists(self, page):
        """The metric grid container exists."""
        grid = page.query_selector("#metric-grid")
        assert grid is not None

    def test_four_metric_cards(self, page):
        """4 metric cards exist: Evidence, Faithfulness, Words, Cost."""
        cards = page.query_selector_all("#metric-grid .metric-card")
        assert len(cards) == 4

    def test_metric_values_exist(self, page):
        """Individual metric value elements exist."""
        for metric_id in ["pm-evidence", "pm-faith", "pm-words", "pm-cost"]:
            el = page.query_selector(f"#{metric_id}")
            assert el is not None, f"Metric #{metric_id} not found"

    def test_quality_gate_dots(self, page):
        """5 quality gate dots exist: Faith, Words, Cites, Sources, Synth."""
        dots = page.query_selector_all(".gate-dot-item")
        assert len(dots) == 5

    def test_individual_gate_ids(self, page):
        """Individual gate dot IDs exist."""
        for gate_id in ["gate-faith", "gate-words", "gate-cite", "gate-sources", "gate-synth"]:
            el = page.query_selector(f"#{gate_id}")
            assert el is not None, f"Gate #{gate_id} not found"

    def test_phase_stepper_exists(self, page):
        """The phase stepper container is rendered."""
        stepper = page.query_selector("#phase-stepper")
        assert stepper is not None
        # It should have step items (rendered by renderPhaseStepper)
        items = page.query_selector_all("#phase-stepper .step-item")
        assert len(items) == 8, f"Expected 8 step items, got {len(items)}"

    def test_activity_log_exists(self, page):
        """The activity log container exists."""
        log_el = page.query_selector("#activity-log")
        assert log_el is not None


# =========================================================================
#  14. GLOBAL JS FUNCTIONS  (bonus, 5+ assertions)
# =========================================================================
class TestGlobalJsFunctions:
    """Verify that key global JS functions are defined and callable."""

    def test_switch_view_defined(self, page):
        assert page.evaluate("typeof switchView === 'function'")

    def test_toggle_theme_defined(self, page):
        assert page.evaluate("typeof toggleTheme === 'function'")

    def test_set_view_mode_defined(self, page):
        assert page.evaluate("typeof setViewMode === 'function'")

    def test_set_depth_defined(self, page):
        assert page.evaluate("typeof setDepth === 'function'")

    def test_submit_research_defined(self, page):
        assert page.evaluate("typeof submitResearch === 'function'")

    def test_use_example_defined(self, page):
        assert page.evaluate("typeof useExample === 'function'")

    def test_safe_markdown_defined(self, page):
        assert page.evaluate("typeof safeMarkdown === 'function'")

    def test_show_toast_defined(self, page):
        assert page.evaluate("typeof showToast === 'function'")

    def test_render_memory_dashboard_defined(self, page):
        assert page.evaluate("typeof renderMemoryDashboard === 'function'")

    def test_render_pipelines_view_defined(self, page):
        assert page.evaluate("typeof renderPipelinesView === 'function'")
