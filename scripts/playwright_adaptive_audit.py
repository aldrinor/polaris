"""
POLARIS Observatory — Playwright Adaptive Layout Audit.

Verifies that every tab fills its viewport width intelligently across
6 viewports x 6 tabs = 36 combinations. Measures dead space (gap between
content bounding box and viewport edge) and reports PASS/WARN/FAIL.

Usage:
    python scripts/playwright_adaptive_audit.py --port 8768
    python scripts/playwright_adaptive_audit.py --port 8768 --no-server
    python scripts/playwright_adaptive_audit.py --port 8768 --tabs report,advanced
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("adaptive_audit")

# ---------------------------------------------------------------------------
# Configuration (LAW VI)
# ---------------------------------------------------------------------------
DEFAULT_PORT = int(os.getenv("ADAPTIVE_AUDIT_PORT", "8768"))
OUTPUT_DIR = Path(os.getenv(
    "ADAPTIVE_AUDIT_OUTPUT_DIR",
    str(_PROJECT_ROOT / "outputs" / "adaptive_audit"),
))
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"

# ---------------------------------------------------------------------------
# Viewport matrix
# ---------------------------------------------------------------------------
VIEWPORTS: list[dict[str, Any]] = [
    {"name": "fullhd", "width": 1920, "height": 1080},
    {"name": "laptop", "width": 1440, "height": 900},
    {"name": "small_laptop", "width": 1280, "height": 720},
    {"name": "tablet_land", "width": 1024, "height": 768},
    {"name": "tablet_port", "width": 768, "height": 1024},
    {"name": "phone", "width": 375, "height": 812},
]

# ---------------------------------------------------------------------------
# Tab matrix
# ---------------------------------------------------------------------------
TABS: list[str] = [
    "research", "evidence", "report", "memory", "pipelines", "advanced",
]

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
PASS_THRESHOLD_PCT = float(os.getenv("ADAPTIVE_PASS_PCT", "5.0"))
WARN_THRESHOLD_PCT = float(os.getenv("ADAPTIVE_WARN_PCT", "15.0"))

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ComboResult:
    """Result for one tab x viewport combination."""

    tab: str
    viewport_name: str
    viewport_width: int
    viewport_height: int
    pane_width: float = 0.0
    content_width: float = 0.0
    dead_space_px: float = 0.0
    dead_space_pct: float = 0.0
    verdict: str = "SKIP"
    screenshot: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Dead-space measurement JS
# ---------------------------------------------------------------------------
MEASURE_JS = """
() => {
    // Find the active view pane
    const pane = document.querySelector('.view-pane.active')
        || document.querySelector('.view-pane[style*="display: flex"]')
        || document.querySelector('.view-pane[style*="display: block"]')
        || document.querySelector('.view-pane:not([style*="display: none"])');

    if (!pane) {
        return { error: 'No active view pane found', paneWidth: 0, containerWidth: 0 };
    }

    const paneRect = pane.getBoundingClientRect();
    const paneWidth = paneRect.width;
    const panePadding = parseFloat(window.getComputedStyle(pane).paddingLeft) +
        parseFloat(window.getComputedStyle(pane).paddingRight);
    const usableWidth = paneWidth - panePadding;

    // Strategy: check if any container element has a CSS max-width that is
    // smaller than the usable pane width. This detects layout constraints
    // regardless of whether content is loaded (empty-state safe).
    //
    // We walk visible children (and grandchildren) looking for the TIGHTEST
    // max-width constraint. If max-width resolves to "none" or a px value
    // >= usableWidth, the container is unconstrained. The "effective container
    // width" is min(usableWidth, tightestMaxWidth).

    // Sidebar/panel classes that are intentionally width-constrained
    const SIDEBAR_CLASSES = [
        'pipeline-column', 'phase-list-column', 'evidence-detail-panel',
        'report-toc', 'storm-sidebar', 'compose-bar', 'compose-drawer',
        'nav-bar', 'app-header', 'toast', 'run-query-text',
    ];

    // Check if an element is a main layout container (not sidebar/inline)
    function isLayoutContainer(el, style) {
        const display = style.display;
        if (display === 'inline' || display === 'inline-block') return false;
        // Must have meaningful dimensions
        if (el.offsetHeight < 50 && el.offsetWidth < 200) return false;
        // Exclude intentionally constrained sidebars/panels
        const cls = el.className || '';
        for (const sc of SIDEBAR_CLASSES) {
            if (cls.includes(sc)) return false;
        }
        return true;
    }

    function resolveMaxWidth(el, parentWidth) {
        const computed = window.getComputedStyle(el);
        const mw = computed.maxWidth;
        if (!mw || mw === 'none') return Infinity;
        // Already pixels
        if (mw.endsWith('px')) return parseFloat(mw);
        // Percentage — resolve against parent
        if (mw.endsWith('%')) return (parseFloat(mw) / 100) * parentWidth;
        // Other units (rem, ch, etc.) — use the element's actual rendered width
        // as a proxy since getComputedStyle resolves to px for used values
        return parseFloat(mw) || Infinity;
    }

    let tightest = Infinity;
    let constrainedBy = '';
    const children = pane.querySelectorAll(':scope > *');

    for (const child of children) {
        const style = window.getComputedStyle(child);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (!isLayoutContainer(child, style)) continue;

        const childMw = resolveMaxWidth(child, usableWidth);
        if (childMw < tightest) {
            tightest = childMw;
            constrainedBy = child.className || child.tagName;
        }

        // One level deeper (e.g., .report-view > .report-content)
        const grandchildren = child.querySelectorAll(':scope > *');
        for (const gc of grandchildren) {
            const gcStyle = window.getComputedStyle(gc);
            if (gcStyle.display === 'none' || gcStyle.visibility === 'hidden') continue;
            if (!isLayoutContainer(gc, gcStyle)) continue;
            const gcMw = resolveMaxWidth(gc, child.offsetWidth || usableWidth);
            if (gcMw < tightest) {
                tightest = gcMw;
                constrainedBy = gc.className || gc.tagName;
            }
        }
    }

    // Effective container width = min(usableWidth, tightest max-width)
    const effectiveWidth = Math.min(usableWidth, tightest === Infinity ? usableWidth : tightest);

    return {
        paneWidth: paneWidth,
        containerWidth: effectiveWidth,
        panePadding: panePadding,
        usableWidth: usableWidth,
        constrainedBy: constrainedBy,
        tightestMaxWidthPx: tightest === Infinity ? -1 : tightest,
    };
}
"""


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------

def _start_server(port: int) -> subprocess.Popen:
    """Start the live server as a subprocess, redirect output to log file."""
    log_file = OUTPUT_DIR / "server.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_file, "w")
    proc = subprocess.Popen(
        [sys.executable, str(_PROJECT_ROOT / "scripts" / "live_server.py"),
         "--port", str(port)],
        stdout=fh,
        stderr=subprocess.STDOUT,
        cwd=str(_PROJECT_ROOT),
    )
    log.info("Started live_server.py on port %d (PID %d)", port, proc.pid)
    return proc


async def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    """Poll health endpoint until it returns 200."""
    import urllib.request
    import urllib.error
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.urlopen(url, timeout=2)
            if req.status == 200:
                log.info("Server healthy on port %d", port)
                return True
        except (urllib.error.URLError, OSError, ConnectionRefusedError):
            pass
        await asyncio.sleep(0.5)
    return False


def _stop_server(proc: subprocess.Popen) -> None:
    """Terminate the server subprocess."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.info("Server process terminated")


