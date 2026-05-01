# Audit — `97b9c1f` batch (4 commits, post-`bb60495` F-9/F-10/F-11 + queue coverage)

**Verdict:** APPROVE_WITH_FIXES
**Findings:** P0=0  P1=1  P2=2  P3=4

Four-commit window: `0c49d57` (test_broker, 9 tests) → `3bac322` (test_actors, 8 tests) → `466b662` (F-9 deps pin) → `97b9c1f` (F-10 dashboard a11y + F-11 pragma removal + cycle-3 audit). Skipping `07e6fb9` (brief-only meta).

This is cycle 4 — the first cycle that could legitimately lock after a clean APPROVE. The bar is high; the locking criterion is two consecutive clean APPROVE.

## Pre-flight

- Read: cycle-1/2/3 audits + cross-reviews; per-commit briefs `0c49d57_broker_coverage.md`, `466b662_f9_requirements_pin.md`, `97b9c1f_f10_f11_dashboard_a11y_pragma.md` (no `3bac322_actors_coverage.md` brief was committed); `git show` for all 4 commits; full diffs of `tests/v6/test_{broker,actors}.py`, `requirements.txt`, `web/tests/e2e/accessibility.spec.ts`, `src/polaris_v6/queue/middleware/connection.py`.
- Read source: `src/polaris_v6/queue/{broker,actors}.py`, `src/polaris_v6/api/upload.py`, `web/app/dashboard/page.tsx:300-330`, `web/app/globals.css:50-110`.
- Ran live: full `tests/v6/` suite (237 pass + 7 xfail + **1 fail** — see P1.1); `web/tests/e2e/accessibility.spec.ts` (30/30 pass); F-10 alone across 3 browsers (3/3 pass in 10s); both servers up at `127.0.0.1:8000` + `:3738`.
- Grepped: `text-destructive` and `bg-destructive` (zero hits in `web/`); `pragma: no cover` (zero hits in `src/polaris_v6/`); `importorskip` cross-checked against `requirements.txt`.

## Per-criterion forced enumeration

- C-broker [test_broker.py 9 tests]: PASS in isolation. `dramatiq.set_broker(...)` is called twice (lines 35, 89) without restoration — leaks across tests, but no observed regression. See P3.1.
- C-actors [test_actors.py 8 tests]: **PASS in isolation; FAILS the v6 suite via test_dramatiq_acceptance.py contamination.** See **P1.1** — the module-level `get_broker(use_stub=True)` at line 25 runs at collection time and binds `@dramatiq.actor` decorators to a stub broker that the acceptance fixture's NEW broker doesn't know about.
- C-F-9 [requirements.txt deps pin]: NONE. All three `importorskip` targets in cycle-4 scope (`dramatiq`, `opentelemetry`, `opentelemetry.sdk`) now have a pin. `opentelemetry-exporter-otlp-proto-grpc>=1.36.0` was already a chromadb transitive dep — making it explicit is correct, not duplicative. See P3.2.
- C-F-10 [dashboard upload-list a11y]: NONE for correctness. Real `setInputFiles` → POST `/api/upload` → `<li>` renders with the `remove` button → axe-clean. Verified the regression-gate property: `--destructive: oklch(0.577 0.245 27.325)` ≈ #d34a3a on `--background: oklch(1 0 0)` (white) gives ~4.04:1 — fails AA's 4.5:1 minimum. If F-7's `text-destructive → text-foreground` revert ever lands, this test fires in light mode (Playwright default).
- C-F-11 [pragma removal]: NONE. `connection.py:37` no longer carries the pragma; replaced with a comment pointing at `test_close_errors_are_logged_not_swallowed`. `grep -rn "pragma: no cover" src/polaris_v6/` returns ZERO. Coverage data now reflects reality.
- C-audit-trail [bb60495_audit.md state]: PARTIAL CONCERN. The committed copy at 97b9c1f shows P1=2 (correct cycle-3 state). The working-tree copy has been modified to P1=1 — uncommitted, so audit-trail integrity at HEAD is intact, but the post-hoc edit is a smell. See P2.1.

