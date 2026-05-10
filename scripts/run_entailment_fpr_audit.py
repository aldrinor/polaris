"""I-bug-101 — Distributional false-positive audit on entailment judge.

Run the entailment judge on N known-good (sentence, span) pairs that
are KNOWN to satisfy the underlying invariant (every numeric in
sentence appears in span; substantive content overlap; semantic
entailment). Measure how often the judge returns NEUTRAL or
CONTRADICTED on these positive controls — the false-NULL_DROP rate.

If FPR > 5%, the judge is too aggressive and would reject legitimate
sentences in production runs at unacceptable rate. Escalate as
urgent.

Usage:
    # Provide a JSONL file of {"sentence": ..., "span": ...} pairs
    python scripts/run_entailment_fpr_audit.py \\
        --golden tests/fixtures/entailment_fpr/known_good_pairs.jsonl \\
        --output outputs/I-bug-101_audit/distribution.json

    # Or run with the built-in mini-fixture (5 pairs, smoke check)
    python scripts/run_entailment_fpr_audit.py --smoke

The actual sweep against 200 production-derived pairs requires
PG_STRICT_VERIFY_ENTAILMENT=enforce + OPENROUTER_API_KEY +
PG_MAX_COST_PER_RUN >= 1.0 (200 calls × $0.001 ≈ $0.20). It is
user-budget-gated and not invoked from this script's smoke path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Minimal known-good fixture for smoke runs. Each pair satisfies all
# six strict_verify checks INCLUDING entailment (the span fully
# supports the sentence).
SMOKE_FIXTURE: list[dict[str, str]] = [
    {
        "sentence": "Tirzepatide reduced HbA1c by 1.5% in adult patients.",
        "span": "In adult patients tirzepatide reduced HbA1c by 1.5%.",
    },
    {
        "sentence": "Semaglutide demonstrated weight loss of 14% over 68 weeks.",
        "span": "Semaglutide demonstrated 14% weight loss over 68 weeks.",
    },
    {
        "sentence": "GLP-1 receptor agonists are recommended for type 2 diabetes.",
        "span": "GLP-1 receptor agonists are recommended for type 2 diabetes.",
    },
    {
        "sentence": "The trial enrolled 2539 participants across 122 sites.",
        "span": "The trial enrolled 2539 participants across 122 sites.",
    },
    {
        "sentence": "Adverse events occurred in 27% of the treatment group.",
        "span": "Adverse events occurred in 27% of patients receiving treatment.",
    },
]


def _load_pairs(golden_path: Path | None, smoke: bool) -> list[dict[str, str]]:
    if smoke:
        return SMOKE_FIXTURE
    if golden_path is None:
        raise ValueError("either --smoke or --golden must be provided")
    if not golden_path.exists():
        raise FileNotFoundError(f"golden file not found: {golden_path}")
    pairs: list[dict[str, str]] = []
    for line in golden_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "sentence" not in obj or "span" not in obj:
            raise ValueError(f"malformed pair (missing sentence/span): {obj}")
        pairs.append({"sentence": obj["sentence"], "span": obj["span"]})
    return pairs


def run_fpr_audit(
    pairs: list[dict[str, str]],
    output_path: Path,
    *,
    live: bool = False,
) -> dict[str, Any]:
    """Run the entailment judge on each pair and tally verdicts.

    `live=True` invokes the real judge (requires PG_STRICT_VERIFY_ENTAILMENT
    not 'off' + OPENROUTER_API_KEY). `live=False` (default) is a dry-run
    that returns a stub manifest documenting the pairs without making
    any LLM call — for unit tests and CI smoke verification of the
    harness without spending budget.
    """
    if not live:
        manifest = {
            "milestone": "I-bug-101",
            "version": "v1",
            "n_pairs": len(pairs),
            "live": False,
            "stub_reason": (
                "Dry-run mode (default). Invoke with --live to call "
                "the real entailment judge. Requires "
                "PG_STRICT_VERIFY_ENTAILMENT in {warn,enforce} + "
                "OPENROUTER_API_KEY + budget headroom."
            ),
            "pairs_preview": pairs[:3],
        }
    else:
        from src.polaris_graph.llm.entailment_judge import (
            _get_judge,
            reset_judge_telemetry,
        )

        reset_judge_telemetry()
        judge = _get_judge()
        verdicts: list[dict[str, Any]] = []
        for i, pair in enumerate(pairs):
            verdict, reason = judge.judge(pair["sentence"], pair["span"])
            verdicts.append({
                "index": i,
                "sentence": pair["sentence"][:120],
                "span": pair["span"][:200],
                "verdict": verdict,
                "reason": reason[:120],
            })

        # Count distributional outcomes.
        n_entailed = sum(1 for v in verdicts if v["verdict"] == "ENTAILED")
        n_neutral = sum(1 for v in verdicts if v["verdict"] == "NEUTRAL")
        n_contradicted = sum(
            1 for v in verdicts if v["verdict"] == "CONTRADICTED"
        )
        n_judge_error = sum(
            1 for v in verdicts if v["reason"].startswith("judge_error:")
        )
        # FPR = NEUTRAL + CONTRADICTED on known-good pairs (judge_error
        # is fail-open so it counts as ENTAILED in the production
        # contract; we report it separately for diagnostic purposes).
        n_fpr = n_neutral + n_contradicted
        fpr_rate = n_fpr / len(pairs) if pairs else 0.0

        manifest = {
            "milestone": "I-bug-101",
            "version": "v1",
            "n_pairs": len(pairs),
            "live": True,
            "verdicts": verdicts,
            "summary": {
                "entailed": n_entailed,
                "neutral": n_neutral,
                "contradicted": n_contradicted,
                "judge_error": n_judge_error,
                "fpr_rate": round(fpr_rate, 4),
                "fpr_alert": fpr_rate > 0.05,
                "fpr_alert_reason": (
                    f"FPR {fpr_rate:.1%} exceeds 5% threshold — "
                    "judge is rejecting too many known-good pairs"
                ) if fpr_rate > 0.05 else None,
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--golden",
        type=Path,
        help="Path to JSONL of {sentence, span} known-good pairs.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Use built-in 5-pair smoke fixture (no --golden needed).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/I-bug-101_audit/distribution.json"),
        help="Where to write the FPR audit manifest.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Invoke the real entailment judge. Requires "
            "PG_STRICT_VERIFY_ENTAILMENT not 'off' + OPENROUTER_API_KEY. "
            "Default: dry-run."
        ),
    )
    args = parser.parse_args()
    try:
        pairs = _load_pairs(args.golden, args.smoke)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    result = run_fpr_audit(pairs, args.output, live=args.live)
    if not args.live:
        print(f"Dry-run wrote stub manifest with {result['n_pairs']} pairs to {args.output}")
        print("Add --live to invoke the real entailment judge (requires API key + budget).")
    else:
        s = result["summary"]
        print(
            f"Live FPR audit: {result['n_pairs']} pairs, "
            f"{s['fpr_rate']:.1%} FPR "
            f"({s['neutral']} NEUTRAL + {s['contradicted']} CONTRADICTED, "
            f"{s['judge_error']} judge_error)"
        )
        if s["fpr_alert"]:
            print(f"FPR ALERT: {s['fpr_alert_reason']}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
