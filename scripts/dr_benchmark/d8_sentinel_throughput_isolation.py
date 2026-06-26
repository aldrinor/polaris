#!/usr/bin/env python3
"""I-wire-006 (#1320) — 4-role D8 Sentinel verification-SECTION isolation throughput harness.

Tests the FAITHFULNESS / 4-role D8 verification SECTION in ISOLATION (NOT the full pipeline),
driving the REAL transport (`openrouter_role_transport` + `sentinel_adapter.run_sentinel`) — no
mocks, so the measured s/claim is honest. Per the I-wire-006 design
(`docs/faithfulness_throughput_design_2026_06_26.md`).

Metrics, per arm:
  - throughput      : claims certified / minute (median + p99 s/claim), extrapolated whole-D8 wall
  - completeness    : % claims that get a REAL verdict (parsed_ok) vs force-close-degraded UNGROUNDED
  - faithfulness    : fabrication-catch — every known-fabricated claim MUST come back UNGROUNDED

Arms (config differences are ENV-driven, faithfulness DECISION logic FROZEN):
  - baseline : the current run config — minimax/minimax-m2, MAX reasoning, 300s sentinel deadline.
  - candidate: the same model + the always-ship/measurable levers — reasoning effort=medium
               (the proven xhigh-burns-budget->blank->fail-closed lever) + fastest-host routing +
               a tighter-but-safe (not 30-45s trap) sentinel deadline.

A model SWAP (Granite Guardian 3.3-8B) needs vLLM serving + operator lock sign-off; it is wired as
an optional arm via PG_SENTINEL_MODEL_SLUG override + a self-hosted base_url, but is NOT the default
candidate here (sign-off-blocked). The candidate measured here is the no-sign-off lever set.

Run ON THE VM only (loads no local model but issues live OpenRouter LLM calls):
    python scripts/dr_benchmark/d8_sentinel_throughput_isolation.py \
        --fixture /root/d8_fixture.json --arm baseline --out /root/d8_iso/baseline.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

# --- repo import path -------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402
from src.polaris_graph.roles.sentinel_adapter import run_sentinel  # noqa: E402
from src.polaris_graph.roles import openrouter_role_transport as _ort  # noqa: E402
from scripts.dr_benchmark.run_gate_b import build_gate_b_transport  # noqa: E402


def _configure_arm(arm: str) -> dict:
    """Set the ENV knobs that distinguish baseline vs candidate. Faithfulness logic untouched —
    every knob here is transport/routing/reasoning-budget only. Returns the effective config."""
    slug = os.environ.get("PG_SENTINEL_MODEL_SLUG", "minimax/minimax-m2")
    # Force the OpenRouter transport for both arms (the benchmark-stage transport).
    os.environ["PG_FOUR_ROLE_TRANSPORT"] = "openrouter"
    os.environ["BENCHMARK_VERIFIER_SENTINEL"] = slug
    if arm == "baseline":
        # Current run config: MAX reasoning (xhigh = the production default), generous 300s deadline.
        effort = "xhigh"
        os.environ["PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL"] = "300"
    elif arm == "candidate":
        # Proven lever: xhigh reasoning burns the token budget -> blank -> fail-closed
        # (feedback_mirror_blank_xhigh_effort_fix). medium returns content fast. NOT a faithfulness
        # relaxation (the blank-ladder already steps down). Plus a tighter-but-SAFE 120s deadline
        # (NOT the 30-45s mass-over-drop trap rejected by the design).
        effort = "medium"
        os.environ["PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL"] = "120"
    elif arm == "candidate_routing":
        # The DESIGN's actual candidate lever: faster ROUTING. Keep baseline reasoning (xhigh) +
        # the 300s floor (NOT the 30-45s trap), and DROP the measured-slow google-vertex from the
        # sentinel provider chain UP FRONT (novita-led) instead of discovering it slow via a per-call
        # deadline burn + reactive rotation. Pure routing/transport — faithfulness-neutral, no locked
        # model slug change, no operator sign-off. PG_PROVIDER_ROUTING_CONFIG repoints the loader.
        effort = "xhigh"
        os.environ["PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL"] = "300"
        os.environ["PG_PROVIDER_ROUTING_CONFIG"] = os.environ.get(
            "PG_PROVIDER_ROUTING_CONFIG",
            str(_REPO / "config/settings/openrouter_provider_routing_sentinel_no_vertex.yaml"),
        )
    else:
        raise SystemExit(f"unknown arm: {arm}")
    # CRITICAL: _REASONING_EFFORT + _TIMEOUT are IMPORT-TIME-frozen module globals; the env var alone
    # is a SILENT NO-OP (read at import, not per-call). Apply via the real setters so the lever FIRES.
    os.environ["PG_FOUR_ROLE_REASONING_EFFORT"] = effort
    _ort.set_four_role_reasoning_effort(effort)
    # Read back the EFFECTIVE sentinel provider chain (proof the routing lever fired).
    try:
        from src.polaris_graph.roles.provider_routing import role_provider_routing as _rpr
        _sentinel_route = _rpr("sentinel")
    except Exception:  # noqa: BLE001
        _sentinel_route = None
    return {
        "arm": arm,
        "sentinel_slug": slug,
        "reasoning_effort": _ort._REASONING_EFFORT,   # read back the LIVE module global (proof it fired)
        "sentinel_deadline_s": os.environ["PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL"],
        "transport": os.environ["PG_FOUR_ROLE_TRANSPORT"],
        "routing_config": os.environ.get("PG_PROVIDER_ROUTING_CONFIG", "<default>"),
        "sentinel_provider_order": (_sentinel_route or {}).get("order"),
    }


def _evidence(span: str) -> list[EvidenceDocument]:
    return [EvidenceDocument(doc_id="iso", text=span)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--arm", required=True, choices=["baseline", "candidate", "candidate_routing"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = all fixture rows")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("PG_FOUR_ROLE_CLAIM_WORKERS", "6")))
    ap.add_argument("--total-claims", type=int, default=1220, help="for whole-D8 wall extrapolation")
    args = ap.parse_args()

    cfg = _configure_arm(args.arm)
    rows = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]

    transport = build_gate_b_transport()
    slug = cfg["sentinel_slug"]
    # Zero the 429/503 telemetry so the snapshot reflects THIS arm only (the throttle discriminator —
    # the transport swallows 429s into backoff, so the counter, not a log grep, is where they land).
    _ort.reset_rate_limit_counter()

    import concurrent.futures as cf

    def _one(row: dict) -> dict:
        t = time.time()
        err = None
        try:
            result, _records = run_sentinel(
                transport, row["claim"], _evidence(row["span"]),
                model_slug=slug, mode="decomposition",
            )
            verdict = result.verdict.name  # GROUNDED | UNGROUNDED
            parsed_ok = bool(getattr(result, "parsed_ok", True))
        except Exception as exc:  # noqa: BLE001 — record, fail-closed
            verdict, parsed_ok, err = "UNGROUNDED", False, f"{type(exc).__name__}: {exc}"
        dt = time.time() - t
        return {
            "id": row["id"], "label": row["label"], "kind": row.get("kind"),
            "verdict": verdict, "parsed_ok": parsed_ok, "latency_s": round(dt, 2),
            "error": err,
        }

    results: list[dict] = []
    wall0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(_one, rows):
            results.append(r)
            tag = "REAL" if r["parsed_ok"] else "DEGRADED"
            print(f"  [{tag}] {r['id'][:24]:24} {r['label']:10} -> {r['verdict']:11} {r['latency_s']:6.1f}s"
                  + (f"  ERR {r['error'][:40]}" if r["error"] else ""), flush=True)
    wall = time.time() - wall0

    lats = [r["latency_s"] for r in results]
    real = [r for r in results if r["parsed_ok"]]
    fabs = [r for r in results if r["label"] == "fabricated"]
    fab_caught = [r for r in fabs if r["verdict"] == "UNGROUNDED"]
    grounded = [r for r in results if r["label"] == "grounded"]
    median_s = statistics.median(lats) if lats else 0.0
    p99_s = sorted(lats)[int(len(lats) * 0.99) - 1] if len(lats) >= 2 else (lats[0] if lats else 0.0)
    # Whole-D8 wall extrapolation at the configured worker count.
    extrap_min = (median_s * args.total_claims / max(args.workers, 1)) / 60.0
    claims_per_min = (len(results) / wall * 60.0) if wall else 0.0

    summary = {
        "arm": args.arm, "config": cfg, "n_claims": len(results), "workers": args.workers,
        "wall_s": round(wall, 1),
        "throughput": {
            "claims_per_min": round(claims_per_min, 2),
            "median_s_per_claim": round(median_s, 2),
            "p99_s_per_claim": round(p99_s, 2),
            "extrapolated_whole_D8_min_for_%d_claims" % args.total_claims: round(extrap_min, 1),
        },
        "completeness": {
            "pct_real_verdict": round(100.0 * len(real) / max(len(results), 1), 1),
            "n_real": len(real), "n_degraded": len(results) - len(real),
        },
        "faithfulness_catch": {
            "n_fabricated": len(fabs), "n_caught_ungrounded": len(fab_caught),
            "catch_rate": round(len(fab_caught) / max(len(fabs), 1), 4),
            # REAL catch = caught by a parsed decomposition (parsed_ok), NOT a trivial fail-close on a
            # force-closed/blank call. Only a REAL catch proves the DECOMPOSITION still flags it.
            "n_caught_via_real_decomposition": sum(
                1 for r in fabs if r["verdict"] == "UNGROUNDED" and r["parsed_ok"]
            ),
            "n_caught_via_failclose_only": sum(
                1 for r in fabs if r["verdict"] == "UNGROUNDED" and not r["parsed_ok"]
            ),
            "false_accepts": [r["id"] for r in fabs if r["verdict"] == "GROUNDED"],
            "n_grounded_overflag": sum(1 for r in grounded if r["verdict"] == "UNGROUNDED" and r["parsed_ok"]),
        },
        # The throttle discriminator: 429/503 hits the transport absorbed into backoff during THIS arm.
        "rate_limit_429_503": _ort.rate_limit_counter_snapshot(),
        # Per-claim latency in submission order — reveals the throttle ONSET (early-fast -> late-slow).
        "latency_series_s": lats,
        "rows": results,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n=== SUMMARY", args.arm, "===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
