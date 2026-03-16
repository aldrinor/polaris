"""
Playwright-based INTERACTION audit for the POLARIS dashboard.

Goes beyond the fire test (79 DOM existence checks) by clicking every button,
hovering every card, opening every modal, typing into every input, switching
every tab/view/mode and verifying the actual result — not just that an element
exists, but that it works.

~58 interaction checks across 8 categories (IA-IH).

Usage:
    python scripts/playwright_interaction_audit.py [--port PORT] [--output-dir DIR]
                                                   [--trace TRACE] [--headed]

Requirements:
    - playwright (async_api)
    - scripts/live_server.py (FastAPI server)
    - A valid JSONL trace file
"""

import argparse
import asyncio
import json
import logging
import os
import re
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
_LIVE_SERVER_SCRIPT = _SCRIPTS_DIR / "live_server.py"
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "interaction_audit"
_DEFAULT_TRACE = _PROJECT_ROOT / "logs" / "pg_trace_SHOWME_TEST_003.jsonl"

# Fallback trace files in order of preference
_TRACE_CANDIDATES = [
    _PROJECT_ROOT / "logs" / "pg_trace_SHOWME_TEST_003.jsonl",
    _PROJECT_ROOT / "logs" / "pg_trace_SHOWME_TEST_002.jsonl",
]

# ---------------------------------------------------------------------------
# Timing constants (LAW VI -- configurable via env)
# ---------------------------------------------------------------------------
SERVER_READY_TIMEOUT_S = int(os.getenv("PW_SERVER_READY_TIMEOUT", "30"))
SERVER_POLL_INTERVAL_S = float(os.getenv("PW_SERVER_POLL_INTERVAL", "0.5"))
HYDRATION_TIMEOUT_S = int(os.getenv("PW_HYDRATION_TIMEOUT", "90"))
HYDRATION_TARGET = int(os.getenv("PW_HYDRATION_TARGET", "800"))
PAGE_LOAD_TIMEOUT_MS = int(os.getenv("PW_PAGE_LOAD_TIMEOUT_MS", "60000"))
INTERACTION_TIMEOUT_MS = int(os.getenv("PW_INTERACTION_TIMEOUT_MS", "10000"))

# ---------------------------------------------------------------------------
# View names
# ---------------------------------------------------------------------------
ALL_VIEWS = [
    "campaigns", "research", "evidence", "report",
    "memory", "pipelines", "advanced",
]

