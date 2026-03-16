"""
POLARIS Observatory — Visual Regression Test Configuration.
Shared viewports, browsers, and utility functions for screenshot comparison.
"""
import pytest
from playwright.sync_api import Page

VIEWPORTS = {
    "phone_375": {"width": 375, "height": 812},
    "tablet_768": {"width": 768, "height": 1024},
    "laptop_1024": {"width": 1024, "height": 768},
    "desktop_1440": {"width": 1440, "height": 900},
}

BROWSERS = ["chromium", "firefox", "webkit"]

# Base URL for the POLARIS live server
BASE_URL = "http://localhost:8766"


def freeze_dynamic_content(page: Page) -> None:
    """Freeze all dynamic counters and timers for deterministic screenshots.

    Uses add_init_script to intercept setInterval BEFORE page JS runs,
    preventing timer callbacks from overwriting frozen text values.
    Must be called BEFORE page.goto().
    """
    # Disable smooth scroll so Playwright doesn't capture mid-animation frames
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script("""
        // Intercept setInterval to block timer-based DOM updates
        const _origSetInterval = window.setInterval;
        window.setInterval = function(fn, ms, ...args) {
            // Allow very short intervals (animation frames) but block
            // 1s+ intervals that update elapsed-time / counters
            if (ms >= 500) return _origSetInterval.call(window, () => {}, ms);
            return _origSetInterval.call(window, fn, ms, ...args);
        };
        window._visualTestMode = true;
    """)


def apply_frozen_values(page: Page) -> None:
    """Set deterministic text values AFTER page has loaded.

    Call this after page.goto() and page.wait_for_load_state().
    """
    page.evaluate("""
        document.querySelectorAll('.elapsed-time').forEach(e => e.textContent = '00:05:23');
        document.querySelectorAll('.event-count').forEach(e => e.textContent = '247');
        document.querySelectorAll('.cost-display').forEach(e => e.textContent = '$1.31');
        document.querySelectorAll('.evidence-counter').forEach(e => e.textContent = '156');
        document.querySelectorAll('.source-counter').forEach(e => e.textContent = '47');
    """)


def navigate_to_view(page: Page, view: str) -> None:
    """Navigate to a specific view using JS switchView() for reliability.

    In user mode, nav bar and views container are hidden unless a pipeline is
    active/complete.  Using switchView() via JS (in operator mode) guarantees
    the view pane actually renders unique content.  Falls back to button click
    if switchView is unavailable.
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

    # Map legacy names
    view_id = {"operator": "advanced", "mindmap": "advanced"}.get(view, view)
    page.evaluate(f"switchView('{view_id}')")
    page.wait_for_timeout(300)


def set_theme(page: Page, theme: str) -> None:
    """Set the theme to 'dark' or 'light'."""
    page.evaluate(f"""
        document.documentElement.setAttribute('data-theme', '{theme}');
        localStorage.setItem('polaris-theme', '{theme}');
    """)
    page.wait_for_timeout(100)
