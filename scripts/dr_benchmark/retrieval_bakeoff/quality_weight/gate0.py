#!/usr/bin/env python3
"""GATE-0 validity harness for the quality_weight retrieval-isolation bake-off (I-ret-002 #1294).

This is the anti-drb_72 gate. NO candidate AUC is trusted until BOTH halves are green:

  (A) SCORER-MATH canary — feed the within-cell AUC scorer (label, score) sets whose answers
      are mathematically KNOWN: perfectly-ranked -> EXACTLY 1.0; perfectly-inverted -> EXACTLY
      0.0; all-tied/constant -> EXACTLY 0.5; a seeded-random set -> within a pre-registered
      tolerance band of 0.5. If any deviates, the metric is mis-wired (the drb_72 "fake numbers
      that look real" failure) and no candidate is believed.

  (B) PER-CANDIDATE LIVENESS canary — for each REAL classifier candidate, feed one obviously
      authoritative doc and one obvious-garbage doc and assert the candidate ranks authoritative
      STRICTLY above garbage AND that the two scores DIFFER (not a constant). A candidate that
      returns a stub / empty / constant / load-fails / has a missing key FAILS LOUD (non-zero
      exit), never scores a believable-low number. The NEGATIVE CONTROLS (constant / random) are
      EXEMPT from semantic-direction liveness (they are EXPECTED to land near 0.5) — the harness
      instead asserts they DO land near 0.5 as a separate scorer sanity check.

The metric primitives (within-(topic x source_type)-cell paired AUC) live here so run_bakeoff.py
and smoke_test.py import the SAME scorer the canary validates — there is exactly one scorer.

Design rules honored:
  - §-1.1: AUC is rank separation of a scalar weight vs a LABELED binary ground truth — never a
    count / pattern-presence / metadata proxy. Pairs are formed ONLY within a (topic x
    source_type) cell so a global "journal=high, youtube=low" source-type prior cannot inflate
    the score (that prior is exactly the proxy this layer is paid to kill).
  - §-1.3 weight-not-filter: the weight is never thresholded to drop a source anywhere here.
  - Faithfulness engine untouched: this harness only ranks scalar weights; it never invokes,
    reads, or relaxes strict_verify / NLI / 4-role / provenance.
"""

from __future__ import annotations

import random
import sys
from collections import defaultdict
from typing import Callable, Iterable, Sequence

# ---------------------------------------------------------------------------
# Pre-registered numeric constants (locked before execution; no magic numbers
# scattered through the logic). LAW VI: tests/thresholds are named constants.
# ---------------------------------------------------------------------------
AUC_PERFECT = 1.0
AUC_INVERTED = 0.0
AUC_CONSTANT = 0.5
# Random-control band: a seeded uniform-random scorer over a finite fixture will not land EXACTLY
# at 0.5; it must land within this half-width of 0.5. 0.5 (the chance level) is the centre; the
# band is wide enough that a correctly-wired random scorer reliably passes on the synthetic canary
# set, narrow enough that a broken scorer (e.g. one that secretly tracks the label) fails it.
RANDOM_BAND_HALF_WIDTH = 0.15
# Liveness: the authoritative-vs-garbage score gap a real classifier must exceed (in raw score
# units AFTER the scorer's own scale — we only require strict ordering + a non-trivial gap so a
# float-jitter "constant" cannot sneak through as "barely higher").
LIVENESS_MIN_SCORE_GAP = 1e-6


class GateZeroQualityError(RuntimeError):
    """Raised fail-loud when a GATE-0 validity check fails. A run that raises this is INVALID
    and MUST be excluded from any score. Structural guard against the drb_72 trust-garbage
    failure: a stub / constant / load-failed / keyless candidate raises here, it never scores."""