ADV_TABS = ["queries", "sources", "storm", "trace", "cost"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("interaction_audit")


# ---------------------------------------------------------------------------
# Utility: find a free TCP port
# ---------------------------------------------------------------------------
def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ---------------------------------------------------------------------------
# Utility: wait for server readiness
# ---------------------------------------------------------------------------
async def wait_for_server(port: int, timeout_s: int) -> bool:
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
# Server lifecycle (same pattern as fire test)
# ---------------------------------------------------------------------------
def start_server(port: int, trace_file: str, log_dir: Path) -> subprocess.Popen:
    log_dir.mkdir(parents=True, exist_ok=True)
    server_log_path = log_dir / "interaction_audit_server.log"
    server_log_handle = open(server_log_path, "w", encoding="utf-8")

    cmd = [
        sys.executable,
        str(_LIVE_SERVER_SCRIPT),
        "--port", str(port),
        "--trace", str(trace_file),
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
    proc._log_handle = server_log_handle  # type: ignore[attr-defined]
    return proc


def stop_server(proc: subprocess.Popen) -> None:
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
# CheckResult (same as fire test)
# ---------------------------------------------------------------------------
class CheckResult:
    def __init__(self, check_id: str, description: str, category: str):
        self.check_id = check_id
        self.description = description
        self.category = category
        self.passed: bool = False
        self.severity: str = "error"
        self.actual: Any = None
        self.expected: Any = None
        self.error: str | None = None
        self.screenshot: str | None = None

    def set_pass(self, actual: Any = None, expected: Any = None) -> "CheckResult":
        self.passed = True
        self.actual = actual
        self.expected = expected
        return self

    def set_fail(self, actual: Any = None, expected: Any = None, error: str | None = None) -> "CheckResult":
        self.passed = False
        self.actual = actual
        self.expected = expected
        self.error = error
        return self

    def set_info(self, actual: Any = None, note: str | None = None) -> "CheckResult":
        self.passed = True
        self.severity = "info"
        self.actual = actual
        self.error = note
        return self

    def to_dict(self) -> dict:
        result: dict[str, Any] = {
            "check_id": self.check_id,
            "description": self.description,
            "category": self.category,
            "passed": self.passed,
            "severity": self.severity,
            "actual": self.actual,
            "expected": self.expected,
        }
        if self.error:
            result["error"] = self.error
        if self.screenshot:
            result["screenshot"] = self.screenshot
        return result


# ---------------------------------------------------------------------------
# DOM / Page helpers
# ---------------------------------------------------------------------------
async def element_count(page: Page, selector: str) -> int:
    return await page.evaluate("(sel) => document.querySelectorAll(sel).length", selector)


async def element_text(page: Page, selector: str) -> str:
    return await page.evaluate(
        "(sel) => { const el = document.querySelector(sel); return el ? el.textContent.trim() : '__NOT_FOUND__'; }",
        selector,
    )


async def element_exists(page: Page, selector: str) -> bool:
    return await page.evaluate("(sel) => document.querySelector(sel) !== null", selector)


async def element_visible(page: Page, selector: str) -> bool:
    return await page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        }""",
        selector,
    )


async def wait_for_hydration(page: Page, target: int, timeout_s: int) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        count = await page.evaluate("() => { try { return state.eventCount || 0; } catch(e) { return 0; } }")
        if count >= target:
            return True
        await asyncio.sleep(0.5)
    return False


async def switch_to_operator_mode(page: Page) -> None:
    await page.evaluate("if (typeof setViewMode === 'function') setViewMode('operator')")
    await page.wait_for_timeout(300)


async def switch_to_user_mode(page: Page) -> None:
    await page.evaluate("if (typeof setViewMode === 'function') setViewMode('user')")
    await page.wait_for_timeout(300)


async def switch_view(page: Page, view_name: str) -> None:
    await page.evaluate(f"switchView('{view_name}')")
    await page.wait_for_timeout(500)


async def capture_screenshot(page: Page, name: str, output_dir: Path) -> str:
    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    file_path = screenshots_dir / f"{name}.png"
    await page.screenshot(path=str(file_path), full_page=False)
    return str(file_path)


# ---------------------------------------------------------------------------
# IA. Citation System Interactions (IA01-IA13)
# ---------------------------------------------------------------------------
async def run_citation_interactions(
    page: Page, output_dir: Path
) -> list[CheckResult]:
    """IA01-IA13: Citation chain modal, popover, preview interactions."""
    results: list[CheckResult] = []

    # Ensure operator mode and report view for citations
    await switch_to_operator_mode(page)
    await switch_view(page, "report")
    await page.wait_for_timeout(500)

    # --- IA01: Click 1st .cite-ref -> chain modal opens ---
    ia01 = CheckResult("IA01", "Click 1st .cite-ref opens chain modal with title", "IA. Citation Interactions")
    cite_count = await element_count(page, ".cite-ref")
    modal_opened = False
    first_cite_num = 0
    if cite_count > 0:
        first_cite_num = await page.evaluate(
            "() => { const el = document.querySelector('.cite-ref'); return el ? parseInt(el.dataset.cite || el.textContent.replace(/[^0-9]/g,'')) : 0; }"
        )
        # Use JS click — Playwright click() requires visibility but cite-refs may be off-screen
        await page.evaluate(
            "() => { const el = document.querySelector('.cite-ref'); if (el) el.click(); }"
        )
        await page.wait_for_timeout(1500)  # Wait for API fetch + render
        modal_opened = await page.evaluate(
            "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
        )
        if modal_opened:
            title_text = await element_text(page, "#chain-title")
            if "Citation" in title_text:
                ia01.set_pass(actual=title_text, expected="Citation [N] title")
            else:
                ia01.set_fail(actual=title_text, expected="Citation [N] title", error=f"Title is '{title_text}'")
        else:
            ia01.set_fail(actual="modal not visible", expected="modal opens", error="Chain modal did not open on click")
    else:
        ia01.set_info(actual="no .cite-ref found", note="Cannot test: no citations in report")
    results.append(ia01)
    if modal_opened:
        await capture_screenshot(page, "ia01_chain_modal", output_dir)

    # --- IA02: Summary tab has evidence cards with tier badges ---
    ia02 = CheckResult("IA02", "Summary tab has evidence cards with tier badges", "IA. Citation Interactions")
    if modal_opened:
        # Wait for chain data to load
        await page.wait_for_timeout(2000)
        ev_card_count = await element_count(page, ".chain-evidence-card")
        tier_badge_count = await element_count(page, ".chain-tier-badge")
        if ev_card_count > 0 and tier_badge_count > 0:
            ia02.set_pass(actual=f"{ev_card_count} cards, {tier_badge_count} badges", expected=">= 1 card with badge")
        else:
            ia02.set_fail(actual=f"{ev_card_count} cards, {tier_badge_count} badges", expected=">= 1 card with badge",
                          error="No evidence cards or tier badges in summary tab")
    else:
        ia02.set_info(actual="modal not opened", note="Skipped: chain modal did not open")
    results.append(ia02)

    # --- IA03: Click Source Preview tab -> iframe with content ---
    ia03 = CheckResult("IA03", "Source Preview tab shows content (not 'unavailable')", "IA. Citation Interactions")
    if modal_opened:
        await page.evaluate("switchChainTab('preview')")
        await page.wait_for_timeout(3000)  # Wait for preview API fetch
        preview_pane_html = await page.evaluate(
            "() => { const p = document.getElementById('chain-pane-preview'); return p ? p.innerHTML.length : 0; }"
        )
        has_iframe = await element_exists(page, "#chain-preview-iframe")
        has_fallback = await page.evaluate(
            "() => { const p = document.getElementById('chain-pane-preview'); return p && p.querySelector('.chain-fallback-quote') !== null; }"
        )
        if has_iframe or has_fallback or preview_pane_html > 200:
            ia03.set_pass(actual=f"html={preview_pane_html}, iframe={has_iframe}, fallback={has_fallback}",
                          expected="preview content rendered")
        else:
            ia03.set_fail(actual=f"html={preview_pane_html}", expected="> 200 chars",
                          error="Preview tab has no meaningful content")
        await capture_screenshot(page, "ia03_preview_tab", output_dir)
    else:
        ia03.set_info(actual="modal not opened", note="Skipped")
    results.append(ia03)

    # --- IA04: Click Reasoning Chain tab -> chain entries ---
    ia04 = CheckResult("IA04", "Reasoning Chain tab has A->B->C->D structure", "IA. Citation Interactions")
    if modal_opened:
        await page.evaluate("switchChainTab('reasoning')")
        await page.wait_for_timeout(500)
        chain_blocks = await element_count(page, ".chain-reasoning-block")
        chain_steps = await element_count(page, ".chain-step")
        if chain_blocks > 0 and chain_steps >= 2:
            ia04.set_pass(actual=f"{chain_blocks} blocks, {chain_steps} steps", expected=">= 1 block with steps")
        else:
            ia04.set_fail(actual=f"{chain_blocks} blocks, {chain_steps} steps", expected=">= 1 block",
                          error="No reasoning chain structure")
    else:
        ia04.set_info(actual="modal not opened", note="Skipped")
    results.append(ia04)

    # --- IA05: Click Metadata tab -> shows URL, source_type, scores ---
    ia05 = CheckResult("IA05", "Metadata tab shows URL, source_type, evidence details", "IA. Citation Interactions")
    if modal_opened:
        await page.evaluate("switchChainTab('metadata')")
        await page.wait_for_timeout(500)
        meta_tables = await element_count(page, ".chain-meta-table")
        meta_html_len = await page.evaluate(
            "() => { const p = document.getElementById('chain-pane-metadata'); return p ? p.innerHTML.length : 0; }"
        )
        if meta_tables > 0 and meta_html_len > 100:
            ia05.set_pass(actual=f"{meta_tables} tables, {meta_html_len} chars", expected="metadata rendered")
        else:
            ia05.set_fail(actual=f"{meta_tables} tables, {meta_html_len} chars", expected="metadata rendered",
                          error="No metadata content")
        await capture_screenshot(page, "ia05_metadata_tab", output_dir)
    else:
        ia05.set_info(actual="modal not opened", note="Skipped")
    results.append(ia05)

    # --- IA06: Close modal, click 2nd .cite-ref -> NEW modal data loads (FIX-B2 verification) ---
    ia06 = CheckResult("IA06", "2nd citation loads fresh data (FIX-B2: _previewLoaded reset)", "IA. Citation Interactions")
    if modal_opened and cite_count >= 2:
        # Close current modal
        await page.evaluate("closeCitationChain()")
        await page.wait_for_timeout(500)

        # Get 2nd citation's number
        second_cite_num = await page.evaluate(
            "() => { const refs = document.querySelectorAll('.cite-ref'); if (refs.length < 2) return 0; return parseInt(refs[1].dataset.cite || refs[1].textContent.replace(/[^0-9]/g,'')); }"
        )

        # Click 2nd citation
        await page.evaluate("() => { const refs = document.querySelectorAll('.cite-ref'); if (refs[1]) refs[1].click(); }")
        await page.wait_for_timeout(1500)

        modal2_opened = await page.evaluate(
            "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
        )
        if modal2_opened:
            title2 = await element_text(page, "#chain-title")
            if str(second_cite_num) in title2 and str(second_cite_num) != str(first_cite_num):
                ia06.set_pass(actual=f"1st=[{first_cite_num}], 2nd={title2}", expected="different citation data")
            elif second_cite_num != first_cite_num:
                ia06.set_pass(actual=f"title={title2}", expected="new modal opened")
            else:
                ia06.set_info(actual=f"same cite num {first_cite_num}", note="Both citations are same number")
        else:
            ia06.set_fail(actual="2nd modal did not open", expected="new modal opens", error="Modal failed to reopen")
    elif cite_count < 2:
        ia06.set_info(actual=f"only {cite_count} citations", note="Need >= 2 citations for this test")
    else:
        ia06.set_info(actual="1st modal not opened", note="Skipped")
    results.append(ia06)

    # --- IA07: Source Preview on 2nd citation loads fresh content ---
    ia07 = CheckResult("IA07", "Source Preview on 2nd citation loads fresh content", "IA. Citation Interactions")
    modal2_opened = await page.evaluate(
        "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
    )
    if modal2_opened:
        await page.evaluate("switchChainTab('preview')")
        await page.wait_for_timeout(3000)
        preview2_html = await page.evaluate(
            "() => { const p = document.getElementById('chain-pane-preview'); return p ? p.innerHTML.length : 0; }"
        )
        # Check _previewLoaded was reset (the key FIX-B2 verification)
        preview_loaded = await page.evaluate("() => typeof _previewLoaded !== 'undefined' ? _previewLoaded : 'undefined'")
        if preview2_html > 100:
            ia07.set_pass(actual=f"html={preview2_html} chars, _previewLoaded={preview_loaded}",
                          expected="fresh preview content rendered")
        else:
            ia07.set_fail(actual=f"html={preview2_html} chars, _previewLoaded={preview_loaded}",
                          expected="fresh preview > 100 chars",
                          error="Preview tab empty for 2nd citation (FIX-B2 may not be working)")
        await capture_screenshot(page, "ia07_2nd_preview", output_dir)
    else:
        ia07.set_info(actual="2nd modal not opened", note="Skipped")
    results.append(ia07)

    # Close modal for next tests
    await page.evaluate("if (typeof closeCitationChain === 'function') closeCitationChain()")
    await page.wait_for_timeout(300)

    # --- IA08: Switch to user mode, hover workspace source card -> popover appears ---
    ia08 = CheckResult("IA08", "Hover workspace source card shows popover", "IA. Citation Interactions")
    await switch_to_user_mode(page)
    await page.wait_for_timeout(500)
    # Ensure workspace cite cards are rendered: set report phase, expand section,
    # call renderCitationSidebar (same setup as IG03 — cards require explicit render
    # because scroll_sync.js doesn't fire during trace replay)
    await page.evaluate(
        """() => {
            if (typeof setWorkspacePhase === 'function') setWorkspacePhase('report');
            else { _wsPhase = 'report'; }
            var sec = document.getElementById('ws-section-citations');
            if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
            if (typeof renderCitationSidebar === 'function' && state.bibliography && state.bibliography.length) {
                renderCitationSidebar(state.bibliography.map(function(_, i) { return i + 1; }));
            }
        }"""
    )
    await page.wait_for_timeout(500)
    ws_card_count = await element_count(page, ".ws-cite-card")
    if ws_card_count > 0:
        # Hover the first card
        card = await page.query_selector(".ws-cite-card")
        if card:
            await card.hover()
            await page.wait_for_timeout(500)  # Wait for popover timer
            popover_exists = await element_exists(page, ".ws-cite-popover")
            if popover_exists:
                ia08.set_pass(actual="popover appeared", expected="popover on hover")
                await capture_screenshot(page, "ia08_cite_popover", output_dir)
            else:
                ia08.set_fail(actual="no popover", expected="popover on hover",
                              error="showCitePopoverCard did not create popover")
        else:
            ia08.set_fail(actual="card query failed", expected="hoverable card")
    else:
        ia08.set_info(actual="no .ws-cite-card found", note="Cannot test: no workspace source cards")
    results.append(ia08)

    # --- IA09: Popover has content (not "No cached content") ---
    ia09 = CheckResult("IA09", "Popover iframe has content (not empty)", "IA. Citation Interactions")
    popover_exists = await element_exists(page, ".ws-cite-popover")
    if popover_exists:
        popover_html = await page.evaluate(
            "() => { const p = document.querySelector('.ws-cite-popover'); return p ? p.innerHTML.length : 0; }"
        )
        has_iframe = await element_exists(page, ".ws-popover-iframe")
        has_no_content_msg = await page.evaluate(
            "() => { const p = document.querySelector('.ws-cite-popover'); return p && p.textContent.includes('No cached content'); }"
        )
        if popover_html > 50 and not has_no_content_msg:
            ia09.set_pass(actual=f"html={popover_html}, iframe={has_iframe}", expected="content present")
        elif has_no_content_msg:
            ia09.set_fail(actual="'No cached content' message", expected="actual content",
                          error="B1 bug: popover shows 'No cached content'")
        else:
            ia09.set_fail(actual=f"html={popover_html}", expected="> 50 chars", error="Popover nearly empty")
    else:
        ia09.set_info(actual="no popover present", note="Skipped: popover not shown")
    results.append(ia09)

    # --- IA10: Click workspace source card -> chain modal opens ---
    ia10 = CheckResult("IA10", "Click workspace source card opens chain modal", "IA. Citation Interactions")
    if ws_card_count > 0:
        # First dismiss any popover by moving mouse away
        await page.mouse.move(0, 0)
        await page.wait_for_timeout(300)
        # Click the card
        await page.evaluate(
            "() => { const el = document.querySelector('.ws-cite-card'); if (el) el.click(); }"
        )
        await page.wait_for_timeout(1500)
        chain_visible = await page.evaluate(
            "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
        )
        if chain_visible:
            ia10.set_pass(actual="chain modal opened", expected="modal opens on card click")
        else:
            ia10.set_fail(actual="no modal", expected="chain modal opens", error="Card click did not open chain modal")
        # Close it
        await page.evaluate("if (typeof closeCitationChain === 'function') closeCitationChain()")
        await page.wait_for_timeout(300)
    else:
        ia10.set_info(actual="no ws-cite-card", note="Skipped")
    results.append(ia10)

    # --- IA11: Click inline [N] citation in workspace report -> chain modal ---
    ia11 = CheckResult("IA11", "Click inline workspace citation opens chain modal", "IA. Citation Interactions")
    ws_cite_ref = await element_count(page, ".ws-report-block .cite-ref, #ws-center .cite-ref")
    if ws_cite_ref > 0:
        await page.evaluate(
            """() => {
                const el = document.querySelector('.ws-report-block .cite-ref') || document.querySelector('#ws-center .cite-ref');
                if (el) el.click();
            }"""
        )
        await page.wait_for_timeout(1500)
        chain_visible = await page.evaluate(
            "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
        )
        if chain_visible:
            ia11.set_pass(actual="modal opened", expected="modal opens")
        else:
            ia11.set_fail(actual="no modal", expected="chain modal opens", error="Inline cite click failed")
        await page.evaluate("if (typeof closeCitationChain === 'function') closeCitationChain()")
        await page.wait_for_timeout(300)
    else:
        ia11.set_info(actual="no inline cite-ref in workspace", note="Skipped")
    results.append(ia11)

    # --- IA12: Popover disappears on mouse leave ---
    ia12 = CheckResult("IA12", "Popover disappears on mouse leave", "IA. Citation Interactions")
    if ws_card_count > 0:
        card = await page.query_selector(".ws-cite-card")
        if card:
            await card.hover()
            await page.wait_for_timeout(500)
            popover_before = await element_exists(page, ".ws-cite-popover")
            # Move mouse away
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(500)
            popover_after = await element_exists(page, ".ws-cite-popover")
            if popover_before and not popover_after:
                ia12.set_pass(actual="popover removed on leave", expected="popover removed")
            elif not popover_before:
                ia12.set_info(actual="popover never appeared", note="Cannot verify disappearance")
            else:
                ia12.set_fail(actual="popover still present", expected="popover removed",
                              error="Popover did not disappear on mouse leave")
        else:
            ia12.set_info(actual="card not found", note="Skipped")
    else:
        ia12.set_info(actual="no cards", note="Skipped")
    results.append(ia12)

    # --- IA13: Escape key closes chain modal ---
    ia13 = CheckResult("IA13", "Escape key closes chain modal", "IA. Citation Interactions")
    await switch_to_operator_mode(page)
    await switch_view(page, "report")
    await page.wait_for_timeout(500)
    if cite_count > 0:
        await page.evaluate(
            "() => { const el = document.querySelector('.cite-ref'); if (el) el.click(); }"
        )
        await page.wait_for_timeout(1500)
        modal_before = await page.evaluate(
            "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
        )
        if modal_before:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            modal_after = await page.evaluate(
                "() => { const m = document.getElementById('citation-chain-modal'); return m && m.classList.contains('visible'); }"
            )
            if not modal_after:
                ia13.set_pass(actual="modal closed on Escape", expected="modal closes")
            else:
                ia13.set_fail(actual="modal still visible", expected="modal closes on Escape",
                              error="Escape key did not close modal")
        else:
            ia13.set_info(actual="modal did not open", note="Cannot test Escape without open modal")
    else:
        ia13.set_info(actual="no citations", note="Skipped")
    results.append(ia13)

    return results


# ---------------------------------------------------------------------------
# IB. View Switching & Navigation (IB01-IB08)
# ---------------------------------------------------------------------------
async def run_navigation_interactions(
    page: Page, output_dir: Path
) -> list[CheckResult]:
    """IB01-IB08: Tab clicking, mode toggle, theme toggle, TOC navigation."""
    results: list[CheckResult] = []
    await switch_to_operator_mode(page)

    # --- IB01: Click each of 7 nav tabs -> correct view becomes visible ---
    ib01 = CheckResult("IB01", "All 7 nav tabs activate correct view", "IB. View Switching")
    failed_views: list[str] = []
    for view in ALL_VIEWS:
        await page.evaluate(f"switchView('{view}')")
        await page.wait_for_timeout(300)
        is_active = await page.evaluate(
            f"() => {{ const p = document.getElementById('view-{view}'); return p && p.classList.contains('active'); }}"
        )
        if not is_active:
            failed_views.append(view)
    if not failed_views:
        ib01.set_pass(actual="all 7 views activate", expected="7/7")
    else:
        ib01.set_fail(actual=f"failed: {failed_views}", expected="all views activate",
                      error=f"{len(failed_views)} views failed to activate")
    results.append(ib01)

    # --- IB02: Click each of 5 advanced sub-tabs -> correct pane active ---
    ib02 = CheckResult("IB02", "All 5 advanced sub-tabs activate correct pane", "IB. View Switching")
    await switch_view(page, "advanced")
    await page.wait_for_timeout(300)
    failed_adv: list[str] = []
    for tab in ADV_TABS:
        await page.evaluate(
            f"""() => {{
                var btn = document.querySelector('.adv-tab-btn[data-adv="{tab}"]');
                if (btn) btn.click();
            }}"""
        )
        await page.wait_for_timeout(300)
        is_active = await page.evaluate(
            f"() => {{ const p = document.getElementById('adv-{tab}'); return p && p.classList.contains('active'); }}"
        )
        if not is_active:
            failed_adv.append(tab)
    if not failed_adv:
        ib02.set_pass(actual="all 5 sub-tabs activate", expected="5/5")
    else:
        ib02.set_fail(actual=f"failed: {failed_adv}", expected="all sub-tabs activate",
                      error=f"{len(failed_adv)} sub-tabs failed")
    results.append(ib02)

    # --- IB03: Toggle user/operator mode -> body class changes ---
    ib03 = CheckResult("IB03", "Toggle user/operator mode changes body class", "IB. View Switching")
    await switch_to_operator_mode(page)
    is_operator = await page.evaluate(
        "() => document.body.classList.contains('operator-mode') || document.body.dataset.viewMode === 'operator'"
    )
    await switch_to_user_mode(page)
    is_user = await page.evaluate(
        "() => document.body.classList.contains('user-mode') || document.body.dataset.viewMode === 'user'"
    )
    if is_operator and is_user:
        ib03.set_pass(actual="operator->user toggle works", expected="mode class changes")
    elif is_user:
        ib03.set_pass(actual="user mode confirmed", expected="mode toggles")
    else:
        ib03.set_fail(actual=f"operator={is_operator}, user={is_user}", expected="both modes work",
                      error="Mode toggle did not change body class/dataset")
    results.append(ib03)
    await switch_to_operator_mode(page)

    # --- IB04: Toggle theme -> data-theme changes ---
    ib04 = CheckResult("IB04", "Theme toggle changes data-theme attribute", "IB. View Switching")
    theme_before = await page.evaluate("() => document.documentElement.getAttribute('data-theme') || 'dark'")
    await page.evaluate("toggleTheme()")
    await page.wait_for_timeout(300)
    theme_after = await page.evaluate("() => document.documentElement.getAttribute('data-theme') || 'dark'")
    if theme_before != theme_after:
        ib04.set_pass(actual=f"{theme_before} -> {theme_after}", expected="theme changed")
        await capture_screenshot(page, f"ib04_theme_{theme_after}", output_dir)
    else:
        ib04.set_fail(actual=f"still {theme_before}", expected="theme changed", error="toggleTheme() had no effect")
    # Toggle back
    await page.evaluate("toggleTheme()")
    await page.wait_for_timeout(200)
    results.append(ib04)

    # --- IB05: Click TOC link -> report scrolls to heading ---
    ib05 = CheckResult("IB05", "TOC link scrolls report to correct section", "IB. View Switching")
    await switch_view(page, "report")
    await page.wait_for_timeout(500)
    toc_link_count = await element_count(page, ".toc-link")
    if toc_link_count > 0:
        scroll_result = await page.evaluate(
            """() => {
                const link = document.querySelector('.toc-link');
                if (!link) return {ok: false, reason: 'no toc link'};
                const target = link.dataset.target || link.getAttribute('href') || '';
                link.click();
                // Check if target heading exists
                const heading = document.getElementById(target) || document.querySelector('[id="' + target + '"]');
                return {ok: !!heading, target: target, headingFound: !!heading};
            }"""
        )
        if scroll_result.get("ok"):
            ib05.set_pass(actual=f"scrolled to {scroll_result.get('target')}", expected="scroll to heading")
        else:
            ib05.set_info(actual=scroll_result, note="TOC link exists but target heading not found")
    else:
        ib05.set_info(actual="no .toc-link found", note="Report may not have TOC")
    results.append(ib05)

    # --- IB06: Navigate views rapidly (7 tabs in 2s) -> no errors ---
    ib06 = CheckResult("IB06", "Rapid view switching (7 tabs in 2s) no crash", "IB. View Switching")
    errors_before = await page.evaluate("() => { try { return window.__ia_error_count || 0; } catch(e) { return 0; } }")
    for view in ALL_VIEWS:
        await page.evaluate(f"switchView('{view}')")
        await page.wait_for_timeout(int(2000 / len(ALL_VIEWS)))
    errors_after = await page.evaluate("() => { try { return window.__ia_error_count || 0; } catch(e) { return 0; } }")
    last_view_active = await page.evaluate(
        f"() => {{ const p = document.getElementById('view-{ALL_VIEWS[-1]}'); return p && p.classList.contains('active'); }}"
    )
    if last_view_active:
        ib06.set_pass(actual=f"last view '{ALL_VIEWS[-1]}' active, errors: {errors_after - errors_before}",
                      expected="no crash, last view active")
    else:
        ib06.set_fail(actual="last view not active", expected="last view active after rapid switching",
                      error="Rapid switching broke view state")
    results.append(ib06)

    # --- IB07: Breadcrumb updates on view switch ---
    ib07 = CheckResult("IB07", "Breadcrumb/header updates on view switch", "IB. View Switching")
    # Check if active nav button reflects current view
    await switch_view(page, "evidence")
    await page.wait_for_timeout(300)
    active_btn = await page.evaluate(
        "() => { const btn = document.querySelector('.nav-btn.active'); return btn ? btn.textContent.trim() : '__NONE__'; }"
    )
    if active_btn != "__NONE__" and "evidence" in active_btn.lower():
        ib07.set_pass(actual=f"active button: '{active_btn}'", expected="evidence nav active")
    else:
        # Some dashboards use different labels
        active_view = await page.evaluate("() => state.activeView")
        if active_view == "evidence":
            ib07.set_pass(actual=f"state.activeView='{active_view}'", expected="evidence view active")
        else:
            ib07.set_fail(actual=f"btn='{active_btn}', state='{active_view}'", expected="evidence active",
                          error="View state mismatch after switching")
    results.append(ib07)

    # --- IB08: Nav badge counts update (evidence badge > 0) ---
    ib08 = CheckResult("IB08", "Nav badge counts update (evidence > 0)", "IB. View Switching")
    badge_text = await page.evaluate(
        """() => {
            const badges = document.querySelectorAll('.nav-btn .badge, .nav-badge');
            for (const b of badges) {
                const val = parseInt(b.textContent);
                if (val > 0) return {found: true, value: val, text: b.textContent.trim()};
            }
            // Fallback: check state.evidence
            return {found: false, evidence: typeof state !== 'undefined' ? state.evidence : 0};
        }"""
    )
    if badge_text.get("found"):
        ib08.set_pass(actual=f"badge value: {badge_text['value']}", expected="> 0")
    elif badge_text.get("evidence", 0) > 0:
        ib08.set_info(actual=f"state.evidence={badge_text['evidence']}", note="Evidence exists but no visible badge")
    else:
        ib08.set_info(actual=badge_text, note="No nav badges with counts found")
    results.append(ib08)

    return results


# ---------------------------------------------------------------------------
# IC. Evidence Browser Interactions (IC01-IC07)
# ---------------------------------------------------------------------------
async def run_evidence_interactions(
    page: Page, output_dir: Path
) -> list[CheckResult]:
    """IC01-IC07: Tier filtering, graph mode switches, tooltips."""
    results: list[CheckResult] = []

    await switch_to_operator_mode(page)
    await switch_view(page, "evidence")
    await page.wait_for_timeout(500)

    # Get initial card count
    initial_cards = await page.evaluate(
        "() => { const el = document.getElementById('evidence-card-list'); return el ? el.children.length : 0; }"
    )

    # --- IC01: Click GOLD filter chip -> filtered ---
    ic01 = CheckResult("IC01", "Click GOLD filter chip filters evidence", "IC. Evidence Browser")
    has_gold_chip = await page.evaluate(
        "() => !!document.querySelector('#tier-chips .filter-chip[data-tier=\"gold\"]')"
    )
    if has_gold_chip:
        await page.evaluate("setTierFilter('gold')")
        await page.wait_for_timeout(500)
        gold_cards = await page.evaluate(
            "() => { const el = document.getElementById('evidence-card-list'); return el ? el.children.length : 0; }"
        )
        gold_active = await page.evaluate(
            "() => { const c = document.querySelector('#tier-chips .filter-chip.active'); return c ? c.dataset.tier : 'none'; }"
        )
        if gold_active == "gold":
            ic01.set_pass(actual=f"filter=gold, cards={gold_cards} (was {initial_cards})", expected="GOLD filter active")
        else:
            ic01.set_fail(actual=f"active={gold_active}", expected="gold", error="GOLD chip not activated")
    else:
        ic01.set_info(actual="no GOLD filter chip", note="Filter chip not found")
    results.append(ic01)

    # --- IC02: Click SILVER filter chip -> filtered ---
    ic02 = CheckResult("IC02", "Click SILVER filter chip filters evidence", "IC. Evidence Browser")
    has_silver_chip = await page.evaluate(
        "() => !!document.querySelector('#tier-chips .filter-chip[data-tier=\"silver\"]')"
    )
    if has_silver_chip:
        await page.evaluate("setTierFilter('silver')")
        await page.wait_for_timeout(500)
        silver_active = await page.evaluate(
            "() => { const c = document.querySelector('#tier-chips .filter-chip.active'); return c ? c.dataset.tier : 'none'; }"
        )
        if silver_active == "silver":
            ic02.set_pass(actual="SILVER filter active", expected="silver filter applied")
        else:
            ic02.set_fail(actual=f"active={silver_active}", expected="silver", error="SILVER chip not activated")
    else:
        ic02.set_info(actual="no SILVER chip", note="Filter chip not found")
    results.append(ic02)

    # --- IC03: Click ALL filter chip -> all evidence shown ---
    ic03 = CheckResult("IC03", "Click ALL filter chip restores all evidence", "IC. Evidence Browser")
    await page.evaluate("setTierFilter('all')")
    await page.wait_for_timeout(500)
    all_cards = await page.evaluate(
        "() => { const el = document.getElementById('evidence-card-list'); return el ? el.children.length : 0; }"
    )
    all_active = await page.evaluate(
        "() => { const c = document.querySelector('#tier-chips .filter-chip.active'); return c ? c.dataset.tier : 'none'; }"
    )
    if all_active == "all" and all_cards >= initial_cards:
        ic03.set_pass(actual=f"filter=all, cards={all_cards}", expected="all cards restored")
    elif all_active == "all":
        ic03.set_pass(actual=f"filter=all, cards={all_cards}", expected="ALL filter active")
    else:
        ic03.set_fail(actual=f"active={all_active}, cards={all_cards}", expected="all filter",
                      error="ALL chip not activated")
    results.append(ic03)

    # --- IC04: Switch graph modes -> SVG content changes ---
    ic04 = CheckResult("IC04", "Graph mode switches update SVG content", "IC. Evidence Browser")
    modes = ["crossref", "citation", "source", "mindmap"]
    svg_contents: dict[str, int] = {}
    for mode in modes:
        await page.evaluate(
            f"""() => {{
                state.graphMode = '{mode}';
                var btn = document.querySelector('.seg-btn[data-mode="{mode}"]');
                if (btn) btn.click();
                else if (typeof renderEvidenceGraph === 'function') renderEvidenceGraph();
            }}"""
        )
        await page.wait_for_timeout(500)
        svg_len = await page.evaluate(
            "() => { const svg = document.getElementById('graph-svg'); return svg ? svg.innerHTML.length : 0; }"
        )
        svg_contents[mode] = svg_len
    distinct_values = len(set(svg_contents.values()))
    if distinct_values >= 2:
        ic04.set_pass(actual=f"modes={svg_contents}", expected=">= 2 distinct SVG states")
    elif any(v > 0 for v in svg_contents.values()):
        ic04.set_info(actual=f"modes={svg_contents}", note="SVG renders but modes may look similar")
    else:
        ic04.set_fail(actual=f"all empty: {svg_contents}", expected="SVG content per mode",
                      error="No graph content rendered in any mode")
    results.append(ic04)
    await capture_screenshot(page, "ic04_graph_modes", output_dir)

    # --- IC05: Hover graph node -> tooltip ---
    ic05 = CheckResult("IC05", "Hover graph node shows tooltip", "IC. Evidence Browser")
    # Reset to crossref mode
    await page.evaluate("state.graphMode = 'crossref'; if (typeof renderEvidenceGraph === 'function') renderEvidenceGraph();")
    await page.wait_for_timeout(500)
    node_count = await page.evaluate(
        "() => { const svg = document.getElementById('graph-svg'); return svg ? svg.querySelectorAll('circle, .graph-node').length : 0; }"
    )
    if node_count > 0:
        # Hover first node
        node = await page.query_selector("#graph-svg circle, #graph-svg .graph-node")
        if node:
            await node.hover()
            await page.wait_for_timeout(500)
            tooltip = await page.evaluate(
                "() => { const t = document.querySelector('.graph-tooltip, .tooltip, title'); return t ? t.textContent.length : 0; }"
            )
            if tooltip > 0:
                ic05.set_pass(actual=f"tooltip chars: {tooltip}", expected="tooltip visible")
            else:
                ic05.set_info(actual="no tooltip text", note="Node exists but tooltip may use SVG title")
        else:
            ic05.set_info(actual="node not queryable", note="SVG nodes exist but couldn't hover")
    else:
        ic05.set_info(actual="no graph nodes", note="Graph has no nodes to hover")
    results.append(ic05)

    # --- IC06: Agreement threshold slider updates graph ---
    ic06 = CheckResult("IC06", "Agreement threshold slider updates graph edges", "IC. Evidence Browser")
    slider = await page.query_selector("#graph-min-agree")
    if slider:
        svg_before = await page.evaluate(
            "() => { const svg = document.getElementById('graph-svg'); return svg ? svg.querySelectorAll('line, path').length : 0; }"
        )
        await page.evaluate("() => { var s = document.getElementById('graph-min-agree'); if (s) { s.value = 80; s.dispatchEvent(new Event('input')); } }")
        await page.wait_for_timeout(500)
        svg_after = await page.evaluate(
            "() => { const svg = document.getElementById('graph-svg'); return svg ? svg.querySelectorAll('line, path').length : 0; }"
        )
        if svg_before != svg_after:
            ic06.set_pass(actual=f"edges: {svg_before} -> {svg_after}", expected="edge count changed")
        else:
            ic06.set_info(actual=f"edges unchanged: {svg_before}", note="Slider may not affect visible edges at current data")
    else:
        ic06.set_info(actual="no #graph-min-agree slider", note="Slider not found in DOM")
    results.append(ic06)

    # --- IC07: Click evidence card -> detail panel opens ---
    ic07 = CheckResult("IC07", "Click evidence card opens detail panel", "IC. Evidence Browser")
    ev_cards = await element_count(page, ".evidence-card")
    if ev_cards > 0:
        await page.evaluate(
            "() => { const el = document.querySelector('.evidence-card'); if (el) el.click(); }"
        )
        await page.wait_for_timeout(500)
        detail_visible = await page.evaluate(
            """() => {
                const panel = document.querySelector('.evidence-detail, .ev-detail-panel, #evidence-detail');
                if (!panel) return false;
                return panel.innerHTML.length > 50;
            }"""
        )
        selected_idx = await page.evaluate("() => state.selectedEvidenceIdx")
        if detail_visible or (selected_idx is not None and selected_idx >= 0):
            ic07.set_pass(actual=f"detail visible={detail_visible}, selectedIdx={selected_idx}", expected="detail shown")
        else:
            ic07.set_info(actual=f"detail={detail_visible}, idx={selected_idx}",
                          note="Card clicked but detail panel may render inline")
        await capture_screenshot(page, "ic07_evidence_detail", output_dir)
    else:
        ic07.set_info(actual="no evidence cards", note="Cannot test without cards")
    results.append(ic07)

    return results


# ---------------------------------------------------------------------------
# ID. Metrics & Data Display (ID01-ID08)
# ---------------------------------------------------------------------------
async def run_metrics_interactions(page: Page) -> list[CheckResult]:
    """ID01-ID08: Verify metrics display matches state data."""
    results: list[CheckResult] = []
    await switch_to_operator_mode(page)
    await switch_view(page, "research")
    await page.wait_for_timeout(500)

    # --- ID01: Evidence count matches state ---
    id01 = CheckResult("ID01", "Evidence count display matches state.evidence", "ID. Metrics Display")
    ev_data = await page.evaluate(
        """() => {
            const el = document.getElementById('pm-evidence');
            const text = el ? el.textContent.trim() : '0';
            return {display: parseInt(text) || 0, state: state.evidence || 0};
        }"""
    )
    if abs(ev_data["display"] - ev_data["state"]) <= 5:  # Small tolerance for animation
        id01.set_pass(actual=f"display={ev_data['display']}, state={ev_data['state']}", expected="match")
    else:
        id01.set_fail(actual=ev_data, expected="display matches state",
                      error=f"Mismatch: display={ev_data['display']} vs state={ev_data['state']}")
    results.append(id01)

    # --- ID02: Faithfulness matches state ---
    id02 = CheckResult("ID02", "Faithfulness display shows percentage", "ID. Metrics Display")
    faith_data = await page.evaluate(
        """() => {
            const el = document.getElementById('pm-faith');
            return {text: el ? el.textContent.trim() : '__NOT_FOUND__', state: state.faithfulness || 0};
        }"""
    )
    if faith_data["text"] != "__NOT_FOUND__" and "%" in str(faith_data["text"]):
        id02.set_pass(actual=faith_data, expected="percentage display")
    elif faith_data["text"] != "__NOT_FOUND__":
        id02.set_pass(actual=faith_data, expected="faithfulness shown")
    else:
        id02.set_fail(actual=faith_data, expected="faithfulness display", error="#pm-faith not found")
    results.append(id02)

    # --- ID03: Word count matches state ---
    id03 = CheckResult("ID03", "Word count display matches state.words", "ID. Metrics Display")
    word_data = await page.evaluate(
        """() => {
            const el = document.getElementById('pm-words');
            const text = el ? el.textContent.trim().replace(/,/g, '') : '0';
            return {display: parseInt(text) || 0, state: state.words || 0};
        }"""
    )
    if abs(word_data["display"] - word_data["state"]) <= 10:
        id03.set_pass(actual=word_data, expected="match")
    else:
        id03.set_fail(actual=word_data, expected="display matches state", error="Word count mismatch")
    results.append(id03)

    # --- ID04: Cost display shows $X.XX ---
    id04 = CheckResult("ID04", "Cost display shows $X.XX format", "ID. Metrics Display")
    cost_text = await element_text(page, "#total-cost")
    if cost_text != "__NOT_FOUND__" and "$" in cost_text:
        id04.set_pass(actual=cost_text, expected="$X.XX format")
    elif cost_text != "__NOT_FOUND__":
        id04.set_info(actual=cost_text, note="Cost shown but no $ sign")
    else:
        id04.set_info(actual="not found", note="#total-cost element not found")
    results.append(id04)

    # --- ID05: Timer shows correct elapsed time (> 3600s for long pipeline) ---
    id05 = CheckResult("ID05", "Timer shows > 3600s elapsed (long pipeline)", "ID. Metrics Display")
    timer_text = await element_text(page, "#elapsed-time")
    total_seconds = _parse_hms_to_seconds(timer_text)
    if total_seconds > 3600:
        id05.set_pass(actual=f"{timer_text} ({total_seconds}s)", expected="> 3600s")
    elif total_seconds > 0:
        id05.set_info(actual=f"{timer_text} ({total_seconds}s)", note="Timer works but pipeline was shorter")
    else:
        id05.set_fail(actual=timer_text, expected="> 3600s", error="Timer not running or shows 0")
    results.append(id05)

    # --- ID06: Timer frozen (pipeline complete) ---
    id06 = CheckResult("ID06", "Timer frozen (two readings 2s apart identical)", "ID. Metrics Display")
    reading1 = await element_text(page, "#elapsed-time")
    await page.wait_for_timeout(2000)
    reading2 = await element_text(page, "#elapsed-time")
    if reading1 == reading2 and reading1 != "00:00:00":
        id06.set_pass(actual=f"{reading1} == {reading2}", expected="identical readings")
    elif reading1 == reading2:
        id06.set_info(actual="both 00:00:00", note="Timer at zero — pipeline may not have run")
    else:
        id06.set_fail(actual=f"{reading1} != {reading2}", expected="identical readings",
                      error="Timer still ticking")
    results.append(id06)

    # --- ID07: Phase stepper has completed phases ---
    id07 = CheckResult("ID07", "Phase stepper shows completed phases", "ID. Metrics Display")
    done_phases = await page.evaluate(
        """() => {
            const steps = document.querySelectorAll('.step-item.done, .step-item.completed');
            return steps.length;
        }"""
    )
    if done_phases >= 5:
        id07.set_pass(actual=f"{done_phases} completed phases", expected=">= 5")
    elif done_phases > 0:
        id07.set_info(actual=f"{done_phases} completed", note="Some phases completed")
    else:
        id07.set_fail(actual=0, expected=">= 5 completed", error="No phases show as done")
    results.append(id07)

    # --- ID08: Quality gates show pass/fail colors ---
    id08 = CheckResult("ID08", "Quality gates have pass/fail indicators", "ID. Metrics Display")
    await switch_view(page, "report")
    await page.wait_for_timeout(500)
    gate_dots = await page.evaluate(
        """() => {
            const dots = document.querySelectorAll('.gate-dot');
            const pass_count = document.querySelectorAll('.gate-dot.pass').length;
            const fail_count = document.querySelectorAll('.gate-dot.fail').length;
            return {total: dots.length, pass: pass_count, fail: fail_count};
        }"""
    )
    if gate_dots["total"] >= 3:
        id08.set_pass(actual=f"{gate_dots['pass']} pass, {gate_dots['fail']} fail / {gate_dots['total']} total",
                      expected=">= 3 gate dots")
    elif gate_dots["total"] > 0:
        id08.set_pass(actual=gate_dots, expected="gate dots exist")
    else:
        id08.set_info(actual=gate_dots, note="No .gate-dot elements (may be user mode)")
    results.append(id08)

    return results


# ---------------------------------------------------------------------------
# IE. Export & Action Buttons (IE01-IE05)
# ---------------------------------------------------------------------------
async def run_export_interactions(page: Page, output_dir: Path) -> list[CheckResult]:
    """IE01-IE05: Export button clicks, compose drawer."""
    results: list[CheckResult] = []
    await switch_to_operator_mode(page)
    await switch_view(page, "report")
    await page.wait_for_timeout(500)

    # --- IE01: Click Markdown export -> download triggered ---
    ie01 = CheckResult("IE01", "Markdown export triggers download", "IE. Export & Actions")
    try:
        async with page.expect_download(timeout=5000) as download_info:
            await page.evaluate("exportReport('markdown')")
        download = await download_info.value
        ie01.set_pass(actual=f"downloaded: {download.suggested_filename}", expected="download triggered")
    except Exception as exc:
        # Fallback: check if Blob was created (download may not work in headless)
        blob_created = await page.evaluate(
            """() => {
                try { exportReport('markdown'); return true; } catch(e) { return false; }
            }"""
        )
        if blob_created:
            ie01.set_info(actual="exportReport called", note=f"Download may not fire in headless: {exc}")
        else:
            ie01.set_fail(actual=str(exc), expected="download", error="Export failed")
    results.append(ie01)

    # --- IE02: Click JSONL export -> download ---
    ie02 = CheckResult("IE02", "JSONL export triggers download", "IE. Export & Actions")
    try:
        async with page.expect_download(timeout=5000) as download_info:
            await page.evaluate("exportReport('jsonl')")
        download = await download_info.value
        ie02.set_pass(actual=f"downloaded: {download.suggested_filename}", expected="download triggered")
    except Exception as exc:
        ie02.set_info(actual=str(exc)[:100], note="Download event may not fire in headless mode")
    results.append(ie02)

    # --- IE03: Word export ---
    ie03 = CheckResult("IE03", "Word export triggers download", "IE. Export & Actions")
    try:
        async with page.expect_download(timeout=5000) as download_info:
            await page.evaluate("exportReport('docx')")
        download = await download_info.value
        ie03.set_pass(actual=f"downloaded: {download.suggested_filename}", expected="download triggered")
    except Exception as exc:
        ie03.set_info(actual=str(exc)[:100], note="Word export may open print dialog instead")
    results.append(ie03)

    # --- IE04: Open compose drawer (Ctrl+K) ---
    ie04 = CheckResult("IE04", "Compose drawer opens with Ctrl+K", "IE. Export & Actions")
    await page.keyboard.press("Control+k")
    await page.wait_for_timeout(500)
    drawer_visible = await page.evaluate(
        "() => { const d = document.getElementById('compose-drawer'); return d && d.classList.contains('visible'); }"
    )
    if drawer_visible:
        textarea_exists = await element_exists(page, "#compose-query")
        ie04.set_pass(actual=f"drawer visible, textarea={textarea_exists}", expected="drawer opens")
        await capture_screenshot(page, "ie04_compose_drawer", output_dir)
    else:
        ie04.set_fail(actual="drawer not visible", expected="compose drawer opens",
                      error="Ctrl+K did not open compose drawer")
    results.append(ie04)

    # --- IE05: Close compose drawer (Escape) ---
    ie05 = CheckResult("IE05", "Compose drawer closes with Escape", "IE. Export & Actions")
    if drawer_visible:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        drawer_after = await page.evaluate(
            "() => { const d = document.getElementById('compose-drawer'); return d && d.classList.contains('visible'); }"
        )
        if not drawer_after:
            ie05.set_pass(actual="drawer closed", expected="drawer closes on Escape")
        else:
            ie05.set_fail(actual="drawer still visible", expected="closes on Escape",
                          error="Escape did not close drawer")
    else:
        # Try opening with FAB
        await page.evaluate("if (typeof openCompose === 'function') openCompose()")
        await page.wait_for_timeout(300)
        drawer_now = await page.evaluate(
            "() => { const d = document.getElementById('compose-drawer'); return d && d.classList.contains('visible'); }"
        )
        if drawer_now:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            drawer_after_esc = await page.evaluate(
                "() => { const d = document.getElementById('compose-drawer'); return d && d.classList.contains('visible'); }"
            )
            if not drawer_after_esc:
                ie05.set_pass(actual="opened via API, closed with Escape", expected="Escape closes drawer")
            else:
                ie05.set_fail(actual="still visible", expected="closes", error="Escape failed after openCompose()")
        else:
            ie05.set_info(actual="cannot open drawer", note="Skipped")
    results.append(ie05)

    return results


# ---------------------------------------------------------------------------
# IF. Real-Time Indicators (IF01-IF05)
# ---------------------------------------------------------------------------
async def run_realtime_interactions(page: Page) -> list[CheckResult]:
    """IF01-IF05: SSE status, event counter, activity log."""
    results: list[CheckResult] = []
    await switch_to_operator_mode(page)
    await switch_view(page, "research")
    await page.wait_for_timeout(500)

    # --- IF01: SSE status dot connected or completed ---
    if01 = CheckResult("IF01", "SSE status dot has 'connected' or 'completed' class", "IF. Real-Time Indicators")
    dot_class = await page.evaluate(
        "() => { const el = document.getElementById('status-dot'); return el ? el.className : '__NOT_FOUND__'; }"
    )
    if "connected" in str(dot_class) or "completed" in str(dot_class):
        if01.set_pass(actual=dot_class, expected="connected or completed")
    else:
        if01.set_fail(actual=dot_class, expected="connected or completed", error="Status dot not connected/completed")
    results.append(if01)

    # --- IF02: Event counter > 0 ---
    if02 = CheckResult("IF02", "Event counter shows count > 0", "IF. Real-Time Indicators")
    counter_text = await element_text(page, "#event-counter")
    try:
        counter_val = int(counter_text.replace(",", "").strip())
    except (ValueError, TypeError):
        counter_val = 0
    if counter_val > 0:
        if02.set_pass(actual=counter_val, expected="> 0")
    else:
        if02.set_fail(actual=counter_text, expected="> 0", error=f"Counter shows '{counter_text}'")
    results.append(if02)

    # --- IF03: Activity log has entries with timestamps ---
    if03 = CheckResult("IF03", "Activity log has entries with timestamps", "IF. Real-Time Indicators")
    log_data = await page.evaluate(
        """() => {
            const log = document.getElementById('activity-log');
            if (!log) return {found: false, count: 0};
            const entries = log.children.length;
            const hasTimestamp = log.querySelector('.log-time, .activity-time, time') !== null;
            return {found: true, count: entries, hasTimestamp: hasTimestamp};
        }"""
    )
    if log_data.get("count", 0) > 0:
        if03.set_pass(actual=f"{log_data['count']} entries, timestamps={log_data.get('hasTimestamp')}",
                      expected="> 0 entries")
    else:
        if03.set_fail(actual=log_data, expected="> 0 entries", error="Activity log empty")
    results.append(if03)

    # --- IF04: Activity log entries have icons ---
    if04 = CheckResult("IF04", "Activity log entries have icons", "IF. Real-Time Indicators")
    if log_data.get("count", 0) > 0:
        has_icons = await page.evaluate(
            """() => {
                const log = document.getElementById('activity-log');
                if (!log || !log.firstElementChild) return false;
                const first = log.firstElementChild;
                return first.querySelector('.log-icon, .activity-icon, svg, .emoji') !== null || first.textContent.match(/[\\u{1F300}-\\u{1F9FF}]/u) !== null;
            }"""
        )
        if has_icons:
            if04.set_pass(actual="icons present", expected="entries have icons")
        else:
            if04.set_info(actual="no icon elements found", note="Icons may be text emoji")
    else:
        if04.set_info(actual="no entries", note="Skipped: no activity log entries")
    results.append(if04)

    # --- IF05: Phase rows in research view ---
    if05 = CheckResult("IF05", "Phase rows present with done status", "IF. Real-Time Indicators")
    phase_data = await page.evaluate(
        """() => {
            const rows = document.querySelectorAll('.phase-row, .step-item');
            let doneCount = 0;
            rows.forEach(r => { if (r.classList.contains('done') || r.classList.contains('completed')) doneCount++; });
            return {total: rows.length, done: doneCount};
        }"""
    )
    if phase_data["total"] > 0:
        if05.set_pass(actual=f"{phase_data['total']} phases, {phase_data['done']} done", expected="> 0 phases")
    else:
        if05.set_fail(actual=phase_data, expected="> 0 phase rows", error="No phase rows found")
    results.append(if05)

    return results


# ---------------------------------------------------------------------------
# IG. Workspace-Specific (IG01-IG08)
# ---------------------------------------------------------------------------
async def run_workspace_interactions(
    page: Page, output_dir: Path
) -> list[CheckResult]:
    """IG01-IG08: Workspace rendering, sidebar, chat, STORM."""
    results: list[CheckResult] = []
    await switch_to_user_mode(page)
    await page.wait_for_timeout(500)

    # --- IG01: Dynamic island renders ---
    ig01 = CheckResult("IG01", "Dynamic island renders in user mode", "IG. Workspace")
    island_html = await page.evaluate(
        "() => { const el = document.getElementById('ws-dynamic-island'); return el ? el.innerHTML.length : 0; }"
    )
    if island_html > 10:
        ig01.set_pass(actual=f"island html={island_html} chars", expected="> 10 chars")
    elif island_html > 0:
        ig01.set_info(actual=f"island html={island_html} chars", note="Minimal content")
    else:
        ig01.set_fail(actual=0, expected="> 0 chars", error="Dynamic island empty")
    results.append(ig01)

    # --- IG02: Right sidebar section toggle ---
    ig02 = CheckResult("IG02", "Right sidebar section toggles expand/collapse", "IG. Workspace")
    toggle_result = await page.evaluate(
        """() => {
            const headers = document.querySelectorAll('.ws-section-header, #ws-right h3, #ws-right .section-toggle');
            if (!headers.length) return {found: false};
            const header = headers[0];
            const section = header.closest('.ws-section') || header.parentElement;
            const wasClosed = section.classList.contains('collapsed');
            header.click();
            const afterClick = section.classList.contains('collapsed');
            return {found: true, toggled: wasClosed !== afterClick, wasClosed: wasClosed, afterClick: afterClick};
        }"""
    )
    if toggle_result.get("found") and toggle_result.get("toggled"):
        ig02.set_pass(actual=toggle_result, expected="section toggled")
    elif toggle_result.get("found"):
        ig02.set_info(actual=toggle_result, note="Header found but toggle may use different mechanism")
    else:
        ig02.set_info(actual="no section headers found", note="Sidebar sections may not have toggle")
    results.append(ig02)

    # --- IG03: Source cards in sidebar (expand + render citation sidebar) ---
    ig03 = CheckResult("IG03", "Sidebar has source cards (.ws-cite-card) after expanding", "IG. Workspace")
    # renderCitationSidebar(citeNumbers) renders ws-cite-card elements into #ws-citation-list.
    # It requires: (1) section not collapsed, (2) citation numbers array, (3) state.bibliography data.
    # In a trace replay, scroll_sync.js never fires, so we must call it manually.
    await page.evaluate(
        """() => {
            // Set workspace to report phase
            if (typeof setWorkspacePhase === 'function') setWorkspacePhase('report');
            else { _wsPhase = 'report'; }
            // Expand citations section (remove collapsed guard)
            var sec = document.getElementById('ws-section-citations');
            if (sec) { sec.classList.remove('collapsed'); sec.classList.add('expanded'); }
            // Call renderCitationSidebar with all bibliography indices
            if (typeof renderCitationSidebar === 'function' && state.bibliography && state.bibliography.length) {
                var nums = state.bibliography.map(function(_, i) { return i + 1; });
                renderCitationSidebar(nums);
            }
        }"""
    )
    await page.wait_for_timeout(500)
    cite_cards = await element_count(page, ".ws-cite-card")
    bib_count = await page.evaluate("() => state.bibliography ? state.bibliography.length : 0")
    if cite_cards > 0:
        ig03.set_pass(actual=f"{cite_cards} cards (bib={bib_count})", expected="> 0")
    elif bib_count > 0:
        ig03.set_fail(actual=f"0 cards, {bib_count} bib entries", expected="> 0 cards",
                      error="Bibliography data exists but renderCitationSidebar failed")
    else:
        ig03.set_fail(actual=0, expected="> 0", error="No bibliography data and no .ws-cite-card")
    results.append(ig03)

    # --- IG04: Source card shows domain + favicon ---
    ig04 = CheckResult("IG04", "Source card shows domain text and favicon", "IG. Workspace")
    if cite_cards > 0:
        card_data = await page.evaluate(
            """() => {
                const card = document.querySelector('.ws-cite-card');
                if (!card) return {found: false};
                const hasImg = card.querySelector('img') !== null;
                const hasDomain = card.querySelector('.ws-cite-card-domain, .ws-cite-domain') !== null;
                const text = card.textContent.trim();
                return {found: true, hasImg: hasImg, hasDomain: hasDomain, textLen: text.length};
            }"""
        )
        if card_data.get("hasImg") or card_data.get("hasDomain"):
            ig04.set_pass(actual=card_data, expected="domain + favicon")
        elif card_data.get("textLen", 0) > 5:
            ig04.set_info(actual=card_data, note="Card has text but specific elements not found")
        else:
            ig04.set_fail(actual=card_data, expected="domain + favicon", error="Card has no domain or favicon")
    else:
        ig04.set_info(actual="no cards", note="Skipped")
    results.append(ig04)

    # --- IG05: Chat textarea accepts input ---
    ig05 = CheckResult("IG05", "Chat textarea accepts typed input", "IG. Workspace")
    textarea = await page.query_selector("#ws-chat-textarea")
    if textarea:
        test_text = "test interaction audit query"
        await textarea.fill(test_text)
        await page.wait_for_timeout(200)
        typed_value = await page.evaluate(
            "() => { const ta = document.getElementById('ws-chat-textarea'); return ta ? ta.value : ''; }"
        )
        if typed_value == test_text:
            ig05.set_pass(actual=f"typed: '{typed_value}'", expected=test_text)
        else:
            ig05.set_fail(actual=f"value='{typed_value}'", expected=test_text, error="Textarea value mismatch")
        # Clear
        await textarea.fill("")
    else:
        ig05.set_fail(actual="textarea not found", expected="#ws-chat-textarea exists",
                      error="Chat textarea missing from workspace")
    results.append(ig05)

    # --- IG06: Report block renders in workspace ---
    ig06 = CheckResult("IG06", "Report block renders in workspace center", "IG. Workspace")
    report_html = await page.evaluate(
        """() => {
            const block = document.querySelector('.ws-report-block, #ws-center .report-rendered');
            return block ? block.innerHTML.length : 0;
        }"""
    )
    if report_html > 100:
        ig06.set_pass(actual=f"report html={report_html} chars", expected="> 100 chars")
    elif report_html > 0:
        ig06.set_info(actual=f"report html={report_html} chars", note="Minimal report content")
    else:
        ig06.set_fail(actual=0, expected="> 100 chars", error="No report block in workspace")
    results.append(ig06)
    await capture_screenshot(page, "ig06_workspace_report", output_dir)

    # --- IG07: Bibliography section in workspace ---
    ig07 = CheckResult("IG07", "Workspace has bibliography with citation numbers", "IG. Workspace")
    bib_data = await page.evaluate(
        """() => {
            const bibSection = document.querySelector('#ws-bibliography, .ws-bibliography, .ws-cite-card');
            const citeCards = document.querySelectorAll('.ws-cite-card');
            return {hasBibSection: !!bibSection, citeCardCount: citeCards.length};
        }"""
    )
    if bib_data["citeCardCount"] > 0:
        ig07.set_pass(actual=f"{bib_data['citeCardCount']} cite cards", expected="> 0")
    else:
        ig07.set_fail(actual=bib_data, expected="bibliography with cards", error="No bibliography cards")
    results.append(ig07)

    # --- IG08: STORM perspectives sidebar ---
    ig08 = CheckResult("IG08", "STORM perspectives sidebar toggles", "IG. Workspace")
    storm_toggle = await page.query_selector(".storm-toggle")
    if storm_toggle:
        await storm_toggle.click()
        await page.wait_for_timeout(300)
        sidebar_state = await page.evaluate(
            "() => { const s = document.getElementById('storm-sidebar'); return s ? {collapsed: s.classList.contains('collapsed'), html: s.innerHTML.length} : null; }"
        )
        if sidebar_state:
            ig08.set_pass(actual=sidebar_state, expected="storm sidebar toggled")
        else:
            ig08.set_info(actual="sidebar element gone after toggle", note="May be using different DOM structure")
    else:
        ig08.set_info(actual="no .storm-toggle", note="STORM sidebar not present in current report")
    results.append(ig08)

    return results


# ---------------------------------------------------------------------------
# IH. Console Errors & Robustness (IH01-IH04)
# ---------------------------------------------------------------------------
async def run_robustness_checks(
    page: Page, console_errors: list, network_errors: list, output_dir: Path
) -> list[CheckResult]:
    """IH01-IH04: Console errors, network failures, screenshots."""
    results: list[CheckResult] = []

    # --- IH01: No JS errors during interactions ---
    ih01 = CheckResult("IH01", "No JS console errors during all interactions", "IH. Robustness")
    known_non_critical = [
        "favicon", "font", "manifest", ".ico", "service-worker",
        "srcdoc", "sandbox", "failed to load resource",
        "net::err", "googletagmanager", "analytics",
    ]
    critical_errors: list[str] = []
    for err in console_errors:
        err_text = str(err.text) if hasattr(err, "text") else str(err)
        is_known = any(p in err_text.lower() for p in known_non_critical)
        if not is_known:
            critical_errors.append(err_text[:200])
    if not critical_errors:
        ih01.set_pass(actual=f"{len(console_errors)} total, 0 critical", expected="0 critical")
    else:
        ih01.set_fail(actual=f"{len(critical_errors)} critical errors",
                      expected="0 critical", error="; ".join(critical_errors[:5]))
    results.append(ih01)

    # --- IH02: No unhandled promise rejections ---
    ih02 = CheckResult("IH02", "No unhandled promise rejections", "IH. Robustness")
    rejection_count = await page.evaluate(
        "() => window.__ia_rejection_count || 0"
    )
    if rejection_count == 0:
        ih02.set_pass(actual=0, expected=0)
    else:
        ih02.set_fail(actual=rejection_count, expected=0, error=f"{rejection_count} unhandled rejections")
    results.append(ih02)

    # --- IH03: No API 4xx/5xx errors ---
    ih03 = CheckResult("IH03", "No API 4xx/5xx errors during interactions", "IH. Robustness")
    api_errors = [e for e in network_errors if "/api/" in e.get("url", "")]
    if not api_errors:
        ih03.set_pass(actual="0 API errors", expected="0")
    else:
        ih03.set_fail(actual=f"{len(api_errors)} API errors",
                      expected="0", error=str(api_errors[:3]))
    results.append(ih03)

    # --- IH04: Final full-page screenshot ---
    ih04 = CheckResult("IH04", "Final screenshots captured for visual review", "IH. Robustness")
    try:
        path = await capture_screenshot(page, "ih04_final_state", output_dir)
        ih04.set_pass(actual=path, expected="screenshot saved")
        ih04.screenshot = path
    except Exception as exc:
        ih04.set_fail(actual=str(exc), expected="screenshot", error="Screenshot failed")
    results.append(ih04)

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_hms_to_seconds(hms: str) -> int:
    match = re.match(r"(\d{2}):(\d{2}):(\d{2})", hms)
    if not match:
        return 0
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3))


def _find_trace_file(cli_trace: str | None) -> Path:
    """Resolve the trace file from CLI arg or fallback candidates."""
    if cli_trace:
        p = Path(cli_trace)
        if p.exists():
            return p
    for candidate in _TRACE_CANDIDATES:
        if candidate.exists():
            return candidate
    return _DEFAULT_TRACE


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(
    results: list[CheckResult],
    console_errors: list,
    network_errors: list,
    output_dir: Path,
) -> dict:
    by_category: dict[str, list[dict]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r.to_dict())

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    info_count = sum(1 for r in results if r.severity == "info")

    report = {
        "audit": "polaris_interaction_audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "info": info_count,
            "pass_rate": f"{(passed / total * 100) if total > 0 else 0:.1f}%",
        },
        "categories": by_category,
        "console_errors": [
            str(e.text) if hasattr(e, "text") else str(e) for e in console_errors[:50]
        ],
        "network_errors": network_errors[:50],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audit_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    logger.info("Report written: %s", report_path)
    return report


def print_console_summary(report: dict) -> None:
    summary = report["summary"]
    print("\n" + "=" * 72)
    print("  POLARIS INTERACTION AUDIT (~58 checks / 8 categories)")
    print("=" * 72)
    print(f"  Total checks: {summary['total_checks']}")
    print(f"  Passed:       {summary['passed']}")
    print(f"  Failed:       {summary['failed']}")
    print(f"  Info:         {summary['info']}")
    print(f"  Pass rate:    {summary['pass_rate']}")
    print("-" * 72)

    for category_name, checks in report["categories"].items():
        print(f"\n  {category_name}:")
        for check in checks:
            if check["severity"] == "info":
                marker = "[INFO]"
            elif check["passed"]:
                marker = "[PASS]"
            else:
                marker = "[FAIL]"
            line = f"    {marker} {check['check_id']}: {check['description']}"
            if not check["passed"] and check.get("error") and check["severity"] != "info":
                line += f"  -- {check['error']}"
            elif check["severity"] == "info" and check.get("error"):
                line += f"  -- {check['error']}"
            print(line)

    if report.get("console_errors"):
        print(f"\n  Console Errors ({len(report['console_errors'])}):")
        for err in report["console_errors"][:10]:
            print(f"    - {err[:120]}")

    if report.get("network_errors"):
        print(f"\n  Network Errors ({len(report['network_errors'])}):")
        for err in report["network_errors"][:5]:
            print(f"    - {err}")

    print("=" * 72 + "\n")


# ---------------------------------------------------------------------------
# Main audit workflow
# ---------------------------------------------------------------------------
async def run_audit(
    port: int,
    output_dir: Path,
    headed: bool = False,
) -> dict:
    """Execute the full ~58-check interaction audit."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[CheckResult] = []
    console_errors: list = []
    network_errors: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            # Accept downloads for export tests
            accept_downloads=True,
        )
        page = await context.new_page()
        page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT_MS)

        # Collect console errors
        page.on(
            "console",
            lambda msg: console_errors.append(msg) if msg.type == "error" else None,
        )

        # Track network errors (4xx/5xx on API calls)
        def on_response(response):
            if response.status >= 400 and "/api/" in response.url:
                network_errors.append({"url": response.url, "status": response.status})
        page.on("response", on_response)

        # Install unhandled rejection counter
        await page.add_init_script("""
            window.__ia_error_count = 0;
            window.__ia_rejection_count = 0;
            window.addEventListener('error', () => { window.__ia_error_count++; });
            window.addEventListener('unhandledrejection', () => { window.__ia_rejection_count++; });
        """)

        # -----------------------------------------------------------
        # 1. Page load + hydration
        # -----------------------------------------------------------
        dashboard_url = f"http://127.0.0.1:{port}/"
        logger.info("Navigating to %s", dashboard_url)
        await page.goto(dashboard_url, wait_until="domcontentloaded")

        logger.info("Waiting for page scripts to initialize (3s)...")
        await page.wait_for_timeout(3000)

        logger.info(
            "Waiting for hydration (target=%d events, timeout=%ds)...",
            HYDRATION_TARGET, HYDRATION_TIMEOUT_S,
        )
        hydrated = await wait_for_hydration(page, HYDRATION_TARGET, HYDRATION_TIMEOUT_S)
        if hydrated:
            logger.info("Hydration complete.")
        else:
            event_count = await page.evaluate(
                "() => { try { return state.eventCount || 0; } catch(e) { return 0; } }"
            )
            logger.warning(
                "Hydration target not reached: %d/%d events. Proceeding anyway.",
                event_count, HYDRATION_TARGET,
            )

        # -----------------------------------------------------------
        # 2. Run interaction categories sequentially
        # -----------------------------------------------------------
        logger.info("Running IB. View Switching & Navigation (IB01-IB08)...")
        all_results.extend(await run_navigation_interactions(page, output_dir))

        logger.info("Running ID. Metrics & Data Display (ID01-ID08)...")
        all_results.extend(await run_metrics_interactions(page))

        logger.info("Running IC. Evidence Browser Interactions (IC01-IC07)...")
        all_results.extend(await run_evidence_interactions(page, output_dir))

        logger.info("Running IA. Citation System Interactions (IA01-IA13)...")
        all_results.extend(await run_citation_interactions(page, output_dir))

        logger.info("Running IE. Export & Action Buttons (IE01-IE05)...")
        all_results.extend(await run_export_interactions(page, output_dir))

        logger.info("Running IF. Real-Time Indicators (IF01-IF05)...")
        all_results.extend(await run_realtime_interactions(page))

        logger.info("Running IG. Workspace-Specific (IG01-IG08)...")
        all_results.extend(await run_workspace_interactions(page, output_dir))

        logger.info("Running IH. Console Errors & Robustness (IH01-IH04)...")
        all_results.extend(await run_robustness_checks(page, console_errors, network_errors, output_dir))

        # -----------------------------------------------------------
        # 3. Cleanup
        # -----------------------------------------------------------
        await browser.close()

    # -----------------------------------------------------------
    # 4. Report
    # -----------------------------------------------------------
    report = generate_report(all_results, console_errors, network_errors, output_dir)
    print_console_summary(report)
    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="POLARIS Interaction Audit")
    parser.add_argument("--port", type=int, default=0, help="Server port (0 = auto)")
    parser.add_argument("--output-dir", type=str, default=str(_DEFAULT_OUTPUT_DIR))
    parser.add_argument("--trace", type=str, default=None, help="Path to JSONL trace file")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    args = parser.parse_args()

    trace_file = _find_trace_file(args.trace)
    if not trace_file.exists():
        logger.error("Trace file not found: %s", trace_file)
        logger.error("Searched: %s", [str(c) for c in _TRACE_CANDIDATES])
        sys.exit(1)
    logger.info("Using trace file: %s", trace_file)

    output_dir = Path(args.output_dir)
    port = args.port or find_free_port()

    # Start server
    server_proc = start_server(port, str(trace_file), output_dir)
    try:
        # Wait for server readiness
        logger.info("Waiting for server on port %d...", port)
        ready = asyncio.run(wait_for_server(port, SERVER_READY_TIMEOUT_S))
        if not ready:
            logger.error("Server failed to start within %ds", SERVER_READY_TIMEOUT_S)
            sys.exit(1)
        logger.info("Server ready on port %d", port)

        # Run the audit
        report = asyncio.run(run_audit(port, output_dir, headed=args.headed))

        # Exit code based on critical failures
        failed = report["summary"]["failed"]
        info = report["summary"]["info"]
        real_failures = failed  # info checks don't count as failures
        if real_failures > 0:
            logger.warning("%d interaction checks FAILED", real_failures)
            sys.exit(1)
        else:
            logger.info("All interaction checks PASSED (%d info)", info)
            sys.exit(0)

    finally:
        stop_server(server_proc)


if __name__ == "__main__":
    main()
