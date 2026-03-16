"""
Playwright automated audit of POLARIS pipeline HTML dashboard.

Headless browser audit that validates all 10 dashboard sections
are populated, reasoning content is present, and no placeholder
text remains.

15 checks:
  1. Dashboard loads
  2. All 10 sections exist
  3. Pipeline overview has duration
  4. Planning reasoning non-empty
  5. Search results table populated
  6. Fetch table populated
  7. STORM transcripts present
  8. STORM Q&A content
  9. Evidence funnel numbers
  10. Verification reasoning present
  11. Iteration decisions present
  12. Synthesis reasoning present
  13. Quality gates table
  14. LLM call log complete
  15. No placeholder text

Output:
  - Screenshots: outputs/dashboard_audit/  (full page + per-section)
  - JSON report: outputs/dashboard_audit/audit_report.json
  - Exit code: 0 if all pass, 1 if any fail

CLI: python scripts/playwright_audit.py \
       --html outputs/dashboard_V001.html \
       --output outputs/dashboard_audit/
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _check_playwright_installed() -> bool:
    """Check if playwright and chromium are available."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


def run_audit(html_path: str, output_dir: str) -> dict:
    """Run all 15 audit checks against the HTML dashboard.

    Args:
        html_path: Path to the HTML dashboard file.
        output_dir: Directory for screenshots and report.

    Returns:
        Audit report dict with pass/fail per check.
    """
    from playwright.sync_api import sync_playwright

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    screenshots_dir = output / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    # Convert to file:// URL
    abs_path = Path(html_path).resolve()
    if not abs_path.exists():
        print(f"ERROR: HTML file not found: {abs_path}")
        sys.exit(1)

    file_url = abs_path.as_uri()
    print(f"Auditing: {file_url}")

    results = []

    def _check(check_num: int, name: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        icon = "[+]" if passed else "[-]"
        results.append({
            "check": check_num,
            "name": name,
            "passed": passed,
            "detail": detail,
        })
        print(f"  {icon} Check {check_num:2d}: {name} — {status}"
              + (f" ({detail})" if detail else ""))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Navigate to dashboard
        page.goto(file_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # -- Check 1: Dashboard loads --
        title = page.title()
        _check(1, "Dashboard loads", bool(title), f"title='{title}'")

        # -- Check 2: All 10 sections exist --
        sections = page.query_selector_all("section[id]")
        section_count = len(sections)
        _check(2, "All 10 sections exist", section_count >= 10,
               f"found {section_count} sections")

        # Take full-page screenshot
        page.screenshot(path=str(screenshots_dir / "full_page.png"), full_page=True)

        # Expand all details for content checks
        page.evaluate("""
            document.querySelectorAll('details').forEach(d => d.open = true);
        """)
        page.wait_for_timeout(300)

        # -- Check 3: Pipeline overview has duration --
        overview = page.query_selector("#overview")
        overview_text = overview.inner_text() if overview else ""
        has_duration = any(
            unit in overview_text for unit in ["ms", "min", "s"]
        )
        _check(3, "Pipeline overview has duration", has_duration,
               f"overview text length={len(overview_text)}")

        # -- Check 4: Planning reasoning non-empty --
        planning = page.query_selector("#planning")
        planning_pres = planning.query_selector_all("pre") if planning else []
        plan_reasoning_found = False
        for pre in planning_pres:
            text = pre.inner_text()
            if len(text) > 100:
                plan_reasoning_found = True
                break
        _check(4, "Planning reasoning non-empty", plan_reasoning_found,
               f"{len(planning_pres)} pre blocks")

        # -- Check 5: Search results table populated --
        search_table = page.query_selector("#search")
        search_rows = 0
        if search_table:
            search_rows = len(search_table.query_selector_all("tbody tr"))
        _check(5, "Search results table populated", search_rows > 1,
               f"{search_rows} rows")

        # -- Check 6: Fetch table populated --
        fetch_table = page.query_selector("#fetch")
        fetch_rows = 0
        if fetch_table:
            fetch_rows = len(fetch_table.query_selector_all("tbody tr"))
        _check(6, "Fetch table populated", fetch_rows > 1,
               f"{fetch_rows} rows")

        # -- Check 7: STORM transcripts present --
        storm_rounds = page.query_selector_all(".storm-round")
        _check(7, "STORM transcripts present", len(storm_rounds) > 0,
               f"{len(storm_rounds)} rounds")

        # -- Check 8: STORM Q&A content --
        storm_qa_valid = True
        storm_qa_detail = ""
        if storm_rounds:
            for i, round_el in enumerate(storm_rounds[:5]):
                q_el = round_el.query_selector(".storm-q")
                a_el = round_el.query_selector(".storm-a")
                q_text = q_el.inner_text() if q_el else ""
                a_text = a_el.inner_text() if a_el else ""
                if not q_text.strip() or not a_text.strip():
                    storm_qa_valid = False
                    storm_qa_detail = f"round {i}: q={len(q_text)} a={len(a_text)}"
                    break
        else:
            storm_qa_valid = False
            storm_qa_detail = "no rounds"
        _check(8, "STORM Q&A content", storm_qa_valid, storm_qa_detail)

        # -- Check 9: Evidence funnel numbers --
        evidence_section = page.query_selector("#evidence")
        funnel_fills = (
            evidence_section.query_selector_all(".funnel-fill")
            if evidence_section else []
        )
        funnel_valid = False
        funnel_detail = f"{len(funnel_fills)} bars"
        for fill in funnel_fills:
            text = fill.inner_text().strip().replace(",", "")
            if text.isdigit() and int(text) > 0:
                funnel_valid = True
                break
        _check(9, "Evidence funnel numbers", funnel_valid, funnel_detail)

        # -- Check 10: Verification reasoning present --
        verify_section = page.query_selector("#verification")
        verify_pres = (
            verify_section.query_selector_all("pre") if verify_section else []
        )
        verify_found = False
        for pre in verify_pres:
            if len(pre.inner_text()) > 50:
                verify_found = True
                break
        _check(10, "Verification reasoning present", verify_found,
               f"{len(verify_pres)} pre blocks")

        # -- Check 11: Iteration decisions present --
        iter_cards = page.query_selector_all(".iteration-card")
        _check(11, "Iteration decisions present", len(iter_cards) > 0,
               f"{len(iter_cards)} cards")

        # -- Check 12: Synthesis reasoning present --
        synth_section = page.query_selector("#synthesis")
        synth_cards = (
            synth_section.query_selector_all(".card") if synth_section else []
        )
        _check(12, "Synthesis reasoning present", len(synth_cards) > 0,
               f"{len(synth_cards)} cards")

        # -- Check 13: Quality gates table --
        qg_section = page.query_selector("#quality-gates")
        qg_rows = 0
        if qg_section:
            qg_table = qg_section.query_selector("table")
            if qg_table:
                qg_rows = len(qg_table.query_selector_all("tbody tr"))
        _check(13, "Quality gates table", qg_rows >= 1,
               f"{qg_rows} rows")

        # -- Check 14: LLM call log complete --
        llm_section = page.query_selector("#llm-calls")
        llm_rows = 0
        if llm_section:
            llm_table = llm_section.query_selector("table")
            if llm_table:
                llm_rows = len(llm_table.query_selector_all("tbody tr"))
        _check(14, "LLM call log complete", llm_rows >= 10,
               f"{llm_rows} rows")

        # -- Check 15: No placeholder text --
        body_text = page.inner_text("body").lower()
        forbidden = ["todo", "placeholder", "coming soon"]
        found_placeholders = [
            word for word in forbidden if word in body_text
        ]
        _check(15, "No placeholder text", len(found_placeholders) == 0,
               f"found: {found_placeholders}" if found_placeholders else "clean")

        # Take per-section screenshots
        section_ids = [
            "overview", "planning", "search-fetch", "storm", "evidence",
            "verification", "iterations", "synthesis", "quality-gates", "llm-calls",
        ]
        for sid in section_ids:
            section_el = page.query_selector(f"#{sid}")
            if section_el:
                try:
                    section_el.screenshot(
                        path=str(screenshots_dir / f"section_{sid}.png"),
                    )
                except Exception:
                    pass  # Section may be too small or hidden

        # Take expanded full-page screenshot
        page.screenshot(
            path=str(screenshots_dir / "full_page_expanded.png"),
            full_page=True,
        )

        browser.close()

    # Build report
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    report = {
        "html_path": str(abs_path),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "all_passed": passed == total,
        },
        "checks": results,
    }

    report_path = output / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Report: {report_path}")
    print(f"  Screenshots: {screenshots_dir}")
    print(f"  Result: {passed}/{total} passed"
          + (" — ALL PASS" if passed == total else " — FAILURES DETECTED"))

    return report


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Automated Playwright audit of POLARIS HTML dashboard.",
    )
    parser.add_argument(
        "--html",
        required=True,
        help="Path to the HTML dashboard file",
    )
    parser.add_argument(
        "--output",
        default="outputs/dashboard_audit",
        help="Output directory for screenshots and report (default: outputs/dashboard_audit)",
    )
    args = parser.parse_args()

    if not _check_playwright_installed():
        print("ERROR: playwright not installed.")
        print("  Install with: pip install playwright && python -m playwright install chromium")
        sys.exit(1)

    report = run_audit(args.html, args.output)
    sys.exit(0 if report["summary"]["all_passed"] else 1)


if __name__ == "__main__":
    main()
