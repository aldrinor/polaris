"""Vast.ai read-only pricing query for POLARIS v6 Phase 0 Task 0.3.

NO COST: this script ONLY queries instance availability and price; it does
NOT provision any instance. Use this to populate the Path A/B/C decision
matrix for Task 0.6.

Usage:
    export VASTAI_API_KEY=...
    python scripts/v6/vastai_query_pricing.py --gpus h100 --num-gpus 4

Outputs JSON with the cheapest matching instances (no spend).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

VASTAI_BASE = "https://console.vast.ai/api/v0"


def search_offers(*, gpu_name: str, num_gpus: int, max_price_per_hour: float) -> dict[str, Any]:
    api_key = os.environ.get("VASTAI_API_KEY")
    if not api_key:
        raise SystemExit("ERROR: VASTAI_API_KEY env var not set.")

    query = {
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "gpu_name": {"eq": gpu_name.upper()},
        "num_gpus": {"eq": num_gpus},
        "dph_total": {"lte": max_price_per_hour},
        "geolocation": {"in": ["US", "CA"]},
    }
    params = {"q": json.dumps(query), "order": "dph_total"}
    headers = {"Authorization": f"Bearer {api_key}"}

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{VASTAI_BASE}/bundles", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-name", default="H100", help="GPU type (H100, H200, A100, ...).")
    parser.add_argument("--num-gpus", type=int, default=4, help="GPUs per instance.")
    parser.add_argument(
        "--max-price-per-hour",
        type=float,
        default=20.0,
        help="Max $/hr filter for the bundle.",
    )
    parser.add_argument("--top", type=int, default=10, help="Top N offers to display.")
    args = parser.parse_args()

    bundles = search_offers(
        gpu_name=args.gpu_name,
        num_gpus=args.num_gpus,
        max_price_per_hour=args.max_price_per_hour,
    )
    offers = bundles.get("offers", [])
    if not offers:
        print(f"No offers matching {args.num_gpus}× {args.gpu_name} ≤ ${args.max_price_per_hour}/hr.")
        return

    print(f"Top {args.top} offers ({args.num_gpus}× {args.gpu_name}, US/CA, verified):")
    print("-" * 80)
    print(f"{'$/hr':>8}  {'GPU':>5}  {'CPU':>4}  {'RAM(GB)':>8}  {'Disk(GB)':>9}  {'DC':<6}  Host")
    for offer in offers[: args.top]:
        print(
            f"{offer.get('dph_total', 0):>8.3f}  "
            f"{offer.get('num_gpus', 0):>5}  "
            f"{int(offer.get('cpu_cores', 0)):>4}  "
            f"{int(offer.get('cpu_ram', 0)):>8}  "
            f"{int(offer.get('disk_space', 0)):>9}  "
            f"{offer.get('geolocation', '?'):<6}  "
            f"{offer.get('hostname', '?')[:50]}"
        )
    print()
    print(f"Total matching offers: {len(offers)}")
    print("(NO COST: this script does not provision anything.)")


if __name__ == "__main__":
    main()
