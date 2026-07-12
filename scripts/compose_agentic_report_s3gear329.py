#!/usr/bin/env python3
"""STEP 15: compose the REAL scoreable multi-section report from the LIVE agentic run.

The mission's metric-(a) full-corpus gate (cp4_used=agentic on the 329-basket corpus) already
PASSED (docs/agentic_sweep_live_summary_s3gear329.json). What was missing was a *composed*
report we can score. This driver closes that gap: it runs the FULL generator
(``generate_multi_section_report``) with the agentic outliner ON (PG_OUTLINE_AGENT=1 + the
§9.1.8 model lock) over data/cp4_corpus_s3gear_329.json and writes report.md.

Model it on scripts/run_honest_on_prerebuild_corpus.py (which already produced report.md +
multi_section_outline.json), minus the retrieval/scope machinery (the corpus is pre-built).

Faithfulness gate (HARD): after composition, assert ZERO unverified numbers reach any
[CITE:ev_xxx] token in the composed report. The strict_verify lane already enforces this
per-section; this driver re-audits the final assembled text as an independent tripwire.

Run (key MUST be in env):
    set -a && . ./.env && set +a
    PG_OUTLINE_AGENT=1 python scripts/compose_agentic_report_s3gear329.py \
        --corpus data/cp4_corpus_s3gear_329.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DRB_QUERY = ROOT / "third_party" / "deep_research_bench" / "data" / "prompt_data" / "query.jsonl"

# STEP 2 (wheel: topic-driven structure) — the section headings are now produced TOPIC-DRIVEN by
# the generator itself (facet outline + general research-report skeleton: PG_FACET_OUTLINE=1 +
# PG_FACET_OUTLINE_SKELETON=1). The prior STEP-16 approach hardcoded a clinical-archetype ->
# AI/labor relabel MAP here — an overfit band-aid tuned to one benchmark task. That map is GONE:
# the outliner emits real topical titles (Introduction / thematic bodies / Cross-Study Synthesis /
# Conclusions and Research Gaps) for ANY domain, so assembly renders the section titles verbatim.


def _derive_title(rq: str) -> str:
    """Derive a neutral report title from the research question — GENERAL, not tuned to any task.

    Takes the first sentence/clause of the RQ, strips a leading imperative ("Please write a ...",
    "Research ...", "I am researching ..."), and Title-cases nothing (keeps the RQ's own wording).
    Falls back to a generic label. No topic is hardcoded."""
    import re as _re
    s = (rq or "").strip().replace("\n", " ")
    s = _re.sub(r"\s+", " ", s)
    # First sentence only.
    s = _re.split(r"(?<=[.?!])\s", s, maxsplit=1)[0]
    # Strip common leading imperatives so the title reads as a subject, not a command.
    s = _re.sub(r"^(please\s+)?(help me\s+)?(write|prepare|produce|conduct|research(ing)?|"
                r"provide|create|complete|collect( and)?( organi[sz]e)?|i am researching|"
                r"i would like|i need)\b[:,]?\s*", "", s, flags=_re.IGNORECASE)
    s = s.strip().rstrip(".").strip()
    if not s:
        return "Research Report"
    # Capitalize the first letter only (preserve proper-noun casing in the rest).
    return s[0].upper() + s[1:]


def _load_drb_prompt(task_id: str) -> str:
    """Load a DeepResearch-Bench task's EXACT prompt verbatim (target/ref/criteria all key on it)."""
    for line in DRB_QUERY.read_text().splitlines():
        o = json.loads(line)
        if str(o.get("id")) == str(task_id):
            return o["prompt"]
    raise SystemExit(f"BLOCKED: DRB task id {task_id} not in {DRB_QUERY}")

logging.basicConfig(
    level=os.environ.get("PG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("compose")


def _tier_fractions(evidence: list[dict]) -> dict[str, float]:
    from collections import Counter
    c = Counter((e.get("tier") or "T?").upper() for e in evidence)
    n = sum(c.values()) or 1
    return {k: v / n for k, v in sorted(c.items())}


# A numeric token that would be a faithfulness breach if it sat inside a [CITE:] sentence
# without having passed strict_verify. We audit the FINAL assembled report: any [CITE:ev_xxx]
# in the verified text is, by construction, already span-grounded — but we re-scan to prove it.
_CITE_RE = re.compile(r"\[CITE:(ev_[0-9a-fA-F]+|[a-z0-9_]+)\]")


def _audit_citations(report_text: str, biblio: list[dict]) -> dict:
    """Independent faithfulness tripwire on the FINAL assembled report.

    strict_verify resolves every kept sentence's provenance token into a global [N] bibliography
    marker and DROPS any sentence whose number failed the span match. So in a faithful final
    report: (1) ZERO raw [CITE:ev_xxx] tokens survive (any survivor is an unverified-number leak
    — the exact breach the mission forbids), and (2) every [N] marker in the prose resolves to a
    real bibliography entry. We assert both."""
    leaked_cites = _CITE_RE.findall(report_text)
    body = report_text.split("\n\n## References\n", 1)[0]  # markers in prose only
    n_markers = set(int(m) for m in re.findall(r"\[(\d+)\]", body))
    biblio_nums = {int(b.get("num")) for b in biblio if str(b.get("num", "")).isdigit()}
    unresolved = sorted(n for n in n_markers if n not in biblio_nums)
    return {
        "leaked_cite_ev_tokens": len(leaked_cites),
        "leaked_cite_samples": sorted(set(leaked_cites))[:10],
        "distinct_bib_markers_in_prose": len(n_markers),
        "bibliography_entries": len(biblio_nums),
        "unresolved_markers": unresolved,
    }


# ── FLYWHEEL Rank4 — ARM THE SEMANTIC TOPIC JUDGE ON A PRE-BUILT CORPUS ─────────────────────────
#
# THE GAP (measured, not theorised): the §-1.3.1(b) off-topic DELETE leg has never fired on this
# path. `is_row_deletable_offtopic` keys on an AFFIRMATIVE ``topic_off_subject`` stamp, and the ONLY
# writer of that stamp is ``classify_topic_relevance`` — which runs at RETRIEVAL time (the live
# sweep) and is called by NOTHING on the pre-built-corpus path. The corpus carries 633
# ``topic_offtopic_demoted`` labels but ZERO ``topic_off_subject`` stamps, so the run logged
# "DELETED 0 judge-confirmed off-topic item(s)" and ~294 alien sources (climate-risk IMF working
# papers, privacy-attack bibliographies, school-infrastructure pages, content-marketing stats) sat in
# the grounding pool, eligible to be CITED in an AI-labour literature review. The faithfulness engine
# cannot catch them: strict_verify checks span fidelity, not topicality — a sentence grounded on a
# climate working paper is perfectly FAITHFUL and perfectly off-topic.
#
# THE FIX: ARM the judge that already exists. We do NOT build a new one, and we do NOT lexically
# guess. §-1.3.1(b) admits exactly one delete trigger — an affirmative SEMANTIC judge verdict,
# FAIL-OPEN. Everything below is fail-open scaffolding around that one call:
#   * The judge is run against ``rq`` — the SAME (DRB-override) question the report is composed and
#     scored against. Judging the corpus's own RQ would produce a FOREIGN verdict (the false
#     hard-drop §-1.3.1(b) forbids, and the exact landmine Rank2b defused).
#   * TOKEN-STARVATION TRAP (the silent no-op): ``PG_SCOPE_TOPIC_MAX_TOKENS`` defaults to 1200, but
#     the judge model is reasoning-first — it burns the budget on hidden reasoning, truncates before
#     emitting its verdict lines, returns empty content, and EVERY batch fails open. The judge would
#     "run", bill real money, and delete nothing. We raise the floor to 4000 and FAIL LOUD if every
#     batch failed open (that is an outage, not a verdict of "all clean").
#   * BLAST-RADIUS CEILING: if the judge confirms OFF_SUBJECT on more than PG_TOPIC_DELETE_MAX_FRACTION
#     (default 0.40) of judged rows, we delete NOTHING and log LOUD. A well-formed but WRONG batch
#     response (index rotation, prompt injection from a snippet) is the one failure the parser cannot
#     catch; this is the containment. It can only ever REFUSE deletion — it can never force a number
#     up, so it is not a banned breadth knob.
#   * T1/T2 DOUBLE-CONFIRMATION (not exemption): a seminal paper wrongly verdicted OFF_SUBJECT is the
#     costliest false delete. A blanket high-tier exemption would use tier as a RELEVANCE proxy and
#     would shield precisely the credible-tier junk this audit found (the IMF climate WPs are T1/T2).
#     So tier is NOT a keep-veto; it is an ESCALATION criterion: a T1/T2 row the batch judge marks
#     OFF_SUBJECT is RE-judged alone on its full quote, and deletes only on a SECOND affirmative
#     verdict. Nobody is kept by tier and nobody is deleted by tier — the bar is just higher where a
#     mistake costs most.
# Default-OFF (``PG_PREBUILT_TOPIC_JUDGE``): unset => returns None => the generator passes ``()`` at
# the pool seam exactly as today => byte-identical.
_TOPIC_JUDGE_ENV = "PG_PREBUILT_TOPIC_JUDGE"
_TOPIC_DELETE_MAX_FRACTION_ENV = "PG_TOPIC_DELETE_MAX_FRACTION"
# Fixed so pass B is REPRODUCIBLE: the shuffle must be a different batch composition,
# not a different result run-to-run.
_TWOPASS_SEED = 1729


def _topic_judge_llm(model: str, max_tokens: int):
    """Synchronous ``str -> str`` LLM bridge for the judge (mirrors the live sweep's `_topic_llm`).

    The judge is a pure sync function by design (unit-testable with a stub), so the async
    OpenRouter client is driven on a worker thread with its own event loop."""
    import asyncio as _asyncio  # noqa: PLC0415
    import concurrent.futures as _futures  # noqa: PLC0415

    def _call(prompt: str) -> str:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

        async def _run() -> str:
            client = OpenRouterClient(model=model)
            try:
                resp = await client.generate(
                    prompt=prompt, max_tokens=max_tokens, temperature=0.0,
                )
                return (resp.content or "").strip()
            finally:
                if hasattr(client, "close"):
                    try:
                        await client.close()
                    except Exception:  # noqa: BLE001
                        pass

        with _futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: _asyncio.run(_run())).result()

    return _call


def _arm_topic_judge(evidence: list, rq: str, run_dir: Path, log,
                     same_work_groups: list | None = None) -> "set[str] | None":
    """Run the semantic topic judge over a PRE-BUILT corpus; return the FRESH OFF_SUBJECT id set.

    Returns None when the flag is OFF (=> the generator's off-topic arm stays inert, byte-identical).
    Returns a (possibly empty) concrete set when the judge ran. FAIL-OPEN everywhere: any exception,
    any starved/unparseable batch, or a tripped blast-radius ceiling yields an EMPTY set — which
    deletes NOTHING. Deletion requires an affirmative verdict; never an absence of one."""
    if os.getenv(_TOPIC_JUDGE_ENV, "0").strip().lower() in ("", "0", "false", "off", "no"):
        return None

    from src.polaris_graph.llm.openrouter_client import PG_GENERATOR_MODEL  # noqa: PLC0415
    from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
        _row_is_chrome_nonsource,
        classify_topic_relevance,
        junk_chrome_before_offtopic_enabled,
        mark_topic_judge_ran,
    )

    # Count what the gate will SKIP, using the gate's OWN predicate (not a re-implementation), so the
    # ceiling's denominator can't drift from what was actually judged.
    _n_chrome = (
        sum(1 for _r in evidence if isinstance(_r, dict) and _row_is_chrome_nonsource(_r))
        if junk_chrome_before_offtopic_enabled() else 0
    )

    model = os.getenv("PG_SCOPE_TOPIC_MODEL", "").strip() or PG_GENERATOR_MODEL
    # The starvation floor. A reasoning-first judge at 1200 truncates before its verdict lines.
    try:
        max_tokens = int(os.getenv("PG_SCOPE_TOPIC_MAX_TOKENS", "").strip() or "4000")
    except ValueError:
        max_tokens = 4000
    max_tokens = max(max_tokens, 4000)
    llm = _topic_judge_llm(model, max_tokens)

    by_id_all = {
        str(r.get("evidence_id", "") or ""): r for r in evidence if isinstance(r, dict)
    }

    t0 = time.time()
    log.info("[topic-judge] ARMED (§-1.3.1(b)): judging %d rows against the COMPOSED rq "
             "(model=%s max_tokens=%d). Fail-open: only an affirmative OFF_SUBJECT deletes.",
             len(evidence), model, max_tokens)
    try:
        result = classify_topic_relevance(evidence, rq, llm)
    except Exception as exc:  # noqa: BLE001 — a judge crash must NEVER delete anything
        log.error("[topic-judge] judge FAILED (%s) — deleting NOTHING (fail-open).", exc)
        return set()
    mark_topic_judge_ran()

    fresh = {
        str(r.get("evidence_id", "") or "")
        for r in (result.demoted_rows or [])
        if isinstance(r, dict) and r.get("topic_off_subject") is True
    }
    fresh.discard("")

    # FAIL-LOUD: the judge ran but confirmed literally nothing across ~1000 rows of a corpus we KNOW
    # carries alien sources. That is far more likely an outage (starved/failed batches) than a clean
    # corpus. Say so; do not silently report success.
    if not fresh:
        log.error("[topic-judge] judge returned ZERO OFF_SUBJECT verdicts over %d rows. Treat as a "
                  "SUSPECTED OUTAGE (starved reasoning budget / failed batches), NOT as 'corpus is "
                  "clean'. Deleting nothing.", result.n_in)
        _write_topic_disclosure(run_dir, result, fresh, "zero_verdicts_suspected_outage", model, t0)
        return set()

    # ── RANK5: CROSS-PASS AGREEMENT — the broken-vs-alien discriminator ────────────────────────
    # A fraction ceiling cannot tell a BROKEN judge from an ALIEN corpus: it fires identically on
    # both. (And on a genuinely ~50%-alien corpus, ANY ceiling below ~55% refuses forever — the
    # instrument structurally cannot answer the question it is asked.) The property that DOES
    # separate them is row-level reproducibility:
    #
    #     A BROKEN judge does not reproduce ROW-LEVEL verdicts across independently shuffled passes.
    #     An ALIEN corpus does — an alien row is alien regardless of which rows it is batched with.
    #
    # So re-judge the candidates in DIFFERENT batch company and delete ONLY on agreement in BOTH
    # passes. Measured on this corpus: 518/533 = 97.2% held (=> alien, not broken), and the 15
    # flappers were exactly the OFF_ASPECT/OFF_SUBJECT boundary rows an independent gate had
    # predicted would be false positives (AI-in-education, AI-in-science, BLS projections).
    # Disagreement => KEEP. This applies to EVERY tier — the old rail escalated only T1/T2, which
    # left the same boundary noise unchecked everywhere else.
    _pass_b_rows = [json.loads(json.dumps(by_id_all[e])) for e in sorted(fresh) if e in by_id_all]
    random.Random(_TWOPASS_SEED).shuffle(_pass_b_rows)
    log.info("[topic-judge] PASS B: re-judging the %d candidates in SHUFFLED batch composition "
             "(seed=%d). Deletable = affirmative OFF_SUBJECT in BOTH passes; any disagreement KEEPS.",
             len(_pass_b_rows), _TWOPASS_SEED)
    try:
        _res_b = classify_topic_relevance(_pass_b_rows, rq, llm)
    except Exception as exc:  # noqa: BLE001 — a pass-B crash must never widen the delete set
        log.error("[topic-judge] PASS B FAILED (%s) — deleting NOTHING (fail-open).", exc)
        _write_topic_disclosure(run_dir, result, set(), "pass_b_failed", model, t0, refused=fresh)
        for _eid in fresh:
            (by_id_all.get(_eid) or {}).pop("topic_off_subject", None)
        return set()
    _b_off = {
        str(r.get("evidence_id", "") or "")
        for r in (_res_b.demoted_rows or [])
        if isinstance(r, dict) and r.get("topic_off_subject") is True
    }
    _flapped = fresh - _b_off
    if _flapped:
        log.warning("[topic-judge] CROSS-PASS: %d/%d held (%.1f%%). %d row(s) FLAPPED on re-judge "
                    "and are KEPT (fail-open): %s", len(fresh & _b_off), len(fresh),
                    100.0 * len(fresh & _b_off) / max(1, len(fresh)), len(_flapped),
                    ", ".join(sorted(_flapped)[:12]))
        # A flapped row must not keep pass A's delete-stamp on the ORIGINAL (the pop above happened
        # on pass B's deep copies).
        for _eid in _flapped:
            (by_id_all.get(_eid) or {}).pop("topic_off_subject", None)
    fresh &= _b_off

    # SAME-WORK-GROUP INVARIANT (free, deterministic): never delete a row whose same-work sibling
    # survived as ON_TOPIC. The same underlying work cannot be both alien and on-topic; if the judge
    # split a group, the group is a boundary case and we keep all of it.
    _rescued_swg: list[str] = []
    for _grp in (same_work_groups or []):
        # Groups arrive as dicts ({'same_work_id', 'member_evidence_ids', ...}), NOT bare id lists.
        # Accept both — a guard that silently matches nothing is worse than no guard at all.
        if isinstance(_grp, dict):
            _ids = [str(x) for x in (_grp.get("member_evidence_ids") or [])]
        elif isinstance(_grp, (list, tuple)):
            _ids = [str(x) for x in _grp]
        else:
            _ids = []
        _off_in = [e for e in _ids if e in fresh]
        if _off_in and any(e not in fresh for e in _ids):
            _rescued_swg.extend(_off_in)
    if _rescued_swg:
        log.warning("[topic-judge] SAME-WORK GUARD rescued %d row(s) whose same-work sibling was "
                    "KEPT (a work cannot be alien and on-topic at once): %s",
                    len(_rescued_swg), ", ".join(sorted(set(_rescued_swg))[:12]))
        for _eid in _rescued_swg:
            (by_id_all.get(_eid) or {}).pop("topic_off_subject", None)
        fresh -= set(_rescued_swg)
    if not fresh:
        log.error("[topic-judge] nothing survived cross-pass agreement — deleting NOTHING.")
        _write_topic_disclosure(run_dir, result, set(), "no_cross_pass_agreement", model, t0)
        return set()

    # T1/T2 ESCALATION — a THIRD look, on top of cross-pass agreement, for the rows where a false
    # delete costs most. Escalate, never exempt: tier is not a keep-veto (that would shield exactly
    # the credible-tier junk this corpus is full of — the 21 T1/T2 rows in the delete set include
    # climate science and mass-deworming RCTs). Tier only raises the BAR. This can only ever rescue.
    escalated_kept: list[str] = []
    for eid in sorted(fresh):
        row = by_id_all.get(eid) or {}
        if str(row.get("tier", "") or "").strip().upper() not in ("T1", "T2"):
            continue
        try:
            confirm = classify_topic_relevance([dict(row)], rq, llm)
        except Exception as exc:  # noqa: BLE001 — uncertainty => KEEP
            log.warning("[topic-judge] T1/T2 re-judge errored for %s (%s) — KEEPING (fail-open).",
                        eid, str(exc)[:80])
            escalated_kept.append(eid)
            continue
        still_off = any(
            isinstance(r, dict) and r.get("topic_off_subject") is True
            for r in (confirm.demoted_rows or [])
        )
        if not still_off:
            escalated_kept.append(eid)
    if escalated_kept:
        log.warning("[topic-judge] T1/T2 escalation RESCUED %d high-tier row(s) the batch judge had "
                    "marked OFF_SUBJECT (second verdict did not confirm): %s",
                    len(escalated_kept), ", ".join(escalated_kept[:12]))
        fresh -= set(escalated_kept)
        # The re-judge above ran on ``dict(row)`` — a COPY — so the gate's stale-stamp `pop` landed
        # on the copy and the ORIGINAL row still carries topic_off_subject=True. Today that is inert
        # (the fresh-id fence is what actually authorises a delete, and this id is no longer in it),
        # but a rescued row that still looks OFF_SUBJECT in memory is a landmine for anything that
        # later serializes the pool to a snapshot: the row would come back as a pre-stamped delete
        # candidate. Clear it on the ORIGINAL — a rescue must leave no trace of the wrong verdict.
        for _eid in escalated_kept:
            (by_id_all.get(_eid) or {}).pop("topic_off_subject", None)

    # BLAST-RADIUS CEILING — containment for a well-formed-but-wrong judge response.
    # THE CEILING IS NOW AN OUTAGE TRIPWIRE, NOT A POLICY KNOB — and that reclassification is the
    # whole point. As a policy knob it was incoherent: it fires identically on a broken judge and on
    # an alien corpus, and on a ~50%-alien corpus ANY setting below ~55% refuses forever, so it could
    # never let a TRUE verdict through. Cross-pass agreement (above) is what now decides deletion,
    # per row. What is left for a fraction to do is catch the one failure a per-row rule cannot: a
    # systemic fault (parser break, model outage, prompt injection) in which BOTH passes are garbage
    # and agree with each other. That looks like a near-total wipe, so the tripwire sits at 0.75 —
    # a level that indicates machinery failure, not corpus composition. It can still only REFUSE;
    # it can never widen a delete set, so it remains a refusal device, never a breadth trigger.
    try:
        max_frac = float(os.getenv(_TOPIC_DELETE_MAX_FRACTION_ENV, "").strip() or "0.75")
    except ValueError:
        max_frac = 0.75
    # Denominator = rows the judge could actually VERDICT, not every row handed in. ``n_in`` counts
    # marquee-exempt rows and chrome non-sources (which are skipped, never judged); including them
    # DILUTES the fraction, so the ceiling would trip LATER than its own setting implies — the rail
    # would be quietly weaker than it reads.
    judged = max(1, int(result.n_in or len(evidence)) - int(result.n_exempt or 0) - _n_chrome)
    frac = len(fresh) / judged
    if frac > max_frac:
        log.error("[topic-judge] OUTAGE TRIPWIRE: %d/%d rows (%.1f%%) survived BOTH passes as "
                  "OFF_SUBJECT, above the %.1f%% systemic-fault threshold. Two passes agreeing on a "
                  "near-total wipe is far more likely broken machinery than a verdict. Refusing to "
                  "delete ANY row (fail-open).",
                  len(fresh), judged, frac * 100, max_frac * 100)
        # The REFUSED candidates are still persisted (as refused, NOT as deleted). Writing an empty
        # id list here would make the containment self-concealing: an operator could not tell a
        # broken judge from a genuinely alien corpus, because the only evidence that distinguishes
        # them — WHICH rows were flagged — would have been discarded by the very rail that fired.
        # Containment must leave an audit trail, not destroy one. Nothing is deleted either way.
        _write_topic_disclosure(run_dir, result, set(), "blast_radius_tripped", model, t0,
                                refused=fresh, ceiling=max_frac, observed_fraction=frac)
        # A REFUSED verdict must not linger on the rows either: every one of these originals still
        # carries topic_off_subject=True from the batch pass. We are declining to act on that
        # verdict, so it must not survive in memory as a pre-stamped delete candidate for any later
        # seam or snapshot. Refusing to delete and leaving the delete-stamp on is the worst of both.
        for _eid in fresh:
            (by_id_all.get(_eid) or {}).pop("topic_off_subject", None)
        return set()

    log.warning("[topic-judge] VERDICT: %d/%d rows affirmatively OFF_SUBJECT (%.1f%%) -> DELETABLE "
                "(§-1.3.1(b), disclosed). kept=%d demoted=%d exempt=%d  %.0fs",
                len(fresh), judged, frac * 100, result.n_kept,
                result.n_demoted_offtopic, result.n_exempt, time.time() - t0)
    _write_topic_disclosure(run_dir, result, fresh, "armed", model, t0)
    return fresh


def _write_topic_disclosure(run_dir: Path, result, fresh: set, status: str, model: str,
                            t0: float, *, refused: set | None = None,
                            ceiling: float | None = None,
                            observed_fraction: float | None = None) -> None:
    """Durable §-1.3.1 disclosure, written BEFORE compose so it survives an aborted run.

    ``fresh`` = rows that WILL be deleted. ``refused`` = rows the judge flagged but a containment
    rail declined to act on (deleted: none). The two are disjoint and never conflated."""
    try:
        payload: dict[str, Any] = {
            "status": status,
            "model": model,
            "n_in": getattr(result, "n_in", 0),
            "n_kept": getattr(result, "n_kept", 0),
            "n_demoted_offtopic": getattr(result, "n_demoted_offtopic", 0),
            "n_exempt": getattr(result, "n_exempt", 0),
            "n_off_subject_deletable": len(fresh),
            "off_subject_ev_ids": sorted(fresh),
            "elapsed_s": round(time.time() - t0, 1),
            "contract": "affirmative OFF_SUBJECT judge verdict only; fail-open; positive relevance "
                        "vetoes; T1/T2 double-confirmed; blast-radius ceiling enforced",
        }
        if refused is not None:
            payload["n_refused_not_deleted"] = len(refused)
            payload["refused_off_subject_ev_ids"] = sorted(refused)
            payload["ceiling_fraction"] = ceiling
            payload["observed_fraction"] = round(observed_fraction or 0.0, 4)
            payload["refused_note"] = (
                "The judge flagged these rows OFF_SUBJECT but a containment rail REFUSED the "
                "deletion — they were KEPT and remain citable. Listed so the refusal itself is "
                "auditable: a genuinely alien corpus and a broken judge look identical without them."
            )
        (run_dir / "topic_judge_dispositions.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — disclosure must never break the run
        logging.getLogger("compose").warning("[topic-judge] disclosure write failed: %s", exc)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--rq-drb-task", default="72",
                    help="override the corpus RQ with this DRB task's verbatim prompt so the "
                         "composed report answers the SAME task it is scored against; empty string "
                         "keeps the corpus RQ")
    ap.add_argument("--title", default=None,
                    help="report title for the judged report.md; default DERIVES it from the RQ "
                         "(general — no title is hardcoded to any task)")
    args = ap.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        log.error("BLOCKED: OPENROUTER_API_KEY not in env — source .env first "
                  "(set -a && . ./.env && set +a)")
        return 2
    # The mission model-lock: agentic outliner ON.
    os.environ.setdefault("PG_OUTLINE_AGENT", "1")
    # P0 CONFIRMED-SAFE COMPOSE CONFIG (2026-07-12) — PIN the non-deadlocking config in the launch
    # path. The clean 24.2min/1449.7s run used exactly this: off-loop ON (shipped, verdict-safe),
    # PG_COMPOSE_BASKET_WORKERS=1 (serial byte-identical MAP+REDUCE — NEVER >1 without a full-328
    # verdict-identity A/B), PG_SIDE_JUDGE_MAX_CONCURRENCY in the 4-8 band (NEVER >=48), and
    # PG_PARALLEL_SECTIONS=3. These are setdefault (an explicit operator override still wins) but they
    # keep this driver on the certified-safe path; the startup guard (compose_config_guard) refuses the
    # deadlocking regime regardless. Faithfulness-neutral: pure concurrency knobs.
    os.environ.setdefault("PG_COMPOSE_BASKET_WORKERS", "1")
    os.environ.setdefault("PG_SIDE_JUDGE_MAX_CONCURRENCY", "8")
    os.environ.setdefault("PG_PARALLEL_SECTIONS", "3")
    # P1-SPEED (2026-07-12) — collapse the ISOLATED pre-compose credibility member-verify pass.
    # ROOT-CAUSE of the 43min (2589.7s) >> 24min (1449.7s) gap, MEASURED from the phase timeline in
    # logs/step3_full328_render.log: threading the PSL gov_suffixes (below) to lift route_all basket
    # utilization ALSO activates the ADVISORY credibility corroboration pass. On this 997-member corpus
    # that pass ran SERIALLY (PG_CREDIBILITY_PASS_MAX_INFLIGHT default=1) and BANKED at its
    # wall*0.85 soft deadline = 1020s, verifying only 207/997 members — a full +1020s phase the 1449.7s
    # baseline NEVER ran (it did not thread gov_suffixes -> credibility degraded-to-unscored, skipped).
    # This pass runs ENTIRELY BEFORE compose (an ISOLATED flat phase — NO PG_PARALLEL_SECTIONS x
    # PG_COMPOSE_BASKET_WORKERS x inner-TPE nesting), so bounding its OWN loop concurrency is NOT the
    # multiplicative compose oversubscription the deadlock guard protects against. Parallelize the
    # member-verify loop and raise the side-judge cap FOR THIS PHASE ONLY (the designed I-deepfix-001
    # box2 lever; credibility_pass_concurrency RESTORES the compose-time cap of 8 before compose starts).
    # Faithfulness-neutral & UNDERCOUNT-only: the pass is ADVISORY (strict_verify / 4-role D8 /
    # span-grounding are untouched); verifying MORE members in LESS time yields STRICTLY MORE
    # corroboration than the 207-serial run and far more than the baseline's zero. All env-overridable.
    os.environ.setdefault("PG_CREDIBILITY_PASS_MAX_INFLIGHT", "16")
    os.environ.setdefault("PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY", "16")
    os.environ.setdefault("PG_CREDIBILITY_PASS_WALL_S", "600")
    # STEP 2: topic-driven, synthesis-enabling structure. Facet outline (thematic sections emerge
    # from the evidence) + the general research-report skeleton (intro / thematic bodies /
    # cross-study synthesis+contradictions / conclusions+gaps). GENERAL structural flags — they
    # hardcode no topic and are overridable from the environment.
    os.environ.setdefault("PG_FACET_OUTLINE", "1")
    os.environ.setdefault("PG_FACET_OUTLINE_SKELETON", "1")
    # STEP 3 (INSIGHT depth): make the cross-study synthesis section quantify agreement/disagreement
    # across the [ev]-backed body figures (enrich its evidence + directive). GENERAL structural
    # lever — role detected structurally, no topic/title hardcoded; strict_verify unchanged.
    os.environ.setdefault("PG_SYNTHESIS_QUANT_DIRECTIVE", "1")
    # STEP 4 (UTILIZATION — the basket under-utilization ghost): the live LLM outline lists only a
    # handful of ev_ids per section, so ~90% of the consolidated baskets reach NO section and never
    # compose a cited claim (measured 31/329 rendered; scripts/measure_utilization_route_all.py). Route
    # every ORPHAN basket to its best-matching thematic section by claim-vs-title content overlap (else a
    # single keep-all residual section). GENERAL, faithfulness-neutral: pure CONSOLIDATE placement —
    # drops no source, caps nothing; every routed basket's rendered sentence re-passes the UNCHANGED
    # strict_verify per clause. Deterministic A/B proved 31->328 baskets rendered. Also drop the
    # PG_MAX_EV_PER_SECTION row-cap ceiling so a facet keeps its full matched payload.
    os.environ.setdefault("PG_ROUTE_ALL_BASKETS", "1")
    os.environ.setdefault("PG_EV_BUDGET_TRACKS_PAYLOAD", "1")

    corpus_path = Path(args.corpus)
    corpus = json.loads(corpus_path.read_text())
    corpus_rq = corpus["research_question"]
    if args.rq_drb_task:
        rq = _load_drb_prompt(args.rq_drb_task)
        log.info("RQ OVERRIDE: composing to DRB task %s verbatim prompt (corpus RQ kept as "
                 "provenance only). task_rq[:90]=%r", args.rq_drb_task, rq[:90])
    else:
        rq = corpus_rq
    evidence = corpus["evidence"]
    raw_clusters = corpus.get("finding_clusters") or []
    clusters = [SimpleNamespace(**c) if isinstance(c, dict) else c for c in raw_clusters]
    swg = corpus.get("same_work_groups")
    domain = corpus.get("domain", "")

    run_id = time.strftime("agentic_report_%Y%m%d_%H%M%S")
    run_dir = ROOT / (args.out_dir or f"outputs/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("corpus=%s  evidence=%d  clusters=%d  same_work_groups=%s  domain=%s",
             corpus_path.name, len(evidence), len(clusters),
             len(swg or []), domain or "(none)")
    log.info("PG_OUTLINE_AGENT=%s  out_dir=%s", os.getenv("PG_OUTLINE_AGENT"), run_dir)

    # FLYWHEEL Rank4: ARM the §-1.3.1(b) semantic topic judge on the PRE-BUILT corpus.
    fresh_off_subject = _arm_topic_judge(evidence, rq, run_dir, log, same_work_groups=swg)

    from src.polaris_graph.generator.multi_section_generator import (  # noqa: PLC0415
        OutlineOnlyStop,
        generate_multi_section_report,
    )
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        PG_EVALUATOR_MODEL, PG_GENERATOR_MODEL,
    )
    from src.polaris_graph.outline.outline_agent import (  # noqa: PLC0415
        outliner_agent_model, outliner_code_model,
    )

    dist = _tier_fractions(evidence)
    log.info("tier fractions: %s", {k: round(v, 3) for k, v in dist.items()})
    log.info("[gen] agent_model=%s code_model=%s generator=%s",
             outliner_agent_model(), outliner_code_model(), PG_GENERATOR_MODEL)

    # STEP 4 (UTILIZATION): thread the PSL government-suffix list so the credibility pass RUNS
    # priors-only (judge=None under always-release => ZERO LLM scoring calls) and BUILDS the per-claim
    # baskets. Without gov_suffixes the pre-run guard DEGRADES to credibility_analysis=None (the
    # 794->9 collapse), which strands EVERY basket and makes PG_ROUTE_ALL_BASKETS inert — the report
    # then renders only the LLM-writer's directly-cited sources. Faithfulness-neutral: priors weights
    # are deterministic authority weights; strict_verify / 4-role D8 / span-grounding stay the ONLY
    # binding gates. Fail-open: an empty/unavailable suffix list leaves the legacy None path.
    _gov_suffixes = None
    try:
        from src.polaris_graph.authority.data_loader import load_authority_data  # noqa: PLC0415
        _gov_suffixes = tuple(load_authority_data().get("psl_gov_suffixes") or ()) or None
        log.info("[credibility] threaded psl_gov_suffixes=%d (priors-only basket build enabled)",
                 len(_gov_suffixes or ()))
    except Exception as _e:  # noqa: BLE001
        log.warning("[credibility] could not load psl_gov_suffixes (%s); credibility pass will "
                    "degrade to None and PG_ROUTE_ALL_BASKETS will be inert", _e)

    t0 = time.time()
    try:
        multi = await generate_multi_section_report(
            research_question=rq,
            evidence=evidence,
            finding_clusters=clusters,
            same_work_groups=swg,
            section_temperature=0.3,
            outline_max_tokens=2500,
            section_max_tokens=2400,
            min_kept_fraction=0.4,
            max_parallel_sections=args.max_parallel,
            tier_fractions=dist,
            domain=domain,
            credibility_pass_gov_suffixes=_gov_suffixes,
            # Rank4: None when the judge is OFF => the pool seam passes () => off-topic arm inert.
            fresh_off_subject_ids=fresh_off_subject,
        )
    except OutlineOnlyStop as _stop:
        log.info("[outline-only] PG_STOP_AFTER_ROUTED_OUTLINE — stopped after routed-outline dump "
                 "(%d sections, %.1fs); skipped per-section compose.",
                 len(_stop.plans), time.time() - t0)
        return 0
    dt = time.time() - t0
    kept = [s for s in multi.sections if not s.dropped_due_to_failure]
    log.info("[gen] elapsed=%.1fs  outline=%d sections  kept=%d  words=%s  "
             "verified=%s  dropped=%s  in_tok=%s out_tok=%s",
             dt, len(multi.outline), len(kept), getattr(multi, "total_words", "?"),
             getattr(multi, "total_sentences_verified", "?"),
             getattr(multi, "total_sentences_dropped", "?"),
             getattr(multi, "total_input_tokens", "?"),
             getattr(multi, "total_output_tokens", "?"))
    for sr in multi.sections:
        mark = "OK " if not sr.dropped_due_to_failure else "DROP"
        log.info("   [%s] %-42s verified=%s dropped=%s regen=%s",
                 mark, sr.title[:42], sr.sentences_verified,
                 sr.sentences_dropped, sr.regen_attempted)

    # Persist the outline
    (run_dir / "multi_section_outline.json").write_text(
        json.dumps([{"title": p.title, "focus": p.focus, "ev_ids": p.ev_ids}
                    for p in multi.outline], indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    # Assemble the JUDGED report body from VERIFIED text only.
    #  - Section headings are the generator's OWN topic-driven titles (facet outline + skeleton):
    #    an Introduction, thematic bodies, a Cross-Study Synthesis & Contradictions section, and a
    #    Conclusions & Research Gaps section — no clinical archetypes, no relabel map.
    #  - A single GENERAL, topic-neutral framing sentence under the title (NO factual claims / no
    #    numbers — pure presentation). The report's substantive framing lives in the generated
    #    Introduction section; this line only states the organizing method. The tripwire re-audits.
    title = args.title or _derive_title(rq)
    intro = (
        "This report synthesizes the retrieved research evidence on the question above. It is "
        "organized as a coherent review: an introduction that frames the scope, thematic sections "
        "that group the evidence by sub-topic, a cross-study synthesis that surfaces where the "
        "findings agree and conflict, and a closing discussion of conclusions and open research "
        "gaps. Every quantitative claim is span-grounded to a cited source; claims that could not "
        "be verified against the underlying evidence were removed rather than paraphrased."
    )
    bodies: list[str] = []
    for sr in multi.sections:
        if sr.dropped_due_to_failure or not sr.verified_text:
            continue
        bodies.append(f"## {sr.title}\n\n{sr.verified_text}")
    sections_concat = "\n\n".join(bodies)
    if getattr(multi, "limitations_text", ""):
        sections_concat += f"\n\n## Limitations\n\n{multi.limitations_text}"

    biblio = getattr(multi, "bibliography", []) or []
    biblio_section = "\n\n## References\n"
    for b in biblio:
        biblio_section += (f"[{b.get('num')}] {str(b.get('statement',''))[:200]} — "
                           f"{b.get('url','')} (tier {b.get('tier','')})\n")

    final_report = (f"# {title}\n\n{intro}\n\n{sections_concat}{biblio_section}")
    (run_dir / "report.md").write_text(final_report, encoding="utf-8")

    # Pipeline telemetry / Methods is a SIDECAR artifact (provenance for us), NOT part of the judged
    # deliverable — a research report's reader does not want the generator's internal telemetry.
    tier_summary = ", ".join(f"{k}={v*100:.0f}%" for k, v in sorted(dist.items()))
    methods = (
        "# Methods / pipeline telemetry (sidecar — NOT part of the judged report.md)\n\n"
        f"Judged task: DRB task {args.rq_drb_task} (verbatim prompt).\n"
        f"Corpus RQ (provenance): {corpus_rq[:200]}...\n"
        f"Corpus: {corpus_path.name} ({len(evidence)} evidence rows, {len(clusters)} baskets; "
        f"domain={domain or 'general'}).\n"
        f"Outliner: AGENTIC (PG_OUTLINE_AGENT=1) — agent {outliner_agent_model()}, "
        f"code {outliner_code_model()}.\n"
        f"Generator: {PG_GENERATOR_MODEL} (multi-section: agentic outline + "
        f"{len(kept)} parallel verified sections + strict_verify + regen-on-failure).\n"
        f"Evaluator/mirror: {PG_EVALUATOR_MODEL}.\n"
        f"Tier distribution: {tier_summary}.\n"
    )
    # §-1.3.1: "Every deletion is DISCLOSED (deleted-row count + reason in Methods — fail loud,
    # never silent)." The chrome gate DELETES failed fetches (bot/captcha cards) from the
    # grounding pool, so the count + per-source reason MUST surface here, not just in a log line.
    _junk_disclosed = getattr(multi, "junk_disclosed", None) or []
    if _junk_disclosed:
        _by_reason: dict[str, int] = {}
        for _d in _junk_disclosed:
            _r = str(_d.get("deletion_reason") or _d.get("signal") or "unknown")
            _by_reason[_r] = _by_reason.get(_r, 0) + 1
        methods += (
            f"\n## Deleted sources (§-1.3.1 junk carve-out): {len(_junk_disclosed)}\n\n"
            "Chrome non-sources (bot/captcha/cookie/404/login pages) are FAILED FETCHES, not\n"
            "sources — they carry no claim, so they are deleted from the grounding pool rather\n"
            "than weighted. Credible on-topic sources are NEVER deleted, only weighted.\n\n"
            + "".join(f"- {_r}: {_n}\n" for _r, _n in sorted(_by_reason.items()))
            + "\nDeleted rows:\n"
            + "".join(
                f"- {_d.get('evidence_id')} [{_d.get('tier', '?')}] "
                f"{str(_d.get('title', ''))[:60]} — {_d.get('url', '')}\n"
                for _d in _junk_disclosed
            )
        )
    (run_dir / "methods.md").write_text(methods, encoding="utf-8")
    (run_dir / "bibliography.json").write_text(
        json.dumps(biblio, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # P0/proof: the agentic-outliner digest surfaced on MultiSectionResult — PROVE the deep render
    # stayed agentic (cp4_used='agentic'), NOT degraded-to-seed (mission metric-1).
    oa_stats = dict(getattr(multi, "outline_agent_stats", None) or {})
    cp4_used = str(oa_stats.get("cp4_used", "MISSING"))
    degraded_to_seed = bool(oa_stats.get("degraded_to_seed", False))
    degrade_reason = str(oa_stats.get("degrade_reason", ""))
    log.info("[agentic] cp4_used=%s degraded_to_seed=%s turns=%s degrade_reason=%r -> %s",
             cp4_used, degraded_to_seed, oa_stats.get("turns"), degrade_reason[:160],
             "AGENTIC" if cp4_used == "agentic" else "NOT-AGENTIC")

    audit = _audit_citations(final_report, biblio)
    faithful = (audit["leaked_cite_ev_tokens"] == 0 and not audit["unresolved_markers"])
    log.info("[faithfulness] leaked_[CITE:ev]=%d  bib_markers_in_prose=%d  bib_entries=%d  "
             "unresolved_markers=%s -> %s",
             audit["leaked_cite_ev_tokens"], audit["distinct_bib_markers_in_prose"],
             audit["bibliography_entries"], audit["unresolved_markers"],
             "PASS" if faithful else "FAIL")

    summary = {
        "corpus": corpus_path.name,
        "judged_drb_task": args.rq_drb_task or None,
        "composed_to_rq": rq[:160],
        "corpus_rq": corpus_rq[:160],
        "report_title": title,
        "section_headings": [s.title for s in multi.sections
                             if not s.dropped_due_to_failure and s.verified_text],
        "evidence_rows": len(evidence),
        "baskets": len(clusters),
        "same_work_groups": len(swg or []),
        "outline_sections": len(multi.outline),
        "kept_sections": len(kept),
        "dropped_sections": len(multi.sections) - len(kept),
        "total_words": getattr(multi, "total_words", None),
        "total_sentences_verified": getattr(multi, "total_sentences_verified", None),
        "total_sentences_dropped": getattr(multi, "total_sentences_dropped", None),
        # §-1.3.1 disclosure: chrome non-sources deleted from the grounding pool (never silent).
        "junk_deleted_rows": len(getattr(multi, "junk_disclosed", None) or []),
        "bibliography_entries": len(biblio),
        "report_chars": len(final_report),
        "report_words": len(final_report.split()),
        "faithfulness_audit": audit,
        "faithfulness_pass": faithful,
        "cp4_used": cp4_used,
        "degraded_to_seed": degraded_to_seed,
        "degrade_reason": degrade_reason[:200],
        "outline_agent_turns": oa_stats.get("turns"),
        "moat_quantified_models": len(getattr(multi, "quantified_models", None) or {}),
        "agent_model": outliner_agent_model(),
        "code_model": outliner_code_model(),
        "generator_model": PG_GENERATOR_MODEL,
        "elapsed_seconds": round(dt, 1),
        "out_dir": str(run_dir),
    }
    (run_dir / "compose_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log.info("WROTE %s (%d chars, %d words) + compose_summary.json",
             run_dir / "report.md", len(final_report), len(final_report.split()))
    print(json.dumps(summary, indent=2))
    return 0 if faithful else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
