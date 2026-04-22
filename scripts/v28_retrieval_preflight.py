"""M-48 (2026-04-22): V28 retrieval preflight — verify per-anchor
primary-trial coverage before committing to a full V28 sweep.

V27 post-mortem: 4/11 anchors produced a primary-publication hit in
the final bibliography despite M-35 anchor queries firing. M-48 adds
first-author + journal variant queries to raise landing probability;
this preflight runs a retrieval-only pass and asserts ≥1 primary-
publication row per anchor BEFORE the full sweep burns budget.

Usage:
    python scripts/v28_retrieval_preflight.py \\
        --slug clinical_tirzepatide_t2dm \\
        --question "What is the efficacy and safety of tirzepatide..." \\
        --domain clinical

Exit codes:
    0 = all anchors produce a primary match → GO for full sweep
    1 = one or more anchors failed → diagnostic report written to
        outputs/v28_retrieval_preflight_report.json; HALT
    2 = configuration / environment error

The preflight is read-only: it doesn't write to the V28 output
directory. Retrieval artifacts go to outputs/v28_preflight_tmp/ and
may be inspected by the operator.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.polaris_graph.nodes.scope_gate import load_scope_template
from src.polaris_graph.retrieval.evidence_selector import (
    _m42e_detect_primary_for_anchor,
)
from src.polaris_graph.retrieval.live_retriever import run_live_retrieval
from src.polaris_graph.retrieval.primary_trial_expander import (
    expand_primary_trial_queries,
    get_primary_trial_anchors_for_slug,
    label_rows_with_population_scope,
)
from src.polaris_graph.retrieval.regulatory_expander import (
    expand_regulatory_queries,
)

logger = logging.getLogger("v28_preflight")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="V28 retrieval preflight: per-anchor primary landing"
    )
    p.add_argument("--slug", required=True,
                   help="sweep slug (e.g. clinical_tirzepatide_t2dm)")
    p.add_argument("--question", required=True,
                   help="research question")
    p.add_argument("--domain", required=True, choices=("clinical", "policy",
                                                        "technical"),
                   help="scope template domain")
    p.add_argument("--max-serper", type=int, default=5,
                   help="Serper queries per expanded query (budget saver)")
    p.add_argument("--max-s2", type=int, default=3,
                   help="S2 queries per expanded query")
    p.add_argument("--fetch-cap", type=int, default=150,
                   help="URL fetch cap")
    p.add_argument("--report", default="outputs/v28_retrieval_preflight_report.json",
                   help="where to write the anchor-coverage report")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(
        level=os.getenv("PG_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args()

    # Load template + anchors
    try:
        template = load_scope_template(args.domain)
    except Exception as exc:
        logger.error("failed to load scope template %r: %s", args.domain, exc)
        return 2

    anchors = get_primary_trial_anchors_for_slug(template, args.slug)
    if not anchors:
        logger.error(
            "no primary_trial_anchors configured for slug=%r domain=%r",
            args.slug, args.domain,
        )
        return 2

    # Build amplified query list (regulatory + primary-trial)
    reg_queries = expand_regulatory_queries(args.question, template)
    trial_queries = expand_primary_trial_queries(
        args.question, template, args.slug,
    )
    amplified = [args.question] + reg_queries + trial_queries
    logger.info(
        "preflight query build: 1 base + %d regulatory + %d primary-trial "
        "= %d total", len(reg_queries), len(trial_queries), len(amplified),
    )

    # Run retrieval
    logger.info("starting retrieval pass (this takes ~60-120 seconds)...")
    retrieval = run_live_retrieval(
        research_question=args.question,
        amplified_queries=amplified,
        protocol=None,  # preflight bypasses protocol gate
        max_serper=args.max_serper,
        max_s2=args.max_s2,
        fetch_cap=args.fetch_cap,
        enable_openalex_enrich=True,
        enable_prefetch_filter=False,
        domain=args.domain,
    )

    # Tag rows with population scope so the report is honest about
    # which anchor matches are direct vs indirect_for_t2d.
    label_rows_with_population_scope(
        retrieval.evidence_rows, template, args.slug,
    )

    # Per-anchor coverage check
    coverage: dict[str, dict] = {}
    for anchor in anchors:
        primary_hits = [
            r for r in retrieval.evidence_rows
            if _m42e_detect_primary_for_anchor(r, anchor)
        ]
        any_hits = [
            r for r in retrieval.evidence_rows
            if anchor.lower() in (r.get("title") or "").lower()
        ]
        coverage[anchor] = {
            "primary_count": len(primary_hits),
            "any_title_mention_count": len(any_hits),
            "primary_urls": [r.get("source_url") or r.get("url") or ""
                             for r in primary_hits[:3]],
            "example_titles": [r.get("title") or ""
                               for r in primary_hits[:3]],
        }

    # Tally
    passed = [a for a, c in coverage.items() if c["primary_count"] >= 1]
    failed = [a for a, c in coverage.items() if c["primary_count"] == 0]

    report = {
        "slug": args.slug,
        "question": args.question,
        "domain": args.domain,
        "anchors_configured": len(anchors),
        "anchors_with_primary_hit": len(passed),
        "anchors_without_primary_hit": len(failed),
        "failed_anchors": failed,
        "per_anchor_coverage": coverage,
        "total_evidence_rows": len(retrieval.evidence_rows),
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    logger.info("wrote report to %s", report_path)

    # Human-readable summary
    print()
    print("=" * 60)
    print(f"V28 RETRIEVAL PREFLIGHT — {args.slug}")
    print("=" * 60)
    print(f"  anchors configured:          {len(anchors)}")
    print(f"  anchors with ≥1 primary:     {len(passed)}/{len(anchors)}")
    print(f"  anchors WITHOUT primary:     {len(failed)}")
    print(f"  total evidence rows fetched: {len(retrieval.evidence_rows)}")
    print()
    if failed:
        print("  FAILED anchors:")
        for a in failed:
            mentions = coverage[a]["any_title_mention_count"]
            print(f"    ✗ {a}  "
                  f"(0 primaries; {mentions} title-only mentions)")
        print()
        print(f"  HALT. Report: {report_path}")
        print(f"  Action: diagnose why these anchors produced no primary "
              f"publication. Candidates: paywalled PDF not fetched, "
              f"first-author variant wrong, journal name outdated.")
        return 1
    print(f"  ALL GREEN. Report: {report_path}")
    print(f"  Proceed to V28 full sweep.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