# ===========================================================================
# METRIC PRIMITIVES (the ONE scorer the canary validates)
# ===========================================================================
def auc_pos_gt_neg(pos_scores: Sequence[float], neg_scores: Sequence[float]) -> float | None:
    """ROC-AUC computed as P(score(pos) > score(neg)) over all POS x NEG pairs (ties = 0.5).

    This pairwise form is mathematically identical to ROC-AUC and needs no sklearn dependency.
    Reused verbatim from scripts/relevance_scorer_bakeoff.py (the named LABEL_SETS seam's AUC).
    Returns None when either class is empty (no pairs => undefined, never a fake 0.5).
    """
    if not pos_scores or not neg_scores:
        return None
    wins = ties = 0
    for p in pos_scores:
        for n in neg_scores:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos_scores) * len(neg_scores))


def paired_within_cell_auc(rows: Iterable[dict], score_key: str = "score") -> dict:
    """Micro-averaged ROC-AUC with POS/NEG pairs formed ONLY within a (topic_id x source_type)
    cell.

    Each row must carry: ``label`` (1 = authoritative, 0 = on-topic-spam), ``topic_id``,
    ``source_type``, and ``score_key`` (the candidate's scalar weight). Pairs cross only a
    same-cell authoritative vs same-cell spam item, so the metric measures QUALITY separation,
    never a topic or source-type prior (the §-1.1 proxy). We MICRO-average (sum all cells' wins
    and ties, divide by all cells' pair count) rather than macro-average per-cell AUCs, so a
    1-pair cell cannot flake the headline number (advisor pt 3).

    Returns {auc, n_pairs, n_cells_scored, n_cells_skipped, per_cell:[...]}. auc is None when no
    cell has both a POS and a NEG item (fail-loud upstream, never a fake number).
    """
    cells: dict[tuple, dict] = defaultdict(lambda: {"pos": [], "neg": []})
    for r in rows:
        label = r.get("label")
        if label not in (0, 1):
            raise GateZeroQualityError(
                f"row label must be 0 or 1 (got {label!r}); the scored label is the binary "
                f"authoritative/spam ground truth, never a tier or a continuous proxy"
            )
        key = (r.get("topic_id"), r.get("source_type"))
        cells[key]["pos" if label == 1 else "neg"].append(float(r[score_key]))

    total_wins = total_ties = total_pairs = 0
    per_cell = []
    n_skipped = 0
    for (topic_id, source_type), bucket in sorted(cells.items(), key=lambda kv: str(kv[0])):
        pos, neg = bucket["pos"], bucket["neg"]
        if not pos or not neg:
            n_skipped += 1
            continue
        wins = ties = 0
        for p in pos:
            for n in neg:
                if p > n:
                    wins += 1
                elif p == n:
                    ties += 1
        npairs = len(pos) * len(neg)
        total_wins += wins
        total_ties += ties
        total_pairs += npairs
        per_cell.append({
            "topic_id": topic_id,
            "source_type": source_type,
            "n_pos": len(pos),
            "n_neg": len(neg),
            "n_pairs": npairs,
            "cell_auc": round((wins + 0.5 * ties) / npairs, 6),
        })

    auc = None if total_pairs == 0 else (total_wins + 0.5 * total_ties) / total_pairs
    return {
        "auc": None if auc is None else round(auc, 6),
        "n_pairs": total_pairs,
        "n_cells_scored": len(per_cell),
        "n_cells_skipped": n_skipped,
        "per_cell": per_cell,
    }


# ===========================================================================
# GATE-0 HALF (A): SCORER-MATH CANARY
# ===========================================================================
def _rows(scores: Sequence[float], labels: Sequence[int], topic_id="t", source_type="s") -> list:
    return [
        {"score": s, "label": l, "topic_id": topic_id, "source_type": source_type}
        for s, l in zip(scores, labels)
    ]


