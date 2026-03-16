"""
POLARIS Observatory — Exhaustive Visual QA Audit (WCAG 2.2 AA + Production-Grade).

Async Playwright script that:
- Manages its own server lifecycle (starts/stops live_server.py)
- Exercises ALL 15 visual states across 2 themes, 7 viewports, 3 browsers
- Runs 15 audit sections (A-O) producing structured JSON + HTML report
- Captures 200+ screenshots with perceptual hash uniqueness verification
- Outputs to outputs/visual_qa_audit/

Usage:
    python scripts/visual_qa_audit.py --port 8766
    python scripts/visual_qa_audit.py --port 8766 --sections A,B,D
    python scripts/visual_qa_audit.py --port 8766 --browser chromium
"""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Ensure project root on sys.path
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
    from PIL import Image, ImageDraw
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
log = logging.getLogger("visual_qa_audit")

# ---------------------------------------------------------------------------
# Configuration (LAW VI — from CLI args or env, no hardcoding)
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path(os.getenv(
    "VQA_OUTPUT_DIR",
    str(_PROJECT_ROOT / "outputs" / "visual_qa_audit"),
))
BASELINES_DIR = OUTPUT_DIR / "baselines"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
DIFFS_DIR = OUTPUT_DIR / "diffs"
REPORTS_DIR = OUTPUT_DIR / "reports"
CSS_DIR = _PROJECT_ROOT / "scripts" / "static" / "css"

# Axe-core CDN URL
AXE_CDN_URL = os.getenv(
    "VQA_AXE_CDN_URL",
    "https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js",
)

# Max diff pixel ratio for regression comparison
MAX_DIFF_RATIO = float(os.getenv("VQA_MAX_DIFF_RATIO", "0.01"))
# Anti-aliasing channel tolerance
CHANNEL_TOLERANCE = int(os.getenv("VQA_CHANNEL_TOLERANCE", "5"))

# Scrollbar width tolerance for overflow detection (Windows ~15px)
SCROLLBAR_TOLERANCE = int(os.getenv("VQA_SCROLLBAR_TOLERANCE", "15"))

# ---------------------------------------------------------------------------
# State Matrix (Section A.4)
# ---------------------------------------------------------------------------
STATE_MATRIX: list[dict[str, Any]] = [
    {
        "id": 1, "name": "landing_user", "label": "Landing (User)",
        "setup": "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=false; updateUIVisibility()",
    },
    {
        "id": 2, "name": "progress_user", "label": "User Progress",
        "setup": "setViewMode('user'); state.pipelineActive=true; state.pipelineComplete=false; updateUIVisibility()",
    },
    {
        "id": 3, "name": "complete_user", "label": "User Post-Complete",
        "setup": "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=true; updateUIVisibility()",
    },
    {
        "id": 4, "name": "op_research", "label": "Operator: Research",
        "setup": "setViewMode('operator'); switchView('research')",
    },
    {
        "id": 5, "name": "op_evidence", "label": "Operator: Evidence",
        "setup": "setViewMode('operator'); switchView('evidence')",
    },
    {
        "id": 6, "name": "op_report", "label": "Operator: Report",
        "setup": "setViewMode('operator'); switchView('report')",
    },
    {
        "id": 7, "name": "op_memory", "label": "Operator: Memory",
        "setup": "setViewMode('operator'); switchView('memory')",
    },
    {
        "id": 8, "name": "op_pipelines", "label": "Operator: Pipelines",
        "setup": "setViewMode('operator'); switchView('pipelines')",
    },
    {
        "id": 9, "name": "op_adv_queries", "label": "Adv: Queries",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"queries\"]')?.click()"
        ),
    },
    {
        "id": 10, "name": "op_adv_sources", "label": "Adv: Sources",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"sources\"]')?.click()"
        ),
    },
    {
        "id": 11, "name": "op_adv_storm", "label": "Adv: STORM",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"storm\"]')?.click()"
        ),
    },
    {
        "id": 12, "name": "op_adv_trace", "label": "Adv: Trace",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"trace\"]')?.click()"
        ),
    },
    {
        "id": 13, "name": "op_adv_cost", "label": "Adv: Cost",
        "setup": (
            "setViewMode('operator'); switchView('advanced'); "
            "document.querySelector('.adv-tab-btn[data-adv=\"cost\"]')?.click()"
        ),
    },
    {
        "id": 14, "name": "modal_citation", "label": "Citation Chain Modal",
        "setup": "setViewMode('operator'); switchView('report')",
        "post_navigate": "citation_modal",
    },
    {
        "id": 15, "name": "modal_auth", "label": "Auth Modal",
        "setup": (
            "document.getElementById('auth-modal').style.display='flex'; "
            "document.getElementById('auth-modal').classList.add('visible')"
        ),
    },
]

# ---------------------------------------------------------------------------
# Viewports (Section H.1)
# ---------------------------------------------------------------------------
VIEWPORTS: dict[str, dict[str, int]] = {
    "mobile_375": {"width": 375, "height": 812},
    "mobile_390": {"width": 390, "height": 844},
    "tablet_768": {"width": 768, "height": 1024},
    "laptop_1024": {"width": 1024, "height": 768},
    "tablet_1024": {"width": 1024, "height": 768},
    "desktop_1440": {"width": 1440, "height": 900},
    "ultrawide_1920": {"width": 1920, "height": 1080},
    "ultrawide_2560": {"width": 2560, "height": 1440},
}

# Subset for base screenshot capture (4 standard breakpoints — TRAP-5 fix)
_base_vp_env = os.getenv("VQA_BASE_VIEWPORTS", "desktop_1440,laptop_1024,tablet_768,mobile_375")
BASE_VIEWPORTS = [v.strip() for v in _base_vp_env.split(",")]

THEMES = ["dark", "light"]

BROWSERS_SUPPORTED = ["chromium", "firefox", "webkit"]

# ---------------------------------------------------------------------------
# Element discovery views for dynamic DOM crawling (Section E — Upgrade 1)
# ---------------------------------------------------------------------------
ELEMENT_DISCOVERY_VIEWS: list[dict[str, str]] = [
    {"name": "landing_user", "setup": "setViewMode('user'); state.pipelineActive=false; state.pipelineComplete=false; updateUIVisibility()"},
    {"name": "op_research", "setup": "setViewMode('operator'); switchView('research')"},
    {"name": "op_evidence", "setup": "setViewMode('operator'); switchView('evidence')"},
    {"name": "op_report", "setup": "setViewMode('operator'); switchView('report')"},
    {"name": "op_memory", "setup": "setViewMode('operator'); switchView('memory')"},
    {"name": "op_pipelines", "setup": "setViewMode('operator'); switchView('pipelines')"},
    {
        "name": "op_adv_queries",
        "setup": "setViewMode('operator'); switchView('advanced'); document.querySelector('.adv-tab-btn[data-adv=\"queries\"]')?.click()",
    },
    {
        "name": "op_adv_sources",
        "setup": "setViewMode('operator'); switchView('advanced'); document.querySelector('.adv-tab-btn[data-adv=\"sources\"]')?.click()",
    },
    {
        "name": "op_adv_storm",
        "setup": "setViewMode('operator'); switchView('advanced'); document.querySelector('.adv-tab-btn[data-adv=\"storm\"]')?.click()",
    },
    {
        "name": "op_adv_trace",
        "setup": "setViewMode('operator'); switchView('advanced'); document.querySelector('.adv-tab-btn[data-adv=\"trace\"]')?.click()",
    },
]

# Max interactive elements to test per view (prevents runtime explosion)
VQA_MAX_ELEMENTS_PER_VIEW = int(os.getenv("VQA_MAX_ELEMENTS_PER_VIEW", "50"))

# Elements expected to have :focus-visible (Section D.1)
EXPECTED_FOCUS_VISIBLE = {
    ".nav-btn", ".seg-btn", ".adv-tab-btn", ".filter-chip", ".trace-chip",
    ".export-btn", ".ev-card", ".example-card", ".depth-chip", ".view-mode-btn",
    ".detail-panel-close", ".landing-submit-btn", ".user-progress-cancel",
    ".chain-tab", ".pipeline-tpl-card", ".pipe-tool-btn", ".wizard-chip",
    ".wizard-send-btn", ".conflict-nav-btn", ".storm-toggle", ".campaign-card",
    ".config-panel-close",
}

# Elements known to be MISSING :focus-visible (Section D.2)
EXPECTED_MISSING_FOCUS = {
    "#theme-toggle", "#auth-button", "#graph-reset-btn", "#pipeline-new-btn",
    "#wizard-input", "#campaign-submit-btn", "#campaign-form-cancel",
    ".auth-modal-close", "#chk-autotab", "#graph-min-agree",
    "#landing-query-input",
}

# ---------------------------------------------------------------------------
# CSS files to scan (Section J)
# ---------------------------------------------------------------------------
CSS_FILES = [
    "base.css", "layout.css", "components.css", "report.css",
    "evidence.css", "operator.css", "citation_chain.css", "pipelines.css",
]

# ---------------------------------------------------------------------------
# API Mock Payloads (Section A.3)
# ---------------------------------------------------------------------------
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
    "**/api/research/status": {
        "status": 200,
        "content_type": "application/json",
        "body": json.dumps({"status": "idle", "pipeline_active": False}),
    },
    "**/api/events": {
        "status": 200,
        "content_type": "text/event-stream",
        "body": "data: {\"type\": \"heartbeat\"}\n\n",
    },
    "**/api/snapshot": {
        "status": 200,
        "content_type": "application/json",
        "body": json.dumps({"events": {}, "stats": {}}),
    },
    "**/api/research/history": {
        "status": 200,
        "content_type": "application/json",
        "body": json.dumps({"results": []}),
    },
    "**/api/campaigns": {
        "status": 200,
        "content_type": "application/json",
        "body": json.dumps({"campaigns": []}),
    },
    "**/api/documents/list": {
        "status": 200,
        "content_type": "application/json",
        "body": json.dumps({"documents": []}),
    },
}

