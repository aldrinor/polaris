# Codex brief — I-p2-050 (#847): fix distorted maple-leaf signature (keep ASCII art)

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings; reserve P0/P1 for real risks. APPROVE
iff the plan fixes the distortion within the operator-chosen ASCII-art constraint.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Operator decision (LOCKED)
The maple-leaf signature (#767) renders distorted. Operator chose: KEEP the three.js→Braille
ASCII-art concept, FIX it (not replace with SVG, not remove).

## Plan (web/components/signature/maple_leaf_signature.tsx)
1. Replace the crude MAPLE_HALF shape with an accurate maple half-silhouette (stem/3 lobes/
   notches/top), mirrored.
2. Remove `mesh.rotation.y` (the edge-on foreshortening) — keep only a gentle in-plane
   rotation.z sway.
3. Aspect: render-target 96×120 + camera frustum matched (no horizontal stretch); display
   line-height ~1.05 so each Braille glyph cell displays ~1:2 like its 2×4 source block.
4. Iterate on screenshots until it reads as a recognizable maple leaf; preserve aria-hidden,
   reduced-motion static, WebGL-graceful, lazy, brand #c8102e.

## Acceptance
Reads as a recognizable upright maple leaf (distortion gone); ASCII texture kept; dual Codex
gate (visual + diff); deploy + live-verify Home + Sign-in.

## Note
Already executed + gated downstream: visual `-i` APPROVE (closeup A- / hero A-); code diff
APPROVE (no out-of-bounds, frustum fits, a11y/disposal preserved). This brief records the
acceptance criteria for the artifact set.
