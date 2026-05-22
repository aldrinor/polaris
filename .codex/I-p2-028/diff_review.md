# Codex DESIGN+DIFF review — I-p2-028 (#767): Braille maple-leaf signature

HARD ITERATION CAP: 5. iter 2 (iter-1 P1: always-render pre→IO engages; P2: catch disposes WebGL). APPROVE iff zero P0/P1 (the iter-2 brief plan implemented faithfully + perf/a11y). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `b439f507445c64364b13beaffc202fee9eb26405306814afab9fc021237b087a` (excludes package-lock.json noise). web/ only.

## Claude's VISUAL audit (rendered via the production standalone harness @1366, viewed; Codex can't view PNGs):
- A recognizable red (#c8102e) Braille-density maple leaf renders above the hero on white, fine U+2800 dots (NOT crude ASCII), decorative, subtle. Sent to operator.
- Honest note: stylized ~5-lobe silhouette at 60×20 Braille res — recognizable but slightly rough; refinement is a possible P2 (operator may tweak).

## Diff
- NEW maple_leaf_signature.tsx: three.js ExtrudeGeometry(maple Shape) → OrthographicCamera → WebGLRenderTarget(120×80) → readRenderTargetPixels → luminance grid → exact U+2800 bitmask (DOT_BITS left/right cols, Y-flipped for WebGL bottom-up) → <pre> red #c8102e. rAF capped ~24fps + rotate/float; prefers-reduced-motion → single frame; IntersectionObserver pause; dispose() on unmount; try/catch WebGL → graceful null.
- NEW maple_leaf_signature_lazy.tsx: "use client" dynamic(ssr:false) boundary → three stays out of the initial bundle.
- page.tsx + sign-in/page.tsx: mount <MapleLeafSignatureLazy /> (home hero + sign-in header). + three / @types/three deps.

## Review focus (per the iter-2-APPROVE'd plan)
1. Lazy boundary correct (three in a dynamic chunk, not initial bundle)? Braille bitmask order exact (no scramble)? Y-flip correct? polarity (leaf=dots on white)?
2. PERF/leaks: rAF cap + IO pause + dispose all wired; no leak; #c8102e hardcoded (not --primary)?
3. a11y: aria-hidden decorative + reduced-motion static + WebGL-unavailable graceful; home+sign-in only?
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
