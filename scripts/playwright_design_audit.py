"""
POLARIS Observatory — Playwright Design Audit System (Exhaustive Visual QA).

Captures 192 screenshots (24 states x 2 themes x 4 viewports), runs 11
heuristic DOM-measurement checks, and generates before/after pixel-diff
comparisons with structured JSON + HTML reports.

Usage:
    python scripts/playwright_design_audit.py --phase before
    python scripts/playwright_design_audit.py --phase heuristics
    python scripts/playwright_design_audit.py --phase after
    python scripts/playwright_design_audit.py --phase compare
    python scripts/playwright_design_audit.py --phase full
    python scripts/playwright_design_audit.py --phase full --states S06,S07 --viewports desktop_1440
"""

import argparse
import asyncio
import base64
import json
import logging
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install")
    sys.exit(1)

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("design_audit")

# ---------------------------------------------------------------------------
# Configuration (LAW VI — from CLI args or env, no hardcoding)
# ---------------------------------------------------------------------------
DEFAULT_PORT = int(os.getenv("DESIGN_AUDIT_PORT", "8767"))
OUTPUT_DIR = Path(os.getenv(
    "DESIGN_AUDIT_OUTPUT_DIR",
    str(_PROJECT_ROOT / "outputs" / "design_audit"),
))

# ---------------------------------------------------------------------------
# State Matrix — 24 states
# ---------------------------------------------------------------------------
STATE_MATRIX: list[dict[str, Any]] = [
    {
        "id": "S01", "name": "landing_user_idle", "label": "Landing (User) — Idle",
        "mode": "user", "view": "landing",
        "setup": "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=false; updateUIVisibility()",
    },
    {
        "id": "S02", "name": "landing_user_query_filled", "label": "Landing — Query Filled",
        "mode": "user", "view": "landing",
        "setup": (
            "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=false; updateUIVisibility(); "
            "const inp = document.getElementById('landing-query-input'); if(inp){inp.value='What are the health effects of PFAS contamination in drinking water?'; inp.dispatchEvent(new Event('input'));}"
        ),
    },
    {
        "id": "S03", "name": "landing_user_depth_deep", "label": "Landing — Deep Depth",
        "mode": "user", "view": "landing",
        "setup": (
            "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=false; updateUIVisibility(); "
            "document.querySelectorAll('.depth-chip').forEach(c => c.classList.remove('active')); "
            "const deep = [...document.querySelectorAll('.depth-chip')].find(c => c.textContent.trim().toLowerCase().includes('deep')); "
            "if(deep) deep.classList.add('active');"
        ),
    },
    {
        "id": "S04", "name": "progress_user_active", "label": "User Progress — Active",
        "mode": "user", "view": "progress",
        "setup": "setViewMode('user'); state.pipelineActive=true; state.pipelineComplete=false; updateUIVisibility()",
    },
    {
        "id": "S05", "name": "complete_user_report", "label": "User Complete — Report",
        "mode": "user", "view": "complete",
        "setup": "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=true; updateUIVisibility()",
    },
    {
        "id": "S06", "name": "op_research_empty", "label": "Operator Research — Empty",
        "mode": "operator", "view": "research",
        "setup": "setViewMode('operator'); switchView('research')",
    },
    {
        "id": "S07", "name": "op_research_phase_selected", "label": "Operator Research — Phase Selected",
        "mode": "operator", "view": "research",
        "setup": (
            "setViewMode('operator'); switchView('research'); "
            "setTimeout(() => { const row = document.querySelector('.phase-row'); if(row) row.click(); }, 200)"
        ),
        "post_wait": 500,
    },
    {
        "id": "S08", "name": "op_research_telemetry_open", "label": "Operator Research — Telemetry Open",
        "mode": "operator", "view": "research",
        "setup": (
            "setViewMode('operator'); switchView('research'); "
            "setTimeout(() => { const d = document.querySelector('.rail-details'); if(d) d.open=true; }, 200)"
        ),
        "post_wait": 500,
    },
    {
        "id": "S09", "name": "op_evidence_graph", "label": "Operator Evidence — Graph",
        "mode": "operator", "view": "evidence",
        "setup": "setViewMode('operator'); switchView('evidence')",
    },
    {
        "id": "S10", "name": "op_evidence_detail_open", "label": "Operator Evidence — Detail Open",
        "mode": "operator", "view": "evidence",
        "setup": (
            "setViewMode('operator'); switchView('evidence'); "
            "setTimeout(() => { const card = document.querySelector('.ev-card'); if(card) card.click(); }, 200)"
        ),
        "post_wait": 500,
    },
    {
        "id": "S11", "name": "op_evidence_filter_gold", "label": "Operator Evidence — Gold Filter",
        "mode": "operator", "view": "evidence",
        "setup": (
            "setViewMode('operator'); switchView('evidence'); "
            "setTimeout(() => { const chip = [...document.querySelectorAll('.filter-chip')].find(c => c.textContent.trim().toLowerCase().includes('gold')); if(chip) chip.click(); }, 200)"
        ),
        "post_wait": 500,
    },
    {
        "id": "S12", "name": "op_report_body", "label": "Operator Report — Body",
        "mode": "operator", "view": "report",
        "setup": "setViewMode('operator'); switchView('report')",
    },
    {
        "id": "S13", "name": "op_memory", "label": "Operator Memory",
        "mode": "operator", "view": "memory",
        "setup": "setViewMode('operator'); switchView('memory')",
    },
    {
        "id": "S14", "name": "op_pipelines_empty", "label": "Operator Pipelines — Empty",
        "mode": "operator", "view": "pipelines",
        "setup": "setViewMode('operator'); switchView('pipelines')",
    },
    {
        "id": "S15", "name": "op_pipelines_template", "label": "Operator Pipelines — Template",
        "mode": "operator", "view": "pipelines",
        "setup": (
            "setViewMode('operator'); switchView('pipelines'); "
            "setTimeout(() => { const tpl = document.querySelector('.pipeline-tpl-card'); if(tpl) tpl.click(); }, 200)"
        ),
        "post_wait": 500,
    },
    {
        "id": "S16", "name": "op_adv_queries", "label": "Advanced — Queries",
        "mode": "operator", "view": "advanced",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"queries\"]')?.click()"
        ),
    },
    {
        "id": "S17", "name": "op_adv_sources", "label": "Advanced — Sources",
        "mode": "operator", "view": "advanced",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"sources\"]')?.click()"
        ),
    },
    {
        "id": "S18", "name": "op_adv_storm", "label": "Advanced — STORM",
        "mode": "operator", "view": "advanced",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"storm\"]')?.click()"
        ),
    },
    {
        "id": "S19", "name": "op_adv_trace", "label": "Advanced — Trace",
        "mode": "operator", "view": "advanced",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"trace\"]')?.click()"
        ),
    },
    {
        "id": "S20", "name": "op_adv_cost", "label": "Advanced — Cost",
        "mode": "operator", "view": "advanced",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"cost\"]')?.click()"
        ),
    },
    {
        "id": "S21", "name": "modal_citation", "label": "Citation Chain Modal",
        "mode": "operator", "view": "report",
        "setup": "setViewMode('operator'); switchView('report')",
        "post_navigate": "citation_modal",
    },
    {
        "id": "S22", "name": "modal_auth", "label": "Auth Modal",
        "mode": "any", "view": "auth",
        "setup": (
            "document.getElementById('auth-modal').style.display='flex'; "
            "document.getElementById('auth-modal').classList.add('visible')"
        ),
    },
    {
        "id": "S23", "name": "op_research_dense", "label": "Operator Research — Dense Layout",
        "mode": "operator", "view": "research",
        "setup": (
            "setViewMode('operator'); switchView('research'); "
            "setTimeout(() => { const btn = document.querySelector('.density-btn:not(.active)'); if(btn) btn.click(); }, 200)"
        ),
        "post_wait": 500,
    },
    {
        "id": "S24", "name": "landing_operator_idle", "label": "Operator Landing → Research",
        "mode": "operator", "view": "research",
        "setup": "setViewMode('operator'); switchView('research')",
    },
]