# Deterministic research result fixture for Report/Evidence views
DETERMINISTIC_RESULT = {
    "vector_id": "vqa_test_001",
    "query": "What are the most effective PFAS remediation techniques?",
    "status": "complete",
    "report": {
        "title": "PFAS Remediation Techniques: A Comprehensive Review",
        "sections": [
            {
                "title": "Introduction",
                "content": (
                    "Per- and polyfluoroalkyl substances (PFAS) represent one of the most "
                    "persistent environmental contaminants of the 21st century [1]. This report "
                    "examines current remediation approaches including granular activated carbon "
                    "(GAC), ion exchange resins, and emerging electrochemical methods [2][3]."
                ),
            },
            {
                "title": "Activated Carbon Adsorption",
                "content": (
                    "Granular activated carbon (GAC) remains the most widely deployed treatment "
                    "technology for PFAS removal, achieving >90% removal efficiency for long-chain "
                    "PFAS compounds [4]. However, short-chain PFAS (C4-C6) show significantly "
                    "lower adsorption rates, typically 40-60% [5][6]."
                ),
            },
            {
                "title": "Ion Exchange Treatment",
                "content": (
                    "Single-use ion exchange resins have demonstrated superior performance for "
                    "short-chain PFAS compared to GAC, with removal rates exceeding 95% across "
                    "all chain lengths [7][8]. The primary limitation is cost: IX treatment runs "
                    "approximately 2-3x the operational cost of GAC systems [9]."
                ),
            },
        ],
        "bibliography": [
            {"id": 1, "title": "PFAS Treatment in Drinking Water", "url": "https://example.com/1", "domain": "epa.gov"},
            {"id": 2, "title": "GAC for PFAS Removal", "url": "https://example.com/2", "domain": "sciencedirect.com"},
            {"id": 3, "title": "Electrochemical PFAS Destruction", "url": "https://example.com/3", "domain": "nature.com"},
        ],
        "word_count": 2847,
        "citation_count": 24,
        "faithfulness": 0.89,
    },
    "evidence": [
        {
            "id": "ev_001", "claim": "GAC achieves >90% removal for long-chain PFAS",
            "source": "epa.gov", "tier": "gold", "relevance": 0.95,
            "is_faithful": True, "perspective": "regulatory",
        },
        {
            "id": "ev_002", "claim": "Short-chain PFAS adsorption rates 40-60%",
            "source": "sciencedirect.com", "tier": "silver", "relevance": 0.88,
            "is_faithful": True, "perspective": "academic",
        },
        {
            "id": "ev_003", "claim": "IX resins exceed 95% removal across chain lengths",
            "source": "nature.com", "tier": "gold", "relevance": 0.92,
            "is_faithful": True, "perspective": "academic",
        },
    ],
    "sources": [
        {"url": "https://epa.gov/pfas", "domain": "epa.gov", "title": "EPA PFAS Overview", "status": "fetched"},
        {"url": "https://sciencedirect.com/pfas-gac", "domain": "sciencedirect.com", "title": "GAC Treatment Study", "status": "fetched"},
        {"url": "https://nature.com/pfas-ix", "domain": "nature.com", "title": "IX Resin Performance", "status": "fetched"},
    ],
}


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def _ensure_dirs() -> None:
    """Create all output directories."""
    for d in [OUTPUT_DIR, BASELINES_DIR, SCREENSHOTS_DIR, DIFFS_DIR, REPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _perceptual_hash(img_bytes: bytes, hash_size: int = 16) -> str:
    """Compute a perceptual hash (16x16 grayscale average hash) of an image."""
    img = Image.open(io.BytesIO(img_bytes)).convert("L").resize(
        (hash_size, hash_size), Image.LANCZOS,
    )
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    # Convert binary string to hex
    return hex(int(bits, 2))[2:].zfill(hash_size * hash_size // 4)


def _pixel_diff(
    img_a_bytes: bytes, img_b_bytes: bytes, tolerance: int = CHANNEL_TOLERANCE,
) -> tuple[float, Optional[bytes]]:
    """Compare two images pixel-by-pixel with channel tolerance.

    Returns (diff_ratio, diff_image_png_bytes_or_None).
    """
    img_a = Image.open(io.BytesIO(img_a_bytes)).convert("RGBA")
    img_b = Image.open(io.BytesIO(img_b_bytes)).convert("RGBA")

    if img_a.size != img_b.size:
        return 1.0, None

    w, h = img_a.size
    px_a = img_a.load()
    px_b = img_b.load()
    total = w * h
    diff_count = 0
    diff_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    diff_px = diff_img.load()

    for y in range(h):
        for x in range(w):
            ra, ga, ba, aa = px_a[x, y]
            rb, gb, bb, ab = px_b[x, y]
            if (
                abs(ra - rb) > tolerance
                or abs(ga - gb) > tolerance
                or abs(ba - bb) > tolerance
                or abs(aa - ab) > tolerance
            ):
                diff_count += 1
                diff_px[x, y] = (255, 0, 0, 180)  # Red overlay
            else:
                # Dimmed original
                diff_px[x, y] = (ra // 3, ga // 3, ba // 3, 255)

    ratio = diff_count / total if total > 0 else 0.0
    buf = io.BytesIO()
    diff_img.save(buf, format="PNG")
    return ratio, buf.getvalue()


def _img_to_base64(img_bytes: bytes) -> str:
    """Convert PNG bytes to a data URI for embedding in HTML."""
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


# =========================================================================
# SERVER LIFECYCLE
# =========================================================================

class ServerManager:
    """Manage the live_server.py subprocess."""

    def __init__(self, port: int):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.log_path = OUTPUT_DIR / "server.log"

    async def start(self) -> None:
        """Start the live server and wait for it to be healthy."""
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
        # Wait for server to respond
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
        raise RuntimeError(f"Server did not become healthy within 30 seconds. Check {self.log_path}")

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
# PAGE SETUP HELPERS
# =========================================================================

async def freeze_dynamic_content(page: Page) -> None:
    """Freeze all dynamic counters and timers for deterministic screenshots.

    Must be called BEFORE page.goto().
    """
    await page.emulate_media(reduced_motion="reduce")
    await page.add_init_script("""
        // Intercept setInterval to block timer-based DOM updates (>=500ms)
        const _origSetInterval = window.setInterval;
        window.setInterval = function(fn, ms, ...args) {
            if (ms >= 500) return _origSetInterval.call(window, () => {}, ms);
            return _origSetInterval.call(window, fn, ms, ...args);
        };

        // Freeze Date.now() for deterministic timestamps
        const _frozenNow = 1709568000000;  // 2024-03-04T16:00:00Z
        Date.now = () => _frozenNow;
        const _OrigDate = Date;
        const _FrozenDate = function(...args) {
            if (args.length === 0) return new _OrigDate(_frozenNow);
            return new _OrigDate(...args);
        };
        _FrozenDate.now = () => _frozenNow;
        _FrozenDate.parse = _OrigDate.parse;
        _FrozenDate.UTC = _OrigDate.UTC;
        _FrozenDate.prototype = _OrigDate.prototype;

        // Freeze Math.random for deterministic rendering
        Math.random = () => 0.42;

        window._visualTestMode = true;
    """)


async def apply_frozen_values(page: Page) -> None:
    """Set deterministic text values AFTER page has loaded."""
    await page.evaluate("""
        document.querySelectorAll('.elapsed-time').forEach(e => e.textContent = '00:05:23');
        document.querySelectorAll('.event-count').forEach(e => e.textContent = '247');
        document.querySelectorAll('.cost-display').forEach(e => e.textContent = '$1.31');
        document.querySelectorAll('.evidence-counter').forEach(e => e.textContent = '156');
        document.querySelectorAll('.source-counter').forEach(e => e.textContent = '47');
        // Header stats
        const el = document.getElementById('elapsed-time');
        if (el) el.textContent = '00:05:23';
        const ec = document.getElementById('event-counter');
        if (ec) ec.textContent = '247';
        const tc = document.getElementById('total-cost');
        if (tc) tc.textContent = '$1.31';
    """)


def _make_route_handler(resp: dict[str, Any]):
    """Factory to create a route handler with properly captured response data.

    Playwright route callbacks receive (route, request) as two positional args.
    A naive lambda ``lambda route, resp=response: ...`` would have ``resp``
    overwritten by the ``request`` positional arg.  This factory avoids that.
    """
    async def handler(route):
        await route.fulfill(
            status=resp["status"],
            content_type=resp["content_type"],
            body=resp["body"],
        )
    return handler


async def setup_mock_routes(page: Page) -> None:
    """Install API route mocks to prevent real server calls."""
    for pattern, response in MOCK_ROUTES.items():
        await page.route(pattern, _make_route_handler(response))


async def inject_deterministic_result(page: Page) -> None:
    """Inject a deterministic research result into the page state."""
    result_json = json.dumps(DETERMINISTIC_RESULT)
    await page.evaluate(f"""
        (function() {{
            const result = {result_json};
            // Set pipeline state
            state.pipelineComplete = true;
            state.pipelineActive = false;
            state.currentResult = result;

            // Populate report view
            const body = document.getElementById('report-body');
            if (body) {{
                const empty = document.getElementById('report-empty');
                if (empty) empty.style.display = 'none';
                let html = '<h1>' + result.report.title + '</h1>';
                result.report.sections.forEach(function(sec) {{
                    html += '<h2>' + sec.title + '</h2><p>' + sec.content + '</p>';
                }});
                body.innerHTML = html;
            }}

            // Populate evidence cards
            const cardList = document.getElementById('evidence-card-list');
            if (cardList) {{
                const empty = document.getElementById('graph-empty');
                if (empty) empty.style.display = 'none';
                let evHtml = '';
                result.evidence.forEach(function(ev) {{
                    evHtml += '<div class="ev-card" data-tier="' + ev.tier + '" tabindex="0">'
                        + '<div class="ev-card-tier tier-' + ev.tier + '">' + ev.tier.toUpperCase() + '</div>'
                        + '<div class="ev-card-claim">' + ev.claim + '</div>'
                        + '<div class="ev-card-source">' + ev.source + '</div>'
                        + '</div>';
                }});
                cardList.innerHTML = evHtml;
            }}

            // Set badge count
            const badge = document.getElementById('badge-evidence');
            if (badge) badge.textContent = String(result.evidence.length);
        }})();
    """)


async def navigate_to_state(page: Page, state_entry: dict[str, Any]) -> None:
    """Navigate the page to a specific visual state.

    Supports ``post_navigate`` key for states that need Playwright Python API
    interaction after the JS setup (e.g., clicking elements, waiting for modals).
    This avoids the Playwright trap where page.evaluate() returns immediately
    from JS setTimeout, causing screenshots before animations complete.
    """
    setup_js = state_entry["setup"]
    try:
        await page.evaluate(setup_js)
    except Exception as exc:
        log.warning("State setup '%s' raised: %s", state_entry["name"], exc)
    await page.wait_for_timeout(500)

    # Post-navigate actions using Playwright Python API (TRAP 1 fix)
    post_action = state_entry.get("post_navigate")
    if post_action == "citation_modal":
        try:
            # Inject and show citation chain modal directly (cite-link may not
            # exist in the deterministic report content)
            await page.evaluate("""
                (function() {
                    var modal = document.getElementById('citation-chain-modal');
                    if (!modal) {
                        modal = document.createElement('div');
                        modal.id = 'citation-chain-modal';
                        modal.className = 'chain-modal-overlay';
                        modal.innerHTML = '<div class="chain-modal">' +
                            '<div class="chain-modal-header">' +
                            '<span class="chain-modal-title">Citation [1]: Water Filtration Evidence</span>' +
                            '<button class="chain-modal-close" aria-label="Close">&times;</button>' +
                            '</div>' +
                            '<div class="chain-modal-body">' +
                            '<div class="chain-tabs">' +
                            '<button class="chain-tab active" data-mode="citation">Citation</button>' +
                            '<button class="chain-tab" data-mode="mindmap">Mindmap</button>' +
                            '</div>' +
                            '<div class="chain-evidence-card">' +
                            '<div class="chain-evidence-text">Recent studies demonstrate that activated carbon filtration removes 95% of chlorine and 85% of organic contaminants from municipal water supplies.</div>' +
                            '<div class="chain-tier-badge tier-gold">GOLD</div>' +
                            '</div></div></div>';
                        document.body.appendChild(modal);
                    }
                    modal.style.display = 'flex';
                })()
            """)
            await page.wait_for_timeout(300)
        except Exception as exc:
            log.warning("Citation modal post-navigate failed: %s", exc)


async def prepare_page_for_screenshot(page: Page) -> None:
    """Common preparation before taking any screenshot."""
    # Force content-visibility visible (Blind Spot 5)
    await page.add_style_tag(
        content="* { content-visibility: visible !important; }"
    )
    # Wait for web fonts with 3s timeout (Google Fonts can stall in headless)
    try:
        await page.evaluate(
            "Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))])"
        )
    except Exception:
        pass  # Font timeout is non-fatal — fallback fonts are acceptable
    # Wait for images with 2s timeout
    try:
        await page.evaluate("""
            Promise.race([
                Promise.all(
                    Array.from(document.images)
                        .filter(img => !img.complete)
                        .map(img => new Promise(res => { img.onload = img.onerror = res; }))
                ),
                new Promise(r => setTimeout(r, 2000))
            ])
        """)
    except Exception:
        pass  # Image timeout is non-fatal


async def safe_goto(page: Page, url: str, timeout: int = 15000) -> None:
    """Navigate to URL and wait for JS modules to initialize.

    Uses domcontentloaded (not networkidle) because SSE connections keep
    the network active indefinitely.  Adds a 800ms settle time for the
    16 JS modules to finish their DOMContentLoaded handlers.
    """
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    await page.wait_for_timeout(800)


async def full_page_screenshot(page: Page, path: Path) -> bytes:
    """Take a full-page screenshot and return the bytes."""
    await prepare_page_for_screenshot(page)
    img_bytes = await page.screenshot(full_page=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(img_bytes)
    return img_bytes


async def element_clip_screenshot(
    page: Page, selector: str, padding: int = 15,
) -> Optional[bytes]:
    """Screenshot an element via expanded bounding-box clip (Trap 2 fix).

    Returns None if the element is off-screen, invisible, or has zero area.
    """
    el = page.locator(selector).first
    if await el.count() == 0:
        return None
    try:
        box = await el.bounding_box()
    except Exception:
        return None
    if not box or box["width"] <= 0 or box["height"] <= 0:
        return None

    vp = page.viewport_size or {"width": 1440, "height": 900}

    # Compute clip with padding, clamped to viewport
    x = max(0, box["x"] - padding)
    y = max(0, box["y"] - padding)
    w = min(box["width"] + 2 * padding, vp["width"] - x)
    h = min(box["height"] + 2 * padding, vp["height"] - y)

    # Skip if element is off-screen or clip would be empty
    if w <= 0 or h <= 0 or x >= vp["width"] or y >= vp["height"]:
        return None

    try:
        return await page.screenshot(clip={"x": x, "y": y, "width": w, "height": h})
    except Exception:
        return None  # Graceful fallback for edge cases


# =========================================================================
# SECTION A: Test Infrastructure — Navigate All States + Uniqueness
# =========================================================================

async def section_a_navigation(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section A: Navigate all 15 states, capture screenshots, verify uniqueness."""
    log.info("=== SECTION A: Navigation + Uniqueness ===")
    results: dict[str, Any] = {
        "section": "A_navigation",
        "states_tested": 0,
        "screenshots_captured": 0,
        "unique_states": 0,
        "duplicate_pairs": [],
        "state_details": [],
        "pass": False,
    }

    hashes: dict[str, list[str]] = defaultdict(list)
    captured = 0

    for theme in THEMES:
        for vp_name in BASE_VIEWPORTS:
            vp = VIEWPORTS[vp_name]
            await page.set_viewport_size(vp)

            # Load page ONCE per theme+viewport (avoids 60 CDN round-trips)
            await safe_goto(page, base_url)
            await apply_frozen_values(page)
            await inject_deterministic_result(page)
            await page.evaluate(f"""
                document.documentElement.setAttribute('data-theme', '{theme}');
                localStorage.setItem('polaris-theme', '{theme}');
            """)
            await page.wait_for_timeout(200)

            for state_entry in STATE_MATRIX:
                # Switch state via JS (no page reload)
                await navigate_to_state(page, state_entry)

                # Capture screenshot
                fname = f"{state_entry['name']}_{theme}_{vp_name}.png"
                fpath = SCREENSHOTS_DIR / fname
                img_bytes = await full_page_screenshot(page, fpath)
                captured += 1
                log.info("  [A] %s (%d/%d)", fname, captured, len(STATE_MATRIX) * len(THEMES) * len(BASE_VIEWPORTS))

                # Compute perceptual hash
                phash = _perceptual_hash(img_bytes)
                hash_key = f"{theme}_{vp_name}"
                hashes[hash_key].append((state_entry["name"], phash, img_bytes))

                results["state_details"].append({
                    "state": state_entry["name"],
                    "theme": theme,
                    "viewport": vp_name,
                    "file": fname,
                    "phash": phash,
                    "size_bytes": len(img_bytes),
                })

    results["screenshots_captured"] = captured
    results["states_tested"] = len(STATE_MATRIX)

    # Check for duplicate hashes within same theme+viewport
    # When hashes match, confirm with pixel_diff to eliminate false positives
    # (pHash at 16×16 can produce identical hashes for visually distinct states)
    duplicates = []
    unique_count = 0
    for key, hash_list in hashes.items():
        seen: dict[str, tuple[str, bytes]] = {}
        for name, phash, img_data in hash_list:
            if phash in seen:
                prev_name, prev_img = seen[phash]
                diff_ratio, _ = _pixel_diff(prev_img, img_data)
                if diff_ratio < 0.01:
                    # Less than 1% pixel difference → truly duplicate
                    duplicates.append({
                        "context": key,
                        "state_a": prev_name,
                        "state_b": name,
                        "phash": phash,
                        "pixel_diff": round(diff_ratio, 4),
                    })
                else:
                    # pHash false positive — images are visually different
                    log.info(
                        "  [A] pHash match but %.1f%% pixel diff: %s vs %s (%s) — not duplicate",
                        diff_ratio * 100, prev_name, name, key,
                    )
                    unique_count += 1
            else:
                seen[phash] = (name, img_data)
                unique_count += 1

    results["unique_states"] = unique_count
    results["duplicate_pairs"] = duplicates
    results["pass"] = len(duplicates) == 0

    log.info(
        "Section A: %d screenshots, %d unique, %d duplicates",
        captured, unique_count, len(duplicates),
    )
    return results


# =========================================================================
# SECTION B: Automated WCAG 2.2 AA — axe-core Injection
# =========================================================================

async def _inject_axe_core(page: Page) -> bool:
    """Inject axe-core into the page. Returns True if successful."""
    try:
        # Check if axe is already loaded
        has_axe = await page.evaluate("typeof window.axe !== 'undefined'")
        if has_axe:
            return True

        # Inject via CDN
        await page.add_script_tag(url=AXE_CDN_URL)
        await page.wait_for_timeout(1000)
        has_axe = await page.evaluate("typeof window.axe !== 'undefined'")
        return has_axe
    except Exception as exc:
        log.warning("Failed to inject axe-core: %s", exc)
        return False


async def _run_axe_scan(page: Page) -> dict[str, Any]:
    """Run axe-core accessibility scan and return results."""
    # Force content-visibility visible before scan (Blind Spot 5)
    await page.add_style_tag(
        content="* { content-visibility: visible !important; }"
    )
    await page.wait_for_timeout(200)

    try:
        results = await page.evaluate("""
            axe.run(document, {
                runOnly: {
                    type: 'tag',
                    values: ['wcag2a', 'wcag2aa', 'wcag22aa']
                },
                resultTypes: ['violations', 'incomplete']
            }).then(r => ({
                violations: r.violations.map(v => ({
                    id: v.id,
                    impact: v.impact,
                    description: v.description,
                    helpUrl: v.helpUrl,
                    tags: v.tags,
                    nodes_count: v.nodes.length,
                    nodes: v.nodes.slice(0, 10).map(n => ({
                        html: n.html.substring(0, 200),
                        target: n.target,
                        failureSummary: n.failureSummary
                    }))
                })),
                incomplete: r.incomplete.map(v => ({
                    id: v.id,
                    impact: v.impact,
                    description: v.description,
                    nodes_count: v.nodes.length,
                })),
                passes_count: r.passes.length,
                violations_count: r.violations.length,
                incomplete_count: r.incomplete.length,
            }))
        """)
        return results
    except Exception as exc:
        log.warning("axe-core scan failed: %s", exc)
        return {"error": str(exc), "violations": [], "incomplete": []}


async def section_b_wcag(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section B: Run axe-core WCAG 2.2 AA audit across states and themes."""
    log.info("=== SECTION B: WCAG 2.2 AA (axe-core) ===")
    results: dict[str, Any] = {
        "section": "B_axe_wcag",
        "total_runs": 0,
        "total_violations": 0,
        "critical_count": 0,
        "serious_count": 0,
        "moderate_count": 0,
        "minor_count": 0,
        "scans": [],
        "pass": False,
    }

    # Subset of states to scan (all 15 x 2 themes = 30 runs)
    states_to_scan = STATE_MATRIX

    for theme in THEMES:
        # Load page ONCE per theme
        await page.set_viewport_size(VIEWPORTS["desktop_1440"])
        await safe_goto(page, base_url)
        await apply_frozen_values(page)
        await inject_deterministic_result(page)
        await page.evaluate(f"""
            document.documentElement.setAttribute('data-theme', '{theme}');
        """)
        await page.wait_for_timeout(200)

        for state_entry in states_to_scan:
            await navigate_to_state(page, state_entry)

            # Inject axe-core
            if not await _inject_axe_core(page):
                results["scans"].append({
                    "state": state_entry["name"],
                    "theme": theme,
                    "error": "Failed to inject axe-core",
                })
                continue

            scan = await _run_axe_scan(page)
            results["total_runs"] += 1

            # Count by impact
            for v in scan.get("violations", []):
                impact = v.get("impact", "minor")
                if impact == "critical":
                    results["critical_count"] += 1
                elif impact == "serious":
                    results["serious_count"] += 1
                elif impact == "moderate":
                    results["moderate_count"] += 1
                else:
                    results["minor_count"] += 1

            results["total_violations"] += scan.get("violations_count", 0)
            results["scans"].append({
                "state": state_entry["name"],
                "theme": theme,
                "violations_count": scan.get("violations_count", 0),
                "incomplete_count": scan.get("incomplete_count", 0),
                "passes_count": scan.get("passes_count", 0),
                "violations": scan.get("violations", []),
            })

    results["pass"] = results["critical_count"] == 0
    log.info(
        "Section B: %d runs, %d violations (C:%d S:%d M:%d m:%d)",
        results["total_runs"], results["total_violations"],
        results["critical_count"], results["serious_count"],
        results["moderate_count"], results["minor_count"],
    )
    return results


# =========================================================================
# SECTION D: Focus Indicator Audit
# =========================================================================

async def section_d_focus(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section D: Tab through elements and verify focus visibility."""
    log.info("=== SECTION D: Focus Indicator Audit ===")
    results: dict[str, Any] = {
        "section": "D_focus_indicators",
        "elements_tested": 0,
        "visible_focus": 0,
        "invisible_focus": 0,
        "missing_focus_elements": [],
        "pass": False,
    }

    await page.set_viewport_size(VIEWPORTS["desktop_1440"])
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await inject_deterministic_result(page)
    await page.evaluate("setViewMode('operator'); switchView('research')")
    await page.wait_for_timeout(500)
    await prepare_page_for_screenshot(page)

    # Disable sticky headers during focus audit (Trap 2)
    await page.add_style_tag(
        content=".app-header, .nav-bar { position: relative !important; z-index: 0 !important; }"
    )

    # Capture baseline (no focus) full page
    baseline_bytes = await page.screenshot(full_page=True)

    focused_elements: list[dict[str, Any]] = []

    # Tab through elements (bounded loop — Trap 1)
    for i in range(100):
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(50)

        focused_tag = await page.evaluate("document.activeElement?.tagName || 'BODY'")
        if focused_tag == "BODY" and i > 5:
            break  # Cycled back

        focused_info = await page.evaluate("""
            (() => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                const box = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return {
                    tag: el.tagName,
                    id: el.id || '',
                    className: el.className?.toString?.() || '',
                    selector: el.id ? '#' + el.id : (el.className ? '.' + el.className.split(' ')[0] : el.tagName),
                    outlineStyle: cs.outlineStyle,
                    outlineWidth: cs.outlineWidth,
                    outlineColor: cs.outlineColor,
                    boxShadow: cs.boxShadow,
                    x: box.x, y: box.y, w: box.width, h: box.height,
                };
            })()
        """)

        if not focused_info:
            continue

        results["elements_tested"] += 1

        # Take a clip of the focused element area
        vp = page.viewport_size or {"width": 1440, "height": 900}
        padding = 15
        clip = {
            "x": max(0, focused_info["x"] - padding),
            "y": max(0, focused_info["y"] - padding),
            "width": min(focused_info["w"] + 2 * padding, vp["width"]),
            "height": min(focused_info["h"] + 2 * padding, vp["height"]),
        }
        # Bounds check
        if clip["x"] + clip["width"] > vp["width"]:
            clip["width"] = vp["width"] - clip["x"]
        if clip["y"] + clip["height"] > vp["height"]:
            clip["height"] = vp["height"] - clip["y"]
        if clip["width"] <= 0 or clip["height"] <= 0:
            continue

        try:
            focused_screenshot = await page.screenshot(clip=clip)
        except Exception:
            continue

        # Check if focus indicator is visible via outline/boxShadow
        has_visible_outline = (
            focused_info["outlineStyle"] not in ("none", "")
            and focused_info["outlineWidth"] not in ("0px", "0", "")
        )
        has_box_shadow = focused_info["boxShadow"] not in ("none", "")
        has_focus_indicator = has_visible_outline or has_box_shadow

        if has_focus_indicator:
            results["visible_focus"] += 1
        else:
            results["invisible_focus"] += 1
            results["missing_focus_elements"].append({
                "selector": focused_info["selector"],
                "tag": focused_info["tag"],
                "id": focused_info["id"],
                "outline": focused_info["outlineStyle"],
                "boxShadow": focused_info["boxShadow"][:80],
            })

        focused_elements.append({
            "index": i,
            "selector": focused_info["selector"],
            "has_focus_indicator": has_focus_indicator,
        })

        # Save focus screenshot
        fname = f"focus_{i:03d}_{focused_info['selector'].replace('#', 'id_').replace('.', 'cls_')}.png"
        (SCREENSHOTS_DIR / fname).write_bytes(focused_screenshot)

    results["pass"] = results["invisible_focus"] == 0
    log.info(
        "Section D: %d elements, %d visible focus, %d invisible",
        results["elements_tested"], results["visible_focus"], results["invisible_focus"],
    )
    return results


# =========================================================================
# SECTION E HELPERS: Dynamic DOM Crawler (Upgrade 1)
# =========================================================================

async def _element_clip_from_locator(
    page: Page, locator: Any, padding: int = 15,
) -> Optional[bytes]:
    """Bounding-box clip screenshot from a Playwright locator handle."""
    try:
        box = await locator.bounding_box()
    except Exception:
        return None
    if not box or box["width"] <= 0 or box["height"] <= 0:
        return None

    vp = page.viewport_size or {"width": 1440, "height": 900}
    x = max(0, box["x"] - padding)
    y = max(0, box["y"] - padding)
    w = min(box["width"] + 2 * padding, vp["width"] - x)
    h = min(box["height"] + 2 * padding, vp["height"] - y)

    if w <= 0 or h <= 0 or x >= vp["width"] or y >= vp["height"]:
        return None

    try:
        return await page.screenshot(clip={"x": x, "y": y, "width": w, "height": h})
    except Exception:
        return None


async def _compute_element_key(page: Page, locator: Any) -> str:
    """Return a stable CSS path string for dedup across views."""
    try:
        return await locator.evaluate("""el => {
            const parts = [];
            let node = el;
            while (node && node !== document.body) {
                let selector = node.tagName.toLowerCase();
                if (node.id) {
                    selector += '#' + node.id;
                    parts.unshift(selector);
                    break;
                }
                const parent = node.parentElement;
                if (parent) {
                    const siblings = Array.from(parent.children).filter(c => c.tagName === node.tagName);
                    if (siblings.length > 1) {
                        selector += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
                    }
                }
                parts.unshift(selector);
                node = node.parentElement;
            }
            return parts.join(' > ');
        }""")
    except Exception:
        return ""


async def _auto_name_element(
    page: Page, locator: Any, view_name: str, index: int,
) -> str:
    """Generate a descriptive filename-safe name for an element."""
    try:
        info = await locator.evaluate("""el => ({
            tag: el.tagName.toLowerCase(),
            id: el.id || '',
            cls: (el.className?.toString?.() || '').split(' ').filter(c => c).slice(0, 2).join('_'),
            aria: el.getAttribute('aria-label') || '',
            text: (el.textContent || '').trim().substring(0, 20),
        })""")
    except Exception:
        return f"{view_name}_el_{index:03d}"

    parts = [view_name, info["tag"]]
    if info["id"]:
        parts.append(info["id"])
    elif info["cls"]:
        parts.append(info["cls"])
    elif info["aria"]:
        parts.append(info["aria"].replace(" ", "_")[:20])
    elif info["text"]:
        parts.append(info["text"].replace(" ", "_")[:20])
    parts.append(f"{index:03d}")

    name = "_".join(parts)
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    return name[:80]


# =========================================================================
# SECTION E: Dynamic Interactive Element State Testing (Upgrade 1)
# =========================================================================

async def section_e_states(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section E: Dynamically discover and test ALL interactive elements across views.

    Per-view dedup for visual diff screenshots (hover/focus), but the monkey-click
    phase queries ALL visible interactive elements fresh each view (no dedup) to
    catch data-driven JS errors.  preventDefault only on anchors (no
    stopPropagation) so the app's real event delegation executes.
    """
    log.info("=== SECTION E: Dynamic Interactive Element States ===")
    results: dict[str, Any] = {
        "section": "E_state_testing",
        "elements_tested": 0,
        "state_changes_detected": 0,
        "invisible_state_changes": [],
        "skipped_obscured": 0,
        "views_crawled": 0,
        "total_discovered": 0,
        "monkey_clicks": 0,
        "js_errors": [],
        "console_errors": [],
        "details": [],
        "pass": False,
    }

    # --- Console & JS error listeners ---
    js_errors: list[dict[str, str]] = []
    console_errors: list[dict[str, str]] = []

    def _on_page_error(error: Any) -> None:
        js_errors.append({"message": str(error), "type": "pageerror"})

    def _on_console(msg: Any) -> None:
        if msg.type == "error":
            console_errors.append({"text": msg.text, "type": "console.error"})

    page.on("pageerror", _on_page_error)
    page.on("console", _on_console)

    await page.set_viewport_size(VIEWPORTS["desktop_1440"])

    # Expanded selector: semantic + ARIA + role-based interactive elements
    _discovery_selector = (
        'button:visible, a[href]:visible, input:visible, '
        '[tabindex="0"]:visible, select:visible, '
        '[role="button"]:visible, [role="tab"]:visible, summary:visible'
    )

    # Max elements for monkey-click phase (independent of visual diff cap)
    _monkey_max = int(os.getenv("VQA_MONKEY_MAX_PER_VIEW", "200"))

    for view_def in ELEMENT_DISCOVERY_VIEWS:
        view_name = view_def["name"]
        results["views_crawled"] += 1

        # Per-view dedup for visual diff screenshots
        view_seen_keys: set[str] = set()

        # Fresh page load per view
        await safe_goto(page, base_url)
        await apply_frozen_values(page)
        await inject_deterministic_result(page)
        await page.emulate_media(reduced_motion="reduce")
        await page.add_style_tag(content=(
            ".app-header, .nav-bar { position: relative !important; z-index: 0 !important; } "
            "* { content-visibility: visible !important; }"
        ))

        # Navigate to view
        try:
            await page.evaluate(view_def["setup"])
        except Exception as exc:
            log.warning("View setup '%s' failed: %s", view_name, exc)
            continue

        # Wait for JS-rendered dynamic content (citations, cards, etc.)
        await page.wait_for_timeout(2000)

        # TRAP-1: Prevent navigation on anchors only — NO stopPropagation,
        # NO capture phase, so event delegation in the app's JS executes.
        await page.evaluate("""
            document.querySelectorAll('a[href]').forEach(el => {
                el.addEventListener('click', e => { e.preventDefault(); });
            });
            window.onbeforeunload = () => '';
        """)

        # Discover ALL visible interactive elements (expanded selector)
        locators = await page.locator(_discovery_selector).all()

        discovered_count = 0
        for idx, loc in enumerate(locators[:VQA_MAX_ELEMENTS_PER_VIEW]):
            # Per-view dedup by CSS path for visual diff screenshots
            css_key = await _compute_element_key(page, loc)
            if not css_key or css_key in view_seen_keys:
                continue
            view_seen_keys.add(css_key)
            discovered_count += 1
            results["total_discovered"] += 1

            # Check visibility and bounding box
            try:
                if not await loc.is_visible():
                    continue
                box = await loc.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue
            except Exception:
                results["skipped_obscured"] += 1
                continue

            elem_name = await _auto_name_element(page, loc, view_name, idx)
            results["elements_tested"] += 1
            elem_detail: dict[str, Any] = {
                "name": elem_name,
                "css_path": css_key,
                "view": view_name,
                "states_captured": {},
            }

            # Capture default state
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(50)
            default_bytes = await _element_clip_from_locator(page, loc)
            if not default_bytes:
                results["skipped_obscured"] += 1
                continue

            fname_prefix = f"state_{elem_name}"
            (SCREENSHOTS_DIR / f"{fname_prefix}_default.png").write_bytes(default_bytes)
            elem_detail["states_captured"]["default"] = f"{fname_prefix}_default.png"

            # --- Hover state ---
            try:
                await loc.hover(timeout=2000)
                await page.wait_for_timeout(100)
                hover_bytes = await _element_clip_from_locator(page, loc)
                if hover_bytes:
                    fname = f"{fname_prefix}_hover.png"
                    (SCREENSHOTS_DIR / fname).write_bytes(hover_bytes)
                    elem_detail["states_captured"]["hover"] = fname
                    diff_ratio, _ = _pixel_diff(default_bytes, hover_bytes)
                    elem_detail["hover_diff"] = round(diff_ratio, 4)
                    if diff_ratio > 0.005:
                        results["state_changes_detected"] += 1
                    else:
                        results["invisible_state_changes"].append({
                            "name": elem_name,
                            "state": "hover",
                            "diff_ratio": round(diff_ratio, 4),
                        })
            except Exception:
                results["skipped_obscured"] += 1

            # TRAP-6: Escape + mouse park after hover
            await page.keyboard.press("Escape")
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(50)

            # --- Focus state ---
            try:
                await loc.focus()
                await page.wait_for_timeout(100)
                focus_bytes = await _element_clip_from_locator(page, loc)
                if focus_bytes:
                    fname = f"{fname_prefix}_focus.png"
                    (SCREENSHOTS_DIR / fname).write_bytes(focus_bytes)
                    elem_detail["states_captured"]["focus"] = fname
                    diff_ratio, _ = _pixel_diff(default_bytes, focus_bytes)
                    elem_detail["focus_diff"] = round(diff_ratio, 4)
                    if diff_ratio > 0.005:
                        results["state_changes_detected"] += 1
                    else:
                        results["invisible_state_changes"].append({
                            "name": elem_name,
                            "state": "focus",
                            "diff_ratio": round(diff_ratio, 4),
                        })
            except Exception:
                results["skipped_obscured"] += 1

            # TRAP-6: Escape + mouse park after focus
            await page.keyboard.press("Escape")
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(50)

            results["details"].append(elem_detail)

        # --- Monkey-Click Phase (UNSHIELDED) ---
        # Re-query ALL visible interactive elements fresh (no dedup).
        # Only prevent anchor navigation — let all real JS handlers fire.
        await page.evaluate("""
            document.querySelectorAll('a[href]').forEach(el => {
                el.addEventListener('click', e => { e.preventDefault(); });
            });
            window.onbeforeunload = () => '';
        """)

        pre_click_js_count = len(js_errors)
        pre_click_console_count = len(console_errors)
        monkey_click_count = 0

        # Fresh query — clicks EVERY visible element including dupes from other views
        all_clickable = await page.locator(_discovery_selector).all()
        for loc in all_clickable[:_monkey_max]:
            try:
                if not await loc.is_visible():
                    continue
                box = await loc.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue
                await loc.click(timeout=2000, force=True)
                monkey_click_count += 1
                results["monkey_clicks"] += 1
                await page.wait_for_timeout(50)
                # TRAP-6: Escape after click to dismiss any popup/modal
                await page.keyboard.press("Escape")
                await page.mouse.move(0, 0)
            except Exception:
                pass  # Element may have become detached or hidden — skip

        # Log monkey-click errors for this view
        new_js = js_errors[pre_click_js_count:]
        new_console = console_errors[pre_click_console_count:]
        if new_js:
            log.warning("  [E] View '%s': %d JS errors during monkey-click", view_name, len(new_js))
        if new_console:
            log.warning("  [E] View '%s': %d console.error during monkey-click", view_name, len(new_console))

        log.info("  [E] View '%s': discovered %d elements, %d monkey-clicks",
                 view_name, discovered_count, monkey_click_count)

    # Remove listeners
    page.remove_listener("pageerror", _on_page_error)
    page.remove_listener("console", _on_console)

    results["js_errors"] = js_errors
    results["console_errors"] = console_errors

    # Pass condition: 0 invisible state changes AND 0 JS exceptions during monkey-click
    results["pass"] = (
        len(results["invisible_state_changes"]) == 0
        and len(js_errors) == 0
    )
    log.info(
        "Section E: %d views, %d discovered, %d tested, %d state changes, "
        "%d invisible, %d skipped, %d monkey-clicks, %d JS errors, %d console.errors",
        results["views_crawled"], results["total_discovered"],
        results["elements_tested"], results["state_changes_detected"],
        len(results["invisible_state_changes"]), results["skipped_obscured"],
        results["monkey_clicks"], len(js_errors), len(console_errors),
    )
    return results


# =========================================================================
# SECTION F: Touch Target Measurement
# =========================================================================

async def section_f_touch_targets(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section F: Measure touch targets at mobile viewport."""
    log.info("=== SECTION F: Touch Target Measurement ===")
    results: dict[str, Any] = {
        "section": "F_touch_targets",
        "elements_measured": 0,
        "pass_44px": 0,
        "fail_44px": [],
        "fail_24px": [],
        "pass": False,
    }

    # Test at mobile viewport
    await page.set_viewport_size(VIEWPORTS["mobile_375"])
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await inject_deterministic_result(page)

    # Switch to operator mode to see all elements
    await page.evaluate("setViewMode('operator'); switchView('research')")
    await page.wait_for_timeout(500)

    targets = await page.evaluate("""
        (() => {
            const selectors = 'button, a[href], input, select, [tabindex], [role="button"], [role="tab"], [role="checkbox"], [role="radio"]';
            const elements = document.querySelectorAll(selectors);
            const results = [];
            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || rect.width === 0) return;
                results.push({
                    tag: el.tagName,
                    id: el.id || '',
                    className: (el.className?.toString?.() || '').substring(0, 80),
                    text: (el.textContent || '').substring(0, 40).trim(),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    minDim: Math.round(Math.min(rect.width, rect.height)),
                });
            });
            return results;
        })()
    """)

    for t in targets:
        results["elements_measured"] += 1
        min_dim = t["minDim"]

        if min_dim >= 44:
            results["pass_44px"] += 1
        else:
            results["fail_44px"].append({
                "element": f"{t['tag']}#{t['id']}" if t["id"] else f"{t['tag']}.{t['className'].split(' ')[0] if t['className'] else '?'}",
                "text": t["text"],
                "size": f"{t['width']}x{t['height']}",
                "min_dim": min_dim,
            })

    # Also check at desktop for 24px minimum
    await page.set_viewport_size(VIEWPORTS["desktop_1440"])
    await page.wait_for_timeout(300)
    desktop_targets = await page.evaluate("""
        (() => {
            const selectors = 'button, a[href], input, select, [tabindex], [role="button"], [role="tab"]';
            const elements = document.querySelectorAll(selectors);
            const results = [];
            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || rect.width === 0) return;
                const minDim = Math.min(rect.width, rect.height);
                if (minDim < 24) {
                    results.push({
                        tag: el.tagName,
                        id: el.id || '',
                        className: (el.className?.toString?.() || '').substring(0, 80),
                        text: (el.textContent || '').substring(0, 40).trim(),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        minDim: Math.round(minDim),
                    });
                }
            });
            return results;
        })()
    """)
    for t in desktop_targets:
        results["fail_24px"].append({
            "element": f"{t['tag']}#{t['id']}" if t["id"] else f"{t['tag']}.{t['className'].split(' ')[0] if t['className'] else '?'}",
            "size": f"{t['width']}x{t['height']}",
            "min_dim": t["minDim"],
        })

    results["pass"] = len(results["fail_44px"]) == 0
    log.info(
        "Section F: %d elements, %d pass 44px, %d fail 44px, %d fail 24px desktop",
        results["elements_measured"], results["pass_44px"],
        len(results["fail_44px"]), len(results["fail_24px"]),
    )
    return results


# =========================================================================
# SECTION G: Cross-Browser Testing (Structural Checks Only)
# =========================================================================

async def _browser_structural_checks(
    browser: Browser, browser_name: str, base_url: str,
) -> dict[str, Any]:
    """Run structural (non-pixel) checks for a single browser."""
    context = await browser.new_context(
        locale="en-US",
        timezone_id="America/Vancouver",
        viewport=VIEWPORTS["desktop_1440"],
    )
    page = await context.new_page()
    await freeze_dynamic_content(page)
    await setup_mock_routes(page)
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await inject_deterministic_result(page)
    await page.evaluate("setViewMode('operator'); switchView('research')")
    await page.wait_for_timeout(500)

    checks: dict[str, Any] = {"browser": browser_name, "issues": []}

    # 1. Horizontal overflow
    overflow = await page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 15"
    )
    checks["horizontal_overflow"] = overflow
    if overflow:
        checks["issues"].append("Horizontal overflow detected")

    # 2. Key layout dimensions
    checks["layout_dims"] = await page.evaluate("""
        (() => {
            const dims = {};
            const selectors = ['.app-header', '.nav-bar', '.views-container', '.landing-page'];
            selectors.forEach(sel => {
                const el = document.querySelector(sel);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    dims[sel] = { width: Math.round(rect.width), height: Math.round(rect.height) };
                }
            });
            return dims;
        })()
    """)

    # 3. Computed style checks on critical properties
    checks["computed_styles"] = await page.evaluate("""
        (() => {
            const results = {};
            const checks = [
                { sel: '.app-header', props: ['display', 'position', 'visibility'] },
                { sel: '.nav-bar', props: ['display', 'visibility'] },
                { sel: '.views-container', props: ['display', 'overflow'] },
            ];
            checks.forEach(c => {
                const el = document.querySelector(c.sel);
                if (el) {
                    const cs = getComputedStyle(el);
                    const vals = {};
                    c.props.forEach(p => vals[p] = cs[p]);
                    results[c.sel] = vals;
                }
            });
            return results;
        })()
    """)

    # 4. axe-core in this browser
    if await _inject_axe_core(page):
        axe_results = await _run_axe_scan(page)
        checks["axe_violations"] = axe_results.get("violations_count", 0)
        checks["axe_critical"] = sum(
            1 for v in axe_results.get("violations", []) if v.get("impact") == "critical"
        )
    else:
        checks["axe_violations"] = -1
        checks["axe_critical"] = -1

    # 5. Capture reference screenshot (human review, not diffed cross-browser)
    fpath = SCREENSHOTS_DIR / f"browser_{browser_name}_reference.png"
    await full_page_screenshot(page, fpath)
    checks["reference_screenshot"] = fpath.name

    await context.close()
    return checks


async def section_g_cross_browser(
    playwright_instance: Any, base_url: str, browsers_to_test: list[str],
) -> dict[str, Any]:
    """Section G: Cross-browser structural checks."""
    log.info("=== SECTION G: Cross-Browser Testing ===")
    results: dict[str, Any] = {
        "section": "G_cross_browser",
        "browsers_tested": [],
        "issues": [],
        "pass": False,
    }

    for browser_name in browsers_to_test:
        log.info("Testing browser: %s", browser_name)
        try:
            launcher = getattr(playwright_instance, browser_name)
            browser = await launcher.launch(headless=True)
            checks = await _browser_structural_checks(browser, browser_name, base_url)
            results["browsers_tested"].append(checks)
            if checks["issues"]:
                results["issues"].extend(checks["issues"])
            await browser.close()
        except Exception as exc:
            log.warning("Browser %s failed: %s", browser_name, exc)
            results["browsers_tested"].append({
                "browser": browser_name,
                "error": str(exc),
            })

    results["pass"] = len(results["issues"]) == 0
    log.info("Section G: %d browsers tested", len(results["browsers_tested"]))
    return results


# =========================================================================
# SECTION H: Responsive + Zoom Testing
# =========================================================================

async def section_h_responsive(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section H: Test all 7 viewports + WCAG 1.4.10 reflow at 320px."""
    log.info("=== SECTION H: Responsive + Zoom Testing ===")
    results: dict[str, Any] = {
        "section": "H_responsive",
        "viewports_tested": 0,
        "overflow_failures": [],
        "reflow_320_pass": False,
        "viewport_details": [],
        "pass": False,
    }

    for vp_name, vp in VIEWPORTS.items():
        await page.set_viewport_size(vp)
        await safe_goto(page, base_url)
        await apply_frozen_values(page)
        await inject_deterministic_result(page)
        await page.evaluate("setViewMode('operator'); switchView('research')")
        await page.wait_for_timeout(500)

        results["viewports_tested"] += 1

        # Check horizontal overflow with scrollbar tolerance (Trap 5)
        overflow = await page.evaluate(f"""
            document.documentElement.scrollWidth > document.documentElement.clientWidth + {SCROLLBAR_TOLERANCE}
        """)

        scroll_w = await page.evaluate("document.documentElement.scrollWidth")
        client_w = await page.evaluate("document.documentElement.clientWidth")

        detail = {
            "viewport": vp_name,
            "width": vp["width"],
            "height": vp["height"],
            "scrollWidth": scroll_w,
            "clientWidth": client_w,
            "overflow": overflow,
        }
        results["viewport_details"].append(detail)

        if overflow:
            results["overflow_failures"].append({
                "viewport": vp_name,
                "scrollWidth": scroll_w,
                "clientWidth": client_w,
                "excess": scroll_w - client_w,
            })

        # Screenshot at each viewport
        fname = f"responsive_{vp_name}.png"
        await full_page_screenshot(page, SCREENSHOTS_DIR / fname)

    # WCAG 1.4.10 Reflow test at 320px (simulates 400% zoom)
    await page.set_viewport_size({"width": 320, "height": 256})
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await page.wait_for_timeout(500)

    reflow_overflow = await page.evaluate(f"""
        document.documentElement.scrollWidth > document.documentElement.clientWidth + {SCROLLBAR_TOLERANCE}
    """)
    results["reflow_320_pass"] = not reflow_overflow

    reflow_scroll_w = await page.evaluate("document.documentElement.scrollWidth")
    reflow_client_w = await page.evaluate("document.documentElement.clientWidth")
    results["reflow_320_detail"] = {
        "scrollWidth": reflow_scroll_w,
        "clientWidth": reflow_client_w,
        "overflow": reflow_overflow,
    }

    # Screenshot at 320px
    await full_page_screenshot(page, SCREENSHOTS_DIR / "responsive_reflow_320.png")

    results["pass"] = len(results["overflow_failures"]) == 0 and results["reflow_320_pass"]
    log.info(
        "Section H: %d viewports, %d overflow failures, reflow=%s",
        results["viewports_tested"],
        len(results["overflow_failures"]),
        results["reflow_320_pass"],
    )
    return results


