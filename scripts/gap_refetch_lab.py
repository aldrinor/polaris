#!/usr/bin/env python3
"""S-X thin-section re-fetch lab — the fast isolation hamster for the gap-refetch ENGINE.

I-arch-plan ruling R10 / doc-00 R8 / Design 5 ORCH-4. This owns the S-X ``gap`` loop as a standalone
file; it FOLDS INTO ``scripts/orchestrator_lab/outline_lab.py``'s ``gap`` mode once WP-3a lands that
file (kept separate now to avoid a parallel-campaign merge collision — the plan says outline_lab.py
"gains a gap mode", built by WP-3a).

Two modes:

  * ``replay`` (default, OFFLINE, no network, no spend): drive ``run_gap_refetch`` on a REPLAY lane
    whose per-query results come from a bank file (``--replay-json``) or a built-in fixture, then
    print — LINE BY LINE for the forensic read (memory 2026-07-01) — the queries issued, per-query
    row counts, the merged delta ids, the fold result, and the DATA-ONLY ``gap_refetch.json``. This
    is the offline contract demo; the unit test ``tests/polaris_graph/test_gap_refetch.py`` is the
    machine gate.

  * ``live`` (VM hamster, network + spend): bind the REAL production per-query lane
    (``run_live_retrieval`` anchor-suppressed, exactly the seam ``_run_gap_round`` uses) and fire a
    real gap set against a banked run's scope. This is the later VM hamster the master plan schedules
    (WAVE-5 activation); it is NOT run locally (heavy retriever import is lazy, inside --live only).

Usage:
    python scripts/gap_refetch_lab.py                              # offline fixture demo
    python scripts/gap_refetch_lab.py --replay-json bank.json --budget 4 --out-dir /tmp/gaplab
    python scripts/gap_refetch_lab.py --live --bank <run_dir> --gap-queries "q1;q2" --budget 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# Repo root on sys.path so `from src.polaris_graph...` resolves when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.retrieval.gap_refetch import (  # noqa: E402
    fold_gap_delta,
    run_gap_refetch,
)


def _fixture_rows_by_query() -> dict[str, list[dict]]:
    """A tiny built-in fixture: two thin-section gap queries, each finding one new source that
    RESTARTS at ev_000 (mirroring a real per-query run_live_retrieval)."""
    return {
        "long-term cardiovascular outcomes tirzepatide elderly": [
            {"evidence_id": "ev_000", "source_url": "https://example.org/cv-elderly",
             "direct_quote": "tirzepatide reduced MACE by 12% in adults over 65 at 96 weeks"},
        ],
        "tirzepatide renal endpoints CKD subgroup": [
            {"evidence_id": "ev_000", "source_url": "https://example.org/renal-ckd",
             "direct_quote": "eGFR decline slowed by 1.1 mL/min/yr in the CKD subgroup"},
        ],
    }


def _replay_lane(rows_by_query: dict[str, list[dict]]):
    """An offline per_query_retrieve: returns the bank/fixture rows for each query, no network."""

    def _lane(*, research_question: str, **_kw):
        rows = rows_by_query.get(research_question, [])
        return SimpleNamespace(evidence_rows=[dict(r) for r in rows])

    return _lane


def _replay_factory(**kwargs):
    """Stand-in for LiveRetrievalResult in the offline lab (merge builds one via kwargs)."""
    return SimpleNamespace(**kwargs)


def _print_outcome(outcome, existing_pool: list[dict]) -> None:
    line = "-" * 78
    print(line)
    print(f"[gap_refetch] active={outcome.active}  budget={outcome.budget}  "
          f"wall_hit={outcome.wall_hit}  rows_added={outcome.rows_added}")
    print(f"[gap_refetch] queries_requested ({len(outcome.queries_requested)}):")
    for q in outcome.queries_requested:
        print(f"    - {q}")
    print(f"[gap_refetch] queries_issued ({len(outcome.queries_issued)}):")
    for q in outcome.queries_issued:
        print(f"    * {q}")
    if outcome.delta_result is not None:
        print("[gap_refetch] delta rows (DELTA-LOCAL ev_ids — renumbered on fold):")
        for r in (getattr(outcome.delta_result, "evidence_rows", None) or []):
            print(f"    {r.get('evidence_id')} | {r.get('source_url')} | "
                  f"{str(r.get('direct_quote'))[:70]}")
    if outcome.checkpoint_path is not None:
        print(f"[gap_refetch] checkpoint: {outcome.checkpoint_path}")
    # The S3-delta fold: renumber the delta against the existing pool + source-URL dedup.
    delta_rows = (getattr(outcome.delta_result, "evidence_rows", None) or []) if outcome.delta_result else []
    fold = fold_gap_delta(existing_pool, delta_rows)
    print(f"[gap_refetch] fold into pool of {len(existing_pool)}: +{fold.added} rows; "
          f"id_remap={fold.id_remap}")
    print(line)


def _run_replay(args) -> int:
    if args.replay_json:
        rows_by_query = json.loads(Path(args.replay_json).read_text(encoding="utf-8"))
    else:
        rows_by_query = _fixture_rows_by_query()
    queries = list(rows_by_query.keys()) if not args.gap_queries else _split_queries(args.gap_queries)
    existing_pool = [
        {"evidence_id": f"ev_{i:03d}", "source_url": f"https://pool.example/{i}"}
        for i in range(args.pool_size)
    ]
    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    outcome = run_gap_refetch(
        gap_queries=queries,
        per_query_retrieve=_replay_lane(rows_by_query),
        result_factory=_replay_factory,
        budget=args.budget,
        run_dir=out_dir,
        section_titles=_split_queries(args.section_titles) if args.section_titles else None,
        log=lambda m: print(m),
    )
    _print_outcome(outcome, existing_pool)
    return 0


def _run_live(args) -> int:  # pragma: no cover — VM hamster path (network + spend), not offline
    if not args.bank or not args.gap_queries:
        print("[gap_refetch][live] --bank <run_dir> and --gap-queries are required", file=sys.stderr)
        return 2
    # Lazy heavy import — kept OUT of the offline path so `replay` never loads the retriever.
    from src.polaris_graph.retrieval.live_retriever import run_live_retrieval
    from src.polaris_graph.retrieval.fs_researcher_query_gen import merge_retrieval_results

    bank = Path(args.bank)
    # A minimal LiveRetrievalResult factory bound to the real class is out of this lab's scope; the
    # real VM hamster reuses the sweep's `_IterLRR` factory + the `_iter_per_query_retrieve` closure.
    # Here we surface the exact call shape so the VM operator can wire it against the banked scope.
    print(f"[gap_refetch][live] would fire {len(_split_queries(args.gap_queries))} gap queries "
          f"through run_live_retrieval (anchor_seed=False) against bank {bank} — "
          "wire via run_honest_sweep_r3._iter_per_query_retrieve + _IterLRR on the VM.")
    _ = (run_live_retrieval, merge_retrieval_results)  # referenced so the import is not dead
    return 0


def _split_queries(raw: str) -> list[str]:
    return [q.strip() for q in raw.split(";") if q.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S-X thin-section re-fetch lab")
    ap.add_argument("--mode", choices=["replay", "live"], default="replay")
    ap.add_argument("--live", action="store_true", help="alias for --mode live")
    ap.add_argument("--replay-json", help="JSON {query: [rows]} bank for offline replay")
    ap.add_argument("--gap-queries", help="';'-separated gap queries (overrides bank keys)")
    ap.add_argument("--section-titles", help="';'-separated triggering section titles")
    ap.add_argument("--budget", type=int, default=4, help="max gap queries to issue (spend cap)")
    ap.add_argument("--pool-size", type=int, default=3, help="offline existing-pool size for fold demo")
    ap.add_argument("--out-dir", help="write gap_refetch.json here (offline)")
    ap.add_argument("--bank", help="banked run dir (live mode)")
    args = ap.parse_args(argv)
    if args.live:
        args.mode = "live"
    return _run_live(args) if args.mode == "live" else _run_replay(args)


if __name__ == "__main__":
    raise SystemExit(main())
