#!/usr/bin/env python3
"""I-wire-007 (#1321) — ADAPTIVE AIMD controller ISOLATION sweep (VM-only).

Proves the per-role AIMD concurrency controller (`adaptive_concurrency.py`, wired into
`openrouter_role_transport.complete()` for the sentinel role) on a LARGE claim set:
  - it RAMPS UP (probes +1 per clean window) from MIN toward the live provider ceiling,
  - BACKS OFF (halves) on a 429/503 or a force-close timeout,
  - SETTLES just under the discovered ceiling,
WITHOUT a 429 storm, with faithfulness UNCHANGED (every fabricated row still UNGROUNDED).

Telemetry-ONLY harness (no change to any gated src file): a background sampler thread snapshots the
LIVE controller's `.limit` / `.in_flight` every `--sample-s` seconds, reconstructing the AIMD
trajectory. Back-off events are inferred from limit DROPS in the series; 429/503 from the transport's
own `rate_limit_counter_snapshot()`; force-closes from per-claim `parsed_ok=False`.

Arms (set via env BEFORE importing the transport so the lazily-built controller reads them):
  - baseline  : PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY=0, static --workers (default 6). The control.
  - adaptive  : PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY=1, --workers >> sentinel MAX so the CONTROLLER, not
                the thread pool, is the binding constraint. Sentinel MAX from the shipped default (12)
                or raised via PG_FOUR_ROLE_ADAPTIVE_SENTINEL_MAX to force a DISCOVERED ceiling.

Run ON THE VM only (issues live OpenRouter sentinel POSTs; minimax-m2 is remote-only):
    python scripts/dr_benchmark/d8_adaptive_sweep.py --fixture /root/d8_large.json \
        --arm adaptive --workers 40 --out /root/d8_iso/adaptive_max32.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _set_arm_env(arm: str) -> None:
    """Set adaptive on/off BEFORE importing the transport (controller is lazily built on first
    acquire and reads these at construction). Faithfulness logic untouched — concurrency knobs only."""
    os.environ["PG_FOUR_ROLE_TRANSPORT"] = "openrouter"
    if arm == "baseline":
        os.environ["PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY"] = "0"
    elif arm == "adaptive":
        os.environ["PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY"] = "1"
    else:
        raise SystemExit(f"unknown arm: {arm}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--arm", required=True, choices=["baseline", "adaptive"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="0 = all fixture rows")
    ap.add_argument("--sample-s", type=float, default=1.0, help="controller poll interval (s)")
    ap.add_argument("--total-claims", type=int, default=1220)
    args = ap.parse_args()

    _set_arm_env(args.arm)

    # Import AFTER env is set so the lazily-built controller honors the arm knobs.
    from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: PLC0415
    from src.polaris_graph.roles.sentinel_adapter import run_sentinel  # noqa: PLC0415
    from src.polaris_graph.roles import openrouter_role_transport as _ort  # noqa: PLC0415
    from scripts.dr_benchmark.run_gate_b import build_gate_b_transport  # noqa: PLC0415

    slug = os.environ.get("PG_SENTINEL_MODEL_SLUG", "minimax/minimax-m2")
    os.environ["BENCHMARK_VERIFIER_SENTINEL"] = slug
    # Keep the production-safe sentinel deadline (NOT the 30-45s over-drop trap).
    os.environ.setdefault("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", "300")

    rows = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]

    transport = build_gate_b_transport()
    _ort.reset_rate_limit_counter()

    # --- controller-trajectory sampler (telemetry only; reads .limit/.in_flight) ------------------
    series: list[dict] = []
    stop = threading.Event()
    t0 = time.time()

    def _sample_controller():
        return _ort._adaptive_controller("sentinel") if args.arm == "adaptive" else None

    def _sampler():
        while not stop.is_set():
            c = _sample_controller()
            if c is not None:
                try:
                    series.append({
                        "t": round(time.time() - t0, 2),
                        "limit": c.limit,
                        "in_flight": c.in_flight,
                    })
                except Exception:  # noqa: BLE001
                    pass
            stop.wait(args.sample_s)

    sampler = threading.Thread(target=_sampler, daemon=True)
    sampler.start()

    def _evidence(span: str):
        return [EvidenceDocument(doc_id="iso", text=span)]

    def _one(row: dict) -> dict:
        t = time.time()
        err = None
        try:
            result, _recs = run_sentinel(
                transport, row["claim"], _evidence(row["span"]),
                model_slug=slug, mode="decomposition",
            )
            verdict = result.verdict.name
            parsed_ok = bool(getattr(result, "parsed_ok", True))
        except Exception as exc:  # noqa: BLE001
            verdict, parsed_ok, err = "UNGROUNDED", False, f"{type(exc).__name__}: {exc}"
        dt = time.time() - t
        return {
            "id": row["id"], "label": row["label"], "kind": row.get("kind"),
            "verdict": verdict, "parsed_ok": parsed_ok, "latency_s": round(dt, 2), "error": err,
        }

    results: list[dict] = []
    wall0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(_one, rows):
            results.append(r)
            tag = "REAL" if r["parsed_ok"] else "DEGRADED"
            c = _sample_controller()
            lim = c.limit if c is not None else args.workers
            print(f"  [{tag}] lim={lim:2} {r['id'][:28]:28} {r['label']:10} -> {r['verdict']:11} "
                  f"{r['latency_s']:6.1f}s" + (f"  ERR {r['error'][:40]}" if r["error"] else ""),
                  flush=True)
    wall = time.time() - wall0
    stop.set()
    sampler.join(timeout=3)

    # --- AIMD trajectory analysis from the limit series -------------------------------------------
    limits = [s["limit"] for s in series]
    backoff_events = sum(1 for a, b in zip(limits, limits[1:]) if b < a)  # limit DROPs == back-offs
    ramp_events = sum(1 for a, b in zip(limits, limits[1:]) if b > a)     # limit RISES == probe-ups
    settled_limit = statistics.mode(limits[len(limits) // 2:]) if len(limits) >= 4 else (limits[-1] if limits else args.workers)
    peak_limit = max(limits) if limits else args.workers
    start_limit = limits[0] if limits else args.workers

    lats = [r["latency_s"] for r in results]
    real = [r for r in results if r["parsed_ok"]]
    fabs = [r for r in results if r["label"] == "fabricated"]
    fab_caught = [r for r in fabs if r["verdict"] == "UNGROUNDED"]
    grounded = [r for r in results if r["label"] == "grounded"]
    median_s = statistics.median(lats) if lats else 0.0
    p99_s = sorted(lats)[int(len(lats) * 0.99) - 1] if len(lats) >= 2 else (lats[0] if lats else 0.0)
    claims_per_min = (len(results) / wall * 60.0) if wall else 0.0
    # whole-D8 wall extrapolation: real throughput-based (claims/min), not the static-worker formula.
    extrap_min = (args.total_claims / claims_per_min) if claims_per_min else 0.0

    rl = _ort.rate_limit_counter_snapshot()

    summary = {
        "arm": args.arm, "n_claims": len(results), "workers": args.workers,
        "wall_s": round(wall, 1),
        "adaptive_controller": {
            "enabled": args.arm == "adaptive",
            "sentinel_min_max": [
                int(os.getenv("PG_FOUR_ROLE_ADAPTIVE_SENTINEL_MIN", "4")),
                int(os.getenv("PG_FOUR_ROLE_ADAPTIVE_SENTINEL_MAX", "12")),
            ],
            "start_limit": start_limit, "peak_limit": peak_limit, "settled_limit": settled_limit,
            "ramp_events": ramp_events, "backoff_events": backoff_events,
            "n_samples": len(series),
        },
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
            "n_caught_via_real_decomposition": sum(
                1 for r in fabs if r["verdict"] == "UNGROUNDED" and r["parsed_ok"]),
            "n_caught_via_failclose_only": sum(
                1 for r in fabs if r["verdict"] == "UNGROUNDED" and not r["parsed_ok"]),
            "false_accepts": [r["id"] for r in fabs if r["verdict"] == "GROUNDED"],
            "n_grounded_overflag": sum(
                1 for r in grounded if r["verdict"] == "UNGROUNDED" and r["parsed_ok"]),
        },
        "rate_limit_429_503": rl,
        "limit_series": series,
        "latency_series_s": lats,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n=== SUMMARY", args.arm, "===")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("limit_series", "latency_series_s")}, indent=2))


if __name__ == "__main__":
    main()
