# I-ux-001c sub-PR 8 — Compare v6 chrome (GH #896)

## Phase: BRIEF REVIEW (not diff review)

Repo equals polaris HEAD. Per CLAUDE.md §3.0: brief → brief APPROVE → diff → diff APPROVE → audit.

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (visual-only marketing-auth chrome, sub-PRs 4-7 pattern)

Rebuild `/compare` page header chrome to v6 marketing-auth lock. Sub-PR 8 of approximately 7+ for I-ux-001c.

Current `/compare` (347 LOC, single file `web/app/compare/page.tsx`, per I-ui-004 #543) is the run-vs-run comparison page (distinct from /benchmark). Two completed runs are selected → `compareRuns(l, r)` → ReportComparison rendering. ALL backend logic preserved verbatim.

v6 changes (header region only, lines ~94-104):
- Brand-red eyebrow "COMPARE · POLARIS CLINICAL RESEARCH" ABOVE the H1
- Display-weight H1 "Compare two runs side-by-side." (replacing "Compare two runs")
- Tightened subtitle locked verbatim: "Shared evidence, unique sources, contradiction counts — see what changes from one verified run to the next."

PRESERVED contracts:
- `data-testid="compare-page"` (existing test selector)
- `data-testid="comparison-result"`
- compareRuns + listCompletedRuns API calls
- All run-picker UI + comparison rendering
- AppShell chrome (NOT chromeless)

## CI test wiring (UNIQUE to this sub-PR)

`/compare` has NO existing `compare_g1_g8.spec.ts` file (no CI coverage today). Per the sub-PR 6 lesson (#892 follow-up), creating a standalone `compare_v6.spec.ts` would be CI-dead. So sub-PR 8 ADDS BOTH:

1. NEW `web/tests/e2e/compare_g1_g8.spec.ts` — establishes baseline CI coverage for /compare: G1 (one header + main), G2 (no dev-language), G8 (zero console errors), + v6 chrome cases (eyebrow + H1 + subtitle render).
2. UPDATE `.github/workflows/web_ci.yml` — add a single block enumerating the new spec, mirroring the existing dashboard_g1_g8.spec.ts block at line 185.

This brings /compare into CI parity with /home, /intake, /dashboard, /runs/[runId] etc.

## Operator-locked constraints

Brand-red 3 paths (all preserved):
1. Brand identity (NEW eyebrow)
2. Evidence-role T1 (not applicable to /compare)
3. Interactive affordance (existing text-primary on links)

Honest sovereignty — no "signed bundle" overclaim. NO new copy about signing.

## File plan

REBUILD
1. `web/app/compare/page.tsx` — header region (lines ~94-104):
   - Add brand-red eyebrow above the H1
   - Display H1 + tightened subtitle
   - Rest of the page (run-picker, compareRuns flow, ReportComparison rendering, ErrorState, LoadingState, EmptyState) PRESERVED VERBATIM

NEW
2. `web/tests/e2e/compare_g1_g8.spec.ts` — G1 + G2 + G8 + v6 chrome cases (mirror dashboard_g1_g8.spec.ts pattern). Mock `**/api/v6/runs**` to avoid auth-gated listCompletedRuns race.

UPDATE
3. `.github/workflows/web_ci.yml` — add 1 block to enumerate `tests/e2e/compare_g1_g8.spec.ts` (model: copy the dashboard_g1_g8 block at line 184-185, swap names).

## Files I have ALSO checked

- web/components/app_shell.tsx — /compare in authed routes; no change
- web/lib/api.ts — compareRuns + listCompletedRuns unchanged
- web/app/dashboard/page.tsx — was sub-PR 6; no cross-reference to /compare
- .github/workflows/web_ci.yml — line 185 has the model dashboard_g1_g8 block

## Brief-review check requests

- `scope_visual_only`: PASS / FAIL — only header chrome changes; compare logic preserved
- `existing_testids_preserved`: PASS / FAIL — compare-page, comparison-result preserved
- `appshell_chrome_preserved`: PASS / FAIL — /compare stays in AppShell
- `ci_wired_via_yaml_update`: PASS / FAIL — web_ci.yml updated to enumerate the new compare_g1_g8 spec; not standalone dead
- `no_signed_bundle_overclaim`: PASS / FAIL — no "signed bundle" copy added

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
  ci_wired_via_yaml_update: PASS | FAIL_with_detail
  no_signed_bundle_overclaim: PASS | FAIL_with_detail
```
