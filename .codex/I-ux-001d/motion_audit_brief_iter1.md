# Codex hero-motion visual audit — I-ux-001d TRACK 1 sub-track A (iter 1)

## §0 cap directive (verbatim from CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Context

I-ux-001d sequencing-plan APPROVED Codex iter-3 (`accept_remaining`, zero P0/P1). TRACK 1 = hero motion stills in Figma. This audit is **sub-track A: smoke test on `hero_first_reveal` desktop full-motion**. 6 frames at t=0/120/250/400/600/700ms per `docs/web/i_ux_001d_motion_still_convention.md`.

If this smoke-test passes, I scale to all 8 scenes × {full-motion + reduced-motion} × {desktop + mobile}. If it fails, I fix the motion grammar before scaling.

## What you're auditing

Six annotated motion stills in `web/p2shots/I-ux-001d/motion/`:
- `hero_first_reveal_pre_desktop_t0.png` (94989 bytes) — rest state, right panel empty, brief visible, affordance hint "Click any sentence" shown
- `hero_first_reveal_start_desktop_t120.png` (117487 bytes) — sentence challenged, claim echo appears (Beat 1)
- `hero_first_reveal_mid_desktop_t250.png` (129883 bytes) — + Faithfulness verdict appears (Beat 2)
- `hero_first_reveal_near_end_desktop_t400.png` (139374 bytes) — + Evidence strength ladder appears (Beat 3 spatial / temporal)
- `hero_first_reveal_end_desktop_t600.png` (162723 bytes) — + Source (climax) Sealed evidence block appears (Beat 4)
- `hero_first_reveal_final_static_desktop_t700.png` (164805 bytes) — + Signature pill + Limits disclosure (Beats 5 + 6); this IS the v6 hero final state

Each frame has a 24px bottom annotation bar showing `<scene> · t=Nms · <state> · desktop · reduced-motion: no` plus a top-right `t=Nms` mark.

## Storyboard reveal-order spec (per `docs/web/proof_replay_storyboard.md`)

```
Beat 0  rest          → user pre-click; affordance hint visible
Beat 1  challenged    → user clicked middle sentence; left-side challenged styling appears; right-side claim echo appears
Beat 2  faithfulness  → binary "Verified by an independent model family" + checklist
Beat 3  certainty     → ordinal evidence-strength ladder (Very low → Low → Moderate → High)
Beat 4  source        → Sealed evidence block (climax — the proof object)
Beat 5  signature     → "Signed bundle · POLARIS Carney Demo key" pill + verify-offline link
Beat 6  disclosure    → "▸ what this verification does NOT prove" collapsed disclosure
```

Timing per convention: 0/120/250/400/600/700ms — total reveal ~700ms (within Vercel design-guideline 400-800ms range).

## What I know is imperfect (smoke-test honesty)

- **t=0 LEFT panel shows the green challenged-sentence border still baked in.** The ① numeric marker was hidden + the active-status line was hidden, but the row's green left border + tinted background remain. At true rest (pre-click), the middle sentence should look like its verified peers above and below. This is a known gap because reverting the row's fills/strokes requires per-state styling that isn't trivially togglable from the cloned frame; I prioritized the right-panel motion grammar for the smoke test.
- **Spatial vs temporal reveal order**: the proof panel y-layout is Claim echo → Faithfulness → Source → Evidence strength → Signature → Disclosure. The temporal storyboard order is the same EXCEPT Source comes AFTER Evidence strength in time (Beat 3 = certainty, Beat 4 = source). So at t=400 (near_end) when Evidence strength reveals, there's a visible gap in the right panel where Source would later appear at t=600. Is that gap a problem? Or should the temporal order match the spatial order (i.e., reveal Source at t=400 and Evidence strength at t=600)?
- **No reduced-motion variant in this smoke test.** That's deliberate — if the full-motion grammar is wrong, the reduced-motion variant inherits the wrongness. Audit full-motion first.

## What I want from this audit

1. **Cause-effect clarity per beat.** Does each frame in sequence READ as "the user clicked, then POLARIS verified, then POLARIS scored evidence strength, then POLARIS surfaced the proof"? Per Vercel motion guidelines (https://vercel.com/design/guidelines) and clinical-context safety, motion must EXPLAIN what's happening.
2. **Two-judgment separation visible per beat.** Beat 2 (faithfulness chip) vs Beat 3 (certainty ladder) must read as TWO DIFFERENT TYPES of read, not blurred into a single judgment. At t=400 specifically, with both visible, is the separation as crisp as the v6 static frame achieved?
3. **Source as climax.** Beat 4 reveal of the Sealed evidence block at t=600 — does it feel like the climax of the reveal, or just another section appearing? It should feel decisively "this is the proof."
4. **The two known imperfections above.** Confirm priority: are these P0/P1 (must fix before scaling) or P2/P3 (acceptable for smoke; carry into the full scale)?
5. **Timing read-through.** Annotation bars + filename t=Nms give Codex the timing axis. Does 700ms total feel right? Or should it be faster (500ms) or slower (900ms) per frontier-bar precedents you're familiar with?
6. **Anything else.** Is there a beat I'm missing? An obvious craft flaw? Be the picky real user; do not soften.

## Specific check requested

- **The challenged-sentence-at-rest issue at t=0**: P1 (must fix before scaling), or P2 (carry forward — acceptable for the audit to read the motion grammar even with this gap)?
- **The spatial vs temporal order**: keep storyboard temporal order (current: Source at t=600, Evidence strength at t=400) or swap to match spatial layout (Source at t=400, Evidence strength at t=600)?
- **Reveal-order tweaks**: should any beat collapse with another (e.g., Faithfulness + Certainty co-reveal at t=250 as ONE "two-judgment summary")? Or stay sequential?

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_scale_up: [...]
specific_check_responses:
  challenged_sentence_at_rest_severity: P1 | P2
  spatial_vs_temporal_order: keep_temporal | swap_to_spatial | other_with_rationale
  reveal_order_tweaks: [...]
```

## Files Codex should consult (and view via `-i`)

- `web/p2shots/I-ux-001d/motion/hero_first_reveal_pre_desktop_t0.png` — `-i` this
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_start_desktop_t120.png` — `-i` this
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_mid_desktop_t250.png` — `-i` this
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_near_end_desktop_t400.png` — `-i` this
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_end_desktop_t600.png` — `-i` this
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_final_static_desktop_t700.png` — `-i` this (= v6 hero final)
- `docs/web/proof_replay_storyboard.md` — the 6-beat spec
- `docs/web/i_ux_001d_motion_still_convention.md` — timestamp table + reduced-motion contract
- `docs/web/i_ux_001d_route_frame_map.md` — per-frame v6 checklist
- `.codex/I-ux-001b/visual_audit_v5.txt` — the v6 hero precedent (A/A- + GREENLIGHT)
