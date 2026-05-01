# Audit — `4fe03f7` batch (5 commits, Phase 2C polish)

**Verdict:** APPROVE_WITH_FIXES
**Findings:** P0=0  P1=3  P2=4  P3=4

Five-commit window: `dae2a9f` (2C.5 a11y) → `07d6c30` (2C.5b error-banner a11y) → `2057fac` (2C.2 visual baselines) → `2bb1de7` (2C.4 perf budgets) → `4fe03f7` (CI extension). Local re-run: 7/7 a11y PASS in 11.8s, 6/6 perf PASS in 5.5s against the live FastAPI 8000 + Next 3738 servers.

## Pre-flight checklist

- I read: `.github/workflows/web_ci.yml` (full), `web/tests/e2e/{accessibility,performance,visual}.spec.ts`, `web/app/dashboard/page.tsx` (lines 320–425), `web/app/inspector/[runId]/page.tsx` (lines 116–170, 305–320, 660–675), `web/app/runs/[runId]/page.tsx` (lines 120–135), `web/playwright.config.ts`, `web/next.config.ts`, `web/package.json` scripts, `requirements.txt` (full), `src/polaris_v6/api/app.py`, `src/polaris_v6/api/bundle.py`, all 5 per-commit briefs, the v2 review-brief format spec.
- I ran: `npx playwright test --project=chromium tests/e2e/accessibility.spec.ts` → 7/7 PASS; `npx playwright test --project=chromium tests/e2e/performance.spec.ts` → 6/6 PASS; `git show <sha> --stat` and `git show <sha> -- <path>` for each commit.
- I grepped for: `disableRules`, `withRules`, `bg-destructive`, `text-destructive`, `webServer:` config block, `does_not_exist_runid_404`, `ev_clin_001:1200-1450`.
- Out of scope per brief: `inspector.spec.ts` content (Phase 2C.1, prior commit `3fd3d20`), cross-browser firefox/webkit (Phase 2C.3, deferred per `8c5ef23` brief), executive-summary feature itself (`c2fbeb2`).

## Per-criterion forced enumeration

- Criterion 1 [Real violation, real fix — no rule suppression]: NONE. `withTags(WCAG_TAGS)` is the only axe configuration. No `disableRules`, no `withRules([])`, no per-page allowlist anywhere in the spec or helper. The dashboard fix changed actual classnames (line 338 dropped `bg-destructive/5`, lines 354+360 promoted `text-destructive` → `text-foreground font-medium`), and 07d6c30 restructured DOM (added `<section role="alert" aria-labelledby>` + `<h1>`). Confirmed legitimate.
- Criterion 2 [WCAG tag breadth]: NONE. `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, best-practice` — exactly as documented.
- Criterion 3 [Loud failure]: NONE. The helper throws `Error` with rule id, impact, node selectors, and `failureSummary`. Adequate diagnostic surface.
- Criterion 4 [No regression on existing e2e]: NONE locally; CI hasn't run yet.
- Criterion 5 [No mocking; live servers]: NONE. No `webServer:` block in `playwright.config.ts`; no `page.route()` interception in any of the new specs. Tests hit real HTTP. Confirmed honest.
- Criterion 6 [Real perf measurements]: NONE. `Date.now()` deltas around live `tab.click()` + `waitFor` calls; `PerformanceObserver` with `type:"paint"` for FCP. No stubbed values. FCP `-1` sentinel correctly fails via `toBeGreaterThanOrEqual(0)`.
- Criterion 7 [Concrete budgets per metric]: see P1 below.
- Criterion 8 [Baselines on disk + committed]: NONE. 4 PNGs present (46K, 9K, 68K, 38K).
- Criterion 9 [Threshold justified]: see P2 below.
- Criterion 10 [Real servers in CI; no mocks]: see P1 below.
- Criterion 11 [Health-check polling before tests]: NONE. 30-iter `curl /health` and `curl /dashboard` loops with log dump on failure.
- Criterion 12 [Failure artefacts captured]: NONE. `actions/upload-artifact@v4` on failure with 7-day retention.
- Criterion 13 [`needs:` gating]: NONE. `e2e_playwright` blocks on `lint_format_typecheck_build`.
- Criterion 14 [Single chromium project]: NONE. `--project=chromium` on every invocation.

## P0 (production-breakers)

NONE. No silent failure path, no broken auth, no data loss, no missing rollback flag, no security hole.

## P1 (phase-rework)

