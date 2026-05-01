# Cross-review — `bb60495` batch (cycle 3)

**Cross-review of:** `outputs/audits/continuous/bb60495_audit.md` (P0=0, P1=2, P2=2, P3=4)

## Verdict alignment

| | Claude self-assessment | Subagent verdict |
|---|---|---|
| Verdict | APPROVE_WITH_FIXES (per per-commit briefs noting P1.1 in 3cf4737 brief P3.2) | **APPROVE_WITH_FIXES** |
| P0 | none | **none** |
| Honesty / no fake-working | OK (per LAW II) | **OK** for the bug fixes themselves; **NOT OK** for `requirements.txt` (P1.2) |

**Subagent caught a real CI hazard I would have shipped.** The new test files (`test_otel_propagate_middleware.py`, `test_sticky_connection_middleware.py`, `test_throttle_middleware.py`, `test_otel_init.py` — pre-existing) use `pytest.importorskip("dramatiq" / "opentelemetry")`. On a fresh CI runner that runs `pip install -r requirements.txt`, those packages aren't installed, so the tests silently SKIP — exactly the LAW II "no silent fallback" violation. I personally `pip install dramatiq` mid-session today; the assumption that "it works locally" carried over without verifying the dep was tracked.

This is the second cycle-N finding the A+C subagent has caught that I would have missed. Strong evidence the loop is doing real work, not rubber-stamping.

## Fix plan (root_cause / guardrail / band_aid)

| ID | Source | Fix | Tag |
|---|---|---|---|
| F-9 | P1.2 | Add `dramatiq>=2.1.0`, `opentelemetry-api>=1.36.0`, `opentelemetry-sdk>=1.36.0`, `opentelemetry-exporter-otlp-proto-grpc>=1.36.0` to `requirements.txt`. Verify by running `pytest tests/v6/test_{otel_propagate,sticky_connection,throttle,actors,broker,otel_init}_*.py` after a `pip uninstall` round-trip — tests must RUN, not skip. | **root_cause** — eliminates the silent-skip class entirely. |
| F-10 | P1.1 | Add a `dashboard/page.tsx:324` a11y guardrail test. Use `page.evaluate` to inject upload state OR POST a small fixture file to `/api/upload`. Assert axe-clean on the upload-list "remove" button. | **guardrail** — closes the cycle-2 verify recommendation's other half. |
| F-11 | P2.1 | Remove `# pragma: no cover` on `connection.py:37` (the except branch IS covered by `test_close_errors_are_logged_not_swallowed`). Coverage data should reflect reality. | **guardrail** — honesty in metrics. |
| Defer | P2.2 | Tighten color-contrast assertion specificity. Cosmetic. |
| Defer | P3.1 | F-8 destructive Button visual identity → design audit. Zero usages today. |
| Defer | P3.2..P3.6 | Cosmetic / acceptable trade-offs / intentional patterns. |

## Cycle-locking math (updated)

Per `REVIEW_BRIEF_FORMAT_v2.md`: lock = TWO consecutive APPROVE rounds (P1=0).
- Cycle 1: APPROVE_WITH_FIXES (P1=3) → F-1..F-6 → cycle 2.
- Cycle 2: APPROVE_WITH_FIXES (P1=1, fresh) → F-7+F-7b+F-8 → cycle 3.
- Cycle 3: APPROVE_WITH_FIXES (P1=1, fresh + new P2.3 root_cause) → **F-9+F-10+F-11+F-12** → cycle 4.
- Cycle 4 (target): clean APPROVE (P1=0).
- Cycle 5 (target): clean APPROVE (P1=0) → **LOCK**.

## Note on audit revision

The cycle-3 subagent rewrote the audit during its 16-min run. Initial mid-run snapshot showed P1=2 (one of which I addressed as F-9 — pinning deps in `requirements.txt`). The final audit consolidated to P1=1 (only F-7b half-complete) PLUS a fresh **P2.3 root_cause**: the CI workflow installs `requirements.txt` and runs ONLY Playwright e2e — no `pytest tests/v6/` step at all, so the new backend tests would silently skip on CI even with deps pinned.

F-9 (deps in legacy requirements.txt) is still correct AND defensive — it ensures any CI step that installs `requirements.txt` picks up the new deps. F-12 (added below) is the actual fix for cycle-3 P2.3.

**F-12 (root_cause):** new `pytest_v6_backend` job in `.github/workflows/web_ci.yml`. Installs `requirements-v6.txt` (canonical) and runs `pytest tests/v6/ --ignore=tests/v6/acceptance`. Verified locally: 237/237 PASS in 18.07s. Closes the LAW II "silent skip on CI" hazard.

Three cycles in, two more audit cycles needed minimum. Each cycle has cost ~$1-2 in subagent tokens; that's ~$8-12 total to lock.

## What the subagent is doing well

The cycle-3 audit has the strongest probes yet:
- `grep -iE "dramatiq|opentelemetry" requirements.txt` (returned NOTHING — primary-source evidence).
- Read `node_modules/@base-ui/react/esm/tooltip/utils/constants.js:1` directly to verify `OPEN_DELAY = 600` (cycle-2).
- `git show 3cf4737 -- outputs/audits/continuous/909eb4c_audit.md | diff` — byte-identity check on the audit-trail.
- Caught the half-complete F-7b regression gate by re-reading my own cycle-2 cross-review's verify recommendation against the diff.

This is the kind of fresh-eyes review the triangle is designed for.

## Closure

Executing F-9 + F-10 + F-11 in this turn. Counter logic: post-bb60495 batch is at 0c49d57 + 3bac322 (broker + actors backend coverage) = 2/5. F-9..F-11 = +3 commits → 5/5 → triggers cycle-4 subagent.
