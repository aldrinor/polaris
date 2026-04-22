"""V25 full-scale launcher — explicit, reproducible, auditable env config.

V25 = V24 code + M-41 bundle (Codex pass-2 READY 2026-04-21):
  M-41a: outline cap 5 → 6 when Mechanism+Regulatory both trigger
         (closes V24 Regulatory-displacement regression).
  M-41b: drop trial summary table rows with >2 dashes
         (closes V24 "3 rows, 2 mostly empty" table finding).
  M-41c: deterministic claim-frame post-check
         (converts probabilistic M-38 prompt rule to code-enforced).
  M-41d: evidence-selector T3 jurisdictional floor
         (unblocks M-37 HC work that was stranded by V24's missing
         Regulatory section).

FIRST V SWEEP UNDER AUTOLOOP V2 PROTOCOL. After completion:
  1. Claude output audit + Codex output audit (parallel)
  2. Cross-review with per-disagreement table
  3. Gate verdict → SHIPPABLE or iterate
  4. If iterate: fix plan + Codex plan review
  5. Re-launch under Codex-approved plan
  Full runbook: state/autoloop_v2_runbook.md

Usage:
    python scripts/run_full_scale_v25.py --out-root outputs/full_scale_v25
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# V25 CAPACITY KNOBS — set BEFORE importing the sweep module so env defaults
# read at import time pick up our values. Every override is annotated with
# its role so future readers know what's on.
# ---------------------------------------------------------------------------

_V25_ENV: dict[str, str] = {
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
    "PG_SCIHUB_ENABLED":      "1",
}


def _apply_env() -> None:
    """Export V25 env. Does NOT overwrite values already set by the user
    in the parent shell — so manual overrides remain possible. Does NOT
    overwrite .env-loaded values either; python-dotenv's load_dotenv()
    inside the sweep script uses its default override=False behavior.
    """
    for key, val in _V25_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V25 env]  {key} = {val}")
        else:
            print(f"[V25 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v25"])

    print("=" * 72)
    print(f"V25 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
