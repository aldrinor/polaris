"""Targeted single-source MAP probe (#1217 Bug B diagnostic).

Runs the production ``distill_section_evidence`` on ONE evidence source for ONE
section, with ``PG_DISTILL_DEBUG=1`` reject tracing on, and dumps the per-source
``CoverageRow`` (status + n_findings + "N proposed, M validated" reason) plus every
validated finding's claim/quote. This answers, for the one source that matters
(the CDC safety source [4] whose findings legacy mined but the distill ledger
dropped): did the MAP propose findings, and if so which validation STEP killed
them — without running a full 8-source A/B.

Faithfulness: this ORCHESTRATES the real production distiller (zero gate drift).
The live MAP call is gated behind ``--live`` (default OFF) so the module imports
+ unit-tests offline. One source = ~one LLM call (~1 cent).

Usage (live, authorized spend, on the OVH VM):
    PG_DISTILL_DEBUG=1 python scripts/dr_benchmark/probe_source_map.py --live \
        --pool <evidence_pool.json> \
        --evidence-id probiotic_immunocompromised_contraindication \
        --section-title "Safety and contraindications" \
        --section-focus "Safety, adverse events, and contraindications of the intervention"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def load_pool(path: str | Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else list(raw.values())
    pool: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        eid = row.get("evidence_id")
        if not eid:
            raise ValueError(f"evidence row {i} has no evidence_id")
        pool[eid] = row
    return pool


async def run_probe(args: argparse.Namespace) -> int:
    from src.polaris_graph.generator.evidence_distiller import distill_section_evidence
    from src.polaris_graph.generator.multi_section_generator import SectionPlan

    pool = load_pool(args.pool)
    if args.evidence_id not in pool:
        raise SystemExit(f"evidence_id {args.evidence_id!r} not in pool ({len(pool)} rows)")
    row = pool[args.evidence_id]
    dq = row.get("direct_quote") or row.get("text") or ""
    print(f"[probe] source={args.evidence_id} dq_len={len(dq)} model={args.model}")

    section = SectionPlan(title=args.section_title, focus=args.section_focus,
                          ev_ids=[args.evidence_id])
    dist = await distill_section_evidence(
        section, [row], pool, model=args.model, max_parallel=1,
    )

    print(f"\n[probe] === COVERAGE ({len(dist.coverage)} row(s)) ===")
    for c in dist.coverage:
        print(f"  status={getattr(c,'status','?')} n_findings={getattr(c,'n_findings','?')} "
              f"reason={getattr(c,'reason','')!r}")
    print(f"\n[probe] === VALIDATED FINDINGS ({len(dist.findings)}) ===")
    for f in dist.findings:
        print(f"  - claim={f.claim!r}")
        print(f"    numbers={f.numbers} atom_ids={f.atom_ids} quote={f.support_quote[:120]!r}")
    if not dist.findings:
        print("  (none — see the [DISTILL_DEBUG] REJECT lines above for the killing step)")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Single-source MAP probe (#1217 Bug B).")
    p.add_argument("--live", action="store_true",
                   help="Make a REAL MAP LLM call (authorized spend). Default OFF.")
    p.add_argument("--pool", type=str, required=False,
                   default="outputs/audits/I-perm-010/run_drb76_iter2/drb_76_gut_microbiota_crc/evidence_pool.json")
    p.add_argument("--evidence-id", type=str, default="probiotic_immunocompromised_contraindication")
    p.add_argument("--section-title", type=str, default="Safety and contraindications")
    p.add_argument("--section-focus", type=str,
                   default="Safety, adverse events, and contraindications of the intervention")
    p.add_argument("--model", type=str, default=os.getenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro"))
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live:
        print("probe_source_map: refusing to run the LIVE MAP call without --live "
              "(it makes a real billable LLM call). Re-run with --live on the OVH VM.")
        return 0
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main())
