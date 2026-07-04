#!/usr/bin/env python3
"""I-wire-007 (#1321) — build a LARGER (~150-200 claim) D8 isolation fixture so the AIMD adaptive
concurrency controller has room to RAMP (probe up from MIN over many clean windows).

Source: the real run-derived `d8_fixture_drb72.json` (65 rows: 50 grounded + 15 fabricated). We
REPLICATE it `--reps` times with a per-replica id suffix so every replica keeps ALL fabricated rows
(the 0-false-accept faithfulness gate stays meaningful at scale) and every (claim, span) pair still
issues a REAL OpenRouter POST (the transport has NO response cache — verified — so duplicates do not
short-circuit; they exercise the live provider ceiling honestly).

Faithfulness-neutral: this only scales the WORKLOAD count. No claim text is altered; labels/kinds are
preserved verbatim. Used by `d8_adaptive_sweep.py` for the controller ramp/back-off/settle measurement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path(__file__).resolve().parent / "d8_fixture_drb72.json"))
    ap.add_argument("--reps", type=int, default=3, help="replica count (65*reps total rows)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    base = json.loads(Path(args.src).read_text(encoding="utf-8"))
    out: list[dict] = []
    for rep in range(args.reps):
        for row in base:
            r = dict(row)
            r["id"] = f"{row['id']}__r{rep}"
            out.append(r)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_fab = sum(1 for r in out if r["label"] == "fabricated")
    print(f"wrote {len(out)} rows ({n_fab} fabricated, {len(out) - n_fab} grounded) -> {args.out}")


if __name__ == "__main__":
    main()