**P1.1 — A11y coverage gap: 4 destructive surfaces still match the exact pattern dae2a9f+07d6c30 fixed.** The 2C.5 commit set claimed to fix the `text-destructive` + `bg-destructive/10` color-contrast violation (4.0:1 < 4.5:1 AA floor). The fix touched two surfaces. Four more with the identical class string remain in shipped code, none covered by the 7-test a11y suite:
- `web/app/dashboard/page.tsx:418` — submit-form error banner. Reachable when the dashboard scope-discovery POST fails (server down, rate-limit, etc.).
- `web/app/inspector/[runId]/page.tsx:149` — Two-family-invariant card (failure variant). Reachable on any run where `family_segregation_passed === false`.
- `web/app/inspector/[runId]/page.tsx:667` — Charts-tab error banner. Reachable on charts API failure.
- `web/app/runs/[runId]/page.tsx:125` — Run-detail page error banner. Reachable on bundle-fetch failure.

Why it matters: the brief itself flags this as P0 ("are there other surfaces using the same `bg-destructive/5` + `text-destructive` pattern that ALSO fail?"). The answer is yes. The error-banner story is half-shipped — same root cause, four un-converted occurrences. To verify: `grep -nE "text-destructive .* bg-destructive/10" web/app/` returns 4 hits beyond the one 07d6c30 fixed.

How to verify the gap matters: write one `accessibility.spec.ts` test per surface that simulates the failure path (e.g. mock backend down via `POLARIS_V6_BACKEND_URL=http://127.0.0.1:9999`) and assert axe-clean.

**P1.2 — Hover-latency budget moved silently.** `web/tests/e2e/performance.spec.ts:13` documents the 2C.4 budget as `Hover → tooltip-visible after open-delay completes < 1.0s`, but no test in the file measures hover latency. The Codex brief admits this ("hover-latency target NOT directly measured here") and proposes accepting the proxy budgets. Result: the original 2C.4 task description's `<100ms hover-latency` budget is silently dropped from the deliverable while the docstring still lists it. Either remove the docstring line or add a hover test (page.locator(...).hover() → wait for `[role="tooltip"]`); don't ship a comment that disagrees with shipped tests.

**P1.3 — Perf budgets are 4-5x looser than measured baselines.** `DOMContentLoaded < 2000ms` passes when local actual is ~450ms (4.4x slack). `FCP < 1500ms` passes when local actual is ~373ms (4x slack). `Vega < 2500ms` vs ~1.0s actual (2.5x). A 3x performance regression — e.g. a lazy-loaded chunk going eager, blocking 1200ms — would slide through every gate. The author flagged this as their own P0 in the brief; my independent assessment confirms. Recommend `2x baseline` rule: budget = max(local_baseline × 2, hard_floor). For the 250ms tab-switch budget that's ~tight enough; for the others it's not. To verify: run with artificial latency injection (DevTools throttling or `--cpu-throttling-rate=4`) and confirm at least one budget should fail.

## P2 (governance precision)

**P2.1 — Tab-switch test masks >1s regressions as locator-timeout, not budget-failure.** `performance.spec.ts:43` and `:62` use `waitFor({timeout: 1_000})` then `expect(switchMs).toBeLessThan(250)`. If the tab takes 1100ms to render, the locator throws TimeoutError before the budget assertion runs — the failure surfaces as flaky-locator, not a perf regression. Fix: bump `waitFor` timeout to e.g. 5000ms so the perf assertion always runs and produces a clean diagnostic. Verify: introduce `await page.waitForTimeout(1100)` after `tab.click()` and confirm the failure mode reads `expected switchMs < 250, got 1100+ms` rather than `locator timed out`.

**P2.2 — `requirements.txt` install on Ubuntu CI: install-time bloat + uncertain runtime.** `pip install -r requirements.txt` pulls ~160 packages including `weasyprint` (needs system libs `libpango-1.0-0`, `libcairo2`, `libharfbuzz0b` not provided by `playwright install --with-deps`), `pytesseract` (needs system tesseract binary), `openai-whisper` (needs ffmpeg), `crawl4ai`, `torch`, `chromadb`, `sentence-transformers`. The bundle/health endpoints don't import any of these, so uvicorn likely boots — but install-time on a fresh runner is ~8-12 min, ~5x what an api-only smoke test needs. Recommend `requirements-api.txt` minimal subset (fastapi, uvicorn, pydantic, sse-starlette, slowapi, python-multipart, watchfiles) for the e2e job. Verify on a fresh ubuntu-latest with `--dry-run` or actually run the job once.

**P2.3 — `visual.spec.ts` exclusion is comment-only.** The CI doesn't run `visual.spec.ts` because the workflow invokes per-file (`tests/e2e/inspector.spec.ts`, `tests/e2e/accessibility.spec.ts`, `tests/e2e/performance.spec.ts`). But the rationale is comment-only at line 132-135. If anyone refactors the e2e step into `npx playwright test` (no file arg), visual.spec.ts WILL run on Linux, find no matching `*-chromium-linux.png` baseline, and either auto-snapshot (per Playwright defaults the first run creates the baseline — turning a missing baseline into a silent commit-needed) or hard-fail. Add `testIgnore` to `playwright.config.ts` for the file under Linux, OR add `--ignore-snapshots` flag on Linux, OR rename file to skip-by-pattern. Verify: actually run `npx playwright test --project=chromium tests/e2e/visual.spec.ts` on Linux and observe whether it errors loud or silently writes new baseline files.

