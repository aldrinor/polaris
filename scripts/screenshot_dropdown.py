"""Screenshot the depth dropdown in its open state."""
import asyncio
import os
import subprocess
import sys
import time
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8790
BASE_URL = f"http://127.0.0.1:{PORT}"


def start_server():
    log_path = os.path.join(PROJECT_ROOT, "logs", "screenshot_server.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-u", "scripts/live_server.py", "--port", str(PORT)],
        cwd=PROJECT_ROOT, stdout=log_file, stderr=subprocess.STDOUT,
    )
    for i in range(30):
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=2)
            return proc, log_file
        except Exception:
            time.sleep(1)
    proc.kill()
    log_file.close()
    raise RuntimeError("Server did not start")


async def capture():
    from playwright.async_api import async_playwright
    proc, log_file = start_server()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 1440, "height": 900}, device_scale_factor=2,
            )
            await page.goto(f"{BASE_URL}/?mode=user", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.evaluate("""(() => {
                document.documentElement.setAttribute('data-theme', 'dark');
                if (typeof setWorkspacePhase === 'function') setWorkspacePhase('idle');
            })()""")
            await page.wait_for_timeout(300)

            # Open the depth dropdown
            await page.evaluate("""(() => {
                var menu = document.getElementById('ws-depth-menu');
                if (menu) menu.classList.add('open');
            })()""")
            await page.wait_for_timeout(200)

            out = os.path.join(PROJECT_ROOT, "current_ui_dropdown.png")
            await page.screenshot(path=out, full_page=False)
            print(f"Saved to {out}")
            await browser.close()
    finally:
        proc.kill()
        proc.wait()
        log_file.close()

if __name__ == "__main__":
    asyncio.run(capture())
