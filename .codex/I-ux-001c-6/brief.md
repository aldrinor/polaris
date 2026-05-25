# I-ux-001c sub-PR 6 — Dashboard v6 chrome (GH #891)

## Phase: BRIEF REVIEW (not diff review)

You are reviewing the SPEC for an upcoming diff. Repo on `bot/I-ux-001c-sub-pr-6-dashboard` equals `polaris` HEAD. Per CLAUDE.md §3.0: brief → brief APPROVE → diff → diff APPROVE → audit.

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (mirror of sub-PR 4/5 pattern — visual-only marketing-auth chrome)

Rebuild `/dashboard` page header chrome to v6 marketing-auth lock. Sub-PR 6 of approximately 7 for I-ux-001c.

Current `/dashboard` (190 LOC, single file `web/app/dashboard/page.tsx`, per I-p2-022 #761) is MONITORING-ONLY (no run-start; that's at /intake → /plan). It lists recent completed runs via real `listCompletedRuns()` (GET /api/v6/runs?status=completed) and links each to its inspector report. ALL this logic preserved verbatim.

v6 changes (header region only, lines ~100-119 of current page.tsx):

- Brand-red eyebrow ("RUNS · POLARIS CLINICAL RESEARCH") added above the H1
- Display H1 ("Your recent runs.") replacing the small "Runs"
- Tightened subtitle locked verbatim: "Open one to replay the proof, claim by claim — every brief carries its own signed bundle."
- Start-new-research button kept in same row position (right side) — preserves the existing CTA

PRESERVED contracts:
- `data-testid="dashboard-page"` (existing test selector, multiple tests depend on it)
- `data-testid="dashboard-start-run"`, `data-testid="runs-list"`, `data-testid="run-row-${runId}"` (run-rows test depends)
- `listCompletedRuns` API call + LoadingState + ErrorState + EmptyState
- All run-row rendering + verdict pill + inspector deep-links
- AppShell chrome (NOT chromeless)

## Operator-locked constraints (carried forward)

Brand-red `#c8102e` THREE authorized paths (all preserved):
1. Brand identity (NEW eyebrow + existing Start-new-research CTA)
2. Evidence-role semantic (TIER_DOT) — not applicable to /dashboard
3. Interactive affordance (existing text-primary on links + states)

Honest sovereignty wording preserved.

## File plan (surgical)

REBUILD
1. `web/app/dashboard/page.tsx` — header row (lines ~100-119) only:
   - Add brand-red eyebrow above the H1
   - Display H1 + tightened subtitle
   - Start-new-research CTA in same row position (right side)
   - Rest of the page (runs-list, LoadingState, ErrorState, EmptyState, run-row rendering, verdict pills, inspector links) PRESERVED VERBATIM

NEW
2. `web/tests/e2e/dashboard_v6.spec.ts` — 2 Playwright cases:
   - Eyebrow + H1 + subtitle render with v6 copy
   - Start-new-research link still navigates to /intake
   Mocks `**/api/v6/runs**` so the auth-gated listCompletedRuns (which calls `/api/v6/runs?status=completed&limit=50`) doesn't race. (Codex brief iter-1 P1 fix: previous `**/api/runs**` glob didn't match the actual BACKEND_URL + endpoint.)

## Files I have ALSO checked

- web/components/app_shell.tsx — /dashboard in authed routes; no change
- web/components/app_shell_gate.tsx — /dashboard NOT chromeless
- web/lib/api.ts — listCompletedRuns contract unchanged
- web/tests/e2e/demo_journey.spec.ts — uses dashboard-page testid (preserved)

## Brief-review check requests (`specific_check_responses`)

- `scope_visual_only`: PASS / FAIL — header chrome only; runs-list/states/run-rows preserved verbatim
- `existing_testids_preserved`: PASS / FAIL — dashboard-page, dashboard-start-run, runs-list, run-row-* preserved
- `appshell_chrome_preserved`: PASS / FAIL — /dashboard stays in AppShell
- `start_run_cta_preserved`: PASS / FAIL — Start-new-research → /intake link preserved with same testid in same row position
- `file_plan_surgical`: PASS / FAIL — single page rebuild + 1 test file

## Output schema (BIND)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  scope_visual_only: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
  appshell_chrome_preserved: PASS | FAIL_with_detail
  start_run_cta_preserved: PASS | FAIL_with_detail
  file_plan_surgical: PASS | FAIL_with_detail
```
