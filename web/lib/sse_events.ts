// I-f4-002 — Live audit-run event types (6 dedicated UI panels).

export const EVENT_NAMES = [
  "query_reform",
  "retrieval_candidate",
  "source_dropped",
  "synthesis_decision",
  "contradiction",
  "verify_decision",
] as const;

export type SSEEventName = (typeof EVENT_NAMES)[number];

export const EVENT_LABELS: Record<SSEEventName, string> = {
  query_reform: "Query reformulations",
  retrieval_candidate: "Retrieval candidates",
  source_dropped: "Sources dropped",
  synthesis_decision: "Synthesis decisions",
  contradiction: "Contradiction events",
  verify_decision: "Per-sentence verify decisions",
};

export interface LoggedEvent {
  name: SSEEventName;
  ts: number;
  payload: string;
}
