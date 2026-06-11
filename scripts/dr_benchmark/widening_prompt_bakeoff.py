"""I-faith-006 (#1180) — empirical bakeoff for the widening-aware entailment-judge prompt.

Scores the BASELINE prompt + each widening candidate (`widen_a/b/c`) against the §-1.1 labeled set
(`tests/fixtures/widening_labeled_set.json`) using the REAL entailment judge, and picks the winner by
``widening_neutral_recall`` subject to ``entailed_precision >= floor`` (no faithfulness regression).

SPEND: running the real judge over the labeled set is LLM spend (~labeled_rows × variants calls). It
is therefore operator/budget-gated like every other paid step — invoke with ``--run`` and a live
``OPENROUTER_API_KEY``; without ``--run`` it only validates the labeled set + candidate prompts
offline (no spend). The winning variant is wired by setting ``PG_ENTAILMENT_PROMPT_VARIANT=<winner>``
in the Gate-B slate (the judge's ``_select_entailment_prompt`` reads it; default "baseline" is
byte-identical).

Usage:
  python -m scripts.dr_benchmark.widening_prompt_bakeoff           # offline validation only
  python -m scripts.dr_benchmark.widening_prompt_bakeoff --run     # real judge bakeoff (SPEND)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.llm import widening_prompt_candidates as candidates

_LABELED_SET = _REPO_ROOT / "tests" / "fixtures" / "widening_labeled_set.json"
_VARIANTS = ["baseline", *candidates.WIDENING_VARIANTS.keys()]


def load_rows() -> list[dict]:
    data = json.loads(_LABELED_SET.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    if not rows:
        raise ValueError(f"{_LABELED_SET} has no rows")
    for r in rows:
        if not r.get("span") or not r.get("sentence") or r.get("gold") not in candidates._VALID_VERDICTS:
            raise ValueError(f"malformed labeled row: {r.get('id')!r}")
    return rows


def validate_variants() -> None:
    """Every candidate must be a drop-in: keep the {span}/{sentence} fields + STRICT-JSON contract."""
    probe = {"span": "X", "sentence": "Y"}
    for name, tmpl in candidates.WIDENING_VARIANTS.items():
        formatted = tmpl.format(**probe)  # raises KeyError if a field is missing/extra
        if "JSON" not in formatted or '"verdict"' not in formatted:
            raise ValueError(f"variant {name!r} lost the STRICT-JSON output contract")


def run_variant(rows: list[dict], variant: str) -> list[str]:
    """Run the REAL judge over every row under ``variant`` (SPEND). Returns predicted verdicts."""
    from src.polaris_graph.llm.entailment_judge import _get_judge

    os.environ["PG_ENTAILMENT_PROMPT_VARIANT"] = variant
    # Force a fresh judge each variant is unnecessary (the prompt is read per-call), but reset the
    # singleton so a prior variant's client is reused safely.
    judge = _get_judge()
    preds: list[str] = []
    for row in rows:
        verdict, _reason = judge.judge(row["sentence"], row["span"])
        preds.append(verdict)
    return preds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run the REAL judge bakeoff (LLM spend)")
    parser.add_argument("--min-entailed-precision", type=float, default=0.95)
    args = parser.parse_args()

    rows = load_rows()
    validate_variants()
    print(f"[bakeoff] labeled set OK: {len(rows)} rows; variants: {_VARIANTS}")

    if not args.run:
        print("[bakeoff] offline validation only (no --run -> no LLM spend). "
              "Re-invoke with --run + OPENROUTER_API_KEY to score against the real judge.")
        return 0

    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        print("[bakeoff] --run requires OPENROUTER_API_KEY (spend-gated).", file=sys.stderr)
        return 2

    scores: dict[str, dict] = {}
    for variant in _VARIANTS:
        preds = run_variant(rows, variant)
        scores[variant] = candidates.score_predictions(rows, preds)
        s = scores[variant]
        print(f"[bakeoff] {variant:9s} widening_neutral_recall={s['widening_neutral_recall']} "
              f"entailed_precision={s['entailed_precision']} confusion={s['confusion']}")

    winner = candidates.pick_winner(scores, min_entailed_precision=args.min_entailed_precision)
    print(f"[bakeoff] WINNER: {winner} "
          f"(wire via PG_ENTAILMENT_PROMPT_VARIANT={winner} in the Gate-B slate)")
    out = _REPO_ROOT / ".codex" / "I-perm-004" / "widening_bakeoff_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"scores": scores, "winner": winner}, indent=2), encoding="utf-8")
    print(f"[bakeoff] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
