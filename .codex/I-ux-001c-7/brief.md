# I-ux-001c sub-PR 7 — /runs/[runId] v6 chrome (GH #894)

## Phase: BRIEF REVIEW (not diff review)

You are reviewing the SPEC for an upcoming diff. Repo equals `polaris` HEAD. Per CLAUDE.md §3.0: brief → brief APPROVE → diff → diff APPROVE → audit.

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (mirror of sub-PRs 4/5/6 visual-only pattern)

Rebuild `/runs/[runId]` page header chrome to v6 marketing-auth lock. Sub-PR 7 of approximately 7 for I-ux-001c.

Current `/runs/[runId]` (270 LOC, single file `web/app/runs/[runId]/page.tsx`, per I-cd-025 #615) is the LIVE RUN PROGRESS page. SSE subscription via `subscribeToRun`; cancel button; bundle export; question display as H1; status pill; queued time; followup panel; RunProgress component. ALL this logic preserved verbatim.

v6 changes (header region only, current lines ~160-180):

- Brand-red eyebrow PROMOTED: existing "Run {runId}" eyebrow (`text-muted-foreground`) → `text-primary` (brand red) + same tracking. Adds a SECOND eyebrow line ABOVE it: "LIVE RUN · POLARIS CLINICAL RESEARCH" (also `text-primary`) — establishes the category match with /home, /intake, /source_review, /plan, /dashboard v6 chrome.
- Display H1: existing `text-2xl sm:text-3xl font-semibold` → `text-3xl sm:text-4xl font-bold` (the question text stays the dynamic content; only typographic weight bumps)
- Metadata p (template/status/queued) preserved verbatim
- Action row (Export bundle + New run buttons) preserved in same position
- Loading + Error fallbacks for H1 preserved

PRESERVED contracts:
- `data-testid="runs-runid-page"` (existing test selector; runs_runid_g1_g8.spec.ts depends)
- getRun + subscribeToRun (SSE) + cancelRun + getBundle + downloadBundleAsJson
- TERMINAL_STATUSES gate on Cancel button
- ErrorState component + status pill
- FollowupPanel + RunProgress component imports + props
- AppShell chrome (NOT chromeless)

## Operator-locked constraints (carried forward)

Brand-red `#c8102e` three authorized paths (all preserved):
1. Brand identity (NEW category eyebrow + PROMOTED run-id eyebrow)
2. Evidence-role T1 semantic — N/A on /runs/[runId]
3. Interactive affordance (existing text-primary on links + Export-bundle button)

Honest sovereignty wording preserved. NO "signed bundle" overclaim (use "audit bundle" or "verified bundle" only when GPG path is live; sub-PR 6 iter-4 carry-forward).

## File plan (surgical)

REBUILD
1. `web/app/runs/[runId]/page.tsx` — header region (current lines ~160-180):
   - Add brand-red category eyebrow ABOVE the existing "Run {runId}" eyebrow
   - Promote existing "Run {runId}" eyebrow to brand-red
   - Bump H1 to display-weight typography
   - Rest of the page (action row, vetted-question metadata, FollowupPanel, RunProgress, SSE subscribe, cancel, bundle export, error states) PRESERVED VERBATIM

UPDATE
2. `web/tests/e2e/runs_runid_g1_g8.spec.ts` — add v6 chrome cases at the end of the existing CI-run spec (matches sub-PR 6 pattern; web_ci.yml line 192 runs this file):
   - v6 chrome: brand-red category eyebrow + brand-red run-id eyebrow + display H1 render
   - v6 chrome: Export-bundle + New-run action row preserved
   Mock `**/api/v6/runs/**` for getRun + SSE so the test doesn't race.

## Files I have ALSO checked

- web/components/app_shell.tsx — `/runs/[runId]` in authed routes; no change
- web/components/app_shell_gate.tsx — `/runs/[runId]` NOT chromeless
- web/lib/api.ts — getRun/subscribeToRun/cancelRun/getBundle unchanged
- web/app/runs/[runId]/components/run_progress.tsx — UNCHANGED (SSE-driven content)
- web/app/runs/[runId]/components/followup_panel.tsx — UNCHANGED
- web/tests/e2e/runs_runid_g1_g8.spec.ts — IS in web_ci.yml line 192 (CI-run); the right destination for the v6 cases

## Brief-review check requests (`specific_check_responses`)

- `scope_visual_only`: PASS / FAIL — header region only; SSE/cancel/bundle/run-progress preserved verbatim
- `existing_testids_preserved`: PASS / FAIL — runs-runid-page preserved; sub-components untouched
- `appshell_chrome_preserved`: PASS / FAIL — /runs/[runId] stays in AppShell
- `dynamic_h1_preserved`: PASS / FAIL — H1 content stays the dynamic question text (with loading/error fallback) — only typographic weight changes
- `v6_tests_ci_wired`: PASS / FAIL — v6 cases added to runs_runid_g1_g8.spec.ts (CI-run per web_ci.yml:192), not a standalone dead file
- `no_signed_bundle_overclaim`: PASS / FAIL — no "signed bundle" copy added that overclaims GPG signing

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
  dynamic_h1_preserved: PASS | FAIL_with_detail
  v6_tests_ci_wired: PASS | FAIL_with_detail
  no_signed_bundle_overclaim: PASS | FAIL_with_detail
```
