# Audit — `bb60495` batch (6 commits, post-`909eb4c` middleware coverage + F-7/F-7b/F-8)

**Verdict:** APPROVE_WITH_FIXES
**Findings:** P0=0  P1=1  P2=3  P3=4

Six-commit window: `9fe4de9` (SSE) → `8ae03b6` (Throttle) → `cc10303` (StickyConnection §9.4) → `dbe62e0` (OtelPropagate) → `3cf4737` (F-7+F-8+cycle-2 audit) → `bb60495` (F-7b a11y guardrail). Local re-run on the running 8000+3738 servers: 228 v6 tests (221 pass + 7 xfail) in 19.3s; 30/30 e2e in 35.1s; 9/9 a11y in 14.2s; 4/4 visual in 5.3s.

## Pre-flight

- Read: cycle-1 + cycle-2 audits + cross-reviews; per-commit briefs for all 6; `git show` all 6; affected `web/` + `src/polaris_v6/` + `tests/v6/` files; `requirements.txt`, `requirements-v6.txt`, `Dockerfile`, `.github/workflows/web_ci.yml`, `.gitignore`.
- Ran: full `tests/v6/` (228 tests, all green); full `web/tests/e2e/` (30 tests, all green).
- Grepped: `text-destructive[^-]`, `text-destructive`, `bg-destructive`, `destructive` (broad); `dramatiq|opentelemetry` in `requirements*.txt`.

## Per-criterion forced enumeration

- C1 [F-7 mechanical scope]: NONE. `grep "text-destructive" web/` returns ZERO hits. Cycle-2 P1.1 closed; dashboard:324 + inspector:315 both → `text-foreground font-medium`.
- C2 [F-7 collateral]: NONE. `card.tsx`/`input.tsx`/`sign-in/page.tsx` clean. `input.tsx` only uses `border-destructive` on `aria-invalid` — different token.
- C3 [F-8 button variant]: NONE for contrast (~17:1 light, ~14:1 dark). See P3.1 for visual-design.
- C4 [F-7b regression gate]: see **P1.1**.
- C5 [SSE test]: NONE. Real `TestClient(create_app())` + `EventSourceResponse`. 6/6 pass. See P3.4.
- C6 [Throttle test]: NONE for correctness. 7/7 pass. See P3.3 timing.
- C7 [Sticky connection §9.4 fix]: NONE for the bug fix. WARNING log + cleared `_local.client` on failure. See **P2.1** for `# pragma: no cover` mismatch.
- C8 [OTEL propagate test]: NONE for correctness. Real TracerProvider, 7/7 pass. See P3.2 for global-state leak.
- C9 [Audit-trail integrity]: NONE. Cycle-2 files at `outputs/audits/continuous/909eb4c_*.md` byte-identical to subagent output (`git show 3cf4737:.. | diff` empty).

## P0

NONE. No silent failure shipped to production paths, no broken auth, no data loss, no security hole. F-7 fix landed correctly; tests pass.

## P1

**P1.1 — F-7b regression gate is half-complete vs cycle-2 verify recommendation.** Cycle-2 audit recommended: "a /dashboard upload list is WCAG-AA clean test in post-upload state + an inspector fixture with drop_reason set both fire color-contrast violations." Cycle-2 cross-review's fix plan called F-7b "Add 1 a11y test PER FAILURE PATH (upload-list-with-files; sentence-with-drop-reason)" (emphasis on PER).

`bb60495` added only the inspector half. The dashboard `/dashboard upload list "remove" button` surface (also fixed by F-7 at `dashboard/page.tsx:324`) has NO regression gate. `grep -n "remove\|upload list" web/tests/e2e/accessibility.spec.ts` returns nothing. If a future contributor reverts that line to `text-destructive`, no test fires.

Production hazard already closed by F-7 — this is a `guardrail` continuation gap. Verify (actionable): the "remove" button only renders AFTER `uploads` is non-empty (via `POST /upload`). A real regression test needs either (a) `page.evaluate()` injecting upload-list state into the React tree before axe, or (b) a backend fixture that pre-populates an upload row, then `await page.goto(...)` + axe. Just adding another `page.goto("/dashboard")` won't fire the surface — that's why cycle-2 said "post-upload state". Tag: **guardrail**.

## P2

