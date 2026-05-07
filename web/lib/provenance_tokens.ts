// I-f5-003 — frontend mirror of polaris_graph.generator2.provenance.

const TOKEN_RE = /^\[#ev:([a-zA-Z0-9_\-]+):(\d+)-(\d+)\]$/;

export interface ParsedToken {
  raw: string;
  source_id: string;
  start: number;
  end: number;
}

export function parseProvenanceToken(token: string): ParsedToken | null {
  const match = TOKEN_RE.exec(token.trim());
  if (!match) return null;
  return {
    raw: token,
    source_id: match[1],
    start: parseInt(match[2], 10),
    end: parseInt(match[3], 10),
  };
}

export function parseAllTokens(tokens: string[]): ParsedToken[] {
  return tokens
    .map(parseProvenanceToken)
    .filter((t): t is ParsedToken => t !== null);
}
