/**
 * I-f13-001: Pin replay demo registry. In production this would fetch from
 * `/runs/{run_id}/pins/{date}` per M-INT-0b post-Carney; today the registry
 * is hand-authored frontend demo data.
 *
 * I-f13-004: added `retracted_source_ids` for source-retraction adversarial.
 */

export interface PinSnapshot {
  pin_date: string;
  query: string;
  verdict: "success" | "abort_no_verified_sections";
  section_count_kept: number;
  section_count_dropped: number;
  verified_sentence_count: number;
  pass_rate: number;
  retracted_source_ids?: string[];
}

export const DEMO_PIN_REGISTRY: Record<string, PinSnapshot> = {
  "2026-01-15": {
    pin_date: "2026-01-15",
    query: "Tirzepatide vs semaglutide cardiovascular outcomes",
    verdict: "success",
    section_count_kept: 4,
    section_count_dropped: 1,
    verified_sentence_count: 18,
    pass_rate: 0.72,
  },
  "2026-03-01": {
    pin_date: "2026-03-01",
    query: "Tirzepatide vs semaglutide cardiovascular outcomes",
    verdict: "success",
    section_count_kept: 5,
    section_count_dropped: 0,
    verified_sentence_count: 21,
    pass_rate: 0.79,
  },
  "2026-04-30": {
    pin_date: "2026-04-30",
    query: "Tirzepatide vs semaglutide cardiovascular outcomes",
    verdict: "success",
    section_count_kept: 5,
    section_count_dropped: 0,
    verified_sentence_count: 23,
    pass_rate: 0.85,
    retracted_source_ids: ["demo-clin-002"],
  },
  "2026-05-15": {
    pin_date: "2026-05-15",
    query: "Tirzepatide vs semaglutide cardiovascular outcomes",
    verdict: "success",
    section_count_kept: 4,
    section_count_dropped: 1,
    verified_sentence_count: 17,
    pass_rate: 0.83,
    retracted_source_ids: ["demo-clin-002", "demo-clin-005"],
  },
};
