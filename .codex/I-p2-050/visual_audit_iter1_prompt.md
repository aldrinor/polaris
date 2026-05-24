# Codex VISUAL audit — I-p2-050 (#847) maple-leaf signature, A++/S bar — iter 1 of 5

You have VISION. The maple-leaf signature (#767, three.js → Braille ASCII art on Home + Sign-in)
was DISTORTED — a spinning render foreshortened it edge-on + a crude shape + a squashed aspect
made it an unrecognizable colored pixel cloud. Operator flagged it; operator chose KEEP the
ASCII-art concept, fix it. Judge whether it now reads as a clean, recognizable maple leaf.

## What I changed
- New maple-leaf shape data (narrow stem, 3 lobes, deep V-notches, pointed top).
- REMOVED the rotation.y spin (the foreshortening cause) — now face-on, only a gentle in-plane sway.
- Fixed aspect: camera frustum matched to the render-target aspect + corrected the display
  line-height (was leading-0.62, squashing it wide; now ~1.05 so each Braille glyph cell
  displays ~1:2 like its 2×4 source block). Bbox is now ~square (188×189), was 1.5:1.

## Attached
1. `leaf_closeup.png` — the signature zoomed (2× DSF) — judge the SHAPE recognizability.
2. `home_fold.png` — the leaf at real size in the Home hero (top-center, above the pill).

## Known/locked
- Brand `#c8102e`. The Braille dots show some red→pink/orange color-fringing — inherent to
  rendering tiny red dotted-glyph art at ~5px (the ASCII aesthetic the operator chose to keep).
  Flag it P1 ONLY if it makes the leaf unacceptable for the front door; otherwise P2.
- Decorative (aria-hidden); reduced-motion → static; lazy + WebGL-graceful.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { leaf_closeup: "", home_fold: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff it now unambiguously reads as a recognizable maple leaf (distortion gone) at an
acceptable front-door bar, zero P0/P1.