**P2.4 — `package-lock.json` cache key uses `web/package-lock.json` path but the e2e job's `npm ci` runs from `web/` (via `defaults.run.working-directory`).** This is correct in practice. But the cache check at install time uses the lockfile-content hash; if the lockfile has Windows-only platform-pinned native deps (e.g. SWC) that don't resolve on Linux, `npm ci` fails. To verify: search lockfile for `os: ["win32"]` and `cpu: ["x64"]` entries; confirm Linux-equivalent variants resolve.

## P3 / deferred_polish

**P3.1 — `nohup ... &` pattern in CI may leave orphan processes.** `start_fastapi_backend` and `build_and_start_next` use `nohup CMD > /tmp/X.log 2>&1 &` and exit when the curl probe succeeds. Common practice; works on GitHub-hosted runners; not strictly worth a `disown` or systemd-style supervisor. Note for posterity.

**P3.2 — No process cleanup on job failure.** If a test fails mid-suite, the FastAPI + Next processes leak until the runner is destroyed. GitHub-hosted runners are ephemeral so this is harmless, but a self-hosted setup would accumulate zombies. Add a `if: always()` cleanup step calling `pkill -f "next start" || true; pkill -f uvicorn || true` for explicit teardown.

**P3.3 — `state/substrate_commit_counter.json` is single-source-of-truth for the K=5 trigger and is gitignored.** Deleting/corrupting the file silently re-arms the counter; the audit cycle isn't replayable from `git log` alone. Recommend either committing it (move outside `state/`) or deriving the count from `git log --grep=PL:.*v6.2 --since=<last-audit-sha>`. Not blocking — the author's brief's "Counter now 5/5 — TRIGGER" message is what actually drove this audit, not the JSON file.

**P3.4 — `expect(results.violations).toEqual([])` is a no-op after the throw.** `accessibility.spec.ts:38` throws on violations BEFORE reaching line 39's `expect.toEqual`. The expect is dead code in the failure path and trivially passes in the success path. Either remove or restructure as guarded assertion. Cosmetic.

## Reviewer independence statement

I read the actual diffs (`git show <sha> -- <path>` for each commit, full `web_ci.yml`, full `accessibility.spec.ts`, full `performance.spec.ts`, full `visual.spec.ts`, `app/dashboard/page.tsx` lines 320–425, `app/inspector/[runId]/page.tsx` lines 116–170 and 660–675, `app/runs/[runId]/page.tsx` lines 120–135, `playwright.config.ts`, `app.py`). I ran the a11y and perf suites locally against the running 8000+3738 dev servers and observed PASS counts/durations matching the briefs.

Where I AGREE with the author's self-flagged P0:
- dae2a9f brief P0 ("are there other surfaces using the same pattern?"). My independent assessment confirms: yes — 4 surfaces. Promoted to my P1.1.
- 2bb1de7 brief P0 ("budgets are loose-but-meaningful"). Confirmed: 4-5x slack. P1.3.
- 2bb1de7 brief P0 ("hover-latency target NOT directly measured"). Confirmed: docstring promises a budget the test file never measures. P1.2.
- 4fe03f7 brief P0 ("`pip install -r requirements.txt` may pull deps that fail on Ubuntu"). Partially confirmed: weasyprint system libs likely missing; install-time bloat is the firmer concern. Downgraded to P2.2.

Where I DISAGREE with the author's self-flagged P0:
- 4fe03f7 brief P0 ("polling `/health` may return ok before all routes are registered"). I read `app.py`. `app = create_app()` runs at module load; `health_router` is included alongside all other routers BEFORE uvicorn binds. No race. Author's concern is hypothetical, not real.
- 4fe03f7 brief P0 ("`PYTHONPATH=src` propagation to background uvicorn"). It's a single shell line — env var sets correctly for the `python -m uvicorn` call, regardless of nohup/&.
- 2057fac brief P0 ("2% threshold + fullPage means small change shifts everything below"). The 2% is on pixel diff ratio, and Playwright's pixel diff is per-pixel-changed counted across the full image. A 30px banner shift creates 30px × width changed pixels = ~3.3% of image area, which would EXCEED the 2% threshold. Test would catch it.

Verdict: **APPROVE_WITH_FIXES**. The destructive-surface coverage gap (P1.1) and the moved-goalpost hover-latency (P1.2) are the two that should land before the next phase claims a11y + perf "done"; the loose budgets (P1.3) are a fitness-tuning issue. P0 = 0; nothing in this batch breaks production. Two consecutive APPROVE rounds (per `REVIEW_BRIEF_FORMAT_v2.md` locking criterion) would close the cycle once P1 fixes land.
