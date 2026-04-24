"""V30 Phase-2 full-scale launcher.

V30 Phase-2 = V29 code + Report Contract Architecture end-to-end:
  - M-54 Report Contract schema (loaded from scope template)
  - M-55 Frame compiler
  - M-56 Deterministic live fetch (DOI/PMID/Unpaywall/OA)
  - M-57 Contract outline compiler (section_order + slot ordering)
  - M-58 Slot-bound generator prose (`Field: value [id].` body)
  - M-59 Slot validator (per-entity, per-slot verdicts)
  - M-60 Frame coverage manifest + methods disclosure
  - M-61 Human/licensed gap completion merge
  - M-63 Contract SECTION-level dispatch (THIS CYCLE): contract
         sections run through run_contract_section producing
         legacy-compatible SectionResult (headings + [N] citations
         + populated biblio_slice); M-44/M-50 gracefully skip
         contract-anchored trials.

V30 Phase-1 outcome (2026-04-23 live run):
  - 8 min / $0.0016 / full audit trail
  - SURPASS-CVOT correctly flagged as FRAME_GAP_UNRECOVERABLE
  - Phase-1 emits retrieval-coverage only (deliberately narrow);
    Phase-2 emits report-coverage via M-58 prose.

Target for Phase-2 full-scale sweep: BEAT-BOTH ChatGPT DR +
Gemini DR on the 7 strategic dimensions. V28/V29 ceiling was
3 BB + 0 BO + 4 LB.

Usage:
    python scripts/run_full_scale_v30_phase2.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_V30_PHASE2_ENV: dict[str, str] = {
    # V30 gating: Phase-1 + Phase-2 both ACTIVE.
    "PG_V30_ENABLED":          "1",
    "PG_V30_PHASE2_ENABLED":   "1",

    # Sweep-level retrieval knobs (V29 baseline)
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
    "PG_SCIHUB_ENABLED":      "1",

    # M-42d: HC T3 quota
    "PG_M41D_HC_QUOTA":       "2",

    # M-43: regulatory anchor cap
    "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",

    # M-35: primary-trial anchor cap
    "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
}


def _apply_env() -> None:
    for key, val in _V30_PHASE2_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V30-P2 env]  {key} = {val}")
        else:
            print(
                f"[V30-P2 env]  {key} = {existing}  "
                "(already set, not overriding)"
            )


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v30_phase2"])

    print("=" * 72)
    print(f"V30 Phase-2 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
