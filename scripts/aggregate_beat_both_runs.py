"""I-bug-107 — aggregate N BEAT-BOTH runs into mean ± stddev per dimension.

A single BEAT-BOTH run has high variance (sweep-to-sweep recovery rates
differ ±5pp on identical input due to LLM nondeterminism). For
benchmark publication and Carney-grade quality reporting, average N
runs and report mean ± stddev per dimension.

This script does NOT run sweeps — sweep orchestration is user-budget
gated (each full sweep is ~$0.10 OpenRouter spend). It aggregates
N pre-existing `outputs/m_live_2_beat_both/manifest.json` artifacts
that were produced by separate `scripts/run_m_live_2_beat_both.py`
invocations.

Usage:
    python scripts/aggregate_beat_both_runs.py \\
        --manifest path/to/run1/manifest.json \\
        --manifest path/to/run2/manifest.json \\
        --manifest path/to/run3/manifest.json \\
        --output outputs/m_live_2_aggregate/manifest.json

Output schema (mirrors single-run schema with aggregate fields):
    {
        "n_runs": 3,
        "input_manifests": [path1, path2, path3],
        "polaris_scores_aggregate": {
            "<dimension>": {
                "mean": float,
                "stddev": float,
                "min": float,
                "max": float,
                "values": [v1, v2, v3]
            }
        },
        "chatgpt_scores": {...},     # from first manifest (baseline; identical across runs)
        "gemini_scores": {...},      # from first manifest (baseline; identical across runs)
        "per_dimension_verdicts": {
            "<dimension>": {
                "polaris_mean": float,
                "polaris_stddev": float,
                "chatgpt": float | None,    # None when competitor missing dim
                "gemini": float | None,     # None when competitor missing dim
                "verdict": "BEAT-BOTH" | "BEAT-ONE" | "TIE" | "BEHIND" | "BEHIND-BOTH" | "N/A" | "INCOMPLETE",
                "robust": bool   # True iff (mean - stddev) > both competitors strictly
            }
        }
    }
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# I-bug-107 iter-1 diff P1 fix: reuse canonical per-dimension tolerance
# from scripts/run_m_live_2_beat_both.py / beat_both_scoring.py instead
# of a hand-rolled 1% relative tolerance. Canonical tolerance reflects
# domain knowledge per dimension (narrative_length tolerance is much
# wider than e.g. unique_citations).
from src.polaris_graph.audit_ir.beat_both_scoring import (  # noqa: E402
    tolerance_for,
)


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load a single BEAT-BOTH manifest. Validates the expected schema."""
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"polaris_scores", "chatgpt_scores", "gemini_scores"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(
            f"manifest {path} missing required keys: {sorted(missing)}"
        )
    return data


