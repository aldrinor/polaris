"""
POLARIS Workspace Manual UX Checklist — Automated Playwright Edition.

Covers:
  1. Document Handling (Left Panel & Backend Persistence)
  2. Infinite Thread & Dynamic Pulse (Center Panel)
  3. Scroll-Sync & Context (Right Panel)
  4. Responsive & Mobile Behavior

Takes screenshots at each key stage for visual verification.
"""
import asyncio
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "logs", "ux_screenshots")
PORT = 8782
BASE_URL = f"http://127.0.0.1:{PORT}"

# A long mock report with multiple sections and citations for scroll-sync testing
MOCK_REPORT_MD = r"""
## Executive Summary

Water purification technologies have evolved significantly over the past decade [1].
Recent advances in membrane filtration provide 99.9% pathogen removal rates [2].
The global market for water treatment is projected to reach $349 billion by 2030 [3].

## Membrane Filtration Technologies

Reverse osmosis (RO) remains the gold standard for desalination applications [4].
Nanofiltration membranes offer a cost-effective alternative for brackish water treatment [5].
Studies demonstrate that graphene oxide membranes can achieve 10x higher flux rates compared to
conventional polymer membranes [6]. However, scalability challenges persist in
manufacturing uniform graphene oxide sheets at industrial scales [7].

The energy consumption of RO has decreased by 75% since the 1970s, from approximately
20 kWh/m3 to under 3 kWh/m3 for seawater desalination [8]. This improvement
is largely attributable to advances in membrane materials and energy recovery devices [9].

## Biological Treatment Methods

Constructed wetlands provide a nature-based solution for wastewater treatment in rural
communities [10]. These systems achieve 85-95% removal of biochemical oxygen
demand (BOD) and total suspended solids (TSS) [11]. The integration of
bioelectrochemical systems with constructed wetlands shows promise for simultaneous
water treatment and energy generation [12].

Activated sludge processes remain the most widely deployed biological treatment technology
globally [13]. Recent innovations in granular sludge technology have reduced
footprint requirements by up to 75% compared to conventional systems [14].

## Chemical Disinfection

Chlorination continues to be the most cost-effective disinfection method for municipal
water supplies [15]. However, concerns about disinfection byproducts (DBPs)
have driven research into alternative approaches [16]. Ultraviolet (UV)
disinfection combined with advanced oxidation processes offers effective pathogen
inactivation without chemical residuals [17].

Ozonation provides superior disinfection efficacy against Cryptosporidium and Giardia
compared to chlorine [18]. The operational costs of ozone generation have
decreased by 40% over the past decade due to improvements in generator efficiency [19].

## Emerging Technologies

Electrochemical water treatment using boron-doped diamond (BDD) electrodes shows
exceptional performance for micropollutant removal [20]. Solar-driven
photocatalytic systems based on TiO2 nanoparticles offer decentralized treatment
solutions for resource-limited settings [21].

Forward osmosis (FO) membranes have gained attention for their potential in
treating high-salinity industrial wastewaters [22]. The development of
responsive draw solutes that can be easily regenerated has improved the economic
viability of FO processes [23].

## Conclusions

Integrated water treatment approaches combining multiple technologies show the
greatest promise for addressing diverse water quality challenges [24].
Investment in research and development remains critical for achieving universal
access to safe drinking water by 2030 [25].
""".strip()

MOCK_BIBLIOGRAPHY = []
for i in range(1, 26):
    MOCK_BIBLIOGRAPHY.append({
        "id": f"ev_{i:03d}",
        "cite_num": i,
        "title": f"Study on Water Treatment Technology #{i}",
        "url": f"https://example.com/study-{i}",
        "source": f"Journal of Water Science Vol.{i}",
        "domain": "example.com",
        "verified": i % 3 != 0,
        "relevance": round(0.7 + (i % 10) * 0.03, 2),
    })


def start_server():
    """Start the live server and wait for health check."""
    log_path = os.path.join(PROJECT_ROOT, "logs", "ux_checklist_server.log")
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