# ---------------------------------------------------------------------------
# Core audit
# ---------------------------------------------------------------------------

async def _audit_combo(
    page,
    tab: str,
    viewport: dict[str, Any],
    port: int,
) -> ComboResult:
    """Measure dead space for one tab x viewport combination."""
    result = ComboResult(
        tab=tab,
        viewport_name=viewport["name"],
        viewport_width=viewport["width"],
        viewport_height=viewport["height"],
    )

    try:
        # Set viewport size
        await page.set_viewport_size({
            "width": viewport["width"],
            "height": viewport["height"],
        })

        # Navigate to base URL (domcontentloaded — SSE connections prevent networkidle)
        await page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(500)

        # Switch to operator mode and navigate to tab
        setup_js = f"setViewMode('operator'); switchView('{tab}')"
        await page.evaluate(setup_js)
        await page.wait_for_timeout(500)

        # Take screenshot
        screenshot_name = f"{tab}_{viewport['width']}x{viewport['height']}.png"
        screenshot_path = SCREENSHOT_DIR / screenshot_name
        await page.screenshot(path=str(screenshot_path), full_page=False)
        result.screenshot = screenshot_name

        # Measure dead space
        metrics = await page.evaluate(MEASURE_JS)

        if metrics.get("error"):
            result.error = metrics["error"]
            result.verdict = "SKIP"
            return result

        pane_width = metrics["paneWidth"]
        container_width = metrics["containerWidth"]
        usable_width = metrics["usableWidth"]

        # Dead space = usable pane width minus container width
        dead_space = max(0, usable_width - container_width)
        dead_pct = (dead_space / usable_width * 100) if usable_width > 0 else 0

        result.pane_width = round(pane_width, 1)
        result.content_width = round(container_width, 1)
        result.dead_space_px = round(dead_space, 1)
        result.dead_space_pct = round(dead_pct, 1)

        if dead_pct > PASS_THRESHOLD_PCT:
            constrained = metrics.get("constrainedBy", "unknown")
            tightest_px = metrics.get("tightestMaxWidthPx", -1)
            log.warning("  Constraint: max-width=%.0fpx on '%s'", tightest_px, constrained)

        if dead_pct <= PASS_THRESHOLD_PCT:
            result.verdict = "PASS"
        elif dead_pct <= WARN_THRESHOLD_PCT:
            result.verdict = "WARN"
        else:
            result.verdict = "FAIL"

    except Exception as exc:
        result.error = str(exc)
        result.verdict = "ERROR"
        log.error("Error auditing %s @ %s: %s", tab, viewport["name"], exc)

    return result


