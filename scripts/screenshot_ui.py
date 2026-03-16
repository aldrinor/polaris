"""
screenshot_ui.py — Capture high-res screenshots of idle + running workspace states.
"""
import asyncio
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8790
BASE_URL = f"http://127.0.0.1:{PORT}"
OUTPUT_IDLE = os.path.join(PROJECT_ROOT, "current_ui.png")
OUTPUT_RUNNING = os.path.join(PROJECT_ROOT, "current_ui_running.png")


def start_server():
    log_path = os.path.join(PROJECT_ROOT, "logs", "screenshot_server.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-u", "scripts/live_server.py", "--port", str(PORT)],
        cwd=PROJECT_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    for i in range(30):
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=2)
            print(f"Server ready after {i + 1}s")
            return proc, log_file
        except Exception:
            time.sleep(1)
    proc.kill()
    log_file.close()
    raise RuntimeError("Server did not start within 30s")


INJECT_DOCS_JS = """(() => {
    // Force dark theme
    document.documentElement.setAttribute('data-theme', 'dark');

    // Hide toasts
    document.querySelectorAll('.toast, .notification').forEach(t => t.style.display = 'none');

    // Inject documents
    if (typeof _docPanelDocs !== 'undefined') {
        _docPanelDocs = [
            {doc_id: 'doc1', filename: 'climate_change_impacts.pdf', label: 'Research', size: 245000},
            {doc_id: 'doc2', filename: 'renewable_energy_trends.pdf', label: 'Analysis', size: 180000},
            {doc_id: 'doc3', filename: 'carbon_capture_tech.docx', label: 'Technical', size: 92000},
            {doc_id: 'doc4', filename: 'global_policy_framework.pdf', label: 'Policy', size: 310000},
            {doc_id: 'doc5', filename: 'economic_projections.xlsx', label: 'Data', size: 156000},
            {doc_id: 'doc6', filename: 'sea_level_models.csv', label: 'Modeling', size: 48000},
        ];
        var list = document.getElementById('ws-doc-list');
        var footer = document.getElementById('ws-doc-footer');
        if (list && typeof _renderDocList === 'function') {
            _renderDocList(list, footer);
        }
    }

    // Select two docs
    if (typeof toggleDocSelection === 'function') {
        toggleDocSelection('doc1');
        toggleDocSelection('doc3');
    }
})()"""


async def capture():
    from playwright.async_api import async_playwright

    proc, log_file = start_server()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 1440, "height": 900},
                device_scale_factor=2,
            )

            # === IDLE STATE ===
            await page.goto(f"{BASE_URL}/?mode=user", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Force idle
            await page.evaluate("if (typeof setWorkspacePhase === 'function') setWorkspacePhase('idle');")
            await page.wait_for_timeout(200)
            await page.evaluate(INJECT_DOCS_JS)
            await page.wait_for_timeout(500)

            await page.screenshot(path=OUTPUT_IDLE, full_page=False)
            print(f"Idle screenshot saved to {OUTPUT_IDLE}")

            # === RUNNING STATE ===
            await page.evaluate("""(() => {
                if (typeof setWorkspacePhase === 'function') setWorkspacePhase('running');

                // Inject a prompt bubble and progress block
                var thread = document.querySelector('.ws-thread-inner');
                if (thread) {
                    // Prompt bubble
                    var prompt = document.createElement('div');
                    prompt.className = 'ws-prompt-bubble';
                    prompt.innerHTML = '<div class="ws-prompt-avatar">Q</div>' +
                        '<div class="ws-prompt-content">' +
                        '<div class="ws-prompt-text">What are the most promising carbon capture technologies and their economic viability for large-scale deployment?</div>' +
                        '<div class="ws-prompt-meta">Standard depth</div></div>';
                    thread.appendChild(prompt);

                    // Progress block
                    var progress = document.createElement('div');
                    progress.className = 'ws-progress-block';
                    progress.innerHTML = '<div class="ws-progress-active">' +
                        '<div class="ws-progress-pulse"></div>' +
                        '<span>Analyzing carbon capture technologies...</span></div>' +
                        '<div class="ws-progress-tasks">' +
                        '<div class="ws-progress-task done"><span class="ws-progress-task-icon">&#10003;</span> Planning research queries</div>' +
                        '<div class="ws-progress-task done"><span class="ws-progress-task-icon">&#10003;</span> Searching 24 sources</div>' +
                        '<div class="ws-progress-task done"><span class="ws-progress-task-icon">&#10003;</span> Fetching content from 18 URLs</div>' +
                        '<div class="ws-progress-task active"><span class="ws-progress-task-icon">&#9679;</span> Analyzing evidence clusters</div>' +
                        '<div class="ws-progress-task pending"><span class="ws-progress-task-icon">&#9675;</span> Verifying claims</div>' +
                        '<div class="ws-progress-task pending"><span class="ws-progress-task-icon">&#9675;</span> Synthesizing report</div></div>' +
                        '<div class="ws-progress-footer"><span class="ws-progress-time">2m 34s</span>' +
                        '<button class="ws-progress-cancel">Cancel</button></div>';
                    thread.appendChild(progress);
                }

                // Inject right-panel metrics
                var evEl = document.getElementById('ws-metric-evidence');
                var srcEl = document.getElementById('ws-metric-sources');
                if (evEl) evEl.textContent = '142';
                if (srcEl) srcEl.textContent = '18';
            })()""")
            await page.wait_for_timeout(500)

            await page.screenshot(path=OUTPUT_RUNNING, full_page=False)
            print(f"Running screenshot saved to {OUTPUT_RUNNING}")

            # === REPORT STATE ===
            await page.evaluate("""(() => {
                if (typeof setWorkspacePhase === 'function') setWorkspacePhase('report');
            })()""")
            await page.wait_for_timeout(500)

            report_path = os.path.join(PROJECT_ROOT, "current_ui_report.png")
            await page.screenshot(path=report_path, full_page=False)
            print(f"Report screenshot saved to {report_path}")

            await browser.close()
    finally:
        proc.kill()
        proc.wait()
        log_file.close()


if __name__ == "__main__":
    asyncio.run(capture())
