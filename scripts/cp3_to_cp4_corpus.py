#!/usr/bin/env python3
"""Deterministic OFFLINE converter: cp3 stage snapshot -> sweep-runtime cp4 corpus.

The FULL-corpus cp4_used=agentic sweep (``scripts/outline_agentic_sweep.py``) loads a corpus in
the runtime schema:

    {"research_question": str,
     "evidence": [ {evidence_id, tier, title, statement, source_url, ...}, ... ],
     "finding_clusters": [ {representative_index, member_indices, corroboration_count,
                            member_hosts, claim_group_id}, ... ],   # indices INTO ``evidence``
     "same_work_groups": [ {member_evidence_ids, canonical_index, same_work_id}, ... ],
     "domain": str, "basket_total": int}

The canonical cp3 snapshot (``data/cp3_s3gear_329basket_snapshot.json``) instead stores baskets by
``member_evidence_ids`` (resolved evidence ids, NOT positional indices) and carries no evidence pool
of its own — the pool lives one stage upstream in the cp2 corpus snapshot's ``evidence_for_gen``
(996 rows) + ``retrieval.evidence_rows`` (the ONE referenced id, ``ev_621``, that the "for-gen"
pool demoted lives only here). This converter joins the two, deterministically, and:

  * maps ``question`` -> ``research_question``;
  * rebuilds ``finding_clusters`` from ``payload.baskets`` — ``member_evidence_ids`` ->
    positional ``member_indices`` into the attached pool, ``representative_evidence_id`` ->
    ``representative_index``; carries ``corroboration_count`` / ``member_hosts`` / ``claim_group_id``;
  * attaches the full evidence pool (evidence_for_gen order, then any referenced id only present in
    retrieval appended at the tail — deterministic, worker-independent);
  * passes ``same_work_groups`` through untouched (they are keyed by ``member_evidence_ids`` and are
    consumed by ``_build_alias_map`` via Mapping access, so no index rewrite is needed);
  * FAILS CLOSED: every ``member_evidence_id`` referenced by any basket OR same-work group MUST
    resolve in the attached pool, else the converter raises (a silent partial corpus is forbidden).

Durability: the supplemented evidence pool is snapshotted to
``data/cp2_evidence_pool_snapshot.json`` so a later run does not depend on the external
``/workspace/POLARIS/...`` path staying mounted; if the external cp2 snapshot is gone, the converter
rebuilds the corpus from that durable pool snapshot.

Usage:
    python scripts/cp3_to_cp4_corpus.py                 # defaults below
    python scripts/cp3_to_cp4_corpus.py --cp3 <f> --cp2 <f> --out <f>

Exit codes: 0 = wrote a fully-resolved corpus; 1 = a referenced id did not resolve (fail-closed).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_DEFAULT_CP3 = ROOT / "data" / "cp3_s3gear_329basket_snapshot.json"
_DEFAULT_CP2 = Path("/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json")
_DEFAULT_POOL_SNAPSHOT = ROOT / "data" / "cp2_evidence_pool_snapshot.json"
_DEFAULT_OUT = ROOT / "data" / "cp4_corpus_s3gear_329.json"


def referenced_evidence_ids(cp3: dict) -> set[str]:
    """Every evidence id the cp3 payload references — via baskets AND same-work groups.

    ALL of these must resolve in the attached pool (fail-closed), because both the basket digest
    (member_indices) and the same-work alias fold (member_evidence_ids) read them downstream.
    """
    payload = cp3["payload"]
    ref: set[str] = set()
    for b in payload["baskets"]:
        ref.update(str(e) for e in b.get("member_evidence_ids") or [])
        rep = b.get("representative_evidence_id")
        if rep:
            ref.add(str(rep))
    for g in payload.get("same_work_groups") or []:
        ref.update(str(e) for e in g.get("member_evidence_ids") or [])
    return ref


def build_pool(cp2: dict, referenced: set[str]) -> tuple[list[dict], list[str]]:
    """Build the deterministic evidence pool from a cp2 corpus snapshot.

    Pool = ``evidence_for_gen`` in its native order (the canonical for-generation pool), then any
    ``referenced`` id NOT present there appended from ``retrieval.evidence_rows`` (first occurrence,
    scanned in row order — deterministic). Returns (pool, still_missing).
    """
    efg = cp2.get("evidence_for_gen") or []
    pool: list[dict] = [dict(r) for r in efg if isinstance(r, dict) and r.get("evidence_id")]
    have = {str(r["evidence_id"]) for r in pool}

    # supplement referenced ids the for-gen pool demoted, from the wider retrieval pool
    rows = (cp2.get("retrieval") or {}).get("evidence_rows") or []
    ret_by_id: dict[str, dict] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("evidence_id"):
            ret_by_id.setdefault(str(r["evidence_id"]), dict(r))
    for eid in sorted(referenced - have):
        if eid in ret_by_id:
            pool.append(ret_by_id[eid])
            have.add(eid)

    still_missing = sorted(referenced - have)
    return pool, still_missing


def build_cp4_corpus(cp3: dict, pool: list[dict]) -> dict:
    """Join cp3 baskets to the attached pool into the sweep-runtime corpus. FAILS CLOSED."""
    payload = cp3["payload"]
    baskets = payload["baskets"]

    id2idx: dict[str, int] = {}
    for i, rec in enumerate(pool):
        id2idx.setdefault(str(rec["evidence_id"]), i)

    referenced = referenced_evidence_ids(cp3)
    missing = sorted(r for r in referenced if r not in id2idx)
    if missing:
        raise ValueError(
            f"{len(missing)} referenced member_evidence_ids do not resolve in the attached pool "
            f"(fail-closed; refusing to write a partial corpus): {missing[:10]}"
            + (" ..." if len(missing) > 10 else "")
        )

    clusters: list[dict] = []
    for b in baskets:
        member_ids = [str(e) for e in b.get("member_evidence_ids") or []]
        member_indices = [id2idx[e] for e in member_ids]
        rep_id = str(b.get("representative_evidence_id") or (member_ids[0] if member_ids else ""))
        clusters.append({
            "representative_index": id2idx[rep_id],
            "member_indices": member_indices,
            "corroboration_count": int(b.get("corroboration_count", len(member_indices))),
            "member_hosts": list(b.get("member_hosts") or []),
            "claim_group_id": b.get("claim_group_id"),
        })

    corpus = {
        "research_question": cp3["question"],
        "domain": cp3.get("domain", ""),
        "evidence": pool,
        "finding_clusters": clusters,
        "same_work_groups": payload.get("same_work_groups") or [],
        "basket_total": len(clusters),
        "_provenance": {
            "converter": "scripts/cp3_to_cp4_corpus.py",
            "cp3_run_id": cp3.get("run_id"),
            "cp3_stage": cp3.get("stage"),
            "pool_size": len(pool),
            "referenced_ids": len(referenced),
            "created_utc": datetime.now(timezone.utc).isoformat(),
        },
    }
    return corpus


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def convert(
    cp3_path: Path = _DEFAULT_CP3,
    cp2_path: Path = _DEFAULT_CP2,
    out_path: Path = _DEFAULT_OUT,
    pool_snapshot_path: Path = _DEFAULT_POOL_SNAPSHOT,
) -> dict:
    """End-to-end: load, build pool (with durability snapshot/fallback), join, write, return corpus."""
    cp3 = _load_json(cp3_path)
    referenced = referenced_evidence_ids(cp3)

    cp2_path = Path(cp2_path)
    pool_snapshot_path = Path(pool_snapshot_path)
    if cp2_path.exists():
        cp2 = _load_json(cp2_path)
        pool, missing = build_pool(cp2, referenced)
        if missing:
            raise ValueError(
                f"cp2 snapshot {cp2_path} is missing {len(missing)} referenced ids "
                f"(cannot fail-closed on a partial pool): {missing[:10]}"
            )
        # snapshot the supplemented pool for durability (external cp2 path may vanish)
        pool_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        pool_snapshot_path.write_text(json.dumps({
            "source_cp2": str(cp2_path),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "referenced_ids": len(referenced),
            "evidence_pool": pool,
        }, indent=1))
    elif pool_snapshot_path.exists():
        snap = _load_json(pool_snapshot_path)
        pool = snap["evidence_pool"]
        print(f"[cp3_to_cp4] external cp2 {cp2_path} absent — using durable pool snapshot "
              f"{pool_snapshot_path} ({len(pool)} rows)")
    else:
        raise FileNotFoundError(
            f"neither the external cp2 snapshot ({cp2_path}) nor the durable pool snapshot "
            f"({pool_snapshot_path}) exists — cannot build the evidence pool"
        )

    corpus = build_cp4_corpus(cp3, pool)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(corpus, indent=1))
    return corpus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cp3", type=Path, default=_DEFAULT_CP3)
    ap.add_argument("--cp2", type=Path, default=_DEFAULT_CP2)
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--pool-snapshot", type=Path, default=_DEFAULT_POOL_SNAPSHOT)
    args = ap.parse_args(argv)

    try:
        corpus = convert(args.cp3, args.cp2, args.out, args.pool_snapshot)
    except (ValueError, FileNotFoundError) as exc:
        print(f"FAIL-CLOSED: {exc}")
        return 1

    prov = corpus["_provenance"]
    print(f"WROTE {args.out}")
    print(f"  research_question : {corpus['research_question'][:80]}...")
    print(f"  domain            : {corpus['domain']}")
    print(f"  pool_size         : {prov['pool_size']}")
    print(f"  referenced_ids    : {prov['referenced_ids']} (all resolved)")
    print(f"  basket_total      : {corpus['basket_total']}")
    print(f"  same_work_groups  : {len(corpus['same_work_groups'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