# State ID lookup
STATE_MAP: dict[str, dict[str, Any]] = {s["id"]: s for s in STATE_MATRIX}

# ---------------------------------------------------------------------------
# Viewports — 4 breakpoints
# ---------------------------------------------------------------------------
VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop_1440": {"width": 1440, "height": 900},
    "laptop_1024": {"width": 1024, "height": 768},
    "tablet_768": {"width": 768, "height": 1024},
    "mobile_375": {"width": 375, "height": 812},
}

THEMES = ["dark", "light"]

# ---------------------------------------------------------------------------
# Heuristic Result
# ---------------------------------------------------------------------------
@dataclass
class HeuristicResult:
    """Structured result from a single heuristic check."""
    id: str
    name: str
    passed: bool
    score: float
    threshold: float
    violations: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


# =========================================================================
# SERVER LIFECYCLE
# =========================================================================

class ServerLifecycle:
    """Start/stop live_server.py (mirrors visual_qa_audit.py:475 pattern)."""

    def __init__(self, port: int):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.log_path = OUTPUT_DIR / "server.log"

    async def start(self) -> None:
        """Start the live server and wait for it to become healthy."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        log.info("Starting live_server.py on port %d ...", self.port)
        log_file = open(self.log_path, "w")
        self.process = subprocess.Popen(
            [
                sys.executable, "-u",
                str(_PROJECT_ROOT / "scripts" / "live_server.py"),
                "--port", str(self.port),
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(_PROJECT_ROOT),
        )
        import aiohttp
        url = f"http://localhost:{self.port}/health"
        for attempt in range(30):
            await asyncio.sleep(1)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status == 200:
                            log.info("Server healthy after %d seconds", attempt + 1)
                            return
            except Exception:
                pass
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Server process exited with code {self.process.returncode}. "
                    f"Check {self.log_path}"
                )
        raise RuntimeError(f"Server did not become healthy within 30s. Check {self.log_path}")

    async def stop(self) -> None:
        """Stop the server process."""
        if self.process and self.process.poll() is None:
            log.info("Stopping server (PID %d) ...", self.process.pid)
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            log.info("Server stopped.")


# =========================================================================
# STATE NAVIGATOR
# =========================================================================

class StateNavigator:
    """Navigate to any state via page.evaluate(), with mock routes and freezing."""

    # Mock routes so the dashboard renders content in every view
    MOCK_ROUTES: dict[str, dict[str, Any]] = {
        "**/api/memory/**": {
            "status": 200,
            "content_type": "application/json",
            "body": json.dumps({
                "total_items": 42,
                "items": [
                    {"id": "m1", "content": "PFAS contamination evidence", "domain": "pfas", "confidence": 0.91},
                    {"id": "m2", "content": "Water purification methods", "domain": "water", "confidence": 0.87},
                ],
            }),
        },
        "**/api/pipelines/**": {
            "status": 200,
            "content_type": "application/json",
            "body": json.dumps({
                "templates": [{"id": "t1", "name": "Standard Research", "stages": 8}],
                "pipelines": [],
            }),
        },
        "**/api/graph/**": {
            "status": 200,
            "content_type": "application/json",
            "body": json.dumps({
                "nodes": [
                    {"id": "n1", "label": "PFAS", "group": "topic"},
                    {"id": "n2", "label": "Water", "group": "topic"},
                ],
                "edges": [{"from": "n1", "to": "n2", "weight": 0.8}],
            }),
        },
        "**/api/research/chain/**": {
            "status": 200,
            "content_type": "application/json",
            "body": json.dumps({
                "chain": [{"id": "c1", "query": "PFAS contamination", "sources": 3, "citations": 12}],
            }),
        },
    }

    def __init__(self, port: int):
        self.port = port
        self.base_url = f"http://localhost:{port}"

    async def setup_page(self, page: Page) -> None:
        """Install mock routes and freeze dynamic content on a fresh page."""
        # Freeze animations and timers
        await page.emulate_media(reduced_motion="reduce")
        await page.add_init_script("""
            const _origSetInterval = window.setInterval;
            window.setInterval = function(fn, ms, ...args) {
                if (ms >= 500) return _origSetInterval.call(window, () => {}, ms);
                return _origSetInterval.call(window, fn, ms, ...args);
            };
            const _frozenNow = 1709568000000;
            Date.now = () => _frozenNow;
            Math.random = () => 0.42;
            window._designAuditMode = true;
        """)
        # Mock API routes — Playwright calls handler(route, request),
        # so we must absorb the request arg to avoid overwriting the closure.
        for pattern, mock in self.MOCK_ROUTES.items():
            async def _make_handler(m):
                async def _handler(route):
                    await route.fulfill(
                        status=m["status"],
                        content_type=m["content_type"],
                        body=m["body"],
                    )
                return _handler
            await page.route(pattern, await _make_handler(mock))

    async def navigate_to_state(self, page: Page, state: dict[str, Any], theme: str) -> None:
        """Navigate the page to a specific state and theme."""
        # Navigate to base URL — use domcontentloaded (not networkidle)
        # because the dashboard keeps SSE/WebSocket connections open.
        await page.goto(self.base_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(500)  # let JS initialize

        # Set theme
        await page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        await page.wait_for_timeout(100)

        # Execute state setup
        setup_js = state["setup"]
        try:
            await page.evaluate(setup_js)
        except Exception as exc:
            log.warning("State setup failed for %s: %s", state["id"], exc)

        # Post-wait for states that need DOM to settle
        post_wait = state.get("post_wait", 300)
        await page.wait_for_timeout(post_wait)

        # Handle post-navigation actions
        if state.get("post_navigate") == "citation_modal":
            await self._open_citation_modal(page)

    async def _open_citation_modal(self, page: Page) -> None:
        """Open a citation chain modal if available."""
        try:
            await page.evaluate("""
                const citeLink = document.querySelector('.cite-link, .cite-ref');
                if (citeLink) citeLink.click();
            """)
            await page.wait_for_timeout(500)
        except Exception:
            log.warning("Could not open citation modal")


# =========================================================================
# SCREENSHOT CAPTURE
# =========================================================================

class ScreenshotCapture:
    """Capture and name screenshots consistently."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def screenshot_path(self, state_name: str, theme: str, viewport: str, phase: str) -> Path:
        """Generate consistent screenshot file path."""
        folder = self.output_dir / phase
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{state_name}_{theme}_{viewport}.png"

    async def capture(self, page: Page, state_name: str, theme: str,
                      viewport: str, phase: str) -> Path:
        """Take a full-page screenshot and save it."""
        path = self.screenshot_path(state_name, theme, viewport, phase)
        await page.screenshot(path=str(path), full_page=False)
        log.info("  Screenshot: %s (%d bytes)", path.name, path.stat().st_size)
        return path


