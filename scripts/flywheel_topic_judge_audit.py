#!/usr/bin/env python3
"""FLYWHEEL Rank4 AUDIT — recover the judge's OFF_SUBJECT verdicts so a human/Fable can grade THEM.

The armed run tripped the blast-radius ceiling (529/997 = 53.1% > 40%) and — correctly — deleted
nothing. But that leaves the load-bearing question unanswered:

    Is the judge BROKEN, or is the corpus genuinely majority-alien?

Those two look identical from the ceiling's point of view, and the ceiling is exactly the wrong
place to answer it. This script re-runs the SAME judge (same model, same RQ, same batch size) over
the SAME corpus and DUMPS EVERY VERDICT WITH ITS TITLE + TIER, deleting nothing and touching no
report path. It is a read-only measuring instrument.

Output: outputs/topic_judge_audit.json  — every row, its verdict, tier, title, url.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("judge-audit")


def main() -> int:
    from scripts.compose_agentic_report_s3gear329 import _load_drb_prompt, _topic_judge_llm
    from src.polaris_graph.llm.openrouter_client import PG_GENERATOR_MODEL
    from src.polaris_graph.retrieval.topic_relevance_gate import classify_topic_relevance

    corpus = json.loads((ROOT / "data/cp4_corpus_s3gear_329.json").read_text())
    evidence = corpus["evidence"]
    rq = _load_drb_prompt("72")  # the SAME question the report is composed + scored against
    model = os.getenv("PG_SCOPE_TOPIC_MODEL", "").strip() or PG_GENERATOR_MODEL

    # SNAPSHOT THE PRIOR LABELS **BEFORE** JUDGING. `classify_topic_relevance` rewrites
    # ``topic_offtopic_demoted`` ON THE ROW OBJECTS IN PLACE (topic_relevance_gate.py:679,685 —
    # and the default-ON rescue-on-stamp leg also writes False onto fresh ON_TOPIC rows). Reading
    # that field back AFTER the judge ran therefore compares the judge against ITSELF: a circular
    # cross-check that reported a fake 100% agreement. The whole point of this column is that it is
    # an INDEPENDENT signal, so it must be captured from the pristine corpus first.
    prior_demoted: set[str] = {
        str(r.get("evidence_id", "")) for r in evidence
        if isinstance(r, dict) and r.get("topic_offtopic_demoted") is True
    }

    log.info("AUDIT: judging %d rows against DRB-72 rq (model=%s). Deletes nothing.",
             len(evidence), model)
    log.info("rq[:110]=%r", rq[:110])

    t0 = time.time()
    result = classify_topic_relevance(evidence, rq, _topic_judge_llm(model, 4000))

    off_subject = {
        str(r.get("evidence_id", ""))
        for r in (result.demoted_rows or [])
        if isinstance(r, dict) and r.get("topic_off_subject") is True
    }
    off_aspect = {
        str(r.get("evidence_id", ""))
        for r in (result.demoted_rows or [])
        if isinstance(r, dict) and r.get("topic_off_subject") is not True
    }

    rows = []
    for r in evidence:
        eid = str(r.get("evidence_id", ""))
        if eid in off_subject:
            verdict = "OFF_SUBJECT"       # deletable class
        elif eid in off_aspect:
            verdict = "OFF_ASPECT"        # demote-keep, never deletable
        else:
            verdict = "ON_TOPIC"
        rows.append({
            "ev_id": eid,
            "verdict": verdict,
            "tier": str(r.get("tier", "") or "?"),
            "title": str(r.get("title", "") or "")[:150],
            # rows carry ``source_url``; ``url`` silently yielded an empty column
            "url": str(r.get("source_url", "") or r.get("url", "") or "")[:120],
            "prior_retrieval_demote": eid in prior_demoted,  # pristine, pre-judge
        })

    out = ROOT / "outputs/topic_judge_audit.json"
    out.write_text(json.dumps({
        "rq": rq,
        "model": model,
        "n_in": result.n_in,
        "n_off_subject": len(off_subject),
        "n_off_aspect": len(off_aspect),
        "n_on_topic": sum(1 for r in rows if r["verdict"] == "ON_TOPIC"),
        "elapsed_s": round(time.time() - t0, 1),
        "rows": rows,
    }, indent=2) + "\n", encoding="utf-8")

    n_off = len(off_subject)
    log.info("OFF_SUBJECT=%d  OFF_ASPECT=%d  ON_TOPIC=%d  (%.1f%% off-subject)  -> %s",
             n_off, len(off_aspect), sum(1 for r in rows if r["verdict"] == "ON_TOPIC"),
             100.0 * n_off / max(1, result.n_in), out)

    # Agreement with the retrieval-time judge already baked into the corpus. NOTE the honest framing:
    # these are two independent INVOCATIONS, not two independent QUESTIONS — the corpus RQ and
    # task-72 are near-identical in subject+aspect. So this rules out a one-off parse/model fault;
    # it does NOT prove question-independence. Do not oversell it.
    both = prior_demoted & off_subject
    fresh_only = sorted(off_subject - prior_demoted)
    log.info("CROSS-CHECK vs the corpus's PRISTINE pre-judge demote labels: prior=%d  fresh_off=%d  "
             "AGREE=%d (%.1f%% of fresh OFF_SUBJECT were ALSO flagged by the earlier invocation)",
             len(prior_demoted), n_off, len(both), 100.0 * len(both) / max(1, n_off))
    log.info("FRESH-ONLY (flagged by this judge with NO prior corroboration — the rows a second "
             "confirmation pass matters most for): %d %s", len(fresh_only), fresh_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
