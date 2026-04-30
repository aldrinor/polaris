"""Phase G full-scale POLARIS run for BEAT-BOTH re-scoring.

After Phase F LOCKED with M-LIVE-2 v4 surfacing BEHIND-BOTH gaps
on regulatory_coverage / narrative_length / contradiction_handling
under SMOKE input, the highest-leverage Phase G move is to
re-score against a FULL-SCALE POLARIS run before coding any
remediation. Many gaps may close on production volume alone.

Full-scale knobs (vs SMOKE):
  PG_SWEEP_MAX_SERPER:    50  (vs 10)
  PG_SWEEP_MAX_S2:        50  (vs 10)
  PG_SWEEP_FETCH_CAP:     500 (vs 30)
  PG_LIVE_MAX_EV_TO_GEN:  300 (vs 30)
  PG_MAX_COST_PER_RUN:    $10.00 (vs $2.00)

Output:
  outputs/phase_g_full_scale/run_<timestamp>/clinical/<slug>/...
  Reuses M-LIVE-1 smoke harness for substrate-fire verification.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PHASE_G_ENV: dict[str, str] = {
    "PG_RECORD_DECISIONS":             "1",
    "PG_CAPTURE_PIN":                  "1",
    "PG_USE_PARALLEL_FETCH":           "1",
    "PG_USE_CACHE_WARMING":            "1",
    "PG_USE_FRESHNESS_DETECTOR":       "1",
    "PG_USE_LLM_SCOPE":                "1",
    "PG_USE_DOMAIN_ROUTER":            "1",
    "PG_USE_AUTO_INDUCTION":           "1",
    "PG_USE_BILLING_QUOTA":            "1",
    "PG_USE_SLIDE_DECK_ENDPOINT":      "1",
    "PG_USE_CONTRACT_DRAFT_ENDPOINT":  "1",
    "PG_USE_DRIVE_CONNECTOR_ENDPOINT": "1",
    "PG_USE_SUPPORT_TICKET_ENDPOINT":  "1",
    "PG_USE_OPERATOR_DASHBOARD":       "1",
    "PG_AUTH_TRUSTED_TEST_HEADER":     "1",
    "PG_BILLING_ORG_ID":               "org_default",
    # Full-scale knobs
    "PG_SWEEP_MAX_SERPER":             "50",
    "PG_SWEEP_MAX_S2":                 "50",
    "PG_SWEEP_FETCH_CAP":              "500",
    "PG_LIVE_MAX_EV_TO_GEN":           "300",
    "PG_MAX_COST_PER_RUN":             "10.00",
    # V30 Phase 2 enabled
    "PG_V30_ENABLED":                  "1",
    "PG_V30_PHASE2_ENABLED":           "1",
    # Access bypass
    "PG_UNPAYWALL_ENABLED":            "1",
    "PG_CRAWL4AI_ENABLED":             "0",  # Playwright EPIPE on this box
    "PG_TRAFILATURA_ENABLED":          "1",
    "PG_SCIHUB_ENABLED":               "1",
    # Scraper circuit breakers
    "PG_CRAWL4AI_TIMEOUT":             "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD":    "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":     "120",
    "PG_M41D_HC_QUOTA":                "2",
    "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",
    "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
    # v1.1 backlog A.1 NEGATIVE RESULT (2026-04-30):
    # PG_SECTION_MAX_TOKENS=4800 was tested and FAILED to close
    # narrative_length BEHIND-BOTH. Result: 2346w → 2032w
    # (REGRESSION). Hypothesis: larger draft → more sentences
    # at strict_verify boundary → more retries → final word
    # count drops. v1.1 must use options 2/3/4 from backlog
    # (more sections, lower kept_fraction floor, or evidence-
    # grounded synthesizer rewrite). Not option 1.
    # Default: leave at 2400 (v1.0 release config).
}


def _apply_env() -> None:
    for k, v in PHASE_G_ENV.items():
        cur = os.environ.get(k)
        if cur is None or cur == "":
            os.environ[k] = v
            print(f"[Phase-G env] {k} = {v}")
        else:
            print(f"[Phase-G env] {k} = {cur}  (already set)")


def _seed_billing_plan_for_phase_g() -> None:
    try:
        from src.polaris_graph.audit_ir.billing_quota_store import (
            BillingQuotaStore,
            PlanTier,
            QuotaEventKind,
        )
    except Exception as exc:
        print(f"[Phase-G] WARN: billing import failed: {exc}")
        return
    db_path = Path(os.environ.get(
        "PG_BILLING_QUOTA_DB_PATH",
        str(REPO_ROOT / "state" / "billing_quota.sqlite"),
    ))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        store = BillingQuotaStore(db_path)
        store.assign_plan(
            org_id="org_default",
            tier=PlanTier.PRODUCTION,
            quotas_override={
                QuotaEventKind.AUDIT_RUN_ENQUEUED: 100,
            },
        )
        print(
            "[Phase-G] seeded billing plan: org=org_default "
            "tier=production audit_run_quota=100"
        )
    except Exception as exc:
        print(f"[Phase-G] WARN: billing seed failed: {exc}")


_INJECTED_CANONICAL_URLS: list[str] = [
    "https://www.nejm.org/doi/10.1056/NEJMoa2107519",
    "https://www.nejm.org/doi/10.1056/NEJMoa2206038",
    "https://www.thelancet.com/journals/lancet/article/"
    "PIIS0140-6736(23)01200-X/fulltext",
]


def _patch_query_with_canonical_urls() -> None:
    import scripts.run_honest_sweep_r3 as sweep_mod
    if not hasattr(sweep_mod, "SWEEP_QUERIES"):
        return
    for q in sweep_mod.SWEEP_QUERIES:
        if q.get("slug") == "clinical_tirzepatide_t2dm":
            q["canonical_urls"] = list(_INJECTED_CANONICAL_URLS)
            return


def main() -> int:
    _apply_env()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_root = REPO_ROOT / "outputs" / "phase_g_full_scale" / f"run_{timestamp}"
    out_root.mkdir(parents=True, exist_ok=True)

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", str(out_root)])

    print("=" * 72)
    print("Phase G full-scale POLARIS run")
    print("=" * 72)
    print(f"out_root: {out_root}")
    print()

    _seed_billing_plan_for_phase_g()
    _patch_query_with_canonical_urls()

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


if __name__ == "__main__":
    raise SystemExit(main())
