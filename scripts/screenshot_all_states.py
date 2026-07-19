"""
Comprehensive Playwright screenshot capture for the POLARIS dashboard.

Captures every tab, button, control, and UI state in both light and dark
themes, then compiles them into a single PDF review document.

Includes:
  - Phase A: Prove-the-cause diagnostics (blue block, evidence state, mobile)
  - Phase B-D: Base state captures (19 states x 2 themes)
  - Phase E.3: Interaction-state matrix (hover, focus, active per family)
  - Phase E.4: Alignment audit (DOM measurements for every changed control)
  - Phase E.5: Before/after diff generation
  - Phase E.6: Jump button post-fix proof

Usage:
    python scripts/screenshot_all_states.py

Output:
    outputs/design_audit/pdf_screenshots/*.png
    outputs/design_audit/diagnostic/*.png
    outputs/design_audit/interactions/{config}/*.png
    outputs/design_audit/diffs/*.png
    outputs/design_audit/alignment_audit.json
    outputs/design_audit/ui_review_v2.pdf
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("POLARIS_DASHBOARD_URL", "http://localhost:8765")
SCREENSHOT_DIR = Path("outputs/design_audit/pdf_screenshots")
DIAGNOSTIC_DIR = Path("outputs/design_audit/diagnostic")
INTERACTION_DIR = Path("outputs/design_audit/interactions")
DIFF_DIR = Path("outputs/design_audit/diffs")
PREVIOUS_RUN_ARCHIVE_DIR = Path("outputs/design_audit/v1_archive")
PDF_OUTPUT = Path("outputs/design_audit/ui_review_v2.pdf")
AUDIT_OUTPUT = Path("outputs/design_audit/alignment_audit.json")
DESKTOP_WIDTH = 1440
DESKTOP_HEIGHT = 900
MOBILE_WIDTH = 390
MOBILE_HEIGHT = 844
TRANSITION_WAIT_MS = 700
PAGE_LOAD_WAIT_MS = 3000

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Track captured screenshots: list of (state_name, theme, filepath)
captured: list[tuple[str, str, Path]] = []
failures: list[tuple[str, str, str]] = []
audit_results: list[dict] = []


# ---------------------------------------------------------------------------
# Helper: set theme
# ---------------------------------------------------------------------------
def set_theme(page: Page, theme: str) -> None:
    """Set dashboard theme to 'light' or 'dark'."""
    page.evaluate(
        f"document.documentElement.setAttribute('data-theme', '{theme}');"
        f"localStorage.setItem('polaris-theme', '{theme}');"
    )
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: switch to a nav view
# ---------------------------------------------------------------------------
def switch_view(page: Page, view_id: str) -> None:
    """Click a nav tab by data-view attribute."""
    page.evaluate(f"""
        if (typeof switchView === 'function') {{
            switchView('{view_id}');
        }} else {{
            document.querySelectorAll('.nav-btn').forEach(function(b) {{
                var isActive = b.dataset.view === '{view_id}';
                b.classList.toggle('active', isActive);
                b.setAttribute('aria-selected', isActive ? 'true' : 'false');
            }});
            document.querySelectorAll('.view-pane').forEach(function(p) {{
                p.classList.toggle('active', p.id === 'view-{view_id}');
            }});
        }}
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: set view mode (user / operator)
# ---------------------------------------------------------------------------
def set_view_mode(page: Page, mode: str) -> None:
    """Set view mode to 'user' or 'operator'."""
    page.evaluate(f"""
        if (typeof setViewMode === 'function') {{
            setViewMode('{mode}');
        }} else {{
            document.body.classList.toggle('user-mode', '{mode}' === 'user');
            document.querySelectorAll('.view-mode-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.mode === '{mode}');
            }});
        }}
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: open compose drawer
# ---------------------------------------------------------------------------
def open_compose(page: Page) -> None:
    """Open the compose drawer via JS."""
    page.evaluate("""
        var drawer = document.getElementById('compose-drawer');
        if (drawer) {
            drawer.classList.add('visible');
            drawer.style.display = 'block';
        }
        var trigger = document.getElementById('compose-trigger');
        if (trigger) trigger.setAttribute('aria-expanded', 'true');
        var fab = document.getElementById('compose-fab');
        if (fab) fab.classList.add('hidden');
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: close compose drawer
# ---------------------------------------------------------------------------
def close_compose(page: Page) -> None:
    """Close the compose drawer."""
    page.evaluate("""
        var drawer = document.getElementById('compose-drawer');
        if (drawer) {
            drawer.classList.remove('visible');
            drawer.style.display = '';
        }
        var trigger = document.getElementById('compose-trigger');
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
        var fab = document.getElementById('compose-fab');
        if (fab) fab.classList.remove('hidden');
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: show landing page
# ---------------------------------------------------------------------------
def show_landing(page: Page) -> None:
    """Ensure the landing page is visible."""
    page.evaluate("""
        var lp = document.getElementById('landing-page');
        if (lp) lp.classList.add('visible');
        var vc = document.querySelector('.views-container');
        if (vc) vc.style.display = 'none';
        var up = document.getElementById('user-progress');
        if (up) up.classList.remove('visible');
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: hide landing, show views
# ---------------------------------------------------------------------------
def show_views(page: Page) -> None:
    """Hide landing and show the views container."""
    page.evaluate("""
        var lp = document.getElementById('landing-page');
        if (lp) lp.classList.remove('visible');
        var vc = document.querySelector('.views-container');
        if (vc) vc.style.display = '';
        var nb = document.getElementById('main-nav-bar');
        if (nb) nb.style.display = '';
        var up = document.getElementById('user-progress');
        if (up) up.classList.remove('visible');
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Helper: inject mock phase data for research view
# ---------------------------------------------------------------------------
def inject_mock_phases(page: Page) -> None:
    """Inject mock phase data to populate the research view sidebar."""
    page.evaluate("""
        var phases = [
            {name: 'plan', label: 'Plan', status: 'done', duration: '12s'},
            {name: 'search', label: 'Search', status: 'done', duration: '45s'},
            {name: 'storm_interviews', label: 'STORM', status: 'done', duration: '38s'},
            {name: 'analyze', label: 'Analyze', status: 'done', duration: '22s'},
            {name: 'verify', label: 'Verify', status: 'active', duration: '...'},
            {name: 'evaluate', label: 'Evaluate', status: 'pending', duration: '--'},
            {name: 'synthesize', label: 'Synthesize', status: 'pending', duration: '--'},
            {name: 'search_gaps', label: 'Gap Search', status: 'pending', duration: '--'}
        ];
        var list = document.getElementById('phase-list');
        if (list) {
            list.innerHTML = '';
            phases.forEach(function(p) {
                var row = document.createElement('div');
                row.className = 'phase-row ' + (p.status === 'active' ? 'active' : '');
                row.setAttribute('data-phase', p.name);
                var statusIcon = p.status === 'done' ? '\\u2713' : (p.status === 'active' ? '\\u25CF' : '\\u25CB');
                var statusClass = p.status === 'done' ? 'done' : (p.status === 'active' ? 'active' : 'pending');
                row.innerHTML = '<span class="phase-status-dot ' + statusClass + '">' + statusIcon + '</span>' +
                    '<span class="phase-name">' + p.label + '</span>' +
                    '<span class="phase-duration">' + p.duration + '</span>';
                list.appendChild(row);
            });
            var prog = document.getElementById('phase-progress');
            if (prog) prog.textContent = '4/8';
        }
        var pmEv = document.getElementById('pm-evidence');
        if (pmEv) pmEv.textContent = '847';
        var pmFaith = document.getElementById('pm-faith');
        if (pmFaith) pmFaith.textContent = '89.2%';
        var pmWords = document.getElementById('pm-words');
        if (pmWords) pmWords.textContent = '11,450';
        var pmCost = document.getElementById('pm-cost');
        if (pmCost) pmCost.textContent = '$1.24';
        var gates = {
            'gate-faith': 'pass', 'gate-words': 'pass',
            'gate-cite': 'pass', 'gate-sources': 'warn',
            'gate-synth': 'pending'
        };
        Object.keys(gates).forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.className = 'gate-dot ' + gates[id];
        });
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------
def take_screenshot(
    page: Page,
    state_name: str,
    theme: str,
    clip: Optional[dict] = None,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Take a screenshot and record it."""
    target_dir = output_dir or SCREENSHOT_DIR
    filename = f"{state_name}_{theme}.png"
    filepath = target_dir / filename
    try:
        kwargs: dict = {"path": str(filepath), "type": "png"}
        if clip:
            kwargs["clip"] = clip
        else:
            kwargs["full_page"] = True
        page.screenshot(**kwargs)
        captured.append((state_name, theme, filepath))
        logger.info("Captured: %s (%s)", state_name, theme)
        return filepath
    except Exception as exc:
        failures.append((state_name, theme, str(exc)))
        logger.warning("FAILED: %s (%s) -- %s", state_name, theme, exc)
        return None


def capture_both_themes(
    page: Page,
    state_name: str,
    clip: Optional[dict] = None,
    output_dir: Optional[Path] = None,
) -> None:
    """Capture the current state in both light and dark themes."""
    for theme in ("light", "dark"):
        set_theme(page, theme)
        take_screenshot(page, state_name, theme, clip=clip, output_dir=output_dir)


def safe_capture(page: Page, state_name: str, setup_fn, clip: Optional[dict] = None):
    """Run setup_fn then capture both themes. On error, log and continue."""
    try:
        logger.info("State: %s", state_name)
        setup_fn()
        capture_both_themes(page, state_name, clip=clip)
    except Exception as exc:
        logger.warning("FAILED state %s: %s", state_name, exc)
        failures.append((state_name, "light", str(exc)))
        failures.append((state_name, "dark", str(exc)))


def get_element_bbox(page: Page, selector: str) -> Optional[dict]:
    """Get bounding box of first element matching selector."""
    try:
        bbox = page.evaluate(f"""
            var el = document.querySelector('{selector}');
            if (el) {{
                var r = el.getBoundingClientRect();
                ({{x: r.x, y: r.y, width: r.width, height: r.height}});
            }} else {{
                null;
            }}
        """)
        if bbox and bbox.get("width", 0) > 0:
            return bbox
    except Exception:
        pass
    return None


def bbox_to_clip(bbox: Optional[dict], pad: int = 20) -> dict:
    """Convert bounding box to clip dict with padding."""
    if bbox:
        vw = int(page_viewport_width.get("w", DESKTOP_WIDTH))
        return {
            "x": max(0, bbox["x"] - pad),
            "y": max(0, bbox["y"] - pad),
            "width": min(vw, bbox["width"] + pad * 2),
            "height": max(60, bbox["height"] + pad * 2),
        }
    return {"x": 0, "y": 50, "width": DESKTOP_WIDTH, "height": 120}


# Global state for current viewport width
page_viewport_width: dict = {"w": DESKTOP_WIDTH}


# ---------------------------------------------------------------------------
# Phase A: Prove-the-cause diagnostics
# ---------------------------------------------------------------------------
def run_phase_a_diagnostics(page: Page) -> None:
    """Phase A: Prove-the-cause diagnostics before styling."""
    logger.info("=" * 60)
    logger.info("PHASE A: Prove-the-cause diagnostics")
    logger.info("=" * 60)

    # A.1 Blue block isolation (jump-btn)
    logger.info("A.1: Blue block isolation")
    set_view_mode(page, "operator")
    show_views(page)
    switch_view(page, "research")
    inject_mock_phases(page)
    set_theme(page, "dark")

    # Crop bottom area where jump-btn appears
    bottom_clip = {
        "x": 200, "y": DESKTOP_HEIGHT - 200,
        "width": DESKTOP_WIDTH - 400, "height": 200,
    }
    take_screenshot(page, "a1_jump_btn_visible", "dark", clip=bottom_clip,
                    output_dir=DIAGNOSTIC_DIR)

    # Hide jump-btn, re-crop to prove it was the cause
    page.evaluate(
        "var jb = document.querySelector('.jump-btn');"
        "if (jb) jb.style.visibility = 'hidden';"
    )
    page.wait_for_timeout(300)
    take_screenshot(page, "a1_jump_btn_hidden", "dark", clip=bottom_clip,
                    output_dir=DIAGNOSTIC_DIR)

    # Restore
    page.evaluate(
        "var jb = document.querySelector('.jump-btn');"
        "if (jb) jb.style.visibility = '';"
    )
    page.wait_for_timeout(300)

    # A.2 Evidence state differentiation
    logger.info("A.2: Evidence state differentiation")
    switch_view(page, "evidence")
    set_theme(page, "dark")
    take_screenshot(page, "a2_evidence_crossref", "dark", output_dir=DIAGNOSTIC_DIR)

    # Click Citation Map seg-btn (real UI action)
    page.evaluate("""
        var citBtn = document.querySelector('.seg-btn[data-mode="citation"]') ||
                     document.querySelector('.seg-btn[data-mode="citation-map"]');
        if (citBtn) citBtn.click();
    """)
    page.wait_for_timeout(TRANSITION_WAIT_MS)
    take_screenshot(page, "a2_evidence_citation_map", "dark", output_dir=DIAGNOSTIC_DIR)

    # A.3 Mobile state differentiation
    logger.info("A.3: Mobile state differentiation")
    page.set_viewport_size({"width": MOBILE_WIDTH, "height": MOBILE_HEIGHT})
    page_viewport_width["w"] = MOBILE_WIDTH
    page.wait_for_timeout(TRANSITION_WAIT_MS)

    set_view_mode(page, "user")
    show_landing(page)
    set_theme(page, "dark")
    take_screenshot(page, "a3_mobile_landing", "dark", output_dir=DIAGNOSTIC_DIR)

    show_views(page)
    switch_view(page, "research")
    page.wait_for_timeout(TRANSITION_WAIT_MS)
    take_screenshot(page, "a3_mobile_research", "dark", output_dir=DIAGNOSTIC_DIR)

    # Restore desktop
    page.set_viewport_size({"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT})
    page_viewport_width["w"] = DESKTOP_WIDTH
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# Main capture sequence (19 base states)
# ---------------------------------------------------------------------------
def run_capture_sequence(page: Page) -> None:
    """Execute the full capture sequence across all states."""

    # Navigate to the dashboard
    logger.info("Navigating to %s ...", BASE_URL)
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(PAGE_LOAD_WAIT_MS)

    # Suppress errors from SSE/network
    page.evaluate("""
        window.onerror = function() { return true; };
        window.addEventListener('unhandledrejection', function(e) { e.preventDefault(); });
    """)

    # -----------------------------------------------------------------------
    # 1. landing_user_idle
    # -----------------------------------------------------------------------
    def setup_landing_user():
        set_view_mode(page, "user")
        show_landing(page)
        close_compose(page)

    safe_capture(page, "landing_user_idle", setup_landing_user)

    # -----------------------------------------------------------------------
    # 2. landing_operator_idle
    # -----------------------------------------------------------------------
    def setup_landing_operator():
        set_view_mode(page, "operator")
        show_landing(page)

    safe_capture(page, "landing_operator_idle", setup_landing_operator)

    # -----------------------------------------------------------------------
    # 3. compose_drawer_open
    # -----------------------------------------------------------------------
    def setup_compose_open():
        set_view_mode(page, "user")
        show_landing(page)
        open_compose(page)

    safe_capture(page, "compose_drawer_open", setup_compose_open)

    # -----------------------------------------------------------------------
    # 4. compose_drawer_with_text
    # -----------------------------------------------------------------------
    def setup_compose_text():
        page.evaluate("""
            var ta = document.getElementById('compose-query');
            if (ta) {
                ta.value = 'What is the impact of microplastics on marine life?';
                ta.dispatchEvent(new Event('input', {bubbles: true}));
            }
        """)
        page.wait_for_timeout(TRANSITION_WAIT_MS)

    safe_capture(page, "compose_drawer_with_text", setup_compose_text)
    close_compose(page)

    # -----------------------------------------------------------------------
    # 5. research_empty (Operator mode)
    # -----------------------------------------------------------------------
    def setup_research_empty():
        set_view_mode(page, "operator")
        show_views(page)
        switch_view(page, "research")

    safe_capture(page, "research_empty", setup_research_empty)

    # -----------------------------------------------------------------------
    # 6. research_with_phases (Operator mode + mock data)
    # -----------------------------------------------------------------------
    def setup_research_phases():
        inject_mock_phases(page)

    safe_capture(page, "research_with_phases", setup_research_phases)

    # -----------------------------------------------------------------------
    # 7. evidence_tab (Operator mode)
    # -----------------------------------------------------------------------
    def setup_evidence():
        switch_view(page, "evidence")

    safe_capture(page, "evidence_tab", setup_evidence)

    # -----------------------------------------------------------------------
    # 8. evidence_citation_map (E.1: real UI action — click Citation Map)
    # -----------------------------------------------------------------------
    def setup_evidence_citation_map():
        page.evaluate("""
            var citBtn = document.querySelector('.seg-btn[data-mode="citation"]') ||
                         document.querySelector('.seg-btn[data-mode="citation-map"]');
            if (citBtn) citBtn.click();
        """)
        page.wait_for_timeout(TRANSITION_WAIT_MS)

    safe_capture(page, "evidence_citation_map", setup_evidence_citation_map)

    # -----------------------------------------------------------------------
    # 9. report_tab
    # -----------------------------------------------------------------------
    def setup_report():
        switch_view(page, "report")

    safe_capture(page, "report_tab", setup_report)

    # -----------------------------------------------------------------------
    # 10. advanced_tab (Operator mode)
    # -----------------------------------------------------------------------
    def setup_advanced():
        set_view_mode(page, "operator")
        show_views(page)
        page.evaluate("""
            var advBtn = document.getElementById('nav-btn-advanced');
            if (advBtn) advBtn.style.display = '';
        """)
        switch_view(page, "advanced")

    safe_capture(page, "advanced_tab", setup_advanced)

    # -----------------------------------------------------------------------
    # 11. pipelines_tab
    # -----------------------------------------------------------------------
    def setup_pipelines():
        switch_view(page, "pipelines")

    safe_capture(page, "pipelines_tab", setup_pipelines)

    # -----------------------------------------------------------------------
    # 12. memory_tab
    # -----------------------------------------------------------------------
    def setup_memory():
        switch_view(page, "memory")

    safe_capture(page, "memory_tab", setup_memory)

    # -----------------------------------------------------------------------
    # 13. nav_bar_closeup (top 100px)
    # -----------------------------------------------------------------------
    def setup_nav_closeup():
        set_view_mode(page, "operator")
        show_views(page)
        switch_view(page, "research")

    safe_capture(
        page, "nav_bar_closeup", setup_nav_closeup,
        clip={"x": 0, "y": 0, "width": DESKTOP_WIDTH, "height": 100},
    )

    # -----------------------------------------------------------------------
    # 14. compose_bar_closeup
    # -----------------------------------------------------------------------
    def setup_compose_bar():
        set_view_mode(page, "user")
        show_landing(page)
        close_compose(page)

    setup_compose_bar()
    bbox = get_element_bbox(page, "#compose-bar")
    clip = bbox_to_clip(bbox)
    capture_both_themes(page, "compose_bar_closeup", clip=clip)

    # -----------------------------------------------------------------------
    # 15. filter_chips_closeup (evidence tier chips)
    # -----------------------------------------------------------------------
    set_view_mode(page, "operator")
    show_views(page)
    switch_view(page, "evidence")
    bbox = get_element_bbox(page, "#tier-chips")
    clip = bbox_to_clip(bbox)
    capture_both_themes(page, "filter_chips_closeup", clip=clip)

    # -----------------------------------------------------------------------
    # 16. depth_chips_closeup (compose drawer depth chips)
    # -----------------------------------------------------------------------
    set_view_mode(page, "user")
    show_landing(page)
    open_compose(page)
    bbox = get_element_bbox(page, "#compose-depth")
    clip = bbox_to_clip(bbox)
    capture_both_themes(page, "depth_chips_closeup", clip=clip)
    close_compose(page)

    # -----------------------------------------------------------------------
    # 17-19. Mobile states (390x844)
    # -----------------------------------------------------------------------
    logger.info("Switching to mobile viewport %dx%d", MOBILE_WIDTH, MOBILE_HEIGHT)
    page.set_viewport_size({"width": MOBILE_WIDTH, "height": MOBILE_HEIGHT})
    page_viewport_width["w"] = MOBILE_WIDTH
    page.wait_for_timeout(TRANSITION_WAIT_MS)

    # 17. mobile_landing
    def setup_mobile_landing():
        set_view_mode(page, "user")
        show_landing(page)
        close_compose(page)

    safe_capture(page, "mobile_landing", setup_mobile_landing)

    # 18. mobile_research (E.2: real UI action — switch to research view)
    def setup_mobile_research():
        show_views(page)
        switch_view(page, "research")

    safe_capture(page, "mobile_research", setup_mobile_research)

    # 19. mobile_compose_open
    def setup_mobile_compose():
        show_landing(page)
        open_compose(page)

    safe_capture(page, "mobile_compose_open", setup_mobile_compose)
    close_compose(page)

    # Restore desktop viewport
    page.set_viewport_size({"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT})
    page_viewport_width["w"] = DESKTOP_WIDTH
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# E.3: Interaction-state matrix
# ---------------------------------------------------------------------------
INTERACTION_FAMILIES = [
    {
        "name": "filter_chip",
        "setup_view": "evidence",
        "selector": ".filter-chip",
        "active_selector": ".filter-chip[data-tier='gold']",
        "states": ["idle", "hover", "active"],
    },
    {
        "name": "seg_btn",
        "setup_view": "evidence",
        "selector": ".seg-btn",
        "active_selector": ".seg-btn[data-mode='citation']",
        "states": ["idle", "hover", "active"],
    },
    {
        "name": "nav_btn",
        "setup_view": "research",
        "selector": ".nav-btn",
        "active_selector": ".nav-btn[data-view='evidence']",
        "states": ["idle", "hover", "active"],
    },
    {
        "name": "adv_tab_btn",
        "setup_view": "advanced",
        "selector": ".adv-tab-btn",
        "active_selector": ".adv-tab-btn[data-tab='sources']",
        "states": ["idle", "hover", "active"],
    },
    {
        "name": "compose_trigger",
        "setup_view": None,  # landing page
        "selector": ".compose-trigger",
        "active_selector": None,
        "states": ["idle", "hover"],
    },
    {
        "name": "depth_chip",
        "setup_view": None,  # landing page with compose open
        "selector": ".depth-chip",
        "active_selector": ".depth-chip.active",
        "states": ["idle", "hover", "active"],
    },
    {
        "name": "view_mode_btn",
        "setup_view": "research",
        "selector": ".view-mode-btn",
        "active_selector": ".view-mode-btn.active",
        "states": ["idle", "hover"],
    },
    {
        "name": "jump_btn",
        "setup_view": "research",
        "selector": ".jump-btn",
        "active_selector": None,
        "states": ["idle", "hover"],
    },
    {
        "name": "bookmark_btn",
        "setup_view": "evidence",
        "selector": ".bookmark-btn",
        "active_selector": None,
        "states": ["idle", "hover"],
    },
]


def capture_interaction_crop(
    page: Page,
    selector: str,
    output_path: Path,
    pad: int = 30,
) -> Optional[Path]:
    """Crop screenshot around a specific element."""
    bbox = get_element_bbox(page, selector)
    if not bbox:
        logger.warning("Element not found for crop: %s", selector)
        return None
    vw = page_viewport_width.get("w", DESKTOP_WIDTH)
    clip = {
        "x": max(0, bbox["x"] - pad),
        "y": max(0, bbox["y"] - pad),
        "width": min(vw, bbox["width"] + pad * 2),
        "height": max(60, bbox["height"] + pad * 2),
    }
    try:
        page.screenshot(path=str(output_path), type="png", clip=clip)
        logger.info("Interaction crop: %s", output_path.name)
        return output_path
    except Exception as exc:
        logger.warning("FAILED interaction crop %s: %s", output_path.name, exc)
        return None


def run_interaction_capture(page: Page) -> None:
    """E.3: Capture interaction states across 4 configurations."""
    logger.info("=" * 60)
    logger.info("PHASE E.3: Interaction-state matrix")
    logger.info("=" * 60)

    configs = [
        ("dark_desktop", "dark", DESKTOP_WIDTH, DESKTOP_HEIGHT),
        ("light_desktop", "light", DESKTOP_WIDTH, DESKTOP_HEIGHT),
        ("dark_mobile", "dark", MOBILE_WIDTH, MOBILE_HEIGHT),
        ("light_mobile", "light", MOBILE_WIDTH, MOBILE_HEIGHT),
    ]

    for config_name, theme, width, height in configs:
        config_dir = INTERACTION_DIR / config_name
        config_dir.mkdir(parents=True, exist_ok=True)

        page.set_viewport_size({"width": width, "height": height})
        page_viewport_width["w"] = width
        page.wait_for_timeout(TRANSITION_WAIT_MS)
        set_theme(page, theme)

        for family in INTERACTION_FAMILIES:
            fname = family["name"]
            selector = family["selector"]
            active_sel = family["active_selector"]

            # Setup the right view
            if family["setup_view"] is None:
                set_view_mode(page, "user")
                show_landing(page)
                close_compose(page)
                if fname == "depth_chip":
                    open_compose(page)
            else:
                set_view_mode(page, "operator")
                show_views(page)
                if family["setup_view"] == "advanced":
                    page.evaluate("""
                        var advBtn = document.getElementById('nav-btn-advanced');
                        if (advBtn) advBtn.style.display = '';
                    """)
                switch_view(page, family["setup_view"])

            # Idle state
            if "idle" in family["states"]:
                capture_interaction_crop(
                    page, selector,
                    config_dir / f"{fname}_idle.png",
                )

            # Hover state
            if "hover" in family["states"]:
                try:
                    el = page.query_selector(selector)
                    if el:
                        el.hover()
                        page.wait_for_timeout(300)
                        capture_interaction_crop(
                            page, selector,
                            config_dir / f"{fname}_hover.png",
                        )
                        # Move mouse away to reset
                        page.mouse.move(0, 0)
                        page.wait_for_timeout(200)
                except Exception as exc:
                    logger.warning("Hover failed for %s: %s", fname, exc)

            # Active state (click to activate)
            if "active" in family["states"] and active_sel:
                try:
                    el = page.query_selector(active_sel)
                    if el:
                        el.click()
                        page.wait_for_timeout(TRANSITION_WAIT_MS)
                        capture_interaction_crop(
                            page, active_sel,
                            config_dir / f"{fname}_active.png",
                        )
                except Exception as exc:
                    logger.warning("Active click failed for %s: %s", fname, exc)

            # Clean up compose if needed
            if fname == "depth_chip":
                close_compose(page)

    # Restore desktop
    page.set_viewport_size({"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT})
    page_viewport_width["w"] = DESKTOP_WIDTH
    page.wait_for_timeout(TRANSITION_WAIT_MS)


# ---------------------------------------------------------------------------
# E.4: Alignment audit (DOM measurements)
# ---------------------------------------------------------------------------
AUDIT_CONTROLS = [
    {"selector": ".filter-chip", "family": "chip", "view": "evidence"},
    {"selector": ".depth-chip", "family": "chip", "view": None},
    {"selector": ".trace-chip", "family": "chip", "view": "advanced"},
    {"selector": ".seg-btn", "family": "tab", "view": "evidence"},
    {"selector": ".nav-btn", "family": "tab", "view": "research"},
    {"selector": ".adv-tab-btn", "family": "tab", "view": "advanced"},
    {"selector": ".view-mode-btn", "family": "toggle", "view": "research"},
    {"selector": ".auto-nav-switch", "family": "toggle", "view": "research"},
    {"selector": ".compose-trigger", "family": "compose", "view": None},
    {"selector": ".jump-btn", "family": "action", "view": "research"},
    {"selector": ".bookmark-btn", "family": "icon", "view": "evidence"},
    {"selector": "#graph-reset-btn", "family": "action", "view": "evidence"},
    {"selector": ".pipe-tool-btn", "family": "action", "view": "pipelines"},
    {"selector": ".export-btn-audit", "family": "action", "view": "report"},
]

# Expected specs per family
FAMILY_SPECS = {
    "chip": {
        "padding": "6px 12px",
        "border_radius": "20px",  # radius-pill
        "font_size": "11px",
        "min_height": 44,
    },
    "tab": {
        "padding": "4px 14px",
        "border_radius": "0px",
        "font_size": "12px",
        "min_height": 44,
    },
    "toggle": {"min_height": 44},
    "compose": {"min_height": 44},
    "action": {"min_height": 44},
    "icon": {"min_height": 44},
}


def run_alignment_audit(page: Page) -> None:
    """E.4: Measure DOM properties for every changed control."""
    logger.info("=" * 60)
    logger.info("PHASE E.4: Alignment audit")
    logger.info("=" * 60)

    configs = [
        ("dark_desktop", "dark", DESKTOP_WIDTH, DESKTOP_HEIGHT),
        ("light_desktop", "light", DESKTOP_WIDTH, DESKTOP_HEIGHT),
        ("dark_mobile", "dark", MOBILE_WIDTH, MOBILE_HEIGHT),
        ("light_mobile", "light", MOBILE_WIDTH, MOBILE_HEIGHT),
    ]

    for config_name, theme, width, height in configs:
        page.set_viewport_size({"width": width, "height": height})
        page_viewport_width["w"] = width
        page.wait_for_timeout(TRANSITION_WAIT_MS)
        set_theme(page, theme)

        for control in AUDIT_CONTROLS:
            selector = control["selector"]
            family = control["family"]

            # Navigate to right view
            if control["view"] is None:
                set_view_mode(page, "user")
                show_landing(page)
                close_compose(page)
                if selector == ".depth-chip":
                    open_compose(page)
            else:
                set_view_mode(page, "operator")
                show_views(page)
                if control["view"] == "advanced":
                    page.evaluate("""
                        var advBtn = document.getElementById('nav-btn-advanced');
                        if (advBtn) advBtn.style.display = '';
                    """)
                switch_view(page, control["view"])

            # Measure all instances of this selector
            metrics_list = page.evaluate(f"""
                (function() {{
                    var els = document.querySelectorAll('{selector}');
                    var results = [];
                    els.forEach(function(el) {{
                        var cs = getComputedStyle(el);
                        var rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return;

                        var iconEl = el.querySelector('svg, i, .icon, [class*="icon"]');
                        var iconSize = null;
                        var iconOffset = null;
                        if (iconEl) {{
                            var ir = iconEl.getBoundingClientRect();
                            iconSize = {{w: ir.width, h: ir.height}};
                            var parentCenter = rect.top + rect.height / 2;
                            var iconCenter = ir.top + ir.height / 2;
                            iconOffset = Math.abs(parentCenter - iconCenter);
                        }}

                        results.push({{
                            selector: '{selector}',
                            text: (el.textContent || '').trim().substring(0, 30),
                            height: Math.round(rect.height),
                            width: Math.round(rect.width),
                            padding: {{
                                top: parseInt(cs.paddingTop) || 0,
                                right: parseInt(cs.paddingRight) || 0,
                                bottom: parseInt(cs.paddingBottom) || 0,
                                left: parseInt(cs.paddingLeft) || 0,
                            }},
                            font_size: cs.fontSize,
                            font_weight: cs.fontWeight,
                            border_radius: cs.borderRadius,
                            border_width: cs.borderWidth,
                            min_width: cs.minWidth,
                            max_width: cs.maxWidth,
                            icon_size: iconSize,
                            icon_vertical_offset: iconOffset ? Math.round(iconOffset * 10) / 10 : null,
                        }});
                    }});
                    return results;
                }})()
            """)

            if not metrics_list:
                logger.warning("No instances found: %s in %s", selector, config_name)
                continue

            spec = FAMILY_SPECS.get(family, {})
            min_h = spec.get("min_height", 44)

            for metrics in metrics_list:
                fails = []
                if metrics["height"] < min_h:
                    fails.append(
                        f"height {metrics['height']}px < {min_h}px minimum"
                    )
                if "padding" in spec:
                    expected_padding = spec["padding"]
                    actual_lr = f"{metrics['padding']['left']}px {metrics['padding']['right']}px"
                    # Simple check: left/right padding
                    exp_parts = expected_padding.split()
                    if len(exp_parts) == 2:
                        exp_tb, exp_lr = exp_parts
                        exp_lr_val = int(exp_lr.replace("px", ""))
                        if metrics["padding"]["right"] != exp_lr_val:
                            fails.append(
                                f"padding_right {metrics['padding']['right']}px "
                                f"!= expected {exp_lr_val}px"
                            )
                if "font_size" in spec:
                    if metrics["font_size"] != spec["font_size"]:
                        fails.append(
                            f"font_size {metrics['font_size']} "
                            f"!= expected {spec['font_size']}"
                        )
                if metrics.get("icon_vertical_offset") is not None:
                    if metrics["icon_vertical_offset"] > 1.0:
                        fails.append(
                            f"icon_vertical_offset {metrics['icon_vertical_offset']}px > 1px"
                        )

                audit_results.append({
                    "selector": selector,
                    "text": metrics.get("text", ""),
                    "config": config_name,
                    "family": family,
                    "pass": len(fails) == 0,
                    "metrics": metrics,
                    "failures": fails,
                })

            # Clean up compose
            if selector == ".depth-chip":
                close_compose(page)

    # Restore desktop
    page.set_viewport_size({"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT})
    page_viewport_width["w"] = DESKTOP_WIDTH
    page.wait_for_timeout(TRANSITION_WAIT_MS)

    # Write audit results
    AUDIT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)
    logger.info("Alignment audit written: %s (%d entries)", AUDIT_OUTPUT, len(audit_results))

    # Summary
    total = len(audit_results)
    passed = sum(1 for r in audit_results if r["pass"])
    failed = total - passed
    logger.info("Audit: %d/%d passed, %d failed", passed, total, failed)
    if failed:
        for r in audit_results:
            if not r["pass"]:
                logger.warning(
                    "  FAIL: %s [%s] %s — %s",
                    r["selector"], r["config"], r.get("text", ""),
                    "; ".join(r["failures"]),
                )


# ---------------------------------------------------------------------------
# E.5: Before/after diff generation
# ---------------------------------------------------------------------------
def generate_diffs() -> None:
    """Generate pixel-diff images between v1 archive and current screenshots."""
    logger.info("=" * 60)
    logger.info("PHASE E.5: Diff generation")
    logger.info("=" * 60)

    try:
        from PIL import Image, ImageChops
    except ImportError:
        logger.warning("Pillow not installed — skipping diff generation")
        return

    DIFF_DIR.mkdir(parents=True, exist_ok=True)
    diff_count = 0

    if not PREVIOUS_RUN_ARCHIVE_DIR.exists():
        logger.warning("No v1 archive at %s — skipping diffs", PREVIOUS_RUN_ARCHIVE_DIR)
        return

    for v1_file in PREVIOUS_RUN_ARCHIVE_DIR.glob("*.png"):
        v2_file = SCREENSHOT_DIR / v1_file.name
        if not v2_file.exists():
            logger.info("No v2 match for %s", v1_file.name)
            continue

        try:
            img1 = Image.open(v1_file).convert("RGB")
            img2 = Image.open(v2_file).convert("RGB")

            # Resize to match if needed
            if img1.size != img2.size:
                img2 = img2.resize(img1.size, Image.LANCZOS)

            diff = ImageChops.difference(img1, img2)
            diff_path = DIFF_DIR / f"diff_{v1_file.name}"
            diff.save(str(diff_path))
            diff_count += 1
        except Exception as exc:
            logger.warning("Diff failed for %s: %s", v1_file.name, exc)

    logger.info("Generated %d diff images in %s", diff_count, DIFF_DIR)


# ---------------------------------------------------------------------------
# E.6: Jump button post-fix proof
# ---------------------------------------------------------------------------
def run_jump_btn_proof(page: Page) -> None:
    """E.6: Prove jump button artifact is gone after styling changes."""
    logger.info("=" * 60)
    logger.info("PHASE E.6: Jump button post-fix proof")
    logger.info("=" * 60)

    set_view_mode(page, "operator")
    show_views(page)
    switch_view(page, "research")
    inject_mock_phases(page)
    set_theme(page, "dark")

    bottom_clip = {
        "x": 200, "y": DESKTOP_HEIGHT - 200,
        "width": DESKTOP_WIDTH - 400, "height": 200,
    }
    take_screenshot(page, "e6_jump_btn_postfix", "dark", clip=bottom_clip,
                    output_dir=DIAGNOSTIC_DIR)

    # Also capture in light theme
    set_theme(page, "light")
    take_screenshot(page, "e6_jump_btn_postfix", "light", clip=bottom_clip,
                    output_dir=DIAGNOSTIC_DIR)

    logger.info("Jump button proof captured — compare to a1_jump_btn_visible")


# ---------------------------------------------------------------------------
# PDF compilation
# ---------------------------------------------------------------------------
def compile_pdf() -> Path:
    """Compile all captured screenshots into a single review PDF."""
    from collections import OrderedDict

    from fpdf import FPDF

    logger.info("Compiling PDF from %d screenshots ...", len(captured))

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    page_w = 297
    page_h = 210
    margin = 10

    # Group by state name so light/dark appear on same page
    states: OrderedDict[str, dict[str, Path]] = OrderedDict()
    for state_name, theme, filepath in captured:
        if state_name not in states:
            states[state_name] = {}
        states[state_name][theme] = filepath

    for state_name, themes in states.items():
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 14)
        pdf.set_xy(margin, margin)
        pdf.cell(
            page_w - 2 * margin, 8,
            text=state_name.replace("_", " ").title(),
            align="C",
        )

        has_light = "light" in themes
        has_dark = "dark" in themes

        if has_light and has_dark:
            img_w = (page_w - 3 * margin) / 2

            pdf.set_font("Helvetica", "", 9)
            pdf.set_xy(margin, 20)
            pdf.cell(img_w, 5, text="Light Theme", align="C")
            try:
                pdf.image(str(themes["light"]), x=margin, y=26, w=img_w)
            except Exception as exc:
                logger.warning("PDF image error (light): %s", exc)

            right_x = margin * 2 + img_w
            pdf.set_xy(right_x, 20)
            pdf.cell(img_w, 5, text="Dark Theme", align="C")
            try:
                pdf.image(str(themes["dark"]), x=right_x, y=26, w=img_w)
            except Exception as exc:
                logger.warning("PDF image error (dark): %s", exc)
        else:
            theme_name = "light" if has_light else "dark"
            filepath = themes[theme_name]
            img_w = page_w - 2 * margin
            pdf.set_font("Helvetica", "", 9)
            pdf.set_xy(margin, 20)
            pdf.cell(img_w, 5, text=f"{theme_name.title()} Theme", align="C")
            try:
                pdf.image(str(filepath), x=margin, y=26, w=img_w)
            except Exception as exc:
                logger.warning("PDF image error: %s", exc)

    # Alignment audit summary page
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(margin, margin)
    pdf.cell(page_w - 2 * margin, 10, text="Alignment Audit Summary", align="C")

    pdf.set_font("Helvetica", "", 10)
    y = 28
    total = len(audit_results)
    passed = sum(1 for r in audit_results if r["pass"])
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text=f"Total controls measured: {total}")
    y += 7
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text=f"Passed: {passed}")
    y += 7
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text=f"Failed: {total - passed}")

    if total - passed > 0:
        y += 10
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_xy(margin, y)
        pdf.cell(0, 6, text="Failed controls:")
        y += 7
        pdf.set_font("Helvetica", "", 8)
        for r in audit_results:
            if not r["pass"]:
                pdf.set_xy(margin + 4, y)
                txt = f"{r['selector']} [{r['config']}]: {'; '.join(r['failures'])}"
                pdf.cell(0, 5, text=txt[:120])
                y += 5
                if y > page_h - margin:
                    pdf.add_page()
                    y = margin

    # Summary page
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(margin, margin)
    pdf.cell(page_w - 2 * margin, 10, text="POLARIS UI Review v2 -- Summary", align="C")

    pdf.set_font("Helvetica", "", 10)
    y = 28
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text=f"Total screenshots captured: {len(captured)}")
    y += 8
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text=f"Total states: {len(states)}")
    y += 8
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text=f"Failures: {len(failures)}")

    if failures:
        y += 10
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_xy(margin, y)
        pdf.cell(0, 6, text="Failed captures:")
        y += 7
        pdf.set_font("Helvetica", "", 9)
        for state_name, theme, error in failures:
            pdf.set_xy(margin + 4, y)
            pdf.cell(0, 5, text=f"- {state_name} ({theme}): {error[:100]}")
            y += 6
            if y > page_h - margin:
                pdf.add_page()
                y = margin

    y += 10
    pdf.set_font("Helvetica", "B", 11)
    if y > page_h - 40:
        pdf.add_page()
        y = margin
    pdf.set_xy(margin, y)
    pdf.cell(0, 6, text="All captured states:")
    y += 7
    pdf.set_font("Helvetica", "", 9)
    for state_name in states:
        themes_list = ", ".join(sorted(states[state_name].keys()))
        pdf.set_xy(margin + 4, y)
        pdf.cell(0, 5, text=f"- {state_name} [{themes_list}]")
        y += 6
        if y > page_h - margin:
            pdf.add_page()
            y = margin

    PDF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(PDF_OUTPUT))
    logger.info("PDF written to: %s", PDF_OUTPUT)
    return PDF_OUTPUT


# ---------------------------------------------------------------------------
# Archive v1 screenshots
# ---------------------------------------------------------------------------
def archive_v1() -> None:
    """Copy current screenshots to v1_archive before changes."""
    import shutil

    if not SCREENSHOT_DIR.exists():
        logger.info("No existing screenshots to archive")
        return

    PREVIOUS_RUN_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in SCREENSHOT_DIR.glob("*.png"):
        shutil.copy2(f, PREVIOUS_RUN_ARCHIVE_DIR / f.name)
        count += 1
    logger.info("Archived %d screenshots to %s", count, PREVIOUS_RUN_ARCHIVE_DIR)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    """Main entry point."""
    # Create all output directories
    for d in [SCREENSHOT_DIR, DIAGNOSTIC_DIR, INTERACTION_DIR, DIFF_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    logger.info("Starting POLARIS dashboard screenshot capture v2")
    logger.info("Base URL: %s", BASE_URL)
    logger.info("Screenshot dir: %s", SCREENSHOT_DIR.resolve())

    # Archive existing screenshots before capture
    archive_v1()

    # Verify server is reachable
    import urllib.request

    try:
        resp = urllib.request.urlopen(BASE_URL, timeout=5)
        if resp.status != 200:
            logger.error("Server returned status %d", resp.status)
            return 1
        logger.info("Server is reachable (HTTP %d)", resp.status)
    except Exception as exc:
        logger.error("Cannot reach server at %s: %s", BASE_URL, exc)
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT},
            device_scale_factor=2,
        )
        page = context.new_page()

        try:
            # Phase A: Diagnostics
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
            page.evaluate("""
                window.onerror = function() { return true; };
                window.addEventListener('unhandledrejection', function(e) { e.preventDefault(); });
            """)
            run_phase_a_diagnostics(page)

            # Base state captures (19 states x 2 themes)
            run_capture_sequence(page)

            # E.3: Interaction matrix
            run_interaction_capture(page)

            # E.4: Alignment audit
            run_alignment_audit(page)

            # E.6: Jump button proof
            run_jump_btn_proof(page)

        except Exception as exc:
            logger.error("Capture sequence failed: %s", exc, exc_info=True)
        finally:
            page.close()
            context.close()
            browser.close()

    # E.5: Diff generation
    generate_diffs()

    # Compile PDF
    if captured:
        pdf_path = compile_pdf()
        file_size = pdf_path.stat().st_size
        logger.info(
            "Done. PDF: %s (%d bytes, %.1f MB)",
            pdf_path.resolve(),
            file_size,
            file_size / (1024 * 1024),
        )
    else:
        logger.error("No screenshots captured. Cannot generate PDF.")
        return 1

    # Print summary
    print("\n" + "=" * 60)
    print("POLARIS UI SCREENSHOT CAPTURE v2 -- SUMMARY")
    print("=" * 60)
    print(f"Screenshots captured: {len(captured)}")
    print(f"Failures:            {len(failures)}")
    print(f"Audit controls:      {len(audit_results)}")
    audit_pass = sum(1 for r in audit_results if r["pass"])
    print(f"Audit pass rate:     {audit_pass}/{len(audit_results)}")
    print(f"PDF output:          {PDF_OUTPUT.resolve()}")
    if PDF_OUTPUT.exists():
        print(f"PDF size:            {PDF_OUTPUT.stat().st_size:,} bytes")
    if failures:
        print("\nFailed states:")
        for state_name, theme, error in failures:
            print(f"  - {state_name} ({theme}): {error[:80]}")
    if audit_results:
        audit_fail = [r for r in audit_results if not r["pass"]]
        if audit_fail:
            print(f"\nAudit failures ({len(audit_fail)}):")
            for r in audit_fail[:20]:
                print(f"  - {r['selector']} [{r['config']}]: {'; '.join(r['failures'])}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