def run_scorer_math_canary(*, seed: int = 1234) -> dict:
    """Validate the within-cell AUC scorer on KNOWN-answer (label, score) sets. Returns a report
    dict; raises GateZeroQualityError fail-loud on ANY deviation (the drb_72 guard)."""
    report: dict = {"checks": []}

    def _record(name: str, got, expected, ok: bool):
        report["checks"].append({"name": name, "got": got, "expected": expected, "ok": ok})
        if not ok:
            raise GateZeroQualityError(
                f"SCORER-MATH canary FAILED on {name!r}: got {got!r}, expected {expected!r}. "
                f"The AUC scorer is mis-wired; no candidate score is trusted (drb_72 guard)."
            )

    # perfect: all authoritative (label 1) score above all spam (label 0) within one cell -> 1.0
    perfect = paired_within_cell_auc(_rows([0.9, 0.8, 0.7, 0.2, 0.1], [1, 1, 1, 0, 0]))
    _record("perfect_ranking", perfect["auc"], AUC_PERFECT, perfect["auc"] == AUC_PERFECT)

    # inverted: every authoritative scores BELOW every spam -> 0.0 (proves no fake credit)
    inverted = paired_within_cell_auc(_rows([0.1, 0.2, 0.3, 0.8, 0.9], [1, 1, 1, 0, 0]))
    _record("inverted_ranking", inverted["auc"], AUC_INVERTED, inverted["auc"] == AUC_INVERTED)

    # constant: every score identical -> all ties -> EXACTLY 0.5
    const = paired_within_cell_auc(_rows([0.5, 0.5, 0.5, 0.5, 0.5, 0.5], [1, 1, 1, 0, 0, 0]))
    _record("constant_scores", const["auc"], AUC_CONSTANT, const["auc"] == AUC_CONSTANT)

    # random control: seeded uniform scores, balanced labels -> within band of 0.5
    rng = random.Random(seed)
    n = 400
    labels = [1] * (n // 2) + [0] * (n // 2)
    rscores = [rng.random() for _ in range(n)]
    rnd = paired_within_cell_auc(_rows(rscores, labels))
    in_band = abs(rnd["auc"] - AUC_CONSTANT) <= RANDOM_BAND_HALF_WIDTH
    _record(
        "random_band",
        rnd["auc"],
        f"{AUC_CONSTANT}+/-{RANDOM_BAND_HALF_WIDTH}",
        in_band,
    )

    # cross-cell isolation: a per-source-type prior that is RIGHT globally but provides ZERO
    # within-cell separation must NOT score above 0.5. Two topics; within each topic the spam
    # item scores HIGHER than the authoritative item (the score tracks source-type, not quality).
    # Global AUC would be misled; within-cell AUC must report <= 0.5.
    prior_rows = [
        {"score": 0.2, "label": 1, "topic_id": "tA", "source_type": "x"},
        {"score": 0.9, "label": 0, "topic_id": "tA", "source_type": "x"},
        {"score": 0.2, "label": 1, "topic_id": "tB", "source_type": "x"},
        {"score": 0.9, "label": 0, "topic_id": "tB", "source_type": "x"},
    ]
    prior = paired_within_cell_auc(prior_rows)
    _record(
        "within_cell_kills_sourcetype_prior",
        prior["auc"],
        "<=0.5",
        prior["auc"] is not None and prior["auc"] <= AUC_CONSTANT,
    )

    report["ok"] = True
    return report


# ===========================================================================
# GATE-0 HALF (B): PER-CANDIDATE LIVENESS CANARY
# ===========================================================================
def assert_candidate_live(
    candidate_name: str,
    scorer: Callable[[str], float],
    authoritative_doc: str,
    garbage_doc: str,
) -> dict:
    """Liveness gate for ONE real classifier. The scorer must (a) load + score without raising,
    (b) rank the authoritative doc STRICTLY above the garbage doc, and (c) emit two scores that
    DIFFER by more than LIVENESS_MIN_SCORE_GAP (so a constant/stub returning the same number for
    both cannot pass). Any failure raises GateZeroQualityError fail-loud.

    A load-fail, a missing API key, or an empty/None return propagates as a raise here — NEVER a
    believable-low score. This is the precise drb_72 anti-pattern the layer must defeat.
    """
    try:
        s_auth = scorer(authoritative_doc)
        s_junk = scorer(garbage_doc)
    except Exception as exc:  # load-fail / missing-key / runtime error -> fail loud, never score
        raise GateZeroQualityError(
            f"LIVENESS canary: candidate {candidate_name!r} raised while scoring "
            f"({type(exc).__name__}: {exc}). A load-fail / missing-key / stub candidate FAILS "
            f"LOUD here; it is never given a believable-low AUC (drb_72 guard)."
        ) from exc

    if s_auth is None or s_junk is None:
        raise GateZeroQualityError(
            f"LIVENESS canary: candidate {candidate_name!r} returned None "
            f"(auth={s_auth!r} junk={s_junk!r}); a stub/empty return FAILS LOUD, never scores."
        )
    s_auth = float(s_auth)
    s_junk = float(s_junk)
    gap = s_auth - s_junk
    if abs(s_auth - s_junk) <= LIVENESS_MIN_SCORE_GAP:
        raise GateZeroQualityError(
            f"LIVENESS canary: candidate {candidate_name!r} returned a CONSTANT/degenerate "
            f"signal (auth={s_auth} junk={s_junk}, |gap|={abs(gap):.3e} <= "
            f"{LIVENESS_MIN_SCORE_GAP:.3e}). A classifier that does not vary cannot be trusted "
            f"to rank quality — it would still produce a real-looking AUC. FAIL LOUD."
        )
    if gap <= 0:
        raise GateZeroQualityError(
            f"LIVENESS canary: candidate {candidate_name!r} ranked GARBAGE >= AUTHORITATIVE "
            f"(auth={s_auth} junk={s_junk}). A real quality classifier MUST score the FDA/Cochrane "
            f"body above keyword-stuffed cookie-banner spam. FAIL LOUD (wrong-direction / mis-wired)."
        )
    return {"candidate": candidate_name, "score_auth": s_auth, "score_junk": s_junk,
            "gap": gap, "ok": True}


def assert_control_near_half(control_name: str, auc: float | None) -> dict:
    """Negative-control sanity: constant / random controls are EXEMPT from semantic-direction
    liveness but MUST land near 0.5 (no quality signal). A control that lands FAR from 0.5 means
    the harness leaked the label into the control — fail loud."""
    if auc is None:
        raise GateZeroQualityError(
            f"control {control_name!r} produced AUC=None (no scorable pairs); the control fixture "
            f"is degenerate. FAIL LOUD."
        )
    if abs(auc - AUC_CONSTANT) > RANDOM_BAND_HALF_WIDTH:
        raise GateZeroQualityError(
            f"control {control_name!r} AUC={auc:.4f} is OUTSIDE 0.5+/-{RANDOM_BAND_HALF_WIDTH}. "
            f"A no-signal control must land near chance; landing far means the harness leaked the "
            f"label into the control scorer (drb_72 guard). FAIL LOUD."
        )
    return {"control": control_name, "auc": auc, "ok": True}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: run the scorer-math canary standalone. The per-candidate liveness canary needs the
    real loaded scorers, so it is driven from run_bakeoff.py / smoke_test.py with the candidate
    registry; this entry point validates the metric math (half A) on its own."""
    try:
        report = run_scorer_math_canary()
    except GateZeroQualityError as exc:
        print(f"GATE-0 scorer-math canary: FAIL\n  {exc}", file=sys.stderr)
        return 1
    for chk in report["checks"]:
        print(f"  [{'PASS' if chk['ok'] else 'FAIL'}] {chk['name']}: "
              f"got={chk['got']} expected={chk['expected']}")
    print("GATE-0 scorer-math canary: PASS (metric math validated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
