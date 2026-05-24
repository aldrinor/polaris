/**
 * useGraphState — single source of truth for ClaimGraph interaction state.
 *
 * Holds selected node + search query; exposes a memoized `visible_node_ids`
 * set (filtered by search) and an `adjacency` map for arrow-key edge
 * traversal. Both ClaimGraph (canvas) and AccessibleGraphList (parallel
 * `<ol>`) consume this hook to stay in sync.
 *
 * I-snowball-004 (combined 004a + 004b scope per DECISION.md).
 */

import { useMemo, useState } from "react";

import type { GraphNode, GraphPayload } from "@/lib/api";

export interface GraphState {
  selected_node_id: string | null;
  search_query: string;
  visible_node_ids: Set<string>;
  snowball_highlight_ids: Set<string> | null;
}

export interface GraphAdjacency {
  /** Outgoing semantic-edge targets, excluding `section_member`. */
  out: Map<string, string[]>;
  /** Incoming semantic-edge sources, excluding `section_member`. */
  in: Map<string, string[]>;
}

export interface GraphActions {
  setSelectedNodeId: (id: string | null) => void;
  setSearchQuery: (q: string) => void;
  setSnowballHighlight: (ids: Set<string> | null) => void;
}

/** Shared search predicate used by list filter AND canvas highlight (Codex iter-2 P2-1.5). */
export function nodeMatchesQuery(node: GraphNode, query: string): boolean {
  if (!query.trim()) return true;
  const q = query.toLowerCase();
  return (
    node.data.label.toLowerCase().includes(q) ||
    node.data.id.toLowerCase().includes(q)
  );
}

export function useGraphState(
  payload: GraphPayload,
): [GraphState, GraphAdjacency, GraphActions] {
  // I-p2-058 (#863): open with a FOCAL node already selected (a section anchor,
  // else the first node) so the graph lands on a narrative path — the spotlight
  // is the default product moment, not something you must discover by clicking
  // (Codex frontier audit iter-2 P1). Lazy initializer → no setState-in-effect.
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    () =>
      payload.elements.nodes.find((n) => n.data.type === "section")?.data.id ??
      payload.elements.nodes[0]?.data.id ??
      null,
  );
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [snowballHighlight, setSnowballHighlight] =
    useState<Set<string> | null>(null);

  const visibleNodeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const n of payload.elements.nodes) {
      if (nodeMatchesQuery(n, searchQuery)) ids.add(n.data.id);
    }
    return ids;
  }, [payload, searchQuery]);

  const adjacency = useMemo<GraphAdjacency>(() => {
    const out = new Map<string, string[]>();
    const inc = new Map<string, string[]>();
    for (const n of payload.elements.nodes) {
      out.set(n.data.id, []);
      inc.set(n.data.id, []);
    }
    for (const e of payload.elements.edges) {
      if (e.data.edge_type === "section_member") continue;
      out.get(e.data.source)?.push(e.data.target);
      inc.get(e.data.target)?.push(e.data.source);
    }
    return { out, in: inc };
  }, [payload]);

  return [
    {
      selected_node_id: selectedNodeId,
      search_query: searchQuery,
      visible_node_ids: visibleNodeIds,
      snowball_highlight_ids: snowballHighlight,
    },
    adjacency,
    { setSelectedNodeId, setSearchQuery, setSnowballHighlight },
  ];
}
