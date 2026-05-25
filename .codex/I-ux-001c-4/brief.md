# I-ux-001c sub-PR 4 — Source Review v6 (GH #887)

## Phase: BRIEF REVIEW (not diff review)

You are reviewing the SPEC for an upcoming diff. Repo on `bot/I-ux-001c-sub-pr-4-source-review` currently equals `polaris` HEAD — no implementation yet. Per CLAUDE.md §3.0 5-artifact triple: brief → brief APPROVE → diff → diff APPROVE → audit. This is step 2.

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (visual-only marketing-auth chrome evolution)

Rebuild `/source_review` page chrome to the I-ux-001d v6 design lock. Sub-PR 4 of approximately 7 for I-ux-001c.

The current `/source_review` (288 LOC, single file `web/app/source_review/page.tsx`, shipped by I-p2-031 #770) has the right authoritative source-set logic (listTemplates → GET /api/v6/templates from real config/v6_templates/*.json, per-tier adequacy via min_sources_per_tier, TierCards). v6 changes are visual-only:

- Brand-red eyebrow ("SOURCES · POLARIS CLINICAL RESEARCH") replacing the bare "← Edit question" link as the page's leading visual
- Display-weight H1 ("Review the sources POLARIS will check.") replacing the small "Review the source set"
- Tightened subtitle (one sentence)
- "← Edit question" link MOVED into the eyebrow row (right side) so it remains accessible but doesn't lead the page
- TierCards visual treatment unchanged (already clean v6 styling per I-p2-031)
- Continue-to-plan CTA preserved
- All substantive logic UNCHANGED: listTemplates, asTemplateId, TIERS, TIER_DOT, TIER_LABEL, prettyDomain, error state, loading state, retry path

PRESERVED contracts:
- `data-testid="source-review-page"` (existing test selector)
- `/plan?q=<encoded>&template=<id>` deep-link (Continue button)
- `/intake?q=<encoded>` deep-link (Edit question)
- AppShell chrome (NOT chromeless; like /intake)

## Operator-locked constraints

- Brand red `#c8102e` ONLY at the brand-red eyebrow + Continue CTA
- Honest sovereignty wording (Canadian-hosted, built toward sovereign deployment) — same posture as v6 home + intake
- No fabricated metrics: the page currently says "the actual sources are retrieved + adequacy-checked during the run" — preserved verbatim (LAW II honest-fail)

## File plan (surgical)

REBUILD
1. `web/app/source_review/page.tsx` — header chrome only:
   - Brand-red eyebrow + display H1 + tightened subtitle (the visual rebuild surface)
   - "← Edit question" link moved into eyebrow row (right side)
   - Rest of the page (TierCards section, Continue CTA, loading + error states, all useState/useEffect logic) PRESERVED VERBATIM

NEW
2. NEW `web/tests/e2e/source_review_v6.spec.ts` — 2 cases:
   - Eyebrow + H1 + subtitle render with v6 copy
   - Edit-question link still navigates to `/intake?q=<encoded>` (preserves the back-link behavior)

NO CHANGES needed to:
- web/lib/api.ts (listTemplates contract unchanged)
- config/v6_templates/*.json (real source set unchanged)
- Any other source_review-related tests if present

## Files I have ALSO checked

- web/components/app_shell.tsx — `/source_review` is in the authed routes set; no change
- web/components/app_shell_gate.tsx — `/source_review` is NOT chromeless
- web/lib/api.ts — listTemplates returns TemplateContent; unchanged
- web/app/intake/components/intake_form.tsx — links to /source_review?q=...; unchanged (matches sub-PR 3 preserved-behavior contract)
- web/app/plan/page.tsx — receives /plan?q=...&template=... from this page; unchanged

## Lessons applied from sub-PR 3 iter-3

- Visual-only scope from the start (no auto-domain chip or synthetic metrics that violate LAW II)
- No backend changes
- Preserve scope_decision_view + downstream handoff
- Existing testids preserved; existing tests pass unchanged

## Brief-review check requests (`specific_check_responses`)

- `scope_visual_only`: PASS / FAIL — spec keeps changes to header chrome only; no source-set logic, no fabricated metrics, no contract changes
- `existing_test_compat`: PASS / FAIL — `data-testid="source-review-page"` selector preserved; `/intake?q=<encoded>` back-link preserved; `/plan?q=<encoded>&template=<id>` forward-link preserved
- `appshell_chrome_preserved`: PASS / FAIL — `/source_review` continues to render inside AppShell (NOT chromeless)
- `file_plan_surgical`: PASS / FAIL — single file rebuild + 1 new test file; no orphan files; no "while we're at it" scope creep

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
  existing_test_compat: PASS | FAIL_with_detail
  appshell_chrome_preserved: PASS | FAIL_with_detail
  file_plan_surgical: PASS | FAIL_with_detail
```