# =========================================================================
# SECTION I: Print Stylesheet Validation
# =========================================================================

async def section_i_print(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section I: Validate print stylesheet behavior."""
    log.info("=== SECTION I: Print Stylesheet Validation ===")
    results: dict[str, Any] = {
        "section": "I_print_stylesheet",
        "hidden_elements": {},
        "visible_elements": {},
        "color_checks": {},
        "dark_mode_print_reset": False,
        "pdf_generated": False,
        "pass": False,
    }

    await page.set_viewport_size(VIEWPORTS["desktop_1440"])
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await inject_deterministic_result(page)
    await page.evaluate("setViewMode('operator'); switchView('report')")
    # Wait for actual rendered report content (TRAP 2 fix — deterministic wait)
    try:
        await page.locator(
            ".report-rendered p, .report-rendered h1, .report-body h1, .report-body p"
        ).first.wait_for(state="visible", timeout=5000)
    except Exception:
        # Fallback: content may not exist if report-body is empty
        await page.wait_for_timeout(500)

    # Emulate print media
    await page.emulate_media(media="print")
    await page.wait_for_timeout(300)

    # Check hidden elements
    hidden_selectors = [
        ".app-header", ".nav-bar", ".query-banner", ".export-toolbar",
        "#theme-toggle", ".pipeline-column",
    ]
    for sel in hidden_selectors:
        is_hidden = await page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (!el) return true;
                const cs = getComputedStyle(el);
                return cs.display === 'none' || cs.visibility === 'hidden';
            }})()
        """)
        results["hidden_elements"][sel] = is_hidden

    # Check visible elements
    visible_selectors = [".report-rendered", ".report-main", ".report-body", "#report-body"]
    for sel in visible_selectors:
        is_visible = await page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (!el) return false;
                const cs = getComputedStyle(el);
                return cs.display !== 'none' && cs.visibility !== 'hidden';
            }})()
        """)
        results["visible_elements"][sel] = is_visible

    # Color checks (should be black text on white bg)
    results["color_checks"] = await page.evaluate("""
        (() => {
            const body = document.body;
            const cs = getComputedStyle(body);
            return {
                color: cs.color,
                backgroundColor: cs.backgroundColor,
            };
        })()
    """)

    # Print screenshot
    await full_page_screenshot(page, SCREENSHOTS_DIR / "print_light.png")

    # Dark mode + print test
    await page.emulate_media(media="screen")
    await page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    await page.wait_for_timeout(100)
    await page.emulate_media(media="print")
    await page.wait_for_timeout(300)

    dark_print_colors = await page.evaluate("""
        (() => {
            const body = document.body;
            const cs = getComputedStyle(body);
            return {
                color: cs.color,
                backgroundColor: cs.backgroundColor,
            };
        })()
    """)
    results["dark_mode_print_colors"] = dark_print_colors
    # Check if dark colors leaked through (should still be light for print)
    bg = dark_print_colors.get("backgroundColor", "")
    results["dark_mode_print_reset"] = "255" in bg or "white" in bg.lower() or bg == "rgba(0, 0, 0, 0)"

    await full_page_screenshot(page, SCREENSHOTS_DIR / "print_dark_mode.png")

    # PDF generation test (Trap 6)
    try:
        pdf_path = REPORTS_DIR / "print_test.pdf"
        await page.pdf(path=str(pdf_path), format="A4", print_background=True)
        results["pdf_generated"] = pdf_path.exists() and pdf_path.stat().st_size > 0
        results["pdf_size_bytes"] = pdf_path.stat().st_size if pdf_path.exists() else 0
    except Exception as exc:
        results["pdf_error"] = str(exc)
        results["pdf_generated"] = False

    # Reset media
    await page.emulate_media(media="screen")

    hidden_ok = all(results["hidden_elements"].values())
    visible_ok = any(results["visible_elements"].values())
    results["pass"] = hidden_ok and visible_ok
    log.info(
        "Section I: hidden=%s, visible=%s, pdf=%s, dark_reset=%s",
        hidden_ok, visible_ok, results["pdf_generated"], results["dark_mode_print_reset"],
    )
    return results


# =========================================================================
# SECTION J: CSS Hardcoded Value Scan (Static Analysis)
# =========================================================================

def section_j_css_scan() -> dict[str, Any]:
    """Section J: Scan CSS files for hardcoded values."""
    log.info("=== SECTION J: CSS Hardcoded Value Scan ===")
    results: dict[str, Any] = {
        "section": "J_css_scan",
        "hardcoded_font_sizes": [],
        "hardcoded_hex_colors": [],
        "hardcoded_z_index": [],
        "duplicate_variables": [],
        "total_issues": 0,
        "pass": False,
    }

    for css_file in CSS_FILES:
        fpath = CSS_DIR / css_file
        if not fpath.exists():
            log.warning("CSS file not found: %s", fpath)
            continue

        content = fpath.read_text(encoding="utf-8")
        lines = content.split("\n")

        in_root = False
        in_print = False
        root_depth = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Track :root blocks (variables declared here are OK)
            if ":root" in stripped:
                in_root = True
                root_depth = 0
            if "@media print" in stripped:
                in_print = True

            if in_root or in_print:
                root_depth += stripped.count("{") - stripped.count("}")
                if root_depth <= 0:
                    in_root = False
                    in_print = False
                continue

            # font-size with px (not in :root or @media print)
            if re.search(r"font-size:\s*\d+px", stripped):
                match = re.search(r"font-size:\s*(\d+px)", stripped)
                results["hardcoded_font_sizes"].append({
                    "file": css_file,
                    "line": line_num,
                    "value": match.group(1) if match else "?",
                    "context": stripped[:100],
                })

            # z-index not using var(--z-*)
            if re.search(r"z-index:\s*\d+", stripped) and "var(--z-" not in stripped:
                match = re.search(r"z-index:\s*(\d+)", stripped)
                results["hardcoded_z_index"].append({
                    "file": css_file,
                    "line": line_num,
                    "value": match.group(1) if match else "?",
                    "context": stripped[:100],
                })

    # Duplicate variable detection (re-scan :root blocks specifically)
    for css_file in CSS_FILES:
        fpath = CSS_DIR / css_file
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8")
        # Find all variable declarations within same selector block
        var_declarations: dict[str, list[tuple[int, str]]] = defaultdict(list)
        current_selector = ""
        for line_num, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            # Track selector
            if "{" in stripped and "}" not in stripped:
                current_selector = stripped.replace("{", "").strip()
            elif "}" in stripped:
                # Check for duplicates within this block
                for var_name, decls in var_declarations.items():
                    if len(decls) > 1:
                        results["duplicate_variables"].append({
                            "file": css_file,
                            "variable": var_name,
                            "selector": current_selector,
                            "declarations": [
                                {"line": ln, "value": val} for ln, val in decls
                            ],
                        })
                var_declarations.clear()
                current_selector = ""

            # Track variable declarations
            var_match = re.match(r"\s*(--[\w-]+)\s*:\s*(.+?)\s*;", line)
            if var_match:
                var_declarations[var_match.group(1)].append(
                    (line_num, var_match.group(2))
                )

    results["total_issues"] = (
        len(results["hardcoded_font_sizes"])
        + len(results["hardcoded_z_index"])
        + len(results["duplicate_variables"])
    )
    results["pass"] = results["total_issues"] == 0
    log.info(
        "Section J: %d font-size px, %d z-index, %d duplicate vars",
        len(results["hardcoded_font_sizes"]),
        len(results["hardcoded_z_index"]),
        len(results["duplicate_variables"]),
    )
    return results


# =========================================================================
# SECTION K: Visual Regression Baselines
# =========================================================================

async def section_k_baselines(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section K: Establish or compare visual regression baselines."""
    log.info("=== SECTION K: Visual Regression Baselines ===")
    results: dict[str, Any] = {
        "section": "K_baselines",
        "baselines_created": 0,
        "baselines_compared": 0,
        "regressions": [],
        "pass": False,
    }

    for theme in THEMES:
        for vp_name in BASE_VIEWPORTS:
            vp = VIEWPORTS[vp_name]
            await page.set_viewport_size(vp)

            # Load page ONCE per theme+viewport
            await safe_goto(page, base_url)
            await apply_frozen_values(page)
            await inject_deterministic_result(page)
            await page.evaluate(f"""
                document.documentElement.setAttribute('data-theme', '{theme}');
            """)
            await page.wait_for_timeout(200)

            for state_entry in STATE_MATRIX:
                await navigate_to_state(page, state_entry)

                fname = f"baseline_{state_entry['name']}_{theme}_{vp_name}.png"
                current_path = SCREENSHOTS_DIR / f"current_{fname}"
                baseline_path = BASELINES_DIR / fname

                img_bytes = await full_page_screenshot(page, current_path)

                if not baseline_path.exists():
                    # First run — save as baseline
                    baseline_path.write_bytes(img_bytes)
                    results["baselines_created"] += 1
                else:
                    # Compare against existing baseline
                    results["baselines_compared"] += 1
                    baseline_bytes = baseline_path.read_bytes()

                    if baseline_bytes == img_bytes:
                        continue  # Identical

                    diff_ratio, diff_img = _pixel_diff(baseline_bytes, img_bytes)
                    if diff_ratio > MAX_DIFF_RATIO:
                        results["regressions"].append({
                            "state": state_entry["name"],
                            "theme": theme,
                            "viewport": vp_name,
                            "diff_ratio": round(diff_ratio, 4),
                            "diff_pixels": f"{diff_ratio * 100:.2f}%",
                        })
                        # Save diff image
                        if diff_img:
                            diff_path = DIFFS_DIR / f"diff_{fname}"
                            diff_path.write_bytes(diff_img)

    results["pass"] = len(results["regressions"]) == 0
    log.info(
        "Section K: %d created, %d compared, %d regressions",
        results["baselines_created"],
        results["baselines_compared"],
        len(results["regressions"]),
    )
    return results


