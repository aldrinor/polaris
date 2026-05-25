# I-ux-001d — Motion still convention

Resolves Codex iter-1 remaining blocker "Define the annotated-still export naming convention and timestamp set before the first Codex motion audit" (`.codex/I-ux-001d/sequencing_verdict_iter1.txt`).

## Codex iter-1 D4 lock

Motion conveyance to Codex = **annotated still sequence** (not interactive prototype URL, not MP4/GIF). Codex `-i` accepts static images; timing is read from filename `t=Nms` tags + on-frame annotations. Figma prototype URL kept as operator evidence + future Playwright-trace ground truth, but the binding audit vehicle is the still sequence.

## Filename convention

```
<scene>_<state>_<viewport>_t<ms>.png
```

Where:
- `<scene>` ∈ exactly 8 primary scenes (per Codex iter-2 P3 — reduced-motion is a per-scene variant, NOT a separate scene):
  - `hero_first_reveal` (6-beat hero choreography)
  - `hero_claim_switch` (claim N → claim N+1)
  - `hero_sentence_hover`
  - `hero_sentence_focus`
  - `hero_mobile_sheet_open`
  - `hero_mobile_sheet_close`
  - `hero_failure_no_verified` (abort state reveal)
  - `hero_failure_refuse` (clinical-safety refuse state)
- `<state>` ∈ {`pre`, `start`, `mid`, `near_end`, `end`, `final_static`, `interrupted`} — semantic label keyed to t=
- `<viewport>` ∈ {`desktop`, `mobile`}
- `<ms>` ∈ explicit timestamp in milliseconds from start of the transition (see timestamp set below)

**Reduced-motion variant** is a per-scene attribute, not a scene. Each of the 8 scenes ships with two file sets: full-motion + reduced-motion (e.g., `hero_first_reveal_pre_desktop_t0.png` + `hero_first_reveal_pre_desktop_t0_reduced.png`). The `_reduced` filename suffix encodes the variant.

Files land in `web/p2shots/I-ux-001d/motion/`.

Examples:
- `hero_first_reveal_pre_desktop_t0.png`
- `hero_first_reveal_start_desktop_t120.png`
- `hero_first_reveal_mid_desktop_t250.png`
- `hero_first_reveal_near_end_desktop_t400.png`
- `hero_first_reveal_end_desktop_t600.png`
- `hero_first_reveal_final_static_desktop_t700.png`
- `hero_claim_switch_start_desktop_t0.png`
- `hero_claim_switch_mid_desktop_t40.png`
- `hero_claim_switch_end_desktop_t120.png`
- `hero_first_reveal_pre_desktop_t0_reduced.png`  (reduced-motion variant of the first-reveal start)
- `hero_first_reveal_mid_desktop_t120_reduced.png`
- `hero_first_reveal_end_desktop_t200_reduced.png`
- `hero_mobile_sheet_open_pre_mobile_t0.png`
- `hero_mobile_sheet_open_mid_mobile_t100.png`
- `hero_mobile_sheet_open_end_mobile_t220.png`

## Timestamp set (per Codex iter-1 D4 lock; 8 scenes — reduced-motion is per-scene variant per iter-2 P3)

| # | Scene | Full-motion timestamps (ms) | Reduced-motion variant timestamps (ms) |
|---|---|---|---|
| 1 | **hero_first_reveal** (rest → challenged → faithfulness → certainty → source span → signature → disclosure; 6 beats) | 0, 120, 250, 400, 600, 700 | 0, 120, 200 (opacity-only crossfade) |
| 2 | **hero_claim_switch** (claim N → claim N+1; <120ms perceived per plan §14) | 0, 40, 120 | 0, 60, 120 (opacity crossfade) |
| 3 | **hero_sentence_hover** (rest → hover) | 0, 60, 120 | NONE (no hover transition; document the omission as the reduced-motion contract) |
| 4 | **hero_sentence_focus** (rest → focus-visible) | 0, 80, 160 | 0, 160 (instant ring) |
| 5 | **hero_mobile_sheet_open** | 0, 100, 220 | 0, 120 (instant pop) |
| 6 | **hero_mobile_sheet_close** | 0, 100, 180 | 0, 120 (instant collapse) |
| 7 | **hero_failure_no_verified** (abort state reveal) | 0, 200, 400 | 0, 200 |
| 8 | **hero_failure_refuse** (clinical-safety refuse state) | 0, 200, 400 | 0, 200 |

Timing rationale (frontier-bar + clinical-safety):
- 6-beat reveal at ~700ms total — within Vercel design-guideline 400-800ms range for hero choreography; below threshold where "lively" becomes "slow" (Linear / Stripe land in 500-700ms for hero reveals).
- Claim switch <120ms — perceptual instantness threshold (Doherty / Card Robertson Mackinlay) prevents the "wait, did anything happen" pause that would erode trust in a clinical-evidence interface.
- Reduced-motion equivalents respect WCAG 2.2 2.3.3 (prefers-reduced-motion) — opacity-only, no parallax, no slide, no scale.

## Annotation overlay (mandatory on EACH still)

Each PNG carries a 16px bottom-bar overlay drawn IN the Figma frame (not as filename metadata) with:

```
<scene>  ·  t=<ms>  ·  <state>  ·  <viewport>  ·  <reduced-motion: yes|no>
```

Codex reads timing from BOTH the filename AND the on-frame annotation — defensive redundancy ensures it can't misread the timing axis.

## What gets audited

Each scene = 1 annotated-still sequence. Codex audits:
- Visual continuity across timestamps (does the motion feel coherent vs jumpy?)
- Beat sequencing (does the eye land on the right element at the right time?)
- Cause-effect clarity (per Vercel design-guideline motion principle: does the motion explain what's happening?)
- Reduced-motion equivalence (does the reduced-motion final state convey the same information without the time-axis?)
- Clinical-safety read (does the motion ever obscure the two-judgment separation or the source-span attribution?)

Per Codex iter-1 D3 cadence lock: ONE hero-motion audit (covering all scenes above), not per-scene. Hero motion grammar is what's being locked, not 8 separate motion treatments.

## What does NOT get audited via stills

- Pixel-precise easing curve (cubic-bezier vs spring) — deferred to I-ux-001c code-time Playwright timing trace
- Real frame rate / GPU layer compositing — code-time concern
- prefers-reduced-motion media-query enforcement — code-time concern (the still convention shows what reduced-motion LOOKS like; the code enforces it)

These deferrals are in line with plan §14: motion is *specified* here, *enforced* at code time.

## Out-of-scope motion for #879

The per-family templates + per-page hero frames are STATIC in #879. Page-to-page transitions (route changes, modal opens, drawer slides on non-hero pages) are deferred to I-ux-001c code-time. The motion language locked here is INTRA-HERO; the cross-page extrapolation happens in code.
