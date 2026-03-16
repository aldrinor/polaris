"""Playwright helper — runs in a separate process to avoid asyncio conflicts.

Usage: python scripts/pw_render_helper.py <port> <report_file> <output_dir>

Reads markdown from report_file, renders it via the live server on the given port,
captures a full-page screenshot, and prints DOM stats as JSON to stdout.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

INJECT_JS = r"""(reportMd) => {
    // Hide existing UI
    Array.from(document.body.children).forEach(function(el) { el.style.display = 'none'; });

    // Create report container
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'width:100%;max-width:900px;margin:0 auto;padding:40px;';
    var container = document.createElement('div');
    container.className = 'report-rendered';
    container.style.cssText = 'display:block;width:100%;';
    wrapper.appendChild(container);
    document.body.appendChild(wrapper);
    document.body.style.overflow = 'visible';
    document.body.style.height = 'auto';
    document.documentElement.style.overflow = 'visible';

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

    return {
        containerHeight: container.scrollHeight,
        h1: container.querySelectorAll('h1').length,
        h2: container.querySelectorAll('h2').length,
        h3: container.querySelectorAll('h3').length,
        tables: container.querySelectorAll('table').length,
        imgs: container.querySelectorAll('img').length,
        b64imgs: container.querySelectorAll('img[src*="base64"]').length,
        links: container.querySelectorAll('a').length,
        lists: container.querySelectorAll('ul,ol').length,
        paragraphs: container.querySelectorAll('p').length,
        keyFindings: container.querySelectorAll('.key-findings').length,
        metricsCards: container.querySelectorAll('.report-metrics-card').length,
        wordCount: container.innerText.split(/\s+/).length,
        htmlLength: container.innerHTML.length,
    };
}"""


def main():
    port = int(sys.argv[1])
    report_file = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    output_dir.mkdir(parents=True, exist_ok=True)

    report_md = report_file.read_text(encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            viewport={"width": 1200, "height": 3000}
        ).new_page()
        page.goto(f"http://localhost:{port}/", timeout=15000)
        page.wait_for_load_state("domcontentloaded")

        result = page.evaluate(INJECT_JS, report_md)
        page.wait_for_timeout(2000)

        page.screenshot(
            path=str(output_dir / "real_output_full.png"),
            full_page=True,
        )

        # Viewport shots
        page.set_viewport_size({"width": 1200, "height": 900})
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.screenshot(
            path=str(output_dir / "real_output_top.png"),
            full_page=False,
        )

        browser.close()

    print(json.dumps(result))


if __name__ == "__main__":
    main()
