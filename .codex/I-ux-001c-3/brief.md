# I-ux-001c sub-PR 3 — Intake v6 (GH #884)

## Phase: BRIEF REVIEW (not diff review)

**You are reviewing the SPEC for an upcoming code diff, not the diff itself.** The repo on this branch (`bot/I-ux-001c-sub-pr-3-intake`) currently equals `polaris` HEAD — no implementation has happened yet. Per CLAUDE.md §3.0 the 5-artifact triple is: **brief → brief APPROVE → diff → diff APPROVE → audit**. This is step 2 (brief APPROVE).

Your job at this phase: confirm the SPEC below is correct, complete, and won't violate any invariants when implemented. If the spec is sound, return `verdict: APPROVE`. The CODE doesn't exist yet — that's expected.

After your APPROVE here, I will implement the diff, then submit it for a separate diff review (different brief, different specific_check_responses).

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (iter-3: scope-shrunk per Codex iter-2 P1 findings)

Rebuild the `/intake` page to the I-ux-001d v6 design lock — **visual-only** evolution. Sub-PR 3 of approximately 7 for I-ux-001c.

**Codex iter-2 caught two real flaws in iter-1/iter-2 of this brief and they are now corrected:**

1. The current intake flow is `intake → source_review → plan` (I-p2-031 #770 shipped the authoritative source-review surface). My earlier spec shortcut `intake → /plan?q=...`, bypassing the source-review step. **Iter-3 PRESERVES the existing handoff: scope_decision_view's CTAs still link to `/source_review?q=...` (in-scope) or the existing disambiguation modal (ambiguous).**

2. A separate `source_set_health.tsx` component on `/intake` would render synthetic tier-availability pills not backed by authoritative data — LAW II violation. **Iter-3 DROPS `source_set_health.tsx` entirely.** The authoritative source-set surface is `/source_review` (already shipped). Intake stays a "just ask" surface; the source-set check lives one step downstream where it has real data.

3. Existing tests (`intake.spec.ts`, `intake_disambiguation_negative.spec.ts`) expect `scope-decision-view` to render in-place after submit. **Iter-3 PRESERVES this render-in-place behavior**; no redirect on success. Visual styling of the scope decision view stays the same in this PR (later sub-PRs can re-style it; sub-PR 3 is intake-only).

The current `/intake` (4 components, ~650 LOC) has the right backend coupling but pre-v6 styling. v6 changes are:

- Brand-red eyebrow ("ASK · POLARIS CLINICAL RESEARCH") replacing the muted "Clinical scope discovery"
- Display-weight H1 ("Ask the research question.") replacing the smaller "Ask a clinical research question"
- Tightened subtitle
- One large textarea (multi-line) replacing the single-line Input, with rotating placeholder among existing `SAMPLE_QUESTIONS`
- Auto-detected research domain chip below the textarea (heuristic on question text — keyword anchors; null when nothing crosses threshold per LAW II)
- DROP the "how it works" 3-step grid — superseded by the v6 home's proof-as-CTA messaging
- PRESERVE PdfDropBanner (real upload affordance, unchanged)
- PRESERVE the scope-decision-view render-in-place behavior + the `intake → source_review` handoff via the scope_decision_view's "Continue to source review →" link
- PRESERVE ALL existing testids (`intake-page`, `intake-question-input`, `scope-decision-view`) so all 5 intake.* tests + demo_journey + demo_walkthrough + intake_g1_g8 pass
- PRESERVE AppShell chrome (intake is NOT chromeless — only `/` is)

## Operator-locked constraints (carried forward)

- Brand red `#c8102e` ONLY at the primary CTA + brand-red eyebrow
- Verified-green ONLY on faithfulness affordances (in this PR: source-set health pills for tiers that have evidence; never for "I haven't checked yet" states)
- Honest sovereignty wording (Canadian-hosted, built toward sovereign deployment)
- AppShellGate behavior for `/intake` is PRESERVED — `/intake` is an authed route inside AppShell (not chromeless like `/`). All nav assertions in demo_journey + nav_parity stay valid.
- No fabricated source-set-health data: if the page can't compute reachable tiers without hitting the backend, the source-set health indicator is OMITTED rather than synthesized. (LAW II honest-fail.) The auto-domain detection is heuristic on question text — that IS computable without backend.

## File plan (iter-3 shrunk)

NEW
1. `web/app/intake/components/auto_domain_chip.tsx` (~80 LOC) — client component; receives question text + emits the detected domain chip. Heuristic: keyword-anchored mapping (e.g. "RCT/trial/dose/contraindication/efficacy" → clinical; "policy/regulation/HTA/NICE/CADTH" → policy; etc). Returns `null` when no domain crosses confidence threshold (LAW II).

REBUILD
2. `web/app/intake/page.tsx` — v6 layout: brand-red eyebrow + display H1 + tightened subtitle + PdfDropBanner + IntakeForm. DROP the STEPS grid.
3. `web/app/intake/components/intake_form.tsx` (~230 LOC current) — keep ALL backend logic verbatim (scope decision / disambiguation / ambiguity modal / ErrorState / scope_decision_view link to `/source_review`). Replace `Input` with shadcn `Textarea` (multi-line, larger); rotate `SAMPLE_QUESTIONS` as placeholder. Mount the new `AutoDomainChip` below the textarea, gated on `question.length > 0`. Bigger primary CTA button. Keep `intake-question-input` testid on the textarea.

DROPPED from iter-1/iter-2
- ~~`source_set_health.tsx`~~ — LAW II violation (would render synthetic tier pills); authoritative source-set lives at `/source_review` already.
- ~~CTA direct-deeplink to `/plan?q=...`~~ — would bypass the working `intake → source_review → plan` flow.

EDIT
4. None to globals.css (existing tokens suffice).

TESTS
5. NEW `web/tests/e2e/intake_v6.spec.ts` — 4 cases: page eyebrow + H1 + subtitle render with v6 copy, textarea visible + accepts multi-line text, auto-domain chip appears after typing a clinical keyword + disappears for an off-domain question, sample-question rotation cycles.
6. NO CHANGES needed to: `intake.spec.ts`, `intake_disambiguation.spec.ts`, `intake_disambiguation_negative.spec.ts`, `intake_edge.spec.ts`, `intake_g1_g8.spec.ts` — they all use `intake-question-input` testid + behavior assertions; the scope-decision-view render-in-place behavior and the source-review handoff are PRESERVED. If `intake_g1_g8.spec.ts` checks the STEPS grid presence specifically, that single assertion is updated (will verify on read).

## Files I have ALSO checked and they're clean

- `web/components/app_shell.tsx` — `/intake` is in the authed routes set; no change
- `web/components/app_shell_gate.tsx` — `/intake` is NOT chromeless
- `web/components/primary_nav.tsx` — Intake link preserved
- `web/lib/api.ts` — `runIntake` + `runDisambiguation` contracts unchanged
- `web/lib/nav.ts` — nav contract unchanged
- `web/app/plan/page.tsx` (the deep-link target) — unchanged
- All 5 existing intake test files — listed above; either KEPT or NOT TOUCHED

## Brief-review check requests (`specific_check_responses` — about the SPEC, not the diff)

- `scope_complete`: PASS / FAIL — the spec covers the v6 visual/behavioral evolution + all preserved testids + all backend invariants without leaving gaps that would force a scope-expansion mid-implementation
- `honest_fail_rules_specified`: PASS / FAIL — the spec explicitly requires `null` return for auto_domain_chip and source_set_health under honest-fail conditions (LAW II compliant)
- `appshell_chrome_decision_clear`: PASS / FAIL — the spec is unambiguous that `/intake` stays inside AppShell (not chromeless like `/`)
- `existing_test_compat_specified`: PASS / FAIL — the spec preserves `intake-page` and `intake-question-input` testids and lists which existing tests are KEPT vs UPDATED vs ADDED
- `file_list_surgical`: PASS / FAIL — the listed files are the minimum needed to deliver v6 intake; no "while we're at it" scope creep
- `cta_target_correct`: PASS / FAIL — `Plan this research →` deep-linking to `/plan?q=<encoded>` matches the I-p2-022 #761 plan-review surface and the existing `plan` route

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
  scope_complete: PASS | FAIL_with_detail
  honest_fail_rules_specified: PASS | FAIL_with_detail
  appshell_chrome_decision_clear: PASS | FAIL_with_detail
  existing_test_compat_specified: PASS | FAIL_with_detail
  file_list_surgical: PASS | FAIL_with_detail
  cta_target_correct: PASS | FAIL_with_detail
```
