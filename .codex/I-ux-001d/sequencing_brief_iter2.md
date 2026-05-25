# Codex sequencing consultation — I-ux-001d (iter 2)

## §0 cap directive (verbatim from CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Resolution of iter-1 remaining blockers

Iter 1 returned `verdict: REQUEST_CHANGES`, `convergence_call: continue`, with three remaining blockers + 6 substantive direction calls (D1-D6). All addressed:

### Iter-1 blocker 1: "Revise #879 to the hybrid sequence above before any Figma production sprint."

**Resolved.** GH#879 issue body updated to reflect the iter-1 hybrid sequence (`gh issue edit 879 --body-file ...`). Updated body documents D1 hybrid sequence, D2 family-contracts model, D3 hybrid audit cadence, D4 annotated-still vehicle, D5 beta acceptance with Source Review promoted to A+, D6 incumbent-informed.

### Iter-1 blocker 2: "Publish an exact 11-page route/frame map, including how Transparency is represented."

**Resolved at `docs/web/i_ux_001d_route_frame_map.md` (NEW).** Key findings:
- 11 page rows × 2 viewports = 22 frames confirmed
- **Transparency is NOT a standalone route.** Verified via `web/app/transparency/` (does-not-exist) and `web/components/site_footer.tsx` (transparency content lives in shell footer + sovereignty proof panel per P2-seq-23 #762). Plan §1 "/transparency URL" is REJECTED; surface satisfied by shell integration. Transparency does NOT get its own hero frame; instead it must be designed AS PART OF the shell template (which is itself a contract layered across every page).
- Source Review IS a real route at `web/app/source_review/page.tsx`; Codex iter-1 D5 critical-path promotion stands
- All 11 pages have salvageable behavior captured in the map (incumbent-informed per D6)

### Iter-1 blocker 3: "Define the annotated-still export naming convention and timestamp set before the first Codex motion audit."

**Resolved at `docs/web/i_ux_001d_motion_still_convention.md` (NEW).** Key decisions:
- Filename: `<scene>_<state>_<viewport>_t<ms>.png`
- 8 scenes (`hero_first_reveal`, `hero_claim_switch`, `hero_sentence_hover`, `hero_sentence_focus`, `hero_mobile_sheet_open`, `hero_mobile_sheet_close`, `hero_failure_no_verified`, `hero_failure_refuse`) + reduced-motion variant per scene
- Timestamp set per Codex iter-1 D4 lock: `hero_first_reveal` at 0/120/250/400/600/700ms; `hero_claim_switch` at 0/40/120ms; rest specified per scene
- 16px on-frame annotation overlay redundant with filename
- One mega audit per Codex iter-1 D3 cadence (NOT per-scene)
- Out-of-scope explicitly listed: easing curves + GPU frame rate + prefers-reduced-motion enforcement (all deferred to I-ux-001c code-time Playwright trace per plan §14)

## Iter-1 D1-D6 calls — locked

All 6 Codex direction calls accepted verbatim:
- **D1 hybrid sequence**: hero motion grammar → per-family templates → 22-frame specialization → e2e click-through
- **D2 family contracts**: 5 families (read-mode / edit-mode / monitor-mode / spatial / marketing-auth), contract-based not cloned
- **D3 hybrid cadence**: 1 hero-motion + 1 family-template contact-sheet + 1 all-22-frame mega + per-page only on critical path or flagged
- **D4 annotated-still sequence**: per the new convention doc
- **D5 beta acceptance with Source Review promotion**: A+ critical path = Home → Intake → Source Review → Plan review → Run progress → Inspector → Compare → Knowledge graph; A on Audit, Sign-in, Dashboard
- **D6 incumbent-informed**: salvage behavior + data contracts + route semantics; rebuild visuals greenfield

## Iter-1 D6 secondary finding: "Local checkout did not contain `docs/stier_experience_plan.md` or `web/app/transparency/page.tsx`"

**Resolved by merging origin/bot/I-ux-001-operating-model + origin/bot/I-ux-001a-prereq-0-signed-bundle + origin/bot/I-ux-001b-foundation into the current branch (`bot/I-ux-001d-extend-prototype-audit`).** Plan v4 + PLAN_APPROVED + foundation docs (design_tokens_v2.md, components_catalogue.md, proof_replay_storyboard.md) + signed bundle artifacts (gpg_verify_bundle.ts, build_canonical_demo_bundle.py, etc.) + hero v6 screenshots are now all on this branch. Codex iter-2 can read the full canonical state.

`web/app/transparency/page.tsx` confirmed does not exist (per route map) — not a missing-file error, an architectural fact.

## What iter-2 needs from Codex

The plan + inventory + naming convention are now locked. **All execution prerequisites met.** Codex should APPROVE the sequencing plan so I can begin TRACK 1 (hero motion stills) in the next iter.

If any of the iter-1 calls (D1-D6) need adjustment given the resolved blockers, surface as P0/P1 now. Otherwise APPROVE.

## Specific check requested

Given:
- 11 pages confirmed (Transparency rejected as a separate page)
- 5 families locked
- Source Review promoted to critical
- 22 frames + 1 mega contact-sheet + 1 hero motion audit
- Annotated stills at the timestamps above
- ~12 days to demo window (2026-06-05..09)

**Is this campaign plan ship-able as-is, or is there a P0/P1 risk I'm not seeing?**

Specific risk worth Codex's check:
- Is the demo-window budget (~12 days) achievable for 22 Figma frames + motion + audit + I-ux-001c implementation + #871 live-demo fix + Caddy/TLS verify + dress rehearsal?
- Should Source Review be designed AS PART OF Intake (combined edit-mode page) instead of standalone? Plan §14 lists them separately but live route consolidation might be the higher-craft answer
- The Transparency-as-shell decision — does that satisfy the plan's "honest sovereignty wording" requirement, or does it warrant a dedicated `/transparency` page anyway for regulatory disclosure?
- Does "incumbent-informed" carry a risk that the v6 hero language (sealed evidence block, two-judgment chip-row, signed-bundle pill) is NOT applied consistently to all 22 frames because old-page habits leak through?

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
  budget_realism: [...]
  source_review_vs_intake_consolidation: [...]
  transparency_shell_vs_page: [...]
  incumbent_leak_risk: [...]
```

## Files Codex should consult before answering

NEW since iter 1:
- `docs/web/i_ux_001d_route_frame_map.md`
- `docs/web/i_ux_001d_motion_still_convention.md`
- GH#879 updated body (to be edited in next step before this iter fires)

Already in scope:
- `docs/stier_experience_plan.md` v4 (now on this branch)
- `.codex/I-ux-001/PLAN_APPROVED.md` (now on this branch)
- `docs/stier_experience_directive_2026_05_24.md` (operator standing directive)
- `docs/web/{design_tokens_v2, components_catalogue, proof_replay_storyboard}.md`
- `web/p2shots/I-ux-001b/hero_stage{2,4}_v6_*.png` (the precedent)
- `.codex/I-ux-001b/visual_audit_v5.txt` (the precedent verdict)
- `.codex/I-ux-001d/sequencing_brief_iter1.md` + `sequencing_verdict_iter1.txt`
- `state/active_issue.json` (~12-day demo-window budget context)
- `web/app/**/page.tsx` (live incumbents)
