# Codex BRIEF review — I-p2-028 (#767): three.js flying maple-leaf Braille signature

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## OPERATOR-LOCKED constraints (HARD — NOT consultable; do not relax)
- A flying maple-leaf signature rendered in **fine-grained Braille/Unicode density art** (U+2800 block, 2×4 dots per glyph) — NOT crude `#@*` ASCII. Operator sent a Braille-art reference image.
- **three.js** is the operator-specified 3D source (3D maple leaf → render to canvas → luminance → Braille glyph grid). Implement WITH three.js.
- **Dark Canada-flag red (#c8102e) on white**; monospace; gentle flying motion.
- **Home + sign-in only.** aria-hidden (decorative). prefers-reduced-motion → static frame (no animation). Lazy-loaded (dynamic import; NOT in the initial route bundle).

## Task
A `MapleLeafSignature` client component: three.js renders a 3D maple-leaf geometry to an offscreen canvas; each frame samples luminance on a grid and maps 2×4 luminance cells → Braille codepoints (U+2800 + dot-bitmask); renders the glyph grid in a monospace `<pre>` (red on white); rAF loop gently rotates/floats the leaf. Reduced-motion → render one static frame, no rAF. Decorative (aria-hidden). Mounted on home + sign-in only.

## Implementation plan (Codex: vet feasibility + perf + a11y)
1. `npm i three` + `@types/three`. Dynamic-import three (next/dynamic ssr:false OR `await import("three")` inside the client effect) so it's a LAZY chunk, never in the initial bundle (G-PERF: route JS < 250KB initial).
2. Maple-leaf geometry: extrude a 2D maple-leaf `THREE.Shape` (canonical 11-point maple silhouette path) via `ExtrudeGeometry` (small depth) → a real 3D leaf. Mesh material flat; orthographic-ish camera.
3. Offscreen render: `WebGLRenderer` to an offscreen canvas at a low resolution (e.g. ~120×80 px → ~60×20 Braille glyphs). Each frame: read pixels (or render to a 2D canvas) → luminance per pixel → for each 2×4 cell compute the Braille dot bitmask (threshold) → codepoint 0x2800 + bitmask → build the glyph-grid string.
4. Render the string in `<pre className="font-mono text-primary ...">`, aria-hidden. rAF loop rotates the mesh (gentle Y/Z), updates the grid. prefers-reduced-motion: render once, cancel rAF.
5. Perf budget: cap FPS (~20-30), low render res, pause via IntersectionObserver when offscreen, dispose() geometry/renderer on unmount. WebGL-unavailable → static fallback (no crash).

## Files I have ALSO checked and they're clean
- web/package.json (three NOT installed — needs add), web/app/page.tsx (home — mount point), web/app/sign-in/page.tsx (sign-in — mount point), web/app/globals.css (#742 --primary #c8102e + prefers-reduced-motion is NOT in globals → handle locally via matchMedia).

## Review focus
1. Is the three.js → offscreen → luminance → Braille (U+2800 2×4) pipeline correct + feasible? Any WebGL/SSR pitfall (Next 16, ssr:false, readPixels)?
2. PERF: three.js as a LAZY dynamic chunk (not initial bundle); rAF capped + IntersectionObserver pause + dispose on unmount — does this respect G-PERF? Any leak risk?
3. a11y: aria-hidden decorative + prefers-reduced-motion static + WebGL-unavailable fallback (no crash) all covered?
4. Honesty/scope: decorative only (no false meaning); home+sign-in only. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 corrections (all iter-1 findings folded)
- **P1 (lazy/SSR boundary):** home + sign-in are Server Components. Create an explicit CLIENT loader `web/components/signature/maple_leaf_signature_lazy.tsx` ("use client") that does `const MapleLeaf = dynamic(() => import("./maple_leaf_signature"), { ssr: false, loading: () => null })`. Home/sign-in render `<MapleLeafSignatureLazy />`. The heavy module (`maple_leaf_signature.tsx`, which imports three) lives behind that dynamic boundary → a real lazy chunk, never in the initial route bundle.
- **P2 (WebGL readback):** use `WebGLRenderTarget` + `renderer.readRenderTargetPixels(target, 0,0,w,h, buffer)` for deterministic pixel readback (not WebGL-canvas→2D copy).
- **P2 (polarity):** `renderer.setClearColor(0xffffff, 1)` (white), render the leaf mesh in dark red; a Braille dot is SET when the cell pixel is LEAF (luminance below threshold), so the leaf is the dots on white. Handle alpha explicitly.
- **P2 (Braille dot order — EXACT, else the art scrambles):** per 2×4 cell, bitmask = OR of set dots using the canonical map — left column rows 0-3 = [0x01, 0x02, 0x04, 0x40], right column rows 0-3 = [0x08, 0x10, 0x20, 0x80]; glyph = String.fromCodePoint(0x2800 + bitmask). NO row-major shifting.
- **P2 (#c8102e):** hardcode `color: "#c8102e"` (or a `text-[#c8102e]` arbitrary) on the `<pre>`, NOT `text-primary` (which flips under `.dark`). White surface behind it.
Re-confirm APPROVE or list only true remaining P0/P1.
