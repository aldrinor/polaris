"""V23 full-scale launcher — explicit, reproducible, auditable env config.

V23 = V22 launcher knobs + M-33 section_max_tokens fix (1200→2400)
landed in scripts/run_honest_sweep_r3.py. No retrieval-side changes
vs V22. Expected retrieval scale: ~362 sources, ~333 evidence_rows
(matches V22's pre_filter=362, fetched=344).

Per advisor feedback 2026-04-19 (blocker 2): previous V4-V9 runs were
launched with ad-hoc env exports at the call site, so the exact env
coverage was not reproducible from the repo. This wrapper makes every
capacity knob and feature flag explicit and version-controlled.

Usage:
    python scripts/run_full_scale_v23.py --out-root outputs/full_scale_v23
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# V23 CAPACITY KNOBS — set BEFORE importing the sweep module so env defaults
# read at import time pick up our values. Every override is annotated with
# its role so future readers know what's on.
# ---------------------------------------------------------------------------

_V23_ENV: dict[str, str] = {
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

    # Sci-Hub last-resort (kept on for unreachable paywalled DOIs)
    "PG_SCIHUB_ENABLED":      "0",
}


def _apply_env() -> None:
    """Export V23 env. Does NOT overwrite values already set by the user
    in the parent shell — so manual overrides remain possible. Does NOT
    overwrite .env-loaded values either; python-dotenv's load_dotenv()
    inside the sweep script uses its default override=False behavior.
    """
    for key, val in _V23_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V23 env]  {key} = {val}")
        else:
            print(f"[V23 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v23"])

    print("=" * 72)
    print(f"V23 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
