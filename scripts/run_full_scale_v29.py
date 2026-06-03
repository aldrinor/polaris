"""V29 full-scale launcher — V28 code + M-51/52/53 custody bundle.

V29 = V28 code + Strategy β cycle 1 of 4:
  - M-51: Selector hard-reservation of anchor-matched primaries
          from live_corpus (Codex CONDITIONAL-no-blockers pass-1)
  - M-52: Generator-side pull from live_corpus when evidence_pool
          lacks anchor-matched primary (Codex audit pending)
  - M-53: Per-anchor custody telemetry v29_primary_custody.json
          (Codex-required diagnostic; M-49 assertion extension)

V29 target per strategic cross-review: 4-5 BB + 2-3 BO + 0-1 LB.
Lift Dims 1/4/5 from LOSE_BOTH to ≥BEAT_ONE. Dim 7 (Narrative) may
still lag (V31 is the dedicated closure cycle).

V28 outcome (2026-04-22 23:14, 2h51m, $0.018):
  - Cross-reviewed: 3 BB + 0 BO + 4 LB (NOT SHIPPABLE)
  - Net ≥BEAT_ONE count regressed 5 → 3 vs V27
  - Root cause: primary papers in live_corpus but dropped by selector
    (SURPASS-4 Del Prato + SURPASS-CVOT Nicholls verified by Codex)

V29 bundle addresses this single defect at both the selector (M-51)
and generator (M-52) boundaries, with M-53 telemetry to diagnose
precisely where the chain breaks if it still does.

Usage:
    python scripts/run_full_scale_v29.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_V29_ENV: dict[str, str] = {
    # Sweep-level retrieval knobs (unchanged from V28)
    "PG_SWEEP_MAX_SERPER":    "50",
    "PG_SWEEP_MAX_S2":        "50",
    "PG_SWEEP_FETCH_CAP":     "500",
    "PG_LIVE_MAX_EV_TO_GEN":  "300",
    "PG_MAX_COST_PER_RUN":    "10.00",

    # Access-bypass feature flags
    "PG_UNPAYWALL_ENABLED":   "1",
    "PG_CRAWL4AI_ENABLED":    "1",
    "PG_FIRECRAWL_ENABLED":   "0",
    "PG_TRAFILATURA_ENABLED": "1",

    # Scraper circuit breakers
    "PG_CRAWL4AI_TIMEOUT":    "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD": "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":  "120",
    "PG_SCIHUB_ENABLED":      "0",

    # M-42d: HC T3 quota
    "PG_M41D_HC_QUOTA":       "2",

    # M-43: regulatory anchor cap (11 in clinical.yaml; fits cap=12)
    "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",

    # M-35: primary-trial anchor cap
    "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
}


def _apply_env() -> None:
    for key, val in _V29_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V29 env]  {key} = {val}")
        else:
            print(f"[V29 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v29"])

    print("=" * 72)
    print(f"V29 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