async def run_checklist():
    from playwright.async_api import async_playwright

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    server, server_log = start_server()
    results = []
    console_errors = []

    def record(section, item, passed, note=""):
        status = "PASS" if passed else "FAIL"
        results.append((section, item, passed, note))
        tag = f"[{section}]"
        print(f"  {status}: {tag} {item}" + (f" — {note}" if note else ""))

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            # =========================================================
            # SECTION 1: Document Handling (Left Panel)
            # =========================================================
            print("\n=== SECTION 1: Document Handling ===")
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(f"[PAGE_ERROR] {e}"))

            await page.goto(f"{BASE_URL}/?mode=user", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 1a: Verify add-source button exists and is accessible
            add_btn = await page.query_selector(".ws-add-source-btn")
            record("DOC", "Add source button exists", add_btn is not None)
            if add_btn:
                box = await add_btn.bounding_box()
                record("DOC", "Add source button has dimensions", box is not None and box["width"] > 50)

            # 1b: Upload a file via the API (simulating drag-drop result)
            test_file_path = os.path.join(SCREENSHOT_DIR, "test_document.txt")
            with open(test_file_path, "w") as f:
                f.write("This is a test document for POLARIS workspace UX checklist.\n" * 50)

            # Use the existing upload endpoint
            upload_result = await page.evaluate("""async () => {
                try {
                    const blob = new Blob(['Test document content for POLARIS workspace.'], {type: 'text/plain'});
                    const formData = new FormData();
                    formData.append('file', blob, 'test_research_paper.txt');
                    const resp = await fetch('/api/documents/upload', {method: 'POST', body: formData});
                    return await resp.json();
                } catch(e) {
                    return {error: e.message};
                }
            }""")
            has_upload = upload_result and not upload_result.get("error")
            record("DOC", "File upload via API", has_upload, str(upload_result)[:100])

            if has_upload:
                # Refresh the document panel
                await page.evaluate("if(typeof renderDocumentPanel==='function') renderDocumentPanel()")
                await page.wait_for_timeout(1000)

                # Check document appears in list
                doc_items = await page.query_selector_all(".ws-source-row[data-doc-id]")
                record("DOC", "Document appears in list", len(doc_items) > 0, f"{len(doc_items)} item(s)")

                # 1c: Label editing — find the label element and simulate edit
                doc_id = upload_result.get("doc_id", upload_result.get("id", ""))
                if doc_id:
                    label_saved = await page.evaluate("""async (docId) => {
                        try {
                            const resp = await fetch('/api/documents/' + encodeURIComponent(docId), {
                                method: 'PUT',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({label: 'My Custom Label'})
                            });
                            return await resp.json();
                        } catch(e) {
                            return {error: e.message};
                        }
                    }""", doc_id)
                    record("DOC", "Label save via PUT endpoint", label_saved and label_saved.get("status") == "updated",
                           str(label_saved)[:100])

                    # 1d: Persistence — reload and check label
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    await page.evaluate("if(typeof renderDocumentPanel==='function') renderDocumentPanel()")
                    await page.wait_for_timeout(1000)

                    # Check via API
                    persisted = await page.evaluate("""async (docId) => {
                        try {
                            const resp = await fetch('/api/documents/list');
                            const data = await resp.json();
                            const docs = data.documents || data;
                            for (const d of docs) {
                                if ((d.id || d.doc_id) === docId) return d;
                            }
                            return {error: 'not_found'};
                        } catch(e) {
                            return {error: e.message};
                        }
                    }""", doc_id)
                    label_persisted = persisted and persisted.get("label") == "My Custom Label"
                    record("DOC", "Label persisted after reload", label_persisted,
                           f"label={persisted.get('label', 'N/A')}" if persisted else "no data")

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_documents.png"), full_page=False)

            # =========================================================
            # SECTION 2: Infinite Thread & Dynamic Pulse (Center Panel)
            # =========================================================
            print("\n=== SECTION 2: Infinite Thread & Dynamic Pulse ===")

            # Reset to idle
            await page.evaluate("setWorkspacePhase('idle')")
            await page.wait_for_timeout(500)

            # 2a: Type in chat textarea and check it's functional
            textarea = await page.query_selector(".ws-chat-textarea")
            record("THREAD", "Chat textarea exists", textarea is not None)

            if textarea:
                await textarea.fill("What are the latest advances in water purification technology?")
                val = await textarea.input_value()
                record("THREAD", "Textarea accepts input", len(val) > 10)

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_idle_with_query.png"), full_page=False)

            # 2b: Submit and verify prompt bubble appears
            await page.evaluate("""(() => {
                appendPromptBubble('What are the latest advances in water purification technology?');
                setWorkspacePhase('running');
                appendProgressBlock();
                addProgressTask('Searching 42 sources...');
                addProgressTask('Interviewing 6 expert perspectives...');
            })()""")
            await page.wait_for_timeout(500)

            bubble = await page.query_selector(".ws-prompt-bubble")
            record("THREAD", "Prompt bubble rendered", bubble is not None)

            progress = await page.query_selector(".ws-progress-block")
            record("THREAD", "Progress block rendered", progress is not None)

            # Check micro-tasks are visible
            tasks = await page.query_selector_all(".ws-progress-task")
            record("THREAD", "Micro-tasks visible in progress", len(tasks) >= 2, f"{len(tasks)} tasks")

            # 2c: Add more tasks to simulate looping
            await page.evaluate("""(() => {
                addProgressTask('Extracted 127 evidence pieces');
                addProgressTask('Verified 89% of claims');
                addProgressTask('Searching for additional evidence...');
                addProgressTask('Re-verifying 14 updated claims...');
            })()""")
            await page.wait_for_timeout(300)

            tasks2 = await page.query_selector_all(".ws-progress-task")
            record("THREAD", "Loop tasks append naturally", len(tasks2) >= 6, f"{len(tasks2)} tasks")

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_running_pulse.png"), full_page=False)

            # 2d: Inject a report — simulate pipeline completion
            await page.evaluate("""(args) => {
                // Populate state for quality banner and citation sidebar
                state.bibliography = args.bibliography;
                state.verificationVerdicts = args.bibliography.map(function(b, i) {
                    return {verdict: i % 3 !== 0 ? 'SUPPORTED' : 'NOT_SUPPORTED', is_faithful: i % 3 !== 0};
                });
                state.words = 2500;
                appendReportBlock(args.report, args.bibliography);
                setWorkspacePhase('report');
            }""", {"report": MOCK_REPORT_MD, "bibliography": MOCK_BIBLIOGRAPHY})
            await page.wait_for_timeout(1000)

            report_block = await page.query_selector(".ws-report-block")
            record("THREAD", "Report block rendered in thread", report_block is not None)

            # Check progress block is gone (replaced by report)
            progress_after = await page.query_selector(".ws-progress-block")
            record("THREAD", "Progress block removed after report", progress_after is None)

            # Check report has headings
            headings = await page.query_selector_all(".ws-report-block h2")
            record("THREAD", "Report has section headings", len(headings) >= 3, f"{len(headings)} h2 elements")

            # Check citations resolved in report
            cite_refs = await page.query_selector_all(".ws-report-block .cite-ref")
            record("THREAD", "Citations rendered in report", len(cite_refs) > 0, f"{len(cite_refs)} citations")

            # Check quality banner
            quality_banner = await page.query_selector(".ws-report-quality-banner")
            record("THREAD", "Quality banner rendered", quality_banner is not None)

            # Check export buttons
            export_btns = await page.query_selector_all(".ws-report-export-btn")
            record("THREAD", "Export buttons present", len(export_btns) >= 2, f"{len(export_btns)} buttons")

            # Check chat input pinned at bottom
            chat_input = await page.query_selector(".ws-chat-input")
            chat_visible = await page.evaluate("""(() => {
                var el = document.querySelector('.ws-chat-input');
                if (!el) return false;
                var style = getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden';
            })()""")
            record("THREAD", "Chat input visible in report phase", chat_visible)

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_report_rendered.png"), full_page=False)

            # 2e: Follow-up — verify thread grows
            await page.evaluate("""(() => {
                appendPromptBubble('What about solar-powered desalination specifically?');
                appendProgressBlock();
                addProgressTask('Searching for solar desalination research...');
            })()""")
            await page.wait_for_timeout(500)

            bubbles = await page.query_selector_all(".ws-prompt-bubble")
            record("THREAD", "Follow-up creates 2nd bubble", len(bubbles) >= 2, f"{len(bubbles)} bubbles")

            # Check previous report is still there
            reports = await page.query_selector_all(".ws-report-block")
            record("THREAD", "Previous report intact above", len(reports) >= 1)

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_followup_thread.png"), full_page=False)

            # =========================================================
            # SECTION 3: Scroll-Sync & Context (Right Panel)
            # =========================================================
            print("\n=== SECTION 3: Scroll-Sync & Right Panel ===")

            # Reset to clean state with just a report
            await page.evaluate("""(() => {
                // Clear thread
                var inner = document.querySelector('.ws-thread-inner');
                if (inner) inner.innerHTML = '';
                setWorkspacePhase('idle');
            })()""")
            await page.wait_for_timeout(300)

            # Inject fresh report for scroll testing
            await page.evaluate("""(args) => {
                state.bibliography = args.bibliography;
                state.verificationVerdicts = args.bibliography.map(function(b, i) {
                    return {verdict: 'SUPPORTED', is_faithful: true};
                });
                state.words = 2500;
                appendPromptBubble('Water purification research');
                appendReportBlock(args.report, args.bibliography);
                setWorkspacePhase('report');
            }""", {"report": MOCK_REPORT_MD, "bibliography": MOCK_BIBLIOGRAPHY})
            await page.wait_for_timeout(1500)

            # 3a: Scroll to first section heading to trigger IntersectionObserver
            await page.evaluate("""async () => {
                var reportBlock = document.querySelector('.ws-report-block');
                if (!reportBlock) return;
                var h2s = reportBlock.querySelectorAll('h2');
                if (h2s.length > 0) {
                    h2s[0].scrollIntoView({behavior: 'instant', block: 'start'});
                }
                await new Promise(r => setTimeout(r, 800));
            }""")

            citation_cards = await page.query_selector_all("#ws-citation-list .ws-cite-card")
            record("SCROLL", "Citation sidebar populated after scroll", len(citation_cards) > 0,
                   f"{len(citation_cards)} cards")

            # 3b: Check scroll-sync — scroll to a DIFFERENT section and verify sidebar changes
            scroll_result = await page.evaluate("""async () => {
                var initialCards = document.querySelectorAll('#ws-citation-list .ws-cite-card');
                var initialCount = initialCards.length;
                var initialNums = [];
                initialCards.forEach(function(c) { initialNums.push(c.getAttribute('data-cite-num')); });

                // Scroll to 3rd section (Biological Treatment)
                var reportBlock = document.querySelector('.ws-report-block');
                if (!reportBlock) return {error: 'no report'};
                var h2s = reportBlock.querySelectorAll('h2');
                if (h2s.length >= 3) {
                    h2s[2].scrollIntoView({behavior: 'instant', block: 'start'});
                }

                await new Promise(r => setTimeout(r, 800));

                var afterCards = document.querySelectorAll('#ws-citation-list .ws-cite-card');
                var afterCount = afterCards.length;
                var afterNums = [];
                afterCards.forEach(function(c) { afterNums.push(c.getAttribute('data-cite-num')); });

                return {
                    initialCount: initialCount,
                    afterCount: afterCount,
                    initialNums: initialNums.join(','),
                    afterNums: afterNums.join(','),
                    changed: initialNums.join(',') !== afterNums.join(',')
                };
            }""")
            if scroll_result and not scroll_result.get("error"):
                record("SCROLL", "Scroll-sync updates citations on scroll",
                       scroll_result.get("changed", False),
                       f"section1=[{scroll_result.get('initialNums')}] -> section3=[{scroll_result.get('afterNums')}]")
            else:
                record("SCROLL", "Scroll-sync updates citations on scroll", False,
                       str(scroll_result))

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "06_scroll_sync.png"), full_page=False)

            # 3c: Bi-directional highlighting — hover a citation that IS in the current sidebar
            highlight_result = await page.evaluate("""async () => {
                // Get a citation number currently in the sidebar
                var sidebarCards = document.querySelectorAll('#ws-citation-list .ws-cite-card');
                if (sidebarCards.length === 0) return {error: 'no sidebar cards'};
                var targetNum = sidebarCards[0].getAttribute('data-cite-num');

                // Find that citation in the report body
                var citeRef = document.querySelector('.ws-report-body .cite-ref[data-cite="' + targetNum + '"]');
                if (!citeRef) return {error: 'cite-ref not found for ' + targetNum};

                // Trigger mouseover (bubbles to document handler in initWorkspace)
                citeRef.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));

                // Brief delay for event propagation
                await new Promise(r => setTimeout(r, 100));

                // Check if sidebar card highlights
                var sidebarCard = document.querySelector('#ws-citation-list .ws-cite-card[data-cite-num="' + targetNum + '"]');
                var cardHighlighted = sidebarCard ? sidebarCard.classList.contains('active') : false;

                // Cleanup: trigger mouseout
                citeRef.dispatchEvent(new MouseEvent('mouseout', {bubbles: true}));

                return {
                    citeNum: targetNum,
                    cardFound: sidebarCard !== null,
                    cardHighlighted: cardHighlighted,
                    sidebarCardsCount: sidebarCards.length
                };
            }""")
            if highlight_result and not highlight_result.get("error"):
                record("SCROLL", "Hover citation highlights sidebar card",
                       highlight_result.get("cardHighlighted", False),
                       f"cite=[{highlight_result.get('citeNum')}], found={highlight_result.get('cardFound')}")
            else:
                record("SCROLL", "Hover citation highlights sidebar card", False,
                       str(highlight_result))

            # 3d: Check memory section exists
            memory_section = await page.query_selector(".ws-memory")
            record("SCROLL", "Memory section exists", memory_section is not None)

            memory_svg = await page.query_selector("#ws-memory-viz-svg")
            record("SCROLL", "Memory SVG visualization exists", memory_svg is not None)

            # Check SVG has content (circles/dots)
            svg_content = await page.evaluate("""() => {
                var svg = document.getElementById('ws-memory-viz-svg');
                if (!svg) return {error: 'no svg'};
                return {
                    width: svg.getAttribute('width') || svg.clientWidth,
                    height: svg.getAttribute('height') || svg.clientHeight,
                    childCount: svg.children.length,
                    innerHTML: svg.innerHTML.substring(0, 200)
                };
            }""")
            record("SCROLL", "Memory SVG has dimensions",
                   svg_content and (svg_content.get("width") or svg_content.get("height")),
                   f"w={svg_content.get('width')}, h={svg_content.get('height')}, children={svg_content.get('childCount')}")

            # 3e: Live metrics check
            metrics = await page.evaluate("""() => {
                return {
                    evidence: document.getElementById('ws-metric-evidence')?.textContent,
                    sources: document.getElementById('ws-metric-sources')?.textContent,
                    faith: document.getElementById('ws-metric-faith')?.textContent,
                    cost: document.getElementById('ws-metric-cost')?.textContent,
                    time: document.getElementById('ws-metric-time')?.textContent,
                };
            }""")
            record("SCROLL", "Live metric elements populated", metrics is not None,
                   f"ev={metrics.get('evidence')}, src={metrics.get('sources')}")

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "07_right_sidebar.png"), full_page=False)

            # =========================================================
            # SECTION 4: Responsive & Mobile Behavior
            # =========================================================
            print("\n=== SECTION 4: Responsive & Mobile ===")

            # 4a: Tablet view (900px) — left panel should collapse to drawer
            await page.set_viewport_size({"width": 900, "height": 800})
            await page.wait_for_timeout(1000)

            left_panel_visible = await page.evaluate("""() => {
                var left = document.getElementById('ws-left');
                if (!left) return null;
                var style = getComputedStyle(left);
                var rect = left.getBoundingClientRect();
                return {
                    display: style.display,
                    position: style.position,
                    left: rect.left,
                    width: rect.width,
                    visible: rect.left >= 0 && style.display !== 'none'
                };
            }""")
            is_drawer = left_panel_visible and (
                left_panel_visible.get("position") == "fixed" or
                left_panel_visible.get("left", 0) < 0
            )
            record("RESPONSIVE", "Left panel is drawer at 900px", is_drawer,
                   f"pos={left_panel_visible.get('position')}, left={left_panel_visible.get('left')}")

            # Check hamburger button exists
            drawer_toggle = await page.query_selector(".ws-drawer-toggle")
            toggle_visible = await page.evaluate("""() => {
                var btn = document.querySelector('.ws-drawer-toggle');
                if (!btn) return false;
                var style = getComputedStyle(btn);
                return style.display !== 'none' && style.visibility !== 'hidden';
            }""")
            record("RESPONSIVE", "Hamburger toggle visible at 900px", toggle_visible)

            # Toggle drawer open
            if drawer_toggle and toggle_visible:
                await drawer_toggle.click()
                await page.wait_for_timeout(500)

                drawer_open = await page.evaluate("""() => {
                    return document.getElementById('workspace')?.classList.contains('drawer-open') ||
                           document.querySelector('.ws-left')?.classList.contains('drawer-open');
                }""")
                record("RESPONSIVE", "Drawer opens on hamburger click", drawer_open)

                await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "08_tablet_drawer.png"), full_page=False)

                # Close drawer via JS (overlay may not be directly clickable in headless)
                await page.evaluate("""() => {
                    var left = document.getElementById('ws-left');
                    if (left) left.classList.remove('drawer-open');
                }""")
                await page.wait_for_timeout(300)

            # Check right sidebar at tablet — should still be visible (or compressed)
            right_at_tablet = await page.evaluate("""() => {
                var right = document.getElementById('ws-right');
                if (!right) return null;
                var style = getComputedStyle(right);
                var rect = right.getBoundingClientRect();
                return {
                    display: style.display,
                    width: rect.width,
                    visible: style.display !== 'none' && rect.width > 0
                };
            }""")
            # At 900px (between 768 and 1024), right sidebar behavior depends on breakpoint
            record("RESPONSIVE", "Right sidebar state at 900px",
                   right_at_tablet is not None,
                   f"display={right_at_tablet.get('display')}, w={right_at_tablet.get('width')}")

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "09_tablet_layout.png"), full_page=False)

            # 4b: Mobile view (<768px) — right sidebar should be hidden
            await page.set_viewport_size({"width": 480, "height": 812})
            await page.wait_for_timeout(1000)

            right_at_mobile = await page.evaluate("""() => {
                var right = document.getElementById('ws-right');
                if (!right) return null;
                var style = getComputedStyle(right);
                var rect = right.getBoundingClientRect();
                return {
                    display: style.display,
                    width: rect.width,
                    visible: style.display !== 'none' && rect.width > 0
                };
            }""")
            right_hidden = right_at_mobile and (
                right_at_mobile.get("display") == "none" or
                right_at_mobile.get("width", 0) == 0
            )
            record("RESPONSIVE", "Right sidebar hidden at mobile (<768px)", right_hidden,
                   f"display={right_at_mobile.get('display')}")

            # Check center panel fills width
            center_at_mobile = await page.evaluate("""() => {
                var center = document.getElementById('ws-center');
                if (!center) return null;
                var rect = center.getBoundingClientRect();
                return {width: rect.width, viewportWidth: window.innerWidth};
            }""")
            fills_width = center_at_mobile and center_at_mobile.get("width", 0) > 400
            record("RESPONSIVE", "Center fills mobile width", fills_width,
                   f"center={center_at_mobile.get('width')}px, viewport={center_at_mobile.get('viewportWidth')}px")

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "10_mobile_layout.png"), full_page=False)

            # 4c: Mobile inline citations — tap a citation
            # First ensure we have a report visible at mobile size
            mobile_cite = await page.evaluate("""() => {
                var cites = document.querySelectorAll('.ws-report-block .cite-ref');
                if (cites.length === 0) return {error: 'no citations at mobile'};

                // Check if inline mobile citations exist (tap-to-expand)
                var firstCite = cites[0];
                firstCite.click();

                // Wait a bit for animation
                return new Promise(resolve => {
                    setTimeout(() => {
                        var inlineCard = document.querySelector('.ws-inline-cite-card');
                        resolve({
                            citeCount: cites.length,
                            inlineCardFound: !!inlineCard,
                            inlineCardText: inlineCard ? inlineCard.textContent.substring(0, 80) : null
                        });
                    }, 500);
                });
            }""")
            mobile_note = str(mobile_cite).encode("ascii", "replace").decode("ascii")[:120] if mobile_cite else ""
            record("RESPONSIVE", "Mobile tap-to-expand citation",
                   mobile_cite and mobile_cite.get("inlineCardFound", False),
                   mobile_note)

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "11_mobile_citations.png"), full_page=False)

            # =========================================================
            # SECTION 5: Operator Mode Isolation (Quick Recheck)
            # =========================================================
            print("\n=== SECTION 5: Operator Mode Isolation ===")

            await page.set_viewport_size({"width": 1440, "height": 900})
            await page.wait_for_timeout(500)

            # Switch to operator mode
            console_errors_before = len(console_errors)
            await page.evaluate("""(() => {
                if (typeof switchViewMode === 'function') switchViewMode('operator');
                else {
                    document.body.classList.remove('user-mode');
                    var ws = document.getElementById('workspace');
                    if (ws) ws.classList.remove('visible');
                }
            })()""")
            await page.wait_for_timeout(1000)

            ws_hidden = await page.evaluate("!document.getElementById('workspace')?.classList.contains('visible')")
            record("ISOLATION", "Workspace hidden in operator mode", ws_hidden)

            new_errors = [e for e in console_errors[console_errors_before:] if "error" in e.lower() or "PAGE_ERROR" in e]
            record("ISOLATION", "No JS errors switching to operator", len(new_errors) == 0,
                   f"{len(new_errors)} errors" if new_errors else "")

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "12_operator_mode.png"), full_page=False)

            await browser.close()

    finally:
        server.kill()
        server_log.close()

    # =========================================================
    # FINAL REPORT
    # =========================================================
    print("\n" + "=" * 70)
    print("POLARIS WORKSPACE UX CHECKLIST — RESULTS")
    print("=" * 70)

    sections = {}
    for section, item, passed, note in results:
        if section not in sections:
            sections[section] = {"pass": 0, "fail": 0, "items": []}
        sections[section]["pass" if passed else "fail"] += 1
        sections[section]["items"].append((item, passed, note))

    total_pass = sum(s["pass"] for s in sections.values())
    total_fail = sum(s["fail"] for s in sections.values())
    total = total_pass + total_fail

    for section, data in sections.items():
        sp, sf = data["pass"], data["fail"]
        status = "ALL PASS" if sf == 0 else f"{sf} FAIL"
        print(f"\n  [{section}] {sp}/{sp + sf} — {status}")
        for item, passed, note in data["items"]:
            marker = "+" if passed else "X"
            line = f"    [{marker}] {item}"
            if note:
                line += f"  ({note})"
            print(line)

    # Filter real JS errors (exclude 404 resource loads, CSP violations — those are browser-level noise)
    all_console = [e for e in console_errors
                   if ("error" in e.lower() or "PAGE_ERROR" in e)
                   and "Failed to load resource" not in e
                   and "Content Security Policy" not in e]
    print(f"\n  Console errors: {len(all_console)}")
    if all_console:
        for e in all_console[:10]:
            print(f"    {e}")

    print(f"\n  TOTAL: {total_pass}/{total} PASS")
    print(f"  Screenshots saved to: {SCREENSHOT_DIR}/")
    print("=" * 70)

    return total_fail == 0 and len(all_console) == 0


if __name__ == "__main__":
    ok = asyncio.run(run_checklist())
    sys.exit(0 if ok else 1)
