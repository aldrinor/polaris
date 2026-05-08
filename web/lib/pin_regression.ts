/**
 * I-f13-003: Inline regression alerts on the pin-replay page. Hard-coded
 * thresholds; production reads from a regression-config file (post-Carney).
 */

import type { PinSnapshot } from "@/lib/pin_replay_demo";

export const REGRESSION_THRESHOLDS = {
  pass_rate_pct_drop: 5,
  verified_sentence_count_drop: 3,
} as const;

export interface RegressionAlert {
  metric: "pass_rate" | "verified_sentence_count";
  a_value: number;
  b_value: number;
  drop: number;
  threshold: number;
  unit: "pct" | "count";
}

export function detectRegressions(
  a: PinSnapshot,
  b: PinSnapshot,
): RegressionAlert[] {
  const alerts: RegressionAlert[] = [];

  const a_pass_pct = Math.round(a.pass_rate * 100);
  const b_pass_pct = Math.round(b.pass_rate * 100);
  const pass_drop = a_pass_pct - b_pass_pct;
  if (pass_drop > REGRESSION_THRESHOLDS.pass_rate_pct_drop) {
    alerts.push({
      metric: "pass_rate",
      a_value: a_pass_pct,
      b_value: b_pass_pct,
      drop: pass_drop,
      threshold: REGRESSION_THRESHOLDS.pass_rate_pct_drop,
      unit: "pct",
    });
  }

  const sentence_drop = a.verified_sentence_count - b.verified_sentence_count;
  if (sentence_drop > REGRESSION_THRESHOLDS.verified_sentence_count_drop) {
    alerts.push({
      metric: "verified_sentence_count",
      a_value: a.verified_sentence_count,
      b_value: b.verified_sentence_count,
      drop: sentence_drop,
      threshold: REGRESSION_THRESHOLDS.verified_sentence_count_drop,
      unit: "count",
    });
  }

  return alerts;
}