# =========================================================================
# HEURISTIC ENGINE — 11 automated DOM measurements
# =========================================================================

class HeuristicEngine:
    """Run H1-H11 DOM measurement checks via page.evaluate()."""

    async def run_all(self, page: Page, viewport_name: str) -> list[HeuristicResult]:
        """Run all heuristic checks and return results."""
        results = []
        checks = [
            self.h1_touch_targets,
            self.h2_radius_system,
            self.h3_spacing_rhythm,
            self.h4_column_alignment,
            self.h5_typography_hierarchy,
            self.h6_surface_hierarchy,
            self.h7_state_clarity,
            self.h8_workflow_clarity,
            self.h9_content_density,
            self.h10_scroll_behavior,
            self.h11_visual_balance,
        ]
        for check in checks:
            try:
                result = await check(page, viewport_name)
                results.append(result)
                status = "PASS" if result.passed else "FAIL"
                log.info("  %s %s: %.0f%% (threshold %.0f%%)",
                         status, result.id, result.score * 100, result.threshold * 100)
            except Exception as exc:
                log.error("  ERROR %s: %s", check.__name__, exc)
                results.append(HeuristicResult(
                    id=check.__name__.split("_")[0].upper(),
                    name=check.__name__,
                    passed=False,
                    score=0.0,
                    threshold=0.0,
                    violations=[{"error": str(exc)}],
                ))
        return results

    # ----- H1: Touch Target Compliance -----
    async def h1_touch_targets(self, page: Page, viewport_name: str) -> HeuristicResult:
        is_mobile = "mobile" in viewport_name or "375" in viewport_name
        min_size = 44 if is_mobile else 36
        threshold = 1.0 if is_mobile else 0.95

        data = await page.evaluate(f"""(() => {{
            const selectors = 'button, input:not([type="hidden"]), [role="tab"], [role="switch"], ' +
                '.phase-row, .ev-card, .filter-chip, .seg-btn, .adv-tab-btn, ' +
                '.depth-chip, .chain-tab, .nav-btn, .view-mode-btn, .density-btn, ' +
                '.export-btn, .bookmark-btn, .detail-panel-close, .pipe-tool-btn, ' +
                '.pipeline-new-btn, .pipeline-tpl-btn, .wizard-chip, .toc-link, ' +
                '.mem-item-delete, .user-progress-cancel, .mem-refresh-btn, ' +
                '.mem-search-input, .chain-modal-close, .export-btn-audit, .auth-field';
            const isDense = document.body.classList.contains('operator-dense');
            const els = document.querySelectorAll(selectors);
            const minSize = isDense ? Math.min({min_size}, 24) : {min_size};
            let total = 0, passing = 0;
            const violations = [];
            for (const el of els) {{
                if (el.offsetParent === null) continue;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
                // Skip elements inside collapsed/hidden containers (< 12px in either dimension)
                if (rect.width < 12 || rect.height < 12) continue;
                // Skip checkbox/radio/color inputs (browser-styled, not actionable targets)
                const tag = el.tagName.toLowerCase();
                if (tag === 'input' && ['checkbox', 'radio', 'color', 'range', 'hidden'].includes(el.type)) continue;
                total++;
                const ok = rect.width >= minSize && rect.height >= minSize;
                if (ok) passing++;
                else violations.push({{
                    selector: tag + (el.className ? '.' + el.className.split(' ')[0] : ''),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    minRequired: minSize,
                }});
            }}
            return {{ total, passing, violations: violations.slice(0, 20), isDense }};
        }})()""")

        score = data["passing"] / max(data["total"], 1)
        return HeuristicResult(
            id="H1", name="Touch Target Compliance",
            passed=score >= threshold, score=score, threshold=threshold,
            violations=data["violations"],
            evidence={"total": data["total"], "passing": data["passing"], "min_size": min_size},
        )

    # ----- H2: Radius System Consistency -----
    async def h2_radius_system(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const validTokens = new Set([
                '0px', '3px', '4px', '5px', '6px', '8px', '12px', '20px', '9999px', '50%'
            ]);
            const all = document.querySelectorAll('*');
            let total = 0, onToken = 0;
            const violations = [];
            for (const el of all) {
                if (el.offsetParent === null && el !== document.body) continue;
                const r = getComputedStyle(el).borderRadius;
                if (r === '0px' || r === '') continue;
                total++;
                const corners = r.split(' ').map(v => v.trim());
                const allValid = corners.every(c => validTokens.has(c));
                if (allValid) { onToken++; }
                else if (violations.length < 15) {
                    violations.push({
                        selector: el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : ''),
                        value: r,
                    });
                }
            }
            return { total, onToken, violations };
        })()""")

        score = data["onToken"] / max(data["total"], 1)
        return HeuristicResult(
            id="H2", name="Radius System Consistency",
            passed=score >= 0.90, score=score, threshold=0.90,
            violations=data["violations"],
            evidence={"total": data["total"], "on_token": data["onToken"]},
        )

    # ----- H3: Spacing Rhythm (4px Grid) -----
    async def h3_spacing_rhythm(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const containers = document.querySelectorAll(
                '.metric-grid, .metric-card, .card, .phase-list-column, .phase-detail-column, ' +
                '.pipeline-column, .ev-card, .report-body, .report-rendered, .adv-pane, ' +
                '.filter-chips, .gate-grid, .source-card, .evidence-cards-area'
            );
            let total = 0, onGrid = 0;
            const violations = [];
            const exempt = new Set([1, 2, 3]);
            for (const el of containers) {
                if (el.offsetParent === null && el !== document.body) continue;
                const cs = getComputedStyle(el);
                const props = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
                               'marginTop', 'marginRight', 'marginBottom', 'marginLeft', 'gap'];
                for (const prop of props) {
                    const raw = cs[prop];
                    if (!raw || raw === 'normal') continue;
                    const val = parseFloat(raw);
                    if (isNaN(val) || val === 0) continue;
                    total++;
                    if (exempt.has(val) || val % 4 === 0) { onGrid++; }
                    else if (violations.length < 15) {
                        violations.push({
                            selector: el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : ''),
                            property: prop,
                            value: raw,
                        });
                    }
                }
            }
            return { total, onGrid, violations };
        })()""")

        score = data["onGrid"] / max(data["total"], 1)
        return HeuristicResult(
            id="H3", name="Spacing Rhythm (4px Grid)",
            passed=score >= 0.85 or data["total"] == 0,
            score=score, threshold=0.85,
            violations=data["violations"],
            evidence={"total": data["total"], "on_grid": data["onGrid"]},
        )

    # ----- H4: Column Alignment -----
    async def h4_column_alignment(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const columns = document.querySelectorAll(
                '.phase-list-column, .phase-detail-column, .pipeline-column, ' +
                '.evidence-cards-area, .adv-pane'
            );
            let total = 0, aligned = 0;
            const violations = [];
            const tolerance = 4;
            for (const col of columns) {
                if (col.offsetParent === null) continue;
                const children = [...col.children].filter(c => {
                    if (c.offsetParent === null) return false;
                    const r = c.getBoundingClientRect();
                    // Exclude off-screen/collapsed elements
                    return r.width > 0 && r.height > 0 && r.left >= -10;
                });
                if (children.length < 2) continue;
                const leftPositions = children.map(c => Math.round(c.getBoundingClientRect().left));
                const mode = leftPositions.sort((a,b) => a - b)[Math.floor(leftPositions.length / 2)];
                for (let i = 0; i < children.length; i++) {
                    total++;
                    const left = Math.round(children[i].getBoundingClientRect().left);
                    if (Math.abs(left - mode) <= tolerance) { aligned++; }
                    else if (violations.length < 10) {
                        violations.push({
                            column: col.className.split(' ')[0],
                            child_index: i,
                            expected_left: mode,
                            actual_left: left,
                            delta: left - mode,
                        });
                    }
                }
            }
            return { total, aligned, violations };
        })()""")

        score = data["aligned"] / max(data["total"], 1)
        return HeuristicResult(
            id="H4", name="Column Alignment",
            passed=score >= 0.95 or data["total"] == 0,
            score=score, threshold=0.95,
            violations=data["violations"],
            evidence={"total": data["total"], "aligned": data["aligned"]},
        )

    # ----- H5: Typography Hierarchy -----
    async def h5_typography_hierarchy(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const hierarchy = [
                { selector: 'h1, .report-body h1, .report-rendered h1', role: 'h1' },
                { selector: 'h2, .report-body h2, .report-rendered h2', role: 'h2' },
                { selector: 'h3, .report-body h3, .report-rendered h3', role: 'h3' },
                { selector: '.section-title', role: 'section-title' },
                { selector: '.report-body p, .report-rendered p, body', role: 'body' },
                { selector: '.label, .metric-card .label', role: 'label' },
                { selector: '.tier-badge, .nav-badge', role: 'badge' },
            ];
            const sizes = {};
            for (const level of hierarchy) {
                const el = document.querySelector(level.selector);
                if (el && el.offsetParent !== null) {
                    sizes[level.role] = parseFloat(getComputedStyle(el).fontSize);
                }
            }
            const violations = [];
            const order = ['h1', 'h2', 'h3', 'section-title', 'body', 'label', 'badge'];
            let inversions = 0;
            let comparisons = 0;
            for (let i = 0; i < order.length - 1; i++) {
                const a = order[i], b = order[i + 1];
                if (sizes[a] !== undefined && sizes[b] !== undefined) {
                    comparisons++;
                    if (sizes[a] < sizes[b]) {
                        inversions++;
                        violations.push({
                            higher: a, higher_size: sizes[a],
                            lower: b, lower_size: sizes[b],
                        });
                    }
                }
            }
            return { sizes, violations, comparisons, inversions };
        })()""")

        score = 1.0 - (data["inversions"] / max(data["comparisons"], 1))
        return HeuristicResult(
            id="H5", name="Typography Hierarchy",
            passed=data["inversions"] == 0, score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"sizes": data["sizes"], "comparisons": data["comparisons"]},
        )

    # ----- H6: Surface Hierarchy (Background Depth) -----
    async def h6_surface_hierarchy(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            function getLuminance(rgb) {
                const match = rgb.match(/\\d+/g);
                if (!match || match.length < 3) return 0;
                const [r, g, b] = match.map(Number);
                return 0.299 * r + 0.587 * g + 0.114 * b;
            }
            const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
            const surfaces = [
                { selector: 'body', role: 'bg-primary' },
                { selector: '.phase-list-column, .pipeline-column', role: 'bg-secondary' },
                { selector: '.metric-card, .ev-card, .report-body', role: 'bg-card' },
                { selector: '.phase-block.expanded, .toast, .cite-popover', role: 'bg-elevated' },
            ];
            const lums = {};
            for (const s of surfaces) {
                const el = document.querySelector(s.selector);
                if (el) {
                    const bg = getComputedStyle(el).backgroundColor;
                    lums[s.role] = getLuminance(bg);
                }
            }
            const order = ['bg-primary', 'bg-secondary', 'bg-card', 'bg-elevated'];
            let violations = [];
            let comparisons = 0;
            let correct = 0;
            const TOLERANCE = 5;  // Allow <=5 luminance delta in light themes (shadow-based depth)
            for (let i = 0; i < order.length - 1; i++) {
                const a = order[i], b = order[i + 1];
                if (lums[a] !== undefined && lums[b] !== undefined) {
                    comparisons++;
                    const delta = Math.abs(lums[a] - lums[b]);
                    if (isDark) {
                        if (lums[a] <= lums[b]) correct++;
                        else violations.push({ a, lum_a: lums[a], b, lum_b: lums[b], expected: 'a <= b (dark)' });
                    } else {
                        if (lums[a] >= lums[b] || delta <= TOLERANCE) correct++;
                        else violations.push({ a, lum_a: lums[a], b, lum_b: lums[b], delta, expected: 'a >= b (light, tolerance 5)' });
                    }
                }
            }
            return { lums, violations, comparisons, correct };
        })()""")

        score = data["correct"] / max(data["comparisons"], 1)
        return HeuristicResult(
            id="H6", name="Surface Hierarchy (Background Depth)",
            passed=len(data["violations"]) == 0, score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"luminances": data["lums"], "comparisons": data["comparisons"]},
        )

    # ----- H7: State Clarity -----
    async def h7_state_clarity(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            function getProps(el) {
                const cs = getComputedStyle(el);
                return {
                    color: cs.color,
                    backgroundColor: cs.backgroundColor,
                    borderColor: cs.borderColor || cs.borderBottomColor,
                };
            }
            function luminance(rgb) {
                const m = rgb.match(/[\\d.]+/g);
                if (!m || m.length < 3) return 0;
                return 0.299 * +m[0] + 0.587 * +m[1] + 0.114 * +m[2];
            }
            function colorDistance(rgb1, rgb2) {
                const m1 = rgb1.match(/[\\d.]+/g);
                const m2 = rgb2.match(/[\\d.]+/g);
                if (!m1 || m1.length < 3 || !m2 || m2.length < 3) return 0;
                const dr = +m1[0] - +m2[0], dg = +m1[1] - +m2[1], db = +m1[2] - +m2[2];
                return Math.sqrt(dr*dr + dg*dg + db*db);
            }
            const types = [
                { selector: '.nav-btn', activeClass: 'active' },
                { selector: '.phase-row', activeClass: 'selected' },
                { selector: '.filter-chip', activeClass: 'active' },
                { selector: '.seg-btn', activeClass: 'active' },
                { selector: '.adv-tab-btn', activeClass: 'active' },
                { selector: '.depth-chip', activeClass: 'active' },
            ];
            let total = 0, clear = 0;
            const violations = [];
            for (const t of types) {
                const els = document.querySelectorAll(t.selector);
                const defaultEl = [...els].find(e => !e.classList.contains(t.activeClass) && e.offsetParent !== null);
                const activeEl = [...els].find(e => e.classList.contains(t.activeClass) && e.offsetParent !== null);
                if (!defaultEl || !activeEl) continue;
                total++;
                const defProps = getProps(defaultEl);
                const actProps = getProps(activeEl);
                let changes = 0;
                if (defProps.color !== actProps.color) changes++;
                if (defProps.backgroundColor !== actProps.backgroundColor) changes++;
                if (defProps.borderColor !== actProps.borderColor) changes++;
                const lumDelta = Math.abs(luminance(defProps.color) - luminance(actProps.color));
                const colDist = colorDistance(defProps.color, actProps.color);
                const bgDist = colorDistance(defProps.backgroundColor, actProps.backgroundColor);
                if (changes >= 2 && (lumDelta > 30 || colDist > 80 || bgDist > 40)) { clear++; }
                else {
                    violations.push({
                        selector: t.selector,
                        changes,
                        lum_delta: Math.round(lumDelta),
                        color_distance: Math.round(colDist),
                        default_props: defProps,
                        active_props: actProps,
                    });
                }
            }
            return { total, clear, violations };
        })()""")

        score = data["clear"] / max(data["total"], 1)
        return HeuristicResult(
            id="H7", name="State Clarity",
            passed=score >= 1.0 or data["total"] == 0,
            score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"total": data["total"], "clear": data["clear"]},
        )

    # ----- H8: Workflow Clarity -----
    async def h8_workflow_clarity(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const navBtns = document.querySelectorAll('.nav-btn[data-view]');
            let total = 0, correct = 0;
            const violations = [];
            for (const btn of navBtns) {
                if (btn.offsetParent === null) continue;
                const viewName = btn.getAttribute('data-view');
                btn.click();
                total++;
                const activePane = document.querySelector('.view-pane.active');
                const activeBtn = document.querySelector('.nav-btn.active');
                const paneVisible = activePane && activePane.offsetHeight > 0;
                const paneMatches = activePane && activePane.id === 'view-' + viewName;
                const onlyOneActive = document.querySelectorAll('.nav-btn.active').length === 1;
                if (paneVisible && paneMatches && onlyOneActive) { correct++; }
                else {
                    violations.push({
                        button: viewName,
                        pane_visible: !!paneVisible,
                        pane_matches: !!paneMatches,
                        active_btn_count: document.querySelectorAll('.nav-btn.active').length,
                    });
                }
            }
            return { total, correct, violations };
        })()""")

        score = data["correct"] / max(data["total"], 1)
        return HeuristicResult(
            id="H8", name="Workflow Clarity",
            passed=score >= 1.0 or data["total"] == 0,
            score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"total": data["total"], "correct": data["correct"]},
        )

    # ----- H9: Content Density -----
    async def h9_content_density(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const vw = window.innerWidth;
            const panels = [
                { selector: '.phase-list-column', name: 'phase-list', expect_min: 0.08, expect_max: 0.22 },
                { selector: '.phase-detail-column', name: 'detail', expect_min: 0.30, expect_max: 0.65 },
                { selector: '.pipeline-column', name: 'metrics-rail', expect_min: 0.15, expect_max: 0.35 },
            ];
            let total = 0, inRange = 0;
            const violations = [];
            for (const p of panels) {
                const el = document.querySelector(p.selector);
                if (!el || el.offsetParent === null) continue;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0) continue;
                total++;
                const ratio = rect.width / vw;
                if (ratio >= p.expect_min && ratio <= p.expect_max) { inRange++; }
                else {
                    violations.push({
                        panel: p.name,
                        width_px: Math.round(rect.width),
                        ratio: Math.round(ratio * 100) / 100,
                        expected: [p.expect_min, p.expect_max],
                    });
                }
            }
            return { total, inRange, violations, viewport_width: vw };
        })()""")

        score = data["inRange"] / max(data["total"], 1)
        return HeuristicResult(
            id="H9", name="Content Density",
            passed=score >= 1.0 or data["total"] == 0,
            score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"total": data["total"], "in_range": data["inRange"],
                      "viewport_width": data["viewport_width"]},
        )

    # ----- H10: Scroll Behavior -----
    async def h10_scroll_behavior(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const scrollables = document.querySelectorAll(
                '.phase-list, .phase-detail-stream, .pipeline-column, .activity-log, ' +
                '.evidence-cards-area, .report-view, .adv-pane'
            );
            let total = 0, correct = 0;
            const violations = [];
            for (const el of scrollables) {
                if (el.offsetParent === null) continue;
                const hasOverflow = el.scrollHeight > el.clientHeight + 2;
                if (!hasOverflow) continue;
                total++;
                const cs = getComputedStyle(el);
                const hasScroll = cs.overflowY === 'auto' || cs.overflowY === 'scroll';
                const hasGutter = cs.scrollbarGutter === 'stable' || cs.scrollbarGutter === 'stable both-edges';
                if (hasScroll || hasGutter) { correct++; }
                else {
                    violations.push({
                        selector: el.className.split(' ')[0],
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        overflowY: cs.overflowY,
                        scrollbarGutter: cs.scrollbarGutter,
                    });
                }
            }
            return { total, correct, violations };
        })()""")

        score = data["correct"] / max(data["total"], 1)
        return HeuristicResult(
            id="H10", name="Scroll Behavior",
            passed=score >= 1.0 or data["total"] == 0,
            score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"total": data["total"], "correct": data["correct"]},
        )

    # ----- H11: Visual Balance (Panel Proportions) -----
    async def h11_visual_balance(self, page: Page, viewport_name: str) -> HeuristicResult:
        data = await page.evaluate("""(() => {
            const tolerance = 5;
            const checks = [];

            // Research view: 200px | 1fr | 340px
            const rv = document.querySelector('.research-view');
            if (rv && rv.offsetParent !== null) {
                const cols = getComputedStyle(rv).gridTemplateColumns;
                if (cols && cols !== 'none') {
                    const widths = cols.split(' ').map(v => parseFloat(v));
                    if (widths.length >= 3) {
                        checks.push({
                            name: 'research-phase-list',
                            expected: 200,
                            actual: Math.round(widths[0]),
                            ok: Math.abs(widths[0] - 200) <= tolerance || widths[0] <= 210,
                        });
                        checks.push({
                            name: 'research-metrics-rail',
                            expected: 340,
                            actual: Math.round(widths[2]),
                            ok: Math.abs(widths[2] - 340) <= tolerance || (widths[2] >= 280 && widths[2] <= 400),
                        });
                    }
                }
            }
            let total = checks.length;
            let passing = checks.filter(c => c.ok).length;
            const violations = checks.filter(c => !c.ok);
            return { total, passing, checks, violations };
        })()""")

        score = data["passing"] / max(data["total"], 1)
        return HeuristicResult(
            id="H11", name="Visual Balance (Panel Proportions)",
            passed=score >= 1.0 or data["total"] == 0,
            score=score, threshold=1.0,
            violations=data["violations"],
            evidence={"checks": data["checks"]},
        )


# =========================================================================
# COMPARISON ENGINE — pixel diff before/after
# =========================================================================

class ComparisonEngine:
    """Generate pixel-diff images comparing before and after screenshots."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.comparisons_dir = output_dir / "comparisons"
        self.comparisons_dir.mkdir(parents=True, exist_ok=True)

    def compare(self, before_path: Path, after_path: Path) -> dict[str, Any]:
        """Compare two screenshots and produce a diff image."""
        if not before_path.exists() or not after_path.exists():
            return {"error": "missing file", "before": str(before_path), "after": str(after_path)}

        img_before = Image.open(before_path).convert("RGB")
        img_after = Image.open(after_path).convert("RGB")

        # Resize to match if needed
        if img_before.size != img_after.size:
            img_after = img_after.resize(img_before.size, Image.LANCZOS)

        diff = ImageChops.difference(img_before, img_after)
        diff_name = f"diff_{before_path.stem}.png"
        diff_path = self.comparisons_dir / diff_name

        # Amplify diff for visibility
        amplified = diff.point(lambda x: min(255, x * 3))
        amplified.save(diff_path)

        # Calculate diff metrics
        total_pixels = img_before.size[0] * img_before.size[1]
        diff_pixels = sum(1 for px in diff.getdata() if sum(px) > 15)
        diff_ratio = diff_pixels / total_pixels if total_pixels > 0 else 0

        return {
            "before": str(before_path),
            "after": str(after_path),
            "diff": str(diff_path),
            "diff_ratio": round(diff_ratio, 4),
            "diff_pixels": diff_pixels,
            "total_pixels": total_pixels,
            "has_changes": diff_ratio > 0.001,
        }

    def compare_all(self) -> list[dict[str, Any]]:
        """Compare all matching before/after screenshots."""
        before_dir = self.output_dir / "before"
        after_dir = self.output_dir / "after"
        results = []

        if not before_dir.exists() or not after_dir.exists():
            log.warning("Missing before/ or after/ directory for comparison")
            return results

        for before_file in sorted(before_dir.glob("*.png")):
            after_file = after_dir / before_file.name
            result = self.compare(before_file, after_file)
            results.append(result)
            status = "CHANGED" if result.get("has_changes") else "SAME"
            log.info("  %s: %s (%.2f%% diff)", status, before_file.name,
                     result.get("diff_ratio", 0) * 100)

        return results


