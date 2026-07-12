#!/usr/bin/env python3
"""FLYWHEEL Rank5 — THE BROKEN-vs-ALIEN DISCRIMINATOR: cross-pass row-level agreement.

The blast-radius ceiling refused to delete because 53% > 40%. But the ceiling CANNOT answer the only
question that matters — is the judge broken, or is the corpus genuinely majority-alien? It fires
identically on both. And with a ~50%-alien corpus, ANY fraction ceiling below ~55% refuses forever:
the instrument structurally cannot answer the question it is being asked.

The discriminator (Fable's, and it is the right one):

    A BROKEN judge does not reproduce ROW-LEVEL verdicts across independently shuffled passes.
    An ALIEN corpus does.

If the 53% comes from index rotation, batch-boundary confusion, or a well-formed-but-wrong response,
then re-judging the same rows in DIFFERENT batch company will scatter the verdicts. If the rows are
simply alien, each row's verdict is a property of the ROW, not of its neighbours, and it will hold.

This runs pass B over the pass-A OFF_SUBJECT candidates with SHUFFLED batch composition and reports
the per-row agreement. It DELETES NOTHING and writes no report — it is a measuring instrument.
Deterministic shuffle (fixed seed) so the result is reproducible.

Output: outputs/topic_judge_twopass.json
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("twopass")

SHUFFLE_SEED = 1729


def main() -> int:
    from scripts.compose_agentic_report_s3gear329 import _load_drb_prompt, _topic_judge_llm
    from src.polaris_graph.llm.openrouter_client import PG_GENERATOR_MODEL
    from src.polaris_graph.retrieval.topic_relevance_gate import classify_topic_relevance

    audit_path = ROOT / "outputs/topic_judge_audit.json"
    if not audit_path.exists():
        log.error("need outputs/topic_judge_audit.json (pass A) first — run flywheel_topic_judge_audit.py")
        return 2
    passA = json.loads(audit_path.read_text())
    a_off = [r["ev_id"] for r in passA["rows"] if r["verdict"] == "OFF_SUBJECT"]
    a_aspect = {r["ev_id"] for r in passA["rows"] if r["verdict"] == "OFF_ASPECT"}
    log.info("pass A: %d OFF_SUBJECT candidates, %d OFF_ASPECT", len(a_off), len(a_aspect))

    corpus = json.loads((ROOT / "data/cp4_corpus_s3gear_329.json").read_text())
    by_id = {str(r.get("evidence_id", "")): r for r in corpus["evidence"] if isinstance(r, dict)}
    rq = _load_drb_prompt("72")
    model = os.getenv("PG_SCOPE_TOPIC_MODEL", "").strip() or PG_GENERATOR_MODEL

    # SHUFFLE: the whole point. Same rows, different batch company. Deep-copy the rows so pass B
    # cannot inherit pass A's in-place stamps (classify_topic_relevance mutates rows — the exact
    # trap that made the first cross-check circular).
    rows_b = [json.loads(json.dumps(by_id[e])) for e in a_off if e in by_id]
    random.Random(SHUFFLE_SEED).shuffle(rows_b)
    log.info("pass B: re-judging the SAME %d rows in SHUFFLED batch composition (seed=%d, model=%s)",
             len(rows_b), SHUFFLE_SEED, model)

    t0 = time.time()
    result = classify_topic_relevance(rows_b, rq, _topic_judge_llm(model, 4000))

    b_off = {
        str(r.get("evidence_id", "")) for r in (result.demoted_rows or [])
        if isinstance(r, dict) and r.get("topic_off_subject") is True
    }
    b_aspect = {
        str(r.get("evidence_id", "")) for r in (result.demoted_rows or [])
        if isinstance(r, dict) and r.get("topic_off_subject") is not True
    }
    a_set = set(a_off)
    both = a_set & b_off                     # OFF_SUBJECT in BOTH passes -> the only deletable class
    flapped_to_aspect = a_set & b_aspect     # demoted to the KEEP class on re-judge
    flapped_to_ontopic = a_set - b_off - b_aspect  # judged ON_TOPIC on re-judge -> clear rescue

    agree = 100.0 * len(both) / max(1, len(a_set))
    log.info("=" * 78)
    log.info("CROSS-PASS AGREEMENT: %d/%d = %.1f%% of pass-A OFF_SUBJECT held up in pass B",
             len(both), len(a_set), agree)
    log.info("  FLAPPED -> OFF_ASPECT (demote-keep): %d", len(flapped_to_aspect))
    log.info("  FLAPPED -> ON_TOPIC   (full rescue): %d", len(flapped_to_ontopic))
    log.info("INTERPRETATION: high agreement => verdicts are a property of the ROW (alien corpus).")
    log.info("                low  agreement => verdicts depend on batch company (BROKEN judge).")
    log.info("=" * 78)

    def show(ids, label):
        if not ids:
            return
        log.info("--- %s ---", label)
        for e in sorted(ids)[:25]:
            r = by_id.get(e, {})
            log.info("   [%s] %s | %s", str(r.get("tier", "?")), e,
                     str(r.get("title", ""))[:78])

    show(flapped_to_ontopic, "RESCUED by pass B (would have been WRONGLY DELETED on a single pass)")
    show(flapped_to_aspect, "DOWNGRADED to OFF_ASPECT by pass B (keep, demote only)")

    out = ROOT / "outputs/topic_judge_twopass.json"
    out.write_text(json.dumps({
        "rq": rq, "model": model, "shuffle_seed": SHUFFLE_SEED,
        "n_pass_a_off_subject": len(a_set),
        "n_both_passes_off_subject": len(both),
        "cross_pass_agreement_pct": round(agree, 1),
        "n_flapped_to_off_aspect": len(flapped_to_aspect),
        "n_flapped_to_on_topic": len(flapped_to_ontopic),
        "elapsed_s": round(time.time() - t0, 1),
        "deletable_both_pass_ev_ids": sorted(both),
        "rescued_by_second_pass_ev_ids": sorted(flapped_to_ontopic),
        "downgraded_to_off_aspect_ev_ids": sorted(flapped_to_aspect),
        "contract": "DELETABLE = affirmative OFF_SUBJECT in BOTH independent shuffled passes. "
                    "Any disagreement => KEEP (fail-open). Deletes nothing by itself.",
    }, indent=2) + "\n", encoding="utf-8")
    log.info("-> %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
