"""
Diagnostic: render report via the REAL app path (state + renderReportView)
and capture screenshots showing all Gemini elements.
"""

import base64
import io
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS = PROJECT_ROOT / "outputs" / "gemini_screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


def _make_chart_b64() -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3, 2))
    ax.bar(["Epoxy", "Urethane", "Silicone"], [45.2, 38.7, 29.1],
           color=["#38bdf8", "#818cf8", "#c084fc"])
    ax.set_ylabel("Adhesion (MPa)")
    ax.set_title("Material Comparison")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# JS functions as separate strings to avoid escape hell
JS_INJECT_STATE = """(reportMd) => {
    var result = {
        hasSafeMarkdown: typeof safeMarkdown === 'function',
        hasMarked: typeof marked !== 'undefined',
        hasDOMPurify: typeof DOMPurify !== 'undefined',
        hasRenderReportView: typeof renderReportView === 'function',
        hasSetViewMode: typeof setViewMode === 'function',
        hasState: typeof state !== 'undefined',
    };

    if (typeof state !== 'undefined') {
        state.fullReport = reportMd;
        state.pipelineComplete = true;
        state.bibliography = [
            {title: 'Source 1', url: 'https://example.com/1', authors: 'Smith 2024'},
            {title: 'Source 2', url: 'https://example.com/2', authors: 'Jones 2023'},
            {title: 'Source 3', url: 'https://example.com/3', authors: 'Lee 2022'},
        ];
    }

    if (typeof setViewMode === 'function') {
        setViewMode('report');
    }

    if (typeof renderReportView === 'function') {
        try {
            renderReportView();
            result.renderResult = 'success';
        } catch(e) {
            result.renderResult = 'error: ' + e.message;
        }
    }

    return result;
}"""

JS_CHECK_DOM = """() => {
    var rr = document.querySelector('.report-rendered');
    var allImgs = document.querySelectorAll('img');
    var b64imgs = document.querySelectorAll('img[src*="base64"]');
    var tables = rr ? rr.querySelectorAll('table') : document.querySelectorAll('table');
    var kf = document.querySelectorAll('.key-findings');
    var metrics = document.querySelectorAll('.report-metrics-card');
    var toc = document.querySelectorAll('.report-toc');

    var imgDetails = [];
    allImgs.forEach(function(img) {
        var rect = img.getBoundingClientRect();
        var cs = window.getComputedStyle(img);
        imgDetails.push({
            srcPrefix: (img.src || '').substring(0, 60),
            isBase64: (img.src || '').indexOf('base64') > -1,
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            naturalW: img.naturalWidth,
            naturalH: img.naturalHeight,
            display: cs.display,
            visibility: cs.visibility,
            maxWidth: cs.maxWidth,
            parentTag: img.parentElement ? img.parentElement.tagName : 'none',
        });
    });

    var kfDetails = [];
    kf.forEach(function(el) {
        var rect = el.getBoundingClientRect();
        kfDetails.push({
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            items: el.querySelectorAll('li').length,
            borderLeft: window.getComputedStyle(el).borderLeftStyle,
        });
    });

    return {
        reportRendered: !!rr,
        rrScrollHeight: rr ? rr.scrollHeight : 0,
        rrDisplay: rr ? window.getComputedStyle(rr).display : 'none',
        allImgs: allImgs.length,
        b64Imgs: b64imgs.length,
        imgDetails: imgDetails,
        tables: tables.length,
        keyFindings: kf.length,
        kfDetails: kfDetails,
        metricsCards: metrics.length,
        toc: toc.length,
        bodyScrollHeight: document.body.scrollHeight,
        htmlSnippet: rr ? rr.innerHTML.substring(0, 300) : 'NO .report-rendered',
    };
}"""

JS_SCROLL_AND_CAPTURE = """(y) => {
    var rr = document.querySelector('.report-rendered');
    if (rr) {
        rr.scrollTop = y;
    }
    window.scrollTo(0, y);
    return {
        windowScrollY: window.scrollY,
        rrScrollTop: rr ? rr.scrollTop : -1,
    };
}"""


