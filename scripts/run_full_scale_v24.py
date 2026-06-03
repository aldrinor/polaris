"""V24 full-scale launcher — explicit, reproducible, auditable env config.

V24 = V23 launcher knobs + the five V24 code fixes Codex-approved
2026-04-21 for Codex DR pass-11 gaps:
  M-35: SURPASS-1..6 / SURMOUNT-1..4 primary-paper retrieval anchors
        (closes Citations LOSE_BOTH).
  M-36: Trial Summary markdown table post-synthesis stage
        (closes Structural depth LOSE_BOTH).
  M-37: Health Canada pdf.hres.ca regulatory-domain tier fix +
        jurisdictional coverage prompt rule (lifts Regulatory /
        Jurisdictional BEAT_ONE → BEAT_BOTH).
  M-38: Claim-frame hard constraint — 3-of-7 frame elements or
        drop short-name attribution (closes Claim frames LOSE_BOTH).
  M-40: Mechanism-section outline rule + title visibility to
        outline LLM (closes Narrative depth LOSE_BOTH).

No retrieval-scale changes vs V23. Expected: ~370-400 sources with
+11 SURPASS/SURMOUNT primary papers surfacing via anchor queries.

Usage:
    python scripts/run_full_scale_v24.py --out-root outputs/full_scale_v24
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# V24 CAPACITY KNOBS — set BEFORE importing the sweep module so env defaults
# read at import time pick up our values. Every override is annotated with
# its role so future readers know what's on.
# ---------------------------------------------------------------------------

_V24_ENV: dict[str, str] = {
    # Sweep-level retrieval knobs (scripts/run_honest_sweep_r3.py:536-538)
    "PG_SWEEP_MAX_SERPER":    "50",     # amplified queries fanned to Serper
    "PG_SWEEP_MAX_S2":        "50",     # amplified queries to Semantic Scholar
    "PG_SWEEP_FETCH_CAP":     "500",    # max URLs classified + fetched per query

    # Generator evidence pool cap
    # (scripts/run_honest_sweep_r3.py:902 -> max_rows in evidence_selector)
    "PG_LIVE_MAX_EV_TO_GEN":  "600",

    # Budget cap (src/polaris_graph/... PG_MAX_COST_PER_RUN)
    "PG_MAX_COST_PER_RUN":    "10.00",

    # M-23 access-bypass feature flags
    "PG_UNPAYWALL_ENABLED":   "1",      # M-23a Unpaywall step 0 (default on)
    "PG_CRAWL4AI_ENABLED":    "1",      # concurrent Crawl4AI primary backend
    "PG_FIRECRAWL_ENABLED":   "0",      # per user directive: costs money
    "PG_TRAFILATURA_ENABLED": "1",      # concurrent Trafilatura backend

    # Scraper circuit breakers (keep defaults tolerant)
    "PG_CRAWL4AI_TIMEOUT":    "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD": "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":  "120",

    # Sci-Hub DISABLED by default (legal/provenance, I-faith-002); CORE is the OA full-text source
    "PG_SCIHUB_ENABLED":      "0",
}


def _apply_env() -> None:
    """Export V24 env. Does NOT overwrite values already set by the user
    in the parent shell — so manual overrides remain possible. Does NOT
    overwrite .env-loaded values either; python-dotenv's load_dotenv()
    inside the sweep script uses its default override=False behavior.
    """
    for key, val in _V24_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V24 env]  {key} = {val}")
        else:
            print(f"[V24 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v24"])

    print("=" * 72)
    print(f"V24 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
