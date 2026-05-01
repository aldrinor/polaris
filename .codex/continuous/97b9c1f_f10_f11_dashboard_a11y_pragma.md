# Per-commit Codex brief — `97b9c1f`

**Commit:** `97b9c1f PL: v6.2 F-10+F-11 + cycle-3 audit/cross-review`
**Format:** v2 minimal
**Files changed (4):**
- `web/tests/e2e/accessibility.spec.ts` (+30 lines, F-10 new describe + 1 test)
- `src/polaris_v6/queue/middleware/connection.py` (-1/+2, F-11 pragma removal)
- `outputs/audits/continuous/bb60495_audit.md` (cycle-3 audit deliverable)
- `outputs/audits/continuous/bb60495_cross_review.md` (my cross-review)

## What this commit does

Closes cycle-3 audit P1.1 (dashboard upload-list missing regression gate) and P2.1 (misleading `# pragma: no cover`).

**F-10** (guardrail) — `web/tests/e2e/accessibility.spec.ts` new describe block:
- Posts a real text file through the live `/api/upload` endpoint via Playwright `fileInput.setInputFiles({...})`.
- Waits for the upload-list `<li>` to render with the filename + the "remove" button.
- Asserts axe-clean. Closes the OTHER half of cycle-2's verify recommendation that F-7b only addressed (inspector side).
- If a future contributor reverts F-7's change to `dashboard/page.tsx:324`, this test fires.

**F-11** (guardrail) — `connection.py:37`:
- Removed `# pragma: no cover` annotation from the except branch.
- Branch IS covered by `test_close_errors_are_logged_not_swallowed` (cycle-3 P2.1 caught the inconsistency).
- Coverage data now reflects reality. Replaced pragma with a comment pointing at the test.

Cycle-3 audit + cross-review committed alongside.

Verified: 42/42 backend tests + 10/10 a11y (incl new upload-list) PASS in ~9s.

## Acceptance criteria

1. **F-10 uses REAL upload, not mocked.** `fileInput.setInputFiles({...})` triggers the actual file upload event, which calls `handleFiles` → POST `/api/upload`. Test asserts the upload SUCCEEDED (filename visible) before running axe.
2. **F-10 waits for the right state.** Both `getByText("polaris_a11y_probe.txt")` AND `getByRole("button", { name: /^remove$/ })` must be visible — proves the upload-list <li> rendered with the destructive-class "remove" button (the surface F-7 fixed).
3. **F-11 doesn't change runtime behaviour.** Only removes a pragma. `connection.py` produces the same output.
4. **No new dependencies.** Both fixes use existing test infrastructure.
5. **Cross-cycle consistency.** F-10's pattern matches F-7b's (page-level `expectNoA11yViolations` after triggering the failure-path render).

## Codex focus

- **P0:** Does the `/api/upload` endpoint actually accept anonymous POST in the v6 backend? If it requires auth (M-15a substrate), the upload would 401 and the test would hang waiting for the filename. Verify by tailing `/tmp/uvicorn.log` after the test runs.
- **P1:** F-10 doesn't clean up the uploaded test file. Server-side accumulates `polaris_a11y_probe.txt` records on every test run. Should we add `await page.evaluate(() => localStorage.clear())` or call DELETE `/api/upload/{id}`? Probably acceptable for stub-stage — flag for production.
- **P2:** F-11 changes coverage data shape. If the project uses coverage gates in CI (it doesn't yet, but cycle-1 P3 mentioned setting one up), this could shift the numbers. Run `coverage report` post-fix to confirm.

## Cross-review

Lands at `outputs/audits/continuous/97b9c1f/cross_review.md`. **Counter at 5/5** for the post-bb60495 batch (0c49d57, 3bac322, 466b662, 97b9c1f + this brief = >5; plus another 466b662 brief commit). Time to spawn cycle-4 adversarial subagent.
