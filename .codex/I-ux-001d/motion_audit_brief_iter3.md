# Codex hero-motion visual audit — I-ux-001d TRACK 1 sub-track A+B+C (iter 3)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## Scope of this iter

Iter 2 APPROVED sub-track A (`hero_first_reveal` desktop full-motion, 6 frames) with `accept_remaining`, `ready_to_scale_with_caveats`. Per iter-3 D3 cadence ("ONE hero-motion audit covering all scenes") I'm extending the audit BEFORE scaling to the other 7 scenes.

This iter audits the FULL `hero_first_reveal` scene across all combinations:
- **Sub-track A** (already APPROVED iter-2): desktop full-motion, 6 frames at t=0/120/250/400/600/700
- **Sub-track B** (NEW): mobile full-motion, 6 frames at t=0/120/250/400/600/700 (mirrors sub-track A grammar in 390x844 bottom-sheet pattern)
- **Sub-track C** (NEW): reduced-motion variants, 6 frames (3 desktop + 3 mobile) at t=0/120/200 with opacity-only crossfade per convention (all reveal-able blocks fade in together at the same rate, no per-beat sequencing)

## What you're auditing

18 motion stills in `web/p2shots/I-ux-001d/motion/`:

**Sub-track A — desktop full-motion (already APPROVED iter-2; included here for cross-frame consistency check):**
- `hero_first_reveal_pre_desktop_t0.png` (95014 bytes)
- `hero_first_reveal_start_desktop_t120.png` (117487 bytes)
- `hero_first_reveal_mid_desktop_t250.png` (129883 bytes)
- `hero_first_reveal_near_end_desktop_t400.png` (139374 bytes)
- `hero_first_reveal_end_desktop_t600.png` (162723 bytes)
- `hero_first_reveal_final_static_desktop_t700.png` (166847 bytes)

**Sub-track B — mobile full-motion (NEW):**
- `hero_first_reveal_pre_mobile_t0.png` (21191 bytes)
- `hero_first_reveal_start_mobile_t120.png` (30764 bytes)
- `hero_first_reveal_mid_mobile_t250.png` (34073 bytes)
- `hero_first_reveal_near_end_mobile_t400.png` (37010 bytes)
- `hero_first_reveal_end_mobile_t600.png` (47343 bytes)
- `hero_first_reveal_final_static_mobile_t700.png` (51833 bytes)

**Sub-track C — reduced-motion variants (NEW):**
- `hero_first_reveal_pre_desktop_t0_reduced.png` (96669 bytes)
- `hero_first_reveal_mid_desktop_t120_reduced.png` (168726 bytes)
- `hero_first_reveal_end_desktop_t200_reduced.png` (168092 bytes)
- `hero_first_reveal_pre_mobile_t0_reduced.png` (22210 bytes)
- `hero_first_reveal_mid_mobile_t120_reduced.png` (51712 bytes)
- `hero_first_reveal_end_mobile_t200_reduced.png` (51602 bytes)

## Reduced-motion contract (per convention)

`docs/web/i_ux_001d_motion_still_convention.md` row 1 reduced-motion variant: `0, 120, 200 (opacity-only crossfade)`. Implementation:
- t=0 → all proof-panel children opacity 0 (same as full-motion t=0)
- t=120 → all proof-panel children opacity 0.5 (mid-crossfade; everything emerging at the same rate, NO per-beat sequencing)
- t=200 → all proof-panel children opacity 1 (same as full-motion final)

This honors WCAG 2.2 2.3.3 prefers-reduced-motion (no slide, no parallax, no transform). The question for audit: does the simultaneous-fade convey the same information as the sequenced 6-beat reveal, just without the temporal narrative?

## What I want from this audit

1. **Mobile sub-track B parity with desktop sub-track A.** Does the mobile bottom-sheet reveal hit the same A bar the desktop achieved? Two-judgment separation crisp in 390x844? Source-as-climax preserved in the smaller frame?

2. **Spatial reorder on mobile.** I applied the same `ladder above source` y-swap (ladder y=157, source y=205). Verify it took effect — Codex iter-2 caveat on desktop was `spatial_reorder_accepted: FAIL_with_detail` due to layout-flow gap; check mobile rendering.

3. **Reduced-motion convention validity.** Does opacity-only-crossfade with EVERYTHING emerging together work as a reduced-motion equivalent? Or should reduced-motion still reveal in beats (just without slide/transform)? Frontier guideline check: Vercel/Apple/iOS reduced-motion patterns.

4. **Cross-frame consistency.** Same brand styling, same content, same hierarchy across all 18 stills?

5. **t=700 / final_static.** Iter-2 P2: "Limits disclosure sits very close to the bottom annotation bar; add clearance before mobile/full rollout." Is the mobile t=700 clearance acceptable, or does the disclosure still feel cramped?

6. **CHALLENGED SENTENCE label tightening.** Iter-2 P2: "still too subtle or not discernible at normal viewing scale." I tightened to slate r=0.23, g=0.31, b=0.42 at 11px Medium with 8% tracking (mobile) and 10px (desktop). Is the readability acceptable now?

7. **Ready to scale to remaining 7 scenes?** If APPROVE: I proceed to `hero_claim_switch`, `hero_sentence_hover`, `hero_sentence_focus`, `hero_mobile_sheet_open`, `hero_mobile_sheet_close`, `hero_failure_no_verified`, `hero_failure_refuse` × {full + reduced} × {desktop + mobile where applicable} = ~50 more frames.

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
ready_to_scale_to_7_remaining_scenes: yes | no | with_caveats
specific_check_responses:
  mobile_subtrack_b_parity: PASS | FAIL_with_detail
  spatial_reorder_mobile: PASS | FAIL_with_detail
  reduced_motion_convention_valid: PASS | needs_different_approach
  cross_frame_consistency: PASS | FAIL_with_detail
  t700_disclosure_clearance_mobile: PASS | FAIL_with_detail
  challenged_label_readability_v2: PASS | needs_further_tightening
```

## Files Codex should `-i`

All 18 stills listed above. Attach in `codex exec -i` order.