async def run_audit(
    port: int,
    tabs: list[str],
    viewports: list[dict[str, Any]],
) -> list[ComboResult]:
    """Run the full adaptive audit across all tab x viewport combos."""
    results: list[ComboResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        page = await context.new_page()

        total = len(tabs) * len(viewports)
        done = 0

        for tab in tabs:
            for vp in viewports:
                done += 1
                label = f"[{done}/{total}] {tab} @ {vp['name']} ({vp['width']}x{vp['height']})"
                log.info("Auditing %s", label)

                result = await _audit_combo(page, tab, vp, port)
                results.append(result)

                verdict_color = {
                    "PASS": "\033[32m",
                    "WARN": "\033[33m",
                    "FAIL": "\033[31m",
                    "ERROR": "\033[31m",
                    "SKIP": "\033[90m",
                }.get(result.verdict, "")
                log.info(
                    "  %s%s\033[0m — pane=%.0fpx content=%.0fpx dead=%.0fpx (%.1f%%)",
                    verdict_color, result.verdict,
                    result.pane_width, result.content_width,
                    result.dead_space_px, result.dead_space_pct,
                )

        await browser.close()

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_summary(results: list[ComboResult]) -> int:
    """Print a formatted summary table. Returns exit code."""
    print("\n" + "=" * 80)
    print("  ADAPTIVE LAYOUT AUDIT — SUMMARY")
    print("=" * 80)
    print(f"  {'Tab':<12} {'Viewport':<14} {'Size':>10} {'Pane':>8} "
          f"{'Content':>8} {'Dead':>8} {'%':>6} {'Verdict':>8}")
    print("-" * 80)

    fail_count = 0
    warn_count = 0
    pass_count = 0

    for r in results:
        verdict_str = r.verdict
        size_str = f"{r.viewport_width}x{r.viewport_height}"

        if r.verdict == "FAIL":
            fail_count += 1
            marker = "\033[31mFAIL\033[0m"
        elif r.verdict == "WARN":
            warn_count += 1
            marker = "\033[33mWARN\033[0m"
        elif r.verdict == "PASS":
            pass_count += 1
            marker = "\033[32mPASS\033[0m"
        elif r.verdict == "ERROR":
            fail_count += 1
            marker = "\033[31mERR \033[0m"
        else:
            marker = "\033[90mSKIP\033[0m"

        print(f"  {r.tab:<12} {r.viewport_name:<14} {size_str:>10} "
              f"{r.pane_width:>7.0f}px {r.content_width:>7.0f}px "
              f"{r.dead_space_px:>7.0f}px {r.dead_space_pct:>5.1f}% {marker:>8}")

    print("-" * 80)
    total = len(results)
    print(f"  TOTAL: {total}  |  PASS: {pass_count}  |  WARN: {warn_count}  "
          f"|  FAIL: {fail_count}")

    if fail_count == 0 and warn_count == 0:
        print("\033[32m  ALL COMBOS PASS\033[0m")
    elif fail_count == 0:
        print(f"\033[33m  {warn_count} warnings, 0 failures\033[0m")
    else:
        print(f"\033[31m  {fail_count} FAILURES detected\033[0m")
    print("=" * 80 + "\n")

    return 1 if fail_count > 0 else 0


def _write_report(results: list[ComboResult]) -> Path:
    """Write JSON report to disk."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "pass_pct": PASS_THRESHOLD_PCT,
            "warn_pct": WARN_THRESHOLD_PCT,
        },
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r.verdict == "PASS"),
            "warn": sum(1 for r in results if r.verdict == "WARN"),
            "fail": sum(1 for r in results if r.verdict == "FAIL"),
            "error": sum(1 for r in results if r.verdict == "ERROR"),
        },
        "results": [asdict(r) for r in results],
    }
    report_path = OUTPUT_DIR / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    log.info("Report written to %s", report_path)
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main(args: argparse.Namespace) -> int:
    """Entry point for the adaptive audit."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Filter tabs if specified
    tabs = TABS
    if args.tabs:
        requested = [t.strip() for t in args.tabs.split(",")]
        tabs = [t for t in requested if t in TABS]
        if not tabs:
            log.error("No valid tabs in --tabs=%s. Available: %s", args.tabs, TABS)
            return 1

    # Filter viewports if specified
    viewports = VIEWPORTS
    if args.viewports:
        requested_vp = [v.strip() for v in args.viewports.split(",")]
        viewports = [v for v in VIEWPORTS if v["name"] in requested_vp]
        if not viewports:
            log.error("No valid viewports in --viewports=%s", args.viewports)
            return 1

    port = args.port
    server_proc = None

    # Start server if needed
    if not args.no_server:
        server_proc = _start_server(port)
        healthy = await _wait_for_server(port)
        if not healthy:
            log.error("Server failed to start on port %d within timeout", port)
            if server_proc:
                _stop_server(server_proc)
            return 1

    try:
        results = await run_audit(port, tabs, viewports)
        _write_report(results)
        exit_code = _print_summary(results)
        return exit_code
    finally:
        if server_proc:
            _stop_server(server_proc)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="POLARIS Adaptive Layout Audit — dead-space verification",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-server", action="store_true",
        help="Skip auto-starting the server (assumes already running)",
    )
    parser.add_argument(
        "--tabs", type=str, default="",
        help="Comma-separated tab filter (e.g., report,advanced)",
    )
    parser.add_argument(
        "--viewports", type=str, default="",
        help="Comma-separated viewport filter (e.g., fullhd,laptop)",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
