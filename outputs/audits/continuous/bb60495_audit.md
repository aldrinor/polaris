# Audit — `bb60495` batch (6 commits, post-`909eb4c` middleware coverage + F-7/F-7b/F-8)

**Verdict:** APPROVE_WITH_FIXES
**Findings:** P0=0  P1=2  P2=2  P3=4

Six-commit window: `9fe4de9` (SSE) → `8ae03b6` (Throttle) → `cc10303` (StickyConnection §9.4) → `dbe62e0` (OtelPropagate) → `3cf4737` (F-7+F-8+cycle-2 audit) → `bb60495` (F-7b a11y guardrail). Local re-run on the running 8000+3738 servers: 228 v6 tests (221 pass + 7 xfail) in 19.3s; 30/30 e2e in 35.1s; 9/9 a11y in 14.2s; 4/4 visual in 5.3s.

## Pre-flight

- Read: cycle-1 audit + cross-review (`4fe03f7_*`); cycle-2 audit + cross-review (`909eb4c_*`); per-commit briefs for all 6 commits; `git show` for all 6; full diffs of `web/components/ui/{button,card,input}.tsx`, `web/app/{dashboard,inspector/[runId],runs/[runId],sign-in}/page.tsx`, `web/tests/e2e/accessibility.spec.ts`; `src/polaris_v6/queue/middleware/{otel_propagate,connection,throttle}.py`; `src/polaris_v6/api/stream.py`; `src/polaris_v6/observability/otel_init.py`; `tests/v6/test_{otel_propagate_middleware,sticky_connection_middleware,throttle_middleware,api_stream,otel_init}.py`; `tests/v6/fixtures/evidence_contract_v1/golden_run_with_drop_reason.json`; `requirements.txt`; `.gitignore`.
- Ran: full `tests/v6/` (228 tests, all green); full `web/tests/e2e/` (30 tests, all green); a11y subset (9 tests).
- Grepped: `text-destructive[^-]`, `text-destructive`, `bg-destructive`, `destructive` (broad), `dramatiq|opentelemetry` in `requirements.txt`, all OTEL fixtures.

## Per-criterion forced enumeration

- C1 [F-7 mechanical scope]: NONE. `grep "text-destructive" web/` returns ZERO hits. Cycle-2 P1.1 fully closed; dashboard:324 + inspector:315 both converted to `text-foreground font-medium`.
- C2 [F-7 collateral]: NONE. `card.tsx`/`input.tsx`/`sign-in/page.tsx` all clean. `input.tsx` only uses `border-destructive`/`ring-destructive` on `aria-invalid` — different token, semantically correct.
- C3 [F-8 destructive button variant]: NONE for contrast. `border-destructive/60 text-foreground` passes AA easily (~17:1 light, ~14:1 dark). See P3.1 for visual-design regression.
- C4 [F-7b regression gate]: see **P1.1**. Half-complete.
- C5 [Backend coverage commits]: see C6-C9 + P1.2 + P2.1.
- C6 [SSE test]: NONE. Real `TestClient(create_app())`, real `EventSourceResponse`, CRLF parser handles real wire format. 6/6 pass. See P3.4.
- C7 [Throttle test]: NONE for correctness. 7/7 pass. See P3.5 timing band.
- C8 [Sticky connection §9.4 fix]: NONE for the bug fix itself. WARNING log + cleared `_local.client` on failure. See **P2.1** for `# pragma: no cover` mismatch.
- C9 [OTEL propagate test]: NONE for correctness. Real TracerProvider in autouse, 7/7 pass. See P3.2 for global-state leak across tests.
- C10 [Audit-trail integrity]: NONE. Cycle-2 audit + cross-review at `outputs/audits/continuous/909eb4c_*.md` byte-identical to what subagent wrote (`git show 3cf4737:.. | diff` empty). `.gitignore` exemption tracks new audits but exposes `outputs/audits/v25..v27/` as untracked (cosmetic, see P3.6).

## P0

NONE. No silent failure shipped to production paths, no broken auth, no data loss, no security hole. F-7 fix landed correctly; tests pass.

## P1

**P1.1 — F-7b regression gate is half-complete vs cycle-2 verify recommendation.** Cycle-2 audit explicitly recommended:

