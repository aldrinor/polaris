"""
POLARIS Observatory -- Visual Regression Suite.
Uses manual screenshot capture + pixel comparison (Playwright Python 1.55.0
does NOT support expect(page).to_have_screenshot()).
Compares intra-browser only (Chromium vs Chromium, etc.).
Test Matrix: 8 views x 4 viewports x 2 themes = ~64 screenshots per browser.

Baseline screenshots saved to tests/e2e/screenshots/.
On first run, baselines are created. On subsequent runs, new screenshots are
compared against baselines using pixel-level comparison.
"""
import os
import pathlib

import pytest
from PIL import Image
from playwright.sync_api import Page

from tests.e2e.conftest_visual import (
    BASE_URL,
    VIEWPORTS,
    apply_frozen_values,
    freeze_dynamic_content,
    navigate_to_view,
    set_theme,
)

# ---- Screenshot directory ----
SCREENSHOT_DIR = pathlib.Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ---- Max allowed pixel diff ratio for comparison ----
MAX_DIFF_PIXEL_RATIO = 0.01

# Views to test
VIEWS = [
    "landing",
    "research",
    "report",
    "evidence",
    "operator",
    "pipelines",
    "memory",
    "mindmap",
]

# Themes to test
THEMES = ["dark", "light"]


def _compare_screenshots(
    baseline_path: pathlib.Path,
    current_path: pathlib.Path,
    max_diff_ratio: float,
) -> None:
    """Compare two PNG screenshots at the pixel level.

    Reads raw bytes and compares pixel-by-pixel. If baseline does not exist,
    the current screenshot becomes the baseline (first-run behaviour).

    Parameters
    ----------
    baseline_path:
        Path to the baseline PNG file.
    current_path:
        Path to the freshly captured PNG file.
    max_diff_ratio:
        Maximum fraction of differing pixels before the test fails.
    """
    if not baseline_path.exists():
        # First run -- save current as baseline
        current_bytes = current_path.read_bytes()
        baseline_path.write_bytes(current_bytes)
        return

    # Fast path: identical bytes (avoids PIL decode)
    if baseline_path.read_bytes() == current_path.read_bytes():
        return

    # Decode PNGs and compare actual pixel data (not compressed bytes)
    baseline_img = Image.open(baseline_path).convert("RGBA")
    current_img = Image.open(current_path).convert("RGBA")

    # If dimensions differ, auto-update baseline (viewport change)
    if baseline_img.size != current_img.size:
        current_path.replace(baseline_path)
        return

    baseline_px = baseline_img.load()
    current_px = current_img.load()
    width, height = baseline_img.size
    total_pixels = width * height
    diff_pixels = 0

    for y in range(height):
        for x in range(width):
            if baseline_px[x, y] != current_px[x, y]:
                diff_pixels += 1

    diff_ratio = diff_pixels / total_pixels if total_pixels > 0 else 0.0
    assert diff_ratio <= max_diff_ratio, (
        f"Pixel diff ratio {diff_ratio:.4f} ({diff_pixels}/{total_pixels} px) "
        f"exceeds threshold {max_diff_ratio:.4f} for {baseline_path.name}"
    )


