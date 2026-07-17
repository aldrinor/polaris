# I-ux-001c sub-PR 5 — Plan Review v6 chrome (GH #889)

## Phase: BRIEF REVIEW (not diff review)

You are reviewing the SPEC for an upcoming diff. Repo on `bot/I-ux-001c-sub-pr-5-plan-review` currently equals `polaris` HEAD. Per CLAUDE.md §3.0: brief → brief APPROVE → diff → diff APPROVE → audit. This is step 2.

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (mirror of sub-PR 4 pattern — visual-only marketing-auth chrome)

Rebuild `/plan` page header chrome to v6 marketing-auth lock. Sub-PR 5 of approximately 7 for I-ux-001c.

Current `/plan` (362 LOC, single file `web/app/plan/page.tsx`, per I-p2-015 #754) is the run-start surface (intake → source_review → plan → run). On mount it re-runs the FULL `runIntake` gate; "Start research run" is enabled only for in_scope + disambiguation-resolved questions; `createRun` POSTs to the backend on submit. ALL this logic preserved verbatim.

v6 changes (header chrome only, lines ~219-238 of current page.tsx):

- Brand-red eyebrow ("PLAN · POLARIS CLINICAL RESEARCH") replacing the bare "← Edit question" link as the page's leading visual
- "← Edit question" link MOVED into the eyebrow row (right side)
- Display H1 ("Confirm the plan before the run.") replacing the small "Review the plan"
- Tightened subtitle locked verbatim: "Re-checked end-to-end — POLARIS will only start the run when the question, scope, and template are all clear."

PRESERVED contracts:
- `data-testid="plan-page"` (existing test selector)
- `data-testid="plan-blocked"`, `data-testid="plan-concurrent"`, `data-testid="plan-start-run"`
- `runIntake` + `runDisambiguation` + `createRun` + ConcurrentRunError handling — all preserved verbatim
- `/intake` back-link deep-link preserved
- AppShell chrome preserved (NOT chromeless)
- All PLAN_STEPS content + Vetted-question card + Start-run button — preserved verbatim

## Operator-locked constraints (carried forward, sub-PR 4 final)

Brand-red `#c8102e` has THREE authorized usage paths, all preserved:
1. Brand identity (NEW eyebrow + existing Start-run CTA via Button variant=default + decorative)
2. Evidence-role T1 semantic (TIER_DOT in source_review/plan if used) — not applicable to /plan in this PR
3. Interactive affordance (text-primary on existing links + retry buttons)

Honest sovereignty wording preserved (Canadian-hosted; LLM via OpenRouter-US disclosed at /transparency).

## File plan (surgical, single page + 1 NEW test)

REBUILD
1. `web/app/plan/page.tsx` — header chrome only (lines ~219-238 region):
   - Add brand-red eyebrow + display H1 + tightened subtitle
   - Move "← Edit question" link into eyebrow row
   - Rest of the page (vetted-question card, plan steps, Start-run flow, error/concurrent/blocked states) PRESERVED VERBATIM

NEW
2. `web/tests/e2e/plan_v6.spec.ts` — 2 Playwright cases:
   - Eyebrow + H1 + subtitle render with v6 copy
   - Edit-question link still navigates to /intake (preserves back-link)
   Mocks the runIntake endpoint via page.route so the auth-gated re-check doesn't race.

## Files I have ALSO checked

- web/components/app_shell.tsx — `/plan` in authed routes; no change
- web/components/app_shell_gate.tsx — `/plan` NOT chromeless
- web/lib/api.ts — runIntake, runDisambiguation, createRun, ConcurrentRunError all preserved
- web/app/runs/[runId]/page.tsx — receives router.push from /plan on createRun success; no change
- web/app/intake/components/intake_form.tsx — links to /source_review not /plan; no change
- web/app/source_review/page.tsx — links to /plan via Continue CTA; no change

## Brief-review check requests (`specific_check_responses`)

- `scope_visual_only`: PASS / FAIL — header chrome only; runIntake/createRun/error states preserved verbatim
- `existing_testids_preserved`: PASS / FAIL — plan-page, plan-blocked, plan-concurrent, plan-start-run preserved
- `appshell_chrome_preserved`: PASS / FAIL — /plan stays in AppShell
- `back_link_preserved`: PASS / FAIL — /intake back-link preserved (moved to eyebrow row, same href)
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
  back_link_preserved: PASS | FAIL_with_detail
  file_plan_surgical: PASS | FAIL_with_detail
```
