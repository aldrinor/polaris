"""I-meta-006 (#1006) — head-to-head FACT scorecard (lane1 faithfulness).

Aggregates per-(system × question) ClaimRows into a per-system scorecard, split
into the clinical-3 (#75/#76/#78) and the overall-5 slices SEPARATELY (the locked
label; Codex design-gate APPROVE iter3). It REUSES ``claim_audit_scorer``.

Lane2 (coverage) is GATED on the 5 hash-pinned gold rubrics, which do NOT exist
yet — authoring them is a SEPARATE follow-up Issue. While rubrics are pending the
scorecard NEVER calls the PASS rule (an empty rubric would read as coverage 0.00 →
a false fail, iter-2 P1). It reports **lane1 FACT faithfulness only**, surfaces
``lane2_pending: true`` + ``pass: null``, and makes NO PASS / "wins" claim.
``pass`` becomes a real boolean only once the hash-pinned rubrics land and
``score_system_question`` is given a non-empty rubric.

Honest framing: per-claim-traceable, every number rolls up from the per-claim
ledger; NOT a one-number superiority headline.
"""
from __future__ import annotations

import re
from collections import Counter

from src.polaris_graph.benchmark.claim_audit_scorer import (
    ClaimRow,
    RubricElement,
    lane1_faithfulness,
    system_passes_question,
)

# The locked 5-question slice (DRB-EN). Clinical = the 3 clinical questions.
CLINICAL_QIDS = ("75", "76", "78")
SOURCE_CRITICAL_QIDS = ("72", "90")
ALL_QIDS = ("75", "76", "78", "72", "90")


def normalize_qid(qid: str) -> str:
    """`Q75` / `DRB-EN#75` / `75` → `75`."""
    m = re.search(r"(\d{1,4})", str(qid))
    return m.group(1) if m else str(qid)


def score_system_question(
    rows: list[ClaimRow],
    *,
    rubric: list[RubricElement] | None = None,
) -> dict:
    """One (system × question) result. With NO rubric → lane1 FACT only +
    lane2_pending + pass=null (PASS rule withheld). With a rubric → the full
    PASS rule."""
    if not rubric:
        return {
            "lane1": lane1_faithfulness(rows),
            "lane2_pending": True,
            "pass": None,
        }
    result = system_passes_question(rows, rubric)
    return {
        "lane1": result["lane1"],
        "lane2": result["lane2"],
        "lane2_pending": False,
        "pass": result["passed"],
        "reasons": result["reasons"],
    }


def _aggregate_subset(
    rows_by_qid: dict[str, list[ClaimRow]], qids: tuple[str, ...],
) -> dict:
    rates: list[float] = []
    hard_fails = 0
    material = 0
    counts: Counter[str] = Counter()
    questions_present: list[str] = []
    for qid, rows in rows_by_qid.items():
        if qid not in qids:
            continue
        questions_present.append(qid)
        l1 = lane1_faithfulness(rows)
        rates.append(l1["unsupported_or_worse_rate"])
        hard_fails += l1["hard_fail_count"]
        material += l1["material_atoms"]
        for verdict, c in l1["verdict_counts"].items():
            counts[verdict] += c
    return {
        "questions_scored": sorted(questions_present),
        "n_questions": len(questions_present),
        "material_atoms": material,
        "mean_unsupported_or_worse_rate": (sum(rates) / len(rates)) if rates else 0.0,
        "hard_fail_count": hard_fails,
        "verdict_counts": dict(counts),
    }


def build_scorecard(
    rows_by_system_qid: dict[tuple[str, str], list[ClaimRow]],
    *,
    rubrics: dict[tuple[str, str], list[RubricElement]] | None = None,
    extended: dict | None = None,
) -> dict:
    """Per-system scorecard with clinical-3 + overall-5 slices.

    ``rows_by_system_qid`` maps (system, question_id) → ClaimRows. ``rubrics`` is
    optional; when absent (the current state), lane2 is reported as pending and no
    PASS/"wins" claim is made. ``extended`` (I-perm-024 #1216) is an OPTIONAL
    precomputed extended-metrics block; when None (the DEFAULT) the returned dict is
    byte-identical to the pre-#1216 scorecard — the extended path is purely additive.
    """
    rubrics = rubrics or {}
    lane2_pending = len(rubrics) == 0

    by_system: dict[str, dict[str, list[ClaimRow]]] = {}
    for (system, qid), rows in rows_by_system_qid.items():
        by_system.setdefault(system, {})[normalize_qid(qid)] = rows

    systems: dict[str, dict] = {}
    for system, rows_by_qid in by_system.items():
        systems[system] = {
            "overall_5": _aggregate_subset(rows_by_qid, ALL_QIDS),
            "clinical_3": _aggregate_subset(rows_by_qid, CLINICAL_QIDS),
            "source_critical_2": _aggregate_subset(rows_by_qid, SOURCE_CRITICAL_QIDS),
        }

    card = {
        "systems": systems,
        "lane2_pending": lane2_pending,
        "note": (
            "lane1 FACT faithfulness only; lane2 coverage pending hash-pinned gold "
            "rubrics (follow-up Issue); clinical-3 and overall-5 reported separately; "
            "per-claim traceable; NOT a superiority claim."
            if lane2_pending else
            "lane1 FACT faithfulness + lane2 coverage; per-claim traceable."
        ),
    }
    if extended is not None:
        card["extended"] = extended
    return card