def main():
    chart_b64 = _make_chart_b64()
    report_md = (
        "# Adhesion Testing of Advanced Polymer Coatings\n\n"
        ":::metrics\n"
        "Sources: 24 | Evidence: 187 | Faithfulness: 89.2% | Unique Claims: 52\n"
        ":::\n\n"
        "## Abstract\n\n"
        "This report examines adhesion testing methodologies for advanced polymer "
        "coatings [1]. The analysis covers three primary material categories: "
        "epoxy-based, urethane-based, and silicone-based formulations [2][3].\n\n"
        "## 1. Material Comparison\n\n"
        "Epoxy-based coatings demonstrated the highest adhesion strength at 45.2 MPa [1], "
        "while urethane formulations achieved 38.7 MPa [2].\n\n"
        "| Material | Adhesion (MPa) | Standard Dev | Test Method |\n"
        "| --- | --- | --- | --- |\n"
        "| Epoxy Resin | 45.2 | +/-2.3 | ASTM D4541 |\n"
        "| Urethane | 38.7 | +/-1.8 | ASTM D4541 |\n"
        "| Silicone | 29.1 | +/-3.1 | ISO 4624 |\n\n"
        "*Table 1: Material comparison.*\n\n"
        f"![Material Comparison](data:image/png;base64,{chart_b64})\n\n"
        "*Figure 1: Adhesion strength by material type.*\n\n"
        "## 2. Environmental Factors\n\n"
        "Temperature cycling reduced adhesion by 12-18% [4]. "
        "Humidity above 85% RH caused 7-9% degradation [5].\n\n"
        "**Key Findings:**\n"
        "- Epoxy retains 82% adhesion after 1000 thermal cycles [1]\n"
        "- Urethane shows 3% UV degradation [2]\n"
        "- Silicone has best chemical resistance [3]\n"
        "- Cross-linked outperforms linear by 25-40% [4]\n"
        "- ASTM D4541 and ISO 4624 comparable within +/-5% [5]\n\n"
        "## 3. Test Methodology\n\n"
        "The pull-off test (ASTM D4541) remains industry standard [6].\n"
    )

    port = find_free_port()
    log_file = open(PROJECT_ROOT / "logs" / "diag_server.log", "w")
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "live_server.py"),
         "--port", str(port)],
        stdout=log_file, stderr=log_file, cwd=str(PROJECT_ROOT),
    )

    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=2)
            break
        except Exception:
            time.sleep(0.5)

    print(f"Server on port {port}")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(
                viewport={"width": 1400, "height": 900}
            ).new_page()
            page.goto(f"http://localhost:{port}/", timeout=15000)
            page.wait_for_load_state("domcontentloaded")

            # Step 1: Inject via real app path
            result = page.evaluate(JS_INJECT_STATE, report_md)
            print(f"Inject: {json.dumps(result, indent=2)}")

            page.wait_for_timeout(3000)

            # Step 2: Check DOM
            dom = page.evaluate(JS_CHECK_DOM)
            print(f"\nDOM: {json.dumps(dom, indent=2)}")

            # Step 3: Screenshots at different scroll positions
            page.screenshot(
                path=str(SCREENSHOTS / "diag_01_viewport.png"),
                full_page=False,
            )
            print("\n[1] Viewport screenshot saved")

            page.screenshot(
                path=str(SCREENSHOTS / "diag_02_fullpage.png"),
                full_page=True,
            )
            print("[2] Full page screenshot saved")

            # Try scrolling both window and container
            for y in [400, 800, 1200, 1600]:
                scroll_info = page.evaluate(JS_SCROLL_AND_CAPTURE, y)
                page.wait_for_timeout(300)
                page.screenshot(
                    path=str(SCREENSHOTS / f"diag_scroll_{y}.png"),
                    full_page=False,
                )
                print(f"[scroll={y}] {scroll_info}")

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f"\nScreenshots: {SCREENSHOTS}")
    print("DONE")


if __name__ == "__main__":
    main()