# =========================================================================
# REPORT GENERATOR — JSON + HTML output
# =========================================================================

class ReportGenerator:
    """Generate machine-readable JSON and human-readable HTML audit reports."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.report_dir = output_dir / "report"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, heuristic_results: dict[str, list[HeuristicResult]],
                 comparison_results: list[dict[str, Any]],
                 screenshot_count: int,
                 duration_seconds: float) -> tuple[Path, Path]:
        """Generate JSON and HTML reports. Returns (json_path, html_path)."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Flatten heuristics
        all_heuristics = []
        for key, results in heuristic_results.items():
            for r in results:
                all_heuristics.append({
                    "state_viewport": key,
                    **asdict(r),
                })

        # Aggregate pass/fail
        total_checks = len(all_heuristics)
        passed_checks = sum(1 for h in all_heuristics if h["passed"])

        report_data = {
            "timestamp": timestamp,
            "duration_seconds": round(duration_seconds, 1),
            "screenshot_count": screenshot_count,
            "heuristics": {
                "total": total_checks,
                "passed": passed_checks,
                "failed": total_checks - passed_checks,
                "pass_rate": round(passed_checks / max(total_checks, 1), 3),
                "details": all_heuristics,
            },
            "comparisons": {
                "total": len(comparison_results),
                "changed": sum(1 for c in comparison_results if c.get("has_changes")),
                "details": comparison_results,
            },
        }

        # Write JSON
        json_path = self.report_dir / "design_audit_report.json"
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2)
        log.info("JSON report: %s", json_path)

        # Write HTML
        html_path = self.report_dir / "design_audit_report.html"
        html = self._render_html(report_data)
        with open(html_path, "w") as f:
            f.write(html)
        log.info("HTML report: %s", html_path)

        return json_path, html_path

    def _render_html(self, data: dict) -> str:
        """Render an HTML report with embedded thumbnails."""
        h = data["heuristics"]
        c = data["comparisons"]

        # Heuristic summary rows
        heuristic_rows = ""
        for detail in h["details"]:
            status = "PASS" if detail["passed"] else "FAIL"
            bg = "#1a3a1a" if detail["passed"] else "#3a1a1a"
            color = "#34d399" if detail["passed"] else "#fb7185"
            violations_str = ""
            if detail["violations"]:
                violations_str = f' <span style="color:#a0a0ab">({len(detail["violations"])} violations)</span>'
            heuristic_rows += f"""
            <tr style="background:{bg}">
                <td style="color:{color};font-weight:700">{status}</td>
                <td>{detail["id"]}</td>
                <td>{detail["name"]}{violations_str}</td>
                <td>{detail["state_viewport"]}</td>
                <td>{detail["score"]:.0%}</td>
                <td>{detail["threshold"]:.0%}</td>
            </tr>"""

        # Comparison rows
        comparison_rows = ""
        for comp in c["details"]:
            if comp.get("error"):
                comparison_rows += f"""
                <tr style="background:#3a3a1a">
                    <td colspan="4">ERROR: {comp["error"]}</td>
                </tr>"""
                continue
            status = "CHANGED" if comp.get("has_changes") else "SAME"
            bg = "#1a2a3a" if comp.get("has_changes") else "#1a1a1a"
            before_name = Path(comp["before"]).name if comp.get("before") else "N/A"
            comparison_rows += f"""
            <tr style="background:{bg}">
                <td>{status}</td>
                <td>{before_name}</td>
                <td>{comp.get("diff_ratio", 0):.2%}</td>
                <td>{comp.get("diff_pixels", 0):,}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>POLARIS Design Audit Report</title>
<style>
    body {{ font-family: 'Inter', system-ui, sans-serif; background: #0c0c0f; color: #fafaf9; padding: 40px; max-width: 1200px; margin: 0 auto; }}
    h1 {{ font-size: 1.5rem; letter-spacing: 2px; color: #38bdf8; border-bottom: 1px solid #2a2a30; padding-bottom: 12px; }}
    h2 {{ font-size: 1.1rem; color: #a0a0ab; margin-top: 32px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
    .stat {{ background: #19191d; border: 1px solid #2a2a30; border-radius: 8px; padding: 16px; text-align: center; }}
    .stat .val {{ font-size: 1.75rem; font-weight: 700; font-family: monospace; }}
    .stat .lbl {{ font-size: 0.75rem; color: #6e6e7a; margin-top: 4px; }}
    .pass {{ color: #34d399; }}
    .fail {{ color: #fb7185; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.8125rem; margin: 12px 0; }}
    th {{ text-align: left; padding: 8px 12px; background: #111114; color: #6e6e7a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 0.6875rem; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #1f1f24; }}
    .ts {{ font-size: 0.6875rem; color: #6e6e7a; }}
</style>
</head>
<body>
<h1>POLARIS DESIGN AUDIT REPORT</h1>
<p class="ts">Generated: {data["timestamp"]} | Duration: {data["duration_seconds"]}s | Screenshots: {data["screenshot_count"]}</p>

<div class="summary">
    <div class="stat"><div class="val {'pass' if h['pass_rate'] >= 0.9 else 'fail'}">{h['pass_rate']:.0%}</div><div class="lbl">Heuristic Pass Rate</div></div>
    <div class="stat"><div class="val pass">{h['passed']}</div><div class="lbl">Checks Passed</div></div>
    <div class="stat"><div class="val fail">{h['failed']}</div><div class="lbl">Checks Failed</div></div>
    <div class="stat"><div class="val">{c['changed']}/{c['total']}</div><div class="lbl">Screenshots Changed</div></div>
</div>

<h2>Heuristic Results</h2>
<table>
<thead><tr><th>Status</th><th>ID</th><th>Check</th><th>State/Viewport</th><th>Score</th><th>Threshold</th></tr></thead>
<tbody>{heuristic_rows}</tbody>
</table>

<h2>Before/After Comparisons</h2>
<table>
<thead><tr><th>Status</th><th>Screenshot</th><th>Diff Ratio</th><th>Diff Pixels</th></tr></thead>
<tbody>{comparison_rows if comparison_rows else '<tr><td colspan="4">No comparisons available. Run --phase compare after capturing before and after.</td></tr>'}</tbody>
</table>
</body>
</html>"""


