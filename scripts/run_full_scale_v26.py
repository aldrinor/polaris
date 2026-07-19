"""V26 full-scale launcher — explicit, reproducible, auditable env config.

V26 = V25 code + M-42 bundle (Codex pass-2 audit verdicts 2026-04-22):
  M-42e: named-trial primary-paper T1 floor (cap 6, quota-trim guard).
  M-42a: anaphoric + group-reference claim-frame prompt tightening.
  M-42b: direct_quote-only trial summary table + timeline builder
         (strict direct_quote OR refetch OR skip contract; no statement
         fallback; LLM fallback receives primary-trial direct_quotes
         only).
  M-42c: mechanism evidence T1+T2 floor (reserve up to 3 slots when
         pool has >=4 mechanism-rich rows) + conditional section prompt
         target (20-35 / 15-20 / 10-15 based on mech ev_id count).
  M-42d: Health Canada T3 quota expansion (1 → 2 slots) with
         FDA/EMA/NICE preservation guard; hpfb-dgpsa.ca anchor added.

Codex verdicts across the M-42 bundle:
  M-42e: READY pass-3 (post-hoc detection + cap-trim telemetry fixes).
  M-42a+b: READY pass-2 (statement fallback removed; LLM fallback
           receives primary-trial direct_quotes; year-from-refetched
           check added).
  M-42c: CONDITIONAL (no blockers; 4 Medium follow-ups tracked as task
         #31 for future tightening).
  M-42d: CONDITIONAL pass-1 + pass-2 fixes applied (telemetry reserved
         semantic; test short-circuit removal).

V26 success criteria (per fix_plan.md):
  - Close Claim frames LOSE_BOTH → BEAT_ONE or BEAT_BOTH
  - Close Structural depth LOSE_BOTH → BEAT_ONE or BEAT_BOTH
  - Preserve V25 baselines: FDA>=7, EMA>=3, NICE>=4, biblio>=40,
    contradictions>=10; improve HC to >=2 (M-42d target).

Autonomous launch authorized per user directive 2026-04-21:
  "Claude launches the next V{N} sweep WITHOUT asking for user
   approval as long as (a) code audit is Codex READY, (b) prior
   V{N-1} did not produce SHIPPABLE, and (c) no halt condition is
   triggered."

Usage:
    python scripts/run_full_scale_v26.py --out-root outputs/full_scale_v26
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# V26 CAPACITY KNOBS — same baseline as V25 with the M-42d HC quota knob
# explicitly at its default to make the behavior auditable.
# ---------------------------------------------------------------------------

LAUNCH_ENV: dict[str, str] = {
    # Sweep-level retrieval knobs (scripts/run_honest_sweep_r3.py:536-538)
    "PG_SWEEP_MAX_SERPER":    "50",     # amplified queries fanned to Serper
    "PG_SWEEP_MAX_S2":        "50",     # amplified queries to Semantic Scholar
    "PG_SWEEP_FETCH_CAP":     "500",    # max URLs classified + fetched per query

    # Generator evidence pool cap
    # (scripts/run_honest_sweep_r3.py:902 -> max_rows in evidence_selector)
    "PG_LIVE_MAX_EV_TO_GEN":  "600",

    # Budget cap (src/polaris_graph/... PG_MAX_COST_PER_RUN)
    "PG_MAX_COST_PER_RUN":    "10.00",

    # M-23 access-bypass feature flags (unchanged from V25)
    "PG_UNPAYWALL_ENABLED":   "1",
    "PG_CRAWL4AI_ENABLED":    "1",
    "PG_FIRECRAWL_ENABLED":   "0",      # per user directive: costs money
    "PG_TRAFILATURA_ENABLED": "1",

    # Scraper circuit breakers (unchanged from V25)
    "PG_CRAWL4AI_TIMEOUT":    "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD": "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":  "120",

    # Sci-Hub DISABLED by default (legal/provenance, I-faith-002); CORE is the OA full-text source
    "PG_SCIHUB_ENABLED":      "0",

    # M-42d knob: HC T3 quota. 2 = default (new in V26). 1 = legacy
    # M-41d behavior. Override via shell env to experiment.
    "PG_M41D_HC_QUOTA":       "2",
}


def _apply_env() -> None:
    """Export V26 env. Does NOT overwrite values already set by the user
    in the parent shell — so manual overrides remain possible. Does NOT
    overwrite .env-loaded values either; python-dotenv's load_dotenv()
    inside the sweep script uses its default override=False behavior.
    """
    for key, val in LAUNCH_ENV.items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[V26 env]  {key} = {val}")
        else:
            print(f"[V26 env]  {key} = {existing}  (already set, not overriding)")


def main() -> int:
    _apply_env()

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", "outputs/full_scale_v26"])

    print("=" * 72)
    print(f"V26 launch with argv: {sys.argv}")
    print("=" * 72)

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
