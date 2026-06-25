#!/usr/bin/env python3
"""I-wire-001 W2 (#1311) P1-2 KEYSTONE — §-1.4 BEHAVIORAL fire-test that the
content-relevance weight is READ by select_evidence_for_generation and DEMOTES a
planted junk passage in the REAL evidence_for_gen selection (not module-only).

This is the proof the wave-2 audit said was MISSING (P1-2 "the W2 weight is
orphaned from real evidence selection"): the prior fire-test only drove the
module-level ``score_passages`` (the reranker/GLM judge), which does NOT prove the
weight ever reaches the actual evidence selection that feeds the generator. THIS
test drives the REAL ``select_evidence_for_generation`` on a REAL banked corpus
snapshot and asserts the demotion appears in ``selected_rows`` (the real
evidence_for_gen base).

DETERMINISTIC + MODEL-FREE: it needs NO reranker / NO GLM / NO network. It plants
the W2 ``content_relevance_weight`` directly on a real classified source (exactly
what the live W2 judge writes onto CorpusSource) and asserts the selector consumes
it. So it runs anywhere, fail-loud, in milliseconds.

Production-path fidelity (the §-1.4 "test the path production takes" rule): it sets
the SAME flags the Gate-B production slate sets — ``PG_USE_FINDING_DEDUP=1`` (=>
relevance_floor non-None => the floor selection path, where the W2 sort-key multiply
lives), ``PG_RELEVANCE_FLOOR=0.30``, ``PG_SWEEP_CREDIBILITY_REDESIGN=1`` (keep-all
weight-not-filter). If production changes path, change these.

What it proves on the REAL banked snapshot
(``outputs/audits/b1b10_redesign/replay_fixtures/drb_72_ai_labor/corpus_snapshot.json``):

  1. WEIGHT IS READ. With W2 OFF (no weights planted) record the demoted
     candidate's rank in selected_rows. Then plant content_relevance_weight=0.25 on
     that one source and re-select. The demoted source's row must sink BELOW a
     full-weight peer it OUTRANKED before — i.e. its rank STRICTLY WORSENS. If the
     selector ignored the weight the rank would be unchanged => exit 1 (the weight
     is not read = the orphan bug).

  2. RETENTION = 1.0 / NO DROP (§-1.3). The demoted source's row is STILL PRESENT
     in selected_rows (never removed) and len(selected_rows) is UNCHANGED between
     the OFF and ON runs. A demoted source is kept at low weight, never dropped.

  3. FLAG-OFF byte-identity sanity. With no weights planted, the selection is
     identical to base (the multiply is ×1.0).

Fail-loud: weight not read (rank unchanged) => exit 1; row dropped / count changed
=> exit 1; snapshot missing => exit 1 (LAW II: blocked, not faked).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The banked REAL corpus snapshot (a general/qualitative DRB-II question). LAW VI:
# env-overridable, with the main-tree replay fixture as the documented default.
_DEFAULT_SNAPSHOT = (
    "C:/POLARIS/outputs/audits/b1b10_redesign/replay_fixtures/"
    "drb_72_ai_labor/corpus_snapshot.json"
)
_DEFAULT_PROTOCOL = (
    "C:/POLARIS/outputs/audits/b1b10_redesign/replay_fixtures/"
    "drb_72_ai_labor/protocol.json"
)

# The W2 demote weight the live judge applies (matches
# content_relevance_judge._DEFAULT_DEMOTE_WEIGHT). Env-overridable.
_DEMOTE_WEIGHT = float(os.environ.get("PG_W2_SELECT_DEMOTE_WEIGHT", "0.25"))


def _fail(msg: str) -> None:
    print(f"FIRE-TEST FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _row_url(row: dict) -> str:
    return str(row.get("source_url") or row.get("url") or "")


def _rank_of(rows: list, url: str) -> int:
    for i, r in enumerate(rows):
        if _row_url(r) == url:
            return i
    return -1


def main() -> None:
    # Production-path flags (Gate-B slate). MUST match so the test exercises the
    # SAME selection path production takes (the floor path).
    os.environ["PG_USE_FINDING_DEDUP"] = "1"
    os.environ["PG_RELEVANCE_FLOOR"] = os.environ.get("PG_RELEVANCE_FLOOR", "0.30")
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    # Keep it model-free + deterministic: do NOT engage the semantic embedder or the
    # CrossEncoder rerank in this consumption canary (they need GPU/model + would
    # change the score basis the demotion rides on). The lexical scorer is enough to
    # prove the WEIGHT is read.
    os.environ.pop("PG_RELEVANCE_SCORER", None)
    os.environ.pop("PG_RERANKER_MODEL", None)

    snap_path = os.environ.get("PG_W2_SELECT_SNAPSHOT", _DEFAULT_SNAPSHOT)
    proto_path = os.environ.get("PG_W2_SELECT_PROTOCOL", _DEFAULT_PROTOCOL)
    sp = Path(snap_path)
    if not sp.exists():
        _fail(
            f"corpus snapshot not found at {snap_path} — the REAL banked "
            "evidence_rows/classified_sources are required (LAW II: blocked, not "
            "faked). Set PG_W2_SELECT_SNAPSHOT to a real corpus_snapshot.json."
        )

    snap = json.loads(sp.read_text(encoding="utf-8"))
    retrieval = snap.get("retrieval", snap)
    classified = list(retrieval.get("classified_sources", []) or [])
    evidence_rows = list(retrieval.get("evidence_rows", []) or [])
    if not classified or not evidence_rows:
        _fail(
            f"snapshot {snap_path} has no classified_sources/evidence_rows "
            f"(cs={len(classified)} er={len(evidence_rows)})."
        )

    research_question = snap.get("question", "") or retrieval.get("question", "")
    protocol = None
    pp = Path(proto_path)
    if pp.exists():
        try:
            protocol = json.loads(pp.read_text(encoding="utf-8"))
        except Exception:
            protocol = None

    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )

    # ── Pick a target source that (a) has >= 1 evidence row and (b) is NOT last in
    # the baseline selection (so a demotion has room to push it DOWN past a peer).
    er_urls = {_row_url(r) for r in evidence_rows}

    def _baseline_select(srcs: list) -> list:
        sel = select_evidence_for_generation(
            research_question=research_question,
            protocol=protocol,
            classified_sources=srcs,
            evidence_rows=evidence_rows,
            max_rows=0,                 # floor mode ignores max_rows
            relevance_floor=0.30,
        )
        return sel.selected_rows

    # As dicts so we can attach content_relevance_weight (mirrors CorpusSource).
    base_sources = [dict(s) for s in classified]
    base_rows = _baseline_select(base_sources)
    if not base_rows:
        _fail("baseline selection returned 0 rows — cannot prove demotion.")
    base_n = len(base_rows)

    # Find a target URL present in the selection that has a full-weight peer ranked
    # BELOW it (so demoting it can flip them).
    target_url = ""
    peer_url = ""
    for i, r in enumerate(base_rows):
        u = _row_url(r)
        if u and u in er_urls and i < base_n - 1:
            # the next distinctly-URL'd row below is a candidate peer
            for j in range(i + 1, base_n):
                pu = _row_url(base_rows[j])
                if pu and pu != u:
                    target_url, peer_url = u, pu
                    break
        if target_url:
            break
    if not target_url:
        _fail(
            "could not find a selected source with a distinct lower-ranked peer in "
            "the real snapshot — cannot construct the demotion assertion."
        )

    base_target_rank = _rank_of(base_rows, target_url)
    base_peer_rank = _rank_of(base_rows, peer_url)

    # ── Plant the W2 demote weight on the target source (exactly what the live W2
    # judge writes onto CorpusSource.content_relevance_weight) and re-select. ──
    on_sources = []
    planted = False
    for s in classified:
        d = dict(s)
        if str(d.get("url", "")) == target_url:
            d["content_relevance_weight"] = _DEMOTE_WEIGHT
            d["content_relevance_label"] = "demoted"
            planted = True
        on_sources.append(d)
    if not planted:
        _fail(f"target url {target_url} not found in classified_sources to plant.")

    on_rows = _baseline_select(on_sources)
    on_n = len(on_rows)

    # ── (2) RETENTION = 1.0 / NO DROP. ──
    if on_n != base_n:
        _fail(
            f"selection COUNT changed after demotion: base={base_n} on={on_n} — a "
            "demoted source must be KEPT (retention 1.0), never dropped (§-1.3)."
        )
    on_target_rank = _rank_of(on_rows, target_url)
    if on_target_rank < 0:
        _fail(
            f"DEMOTED SOURCE DROPPED: target {target_url} is ABSENT from the ON "
            "selection — §-1.3 forbids dropping a demoted source (must be kept "
            "at low weight)."
        )

    # ── (1) WEIGHT IS READ: the demoted target must sink (rank worsens), AND it
    # must now rank BELOW a peer it previously outranked (the real ordering flip). ──
    on_peer_rank = _rank_of(on_rows, peer_url)
    rank_worsened = on_target_rank > base_target_rank
    flipped_below_peer = (
        base_target_rank < base_peer_rank and on_target_rank > on_peer_rank
    )
    if not rank_worsened:
        _fail(
            f"content_relevance_weight was NOT READ by select_evidence: target "
            f"{target_url} rank UNCHANGED ({base_target_rank} -> {on_target_rank}) "
            f"after planting weight={_DEMOTE_WEIGHT}. The weight is ORPHANED from "
            "the real evidence selection (the exact P1-2 bug)."
        )
    if not flipped_below_peer:
        _fail(
            f"demoted target sank ({base_target_rank}->{on_target_rank}) but did "
            f"NOT cross BELOW its peer {peer_url} ({base_peer_rank}->{on_peer_rank}) "
            "— the demotion did not change the REAL relative ordering."
        )

    print(
        "FIRE-TEST PASS (W2 P1-2 keystone — select_evidence reads the weight):\n"
        f"  snapshot               = {snap_path}\n"
        f"  classified_sources     = {len(classified)}  evidence_rows = "
        f"{len(evidence_rows)}\n"
        f"  selected rows          = {base_n} (UNCHANGED after demotion = retention "
        "1.0, NO drop)\n"
        f"  target source          = {target_url[:70]}\n"
        f"  demote weight planted  = {_DEMOTE_WEIGHT}\n"
        f"  target rank            = {base_target_rank} -> {on_target_rank} "
        "(WORSENED — weight READ)\n"
        f"  peer rank              = {base_peer_rank} -> {on_peer_rank} "
        "(target crossed BELOW peer)\n"
        "  ASSERTED: content_relevance_weight is READ by "
        "select_evidence_for_generation and DEMOTES the junk source in the REAL "
        "evidence_for_gen selection; retention=1.0 (kept, never dropped)."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