def _extract_polaris_dimension_values(
    manifests: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Group polaris_scores values by dimension across N manifests.

    Returns: {dimension_name: [run1_value, run2_value, ...]}
    """
    by_dim: dict[str, list[float]] = {}
    for manifest in manifests:
        for dim_name, dim_score in manifest["polaris_scores"].items():
            value = dim_score.get("value")
            if value is None:
                continue
            by_dim.setdefault(dim_name, []).append(float(value))
    return by_dim


def _aggregate_polaris_scores(
    manifests: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compute per-dimension mean / stddev / min / max across N runs."""
    by_dim = _extract_polaris_dimension_values(manifests)
    aggregate: dict[str, dict[str, Any]] = {}
    for dim_name, values in by_dim.items():
        if not values:
            continue
        mean = statistics.mean(values)
        stddev = statistics.stdev(values) if len(values) >= 2 else 0.0
        aggregate[dim_name] = {
            "mean": round(mean, 4),
            "stddev": round(stddev, 4),
            "min": min(values),
            "max": max(values),
            "values": values,
            "n": len(values),
        }
    return aggregate


def _compute_robust_verdicts(
    polaris_aggregate: dict[str, dict[str, Any]],
    chatgpt_scores: dict[str, dict[str, Any]],
    gemini_scores: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-dimension verdict using mean ± stddev for robustness.

    A verdict is "robust BEAT-BOTH" iff (mean - stddev) > both
    competitor scores (i.e., even the worst-case run beats both).

    Otherwise the verdict uses the mean directly with the original
    BEAT-BOTH / BEAT-ONE / TIE / BEHIND taxonomy.
    """
    verdicts: dict[str, dict[str, Any]] = {}
    for dim_name, agg in polaris_aggregate.items():
        polaris_mean = agg["mean"]
        polaris_stddev = agg["stddev"]
        # I-bug-107 iter-1 P2 fix: explicitly handle missing competitor
        # dimensions instead of fabricating 0.0. If either competitor
        # didn't score this dimension, the verdict can't be computed.
        chatgpt_score = chatgpt_scores.get(dim_name)
        gemini_score = gemini_scores.get(dim_name)
        if chatgpt_score is None or gemini_score is None:
            verdicts[dim_name] = {
                "polaris_mean": polaris_mean,
                "polaris_stddev": polaris_stddev,
                "polaris_worst_case": round(polaris_mean - polaris_stddev, 4),
                "chatgpt": None,
                "gemini": None,
                "verdict": "INCOMPLETE",
                "robust": False,
                "reason": (
                    f"competitor missing dimension: "
                    f"chatgpt={chatgpt_score is None}, "
                    f"gemini={gemini_score is None}"
                ),
            }
            continue
        chatgpt_val = chatgpt_score.get("value", 0.0)
        gemini_val = gemini_score.get("value", 0.0)

        # I-bug-107 iter-1 diff P2 fix: canonical all-zero N/A guard
        # (mirrors scripts/run_m_live_2_beat_both.py:492-494). When all
        # three scored 0.0, the dimension is structurally unmeasurable
        # — emit N/A, not TIE.
        if polaris_mean == 0.0 and chatgpt_val == 0.0 and gemini_val == 0.0:
            verdicts[dim_name] = {
                "polaris_mean": polaris_mean,
                "polaris_stddev": polaris_stddev,
                "polaris_worst_case": round(polaris_mean - polaris_stddev, 4),
                "chatgpt": chatgpt_val,
                "gemini": gemini_val,
                "verdict": "N/A",
                "robust": False,
                "rationale": (
                    "All 3 manifests scored 0.0 — dimension not "
                    "measurable on current inputs."
                ),
            }
            continue

        # I-bug-107 iter-1 diff P1 fix: use canonical per-dimension
        # tolerance (`tolerance_for(dim)`) — same as the single-run
        # verdict path. NOT a hand-rolled 1% rule.
        # I-bug-107 iter-2 diff P1 fix: use canonical ahead/behind/tie
        # taxonomy (mirrors scripts/run_m_live_2_beat_both.py:527-543).
        # Ahead-one + behind-one MUST resolve to BEHIND, NOT BEAT-ONE.
        tol = tolerance_for(dim_name)

        def _cmp_one(competitor_val: float) -> str:
            delta = polaris_mean - competitor_val
            if abs(delta) <= tol:
                return "tie"
            return "ahead" if delta > 0 else "behind"

        vs_chatgpt = _cmp_one(chatgpt_val)
        vs_gemini = _cmp_one(gemini_val)
        ahead_count = sum(1 for v in (vs_chatgpt, vs_gemini) if v == "ahead")
        behind_count = sum(1 for v in (vs_chatgpt, vs_gemini) if v == "behind")

        if ahead_count == 2:
            verdict = "BEAT-BOTH"
        elif ahead_count == 1 and behind_count == 0:
            verdict = "BEAT-ONE"
        elif behind_count == 2:
            verdict = "BEHIND-BOTH"
        elif behind_count >= 1:
            verdict = "BEHIND"
        else:
            verdict = "TIE"

        # I-bug-107 iter-1 P1 fix: robust = STRICT (mean - stddev) > both
        # competitor scores. NO tolerance — acceptance specifies strict
        # inequality. A near-margin worst_case=100.5 vs competitor=100
        # MUST count as robust=True.
        worst_case = polaris_mean - polaris_stddev
        robust = worst_case > chatgpt_val and worst_case > gemini_val

        verdicts[dim_name] = {
            "polaris_mean": polaris_mean,
            "polaris_stddev": polaris_stddev,
            "polaris_worst_case": round(worst_case, 4),
            "chatgpt": chatgpt_val,
            "gemini": gemini_val,
            "verdict": verdict,
            "robust": robust,
        }
    return verdicts


def aggregate(manifest_paths: list[Path], output_path: Path) -> dict[str, Any]:
    """Aggregate N BEAT-BOTH manifests into mean ± stddev per dimension.

    Returns the aggregate manifest dict. Also writes it to output_path.
    """
    if len(manifest_paths) < 2:
        raise ValueError(
            f"Need >=2 manifests to compute mean ± stddev; got {len(manifest_paths)}"
        )
    manifests = [_load_manifest(p) for p in manifest_paths]
    polaris_aggregate = _aggregate_polaris_scores(manifests)

    # Competitor scores should be identical across runs (same source text).
    # Use first manifest's scores as the canonical baseline.
    first = manifests[0]
    aggregate_manifest = {
        "milestone": "I-bug-107",
        "version": "v1",
        "n_runs": len(manifests),
        "input_manifests": [str(p) for p in manifest_paths],
        "polaris_scores_aggregate": polaris_aggregate,
        "chatgpt_scores": first["chatgpt_scores"],
        "gemini_scores": first["gemini_scores"],
        "per_dimension_verdicts": _compute_robust_verdicts(
            polaris_aggregate,
            first["chatgpt_scores"],
            first["gemini_scores"],
        ),
        "summary": _build_summary(polaris_aggregate),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(aggregate_manifest, indent=2),
        encoding="utf-8",
    )
    return aggregate_manifest


def _build_summary(
    polaris_aggregate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Bird's-eye summary: total dims, dims with high stddev (>10%), etc."""
    n_dims = len(polaris_aggregate)
    high_variance_dims = [
        dim
        for dim, agg in polaris_aggregate.items()
        if agg["mean"] != 0 and (agg["stddev"] / abs(agg["mean"])) > 0.1
    ]
    return {
        "n_dimensions": n_dims,
        "high_variance_dimensions": high_variance_dims,
        "high_variance_count": len(high_variance_dims),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--manifest",
        action="append",
        required=True,
        type=Path,
        help="Path to a BEAT-BOTH manifest.json. Repeatable; >=2 required.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/m_live_2_aggregate/manifest.json"),
        help="Path to write aggregate manifest.",
    )
    args = parser.parse_args()

    try:
        result = aggregate(args.manifest, args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Aggregated {result['n_runs']} runs → {args.output}")
    print(f"  {result['summary']['n_dimensions']} dimensions analyzed")
    print(
        f"  {result['summary']['high_variance_count']} high-variance "
        f"dims (stddev > 10% of mean): "
        f"{result['summary']['high_variance_dimensions']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
