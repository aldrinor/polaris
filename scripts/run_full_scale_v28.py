"""V28 full-scale launcher — V27 code + M-44..M-50 bundle.

V28 = V27 code + complete M-44..M-50 V28 bundle:
  - M-44: primary-trial scorer/subset injection + same-sentence
          validator + one-shot regen (Codex pass-3 READY)
  - M-45: refetch diagnostics with per-URL backend/method + failure
          mode (Codex pass-2 SIGN OFF)
  - M-46: selector early-exit fix — floors fire even when
          pool_size <= max_rows (Codex READY)
  - M-47: evidence-linked clamp/PK quantitative validator with
          field-context tokens + regen (Codex pass-2)
  - M-48: per-anchor first-author variants + population-scope
          labels (Codex APPROVED pass-2)
  - M-50: per-trial subsections for T2D-direct primaries (Codex
          audit in flight)

V28 target (cross-reviewed content audit): 5 BEAT_BOTH + 2 BEAT_ONE
+ 0 LOSE_BOTH (up from V27's 3 BB + 2 BO + 2 LB).

V27 outcome (2026-04-22 06:58→11:11, 113.7 min):
  - 3 BEAT_BOTH (Regulatory, Jurisdictional, Contradictions)
  - 2 BEAT_ONE (Citations, Narrative depth)
  - 2 LOSE_BOTH (Claim frames, Structural depth)
  - Content audit: ChatGPT 4 wins / V27 1 / Gemini 1

V27 → V28 targeted lifts:
  - Citations: BEAT_ONE → BEAT_BOTH (M-44 + M-48 variants)
  - Claim frames: LOSE_BOTH → BEAT_BOTH (M-44 + M-45 table + M-50
    subsections)
  - Structural depth: LOSE_BOTH → BEAT_BOTH (M-45 table + M-50
    subsections)
  - Narrative depth: LOSE_BOTH → BEAT_ONE (M-47 + M-50)
  - Regulatory / Jurisdictional / Contradictions: BEAT_BOTH preserved

V28 preflight (optional, budget saver):
    python scripts/v28_retrieval_preflight.py \\
        --slug clinical_tirzepatide_t2dm \\
        --question "What is the efficacy..." \\
        --domain clinical

Usage:
    python scripts/run_full_scale_v28.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


LAUNCH_ENV: dict[str, str] = {
    # Sweep-level retrieval knobs
    "PG_SWEEP_MAX_SERPER":    "50",
    "PG_SWEEP_MAX_S2":        "50",
    "PG_SWEEP_FETCH_CAP":     "500",

    # M-46 (2026-04-22): PG_LIVE_MAX_EV_TO_GEN reduced 600 → 300 so
    # the selector's short-circuit path is less likely to trigger,
    # giving M-42e/c/d floors more surface area. M-46 SELECTOR fix
    # (committed in e6fd147) makes floors fire even in the
    # short-circuit path, but 300 also reduces prompt-window load.
    "PG_LIVE_MAX_EV_TO_GEN":  "300",

    "PG_MAX_COST_PER_RUN":    "10.00",

    # M-23 access-bypass feature flags (unchanged from V27)
    "PG_UNPAYWALL_ENABLED":   "1",
    "PG_CRAWL4AI_ENABLED":    "1",
    "PG_FIRECRAWL_ENABLED":   "0",
    "PG_TRAFILATURA_ENABLED": "1",

    # Scraper circuit breakers (unchanged from V27)
    "PG_CRAWL4AI_TIMEOUT":    "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD": "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":  "120",
    "PG_SCIHUB_ENABLED":      "0",

    # M-42d knob: HC T3 quota (unchanged from V27)
    "PG_M41D_HC_QUOTA":       "2",

    # M-43 knob: regulatory anchor cap (unchanged from V27)
    "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",

    # M-35 knob: primary-trial anchor cap (default 15; 11 configured
    # in clinical.yaml so cap is not hit, but set explicitly for
    # reproducibility)
    "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
}


def _apply_env() -> None:
    for key, val in LAUNCH_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V28 env]  {key} = {val}")
        else:
            print(f"[V28 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v28"])

    print("=" * 72)
    print(f"V28 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
