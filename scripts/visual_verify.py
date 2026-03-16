"""
Visual verification of Gemini-class frontend rendering.
Captures viewport screenshots at key scroll positions for Claude Vision review.
"""

import base64
import io
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

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


def _build_report(chart_b64: str) -> str:
    return (
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
        "while urethane formulations achieved 38.7 MPa [2]. Silicone-based coatings "
        "showed 29.1 MPa [3].\n\n"
        "| Material | Adhesion (MPa) | Standard Dev | Test Method |\n"
        "| --- | --- | --- | --- |\n"
        "| Epoxy Resin | 45.2 | +/-2.3 | ASTM D4541 |\n"
        "| Urethane | 38.7 | +/-1.8 | ASTM D4541 |\n"
        "| Silicone | 29.1 | +/-3.1 | ISO 4624 |\n"
        "| Acrylic | 22.5 | +/-2.7 | ASTM D4541 |\n\n"
        "*Table 1: Adhesion strength comparison across material categories.*\n\n"
        f"![Material Comparison](data:image/png;base64,{chart_b64})\n\n"
        "*Figure 1: Adhesion strength by material type.*\n\n"
        "## 2. Environmental Factors\n\n"
        "Temperature cycling between -40C and 85C reduced adhesion by 12-18% "
        "across all materials [4]. Humidity exposure above 85% RH for 500 hours "
        "caused a 7-9% degradation [5].\n\n"
        "**Key Findings:**\n"
        "- Epoxy coatings retain 82% adhesion after 1000 thermal cycles [1]\n"
        "- Urethane formulations show superior UV resistance with only 3% degradation [2]\n"
        "- Silicone-based coatings exhibit the best chemical resistance [3]\n"
        "- Cross-linked formulations outperform linear polymers by 25-40% [4]\n"
        "- ASTM D4541 and ISO 4624 produce comparable results within +/-5% [5]\n\n"
        "## 3. Test Methodology\n\n"
        "The pull-off adhesion test (ASTM D4541) remains the industry standard [6]. "
        "Recent developments in nano-indentation provide sub-micron resolution for "
        "thin-film adhesion characterization [7].\n"
    )


# JS to inject report — kept as raw string to avoid escape issues
INJECT_JS = r"""(reportMd) => {
    // Hide everything else
    document.querySelectorAll('body > *').forEach(el => { el.style.display = 'none'; });

    // Create standalone report container
    var container = document.createElement('div');
    container.className = 'report-rendered';
    container.style.cssText = 'padding:32px 48px;background:var(--bg-primary,white);min-height:100vh;display:block;';
    document.body.appendChild(container);

    var html = typeof marked !== 'undefined' ? marked.parse(reportMd) : reportMd;
    if (typeof DOMPurify !== 'undefined') {
        html = DOMPurify.sanitize(html, {
            ADD_ATTR: ['target'],
            ADD_DATA_URI_TAGS: ['img'],
            ADD_URI_SAFE_ATTR: ['src']
        });
    }
    container.innerHTML = html;

    // Wrap Key Findings
    html = container.innerHTML;
    html = html.replace(
        /<p><strong>Key Findings:?<\/strong><\/p>\s*<ul>([\s\S]*?)<\/ul>/gi,
        function(match, listContent) {
            return '<div class="key-findings"><div class="key-findings-title">Key Findings</div><ul>' + listContent + '</ul></div>';
        }
    );
    // Parse :::metrics blocks
    html = html.replace(
        /<p>:::metrics\s*\n?([\s\S]*?):::<\/p>/gi,
        function(match, metricsContent) {
            var items = metricsContent.split('|').map(function(s) { return s.trim(); }).filter(Boolean);
            var cardHtml = '<div class="report-metrics-card">';
            items.forEach(function(item) {
                var parts = item.split(':').map(function(s) { return s.trim(); });
                if (parts.length >= 2) {
                    cardHtml += '<div class="metric-item"><div class="metric-value">' + parts[1] + '</div><div class="metric-label">' + parts[0] + '</div></div>';
                }
            });
            cardHtml += '</div>';
            return cardHtml;
        }
    );
    container.innerHTML = html;

    return {
        imgs: document.querySelectorAll('img[src^="data:image/png;base64"]').length,
        tables: document.querySelectorAll('table').length,
        keyFindings: document.querySelectorAll('.key-findings').length,
        metricsCards: document.querySelectorAll('.report-metrics-card').length,
        h1: document.querySelectorAll('h1').length,
        h2: document.querySelectorAll('h2').length,
    };
}"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main():
    from playwright.sync_api import sync_playwright

    chart_b64 = _make_chart_b64()
    report_md = _build_report(chart_b64)

    port = find_free_port()
    log_path = PROJECT_ROOT / "logs" / "visual_verify_server.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "live_server.py"),
         "--port", str(port)],
        stdout=log_file, stderr=log_file, cwd=str(PROJECT_ROOT),
    )

    # Wait for server
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=2)
            break
        except Exception:
            time.sleep(0.5)

    print(f"Server started on port {port}")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            page.goto(f"http://localhost:{port}/", timeout=15000)
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Inject report
            dom_counts = page.evaluate(INJECT_JS, report_md)
            print(f"DOM: {dom_counts}")

            page.wait_for_timeout(2000)  # Let images decode

            # Screenshot 1: Top — metrics card + abstract
            page.screenshot(
                path=str(SCREENSHOTS / "visual_01_metrics_abstract.png"),
                full_page=False,
            )
            print("  [1] Metrics + Abstract viewport")

            # Screenshot 2: Scroll to table area
            page.evaluate("() => window.scrollTo(0, 550)")
            page.wait_for_timeout(500)
            page.screenshot(
                path=str(SCREENSHOTS / "visual_02_table.png"),
                full_page=False,
            )
            print("  [2] Table viewport")

            # Screenshot 3: Scroll to chart
            page.evaluate("() => window.scrollTo(0, 950)")
            page.wait_for_timeout(500)
            page.screenshot(
                path=str(SCREENSHOTS / "visual_03_chart.png"),
                full_page=False,
            )
            print("  [3] Chart viewport")

            # Screenshot 4: Scroll to Key Findings
            page.evaluate("() => window.scrollTo(0, 1300)")
            page.wait_for_timeout(500)
            page.screenshot(
                path=str(SCREENSHOTS / "visual_04_key_findings.png"),
                full_page=False,
            )
            print("  [4] Key Findings viewport")

            # Screenshot 5: Full page
            page.screenshot(
                path=str(SCREENSHOTS / "visual_05_full_page.png"),
                full_page=True,
            )
            print("  [5] Full page")

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server stopped")

    print(f"\nScreenshots saved to: {SCREENSHOTS}")
    print("DONE")


if __name__ == "__main__":
    main()