# =========================================================================
# SECTION M: Scroll & Z-Index Stress Test (Upgrade 2 + TRAP-2 + TRAP-4)
# =========================================================================

async def section_m_scroll_zindex(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section M: Scroll stress and z-index overlap testing.

    Injects filler content to make .report-view scrollable, then verifies
    header stays at y=0 and nothing overlaps it (TRAP-2: elementFromPoint).
    Uses safe_goto + apply_frozen_values state reset (TRAP-4).
    """
    log.info("=== SECTION M: Scroll & Z-Index Stress Test ===")
    results: dict[str, Any] = {
        "section": "M_scroll_zindex",
        "header_fixed": False,
        "nav_position_correct": False,
        "zindex_overlap_detected": False,
        "details": {},
        "pass": False,
    }

    # TRAP-4: State reset before
    await page.set_viewport_size(VIEWPORTS["desktop_1440"])
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await inject_deterministic_result(page)

    # Navigate to op_report
    await page.evaluate("setViewMode('operator'); switchView('report')")
    await page.wait_for_timeout(500)

    # Inject 50 filler paragraphs into #report-body to ensure scrollability
    await page.evaluate("""
        (() => {
            const body = document.querySelector('#report-body');
            if (!body) return;
            let filler = '';
            for (let i = 0; i < 50; i++) {
                filler += '<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. '
                    + 'Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. '
                    + 'Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris '
                    + 'nisi ut aliquip ex ea commodo consequat. Paragraph ' + (i + 1) + '.</p>';
            }
            body.innerHTML += filler;
        })()
    """)
    await page.wait_for_timeout(300)

    # Scroll .report-view to 1000px
    scroll_result = await page.evaluate("""
        (() => {
            const rv = document.querySelector('.report-view');
            if (!rv) return { error: 'no .report-view' };
            rv.scrollTop = 1000;
            return { scrollTop: rv.scrollTop, scrollHeight: rv.scrollHeight };
        })()
    """)
    results["details"]["scroll_result"] = scroll_result
    await page.wait_for_timeout(300)

    # Assert .app-header bounding_box y === 0 (2px tolerance)
    header_box = await page.evaluate("""
        (() => {
            const header = document.querySelector('.app-header');
            if (!header) return null;
            const rect = header.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        })()
    """)
    results["details"]["header_box"] = header_box
    if header_box:
        results["header_fixed"] = abs(header_box["y"]) <= 2

    # Assert .nav-bar is below header and within viewport.
    # Note: .query-banner may sit between header and nav-bar, so we do NOT
    # assert adjacency — only that nav is below header and not scrolled away.
    nav_box = await page.evaluate("""
        (() => {
            const nav = document.querySelector('.nav-bar');
            if (!nav) return null;
            const rect = nav.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        })()
    """)
    results["details"]["nav_box"] = nav_box
    if header_box and nav_box:
        vp_h = (page.viewport_size or {"height": 900})["height"]
        results["nav_position_correct"] = (
            nav_box["y"] > header_box["y"]
            and nav_box["y"] + nav_box["height"] <= vp_h + 2
        )

    # TRAP-2: elementFromPoint instead of z-index scanning
    overlap_check = await page.evaluate("""
        (() => {
            const topEl = document.elementFromPoint(window.innerWidth / 2, 10);
            if (!topEl) return { error: 'no element at point' };
            const header = document.querySelector('.app-header');
            if (!header) return { error: 'no .app-header' };
            const headerOwns = header.contains(topEl);
            return {
                headerOwns: headerOwns,
                topElementTag: topEl.tagName,
                topElementId: topEl.id || '',
                topElementClass: (topEl.className?.toString?.() || '').substring(0, 80),
            };
        })()
    """)
    results["details"]["overlap_check"] = overlap_check
    results["zindex_overlap_detected"] = not overlap_check.get("headerOwns", True)

    # Evidence screenshot
    await full_page_screenshot(page, SCREENSHOTS_DIR / "scroll_zindex_stress.png")

    # TRAP-4: State reset after
    await safe_goto(page, base_url)
    await apply_frozen_values(page)

    results["pass"] = (
        results["header_fixed"]
        and results["nav_position_correct"]
        and not results["zindex_overlap_detected"]
    )
    log.info(
        "Section M: header_fixed=%s, nav_correct=%s, overlap=%s",
        results["header_fixed"], results["nav_position_correct"],
        results["zindex_overlap_detected"],
    )
    return results


# =========================================================================
# SECTION N: Live Interactions (Upgrade 3 + TRAP-4)
# =========================================================================

async def section_n_live_interactions(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section N: Test real UI interactions via clicks (not page.evaluate).

    5 sub-tests: theme toggle, nav tabs, adv sub-tabs, depth chips, evidence
    tier filters.  Uses safe_goto + apply_frozen_values state reset (TRAP-4).
    """
    log.info("=== SECTION N: Live Interactions ===")
    results: dict[str, Any] = {
        "section": "N_live_interactions",
        "tests_run": 0,
        "tests_passed": 0,
        "failures": [],
        "details": {},
        "pass": False,
    }

    # TRAP-4: State reset before
    await page.set_viewport_size(VIEWPORTS["desktop_1440"])
    await safe_goto(page, base_url)
    await apply_frozen_values(page)
    await inject_deterministic_result(page)

    # --- N.1: Theme Toggle ---
    results["tests_run"] += 1
    try:
        await page.evaluate("setViewMode('operator'); switchView('research')")
        await page.wait_for_timeout(300)

        theme_before = await page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
        )
        toggle = page.locator("#theme-toggle")
        if await toggle.count() > 0:
            await toggle.click()
            await page.wait_for_timeout(300)
            theme_after = await page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            toggled = theme_before != theme_after

            # Click again to revert
            await toggle.click()
            await page.wait_for_timeout(300)
            theme_reverted = await page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            reverted = theme_reverted == theme_before

            results["details"]["N1_theme_toggle"] = {
                "before": theme_before, "after": theme_after,
                "toggled": toggled, "reverted": reverted,
            }
            if toggled and reverted:
                results["tests_passed"] += 1
            else:
                results["failures"].append({
                    "test": "N1_theme_toggle",
                    "expected": f"toggle from {theme_before}",
                    "actual": f"after={theme_after}, revert={theme_reverted}",
                })
        else:
            results["failures"].append({
                "test": "N1_theme_toggle", "error": "#theme-toggle not found",
            })
    except Exception as exc:
        results["failures"].append({"test": "N1_theme_toggle", "error": str(exc)})

    # --- N.2: Nav Tabs ---
    nav_tabs = ["research", "evidence", "report", "memory", "pipelines", "advanced"]
    for tab_name in nav_tabs:
        results["tests_run"] += 1
        try:
            await page.evaluate("setViewMode('operator')")
            await page.wait_for_timeout(200)

            btn = page.locator(f'.nav-btn[data-view="{tab_name}"]')
            if await btn.count() == 0:
                results["failures"].append({
                    "test": f"N2_nav_{tab_name}", "error": "Button not found",
                })
                continue

            await btn.click()
            await page.wait_for_timeout(300)

            is_selected = await btn.get_attribute("aria-selected")
            has_active = await btn.evaluate("el => el.classList.contains('active')")
            active_panes = await page.locator(".view-pane.active").count()

            passed = (is_selected == "true" or has_active) and active_panes == 1
            results["details"][f"N2_nav_{tab_name}"] = {
                "aria_selected": is_selected,
                "has_active": has_active,
                "active_panes": active_panes,
                "passed": passed,
            }
            if passed:
                results["tests_passed"] += 1
            else:
                results["failures"].append({
                    "test": f"N2_nav_{tab_name}",
                    "expected": "aria-selected=true, 1 active pane",
                    "actual": f"selected={is_selected}, active={has_active}, panes={active_panes}",
                })
        except Exception as exc:
            results["failures"].append({
                "test": f"N2_nav_{tab_name}", "error": str(exc),
            })

    # --- N.3: Advanced Sub-Tabs ---
    adv_tabs = ["queries", "sources", "storm", "trace", "cost"]
    await page.evaluate("setViewMode('operator'); switchView('advanced')")
    await page.wait_for_timeout(300)
    for adv_key in adv_tabs:
        results["tests_run"] += 1
        try:
            btn = page.locator(f'.adv-tab-btn[data-adv="{adv_key}"]')
            if await btn.count() == 0:
                results["failures"].append({
                    "test": f"N3_adv_{adv_key}", "error": "Button not found",
                })
                continue

            await btn.click()
            await page.wait_for_timeout(300)

            pane = page.locator(f"#adv-{adv_key}")
            pane_active = False
            if await pane.count() > 0:
                pane_active = await pane.evaluate(
                    "el => el.classList.contains('active')"
                )

            results["details"][f"N3_adv_{adv_key}"] = {"pane_active": pane_active}
            if pane_active:
                results["tests_passed"] += 1
            else:
                results["failures"].append({
                    "test": f"N3_adv_{adv_key}",
                    "expected": f"#adv-{adv_key} has .active",
                    "actual": f"pane_active={pane_active}",
                })
        except Exception as exc:
            results["failures"].append({
                "test": f"N3_adv_{adv_key}", "error": str(exc),
            })

    # --- N.4: Depth Chips (landing page) ---
    await page.evaluate(
        "setViewMode('user'); state.pipelineActive=false; "
        "state.pipelineComplete=false; updateUIVisibility()"
    )
    await page.wait_for_timeout(300)

    depth_chips = await page.locator(".depth-chip").all()
    for i, chip in enumerate(depth_chips):
        results["tests_run"] += 1
        try:
            await chip.click()
            await page.wait_for_timeout(200)
            has_active = await chip.evaluate("el => el.classList.contains('active')")
            results["details"][f"N4_depth_chip_{i}"] = {"has_active": has_active}
            if has_active:
                results["tests_passed"] += 1
            else:
                results["failures"].append({
                    "test": f"N4_depth_chip_{i}",
                    "expected": ".active class after click",
                    "actual": f"has_active={has_active}",
                })
        except Exception as exc:
            results["failures"].append({
                "test": f"N4_depth_chip_{i}", "error": str(exc),
            })

    # --- N.5: Evidence Tier Filters ---
    await page.evaluate("setViewMode('operator'); switchView('evidence')")
    await page.wait_for_timeout(300)

    tier_chips = await page.locator(".filter-chip[data-tier]").all()
    for i, chip in enumerate(tier_chips):
        results["tests_run"] += 1
        try:
            await chip.click()
            await page.wait_for_timeout(200)
            has_active = await chip.evaluate("el => el.classList.contains('active')")
            results["details"][f"N5_tier_filter_{i}"] = {"has_active": has_active}
            if has_active:
                results["tests_passed"] += 1
            else:
                results["failures"].append({
                    "test": f"N5_tier_filter_{i}",
                    "expected": ".active class after click",
                    "actual": f"has_active={has_active}",
                })
        except Exception as exc:
            results["failures"].append({
                "test": f"N5_tier_filter_{i}", "error": str(exc),
            })

    # --- N.6: Density Toggle ---
    results["tests_run"] += 1
    try:
        await page.evaluate("setViewMode('operator'); switchView('research')")
        await page.wait_for_timeout(300)

        dense_btn = page.locator('.density-btn[data-density="dense"]')
        default_btn = page.locator('.density-btn[data-density="default"]')
        if await dense_btn.count() > 0:
            await dense_btn.click()
            await page.wait_for_timeout(200)
            has_dense = await page.evaluate(
                "document.body.classList.contains('operator-dense')"
            )

            # Click default to revert
            if await default_btn.count() > 0:
                await default_btn.click()
                await page.wait_for_timeout(200)
            no_dense = not await page.evaluate(
                "document.body.classList.contains('operator-dense')"
            )

            results["details"]["N6_density_toggle"] = {
                "dense_applied": has_dense,
                "dense_removed": no_dense,
            }
            if has_dense and no_dense:
                results["tests_passed"] += 1
            else:
                results["failures"].append({
                    "test": "N6_density_toggle",
                    "expected": "dense class toggled",
                    "actual": f"applied={has_dense}, removed={no_dense}",
                })
        else:
            results["failures"].append({
                "test": "N6_density_toggle",
                "error": "Density button not found",
            })
    except Exception as exc:
        results["failures"].append({"test": "N6_density_toggle", "error": str(exc)})

    # --- N.7: ARIA Accessibility Assertions ---
    results["tests_run"] += 1
    try:
        await page.evaluate("setViewMode('operator')")
        await page.wait_for_timeout(200)

        a11y_checks = {}
        # role="status" on #polaris-status
        a11y_checks["polaris_status"] = await page.locator(
            '#polaris-status[role="status"]'
        ).count() > 0
        # role="alert" on #polaris-alert
        a11y_checks["polaris_alert"] = await page.locator(
            '#polaris-alert[role="alert"]'
        ).count() > 0
        # role="switch" on auto-nav
        a11y_checks["auto_nav_switch"] = await page.locator(
            '#chk-autotab[role="switch"]'
        ).count() > 0
        # role="toolbar" on operator toolbar
        a11y_checks["operator_toolbar"] = await page.locator(
            '.operator-toolbar[role="toolbar"]'
        ).count() > 0
        # Advanced sub-tabs have role="tablist"
        a11y_checks["adv_tablist"] = await page.locator(
            '.adv-tab-bar[role="tablist"]'
        ).count() > 0
        # color-scheme on html
        color_scheme = await page.evaluate(
            "getComputedStyle(document.documentElement).colorScheme"
        )
        a11y_checks["color_scheme"] = bool(color_scheme)

        all_pass = all(a11y_checks.values())
        results["details"]["N7_aria_a11y"] = a11y_checks
        if all_pass:
            results["tests_passed"] += 1
        else:
            failed = [k for k, v in a11y_checks.items() if not v]
            results["failures"].append({
                "test": "N7_aria_a11y",
                "expected": "All ARIA landmarks present",
                "actual": f"Missing: {failed}",
            })
    except Exception as exc:
        results["failures"].append({"test": "N7_aria_a11y", "error": str(exc)})

    # TRAP-4: State reset after
    await safe_goto(page, base_url)
    await apply_frozen_values(page)

    results["pass"] = len(results["failures"]) == 0
    log.info(
        "Section N: %d tests, %d passed, %d failures",
        results["tests_run"], results["tests_passed"], len(results["failures"]),
    )
    return results


