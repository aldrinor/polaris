# Codex sequencing consultation — I-ux-001d (iter 3)

## §0 cap directive (verbatim from CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Resolution of iter-2 P1/P2/P3 findings

Iter 2 returned `verdict: REQUEST_CHANGES`, zero P0, 2 P1, 3 P2, 1 P3, `convergence_call: continue`. All resolved:

### Iter-2 P1-001 (route inventory gap) → RESOLVED

Codex grounded that `web/lib/nav.ts:25-34` exposes 9 primary nav items including `/upload`, `/benchmark`, `/contracts`, `/pin_replay`, `/memory` — I had not represented these.

**Resolution: CUT from primary nav for the demo, kept as reachable URLs.** Documented in `docs/web/i_ux_001d_route_frame_map.md` "Nav cut" section with primary-source citations:
- 5 cut routes table (upload/benchmark/contracts/pin_replay/memory) — out-of-demo-scope, in-product-scope
- Rationale: frontier-bar nav restraint (Linear/Stripe/Perplexity 3-5 items, not 9); budget reality; critical-path focus; operator framing #872 "very strong and fresh impact" demands focus
- Concrete code change: `web/lib/nav.ts` PRIMARY_NAV trim at I-ux-001c (#878) implementation time
- Demo primary nav becomes 4 items: Home · Ask · Dashboard · Compare + footer Transparency link

This is a product-direction call I'm making per Codex iter-2's "pick one." If Codex disagrees and wants the 5 routes IN scope, return REQUEST_CHANGES with P0 — that triggers expanding the frame budget from 24 to 34. Within the 11-day demo window, that change is the dominant risk.

### Iter-2 P1-002 (transparency contract conflict) → RESOLVED

Codex grounded that:
- `web/next.config.ts:101-106` rewrites `/transparency` → FastAPI JSON
- `web/components/site_footer.tsx:35-39` LINKS to `/transparency` → human reader hits JSON dead-end
- `docs/stier_experience_plan.md` §6 requires intended-use + non-use + model path + data residency + verifier limits as a real human disclosure

**Resolution: dedicated `/transparency` HTML page (NEW page #12) + machine JSON relocated to `/.well-known/transparency.json`** per RFC 8615. Footer link retargets at the HTML page. Page added to the route map (originally 11 → now 12; frames 22 → 24).

This is the standard pattern (OpenAI, Anthropic, security.txt, .well-known/* family — well-known URIs ARE the machine path; human content gets the canonical pretty URL).

### Iter-2 P2 (budget tightness) → ACKNOWLEDGED + bounded

Codex's specific check `budget_realism`: "Not safely achievable as-is." Resolution at `docs/web/i_ux_001d_route_frame_map.md` "Budget posture acknowledgment" section explicitly states the constraints under which the 24-frame budget IS achievable:

1. Frame inventory FROZEN as of this iter-2 resolution
2. I-ux-001c (#878) implementation begins IMMEDIATELY after Tracks 1+2 gates pass (parallel with Tracks 3-5)
3. The 5 cut nav routes stay cut
4. #871 sequenced as PARALLEL work, not before
5. Codex audits hit one-iter APPROVE on Tracks 1+2 (the substrate is now tight enough that 3-5-iter cycles per gate should not be necessary)

Slippage mitigation: if Tracks 1+2 exceed 3 days combined, drop 4 supporting-page A frames (Audit, Sign-in, Dashboard, Transparency) from the prototype set; design at code-time only.

### Iter-2 P2 (Source Review should remain standalone but visually behave as step-2-of-Intake) → RESOLVED

Documented in the route map row 3: "Source Review (visually = step-2-of-Intake preflight per Codex iter-2 P2)" — design constraint baked in for the edit-mode family template work.

### Iter-2 P2 (per-frame v6 checklist) → RESOLVED

Added at `docs/web/i_ux_001d_route_frame_map.md` "Per-frame v6 proof-language checklist" — 10 explicit checkboxes every desktop + mobile frame must pass before Codex audit submission. Prevents incumbent-leak.

### Iter-2 P3 (motion convention: 8 scenes, not 9) → RESOLVED

Updated `docs/web/i_ux_001d_motion_still_convention.md`:
- Scene list explicitly enumerates 8 primary scenes
- Reduced-motion is now a per-scene variant (suffix `_reduced.png`), NOT a 9th scene
- Per-scene timestamp table shows full-motion + reduced-motion columns

## What iter-3 needs from Codex

All iter-2 findings resolved at the primary-source-of-truth level (route map + motion convention + GH#879 body about to be updated). The plan is now:

- 12 pages × 2 viewports = **24 Figma frames**
- **8 motion scenes** + reduced-motion variant per scene
- **4-item demo primary nav** (Home · Ask · Dashboard · Compare) — 5 routes cut from nav, kept as direct-URL
- **Transparency = dedicated `/transparency` HTML page** + `/.well-known/transparency.json` for machines
- **5 audit gates**: hero-motion / family-template contact-sheet / 24-frame mega / e2e click-through / per-page critical-path (only if flagged)
- **Per-frame v6 checklist** (10 items) before submission
- **Source Review** visually behaves as step-2-of-Intake preflight, route stays standalone
- **Budget posture**: ~11 days to demo; 5 constraints documented; slippage mitigation = drop 4 supporting-page A frames if Tracks 1+2 exceed 3 days

Ready for sequencing-plan APPROVE.

## Specific check requested

Same questions, post-resolution:

- **Budget realism after the 5-route cut + 2-page transparency add**: 24 frames + motion + audits + I-ux-001c + #871 + TLS + rehearsal in 11 days. Plausible under the 5 documented constraints?
- **The nav cut** — am I making the right product call (4-item nav for demo, 5 routes deep-link only)? Codex iter-2 said "pick one"; I picked CUT. Want explicit Codex sign-off OR REQUEST_CHANGES with the alternative.
- **The transparency page split** — `/transparency` HTML for humans + `/.well-known/transparency.json` for machines. Standard? Frontier-bar? Or is there a better pattern?
- **The per-frame v6 checklist** — does it cover the incumbent-leak surface, or are there obvious gaps (e.g., I didn't list "no decorative icons next to text-bearing chips" — should that be there)?
- **Source Review visually as step-2-of-Intake** — design constraint right? Or should it be its own visual language (different from Intake) to signal the safety/adequacy gate?

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
  budget_realism_post_resolution: [...]
  nav_cut_call: APPROVE | REQUEST_CHANGES_with_alternative
  transparency_page_split: APPROVE | better_pattern_proposal
  v6_checklist_coverage: [...]
  source_review_step2_of_intake: APPROVE | alternative_proposal
```

## Files Codex should consult

UPDATED since iter 2:
- `docs/web/i_ux_001d_route_frame_map.md` (12 pages + nav cut + transparency + checklist + budget posture)
- `docs/web/i_ux_001d_motion_still_convention.md` (8 scenes; reduced-motion as variant)
- GH#879 body (about to be edited)

Already in scope from prior iters:
- `.codex/I-ux-001d/sequencing_brief_iter1.md` + `sequencing_verdict_iter1.txt`
- `.codex/I-ux-001d/sequencing_brief_iter2.md` + `sequencing_verdict_iter2.txt`
- `docs/stier_experience_plan.md` v4 + `.codex/I-ux-001/PLAN_APPROVED.md`
- `docs/stier_experience_directive_2026_05_24.md`
- `docs/web/{design_tokens_v2, components_catalogue, proof_replay_storyboard}.md`
- `web/lib/nav.ts` (primary-source for the nav-cut grounding)
- `web/next.config.ts` (primary-source for the transparency rewrite grounding)
- `web/components/site_footer.tsx` (primary-source for the footer-link grounding)
- `web/p2shots/I-ux-001b/hero_stage{2,4}_v6_*.png` + `.codex/I-ux-001b/visual_audit_v5.txt` (precedent)
