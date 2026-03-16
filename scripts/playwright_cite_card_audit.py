"""
Playwright-based visual audit for citation card redesign and popover resize.

Validates CSS properties, DOM structure, hover interactions, and popover
geometry against the specification. Outputs a JSON report and console
summary with PASS/FAIL per check.

Usage:
    python scripts/playwright_cite_card_audit.py [--port PORT] [--output-dir DIR]

Requirements:
    - playwright (async_api)
    - scripts/live_server.py (FastAPI server)
    - scripts/static/js/test_report.js (test bibliography data)
"""

import argparse
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Page

# ---------------------------------------------------------------------------
# Project root (LAW VI -- no hard-coded paths)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_TEST_REPORT_JS = _SCRIPTS_DIR / "static" / "js" / "test_report.js"
_LIVE_SERVER_SCRIPT = _SCRIPTS_DIR / "live_server.py"
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "cite_card_audit"

# ---------------------------------------------------------------------------
# Timing constants (LAW VI -- configurable via env)
# ---------------------------------------------------------------------------
SERVER_READY_TIMEOUT_S = int(os.getenv("PW_SERVER_READY_TIMEOUT", "15"))
SERVER_POLL_INTERVAL_S = float(os.getenv("PW_SERVER_POLL_INTERVAL", "0.5"))
DOM_SETTLE_MS = int(os.getenv("PW_DOM_SETTLE_MS", "500"))
POPOVER_HOVER_MS = int(os.getenv("PW_POPOVER_HOVER_MS", "300"))
PAGE_LOAD_TIMEOUT_MS = int(os.getenv("PW_PAGE_LOAD_TIMEOUT_MS", "60000"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cite_card_audit")


# ---------------------------------------------------------------------------
# Utility: find a free TCP port
# ---------------------------------------------------------------------------
def find_free_port() -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ---------------------------------------------------------------------------
# Utility: wait for server readiness
# ---------------------------------------------------------------------------
async def wait_for_server(port: int, timeout_s: int) -> bool:
    """Poll the server TCP port until it accepts connections or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(SERVER_POLL_INTERVAL_S)
    return False


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------
def start_server(port: int, log_dir: Path) -> subprocess.Popen:
    """
    Start live_server.py on the given port with --no-tunnel.

    CRITICAL: stdout/stderr redirected to a log file to avoid
    subprocess.PIPE deadlocks on Windows (MEMORY lesson #16).
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    server_log_path = log_dir / "cite_card_audit_server.log"
    server_log_handle = open(server_log_path, "w", encoding="utf-8")

    cmd = [
        sys.executable,
        str(_LIVE_SERVER_SCRIPT),
        "--port", str(port),
        "--no-tunnel",
    ]
    logger.info("Starting server: %s", " ".join(cmd))
    logger.info("Server log: %s", server_log_path)

    proc = subprocess.Popen(
        cmd,
        stdout=server_log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(_PROJECT_ROOT),
    )
    # Keep handle reference so it stays open while server runs
    proc._log_handle = server_log_handle  # type: ignore[attr-defined]
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    """Terminate the server process and close the log handle."""
    if proc.poll() is None:
        logger.info("Terminating server (pid=%d)", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    log_handle = getattr(proc, "_log_handle", None)
    if log_handle and not log_handle.closed:
        log_handle.close()


# ---------------------------------------------------------------------------
# Check result helpers
# ---------------------------------------------------------------------------
class CheckResult:
    """Container for a single audit check result."""

    def __init__(self, check_id: str, description: str):
        self.check_id = check_id
        self.description = description
        self.passed: bool = False
        self.actual: Any = None
        self.expected: Any = None
        self.error: str | None = None

    def set_pass(self, actual: Any = None, expected: Any = None) -> "CheckResult":
        self.passed = True
        self.actual = actual
        self.expected = expected
        return self

    def set_fail(
        self, actual: Any = None, expected: Any = None, error: str | None = None
    ) -> "CheckResult":
        self.passed = False
        self.actual = actual
        self.expected = expected
        self.error = error
        return self

    def to_dict(self) -> dict:
        result = {
            "check_id": self.check_id,
            "description": self.description,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
        }
        if self.error:
            result["error"] = self.error
        return result


# ---------------------------------------------------------------------------
# Computed style helper (runs in browser context)
# ---------------------------------------------------------------------------
async def get_computed_style(page: Page, selector: str, prop: str) -> str:
    """Return a computed CSS property value for the first matching element."""
    return await page.evaluate(
        """
        ([sel, prop]) => {
            const el = document.querySelector(sel);
            if (!el) return '__NOT_FOUND__';
            return window.getComputedStyle(el)[prop];
        }
        """,
        [selector, prop],
    )


async def get_computed_style_nth(
    page: Page, selector: str, prop: str, index: int = 0
) -> str:
    """Return a computed CSS property for the Nth matching element."""
    return await page.evaluate(
        """
        ([sel, prop, idx]) => {
            const els = document.querySelectorAll(sel);
            if (!els[idx]) return '__NOT_FOUND__';
            return window.getComputedStyle(els[idx])[prop];
        }
        """,
        [selector, prop, index],
    )


async def element_count(page: Page, selector: str) -> int:
    """Return count of elements matching selector."""
    return await page.evaluate(
        "(sel) => document.querySelectorAll(sel).length", selector
    )


async def element_text(page: Page, selector: str) -> str:
    """Return textContent of first matching element."""
    return await page.evaluate(
        """
        (sel) => {
            const el = document.querySelector(sel);
            return el ? el.textContent.trim() : '__NOT_FOUND__';
        }
        """,
        selector,
    )


# ---------------------------------------------------------------------------
# Citation Card checks (C1 -- C11)
# ---------------------------------------------------------------------------
async def run_card_checks(page: Page) -> list[CheckResult]:
    """Execute all citation card visual checks."""
    results: list[CheckResult] = []

    # C1: 5 .ws-cite-card elements exist
    c1 = CheckResult("C1", "5 .ws-cite-card elements exist")
    count = await element_count(page, ".ws-cite-card")
    if count == 5:
        c1.set_pass(actual=count, expected=5)
    else:
        c1.set_fail(actual=count, expected=5, error=f"Found {count} cards, expected 5")
    results.append(c1)

    # C2: .ws-cite-card-num has pill shape (border-radius >= 10px, background not empty)
    c2 = CheckResult("C2", ".ws-cite-card-num pill shape (border-radius >= 10px, accent background)")
    border_radius = await get_computed_style(page, ".ws-cite-card-num", "borderRadius")
    background = await get_computed_style(page, ".ws-cite-card-num", "backgroundColor")
    br_value = _parse_px(border_radius)
    has_bg = background not in ("", "none", "transparent", "rgba(0, 0, 0, 0)")
    if br_value >= 10 and has_bg:
        c2.set_pass(
            actual={"border_radius": border_radius, "background": background},
            expected="border-radius >= 10px, background not empty",
        )
    else:
        c2.set_fail(
            actual={"border_radius": border_radius, "background": background},
            expected="border-radius >= 10px, background not empty",
            error=f"br={br_value}px (>= 10?), has_bg={has_bg}",
        )
    results.append(c2)

    # C3: .ws-cite-card-num shows just the number (no brackets)
    c3 = CheckResult("C3", ".ws-cite-card-num shows plain number (no brackets)")
    num_text = await element_text(page, ".ws-cite-card-num")
    if num_text == "1":
        c3.set_pass(actual=num_text, expected="1")
    else:
        c3.set_fail(actual=num_text, expected="1", error=f"Text is '{num_text}', expected '1'")
    results.append(c3)

    # C4: .ws-cite-card-title has font-weight 600
    c4 = CheckResult("C4", ".ws-cite-card-title font-weight is 600")
    fw = await get_computed_style(page, ".ws-cite-card-title", "fontWeight")
    if fw == "600":
        c4.set_pass(actual=fw, expected="600")
    else:
        c4.set_fail(actual=fw, expected="600", error=f"font-weight is {fw}")
    results.append(c4)

    # C5: .ws-cite-card-title has -webkit-line-clamp: 2
    c5 = CheckResult("C5", ".ws-cite-card-title has -webkit-line-clamp: 2")
    line_clamp = await page.evaluate(
        """
        () => {
            const el = document.querySelector('.ws-cite-card-title');
            if (!el) return '__NOT_FOUND__';
            return window.getComputedStyle(el).webkitLineClamp || window.getComputedStyle(el)['-webkit-line-clamp'] || '';
        }
        """
    )
    if str(line_clamp) == "2":
        c5.set_pass(actual=line_clamp, expected="2")
    else:
        c5.set_fail(actual=line_clamp, expected="2", error=f"line-clamp is '{line_clamp}'")
    results.append(c5)

    # C6: .ws-cite-card-favicon width 18px and border not empty
    c6 = CheckResult("C6", ".ws-cite-card-favicon width 18px with border")
    favicon_width = await get_computed_style(page, ".ws-cite-card-favicon", "width")
    favicon_border = await get_computed_style(
        page, ".ws-cite-card-favicon", "borderStyle"
    )
    fw_px = _parse_px(favicon_width)
    has_border = favicon_border not in ("", "none")
    if fw_px == 18 and has_border:
        c6.set_pass(
            actual={"width": favicon_width, "border_style": favicon_border},
            expected="width=18px, border present",
        )
    else:
        c6.set_fail(
            actual={"width": favicon_width, "border_style": favicon_border},
            expected="width=18px, border present",
            error=f"width={fw_px}px, border={favicon_border}",
        )
    results.append(c6)

    # C7: At least 3 .ws-cite-card-snippet elements
    c7 = CheckResult("C7", "At least 3 .ws-cite-card-snippet elements exist")
    snippet_count = await element_count(page, ".ws-cite-card-snippet")
    if snippet_count >= 3:
        c7.set_pass(actual=snippet_count, expected=">= 3")
    else:
        c7.set_fail(
            actual=snippet_count, expected=">= 3",
            error=f"Found {snippet_count} snippets",
        )
    results.append(c7)

    # C8: Card 5 (unverified) badge has class 'unverified' and amber background
    c8 = CheckResult("C8", "Card 5 badge is 'unverified' with amber background")
    badge_5_classes = await page.evaluate(
        """
        () => {
            const card = document.querySelector('.ws-cite-card[data-cite-num="5"]');
            if (!card) return '__NO_CARD__';
            const badge = card.querySelector('.ws-cite-card-badge');
            if (!badge) return '__NO_BADGE__';
            return badge.className;
        }
        """
    )
    badge_5_bg = await page.evaluate(
        """
        () => {
            const card = document.querySelector('.ws-cite-card[data-cite-num="5"]');
            if (!card) return '__NO_CARD__';
            const badge = card.querySelector('.ws-cite-card-badge');
            if (!badge) return '__NO_BADGE__';
            return window.getComputedStyle(badge).backgroundColor;
        }
        """
    )
    has_unverified_class = "unverified" in str(badge_5_classes)
    is_amber_ish = _is_amber_background(str(badge_5_bg))
    if has_unverified_class and is_amber_ish:
        c8.set_pass(
            actual={"classes": badge_5_classes, "background": badge_5_bg},
            expected="class 'unverified', amber background",
        )
    else:
        c8.set_fail(
            actual={"classes": badge_5_classes, "background": badge_5_bg},
            expected="class 'unverified', amber background",
            error=f"unverified_class={has_unverified_class}, amber={is_amber_ish}",
        )
    results.append(c8)

    # C9: Card 1 (verified) badge has class 'verified' and green background
    c9 = CheckResult("C9", "Card 1 badge is 'verified' with green background")
    badge_1_classes = await page.evaluate(
        """
        () => {
            const card = document.querySelector('.ws-cite-card[data-cite-num="1"]');
            if (!card) return '__NO_CARD__';
            const badge = card.querySelector('.ws-cite-card-badge');
            if (!badge) return '__NO_BADGE__';
            return badge.className;
        }
        """
    )
    badge_1_bg = await page.evaluate(
        """
        () => {
            const card = document.querySelector('.ws-cite-card[data-cite-num="1"]');
            if (!card) return '__NO_CARD__';
            const badge = card.querySelector('.ws-cite-card-badge');
            if (!badge) return '__NO_BADGE__';
            return window.getComputedStyle(badge).backgroundColor;
        }
        """
    )
    has_verified_class = "verified" in str(badge_1_classes) and "unverified" not in str(badge_1_classes)
    is_green_ish = _is_green_background(str(badge_1_bg))
    if has_verified_class and is_green_ish:
        c9.set_pass(
            actual={"classes": badge_1_classes, "background": badge_1_bg},
            expected="class 'verified', green background",
        )
    else:
        c9.set_fail(
            actual={"classes": badge_1_classes, "background": badge_1_bg},
            expected="class 'verified', green background",
            error=f"verified_class={has_verified_class}, green={is_green_ish}",
        )
    results.append(c9)

    # C10: .ws-cite-card border-radius is 10px
    c10 = CheckResult("C10", ".ws-cite-card border-radius is 10px")
    card_br = await get_computed_style(page, ".ws-cite-card", "borderRadius")
    card_br_px = _parse_px(card_br)
    if card_br_px == 10:
        c10.set_pass(actual=card_br, expected="10px")
    else:
        c10.set_fail(actual=card_br, expected="10px", error=f"border-radius is {card_br}")
    results.append(c10)

    # C11: .ws-cite-card hover shadow appears
    c11 = CheckResult("C11", ".ws-cite-card hover produces box-shadow")
    card_1 = page.locator('.ws-cite-card[data-cite-num="1"]')
    await card_1.hover()
    # Small delay for CSS transition to complete
    await page.wait_for_timeout(200)
    shadow_after_hover = await page.evaluate(
        """
        () => {
            const card = document.querySelector('.ws-cite-card[data-cite-num="1"]');
            if (!card) return 'none';
            return window.getComputedStyle(card).boxShadow;
        }
        """
    )
    if shadow_after_hover and shadow_after_hover != "none":
        c11.set_pass(actual=shadow_after_hover, expected="not 'none'")
    else:
        c11.set_fail(
            actual=shadow_after_hover,
            expected="not 'none'",
            error="No box-shadow on hover",
        )
    results.append(c11)

    # Move mouse away to clear hover state
    await page.mouse.move(0, 0)
    await page.wait_for_timeout(100)

    return results


# ---------------------------------------------------------------------------
# Popover checks (P1 -- P6)
# ---------------------------------------------------------------------------
async def run_popover_checks(page: Page) -> list[CheckResult]:
    """Execute all popover visual checks."""
    results: list[CheckResult] = []

    # P1: Hover card 1 for 300ms, popover appears
    p1 = CheckResult("P1", "Popover .ws-cite-popover appears on hover (300ms)")
    card_1 = page.locator('.ws-cite-card[data-cite-num="1"]')
    await card_1.hover()
    await page.wait_for_timeout(POPOVER_HOVER_MS)
    popover_visible = await page.evaluate(
        """
        () => {
            const pop = document.querySelector('.ws-cite-popover');
            if (!pop) return false;
            const rect = pop.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }
        """
    )
    if popover_visible:
        p1.set_pass(actual="visible", expected="visible")
    else:
        p1.set_fail(actual="not visible", expected="visible", error="Popover not found or zero-size")
    results.append(p1)

    # P2: Popover width ~480px (470-490)
    p2 = CheckResult("P2", "Popover width is ~480px (470-490)")
    popover_width = await page.evaluate(
        """
        () => {
            const pop = document.querySelector('.ws-cite-popover');
            if (!pop) return -1;
            return pop.getBoundingClientRect().width;
        }
        """
    )
    if 470 <= popover_width <= 490:
        p2.set_pass(actual=popover_width, expected="470-490")
    else:
        p2.set_fail(
            actual=popover_width, expected="470-490",
            error=f"Width is {popover_width}px",
        )
    results.append(p2)

    # P3: Popover max-height >= 600px
    p3 = CheckResult("P3", "Popover max-height >= 600px")
    popover_max_h = await get_computed_style(page, ".ws-cite-popover", "maxHeight")
    max_h_px = _parse_px(popover_max_h)
    if max_h_px >= 600:
        p3.set_pass(actual=popover_max_h, expected=">= 600px")
    else:
        p3.set_fail(
            actual=popover_max_h, expected=">= 600px",
            error=f"max-height is {popover_max_h}",
        )
    results.append(p3)

    # P4: .ws-popover-iframe-wrap height ~340px (330-350)
    p4 = CheckResult("P4", ".ws-popover-iframe-wrap height ~340px (330-350)")
    iframe_wrap_h = await page.evaluate(
        """
        () => {
            const wrap = document.querySelector('.ws-popover-iframe-wrap');
            if (!wrap) return -1;
            return wrap.getBoundingClientRect().height;
        }
        """
    )
    if 330 <= iframe_wrap_h <= 350:
        p4.set_pass(actual=iframe_wrap_h, expected="330-350")
    else:
        p4.set_fail(
            actual=iframe_wrap_h, expected="330-350",
            error=f"Height is {iframe_wrap_h}px",
        )
    results.append(p4)

    # P5: .ws-popover-chrome padding ~10px 14px
    p5 = CheckResult("P5", ".ws-popover-chrome padding is approximately 10px 14px")
    chrome_pt = await get_computed_style(page, ".ws-popover-chrome", "paddingTop")
    chrome_pr = await get_computed_style(page, ".ws-popover-chrome", "paddingRight")
    chrome_pb = await get_computed_style(page, ".ws-popover-chrome", "paddingBottom")
    chrome_pl = await get_computed_style(page, ".ws-popover-chrome", "paddingLeft")
    pt = _parse_px(chrome_pt)
    pr = _parse_px(chrome_pr)
    pb = _parse_px(chrome_pb)
    pl = _parse_px(chrome_pl)
    # Allow +/- 2px tolerance
    vertical_ok = abs(pt - 10) <= 2 and abs(pb - 10) <= 2
    horizontal_ok = abs(pr - 14) <= 2 and abs(pl - 14) <= 2
    if vertical_ok and horizontal_ok:
        p5.set_pass(
            actual=f"{chrome_pt} {chrome_pr} {chrome_pb} {chrome_pl}",
            expected="~10px 14px 10px 14px",
        )
    else:
        p5.set_fail(
            actual=f"{chrome_pt} {chrome_pr} {chrome_pb} {chrome_pl}",
            expected="~10px 14px 10px 14px",
            error=f"Padding: {pt} {pr} {pb} {pl}",
        )
    results.append(p5)

    # P6: .ws-popover-title-sm max-width >= 250px
    p6 = CheckResult("P6", ".ws-popover-title-sm max-width >= 250px")
    title_mw = await get_computed_style(page, ".ws-popover-title-sm", "maxWidth")
    mw_px = _parse_px(title_mw)
    if mw_px >= 250:
        p6.set_pass(actual=title_mw, expected=">= 250px")
    else:
        p6.set_fail(
            actual=title_mw, expected=">= 250px",
            error=f"max-width is {title_mw}",
        )
    results.append(p6)

    # Move mouse away to dismiss popover
    await page.mouse.move(0, 0)
    await page.wait_for_timeout(200)

    return results


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------
async def capture_screenshots(page: Page, output_dir: Path) -> list[str]:
    """Capture before-hover, after-hover, and single-card screenshots."""
    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    captured: list[str] = []

    # 1. Full-page BEFORE hover
    before_path = screenshots_dir / "full_page_before_hover.png"
    await page.screenshot(path=str(before_path), full_page=True)
    captured.append(str(before_path))
    logger.info("Screenshot: %s", before_path)

    # 2. Single citation card element screenshot
    card_1 = page.locator('.ws-cite-card[data-cite-num="1"]')
    card_path = screenshots_dir / "single_card_1.png"
    await card_1.screenshot(path=str(card_path))
    captured.append(str(card_path))
    logger.info("Screenshot: %s", card_path)

    # 3. Full-page AFTER hover (with popover visible)
    await card_1.hover()
    await page.wait_for_timeout(POPOVER_HOVER_MS)
    after_path = screenshots_dir / "full_page_after_hover.png"
    await page.screenshot(path=str(after_path), full_page=True)
    captured.append(str(after_path))
    logger.info("Screenshot: %s", after_path)

    # Move mouse away
    await page.mouse.move(0, 0)
    await page.wait_for_timeout(100)

    return captured


# ---------------------------------------------------------------------------
# Pixel parsing helpers
# ---------------------------------------------------------------------------
def _parse_px(value: str) -> float:
    """Extract numeric pixel value from a CSS string like '10px' or '10.5px'.

    Returns -1 if the value cannot be parsed.
    """
    if not value or value == "__NOT_FOUND__":
        return -1
    cleaned = value.strip().lower().replace("px", "")
    try:
        return float(cleaned)
    except ValueError:
        return -1


def _is_amber_background(bg: str) -> bool:
    """Check if an rgba/rgb color string is amber-ish (high R, mid G, low B)."""
    rgba = _parse_rgba(bg)
    if rgba is None:
        return False
    r, g, b, _a = rgba
    # Amber: R > G > B with G reasonably high
    # For rgba(251, 191, 36, 0.1) the computed value stays as-is in Chromium
    if r == 0 and g == 0 and b == 0:
        return False
    return r > g > b and g > 5


def _is_green_background(bg: str) -> bool:
    """Check if an rgba/rgb color string is green-ish (high G, lower R/B)."""
    rgba = _parse_rgba(bg)
    if rgba is None:
        return False
    r, g, b, _a = rgba
    # For rgba(74, 222, 128, 0.1) the computed value has G dominant
    if r == 0 and g == 0 and b == 0:
        return False
    return g > r and g > b


def _parse_rgba(color_str: str) -> tuple[float, float, float, float] | None:
    """Parse 'rgba(r, g, b, a)' or 'rgb(r, g, b)' into a tuple."""
    if not color_str:
        return None
    color_str = color_str.strip()
    if color_str.startswith("rgba(") and color_str.endswith(")"):
        inner = color_str[5:-1]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 4:
            try:
                return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError:
                return None
    elif color_str.startswith("rgb(") and color_str.endswith(")"):
        inner = color_str[4:-1]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 3:
            try:
                return (float(parts[0]), float(parts[1]), float(parts[2]), 1.0)
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(
    card_results: list[CheckResult],
    popover_results: list[CheckResult],
    screenshots: list[str],
    output_dir: Path,
) -> dict:
    """Build and write the JSON audit report."""
    all_results = card_results + popover_results
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed

    report = {
        "audit": "cite_card_popover_audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{(passed / total * 100) if total > 0 else 0:.1f}%",
        },
        "card_checks": [r.to_dict() for r in card_results],
        "popover_checks": [r.to_dict() for r in popover_results],
        "screenshots": screenshots,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "cite_card_audit_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    logger.info("Report written: %s", report_path)

    return report


def print_console_summary(report: dict) -> None:
    """Print a human-readable PASS/FAIL summary to stdout."""
    summary = report["summary"]
    print("\n" + "=" * 60)
    print("  CITATION CARD AUDIT RESULTS")
    print("=" * 60)
    print(f"  Total checks: {summary['total_checks']}")
    print(f"  Passed:       {summary['passed']}")
    print(f"  Failed:       {summary['failed']}")
    print(f"  Pass rate:    {summary['pass_rate']}")
    print("-" * 60)

    for section_name, section_key in [
        ("Card Checks", "card_checks"),
        ("Popover Checks", "popover_checks"),
    ]:
        print(f"\n  {section_name}:")
        for check in report[section_key]:
            marker = "[PASS]" if check["passed"] else "[FAIL]"
            line = f"    {marker} {check['check_id']}: {check['description']}"
            if not check["passed"] and check.get("error"):
                line += f"  -- {check['error']}"
            print(line)

    print("\n  Screenshots:")
    for path in report.get("screenshots", []):
        print(f"    - {path}")

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Main audit workflow
# ---------------------------------------------------------------------------
async def run_audit(port: int, output_dir: Path) -> dict:
    """Execute the full cite card + popover audit."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read test_report.js content for injection
    if not _TEST_REPORT_JS.exists():
        raise FileNotFoundError(f"Test data not found: {_TEST_REPORT_JS}")
    test_js_content = _TEST_REPORT_JS.read_text(encoding="utf-8")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Set generous navigation timeout (dashboard loads heavy JS + SSE)
        page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT_MS)

        # Navigate to the dashboard.
        # CRITICAL: Use "domcontentloaded" instead of "networkidle" because
        # the dashboard opens SSE streams that keep the network perpetually
        # active, causing "networkidle" to never fire.
        dashboard_url = f"http://127.0.0.1:{port}/"
        logger.info("Navigating to %s", dashboard_url)
        await page.goto(dashboard_url, wait_until="domcontentloaded")

        # Wait for all CSS and JS to load (stylesheets, workspace_manager.js)
        logger.info("Waiting for page scripts to initialize...")
        await page.wait_for_timeout(3000)

        # Verify key functions exist before injecting test data
        functions_ready = await page.evaluate(
            """
            () => {
                return typeof setWorkspacePhase === 'function'
                    && typeof renderCitationSidebar === 'function';
            }
            """
        )
        if not functions_ready:
            raise RuntimeError(
                "Dashboard JS not fully loaded: setWorkspacePhase or "
                "renderCitationSidebar not found after 3s wait"
            )
        logger.info("Dashboard JS functions confirmed available.")

        # Inject test data via page.evaluate()
        logger.info("Injecting test_report.js content")
        await page.evaluate(test_js_content)

        # Wait for DOM to settle after rendering citation cards
        await page.wait_for_timeout(DOM_SETTLE_MS)

        # Run checks
        logger.info("Running citation card checks (C1-C11)...")
        card_results = await run_card_checks(page)

        logger.info("Running popover checks (P1-P6)...")
        popover_results = await run_popover_checks(page)

        logger.info("Capturing screenshots...")
        screenshots = await capture_screenshots(page, output_dir)

        await browser.close()

    # Generate report
    report = generate_report(card_results, popover_results, screenshots, output_dir)
    print_console_summary(report)

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Playwright audit for citation card redesign and popover resize"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Server port (0 = auto-detect free port)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(_DEFAULT_OUTPUT_DIR),
        help=f"Output directory for report and screenshots (default: {_DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


async def async_main() -> None:
    """Async entry point: start server, run audit, cleanup."""
    args = parse_args()
    port = args.port if args.port > 0 else find_free_port()
    output_dir = Path(args.output_dir)

    logger.info("Audit output directory: %s", output_dir)
    logger.info("Using port: %d", port)

    # Start the server
    server_proc = start_server(port, output_dir)
    try:
        # Wait for server to be ready
        logger.info(
            "Waiting up to %ds for server on port %d...",
            SERVER_READY_TIMEOUT_S, port,
        )
        ready = await wait_for_server(port, SERVER_READY_TIMEOUT_S)
        if not ready:
            raise RuntimeError(
                f"Server did not become ready within {SERVER_READY_TIMEOUT_S}s on port {port}"
            )
        logger.info("Server is ready.")

        # Run the audit
        report = await run_audit(port, output_dir)

        # Exit with non-zero if any checks failed
        if report["summary"]["failed"] > 0:
            sys.exit(1)

    finally:
        stop_server(server_proc)
        logger.info("Server stopped. Audit complete.")


def main() -> None:
    """Synchronous entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
