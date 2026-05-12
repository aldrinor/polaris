/**
 * snowballNeighbors — BFS frontier walk on the loaded GraphPayload.
 *
 * Pure function. Walks semantic edges only (cites + contradicts; NEVER
 * section_member or frame_member, which are styling-only per
 * I-snowball-002 brief iter 5 + I-snowball-001 DECISION.md).
 *
 * Undirected traversal (matches `cy.elements().bfs()` default and the
 * approved DECISION.md caveat). v1 scope per I-snowball-005 brief iter 2:
 * no `includeCoCites` parameter — current GraphEdgeType schema doesn't
 * include `co_cites_default_off`. Add it back when co-citation edges
 * land in a future PR.
 */

import type { GraphEdgeType, GraphPayload } from "@/lib/api";

const SEMANTIC_EDGE_TYPES: ReadonlySet<GraphEdgeType> = new Set([
  "cites",
  "contradicts",
]);

export function snowballNeighbors(
  payload: GraphPayload,
  targetId: string,
  maxHops: number,
): Set<string> {
  if (maxHops < 0) return new Set();
  // Build undirected adjacency on semantic edges only.
  const adj = new Map<string, Set<string>>();
  for (const n of payload.elements.nodes) {
    adj.set(n.data.id, new Set());
  }
  for (const e of payload.elements.edges) {
    if (!SEMANTIC_EDGE_TYPES.has(e.data.edge_type)) continue;
    adj.get(e.data.source)?.add(e.data.target);
    adj.get(e.data.target)?.add(e.data.source);
  }
  if (!adj.has(targetId)) return new Set();
  // BFS frontier walk
  const visited = new Set<string>([targetId]);
  let frontier: Set<string> = new Set([targetId]);
  for (let hop = 0; hop < maxHops; hop++) {
    const next = new Set<string>();
    for (const id of frontier) {
      for (const neighbor of adj.get(id) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          next.add(neighbor);
        }
      }
    }
    if (next.size === 0) break;
    frontier = next;
  }
  return visited;
}
