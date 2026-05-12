/**
 * graph_export — browser-side PNG + JSON downloads for ClaimGraph.
 *
 * `exportPNG(cy)` returns a Promise<Blob> via cytoscape's `cy.png({...,
 * output: 'blob-promise'})`. 4x scale for retina-grade output.
 *
 * `exportJSON(payload)` produces a Blob whose body is the canonicalized
 * elements JSON: positions stripped, nodes+edges sorted by id, keys
 * recursively sorted, no whitespace. Mirrors backend
 * `src/polaris_graph/api/graph_route.py:206-216` (modulo Python
 * `ensure_ascii=True` vs JSON.stringify; consumer hashes the canonical
 * form, so non-ASCII characters serialized differently between Python
 * and JS will not byte-match. Documented; OK for v1 since labels are
 * latin-1 by convention).
 *
 * `triggerDownload(blob, filename)` uses URL.createObjectURL + temp
 * `<a download>` click, then revokes the URL after the click is
 * dispatched.
 */

import type cytoscape from "cytoscape";

import type { GraphPayload } from "@/lib/api";

export async function exportPNG(
  cy: cytoscape.Core | null,
): Promise<Blob | null> {
  if (!cy) return null;
  const result = await cy.png({
    full: true,
    scale: 4,
    output: "blob-promise",
  });
  return result as Blob;
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    const sorted: Record<string, unknown> = {};
    for (const k of Object.keys(value as Record<string, unknown>).sort()) {
      sorted[k] = sortKeys((value as Record<string, unknown>)[k]);
    }
    return sorted;
  }
  return value;
}

export function exportJSON(payload: GraphPayload): Blob {
  const nodes = payload.elements.nodes
    .map((n) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { position: _drop, ...rest } = n;
      return rest;
    })
    .sort((a, b) =>
      a.data.id < b.data.id ? -1 : a.data.id > b.data.id ? 1 : 0,
    );
  const edges = [...payload.elements.edges].sort((a, b) =>
    a.data.id < b.data.id ? -1 : a.data.id > b.data.id ? 1 : 0,
  );
  const canonical = JSON.stringify(sortKeys({ nodes, edges }));
  return new Blob([canonical], { type: "application/json" });
}

export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke after the click has been dispatched to free memory.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