> Verify: a /dashboard upload list is WCAG-AA clean test in post-upload state + an inspector fixture with drop_reason set both fire color-contrast violations.

`bb60495` only added the inspector half. The dashboard `/dashboard upload list "remove" button` surface (the OTHER surface that F-7 fixed at `dashboard/page.tsx:324`) has NO regression gate. `grep -n "remove\|upload list" web/tests/e2e/accessibility.spec.ts` returns no matches. If a future contributor reverts the dashboard change to `text-destructive`, no test fires.

The brief's title — "F-7b guardrail — a11y test for verified-sentence drop_reason path" — accurately scopes itself to inspector. But cycle-2 cross-review's fix plan called F-7b "Add 1 a11y test PER FAILURE PATH (upload-list-with-files; sentence-with-drop-reason)" (emphasis on PER). Only 1 of 2 paths is gated.

This is a `guardrail` continuation gap, not a production hazard (F-7 already shipped). Verify: add a dashboard test that programmatically simulates an upload-list state (or use `page.evaluate()` to inject upload state) and runs axe. Tag: **guardrail**.

**P1.2 — Missing `dramatiq` + `opentelemetry-api` + `opentelemetry-sdk` in `requirements.txt`.** Production code at `src/polaris_v6/queue/middleware/{otel_propagate,connection,throttle}.py` imports `dramatiq` at module top. Production code at `src/polaris_v6/observability/otel_init.py` imports `opentelemetry.sdk.trace` and `opentelemetry.exporter.otlp.proto.grpc.trace_exporter`. Local `pip show` confirms `dramatiq 2.1.0`, `opentelemetry-api 1.36.0`, `opentelemetry-sdk 1.36.0` installed.

**`grep -iE "dramatiq|opentelemetry" requirements.txt` returns NOTHING.**

The 4 new test files (`test_otel_propagate_middleware.py`, `test_sticky_connection_middleware.py`, `test_throttle_middleware.py`, `test_otel_init.py`) all use `pytest.importorskip("dramatiq")` and similar. On CI fresh install (`pip install -r requirements.txt`), these tests will SILENTLY SKIP — exactly the "no silent fallback" violation that LAW II + CLAUDE.md §9.4 forbid. The `test_otel_init.py` file is even more egregious: it calls `init_otel()` which would `ImportError` on the production import chain itself.

This isn't theoretical — the recent run shows `Failed to export traces to localhost:4317, error code: StatusCode.UNAVAILABLE` after `test_otel_init` set the global tracer provider. That's primary-source evidence the OTEL stack runs locally; on a clean CI box, the stack would be entirely absent and tests would skip silently.

Tag: **root_cause** — add the 3 deps to `requirements.txt` with version pins matching local (`dramatiq>=2.1.0`, `opentelemetry-api>=1.36.0`, `opentelemetry-sdk>=1.36.0`, plus `opentelemetry-exporter-otlp-proto-grpc` for `init_otel`). Verify: drop a CI-clone in a fresh venv, `pip install -r requirements.txt`, and confirm the new tests ACTUALLY RUN (not skip).

## P2

**P2.1 — `# pragma: no cover` on `connection.py:37` is misleading.** The except branch is EXPLICITLY exercised by `test_close_errors_are_logged_not_swallowed` (`tests/v6/test_sticky_connection_middleware.py:53`). The pragma tells coverage tools to ignore the branch; the branch is in fact covered. This makes coverage data dishonest. Either (a) remove the pragma so the branch counts as covered, or (b) keep the pragma + remove the test. Per the brief's own P3 self-flag: "Remove pragma." Tag: **guardrail**.

**P2.2 — F-7b a11y test does not assert the COLOR-CONTRAST rule specifically.** The test calls `expectNoA11yViolations` which runs all WCAG2AA rules. If F-7 reverted, axe would catch it via the color-contrast rule — but if a different a11y rule started failing for an unrelated reason, the test would fire too, masking which surface caused the regression. Tighter: assert `results.violations.find(v => v.id === "color-contrast")` is absent, or capture the count of color-contrast violations specifically. Cosmetic; current form catches the regression that matters. Tag: **guardrail** (cosmetic).

## P3