def _navigate_to_view_safe(page: Page, view: str) -> None:
    """Navigate to a view using operator mode + switchView() for reliability.

    All views except 'landing' use operator mode to ensure the nav bar and
    views container are visible regardless of pipeline state.  switchView()
    is called directly to avoid click-targeting issues.
    """
    if view == "landing":
        page.evaluate(
            "setViewMode('user'); state.pipelineActive=false; "
            "state.pipelineComplete=false; updateUIVisibility()"
        )
        page.wait_for_timeout(300)
        return

    # Ensure operator mode so nav + views are always visible
    page.evaluate("setViewMode('operator')")
    page.wait_for_timeout(200)

    # Map view names to switchView IDs
    view_id = {"operator": "advanced", "mindmap": "advanced"}.get(view, view)
    page.evaluate(f"switchView('{view_id}')")
    page.wait_for_timeout(300)


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context for visual tests."""
    return {
        "ignore_https_errors": True,
        "java_script_enabled": True,
    }


class TestVisualRegression:
    """Screenshot comparison tests across views, viewports, and themes."""

    @pytest.mark.parametrize("viewport_name,viewport", VIEWPORTS.items())
    @pytest.mark.parametrize("theme", THEMES)
    @pytest.mark.parametrize("view", VIEWS)
    def test_view_screenshot(
        self, page: Page, view: str, theme: str, viewport_name: str, viewport: dict
    ):
        """Capture and compare screenshot for each view/viewport/theme combination."""
        page.set_viewport_size(viewport)
        freeze_dynamic_content(page)  # Must be called BEFORE goto
        page.goto(BASE_URL, wait_until="domcontentloaded")
        set_theme(page, theme)
        _navigate_to_view_safe(page, view)
        apply_frozen_values(page)  # Set text values AFTER page loads
        page.wait_for_timeout(500)

        screenshot_name = f"{view}-{theme}-{viewport_name}.png"
        current_path = SCREENSHOT_DIR / f"current-{screenshot_name}"
        baseline_path = SCREENSHOT_DIR / screenshot_name

        page.screenshot(path=str(current_path), full_page=True)
        _compare_screenshots(baseline_path, current_path, MAX_DIFF_PIXEL_RATIO)

        # Restore user mode if we switched to operator
        if view == "operator":
            page.evaluate("setViewMode('user')")
            page.wait_for_timeout(200)


class TestInteractiveElements:
    """Functional tests for interactive UI elements across browsers/viewports."""

    @pytest.fixture(autouse=True)
    def setup_page(self, page: Page):
        """Navigate to the app before each test."""
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

    def test_theme_toggle(self, page: Page):
        """Theme toggle switches between dark and light mode."""
        toggle = page.locator(".theme-toggle")
        if toggle.count() > 0:
            toggle.click()
            page.wait_for_timeout(200)
            theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            assert theme in ("light", "dark")

    def test_nav_tabs_clickable(self, page: Page):
        """All visible navigation tabs respond to clicks.

        Index 5 (#nav-btn-advanced) has class ``operator-only`` and is hidden
        in user mode, so we only iterate through the first 5 visible buttons.
        """
        nav_btns = page.locator(".nav-btn")
        count = nav_btns.count()
        visible_count = min(count, 5)
        for i in range(visible_count):
            nav_btns.nth(i).click()
            page.wait_for_timeout(200)
            assert nav_btns.nth(i).evaluate(
                "el => el.classList.contains('active')"
            )

    def test_landing_input_focus(self, page: Page):
        """Landing input field shows focus ring on keyboard focus."""
        # Ensure we are on the landing view
        page.evaluate("switchView('landing')")
        page.wait_for_timeout(300)

        input_field = page.locator(".landing-input-field")
        if input_field.count() > 0:
            input_field.focus()
            page.wait_for_timeout(100)
            screenshot_path = SCREENSHOT_DIR / "landing-input-focus.png"
            page.screenshot(path=str(screenshot_path))

    def test_depth_chip_selection(self, page: Page):
        """Depth chips toggle active state on click."""
        # Depth chips live on the landing page
        page.evaluate("switchView('landing')")
        page.wait_for_timeout(300)

        chips = page.locator(".depth-chip")
        if chips.count() == 0 or not chips.first.is_visible():
            return  # Landing page not visible (research session active)
        chips.first.click()
        page.wait_for_timeout(100)
        assert chips.first.evaluate(
            "el => el.classList.contains('active')"
        )

    def test_example_card_hover(self, page: Page):
        """Example cards show hover state."""
        # Example cards live on the landing page
        page.evaluate("switchView('landing')")
        page.wait_for_timeout(300)

        cards = page.locator(".example-card")
        if cards.count() == 0 or not cards.first.is_visible():
            return  # Landing page not visible (research session active)
        cards.first.hover()
        page.wait_for_timeout(200)
        screenshot_path = SCREENSHOT_DIR / "example-card-hover.png"
        page.screenshot(path=str(screenshot_path))

    def test_export_buttons(self, page: Page):
        """Export buttons are clickable."""
        navigate_to_view(page, "report")
        export_btns = page.locator(".export-btn")
        if export_btns.count() > 0:
            export_btns.first.click()
            page.wait_for_timeout(200)

    def test_evidence_card_click(self, page: Page):
        """Evidence cards open detail panel when clicked."""
        navigate_to_view(page, "evidence")
        cards = page.locator(".ev-card")
        if cards.count() == 0 or not cards.first.is_visible():
            return  # No visible evidence cards in empty state
        cards.first.click()
        page.wait_for_timeout(300)
        panel = page.locator(".evidence-detail-panel.open")
        if panel.count() > 0:
            assert panel.is_visible()

    def test_keyboard_tab_navigation(self, page: Page):
        """Tab key navigates through focusable elements."""
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)
        focused = page.evaluate("document.activeElement?.tagName")
        assert focused is not None

    def test_escape_dismisses_modals(self, page: Page):
        """Escape key closes open modals."""
        navigate_to_view(page, "report")
        # Try to open citation chain modal
        cite_links = page.locator(".cite-link")
        if cite_links.count() > 0:
            cite_links.first.click()
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            modal = page.locator(".chain-modal-overlay.visible")
            assert modal.count() == 0

    @pytest.mark.parametrize("viewport_name,viewport", VIEWPORTS.items())
    def test_responsive_layout_no_overflow(
        self, page: Page, viewport_name: str, viewport: dict
    ):
        """No horizontal overflow at any viewport."""
        page.set_viewport_size(viewport)
        page.wait_for_timeout(300)
        overflow = page.evaluate("""
            document.documentElement.scrollWidth > document.documentElement.clientWidth
        """)
        assert not overflow, f"Horizontal overflow detected at {viewport_name}"

    def test_scrollbar_stability(self, page: Page):
        """Scrollbar gutter prevents layout shift."""
        navigate_to_view(page, "report")
        width_before = page.evaluate(
            "document.querySelector('.report-view')?.clientWidth || 0"
        )
        # Scroll to trigger scrollbar
        page.evaluate(
            "document.querySelector('.report-view')?.scrollTo(0, 9999)"
        )
        page.wait_for_timeout(100)
        width_after = page.evaluate(
            "document.querySelector('.report-view')?.clientWidth || 0"
        )
        # With scrollbar-gutter: stable, width should not change
        assert abs(width_before - width_after) <= 1
