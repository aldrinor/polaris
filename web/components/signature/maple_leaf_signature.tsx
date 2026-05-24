// I-p2-028 (#767): the flying maple-leaf signature, rendered in fine-grained
// Braille/Unicode density art (U+2800, 2×4 dots per glyph). three.js extrudes a
// maple-leaf shape, renders it to an offscreen render target, and each frame the
// luminance grid is mapped to Braille glyphs (dark-red leaf on white). Decorative
// (aria-hidden); prefers-reduced-motion → one static frame; WebGL-unavailable →
// graceful absence; lazy-loaded (this module + three live behind a dynamic import).
"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

// Offscreen render resolution → Braille grid (2px×4px per glyph). I-p2-050 (#847):
// the source is sized slightly TALLER than wide to match a maple leaf, and the
// camera frustum (below) is sized to the SAME aspect so the rendered leaf is not
// stretched. PX_H must be a multiple of 4, PX_W a multiple of 2.
const PX_W = 96;
const PX_H = 120;
const GLYPH_W = PX_W / 2; // 48
const GLYPH_H = PX_H / 4; // 30
const LUMA_THRESHOLD = 200; // below = leaf pixel (dot set)
const FRAME_MS = 1000 / 24; // cap ~24fps

// Canonical Braille dot bitmask per [row][col=left,right]: rows 0-3 top→bottom.
const DOT_BITS: readonly [number, number][] = [
  [0x01, 0x08], // row 0: left, right
  [0x02, 0x10], // row 1
  [0x04, 0x20], // row 2
  [0x40, 0x80], // row 3
];

// A symmetric, recognizable maple-leaf half-silhouette (x>=0, bottom→top),
// mirrored to form the full leaf. Normalized to roughly [-1, 1]. I-p2-050 (#847):
// rebuilt to trace the iconic Canadian leaf — narrow stem, three lobes (lower,
// middle/widest, upper) separated by deep V-notches, tapering to a sharp top point.
const MAPLE_HALF: readonly [number, number][] = [
  [0.0, -1.0], // stem tip (bottom)
  [0.05, -0.55], // stem shoulder → leaf base
  [0.17, -0.5], // lower lobe rise
  [0.12, -0.36], // notch in
  [0.42, -0.34], // lower lobe point
  [0.27, -0.13], // notch in
  [0.66, -0.1], // middle lobe point (widest)
  [0.37, 0.05], // deep notch
  [0.44, 0.27], // upper lobe point
  [0.2, 0.25], // notch in
  [0.26, 0.54], // upper inner point
  [0.09, 0.55], // notch near top
  [0.12, 0.82], // top shoulder
  [0.0, 1.0], // top tip
];

function buildLeafShape(): THREE.Shape {
  const shape = new THREE.Shape();
  shape.moveTo(MAPLE_HALF[0][0], MAPLE_HALF[0][1]);
  for (let i = 1; i < MAPLE_HALF.length; i++) {
    shape.lineTo(MAPLE_HALF[i][0], MAPLE_HALF[i][1]);
  }
  // Mirror back down the left side (skip the shared top + bottom points).
  for (let i = MAPLE_HALF.length - 2; i >= 1; i--) {
    shape.lineTo(-MAPLE_HALF[i][0], MAPLE_HALF[i][1]);
  }
  shape.closePath();
  return shape;
}

function pixelsToBraille(buf: Uint8Array): string {
  const lines: string[] = [];
  for (let gy = 0; gy < GLYPH_H; gy++) {
    let line = "";
    for (let gx = 0; gx < GLYPH_W; gx++) {
      let mask = 0;
      for (let dr = 0; dr < 4; dr++) {
        for (let dc = 0; dc < 2; dc++) {
          const px = gx * 2 + dc;
          const py = gy * 4 + dr;
          // WebGL readback is bottom-up → flip Y so the leaf is upright.
          const bufRow = PX_H - 1 - py;
          const idx = (bufRow * PX_W + px) * 4;
          const luma =
            0.299 * buf[idx] + 0.587 * buf[idx + 1] + 0.114 * buf[idx + 2];
          if (luma < LUMA_THRESHOLD) mask |= DOT_BITS[dr][dc];
        }
      }
      line += String.fromCodePoint(0x2800 + mask);
    }
    lines.push(line);
  }
  return lines.join("\n");
}