**P3.1 — F-8 destructive Button visual identity weakened.** Old: `bg-destructive/10 text-destructive` (red-tinted background + red text — strong visual signal). New: `border-destructive/60 text-foreground font-medium` (border-only red + default text color). Border-only is a notable departure from typical "tinted-red destructive button" UX convention. The button's only "destructive" signal is now a 1px border at 60% opacity. Future design work will likely revisit this — flag for design audit. Zero current usages so no UX regression today.

**P3.2 — OTEL TracerProvider autouse fixture pollutes downstream tests.** `_otel_provider` autouse fixture sets `trace.set_tracer_provider(provider)` and explicitly does NOT restore: "Provider is global; we leave it set across tests for simplicity." Pre-existing pattern (matches `init_otel` behaviour) so not a regression — but the post-test `Failed to export traces to localhost:4317` log is direct evidence the global state leaks. Acceptable for current state; flag for a `pytest_sessionfinish` cleanup.

**P3.3 — Throttle test timing band 110-250ms is tight for Windows CI.** `time.sleep(0.15)` + assertion `elapsed_ms < 250`. On heavily-loaded Windows CI (no realtime scheduling), 50ms scheduler jitter + GC pause could push past 250ms. Brief's own P1 self-flag. Widen to 110-400ms or use mock-time. Acceptable for now (tests passed locally).

**P3.4 — SSE test does not assert stream-close.** The endpoint emits 5 events then ends; tests don't assert `response.is_closed` or read past the last event. Some SSE clients hang indefinitely if the server doesn't send a terminator. Brief's own P2. Acceptable for stub stage.

**P3.5 — `.gitignore` exemption broader than intended.** `!outputs/audits/` exposes `outputs/audits/v25/`, `v26/`, `v27/` as untracked dirs (visible in `git status`). They were previously gitignored entirely. No correctness issue — files aren't auto-staged — but the working tree is now slightly noisier. Tighten to `!outputs/audits/continuous/` only.

**P3.6 — F-7b fixture `cost_usd: 0.31` and other arbitrary fields.** Document acceptable ranges in fixture-conventions or schema. Out of scope for this commit; brief's own P3.

## Cross-cycle integrity

- Cycle-1 P2.2 (`requirements.txt` install bloat): SUPERSEDED. P1.2 above is a NEW concern: bloat + missing deps both fail in the same audit but for different reasons.
- Cycle-1 P2.4 (cross-platform `package-lock.json`): unchanged, no regression. New OTEL+dramatiq deps are Python-side and don't touch lockfile.
- Cycle-2 P2.2 (F-5 `testIgnore` Linux-only): unchanged in this batch.

## Reviewer independence statement

I read actual diffs (`git show <sha>` for all 6 commits + cycle-1 + cycle-2 audits + cross-reviews), grepped the codebase mechanically (4 distinct patterns under `web/` + 2 under top-level), inspected each new test file end-to-end, ran 228 v6 + 30 e2e tests live, and cross-checked `requirements.txt` against `pip show`. The missing-deps finding (P1.2) is from primary-source evidence (`grep` empty) not assertion. The half-complete F-7b regression gate (P1.1) is from reading cycle-2's verify recommendation against the actual `accessibility.spec.ts` diff.

AGREE: F-7 closed cycle-2 P1.1 (root_cause for the destructive token); F-8 hardened the latent landmine; backend coverage commits exercise real subroutines (no mock-theater); audit-trail durably committed.

DISAGREE: F-7b's "Closes the audit gap noted in 3cf4737 brief" framing overstates. The dashboard upload-list path remains un-gated. And the 4 new test files are masked by `pytest.importorskip` against deps that aren't in `requirements.txt` — silently skipping on CI is the LAW II antipattern.

**Verdict: APPROVE_WITH_FIXES.** P0 = 0; nothing breaks production today (F-7 already shipped, all tests pass against installed local deps). Two P1s (one root_cause: deps; one guardrail: dashboard regression gate) MUST land before locking. Cycle-3 returns APPROVE_WITH_FIXES with fresh P1s, so the two-consecutive-clean-APPROVE locking criterion does NOT yet apply. After P1.1+P1.2 land and a 4th audit returns clean (P1=0), the lock applies after one MORE clean cycle (cycle-5 — the criterion is TWO consecutive APPROVE).