# =========================================================================
# MAIN ORCHESTRATOR
# =========================================================================

class DesignAuditRunner:
    """Main orchestrator for the design audit pipeline."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.port = args.port
        self.phase = args.phase
        self.headless = args.headless
        self.output_dir = Path(args.output)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Parse filters
        self.selected_states = self._parse_states(args.states)
        self.selected_viewports = self._parse_viewports(args.viewports)
        self.selected_themes = self._parse_themes(args.themes)

        # Components
        self.server = ServerLifecycle(self.port)
        self.navigator = StateNavigator(self.port)
        self.capture = ScreenshotCapture(self.output_dir)
        self.heuristics = HeuristicEngine()
        self.comparisons = ComparisonEngine(self.output_dir)
        self.reporter = ReportGenerator(self.output_dir)

    def _parse_states(self, states_arg: str) -> list[dict[str, Any]]:
        if states_arg == "all":
            return STATE_MATRIX
        ids = [s.strip().upper() for s in states_arg.split(",")]
        return [s for s in STATE_MATRIX if s["id"] in ids]

    def _parse_viewports(self, vp_arg: str) -> dict[str, dict[str, int]]:
        if vp_arg == "all":
            return VIEWPORTS
        names = [v.strip() for v in vp_arg.split(",")]
        return {k: v for k, v in VIEWPORTS.items() if k in names}

    def _parse_themes(self, themes_arg: str) -> list[str]:
        if themes_arg == "both":
            return THEMES
        return [themes_arg]

    async def run(self) -> int:
        """Execute the audit pipeline. Returns 0 on pass, 1 on fail."""
        start_time = time.time()
        screenshot_count = 0
        heuristic_results: dict[str, list[HeuristicResult]] = {}
        comparison_results: list[dict[str, Any]] = []

        try:
            await self.server.start()

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)

                for vp_name, vp_size in self.selected_viewports.items():
                    for theme in self.selected_themes:
                        context = await browser.new_context(
                            viewport=vp_size,
                            device_scale_factor=1,
                            color_scheme="dark" if theme == "dark" else "light",
                        )
                        page = await context.new_page()
                        await self.navigator.setup_page(page)

                        for state in self.selected_states:
                            state_label = f"{state['id']}:{state['name']}"
                            log.info("[%s] %s / %s / %s", self.phase, state_label, theme, vp_name)

                            try:
                                await self.navigator.navigate_to_state(page, state, theme)
                            except Exception as exc:
                                log.error("  Navigation failed: %s", exc)
                                continue

                            # Screenshot phases
                            if self.phase in ("before", "after", "full"):
                                await self.capture.capture(
                                    page, state["name"], theme, vp_name, self.phase
                                    if self.phase != "full" else "after"
                                )
                                screenshot_count += 1

                            # Heuristic phase
                            if self.phase in ("heuristics", "full"):
                                key = f"{state['name']}_{theme}_{vp_name}"
                                results = await self.heuristics.run_all(page, vp_name)
                                heuristic_results[key] = results

                        await context.close()

                await browser.close()

            # Comparison phase
            if self.phase in ("compare", "full"):
                comparison_results = self.comparisons.compare_all()

            # Generate report
            duration = time.time() - start_time
            json_path, html_path = self.reporter.generate(
                heuristic_results, comparison_results, screenshot_count, duration
            )

            # Summary
            total_h = sum(len(v) for v in heuristic_results.values())
            passed_h = sum(1 for v in heuristic_results.values() for r in v if r.passed)
            failed_h = total_h - passed_h

            log.info("=" * 60)
            log.info("DESIGN AUDIT COMPLETE")
            log.info("  Phase: %s", self.phase)
            log.info("  Screenshots: %d", screenshot_count)
            log.info("  Heuristics: %d passed, %d failed (of %d)", passed_h, failed_h, total_h)
            log.info("  Comparisons: %d files", len(comparison_results))
            log.info("  Duration: %.1fs", duration)
            log.info("  Report: %s", html_path)
            log.info("=" * 60)

            return 0 if failed_h == 0 else 1

        except Exception as exc:
            log.error("Audit failed: %s", exc, exc_info=True)
            return 1
        finally:
            await self.server.stop()


# =========================================================================
# CLI
# =========================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="POLARIS Design Audit — Exhaustive Visual QA System"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Server port (default: {DEFAULT_PORT})")
    parser.add_argument("--phase", choices=["before", "after", "compare", "heuristics", "full"],
                        default="full", help="Audit phase to run")
    parser.add_argument("--states", default="all",
                        help="Comma-separated state IDs (e.g. S06,S07) or 'all'")
    parser.add_argument("--viewports", default="all",
                        help="Comma-separated viewport names or 'all'")
    parser.add_argument("--themes", choices=["dark", "light", "both"], default="both",
                        help="Theme(s) to test")
    parser.add_argument("--output", default=str(OUTPUT_DIR),
                        help=f"Output directory (default: {OUTPUT_DIR})")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run headless (default: true)")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Run with visible browser")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    runner = DesignAuditRunner(args)
    return await runner.run()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