export default function MapleLeafSignature() {
  const [art, setArt] = useState<string>("");
  const preRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    let renderer: THREE.WebGLRenderer | null = null;
    let target: THREE.WebGLRenderTarget | null = null;
    let geometry: THREE.ExtrudeGeometry | null = null;
    let material: THREE.MeshBasicMaterial | null = null;
    let rafId = 0;
    let lastFrame = 0;
    let visible = true;
    let cancelled = false;

    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setClearColor(0xffffff, 1); // white surface
      renderer.setSize(PX_W, PX_H, false);
      target = new THREE.WebGLRenderTarget(PX_W, PX_H);

      const scene = new THREE.Scene();
      // I-p2-050 (#847): frustum aspect = PX_W:PX_H (0.8) so the rendered leaf is
      // NOT horizontally stretched; sized to fit the [-1,1] leaf with margin.
      const cam = new THREE.OrthographicCamera(
        -0.944,
        0.944,
        1.18,
        -1.18,
        0.1,
        10,
      );
      cam.position.z = 3;

      geometry = new THREE.ExtrudeGeometry(buildLeafShape(), {
        depth: 0.35,
        bevelEnabled: false,
      });
      geometry.center();
      material = new THREE.MeshBasicMaterial({ color: 0xc8102e }); // Canada red
      const mesh = new THREE.Mesh(geometry, material);
      scene.add(mesh);

      const buf = new Uint8Array(PX_W * PX_H * 4);
      const renderOnce = (t: number) => {
        // I-p2-050 (#847): NO rotation.y — a Y-spin foreshortens the leaf edge-on
        // (the old distortion). Keep only a gentle IN-PLANE sway (rotation.z), so it
        // still "floats" per #767 but always reads as an upright, face-on leaf.
        mesh.rotation.z = Math.sin(t * 0.0005) * 0.14;
        renderer!.setRenderTarget(target!);
        renderer!.render(scene, cam);
        renderer!.readRenderTargetPixels(target!, 0, 0, PX_W, PX_H, buf);
        renderer!.setRenderTarget(null);
        if (!cancelled) setArt(pixelsToBraille(buf));
      };

      const reduce = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;

      if (reduce) {
        renderOnce(900); // a single, pleasing static frame
      } else {
        const loop = (t: number) => {
          rafId = requestAnimationFrame(loop);
          if (!visible || t - lastFrame < FRAME_MS) return;
          lastFrame = t;
          renderOnce(t);
        };
        rafId = requestAnimationFrame(loop);
      }

      // Pause the loop when the signature is scrolled offscreen.
      const io = new IntersectionObserver(
        (entries) => {
          visible = entries[0]?.isIntersecting ?? true;
        },
        { threshold: 0 },
      );
      if (preRef.current) io.observe(preRef.current);

      return () => {
        cancelled = true;
        cancelAnimationFrame(rafId);
        io.disconnect();
        geometry?.dispose();
        material?.dispose();
        target?.dispose();
        renderer?.dispose();
      };
    } catch {
      // WebGL unavailable / setup failure → dispose anything allocated +
      // graceful absence (decorative only). (Codex iter-1 P2.)
      geometry?.dispose();
      material?.dispose();
      target?.dispose();
      renderer?.dispose();
      return () => {
        cancelled = true;
      };
    }
  }, []);

  // Always render the <pre> (even before the first frame) so the
  // IntersectionObserver in the effect has a stable element to observe — the
  // offscreen perf-pause depends on it (Codex iter-1 P1). It's empty (0 lines)
  // until the first frame fills `art`.
  return (
    <pre
      ref={preRef}
      aria-hidden
      className="pointer-events-none overflow-hidden font-mono text-[5px] leading-[1.05] tracking-[-0.06em] select-none sm:text-[6px]"
      style={{ color: "#c8102e" }}
    >
      {art}
    </pre>
  );
}
