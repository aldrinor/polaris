# Codex hero-motion mega-audit — I-ux-001d TRACK 1 final (iter 1)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## Scope of this mega-audit

Per I-ux-001d sequencing-plan iter-3 D3 cadence lock: "ONE hero-motion audit covering all scenes." TRACK 1 is now structurally complete — all 8 scenes built (73 total motion stills). This mega-audit covers representative key-frames across all 8 scenes (22 stills total, within the 24 ceiling).

Scene 1 (`hero_first_reveal`) already APPROVED in motion_audit_iter-3 across 18 stills (`accept_remaining`, `ready_to_scale_with_caveats`). This mega-audit adds the 7 newly-built scenes and confirms cross-scene grammar consistency.

## What's being audited (22 representative stills)

### Scene 1 — hero_first_reveal (already APPROVED; 1 reference still for cross-scene context)
- `hero_first_reveal_final_static_desktop_t700.png`

### Scene 2 — hero_claim_switch (desktop full-motion, 3 stills)
Claim N → claim N+1 in <120ms perceived:
- `hero_claim_switch_start_desktop_t0.png` (claim 2 selected; proof panel for claim 2)
- `hero_claim_switch_mid_desktop_t40.png` (mid-transition; proof panel at 0.4 opacity; verified-1 row gets subtle tint)
- `hero_claim_switch_end_desktop_t120.png` (claim 1 now active; proof panel echo swapped; active-status moved to verified-1)

### Scene 3 — hero_sentence_hover (desktop, 3 stills)
Rest → hover (no reduced-motion variant per convention):
- `hero_sentence_hover_pre_desktop_t0.png` (rest)
- `hero_sentence_hover_mid_desktop_t60.png` (tint ramping in @ 4%)
- `hero_sentence_hover_end_desktop_t120.png` (hover stable @ 8% warm-cream tint on verified-1)

### Scene 4 — hero_sentence_focus (desktop full, 3 stills)
Rest → focus-visible per WCAG 2.4.7:
- `hero_sentence_focus_pre_desktop_t0.png` (rest)
- `hero_sentence_focus_mid_desktop_t80.png` (focus ring appearing)
- `hero_sentence_focus_end_desktop_t160.png` (2px verified-green OUTSIDE ring + tinted bg)

### Scene 5 — hero_mobile_sheet_open (mobile, 3 stills)
Sheet collapsed → expanded:
- `hero_mobile_sheet_open_pre_mobile_t0.png` (sheet y=760, only handle peeks)
- `hero_mobile_sheet_open_mid_mobile_t100.png` (sheet y=480, mid)
- `hero_mobile_sheet_open_end_mobile_t220.png` (sheet y=226, fully open = v6 final)

### Scene 6 — hero_mobile_sheet_close (mobile, 3 stills)
Reverse direction:
- `hero_mobile_sheet_close_pre_mobile_t0.png` (sheet y=226, open)
- `hero_mobile_sheet_close_mid_mobile_t100.png` (sheet y=480)
- `hero_mobile_sheet_close_end_mobile_t180.png` (sheet y=760, closed)

### Scene 7 — hero_failure_no_verified (desktop full, 3 stills)
Abort state — corpus generated but no sentence survived faithfulness check:
- `hero_failure_no_verified_pre_desktop_t0.png` (panel still empty)
- `hero_failure_no_verified_mid_desktop_t200.png` (abort panel @ 0.6 opacity)
- `hero_failure_no_verified_end_desktop_t400.png` (full abort panel: warm amber badge, headline, 3 honest-bullet explanation, green signed bundle pill, view-unverified-draft link)

### Scene 8 — hero_failure_refuse (desktop full, 3 stills)
Clinical-safety refuse — out-of-scope question per plan §6 intended-use non-uses:
- `hero_failure_refuse_pre_desktop_t0.png` (panel still empty)
- `hero_failure_refuse_mid_desktop_t200.png` (refuse panel @ 0.6 opacity)
- `hero_failure_refuse_end_desktop_t400.png` (full refuse: quoted question, magenta-red 'POLARIS WILL NOT ANSWER THIS' badge, intended-use boundary explanation, green 'WHAT POLARIS CAN ANSWER' alternative list)

## What I want from this mega-audit

1. **Cross-scene grammar consistency.** Do all 8 scenes share the same visual language? Annotation bars + top-marks present everywhere? Typography/colour discipline consistent?
2. **The two failure designs (scenes 7+8) — do they hold up as proof-as-hero?** The signed-bundle pill stays green in both (the bundle is still authoritative). The badges are warm amber (no_verified = honest fail) vs magenta-red (refuse = out-of-scope). Is the distinction clear, and is each design at the same A+ bar as the success hero?
3. **Mobile sheet animations (5+6) — does y-translation read as motion?** The convention is opacity for reduced; full-motion uses position. Convey vertical sheet behavior in stills?
4. **Sentence-level micro-states (3+4) — readable at desktop scale?** Hover is intentionally subtle (4-8% tint); focus is intentionally bold (2px ring). Are they each appropriate to their role (hover = "I'm aware of this", focus = "I'm committing to this")?
5. **Claim switch (2) — does the <120ms perceived target read?** Three timestamps for a 120ms transition is tight. Does it feel snappy or rushed?
6. **TRACK 1 ready to sign off?** If APPROVE → proceed to TRACK 2 (family-template contact-sheet: read/edit/monitor/spatial/marketing-auth × 1 desktop each = 5 frames).

## Carry-forward iter-3 caveats (Codex check whether scale-up addressed them)

- iter-3 P3: mobile reduced-motion handle bar — fix applied in scene 2 onward (exclude handle from opacity-reveal set). Verify scenes 5+6 (and reduced variants throughout) preserve the handle.
- iter-3 P2: spatial reorder on mobile didn't take — this was scene-1 specific; new scenes use different layout patterns so the caveat doesn't propagate. Verify the new scenes have crisp visual hierarchy.

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
track_1_ready_to_signoff: yes | no | with_caveats
specific_check_responses:
  cross_scene_grammar_consistency: PASS | FAIL_with_detail
  failure_designs_aplus: PASS | FAIL_with_detail
  mobile_sheet_motion_readable_in_stills: PASS | FAIL_with_detail
  hover_focus_micro_states_appropriate: PASS | FAIL_with_detail
  claim_switch_120ms_feel: PASS | FAIL_with_detail
  iter3_carryforward_addressed: PASS | FAIL_with_detail
```

## Files to `-i` (22 stills listed above, in scene-1 → scene-8 order)
