"""
Final visual verification with tall viewport to capture all content.
Uses standalone rendering (not the real app views) since the real app
requires an active research session with SSE events.
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

    fig, ax = plt.subplots(figsize=(4, 3))
    materials = ["Epoxy", "Urethane", "Silicone", "Acrylic"]
    values = [45.2, 38.7, 29.1, 22.5]
    colors = ["#38bdf8", "#818cf8", "#c084fc", "#fb923c"]
    ax.bar(materials, values, color=colors)
    ax.set_ylabel("Adhesion (MPa)")
    ax.set_title("Material Comparison")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# JS to inject — uses the app's CSS by adding .report-rendered class
# and explicitly sets dimensions to ensure content expands
INJECT_JS = r"""(reportMd) => {
    // Hide all existing content
    var body = document.body;
    Array.from(body.children).forEach(function(el) {
        el.style.display = 'none';
    });

    // Create report container matching real CSS selectors
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'width:100%;max-width:900px;margin:0 auto;padding:40px;';
    var container = document.createElement('div');
    container.className = 'report-rendered';
    container.style.cssText = 'display:block;width:100%;';
    wrapper.appendChild(container);
    body.appendChild(wrapper);
    body.style.overflow = 'visible';
    body.style.height = 'auto';
    document.documentElement.style.overflow = 'visible';
    document.documentElement.style.height = 'auto';

    // Render markdown
    var html = typeof marked !== 'undefined' ? marked.parse(reportMd) : reportMd;
    if (typeof DOMPurify !== 'undefined') {
        html = DOMPurify.sanitize(html, {
            ADD_ATTR: ['target'],
            ADD_DATA_URI_TAGS: ['img'],
            ADD_URI_SAFE_ATTR: ['src']
        });
    }
    container.innerHTML = html;

    // Apply Key Findings wrapping
    html = container.innerHTML;
    html = html.replace(
        /<p><strong>Key Findings:?<\/strong><\/p>\s*<ul>([\s\S]*?)<\/ul>/gi,
        function(m, list) {
            return '<div class="key-findings"><div class="key-findings-title">Key Findings</div><ul>' + list + '</ul></div>';
        }
    );
    // Apply :::metrics parsing
    html = html.replace(
        /<p>:::metrics\s*\n?([\s\S]*?):::<\/p>/gi,
        function(m, content) {
            var items = content.split('|').map(function(s) { return s.trim(); }).filter(Boolean);
            var card = '<div class="report-metrics-card">';
            items.forEach(function(item) {
                var parts = item.split(':').map(function(s) { return s.trim(); });
                if (parts.length >= 2) {
                    card += '<div class="metric-item"><div class="metric-value">' + parts[1] + '</div><div class="metric-label">' + parts[0] + '</div></div>';
                }
            });
            card += '</div>';
            return card;
        }
    );
    container.innerHTML = html;

    // Force all images to render at natural size
    container.querySelectorAll('img').forEach(function(img) {
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        img.style.display = 'block';
    });

    // Check results
    return {
        containerHeight: container.scrollHeight,
        imgs: container.querySelectorAll('img[src*="base64"]').length,
        tables: container.querySelectorAll('table').length,
        keyFindings: container.querySelectorAll('.key-findings').length,
        metricsCards: container.querySelectorAll('.report-metrics-card').length,
        headings: container.querySelectorAll('h1,h2,h3').length,
        htmlLength: container.innerHTML.length,
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
        "while urethane formulations achieved 38.7 MPa [2]. "
        "Silicone-based coatings showed 29.1 MPa [3].\n\n"
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

    port = find_free_port()
    log_file = open(PROJECT_ROOT / "logs" / "visual_final_server.log", "w")
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
            # Use a TALL viewport to see everything without scrolling
            page = browser.new_context(
                viewport={"width": 1200, "height": 3000}
            ).new_page()
            page.goto(f"http://localhost:{port}/", timeout=15000)
            page.wait_for_load_state("domcontentloaded")

            # Inject report
            result = page.evaluate(INJECT_JS, report_md)
            print(f"Inject result: {json.dumps(result, indent=2)}")

            # Wait for image decode
            page.wait_for_timeout(3000)

            # Capture with tall viewport (should see everything)
            page.screenshot(
                path=str(SCREENSHOTS / "final_all_content.png"),
                full_page=True,
            )
            print("Full page screenshot saved")

            # Also capture at normal viewport for realistic view
            page.set_viewport_size({"width": 1200, "height": 900})
            page.wait_for_timeout(500)

            # Top section (metrics + abstract)
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(200)
            page.screenshot(
                path=str(SCREENSHOTS / "final_01_top.png"),
                full_page=False,
            )
            print("[1] Top section")

            # Mid section (table + chart)
            page.evaluate("() => window.scrollTo(0, 600)")
            page.wait_for_timeout(200)
            page.screenshot(
                path=str(SCREENSHOTS / "final_02_mid.png"),
                full_page=False,
            )
            print("[2] Mid section")

            # Bottom section (key findings)
            page.evaluate("() => window.scrollTo(0, 1200)")
            page.wait_for_timeout(200)
            page.screenshot(
                path=str(SCREENSHOTS / "final_03_bottom.png"),
                full_page=False,
            )
            print("[3] Bottom section")

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
