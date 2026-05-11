"""Drive ChatGPT Deep Research and Gemini Deep Research through the
browser UI via Playwright + CDP. Saves outputs as markdown.

Run:
  python scripts/competitor_dr_runner.py --provider chatgpt --question Q1
  python scripts/competitor_dr_runner.py --provider gemini  --question Q1
  python scripts/competitor_dr_runner.py --provider both    --all

Selectors confirmed against current chatgpt.com + gemini.google.com
(2026-05). Polls until DR finishes (typically 10-30 min). Saves
final markdown to state/compare_{provider}_{qid}.md.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from playwright.async_api import Page, async_playwright


CDP_URL = "http://localhost:9222"
OUT_DIR = Path("state")

QUESTIONS = {
    "Q1": "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?",
    "Q2": "How are Canada's CUSMA review preparations (2026 Article 34.7 mandatory review) being shaped by the second Trump administration's tariff threats on Canadian steel, aluminum, and softwood lumber, and what are the realistic negotiating leverage points for the Carney government?",
    "Q3": "What is the projected impact of generative-AI adoption on Canadian white-collar employment in finance, legal, and public-sector knowledge work over 2026-2030, and what active labour-market interventions have evidence of effectiveness in analogous past technology shocks?",
    "Q4": "What is the evidence base for the effectiveness of supply-side housing interventions (zoning reform, infrastructure-tied federal transfers, modular construction subsidies, foreign-buyer bans) versus demand-side interventions (mortgage stress-test changes, first-time-buyer incentives, immigration-pacing) on housing affordability in major Canadian metros 2020-2026?",
    "Q5": "What is the evidence base for the effectiveness of pharmacare programs at reducing population-level chronic-disease morbidity and out-of-pocket household drug spending, comparing Quebec RPAM, New Zealand PHARMAC, and UK NHS models, with implications for the federal Pharmacare Act (Bill C-64) rollout in Canada?",
}

DR_TIMEOUT_MIN = 60
DR_POLL_INTERVAL_S = 30


# ---------------------------------------------------------------------------
# ChatGPT Deep Research
# ---------------------------------------------------------------------------

async def chatgpt_run_dr(page: Page, question: str) -> str:
    print("[chatgpt] navigating to chatgpt.com")
    await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3500)

    # Ensure composer empty (clear any prior text)
    composer = await page.wait_for_selector("#prompt-textarea", timeout=10000)
    await composer.click()
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(500)

    # Click + button to open tools menu
    print("[chatgpt] clicking + button")
    plus = await page.query_selector('[data-testid="composer-plus-btn"]')
    if not plus:
        raise RuntimeError("ChatGPT + composer button not found")
    await plus.click()
    await page.wait_for_timeout(1500)

    # Click "Deep research" menuitemradio inside the popover
    print("[chatgpt] enabling Deep research")
    # Try by role+text, fall back to text only
    dr_clicked = False
    candidates = [
        '[role="menuitemradio"]:has-text("Deep research")',
        '[role="menuitem"]:has-text("Deep research")',
        'div[role="menuitemradio"]:has-text("Deep research")',
        'text=Deep research',
    ]
    for sel in candidates:
        try:
            el = await page.wait_for_selector(sel, timeout=2500)
            if el and await el.is_visible():
                await el.click()
                dr_clicked = True
                print(f"[chatgpt] Deep research clicked via {sel}")
                break
        except Exception:
            continue
    if not dr_clicked:
        raise RuntimeError("Could not click Deep research entry")
    await page.wait_for_timeout(1500)

    # Refocus composer (some flows steal focus)
    composer = await page.query_selector("#prompt-textarea")
    await composer.click()
    await page.wait_for_timeout(300)

    # Type question (use fill on contenteditable)
    print(f"[chatgpt] typing question ({len(question)} chars)")
    await page.keyboard.insert_text(question)
    await page.wait_for_timeout(800)

    # Submit
    print("[chatgpt] submitting")
    send_btn = await page.query_selector('[data-testid="send-button"]')
    if send_btn and await send_btn.is_enabled():
        await send_btn.click()
    else:
        await composer.press("Enter")

    # Some ChatGPT DR flows surface a follow-up clarification dialog. Wait
    # for it; if the user has to answer, the run hangs. We auto-skip by
    # clicking the "Start research" / "Submit" / similar.
    await page.wait_for_timeout(5000)
    skip_candidates = [
        'button:has-text("Start research")',
        'button:has-text("Skip")',
        'button:has-text("Submit")',
        'button:has-text("Begin")',
        'button:has-text("Continue")',
    ]
    for sel in skip_candidates:
        try:
            b = await page.query_selector(sel)
            if b and await b.is_visible():
                print(f"[chatgpt] clicking clarification gate: {sel}")
                await b.click()
                break
        except Exception:
            continue

    # Poll for completion. ChatGPT DR shows a "Researching..." status; when
    # done, the final report is in the last assistant message and contains
    # "Sources" or a numbered citation block.
    print(f"[chatgpt] polling up to {DR_TIMEOUT_MIN} min")
    start = time.time()
    deadline = start + DR_TIMEOUT_MIN * 60
    last_text = ""
    stable_streak = 0
    while time.time() < deadline:
        await page.wait_for_timeout(DR_POLL_INTERVAL_S * 1000)
        try:
            asst = await page.query_selector_all('[data-message-author-role="assistant"]')
            if not asst:
                print(f"[chatgpt] no assistant message yet ({int(time.time()-start)}s)")
                continue
            last = asst[-1]
            text = await last.inner_text()
            elapsed = int(time.time() - start)
            print(f"[chatgpt] elapsed={elapsed}s len={len(text)} stable={stable_streak}")
            if len(text) > 2000 and (
                "ources" in text or "[1]" in text or "[^" in text or "Bibliography" in text
            ):
                if text == last_text:
                    stable_streak += 1
                    if stable_streak >= 2:
                        return text
                else:
                    stable_streak = 0
                    last_text = text
        except Exception as e:
            print(f"[chatgpt] poll error: {e}")
    raise TimeoutError(f"ChatGPT DR did not complete within {DR_TIMEOUT_MIN} min")


# ---------------------------------------------------------------------------
# Gemini Deep Research
# ---------------------------------------------------------------------------

async def gemini_run_dr(page: Page, question: str) -> str:
    print("[gemini] navigating to gemini.google.com/app")
    await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)

    # Click Tools button
    print("[gemini] opening Tools menu")
    tools = await page.wait_for_selector("button:has-text('Tools')", timeout=10000)
    await tools.click()
    await page.wait_for_timeout(1500)

    # Click "Deep research"
    print("[gemini] selecting Deep research")
    dr_clicked = False
    for sel in [
        '[role="menuitem"]:has-text("Deep research")',
        'button:has-text("Deep research")',
        'text=Deep research',
    ]:
        try:
            el = await page.wait_for_selector(sel, timeout=2500)
            if el and await el.is_visible():
                await el.click()
                dr_clicked = True
                print(f"[gemini] Deep research clicked via {sel}")
                break
        except Exception:
            continue
    if not dr_clicked:
        raise RuntimeError("Could not click Gemini Deep research")
    await page.wait_for_timeout(1500)

    # Focus composer and type question
    composer = None
    for sel in [
        'rich-textarea [contenteditable="true"]',
        '[contenteditable="true"][role="textbox"]',
        '[contenteditable="true"]',
    ]:
        composer = await page.query_selector(sel)
        if composer and await composer.is_visible():
            break
    if not composer:
        raise RuntimeError("Gemini composer not found")
    await composer.click()
    await page.keyboard.insert_text(question)
    await page.wait_for_timeout(800)

    # Submit (button or Enter)
    print("[gemini] submitting")
    send = await page.query_selector('button[aria-label="Send message"]')
    if send and await send.is_enabled():
        await send.click()
    else:
        await composer.press("Enter")

    # Gemini DR may present a research-plan preview to approve. Click
    # "Start research" or "Approve plan" if shown.
    await page.wait_for_timeout(6000)
    for sel in [
        'button:has-text("Start research")',
        'button:has-text("Approve plan")',
        'button:has-text("Approve")',
        'button:has-text("Start")',
    ]:
        try:
            b = await page.query_selector(sel)
            if b and await b.is_visible():
                print(f"[gemini] clicking plan-approval: {sel}")
                await b.click()
                break
        except Exception:
            continue

    # Poll for completion
    print(f"[gemini] polling up to {DR_TIMEOUT_MIN} min")
    start = time.time()
    deadline = start + DR_TIMEOUT_MIN * 60
    last_text = ""
    stable_streak = 0
    while time.time() < deadline:
        await page.wait_for_timeout(DR_POLL_INTERVAL_S * 1000)
        try:
            responses = await page.query_selector_all(
                'message-content, model-response, [data-test-id="response"]'
            )
            if not responses:
                # Try generic message containers
                responses = await page.query_selector_all('[class*="message" i]')
            if not responses:
                print(f"[gemini] no response yet ({int(time.time()-start)}s)")
                continue
            last = responses[-1]
            text = await last.inner_text()
            elapsed = int(time.time() - start)
            print(f"[gemini] elapsed={elapsed}s len={len(text)} stable={stable_streak}")
            if len(text) > 2000 and (
                "ources" in text or "[1]" in text or "Bibliography" in text
            ):
                if text == last_text:
                    stable_streak += 1
                    if stable_streak >= 2:
                        return text
                else:
                    stable_streak = 0
                    last_text = text
        except Exception as e:
            print(f"[gemini] poll error: {e}")
    raise TimeoutError(f"Gemini DR did not complete within {DR_TIMEOUT_MIN} min")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_one(provider: str, qid: str, question: str) -> None:
    out_path = OUT_DIR / f"compare_{provider}_{qid.lower()}.md"
    if out_path.exists() and out_path.stat().st_size > 2000:
        print(f"[skip] {out_path} already exists ({out_path.stat().st_size} bytes)")
        return

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        # Reuse the existing tab if open; otherwise open a new one.
        target_host = "chatgpt.com" if provider == "chatgpt" else "gemini.google.com"
        page = next((pg for pg in context.pages if target_host in pg.url), None)
        if not page:
            page = await context.new_page()
        await page.bring_to_front()
        if provider == "chatgpt":
            content = await chatgpt_run_dr(page, question)
        else:
            content = await gemini_run_dr(page, question)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"# {provider.upper()} Deep Research — {qid}\n\n"
        f"**Question:** {question}\n\n---\n\n" + content,
        encoding="utf-8",
    )
    print(f"[saved] {out_path} ({len(content)} chars)")


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", choices=["chatgpt", "gemini", "both"], default="both")
    p.add_argument("--question", choices=list(QUESTIONS.keys()) + ["all"], default="all")
    args = p.parse_args()

    providers = ["chatgpt", "gemini"] if args.provider == "both" else [args.provider]
    questions = list(QUESTIONS.keys()) if args.question == "all" else [args.question]

    for qid in questions:
        for provider in providers:
            print(f"\n=== {provider} / {qid} ===")
            try:
                await run_one(provider, qid, QUESTIONS[qid])
            except Exception as e:
                print(f"[error] {provider}/{qid}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
