# Brief: I-ux-001c (GH #878) — Hero implementation, sub-PR 1: Inspector Proof Replay v6 (centerpiece)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope

I-ux-001d (#879) shipped the Figma design lock for all 12 pages + motion grammar + family templates (Codex APPROVE across all 5 tracks). I-ux-001c (#878) is the code implementation phase. This sub-PR 1 implements the **Inspector hero (Proof Replay)** — the CENTERPIECE.

**This sub-PR is intentionally narrow**: rebuild only the Inspector hero band to match the v6 prototype (one of the 12 pages). Subsequent sub-PRs handle the other 11 pages in family-page-group cadence per the I-ux-001d sign-off handover.

## What ships in this sub-PR

1. **Updated `web/components/inspector/inspector_proof_header.tsx`** — match v6 hero band: H1 (research question), two-judgment chip row (faithfulness + certainty), provenance two-band strip with humanized verdicts (no `abort_*` tokens), tri-state SignatureBadge (already correct per I-ux-001a), Bundle manifest disclosure (already correct).
2. **Updated `web/components/proof_replay/proof_replay.tsx`** — match v6 hero spec: split-view with brief reading column LEFT, proof panel RIGHT. The proof panel's named children in vertical order (per Codex iter-1 D5 spatial reorder from I-ux-001d):
   - CHALLENGED SENTENCE label (Inter Medium 10/8% letter-spacing, slate; hidden when no claim selected)
   - Claim echo (the user-selected sentence quoted in italic with ① marker)
   - Faithfulness block ("Verified" big + "by an independent model family" + 3-item checklist with ✓ marks)
   - divider hairline
   - Evidence strength ladder (Very low / Low / Moderate / High — 4-step horizontal bar, selected step in slate-blue with white text)
   - divider hairline
   - Source (climax) — "The exact passage that supports this claim" header + unified Sealed evidence block (continuous 2px verified-green left rule through source-card + span content + "matched N of N numbers" stamp in bottom-right of span area)
   - divider hairline
   - Signature pill (gpg_verified green) + verify-offline link
   - "▸ what this verification does NOT prove" collapsed disclosure
3. **New `web/components/inspector/intended_use_strip.tsx`** — the amber INTENDED USE band (per Codex iter-1 P1 fix from I-ux-001d TRACK 2): "NOT clinical decision-support · independent judgment required" (full copy on desktop, truncated on mobile per the mobile-fit constraint).
4. **Mobile bottom-sheet variant** — `useMediaQuery('(max-width: 768px)')` switches the proof panel from sidebar to bottom-sheet (handle bar visible, sheet expandable; mirror Stage 4 v6 mobile prototype).
5. **6-beat motion choreography** — opacity-reveal on proof-panel named children, `prefers-reduced-motion` honored (opacity-only crossfade per `i_ux_001d_motion_still_convention.md`):
   - rest (claim not selected) — proof panel collapsed/hidden
   - claim click → t=0 pre, t=120 claim echo, t=250 +faithfulness, t=400 +evidence strength, t=600 +source, t=700 +signature + disclosure
   - claim-to-claim switch — proof panel opacity 0.4 mid-transition (t=40), then content swaps + restores opacity (<120ms perceived total)
6. **Design tokens update** — `web/app/globals.css` `@theme` block adds the v6 two-judgment color palette: faithfulness verified-green / amber / magenta-red (hue 320 distinct from brand red hue 22); evidence-strength slate-blue ordinal ladder; per-certainty foregrounds (`--certainty-{high,moderate,low,very-low}-fg`); motion tokens (`--motion-fast-out-slow-in: 200ms`, `--motion-emphasized: 320ms`).

## What does NOT ship in this sub-PR (deferred to subsequent sub-PRs)

- Home page hero (sub-PR 2)
- Intake / Source-Review / Plan-Review (sub-PR 3 — edit-mode family-page-group)
- Run-progress / Dashboard (sub-PR 4 — monitor-mode family-page-group)
- Compare follow-up (sub-PR 5)
- Knowledge graph (sub-PR 6)
- Audit / Sign-in / Transparency (sub-PR 7 — supporting family-page-group)
- Carry-forward P2/P3 from Codex TRACK 4: intake "Continue to source review" copy, runs "Open verified brief" affordance, cross-page exit affordances, clinical acronym tooltips, KG trust legend — each scoped per-page sub-PR

## Why this sub-PR scope is right

- Inspector is the CENTERPIECE (per plan §14 + I-ux-001d acceptance bar). It's the page Mark Carney's office will dwell on longest.
- It's the existing page that ALREADY has the proof-as-hero band installed (from I-p2-043 #833). The change is REBUILD to match v6 spec, not greenfield.
- The new components (intended_use_strip, motion choreography) become reusable for the 11 other page implementations.
- ~200 LOC cap is achievable for this scope (one file rebuilt + one new component + token update).

## Files I have ALSO checked and they're clean (per §-1.2 step 2)

- `web/lib/inspector_bundle_loader.ts` — already returns tri-state `signatureState`; correct since I-ux-001a #873
- `web/lib/signed_bundle.ts` — schema correct
- `web/components/inspector/bundle_header.tsx` — `SignatureBadge` already tri-state; correct
- `web/components/inspector/family_segregation_badge.tsx` — correct
- `web/app/inspector/[runId]/page.tsx` — server component is correct; no changes needed
- `web/app/inspector/[runId]/inspector_view.tsx` — Tabs structure is correct; the inner Proof Replay component is what changes
- `web/public/canonical_bundles/v1_canonical_success/` — real signed demo bundle from I-ux-001a (#875); the implementation will render this real data
- `docs/web/proof_replay_storyboard.md` + `docs/web/components_catalogue.md` + `docs/web/design_tokens_v2.md` — locked design source-of-truth from I-ux-001b/d (this PR implements against them)

## Smoke test plan (§-1.2 step 3 — before claiming the change works)

1. `cd web && pnpm install && pnpm dev` — local Next.js dev server
2. Navigate to `http://localhost:3000/inspector/v1-canonical-success`
3. Visually verify: H1 = the actual research question; two-judgment chips visible; click a sentence → 6-beat reveal animates the proof panel; mobile viewport (devtools 390x844) → bottom-sheet variant
4. `pnpm exec playwright test web/tests/e2e/inspector_proof_replay.spec.ts` (NEW e2e test)
5. `pnpm exec axe web/app/inspector` — WCAG 2.2 AA target zero violations on the rebuilt hero

## Acceptance criteria

- Inspector hero matches the v6 Figma prototype at the same A+ bar Codex GREENLIT (`web/p2shots/I-ux-001b/hero_stage2_v6_desktop.png`, `web/p2shots/I-ux-001b/hero_stage4_v6_mobile.png`)
- Mobile bottom-sheet variant matches Stage 4 of the storyboard
- Motion honors `prefers-reduced-motion` (opacity-only crossfade at t=0/120/200)
- All 12 v6 checklist items pass on the live page (sealed evidence block, two-judgment separation, tri-state signature, intended-use strip, no jargon, semantic-icon restraint, etc.)
- Codex visual audit via `codex exec -i <live-page-screenshot>` returns APPROVE
- Playwright e2e test passes (sentence click → proof panel populates; signature badge shows correct state)
- axe-core scan returns zero WCAG 2.2 AA violations on `/inspector/[runId]`

## Codex review iteration plan

- iter 1 = this brief review (acceptance criteria + scope cap correctness)
- iter 2-5 (if needed) = diff review post-implementation
- Visual audit happens as a separate Codex call (`codex exec -i live_render.png`) after `pnpm dev` is running, NOT folded into the diff review

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  scope_cap_appropriate: PASS | FAIL_with_detail
  acceptance_criteria_complete: PASS | FAIL_with_detail
  smoke_test_plan_realistic: PASS | FAIL_with_detail
  files_also_checked_credible: PASS | FAIL_with_detail
```

## Files Codex should consult

- This brief
- `docs/web/proof_replay_storyboard.md`
- `docs/web/components_catalogue.md`
- `docs/web/design_tokens_v2.md`
- `web/p2shots/I-ux-001b/hero_stage2_v6_desktop.png` (visual target)
- `web/p2shots/I-ux-001b/hero_stage4_v6_mobile.png` (mobile visual target)
- `web/components/inspector/inspector_proof_header.tsx` (current — to be rebuilt)
- `web/components/proof_replay/` (current — to be rebuilt)
- `web/app/inspector/[runId]/page.tsx` + `inspector_view.tsx` (consumer wrappers — minimal changes)
- `.codex/I-ux-001d/track4_e2e_journey_verdict_iter1.txt` (P2/P3 code-time carry-forward list)
