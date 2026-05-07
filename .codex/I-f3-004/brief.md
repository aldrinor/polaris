# Codex Brief Review — I-f3-004 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-004 — Backend: sovereignty CI test
**Phase:** 1 / **Feature:** F3
**LOC budget:** 80 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Add `.github/workflows/sovereignty.yml` that runs the existing sovereignty test suite (router + classification) on every PR. Acceptance per breakdown: "CI fails on intentional violation" — i.e., if anyone ever weakens the router or removes the EXTERNAL_LEAK_FORBIDDEN guard, CI fails.

## Substrate (HONEST)

- I-f3-002 + I-f3-003 (just merged): `tests/polaris_graph/sovereignty/test_classification.py` (7 tests) + `tests/polaris_graph/sovereignty/test_router.py` (9 tests). Both use `PYTHONPATH=src python -m pytest`.
- `.github/workflows/web_ci.yml` exists; per existing pattern.
- Per breakdown the workflow runs the sovereignty tests AND a "negative" red-team test that intentionally tries to leak a CLIENT doc through the router and asserts the router blocks it (i.e., proves the gate is working in CI, not just locally).

## Acceptance criteria (binding)

1. **`.github/workflows/sovereignty.yml`** (NEW): GitHub Actions workflow.
   - Triggers: `on: pull_request` + `on: push: branches: [polaris, main]`.
   - Single job `sovereignty-tests` running on `ubuntu-latest`.
   - Steps:
     1. `actions/checkout@v4`.
     2. `actions/setup-python@v5` with Python 3.11.
     3. Install: `pip install pytest`.
     4. Run `PYTHONPATH=src python -m pytest tests/polaris_graph/sovereignty/ -v` — exits non-zero if ANY sovereignty test fails (proves classification + router contracts hold).
   - LOC: ~30.

2. **`tests/polaris_graph/sovereignty/test_red_team.py`** (NEW): an intentional red-team test that proves the gate fires on violation. 3 tests:
   - `test_red_team_client_doc_blocked`: simulates an outbound payload containing a CLIENT doc; asserts `assert_safe_for_external` raises `SovereigntyViolationError`. Models the threat scenario "an upstream caller forgot to filter" — the router catches it.
   - `test_red_team_can_real_blocked`: same for CAN_REAL.
   - `test_red_team_unknown_default_deny_blocked`: same for unclassified item (UNKNOWN default-deny).
   - Each test asserts the specific classification appears in the error message — proves the gate identifies WHICH classification violated. LOC: ~40.

## Planned diff shape

```
.github/workflows/sovereignty.yml                       NEW +30
tests/polaris_graph/sovereignty/test_red_team.py        NEW +40
```

LOC: +70 net. Under CHARTER §1 200-cap by 130; under breakdown's 80-LOC budget by 10.

## Out of scope (deferred)

- Frontend drag-drop upload zone → I-f3-005.
- Network-layer interceptor (e.g., wrapping httpx) — out of scope; router is policy-library-only per I-f3-003 design.

## Risks for Codex Red-Team

1. **CI workflow scope.** `on: pull_request` ensures the test runs before merge. `on: push` on polaris+main provides defense-in-depth (catches anyone bypassing PR review).

2. **Test name pattern `test_red_team_*`.** Distinct from existing `test_router.py` so it's clear these are red-team violation tests (not happy-path).

3. **Each red-team test asserts specific classification in error message.** If someone weakens `EXTERNAL_LEAK_FORBIDDEN` to remove e.g. CAN_REAL, `test_red_team_can_real_blocked` fails with no `CAN_REAL` in error → CI fails. Strong signal.

4. **Python 3.11 in CI matches development.** Local dev uses 3.13 per system, but 3.11 is the minimum supported across the repo (per existing workflows).

5. **`pip install pytest`** is the minimal install — no project deps needed for the sovereignty tests since they only depend on the canonical Python stdlib + `pytest` + the `polaris_graph.sovereignty.*` modules (which have zero external deps).

6. **No new package.json / requirements.txt dep.**

7. **CHARTER §1 LOC cap.** 70 net.

8. **Workflow file LOC.** YAML is verbose but ~30 lines is enough for the single job + steps. Readable.

9. **`if: false` red-team mode NOT used** — the red-team tests are POSITIVE assertions that the gate fires. No skipped tests; every test runs every CI run.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
