"""Offline replay harness for the section-basket map (Design 4 §7a / MASTER S5).

Builds the deterministic basket->section map OFFLINE from either the bundled fixture or a
banked run dir, and prints the full assignment table one line per basket for line-by-line
forensic reading (§-1.1): claim_cluster_id | head-claim | primary section | corroborating
sections | signals {p,q,t} | member count | corroboration. Pure + deterministic => each
iteration is seconds. No LLM, no network.

Fixture mode (default):
    python scripts/replay_section_basket_map.py

Banked-run mode (expects a JSON with `baskets` + `section_plans`, optional `sub_queries` /
`evidence_rows` — the same shape the fixture uses; adapt a real run's persisted baskets +
outline plans into this shape):
    python scripts/replay_section_basket_map.py --input <path.json>

Weight/threshold overrides are honored through the env knobs the module reads (LAW VI):
    PG_SECTION_BASKET_MAP_W_PROVENANCE / _W_SUBQUERY / _W_TOPICAL / _TOPICAL_MIN.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.synthesis import section_basket_map as sbm  # noqa: E402

_DEFAULT_FIXTURE = (
    _REPO_ROOT / "tests" / "fixtures" / "section_basket_map" / "drb72_mini.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(payload: dict, *, dump_json: bool) -> int:
    baskets = payload.get("baskets") or []
    section_plans = payload.get("section_plans") or []
    m = sbm.build_section_basket_map(
        baskets,
        section_plans,
        evidence_pool=payload.get("evidence_rows"),
        sub_queries=payload.get("sub_queries"),
    )

    print(f"weights={sbm.resolve_weights()}  sections={len(section_plans)}  baskets={len(baskets)}")
    print(f"stranded_count={m.stranded_count}  residual_section_index={m.residual_section_index}")
    print("-" * 100)
    for row in m.assignment_table:
        sig = row["signals"]
        print(
            f"{row['claim_cluster_id']:30s} | {row['head_claim'][:44]:44s} | "
            f"P={row['primary_section']:<2} C={str(row['corroborating_sections']):10s} | "
            f"p={sig['provenance']} q={sig['subquery']} t={sig['topical']} | "
            f"m={row['member_count']} corr={row['corroboration_count']}"
        )
    print("-" * 100)
    for idx in sorted(m.views_by_section):
        roles = [v.role for v in m.views_by_section[idx]]
        primaries = roles.count("primary")
        corro = roles.count("corroborating")
        print(f"section {idx}: {len(roles)} views (primary={primaries} corroborating={corro})")

    # Determinism self-check: a second build must be byte-identical.
    ok = sbm.dumps_map(m) == sbm.dumps_map(
        sbm.build_section_basket_map(
            baskets,
            section_plans,
            evidence_pool=payload.get("evidence_rows"),
            sub_queries=payload.get("sub_queries"),
        )
    )
    print(f"determinism_self_check={'PASS' if ok else 'FAIL'}")
    if m.stranded_count != 0:
        print("STRANDED baskets present — invariant violated", file=sys.stderr)
        return 2
    if dump_json:
        print(sbm.dumps_map(m))
    return 0 if ok else 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline section-basket map replay")
    ap.add_argument("--input", type=Path, default=_DEFAULT_FIXTURE, help="fixture/banked JSON")
    ap.add_argument("--json", action="store_true", help="also print the full deterministic map JSON")
    args = ap.parse_args(argv)
    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 1
    return _run(_load(args.input), dump_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
