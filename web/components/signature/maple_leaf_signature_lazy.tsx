// I-p2-028 (#767): client lazy boundary for the maple-leaf signature. The heavy
// module (three.js + the Braille renderer) loads ONLY here, as a dynamic chunk,
// so it never enters the initial route bundle (G-PERF). Decorative; ssr:false
// because it needs WebGL + window.
"use client";

import dynamic from "next/dynamic";

const MapleLeafSignature = dynamic(() => import("./maple_leaf_signature"), {
  ssr: false,
  loading: () => null,
});

export function MapleLeafSignatureLazy() {
  return <MapleLeafSignature />;
}