## P0

NONE. No silent failure to production paths, no broken auth, no data loss, no security hole. F-7/F-8/F-9/F-10/F-11 all materially shipped; the upload endpoint behaves; a11y regression gate fires correctly.

## P1

**P1.1 — `test_actors.py:25` module-level `get_broker(use_stub=True)` introduces a test-suite regression.** Empirically verified, order-independent:

```
$ PYTHONPATH=src python -m pytest tests/v6/ -q
... 1 failed, 237 passed, 7 xfailed in 19.39s
FAILED tests/v6/acceptance/test_dramatiq_acceptance.py::test_scenario_1_enqueue_and_complete
- dramatiq.errors.QueueNotFound: default
```

Reproduced in both orderings:
- `pytest tests/v6/test_actors.py tests/v6/acceptance/test_dramatiq_acceptance.py` → FAIL
- `pytest tests/v6/acceptance/test_dramatiq_acceptance.py tests/v6/test_actors.py` → FAIL (because pytest collects modules first, runs second)
- `pytest tests/v6/acceptance/test_dramatiq_acceptance.py` (alone) → PASS

**Root cause.** `tests/v6/test_actors.py` lines 23-25 import `get_broker` and call `get_broker(use_stub=True)` at MODULE-LEVEL. Module-level code runs at pytest collection time. This calls `dramatiq.set_broker(broker_A)`, which makes `broker_A` the active global. The next line then imports `polaris_v6.queue.actors`, whose `@dramatiq.actor` decorators bind the actor queues into `broker_A`'s queue map.

When `tests/v6/acceptance/test_dramatiq_acceptance.py::test_scenario_1` later runs, its `stub_broker` fixture creates `broker_B` and calls `dramatiq.set_broker(broker_B)`. `broker_B` is now the global broker, but the actor queue declarations remain pinned to `broker_A`. So `broker.join("default", ...)` on `broker_B` raises `QueueNotFound: default`.

The commit message for `3bac322` claims "All 8 PASS in 0.88s. v6 test count: 237 → 245." That's accurate **in isolation** — the new tests do pass. But the same suite-level claim hides a regression: pre-commit, the v6 suite was 228 pass + 7 xfail (per cycle-3 audit's local-run section). Post-commit the suite shows 237 pass + 1 fail + 7 xfail. The acceptance-test regression was masked because the briefs ran tests in isolation, not as a suite.

**Fix path.** Move `get_broker(use_stub=True)` into a module-scoped fixture (or `conftest.py` autouse with cleanup) so the broker is constructed inside test scope and the global is reset between modules. Or refactor `polaris_v6.queue.actors` so actor decoration doesn't depend on broker-construction order. Tag: **root_cause** — the test contract is genuinely incompatible with the existing acceptance fixture; this is not a "rerun in clean state" workaround.

This is a fresh regression introduced by the cycle-4 batch and exactly the kind of finding the locking criterion is designed to catch.

## P2

**P2.1 — Working-tree edit of committed audit `bb60495_audit.md` (P1=2 → P1=1).** The audit was committed at 97b9c1f with header `**Findings:** P0=0  P1=2  P2=2  P3=4`. Working tree currently shows `P0=0  P1=1  P2=3  P3=4` and a substantially shortened pre-flight section. `git status` shows ` M outputs/audits/continuous/bb60495_audit.md`. The HEAD audit-trail integrity is intact (the commit itself is byte-correct), but post-hoc rewriting committed audits is a smell — the audit history should be append-only or commit-the-edit. Tag: **guardrail** — convention.

**P2.2 — `3bac322_actors_coverage.md` per-commit brief was never committed.** `ls .codex/continuous/` shows briefs for `0c49d57`, `466b662`, `97b9c1f` but NOT for `3bac322`. The cycle's review-brief discipline calls for one brief per commit. Cosmetic but breaks the chain. Tag: **guardrail**.

