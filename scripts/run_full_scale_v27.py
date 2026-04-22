"""V27 full-scale launcher — V26 rerun with M-43 anchor cap fix.

V27 = V26 code + M-43 (regulatory_anchors cap 10 → 12).

V26 outcome (2026-04-22 03:44→05:38, 113.7 min):
  - manifest.status=partial_qwen_advisory, release_allowed=False
  - Biblio 48 (up from V25=40), contradictions 15 (same as V25)
  - HC=3 (M-42d target MET, up from V25=1)
  - Report 3527 words (up from V25=1455, +142%)
  - **REGRESSION: NICE=0** (V25=4). Caught by preservation test suite.

V26 regression root cause (caught by preservation suite, fixed as M-43):
  Adding M-42d's hpfb-dgpsa.ca anchor pushed clinical.yaml's
  `regulatory_anchors` list to 11 entries. `PG_SWEEP_MAX_REGULATORY_ANCHORS`
  default cap = 10 silently truncated the 11th entry (nice.org.uk),
  killing NICE retrieval end-to-end (0 NICE URLs in V26 corpus).

M-43 fix (commit pending):
  - `_DEFAULT_MAX_ANCHORS` raised 10 → 12 in regulatory_expander.py
  - V27 launcher explicitly sets `PG_SWEEP_MAX_REGULATORY_ANCHORS=12`
    so the fix is visible in the sweep config
  - Regression test: `test_m43_anchor_cap.py` asserts all 11
    clinical.yaml anchors (incl. nice.org.uk) emit queries

Codex M-43 verdict: READY required before V27 launch.

V27 success criteria (V25 baseline preservation + V26 improvements):
  - Preserve: FDA>=7, EMA>=3, NICE>=4 (M-43 fix), biblio>=40,
    contradictions>=10, T2>=3
  - M-42d improvement: HC>=2 (V26 already achieved 3)
  - Claim frames + Structural depth LOSE_BOTH → BEAT_ONE/BEAT_BOTH

Usage:
    python scripts/run_full_scale_v27.py --out-root outputs/full_scale_v27
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_V27_ENV: dict[str, str] = {
    # Sweep-level retrieval knobs
    "PG_SWEEP_MAX_SERPER":    "50",
    "PG_SWEEP_MAX_S2":        "50",
    "PG_SWEEP_FETCH_CAP":     "500",
    "PG_LIVE_MAX_EV_TO_GEN":  "600",
    "PG_MAX_COST_PER_RUN":    "10.00",

    # M-23 access-bypass feature flags
    "PG_UNPAYWALL_ENABLED":   "1",
    "PG_CRAWL4AI_ENABLED":    "1",
    "PG_FIRECRAWL_ENABLED":   "0",
    "PG_TRAFILATURA_ENABLED": "1",

    # Scraper circuit breakers
    "PG_CRAWL4AI_TIMEOUT":    "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD": "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":  "120",
    "PG_SCIHUB_ENABLED":      "1",

    # M-42d knob: HC T3 quota
    "PG_M41D_HC_QUOTA":       "2",

    # M-43 knob: regulatory anchor cap. clinical.yaml has 11 anchors;
    # V26 default cap=10 truncated nice.org.uk → NICE=0 regression.
    # 12 accommodates current + 1 future. Code default is now 12 too;
    # this env var makes the choice explicit in the sweep config.
    "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",
}


def _apply_env() -> None:
    for key, val in _V27_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V27 env]  {key} = {val}")
        else:
            print(f"[V27 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v27"])

    print("=" * 72)
    print(f"V27 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
