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

/** A cited span rendered WITH its real surrounding source context so it reads
 * naturally, while the EXACT cited passage stays auditable. `span` is exactly
 * `full_text[start:end]` (unchanged — faithful); `before`/`after` are real
 * adjacent source text snapped to word boundaries; the ellipsis flags signal
 * the context is a window, not the whole body. No synthetic text is introduced. */
export interface SpanInContext {
  before: string;
  span: string;
  after: string;
  leadingEllipsis: boolean;
  trailingEllipsis: boolean;
}

/** I-p2-038 (#821): build a word-boundary-snapped context window around an exact
 * cited span so the proof reads naturally (the raw span often starts mid-token).
 * Returns null when the span itself can't be sliced from `fullText`. */
export function spanInContext(
  fullText: string | null | undefined,
  start: number,
  end: number,
  window = 90,
): SpanInContext | null {
  if (
    typeof fullText !== "string" ||
    start < 0 ||
    end > fullText.length ||
    start > end
  ) {
    return null;
  }
  const span = fullText.slice(start, end);
  // Expand left to a word boundary (so `before` doesn't itself start mid-word).
  let ctxStart = Math.max(0, start - window);
  if (ctxStart > 0) {
    const sp = fullText.indexOf(" ", ctxStart);
    if (sp !== -1 && sp < start) ctxStart = sp + 1;
  }
  // Expand right to a word boundary.
  let ctxEnd = Math.min(fullText.length, end + window);
  if (ctxEnd < fullText.length) {
    const sp = fullText.lastIndexOf(" ", ctxEnd);
    if (sp !== -1 && sp > end) ctxEnd = sp;
  }
  return {
    before: fullText.slice(ctxStart, start),
    span,
    after: fullText.slice(end, ctxEnd),
    leadingEllipsis: ctxStart > 0,
    trailingEllipsis: ctxEnd < fullText.length,
  };
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
