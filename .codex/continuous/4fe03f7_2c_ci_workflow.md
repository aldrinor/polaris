# Per-commit Codex brief — `4fe03f7`

**Commit:** `4fe03f7 PL: v6.2 CI gate — extend web_ci.yml with e2e+a11y+perf Playwright job`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (1):**
- `.github/workflows/web_ci.yml` (+98/-0): new `e2e_playwright` job

## What this commit does

Extends the existing GitHub Actions `web_ci` workflow with a second job, `e2e_playwright`, that runs the full Playwright e2e + accessibility + performance suite against a real backend + frontend on every PR/push.

Job pipeline:
1. **needs: lint_format_typecheck_build** — only runs if static gates pass (saves CI minutes).
2. **Python 3.13 setup + `pip install -r requirements.txt`** — pulls FastAPI + Pydantic + uvicorn from the existing requirements.
3. **Node 22 setup + `npm ci`** — frontend deps (cached).
4. **`npx playwright install --with-deps chromium`** — single-browser to keep CI minutes bounded.
5. **Boot FastAPI** on 127.0.0.1:8000 in background, poll `/health` for ≤30s.
6. **Build + boot Next.js** on 127.0.0.1:3738, poll `/dashboard` for ≤30s.
7. **Run e2e suites** sequentially: inspector (9 tests) → accessibility (7) → performance (6) = **22 tests** total per CI run.
8. **Upload traces on failure** for 7-day retention.

`visual.spec.ts` is INTENTIONALLY excluded — its baselines are `*-chromium-win32.png` (locally captured on Windows). Linux baselines need to be added before that suite can pass on `ubuntu-latest`. Tracked as P0 in the 2057fac brief.

## Acceptance criteria

1. **Real servers, no mocks.** The job boots actual FastAPI + Next.js processes; Playwright tests hit them via real HTTP. No `webServer:` config block in `playwright.config.ts` to maintain explicit visibility into what's running.
2. **Health-check before tests.** Both servers have a polling loop with timeout + log dump on failure. Tests don't race the boot sequence.
3. **Failure artefacts captured.** Trace uploads enable postmortem on broken CI runs.
4. **`needs:` gating.** Static gates (lint/typecheck/build) must pass before e2e runs. Saves wasted minutes when a syntax error already broke things.
5. **Single chromium project.** Cross-browser (firefox/webkit) NOT in CI initially — adds ~3× runtime; deferable per the 8c5ef23 brief P1.

## Codex focus

- **P0:** Two issues with the Python install: (a) `pip install -r requirements.txt` may pull dependencies that fail on Ubuntu (some Windows-only packages?); (b) `polaris_v6.api.app:app` import path assumes `src` layout — does `PYTHONPATH=src` propagate correctly to the background uvicorn?
- **P0:** Background process race — the `nohup ... &` approach may exit before the server is listening. The 30-iteration poll is the safety net but if `/health` returns before all routes are registered, the inspector tests could fail with 404s. Should we poll a more representative endpoint (`/runs/golden_clinical_001/bundle`)?
- **P1:** No caching of Playwright browser binaries between runs. `actions/cache` on `~/.cache/ms-playwright` would shave ~30s off every run.
- **P2:** The job runs all 22 tests serially in 3 separate `npx playwright test` invocations. Combining into one invocation (`tests/e2e/inspector.spec.ts tests/e2e/accessibility.spec.ts tests/e2e/performance.spec.ts`) would skip 2 cold-start overheads.

## Cross-review

Lands at `outputs/audits/continuous/4fe03f7_cross_review.md`.

**A+C K=5 trigger: this commit puts the substrate counter at 5/5.** Next action per `memory/autoloop_continuous_codex_brief_discipline.md` is to spawn a `general-purpose` subagent with cleared context + adversarial-review prompt + pointers to the 5 per-commit briefs above. Subagent writes `outputs/audits/continuous/4fe03f7_audit.md`; Claude writes the cross-review and gates per `autoloop_v2_audit_cross_review.md`. Substrate counter resets to 0 after the audit cycle completes.