# =========================================================================
# SECTION O: Data Extremes / Chaos Test (Upgrade 4 + TRAP-3 + TRAP-4)
# =========================================================================

async def section_o_data_extremes(
    page: Page, base_url: str,
) -> dict[str, Any]:
    """Section O: Inject chaos data and test for overflow across views + viewports.

    Tests 3 views (report, evidence, research) x all BASE_VIEWPORTS.
    TRAP-3: wraps chaos in .report-rendered for proper CSS context.
    TRAP-4: safe_goto + apply_frozen_values state reset before/after.
    """
    log.info("=== SECTION O: Data Extremes (Chaos Test) ===")
    results: dict[str, Any] = {
        "section": "O_data_extremes",
        "tests_run": 0,
        "overflow_failures": [],
        "details": [],
        "pass": False,
    }

    # Chaos payload: 300-char no-space string, 20-col table, 200-char URL
    chaos_html = (
        '<h1>' + 'A' * 300 + '</h1>'
        '<table><tr>'
        + ''.join(f'<th>{"H" * 50}</th>' for _ in range(20))
        + '</tr><tr>'
        + ''.join(f'<td>{"D" * 50}</td>' for _ in range(20))
        + '</tr></table>'
        '<p><a href="https://example.com/' + 'C' * 200
        + '">https://example.com/' + 'C' * 200 + '</a></p>'
    )
    chaos_escaped = chaos_html.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

    # Tight-component chaos payload: overflows grid cells and cards
    tight_chaos = "'A'.repeat(300) + '<br>' + 'B'.repeat(200)"

    # TRAP-3: Chaos targets per view with proper CSS context wrappers
    chaos_targets = [
        {
            "name": "report_view",
            "setup": "setViewMode('operator'); switchView('report')",
            "inject_js": f"""
                (() => {{
                    const body = document.querySelector('#report-body');
                    if (body) body.innerHTML = '<div class="report-rendered">' + '{chaos_escaped}' + '</div>';
                }})()
            """,
        },
        {
            "name": "evidence_view",
            "setup": "setViewMode('operator'); switchView('evidence')",
            "inject_js": """
                (() => {
                    const cardList = document.querySelector('#evidence-card-list');
                    if (cardList) {
                        cardList.innerHTML = '<div class="ev-card">'
                            + '<div class="ev-card-claim">' + 'X'.repeat(500) + '</div>'
                            + '<div class="ev-card-source">https://example.com/' + 'U'.repeat(300) + '</div>'
                            + '</div>';
                    }
                })()
            """,
        },
        {
            "name": "research_view",
            "setup": "setViewMode('operator'); switchView('research')",
            "inject_js": """
                (() => {
                    const stream = document.querySelector('.reasoning-stream')
                        || document.querySelector('.phase-block-body');
                    if (stream) stream.innerHTML = '<p>' + 'R'.repeat(300) + '</p>';
                })()
            """,
        },
        {
            "name": "evidence_cards_tight",
            "setup": "setViewMode('operator'); switchView('evidence')",
            "inject_js": """
                (() => {
                    document.querySelectorAll('.ev-card').forEach(card => {
                        card.innerHTML = '<div class="ev-card-claim">' + 'X'.repeat(500) + '</div>'
                            + '<div class="ev-card-source">https://example.com/' + 'U'.repeat(300) + '</div>';
                    });
                    // Also blast any source-card elements
                    document.querySelectorAll('.source-card').forEach(card => {
                        card.innerHTML = '<div>' + 'S'.repeat(400) + '</div>'
                            + '<div>https://example.com/' + 'L'.repeat(300) + '</div>';
                    });
                })()
            """,
        },
        {
            "name": "advanced_cards_tight",
            "setup": "setViewMode('operator'); switchView('advanced'); document.querySelector('.adv-tab-btn[data-adv=\"queries\"]')?.click()",
            "inject_js": """
                (() => {
                    // Blast all adv-card and campaign-item elements
                    document.querySelectorAll('.adv-card, .campaign-item, .campaign-item-header').forEach(card => {
                        card.innerHTML = '<div>' + 'Q'.repeat(500) + '</div>'
                            + '<table><tr>' + '<td>' + 'T'.repeat(50) + '</td>'.repeat(10) + '</tr></table>';
                    });
                    // Also try query list items
                    document.querySelectorAll('.query-item, .history-item, .bookmark-item').forEach(el => {
                        el.innerHTML = '<div>' + 'H'.repeat(400) + '</div>';
                    });
                })()
            """,
        },
    ]

    for target in chaos_targets:
        for vp_name in BASE_VIEWPORTS:
            vp = VIEWPORTS[vp_name]
            results["tests_run"] += 1

            # TRAP-4: Fresh state per test
            await page.set_viewport_size(vp)
            await safe_goto(page, base_url)
            await apply_frozen_values(page)
            await inject_deterministic_result(page)

            # Navigate to target view
            try:
                await page.evaluate(target["setup"])
            except Exception as exc:
                log.warning("Chaos setup '%s' failed: %s", target["name"], exc)
                continue
            await page.wait_for_timeout(300)

            # Inject chaos payload
            try:
                await page.evaluate(target["inject_js"])
            except Exception as exc:
                log.warning("Chaos inject '%s' failed: %s", target["name"], exc)
                continue
            await page.wait_for_timeout(300)

            # Check for horizontal overflow
            overflow_data = await page.evaluate(f"""
                (() => {{
                    const sw = document.documentElement.scrollWidth;
                    const cw = document.documentElement.clientWidth;
                    return {{
                        scrollWidth: sw,
                        clientWidth: cw,
                        overflow: sw > cw + {SCROLLBAR_TOLERANCE},
                        excess: sw - cw,
                    }};
                }})()
            """)

            detail = {
                "target": target["name"],
                "viewport": vp_name,
                **overflow_data,
            }
            results["details"].append(detail)

            if overflow_data.get("overflow"):
                priority = "P0" if vp["width"] <= 768 else "P1"
                results["overflow_failures"].append({
                    **detail,
                    "priority": priority,
                })

            # Evidence screenshot
            fname = f"chaos_{target['name']}_{vp_name}.png"
            await full_page_screenshot(page, SCREENSHOTS_DIR / fname)

    # TRAP-4: State reset after
    await safe_goto(page, base_url)
    await apply_frozen_values(page)

    results["pass"] = len(results["overflow_failures"]) == 0
    log.info(
        "Section O: %d tests, %d overflow failures",
        results["tests_run"], len(results["overflow_failures"]),
    )
    return results


