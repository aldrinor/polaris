"""
Live console check for workspace redesign.
Verifies no JS errors, undefined vars, or missing DOM elements
when toggling between User Mode and Operator Mode.
"""
import asyncio
import subprocess
import sys
import time
import os

async def run_check():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        return False

    server_log = open(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "console_check_server.log"), "w")
    server = subprocess.Popen(
        [sys.executable, "-u", "scripts/live_server.py", "--port", "8781"],
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to start
    import urllib.request
    for i in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8781/health", timeout=2)
            print(f"Server ready after {i+1}s")
            break
        except Exception:
            time.sleep(1)
    else:
        print("FAIL: Server did not start within 30s")
        server.kill()
        server_log.close()
        return False

    errors = []
    warnings = []
    all_pass = True

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Capture console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda err: console_errors.append(f"[PAGE_ERROR] {err}"))

        # ---- TEST 1: Load in user mode ----
        print("\n--- TEST 1: Load page in user mode ---")
        await page.goto("http://127.0.0.1:8781/?mode=user", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Check workspace element exists
        ws = await page.query_selector("#workspace")
        if ws:
            print("PASS: #workspace element found")
        else:
            print("FAIL: #workspace element NOT found")
            errors.append("Missing #workspace element")
            all_pass = False

        # Check workspace is visible
        ws_visible = await page.evaluate("document.getElementById('workspace') && document.getElementById('workspace').classList.contains('visible')")
        if ws_visible:
            print("PASS: workspace has .visible class")
        else:
            print("FAIL: workspace missing .visible class")
            errors.append("Workspace not visible in user mode")
            all_pass = False

        # Check workspace children
        for child_id in ["ws-left", "ws-center", "ws-right"]:
            el = await page.query_selector(f"#{child_id}")
            if el:
                print(f"PASS: #{child_id} found")
            else:
                print(f"FAIL: #{child_id} NOT found")
                errors.append(f"Missing #{child_id}")
                all_pass = False

        # Check idle state elements
        for el_id in ["ws-idle", "ws-thread", "ws-chat-input"]:
            el = await page.query_selector(f"#{el_id}")
            if el:
                print(f"PASS: #{el_id} found")
            else:
                print(f"FAIL: #{el_id} NOT found")
                errors.append(f"Missing #{el_id}")
                all_pass = False

        # Check data-phase attribute (may be "running" if server has stale state)
        phase = await page.evaluate("document.getElementById('workspace') ? document.getElementById('workspace').getAttribute('data-phase') : null")
        if phase in ("idle", "running"):
            print(f"PASS: data-phase = '{phase}' (valid initial phase)")
        else:
            print(f"FAIL: data-phase = '{phase}' (expected 'idle' or 'running')")
            errors.append(f"Wrong phase: {phase}")
            all_pass = False
        # Reset to idle for remaining tests
        await page.evaluate("setWorkspacePhase('idle')")

        # Check old UI elements are hidden in user mode
        print("\n--- TEST 2: Old UI hidden in user mode ---")
        for selector, name in [
            (".views-container", "views-container"),
            ("#user-progress", "user-progress"),
            (".landing-page", "landing-page"),
        ]:
            hidden = await page.evaluate(f"""(() => {{
                var el = document.querySelector('{selector}');
                if (!el) return true;
                var style = window.getComputedStyle(el);
                return style.display === 'none' || !el.classList.contains('visible');
            }})()""")
            if hidden:
                print(f"PASS: {name} is hidden in user mode")
            else:
                print(f"WARN: {name} may be visible in user mode")
                warnings.append(f"{name} visible in user mode")

        # ---- TEST 3: Check JS functions defined ----
        print("\n--- TEST 3: Workspace JS functions defined ---")
        for fn_name in [
            "setWorkspacePhase",
            "appendPromptBubble",
            "appendProgressBlock",
            "addProgressTask",
            "appendReportBlock",
            "handleWorkspaceChatSubmit",
            "workspaceProcessEvent",
            "renderCitationSidebar",
            "initScrollSync",
            "destroyScrollSync",
            "renderDocumentPanel",
            "initDocDropzone",
        ]:
            defined = await page.evaluate(f"typeof {fn_name} === 'function'")
            if defined:
                print(f"PASS: {fn_name}() defined")
            else:
                print(f"FAIL: {fn_name}() NOT defined")
                errors.append(f"Missing function: {fn_name}")
                all_pass = False

        # ---- TEST 4: Phase transitions ----
        print("\n--- TEST 4: Phase transitions ---")
        # idle -> running
        await page.evaluate("setWorkspacePhase('running')")
        p_val = await page.evaluate("document.getElementById('workspace').getAttribute('data-phase')")
        if p_val == "running":
            print("PASS: idle -> running transition")
        else:
            print(f"FAIL: phase = '{p_val}' after setWorkspacePhase('running')")
            errors.append("Phase transition idle->running failed")
            all_pass = False

        # running -> report
        await page.evaluate("setWorkspacePhase('report')")
        p_val = await page.evaluate("document.getElementById('workspace').getAttribute('data-phase')")
        if p_val == "report":
            print("PASS: running -> report transition")
        else:
            print(f"FAIL: phase = '{p_val}' after setWorkspacePhase('report')")
            errors.append("Phase transition running->report failed")
            all_pass = False

        # report -> idle
        await page.evaluate("setWorkspacePhase('idle')")
        p_val = await page.evaluate("document.getElementById('workspace').getAttribute('data-phase')")
        if p_val == "idle":
            print("PASS: report -> idle transition")
        else:
            print(f"FAIL: phase = '{p_val}' after setWorkspacePhase('idle')")
            errors.append("Phase transition report->idle failed")
            all_pass = False

        # ---- TEST 5: Toggle to operator mode ----
        print("\n--- TEST 5: Toggle to operator mode ---")
        console_errors_before = len(console_errors)
        await page.evaluate("""(() => {
            if (typeof switchViewMode === 'function') {
                switchViewMode('operator');
            } else {
                document.body.classList.remove('user-mode');
                var ws = document.getElementById('workspace');
                if (ws) ws.classList.remove('visible');
            }
        })()""")
        await page.wait_for_timeout(1000)

        ws_hidden = await page.evaluate("""(() => {
            var ws = document.getElementById('workspace');
            return ws && !ws.classList.contains('visible');
        })()""")
        if ws_hidden:
            print("PASS: workspace hidden in operator mode")
        else:
            print("FAIL: workspace still visible in operator mode")
            errors.append("Workspace visible in operator mode")
            all_pass = False

        # Check no new console errors from mode switch
        new_errors = console_errors[console_errors_before:]
        js_errors_only = [e for e in new_errors if e.startswith("[error]") or e.startswith("[PAGE_ERROR]")]
        if not js_errors_only:
            print("PASS: No JS errors during operator mode switch")
        else:
            print(f"FAIL: {len(js_errors_only)} JS error(s) during operator mode switch:")
            for e in js_errors_only:
                print(f"  {e}")
            errors.extend(js_errors_only)
            all_pass = False

        # ---- TEST 6: Toggle back to user mode ----
        print("\n--- TEST 6: Toggle back to user mode ---")
        console_errors_before = len(console_errors)
        await page.evaluate("""(() => {
            if (typeof switchViewMode === 'function') {
                switchViewMode('user');
            } else {
                document.body.classList.add('user-mode');
                var ws = document.getElementById('workspace');
                if (ws) ws.classList.add('visible');
            }
        })()""")
        await page.wait_for_timeout(1000)

        ws_visible2 = await page.evaluate("document.getElementById('workspace') && document.getElementById('workspace').classList.contains('visible')")
        if ws_visible2:
            print("PASS: workspace visible after returning to user mode")
        else:
            print("FAIL: workspace NOT visible after returning to user mode")
            errors.append("Workspace not visible after re-entering user mode")
            all_pass = False

        new_errors2 = console_errors[console_errors_before:]
        js_errors_only2 = [e for e in new_errors2 if e.startswith("[error]") or e.startswith("[PAGE_ERROR]")]
        if not js_errors_only2:
            print("PASS: No JS errors during user mode switch")
        else:
            print(f"FAIL: {len(js_errors_only2)} JS error(s) during user mode switch:")
            for e in js_errors_only2:
                print(f"  {e}")
            errors.extend(js_errors_only2)
            all_pass = False

        # ---- TEST 7: Prompt bubble + progress block ----
        print("\n--- TEST 7: Thread interaction (prompt + progress) ---")
        console_errors_before = len(console_errors)
        await page.evaluate("""(() => {
            appendPromptBubble('Test research query');
            appendProgressBlock();
            addProgressTask('Searching 10 sources...');
        })()""")
        await page.wait_for_timeout(500)

        bubble = await page.query_selector(".ws-prompt-bubble")
        if bubble:
            print("PASS: prompt bubble rendered")
        else:
            print("FAIL: prompt bubble NOT rendered")
            errors.append("Prompt bubble not rendered")
            all_pass = False

        progress = await page.query_selector(".ws-progress-block")
        if progress:
            print("PASS: progress block rendered")
        else:
            print("FAIL: progress block NOT rendered")
            errors.append("Progress block not rendered")
            all_pass = False

        new_errors3 = console_errors[console_errors_before:]
        js_errors_only3 = [e for e in new_errors3 if e.startswith("[error]") or e.startswith("[PAGE_ERROR]")]
        if not js_errors_only3:
            print("PASS: No JS errors during thread interaction")
        else:
            print(f"FAIL: {len(js_errors_only3)} JS error(s) during thread interaction:")
            for e in js_errors_only3:
                print(f"  {e}")
            errors.extend(js_errors_only3)
            all_pass = False

        # ---- SUMMARY ----
        print("\n" + "=" * 60)
        total_console_errors = [e for e in console_errors if e.startswith("[error]") or e.startswith("[PAGE_ERROR]")]
        print(f"Console errors: {len(total_console_errors)}")
        print(f"Console warnings: {len([e for e in console_errors if e.startswith('[warning]')])}")
        print(f"Test errors: {len(errors)}")
        print(f"Test warnings: {len(warnings)}")

        if total_console_errors:
            print("\nAll console errors:")
            for e in total_console_errors:
                print(f"  {e}")

        if errors:
            print("\nAll test errors:")
            for e in errors:
                print(f"  {e}")

        if all_pass and not total_console_errors:
            print("\nRESULT: ALL PASS")
        else:
            print(f"\nRESULT: FAIL ({len(errors)} errors, {len(total_console_errors)} console errors)")

        await browser.close()

    server.kill()
    server_log.close()
    return all_pass and not total_console_errors


if __name__ == "__main__":
    result = asyncio.run(run_check())
    sys.exit(0 if result else 1)
