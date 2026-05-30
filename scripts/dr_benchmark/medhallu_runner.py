"""Run POLARIS's entailment-verification layer against MedHallu (I-safety-002a / #924).

Codex-designed (.codex/I-safety-002a/codex_medhallu_design.txt). Honest scope: this measures
POLARIS's NLI/entailment verifier as a MedHallu detector — NOT the full provenance pipeline
(strict_verify cannot run on raw MedHallu answers). Positive class = hallucinated.

Frozen knobs (set BEFORE importing the verifier): pinned NLI model, no cross-source, no
domain-adaptive, shipped threshold, NO LLM fallback for the headline (abort if NLI down).

Usage:
  python -m scripts.dr_benchmark.medhallu_runner --split pqa_labeled --limit 10
  python -m scripts.dr_benchmark.medhallu_runner --split pqa_labeled --limit 10 --negative-control
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

# --- Codex: freeze verifier knobs BEFORE importing the NLI verifier (module reads at import) ---
os.environ.setdefault("PG_NLI_MODEL", "flan-t5-large")  # pinned, not "auto"
os.environ["PG_CROSS_SOURCE_ENABLED"] = "0"             # MedHallu = one gold packet, no corroboration
os.environ["PG_NLI_DOMAIN_ADAPTIVE"] = "0"
os.environ.setdefault("PG_FAITHFULNESS_NLI_THRESHOLD", "0.65")

import pysbd  # noqa: E402

from scripts.dr_benchmark.medhallu_adapter import (  # noqa: E402
    Confusion,
    RunGuards,
    add_prediction,
    aggregate_answer_verdict,
    build_evidence_object,
    expected_candidate_count,
    metrics,
    pair_row,
)
from src.polaris_graph.agents.nli_verifier import verify_evidence_nli  # noqa: E402

_SEG = pysbd.Segmenter(language="en", clean=False)


def _join_knowledge(knowledge) -> str:
    return " ".join(knowledge) if isinstance(knowledge, list) else str(knowledge)


def _split_claims(answer: str) -> list[str]:
    return [s.strip() for s in _SEG.segment(answer or "") if s.strip()]


async def _verdict_for_candidate(cand, question: str, knowledge: str) -> str:
    """Atomize -> claim-by-claim entailment via verify_evidence_nli -> answer verdict.

    Aborts the headline (RunGuards) if the NLI model is unavailable (returns []).
    """
    claims = _split_claims(cand.answer_text)
    if not claims:
        return "invalid"
    evidence = [build_evidence_object(c, question, knowledge, cand) for c in claims]
    url_content_map = {ev["source_url"]: knowledge for ev in evidence}
    results = await verify_evidence_nli(evidence, url_content_map, research_query="")
    if not results:
        RunGuards(nli_model_available=False).assert_headline_valid()  # raises
    flags = [bool(r.get("is_faithful")) for r in results]
    return aggregate_answer_verdict(flags)


async def run(split: str, limit: int, negative_control: bool) -> dict:
    from datasets import load_dataset

    RunGuards(nli_model_available=True, negative_control=negative_control).assert_headline_valid() if not negative_control else None

    ds = load_dataset("UTAustin-AIHealth/MedHallu", split, split="train")
    n = min(limit, len(ds)) if limit else len(ds)
    rows = [ds[i] for i in range(n)]

    # Negative control (Codex): shuffle Knowledge across rows; ground-truth support should
    # COLLAPSE. If F1 stays high, the detector is using artifacts/memorized labels, not the packet.
    if negative_control:
        shuffled = [_join_knowledge(r["Knowledge"]) for r in rows]
        random.Random(0xC0DEX).shuffle(shuffled)

    conf = Confusion()
    per_difficulty: dict[str, Confusion] = {}
    for i, r in enumerate(rows):
        question = r["Question"]
        knowledge = shuffled[i] if negative_control else _join_knowledge(r["Knowledge"])
        difficulty = str(r.get("Difficulty Level", "unknown"))
        row = {
            "row_id": f"{split}:{i}",
            "question": question,
            "knowledge": _join_knowledge(r["Knowledge"]),  # real knowledge for source-isolation guard
            "ground_truth": r["Ground Truth"],
            "hallucinated_answer": r["Hallucinated Answer"],
        }
        for cand in pair_row(row, split):
            verdict = await _verdict_for_candidate(cand, question, knowledge)
            add_prediction(conf, verdict, cand.gold_hallucinated)
            d = per_difficulty.setdefault(difficulty, Confusion())
            add_prediction(d, verdict, cand.gold_hallucinated)

    return {
        "split": split,
        "rows_scored": n,
        "candidates": expected_candidate_count(n, 0)["pqa_labeled"] if split == "pqa_labeled" else n * 2,
        "negative_control": negative_control,
        "nli_model": os.environ["PG_NLI_MODEL"],
        "threshold": float(os.environ["PG_FAITHFULNESS_NLI_THRESHOLD"]),
        "overall": metrics(conf),
        "by_difficulty": {k: metrics(v) for k, v in sorted(per_difficulty.items())},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope_label": (
            "POLARIS entailment-verification layer as a MedHallu detector. Positive class = "
            "hallucinated. Verifier: MiniCheck flan-t5-large, threshold 0.65, no retrieval, no "
            "strict provenance, no LLM fallback. NOT the full POLARIS provenance pipeline."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="pqa_labeled", choices=["pqa_labeled", "pqa_artificial"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--negative-control", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    result = asyncio.run(run(args.split, args.limit, args.negative_control))
    out = Path(args.out) if args.out else Path(
        f"outputs/dr_benchmark/medhallu_{args.split}_n{args.limit}"
        f"{'_negctrl' if args.negative_control else ''}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