**P2.1 — `# pragma: no cover` on `connection.py:37` is misleading.** The except branch is EXPLICITLY exercised by `test_close_errors_are_logged_not_swallowed`. Pragma tells coverage tools to ignore an actually-covered branch — coverage data dishonest. Remove pragma. Tag: **guardrail**. (Brief's own P3 self-flag.)

**P2.2 — F-7b a11y test does not assert COLOR-CONTRAST rule specifically.** Calls `expectNoA11yViolations` (all WCAG2AA rules). If F-7 reverted, axe catches via color-contrast — but unrelated a11y failures also fire, masking surface origin. Tighter: assert `results.violations.find(v => v.id === "color-contrast")` absent. Cosmetic. Tag: **guardrail**.

**P2.3 — `tests/v6/` has no CI runner, deps split between two pin files.** The 4 new backend coverage tests + existing `test_otel_init` rely on `dramatiq`, `opentelemetry-{api,sdk}`, `sse-starlette` — all pinned in `requirements-v6.txt` (Phase 0 Task 0.5; `dramatiq[redis,watch]==2.1.0`, `opentelemetry-{api,sdk}==1.41.1`). But: legacy `requirements.txt` lacks them; `.github/workflows/web_ci.yml` installs `requirements.txt` and only runs Playwright e2e (no `pytest tests/v6/` step); `Dockerfile` also uses `requirements.txt`. Tests pass locally because the user's env has -v6.txt loaded; on a fresh CI box installing only `requirements.txt`, the new tests would SILENTLY SKIP via `pytest.importorskip` — LAW II "silent skip" antipattern. Today no such CI runner exists, so latent rather than active. The pre-existing requirements.txt header already enumerates this class of "Known gaps". Verify: add a backend CI job that installs `-r requirements-v6.txt` AND runs `pytest tests/v6/`. Tag: **root_cause** for the missing CI; **guardrail** for the dep consolidation.

## P3

**P3.1 — F-8 destructive Button visual identity weakened.** Old: `bg-destructive/10 text-destructive` (red-tinted bg + red text). New: `border-destructive/60 text-foreground font-medium` (border-only). Border-only is a departure from typical "tinted-red destructive" UX convention; "destructive" signal is now a 1px border at 60% opacity. Zero current usages, no regression today; flag for design audit.

**P3.2 — OTEL TracerProvider autouse fixture leaks global state.** `_otel_provider` does NOT restore: "Provider is global; we leave it set across tests for simplicity." Post-test `Failed to export traces to localhost:4317` log is direct evidence. Pre-existing pattern (matches `init_otel`); flag for `pytest_sessionfinish` cleanup.

**P3.3 — Throttle test timing band 110-250ms tight for Windows CI.** `time.sleep(0.15)` + `<250ms` could overshoot on jittery CI. Brief's own P1. Widen to 110-400ms.

**P3.4 — SSE test does not assert stream-close.** Endpoint emits 5 events; tests don't assert `response.is_closed`. Some SSE clients hang on missing terminator. Acceptable for stub stage.

**P3.5 — `.gitignore` exemption broader than intended.** `!outputs/audits/` exposes `outputs/audits/v25..v27/` as untracked (was previously gitignored). Tighten to `!outputs/audits/continuous/` only.

**P3.6 — F-7b fixture `cost_usd: 0.31` arbitrary.** Document acceptable ranges in fixture-conventions; out of scope.

## Cross-cycle integrity

- Cycle-1 P2.2 (`requirements.txt` install bloat): unchanged, no regression. P2.3 above is a related but distinct issue (split between -v6.txt and -txt files; no CI runs tests/v6).
- Cycle-1 P2.4 (cross-platform `package-lock.json`): unchanged, no regression. New OTEL+dramatiq deps are Python-side and don't touch lockfile.
- Cycle-2 P2.2 (F-5 `testIgnore` Linux-only): unchanged in this batch.
- Cycle-2 P2.1 (F-3 DOMContentLoaded slack at lower-bound): unchanged in this batch.

## Reviewer independence statement

I read actual diffs (`git show` for all 6 commits + prior audits), grepped the codebase mechanically, inspected each new test file, ran 228 v6 + 30 e2e tests live, and cross-checked `requirements.txt` + `requirements-v6.txt` + `Dockerfile` + `web_ci.yml` against `pip show`. P2.3 (CI runner gap) is from primary-source evidence (workflow's `pip install -r requirements.txt` line + no `pytest tests/v6/` step). P1.1 is from reading cycle-2's verify recommendation against the actual `accessibility.spec.ts` diff.

AGREE: F-7 closed cycle-2 P1.1 (root_cause); F-8 hardened the landmine; backend coverage commits exercise real subroutines (no mock-theater); audit-trail durably committed; `requirements-v6.txt` exists and is canonical.

DISAGREE: F-7b's "Closes the audit gap" framing overstates — the dashboard upload-list path remains un-gated.

**Verdict: APPROVE_WITH_FIXES.** P0 = 0; nothing breaks production today. One P1 (guardrail: dashboard regression gate). P2.3 (CI gap) is latent but worth landing before v6 production. Cycle-3 returns APPROVE_WITH_FIXES with one new P1, so the two-consecutive-clean-APPROVE locking criterion does NOT yet apply. After P1.1 lands and a 4th audit returns P1=0, the lock applies after one MORE clean cycle (cycle-5 — criterion is TWO consecutive APPROVE rounds; we have ZERO yet).
