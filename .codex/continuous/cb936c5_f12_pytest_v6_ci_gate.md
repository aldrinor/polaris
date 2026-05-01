# Per-commit Codex brief — `cb936c5`

**Commit:** `cb936c5 PL: v6.2 F-12 root_cause — pytest tests/v6/ CI gate (cycle-3 P2.3)`
**Format:** v2 minimal
**Files changed (2):**
- `.github/workflows/web_ci.yml` (+45/-1) — new `pytest_v6_backend` job + widened trigger paths
- `outputs/audits/continuous/bb60495_cross_review.md` (+10/-1) — added F-12 entry + audit-revision note

## What this commit does

Closes cycle-3 audit P2.3 (the "missing CI runner" root_cause finding the subagent landed in the audit's final revision).

**Discovery sequence:**
1. I read the cycle-3 audit mid-run when the file first appeared on disk → saw P1=2 with one P1 being "missing dramatiq/opentelemetry deps in requirements.txt".
2. I shipped F-9 to address that — added the deps to legacy `requirements.txt`.
3. The cycle-3 subagent kept running for ~16 min and rewrote the audit. Final version has P1=1 + a fresh **P2.3 root_cause** that the CI workflow installs `requirements.txt` and runs ONLY Playwright e2e — NO `pytest tests/v6/` step at all.
4. The deps actually live in `requirements-v6.txt` (canonical Phase 0 Task 0.5 pin file). My F-9 was defensive duplication; the real fix is a CI step that installs `-v6.txt` AND runs the backend tests.

**F-12 implementation:**
- New `pytest_v6_backend` job. Triggers on `src/polaris_v6/`, `tests/v6/`, `requirements*.txt`, and `web_ci.yml` changes (widened from `web/**` only).
- Sets up Python 3.13 with pip cache.
- Installs `requirements-v6.txt` (canonical pinned source).
- Runs `PYTHONPATH=src pytest tests/v6/ --ignore=tests/v6/acceptance -q --strict-markers --no-header`.
- Acceptance suite excluded — needs live broker (Phase 1+ cluster).

Verified locally with the EXACT CI command: **237/237 PASS in 18.07s**.

## Acceptance criteria

1. **The job actually runs the same command CI will run.** Not `pytest tests/v6/test_specific.py` cherry-picking — the full glob with the same flags. Verified by running it locally.
2. **`-v6.txt` is the canonical pin source.** Not `requirements.txt` (legacy). My F-9 dup is defensive; F-12 uses the right one.
3. **`needs: lint_format_typecheck_build`** — gated on static checks. Saves CI minutes when something obvious is broken.
4. **No mocking of pytest setup.** Real pip install, real PYTHONPATH, real test collection.
5. **Acceptance suite intentionally excluded** with a comment explaining why (live broker dependency).

## Codex focus

- **P0:** Will `pip install -r requirements-v6.txt` actually succeed on ubuntu-latest? `dramatiq[redis,watch]==2.1.0` requires the watchdog extra; `opentelemetry-instrumentation-fastapi==0.62b1` is a beta release. Both need verification on a fresh runner.
- **P1:** The `--strict-markers` flag means any pytest marker not registered in pytest.ini will fail the test. Verify our existing tests don't use unregistered markers.
- **P2:** No `--cov` flag. We're not gating coverage. Future enhancement: add `--cov=src/polaris_v6 --cov-report=term-missing --cov-fail-under=70`.

## Cross-review

Lands at `outputs/audits/continuous/cb936c5/cross_review.md`. **Counter at 5/5 in the post-bb60495 fix batch** — cycle-4 subagent currently running, will see this F-12 fix.
