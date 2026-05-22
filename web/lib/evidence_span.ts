// I-p2-004 (#743): the SINGLE shared resolver for provenance-token → exact
// source span. Consumed by the citation chip now and by the Proof-Replay
// inspector (#756) — one resolver boundary, no duplicate parsing.
//
// No-synthetic-proof contract (Codex brief iter-2/3): returns quote=null
// (→ honest fallback) unless the bounds are fully valid against the actual
// source body. NEVER a silently-clamped slice (that would be synthetic proof).

import { parseProvenanceToken } from "@/lib/provenance_tokens";

export interface EvidenceSource {
  source_id: string;
  full_text?: string | null;
  snippet?: string | null;
  title?: string | null;
  url?: string | null;
  tier?: string | number | null;
}

export interface ResolvedSpan {
  raw: string;
  sourceId: string;
  source: EvidenceSource | null;
  start: number;
  end: number;
  /** The EXACT cited passage `full_text[start:end]`, or null when unresolved
   * (missing source / no full_text / out-of-range bounds) — never clamped. */
  quote: string | null;
}

function sourcesOf(evidencePool: unknown): EvidenceSource[] {
  const s = (evidencePool as { sources?: unknown } | null)?.sources;
  return Array.isArray(s) ? (s as EvidenceSource[]) : [];
}

/** Resolve a `[#ev:<id>:<start>-<end>]` token against the evidence pool.
 * Returns null if the token itself is malformed; otherwise a ResolvedSpan
 * whose `quote` is null unless every bound is valid against the real body. */
export function resolveSpan(
  token: string,
  evidencePool: unknown,
): ResolvedSpan | null {
  const parsed = parseProvenanceToken(token);
  if (!parsed) return null;
  // sources is an ARRAY → look up by source_id (never index).
  const source =
    sourcesOf(evidencePool).find((s) => s?.source_id === parsed.source_id) ??
    null;
  const body = source?.full_text ?? null; // exact span only from full_text
  let quote: string | null = null;
  if (
    typeof body === "string" &&
    body.length > 0 &&
    parsed.start >= 0 &&
    parsed.end <= body.length &&
    parsed.start <= parsed.end
  ) {
    quote = body.slice(parsed.start, parsed.end);
  }
  return {
    raw: token,
    sourceId: parsed.source_id,
    source,
    start: parsed.start,
    end: parsed.end,
    quote,
  };
}
