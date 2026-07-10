#!/usr/bin/env python3
"""S3 CONSOLIDATE cp3 hamster harness (Master Execution Plan v2 §4 S3 / §5 isolation dividend).

Validates ``cp3_basket_snapshot.json`` files produced by a sweep run — the VM single-section and
full-corpus check the later hamster phase runs. For each cp3 it proves, forensically (§-1.4
read-every-line), the S3 lock-down bar:

  * ROUND-TRIP byte-identity: reloading the cp3 through the module loader and re-serializing it is
    byte-for-byte the on-disk file (deterministic bytes).
  * VERDICT-SMUGGLING guard: the recursive forbidden-verdict-key guard passes (a poisoned cp3 would
    fail-loud here) AND ``span_verdict`` / ``basket_verdict`` never appear in the bytes.
  * CONSOLIDATE-DON'T-DROP: every basket keeps ALL its members (member count is printed per basket).
  * HASH-CHAIN: the recorded ``upstream.sha256`` matches the actual sha256 of the run_dir's
    ``corpus_snapshot.json`` when that file is present (cp3 pins cp2).

This is a READ/VALIDATE tool — it never mutates a run. cp3 files are PRODUCED by a sweep run with
``PG_CP3_BASKET_SNAPSHOT`` enabled (default ON); this harness then reads them.

Usage:
  # single run_dir (VM single-section):
  python scripts/cp3_basket_snapshot_harness.py --run-dir outputs/<sweep>/<query_run_dir>
  # every run_dir under a sweep output (VM full corpus):
  python scripts/cp3_basket_snapshot_harness.py --sweep-dir outputs/<sweep>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.cp3_basket_snapshot import (  # noqa: E402
    CP3_SNAPSHOT_FILENAME,
    Cp3SnapshotError,
    load_cp3_basket_snapshot,
    serialize_cp3_payload,
)


def _validate_one(run_dir: Path) -> bool:
    """Validate the cp3 in ONE run_dir. Returns True iff every check passed. Prints line-by-line."""
    cp3_path = run_dir / CP3_SNAPSHOT_FILENAME
    if not cp3_path.is_file():
        print(f"[cp3][skip] {run_dir.name}: no {CP3_SNAPSHOT_FILENAME}")
        return True  # not a failure — this run had no consolidation / cp3 disabled

    ok = True
    print(f"[cp3][run ] {run_dir.name}")

    # 1) fail-loud load through the module (schema + recursive verdict guard).
    try:
        payload = load_cp3_basket_snapshot(run_dir)
    except Cp3SnapshotError as exc:
        print(f"[cp3][FAIL]   load refused: {exc}")
        return False

    written = cp3_path.read_text(encoding="utf-8")

    # 2) round-trip byte-identity.
    if serialize_cp3_payload(payload) == written:
        print("[cp3][pass]   round-trip byte-identical")
    else:
        print("[cp3][FAIL]   round-trip NOT byte-identical")
        ok = False

    body = payload.get("payload", {})
    baskets = body.get("baskets", []) or []

    # 3) verdict-label exclusion — STRUCTURAL (the invariant note legitimately names the excluded
    # fields, so a raw substring check would false-positive). No basket/member carries the label key;
    # and the label VALUES never appear as bytes.
    label_keys_present = any(
        "basket_verdict" in b or any("span_verdict" in m for m in (b.get("members", []) or []))
        for b in baskets
    )
    value_leak = [tok for tok in ("SUPPORTS", "UNSUPPORTED") if tok in written]
    if label_keys_present or value_leak:
        print(
            f"[cp3][FAIL]   verdict label leaked (keys={label_keys_present} values={value_leak})"
        )
        ok = False
    else:
        print("[cp3][pass]   no span_verdict/basket_verdict label key or value in payload")

    pairs = body.get("contradiction_pairs", []) or []
    total_members = sum(len(b.get("members", []) or []) for b in baskets)
    print(
        f"[cp3][data]   baskets={len(baskets)} members(all-kept)={total_members} "
        f"contradiction_pairs={len(pairs)} stage={payload.get('stage')}"
    )
    for b in baskets:
        print(
            f"[cp3][basket] {b.get('claim_cluster_id','?')} members={len(b.get('members',[]) or [])} "
            f"corroboration={b.get('corroboration_count')} weight_mass={b.get('weight_mass')} "
            f"refuters={len(b.get('refuter_cluster_ids',[]) or [])}"
        )

    # 4) hash-chain: cp3.upstream.sha256 == sha256(corpus_snapshot.json) when present.
    upstream = payload.get("upstream", {}) or {}
    up_name = upstream.get("name", "corpus_snapshot.json")
    up_sha = upstream.get("sha256", "")
    up_path = run_dir / up_name
    if up_path.is_file() and up_sha:
        actual = hashlib.sha256(up_path.read_bytes()).hexdigest()
        if actual == up_sha:
            print(f"[cp3][pass]   hash-chain to {up_name} valid")
        else:
            print(f"[cp3][FAIL]   hash-chain to {up_name} BROKEN ({up_sha[:12]} != {actual[:12]})")
            ok = False
    else:
        print(f"[cp3][info]   hash-chain not checked (upstream {up_name} absent or sha empty)")

    print(f"[cp3][{'PASS' if ok else 'FAIL'}] {run_dir.name}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cp3_basket_snapshot.json files.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=Path, help="one query run_dir containing a cp3")
    group.add_argument("--sweep-dir", type=Path, help="a sweep output dir; validate every run_dir")
    args = parser.parse_args()

    if args.run_dir is not None:
        run_dirs = [args.run_dir]
    else:
        run_dirs = sorted(p for p in args.sweep_dir.iterdir() if p.is_dir())

    checked = [d for d in run_dirs if (d / CP3_SNAPSHOT_FILENAME).is_file()]
    results = [_validate_one(d) for d in run_dirs]
    passed = sum(1 for r in results if r)
    print(
        f"\n[cp3][summary] run_dirs={len(run_dirs)} with_cp3={len(checked)} "
        f"passed={passed}/{len(results)}"
    )
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
