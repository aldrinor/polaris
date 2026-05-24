# Claude architect audit — I-p2-050 (#847): fix distorted maple-leaf signature

## Goal
The #767 three.js→Braille maple-leaf signature rendered as an unrecognizable distorted pixel
cloud on Home + Sign-in (front door + auth). Operator flagged it; operator chose KEEP the
ASCII-art concept and fix it. Make it read as a recognizable, upright maple leaf.

## Root causes → fixes (1 file: maple_leaf_signature.tsx, +40/-22)
1. **Edge-on foreshortening:** `mesh.rotation.y = t*0.0006` spun it around the vertical axis →
   most frames a skewed sliver. REMOVED; kept only a gentle in-plane `rotation.z` sway (still
   "floats" per #767, always face-on).
2. **Crude shape:** the 12-pt MAPLE_HALF traced a spiky generic polygon → rebuilt as a 14-pt
   accurate maple half-silhouette (narrow stem, 3 lobes, deep V-notches, pointed top), mirrored.
3. **Horizontal squash:** 120×80 source vs a square camera frustum stretched the leaf →
   source 96×120 + camera frustum matched to that aspect (faithful); bbox now ~square (188×189,
   was 1.5:1).
4. **Display squash:** `leading-[0.62]` compressed line-height to ~half → leaf displayed wide.
   Now `leading-[1.05]` so each Braille glyph cell displays ~1:2, matching its 2px×4px source
   block; font text-[5px] sm:text-[6px] to offset the taller leading.

## Preserved
Decorative aria-hidden; prefers-reduced-motion → static frame; WebGL-unavailable graceful
absence; lazy dynamic import; IntersectionObserver offscreen-pause; dispose-on-unmount; brand
`#c8102e`. (DOT_BITS + pixelsToBraille loops unchanged; Codex verified no out-of-bounds —
max idx 46078 < 46080 buffer.)

## Honest residual (P2, accepted with the ASCII choice)
The tiny red Braille dots still show mild red→pink/orange antialias fringing at ~5-6px, and the
lobe points are slightly soft — inherent to dotted-glyph art at small size, which the operator
chose to keep. The S+ refinement (render at a larger source before downscaling to sharpen) is a
follow-up; it does not block recognition. The PRIMARY defect (distorted/edge-on/squashed →
unrecognizable) is fixed.

## Dual Codex gate
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 1: closeup A- / hero A-; distortion gone,
  reads as a recognizable maple leaf). Code diff APPROVE (iter 1, zero findings, bounds verified).
- Render gates green (home G1/G6/G3, sign-in form render).

canonical-diff-sha256: 5adcb5d3aadac823245c300d67f2e5bcb95d18037e6f5d2f26b9b3b4d764abe5