# =========================================================================
# SECTION L: Report Generation
# =========================================================================

def _classify_priority(section_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract findings with priority classification."""
    findings = []

    section = section_results.get("section", "")

    # Section A: duplicate states
    if section == "A_navigation":
        for dup in section_results.get("duplicate_pairs", []):
            findings.append({
                "priority": "P0",
                "section": "A",
                "description": f"Duplicate state: {dup['state_a']} == {dup['state_b']} in {dup['context']}",
                "wcag": "N/A",
                "remediation": "Fix navigation — views must render unique content",
            })

    # Section B: axe-core violations
    if section == "B_axe_wcag":
        for scan in section_results.get("scans", []):
            for v in scan.get("violations", []):
                impact = v.get("impact", "minor")
                priority = {
                    "critical": "P0", "serious": "P1", "moderate": "P2", "minor": "P3",
                }.get(impact, "P3")
                findings.append({
                    "priority": priority,
                    "section": "B",
                    "description": f"[{scan['state']}/{scan['theme']}] {v['id']}: {v['description']} ({v['nodes_count']} nodes)",
                    "wcag": ", ".join(t for t in v.get("tags", []) if "wcag" in t),
                    "remediation": v.get("helpUrl", ""),
                })

    # Section D: invisible focus
    if section == "D_focus_indicators":
        for elem in section_results.get("missing_focus_elements", []):
            findings.append({
                "priority": "P1",
                "section": "D",
                "description": f"Missing focus indicator: {elem['selector']}",
                "wcag": "WCAG 2.4.7 Focus Visible",
                "remediation": "Add :focus-visible styles with outline or box-shadow",
            })

    # Section F: touch target failures
    if section == "F_touch_targets":
        for t in section_results.get("fail_44px", []):
            findings.append({
                "priority": "P1",
                "section": "F",
                "description": f"Touch target too small: {t['element']} ({t['size']}, min={t['min_dim']}px < 44px)",
                "wcag": "WCAG 2.5.8 Target Size (Minimum)",
                "remediation": "Increase touch target to at least 44x44px at mobile viewports",
            })

    # Section E: invisible state changes + JS errors from monkey-click
    if section == "E_state_testing":
        for inv in section_results.get("invisible_state_changes", []):
            findings.append({
                "priority": "P2",
                "section": "E",
                "description": (
                    f"No visual {inv['state']} feedback: {inv['name']} "
                    f"(diff={inv['diff_ratio']})"
                ),
                "wcag": "WCAG 2.4.7 Focus Visible / UX Best Practice",
                "remediation": "Add :hover/:focus-visible style (background, border, or shadow change)",
            })
        for js_err in section_results.get("js_errors", []):
            findings.append({
                "priority": "P1",
                "section": "E",
                "description": f"JS exception during monkey-click: {js_err['message'][:200]}",
                "wcag": "Functional Integrity",
                "remediation": "Fix the JavaScript error to prevent crashes during user interaction",
            })
        # console.error entries are logged in results for diagnostics but do NOT
        # generate findings — CSP, network, and resource-loading errors are
        # test-environment noise, not application bugs.  Only pageerror (real
        # JS exceptions) produce P1 findings above.

    # Section H: overflow
    if section == "H_responsive":
        for o in section_results.get("overflow_failures", []):
            findings.append({
                "priority": "P1",
                "section": "H",
                "description": f"Horizontal overflow at {o['viewport']} ({o['excess']}px excess)",
                "wcag": "WCAG 1.4.10 Reflow",
                "remediation": "Fix overflow — content must reflow without horizontal scroll",
            })
        if not section_results.get("reflow_320_pass"):
            findings.append({
                "priority": "P0",
                "section": "H",
                "description": "WCAG 1.4.10 Reflow FAIL: horizontal overflow at 320px (400% zoom equivalent)",
                "wcag": "WCAG 1.4.10 Reflow",
                "remediation": "Content must reflow at 320px width without horizontal scrolling",
            })

    # Section I: print stylesheet
    if section == "I_print_stylesheet":
        vis = section_results.get("visible_elements", {})
        if not any(vis.values()):
            findings.append({
                "priority": "P1",
                "section": "I",
                "description": "Report body not visible in print media — printed page will be blank",
                "wcag": "Usability",
                "remediation": "Add @media print rule to ensure #report-body or .report-body is display:block",
            })
        if not section_results.get("dark_mode_print_reset"):
            findings.append({
                "priority": "P1",
                "section": "I",
                "description": "Dark mode colors leak into print output",
                "wcag": "Usability",
                "remediation": "Reset background/color to black-on-white in @media print",
            })

    # Section J: hardcoded values
    if section == "J_css_scan":
        if section_results.get("duplicate_variables"):
            for dup in section_results["duplicate_variables"]:
                findings.append({
                    "priority": "P2",
                    "section": "J",
                    "description": f"Duplicate CSS var {dup['variable']} in {dup['file']} ({dup['selector']})",
                    "wcag": "N/A",
                    "remediation": "Remove duplicate declaration — only one value per variable per selector",
                })
        for fz in section_results.get("hardcoded_font_sizes", [])[:10]:
            findings.append({
                "priority": "P2",
                "section": "J",
                "description": f"Hardcoded font-size: {fz['value']} in {fz['file']}:{fz['line']}",
                "wcag": "Best Practice",
                "remediation": "Use CSS variable (e.g., var(--text-base)) instead of px",
            })
        for zi in section_results.get("hardcoded_z_index", []):
            findings.append({
                "priority": "P3",
                "section": "J",
                "description": f"Hardcoded z-index: {zi['value']} in {zi['file']}:{zi['line']}",
                "wcag": "Best Practice",
                "remediation": "Use CSS variable (e.g., var(--z-overlay)) instead of raw number",
            })

    # Section K: regressions
    if section == "K_baselines":
        for reg in section_results.get("regressions", []):
            findings.append({
                "priority": "P2",
                "section": "K",
                "description": f"Visual regression: {reg['state']}_{reg['theme']}_{reg['viewport']} ({reg['diff_pixels']})",
                "wcag": "N/A",
                "remediation": "Review diff image and update baseline if intentional",
            })

    # Section M: scroll/z-index
    if section == "M_scroll_zindex":
        if not section_results.get("header_fixed"):
            findings.append({
                "priority": "P1",
                "section": "M",
                "description": "Header y-offset failure: header not at y=0 after scroll",
                "wcag": "N/A",
                "remediation": "Fix header positioning — should stay at top when .report-view scrolls",
            })
        if not section_results.get("nav_position_correct"):
            findings.append({
                "priority": "P1",
                "section": "M",
                "description": "Nav-bar position incorrect relative to header after scroll",
                "wcag": "N/A",
                "remediation": "Fix nav-bar positioning — should be directly below header",
            })
        if section_results.get("zindex_overlap_detected"):
            findings.append({
                "priority": "P2",
                "section": "M",
                "description": "Z-index overlap: element covers header region after scroll",
                "wcag": "N/A",
                "remediation": "Fix z-index stacking — header must be topmost at y=10",
            })

    # Section N: live interactions
    if section == "N_live_interactions":
        for fail in section_results.get("failures", []):
            test_name = fail.get("test", "")
            # Theme toggle / nav tab / adv tab failures are P1 (core navigation)
            if any(test_name.startswith(p) for p in ("N1_", "N2_", "N3_")):
                priority = "P1"
            else:
                priority = "P2"
            desc_detail = fail.get("error", fail.get("actual", "unknown"))
            findings.append({
                "priority": priority,
                "section": "N",
                "description": f"Live interaction failure: {test_name} — {desc_detail}",
                "wcag": "N/A",
                "remediation": "Fix click handler — element must respond to real clicks",
            })

    # Section O: data extremes
    if section == "O_data_extremes":
        for fail in section_results.get("overflow_failures", []):
            findings.append({
                "priority": fail.get("priority", "P1"),
                "section": "O",
                "description": (
                    f"Chaos overflow: {fail['target']} at {fail['viewport']} "
                    f"({fail.get('excess', '?')}px excess)"
                ),
                "wcag": "WCAG 1.4.10 Reflow",
                "remediation": "Add overflow-x:auto / word-break:break-all to container",
            })

    return findings


def _compute_grade(findings: list[dict[str, Any]], section_results: dict[str, Any]) -> str:
    """Compute overall grade based on findings and section results."""
    p0_count = sum(1 for f in findings if f["priority"] == "P0")
    p1_count = sum(1 for f in findings if f["priority"] == "P1")

    # Unique state count from Section A
    a_results = section_results.get("A_navigation", {})
    duplicate_count = len(a_results.get("duplicate_pairs", []))
    total_states = a_results.get("states_tested", 15)
    unique_ratio = (total_states - duplicate_count) / total_states if total_states > 0 else 0

    # axe-core critical count from Section B
    b_results = section_results.get("B_axe_wcag", {})
    axe_critical = b_results.get("critical_count", 0)

    if p0_count > 10 or unique_ratio < 0.5 or axe_critical > 5:
        return "F"
    if p0_count > 3 or p1_count > 20 or unique_ratio < 0.75:
        return "D"
    if p0_count > 0 or p1_count > 10:
        return "C"
    if p1_count > 3 or axe_critical > 0:
        return "B"
    return "A"


def _generate_html_report(
    all_results: dict[str, Any],
    findings: list[dict[str, Any]],
    grade: str,
) -> str:
    """Generate a self-contained HTML report with embedded screenshots."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Count by priority
    priority_counts = defaultdict(int)
    for f in findings:
        priority_counts[f["priority"]] += 1

    # Section summaries
    section_summaries = []
    for key, data in all_results.get("sections", {}).items():
        passed = data.get("pass", False)
        section_summaries.append({
            "name": key,
            "pass": passed,
            "icon": "PASS" if passed else "FAIL",
        })

    findings_html = ""
    for f in sorted(findings, key=lambda x: x["priority"]):
        color = {"P0": "#ef4444", "P1": "#f97316", "P2": "#eab308", "P3": "#6b7280"}.get(f["priority"], "#6b7280")
        findings_html += f"""
        <tr>
            <td style="color:{color};font-weight:bold">{f['priority']}</td>
            <td>{f['section']}</td>
            <td>{f['description']}</td>
            <td style="font-size:11px">{f['wcag']}</td>
            <td style="font-size:11px">{f['remediation']}</td>
        </tr>"""

    sections_html = ""
    for s in section_summaries:
        bg = "#22c55e" if s["pass"] else "#ef4444"
        sections_html += f'<span style="display:inline-block;padding:4px 12px;margin:3px;border-radius:4px;background:{bg};color:white;font-size:12px">{s["name"]}: {s["icon"]}</span> '

    grade_color = {"A": "#22c55e", "B": "#3b82f6", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}.get(grade, "#6b7280")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>POLARIS Visual QA Audit Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #0f172a; color: #e2e8f0; }}
  h1 {{ color: #38bdf8; border-bottom: 2px solid #1e3a5f; padding-bottom: 8px; }}
  h2 {{ color: #94a3b8; margin-top: 32px; }}
  .grade {{ display: inline-block; font-size: 72px; font-weight: 900; color: {grade_color}; border: 4px solid {grade_color}; border-radius: 16px; padding: 8px 24px; margin: 16px 0; }}
  .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
  .summary-card {{ background: #1e293b; border-radius: 8px; padding: 16px; text-align: center; }}
  .summary-card .value {{ font-size: 28px; font-weight: 700; }}
  .summary-card .label {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
  th {{ background: #1e293b; padding: 8px 12px; text-align: left; color: #94a3b8; border-bottom: 2px solid #334155; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; vertical-align: top; }}
  tr:hover td {{ background: #1e293b33; }}
  .sections {{ margin: 16px 0; }}
  .meta {{ font-size: 12px; color: #64748b; margin: 8px 0; }}
</style>
</head>
<body>
<h1>POLARIS Visual QA Audit Report</h1>
<div class="meta">Generated: {timestamp}</div>

<div class="grade">{grade}</div>

<div class="summary">
  <div class="summary-card"><div class="value" style="color:#ef4444">{priority_counts.get('P0', 0)}</div><div class="label">P0 Critical</div></div>
  <div class="summary-card"><div class="value" style="color:#f97316">{priority_counts.get('P1', 0)}</div><div class="label">P1 High</div></div>
  <div class="summary-card"><div class="value" style="color:#eab308">{priority_counts.get('P2', 0)}</div><div class="label">P2 Medium</div></div>
  <div class="summary-card"><div class="value" style="color:#6b7280">{priority_counts.get('P3', 0)}</div><div class="label">P3 Low</div></div>
</div>

<h2>Section Results</h2>
<div class="sections">{sections_html}</div>

<h2>All Findings ({len(findings)})</h2>
<table>
<thead><tr><th>Priority</th><th>Section</th><th>Description</th><th>WCAG</th><th>Remediation</th></tr></thead>
<tbody>{findings_html}</tbody>
</table>

<h2>Section Details</h2>
<pre style="background:#1e293b;padding:16px;border-radius:8px;overflow-x:auto;font-size:11px;max-height:600px;overflow-y:auto">{json.dumps(all_results.get('sections', {}), indent=2, default=str)}</pre>

</body>
</html>"""
    return html


def section_l_report(
    all_section_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Section L: Generate final report with grading."""
    log.info("=== SECTION L: Report Generation ===")

    # Collect all findings
    all_findings: list[dict[str, Any]] = []
    for section_data in all_section_results.values():
        all_findings.extend(_classify_priority(section_data))

    # Deduplicate findings (same description within same section)
    seen_descs: set[str] = set()
    unique_findings: list[dict[str, Any]] = []
    for f in all_findings:
        key = f"{f['section']}:{f['description'][:120]}"
        if key not in seen_descs:
            seen_descs.add(key)
            unique_findings.append(f)

    grade = _compute_grade(unique_findings, all_section_results)

    # Build final report structure
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "grade": grade,
        "summary": {
            "total_findings": len(unique_findings),
            "P0": sum(1 for f in unique_findings if f["priority"] == "P0"),
            "P1": sum(1 for f in unique_findings if f["priority"] == "P1"),
            "P2": sum(1 for f in unique_findings if f["priority"] == "P2"),
            "P3": sum(1 for f in unique_findings if f["priority"] == "P3"),
        },
        "sections": all_section_results,
        "findings": unique_findings,
    }

    # Write JSON
    json_path = REPORTS_DIR / "audit_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("JSON report: %s (%d bytes)", json_path, json_path.stat().st_size)

    # Write HTML
    html_content = _generate_html_report(report, unique_findings, grade)
    html_path = REPORTS_DIR / "audit_report.html"
    html_path.write_text(html_content, encoding="utf-8")
    log.info("HTML report: %s (%d bytes)", html_path, html_path.stat().st_size)

    return report


# =========================================================================
# MAIN ORCHESTRATOR
# =========================================================================

async def run_audit(
    port: int,
    sections: Optional[list[str]] = None,
    browsers: Optional[list[str]] = None,
    skip_server: bool = False,
) -> dict[str, Any]:
    """Run the full visual QA audit."""
    _ensure_dirs()

    base_url = f"http://localhost:{port}"
    browsers = browsers or ["chromium"]

    # Start server if needed
    server = ServerManager(port)
    if not skip_server:
        await server.start()

    all_results: dict[str, dict[str, Any]] = {}

    try:
        async with async_playwright() as p:
            # Launch primary browser (Chromium)
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale="en-US",
                timezone_id="America/Vancouver",
                viewport=VIEWPORTS["desktop_1440"],
            )
            page = await context.new_page()

            # Pre-page setup: freeze dynamic content + mock routes
            await freeze_dynamic_content(page)
            await setup_mock_routes(page)

            run_all = sections is None
            active_sections = set(s.upper() for s in sections) if sections else set()

            # Phase 1: Navigation + Screenshots (Section A)
            if run_all or "A" in active_sections:
                # Need a fresh page for each state — re-create page per state inside section_a
                all_results["A_navigation"] = await section_a_navigation(page, base_url)

            # Phase 2: WCAG (Section B)
            if run_all or "B" in active_sections:
                all_results["B_axe_wcag"] = await section_b_wcag(page, base_url)

            # Phase 3: Focus (Section D)
            if run_all or "D" in active_sections:
                all_results["D_focus_indicators"] = await section_d_focus(page, base_url)

            # Phase 3: States (Section E)
            if run_all or "E" in active_sections:
                all_results["E_state_testing"] = await section_e_states(page, base_url)

            # Phase 3: Touch (Section F)
            if run_all or "F" in active_sections:
                all_results["F_touch_targets"] = await section_f_touch_targets(page, base_url)

            # Phase 4: Responsive (Section H)
            if run_all or "H" in active_sections:
                all_results["H_responsive"] = await section_h_responsive(page, base_url)

            # Phase 4: Print (Section I)
            if run_all or "I" in active_sections:
                all_results["I_print_stylesheet"] = await section_i_print(page, base_url)

            # Phase 4b: Scroll/Z-Index Stress (Section M)
            if run_all or "M" in active_sections:
                all_results["M_scroll_zindex"] = await section_m_scroll_zindex(page, base_url)

            # Phase 4c: Live Interactions (Section N)
            if run_all or "N" in active_sections:
                all_results["N_live_interactions"] = await section_n_live_interactions(page, base_url)

            # Phase 4d: Data Extremes / Chaos (Section O)
            if run_all or "O" in active_sections:
                all_results["O_data_extremes"] = await section_o_data_extremes(page, base_url)

            await context.close()
            await browser.close()

            # Phase 4: Cross-browser (Section G) — needs separate browser launches
            if run_all or "G" in active_sections:
                all_results["G_cross_browser"] = await section_g_cross_browser(
                    p, base_url, browsers,
                )

            # Phase 5: Baselines (Section K) — needs fresh browser
            if run_all or "K" in active_sections:
                browser2 = await p.chromium.launch(headless=True)
                ctx2 = await browser2.new_context(
                    locale="en-US",
                    timezone_id="America/Vancouver",
                    viewport=VIEWPORTS["desktop_1440"],
                )
                page2 = await ctx2.new_page()
                await freeze_dynamic_content(page2)
                await setup_mock_routes(page2)
                all_results["K_baselines"] = await section_k_baselines(page2, base_url)
                await ctx2.close()
                await browser2.close()

        # Phase 5: CSS Scan (Section J) — no browser needed
        if run_all or "J" in active_sections:
            all_results["J_css_scan"] = section_j_css_scan()

        # Phase 5: Report (Section L)
        report = section_l_report(all_results)

        log.info("=" * 60)
        log.info("AUDIT COMPLETE — Grade: %s", report["grade"])
        log.info(
            "Findings: P0=%d P1=%d P2=%d P3=%d",
            report["summary"]["P0"],
            report["summary"]["P1"],
            report["summary"]["P2"],
            report["summary"]["P3"],
        )
        log.info("Reports: %s", REPORTS_DIR)
        log.info("=" * 60)

        return report

    finally:
        if not skip_server:
            await server.stop()


# =========================================================================
# CLI ENTRY POINT
# =========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POLARIS Visual QA Audit — WCAG 2.2 AA + Production-Grade",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("VQA_PORT", "8766")),
        help="Port for live server (default: 8766)",
    )
    parser.add_argument(
        "--sections", type=str, default=None,
        help="Comma-separated sections to run (A-O, e.g., A,B,D,M,N,O). Default: all 15 sections",
    )
    parser.add_argument(
        "--browser", type=str, default="chromium,firefox,webkit",
        help="Comma-separated browsers for Section G (chromium,firefox,webkit)",
    )
    parser.add_argument(
        "--skip-server", action="store_true",
        help="Skip starting the server (assumes it's already running)",
    )
    args = parser.parse_args()

    sections = args.sections.split(",") if args.sections else None
    browsers = args.browser.split(",") if args.browser else ["chromium"]

    asyncio.run(run_audit(
        port=args.port,
        sections=sections,
        browsers=browsers,
        skip_server=args.skip_server,
    ))


if __name__ == "__main__":
    main()