## P3

**P3.1 — `test_broker.py` global-broker leakage.** Same class of issue as P1.1, materially less impactful: `test_use_stub_explicit_true_returns_stubbroker` and `test_set_broker_registers_globally` call `dramatiq.set_broker(...)` without restoration. No observed regression today (broker tests don't decorate actors), but the same fixture-scoping fix for P1.1 should also restore the global broker at test exit.

**P3.2 — `opentelemetry-exporter-otlp-proto-grpc` was already a chromadb transitive.** Pinning it in `requirements.txt` is "make implicit explicit," which is correct for Phase 0 documentation, but a cycle-5 reviewer might flag it as duplicative if they don't read this. The pin doesn't add a new transitive (grpcio 1.74 + protobuf 6.33 + googleapis-common-protos already installed via chromadb).

**P3.3 — F-10 doesn't clean up the server-side upload record.** `src/polaris_v6/api/upload.py:47` `_UPLOAD_TABLE` accumulates every test run's `polaris_a11y_probe.txt`. Module-level dict, in-memory only, server restart clears. Acceptable for stub stage; flag for production. (Same finding as `97b9c1f` brief P1.)

**P3.4 — Cycle-3 deferred items unchanged.** Re-evaluated each:
- P2.2 (color-contrast assertion specificity): no change. Still acceptable.
- P3.1 (destructive button visual identity): no change; still zero usages.
- P3.2 (OTEL TracerProvider fixture leak): no change; still pre-existing pattern.
- P3.5 (.gitignore exemption breadth): no change. `outputs/audits/v25/`, `v26/`, `v27/*.md` still untracked-visible. None escalated by cycle-4 batch.

## Cross-cycle integrity

Cycle-1 P2.2 (install bloat), cycle-1 P2.4 (cross-platform lockfile), cycle-2 P2.2 (`testIgnore` Linux-only): unchanged. F-9's dep-pin doesn't fix cycle-1 P2.2 (which was about minimal subset extraction); it fixes the orthogonal "not pinned" issue. Both still valid concerns; neither blocks lock.

Audit-trail at `outputs/audits/continuous/{4fe03f7,909eb4c,bb60495}_*.md` all tracked. `.gitignore` exemption working as intended for the `continuous/` subdir.

## Reviewer independence statement

I read actual diffs (`git show <sha>` for all 4 commits + `git ls-files` for briefs + working-tree diff for `bb60495_audit.md`), grepped the codebase mechanically (3 distinct patterns under `web/` + 2 under `src/polaris_v6/`), inspected each new test file end-to-end, **ran the full v6 test suite live and observed the regression** (237 pass + 1 fail + 7 xfail), ran the F-10 a11y test alone across 3 browsers, cross-checked `requirements.txt` against `importorskip` targets, computed contrast ratios from `globals.css` oklch values to verify F-10 is a real regression gate.

The P1.1 finding is from primary-source pytest output, reproduced in two orderings, with root cause identified at the line-and-mechanism level.

AGREE: F-7/F-8 destructive-token fix shipped clean (zero hits); F-9 closes the silent-skip class; F-10 is a real regression gate (contrast math confirms); F-11 pragma removal is honest (zero remaining); audit-trail at HEAD is byte-correct.

DISAGREE: cycle-3 cross-review predicted "cycle 4 (target): clean APPROVE." The new test_actors.py introduces a real cross-test regression that masks itself when the new tests are run alone. The locking math now shifts: cycle-5 needs to be the first clean APPROVE, cycle-6 the second.

**Verdict: APPROVE_WITH_FIXES.** P0 = 0; nothing breaks production today (acceptance test was already xfail-heavy and scenario_1 is a stub-broker drainage test, not a production codepath). One P1 (root_cause: fix the module-level side-effect in test_actors.py) MUST land before locking. Cycle-5 cannot lock; the consecutive-APPROVE criterion now requires cycle-5 clean + cycle-6 clean.
