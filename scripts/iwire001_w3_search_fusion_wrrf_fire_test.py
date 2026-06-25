#!/usr/bin/env python3
"""I-wire-001 W3 — §-1.4 BEHAVIORAL fire-test for search-fusion WRRF.

FAIL-LOUD canary (non-zero exit if the effect did not fire). Acceptance per the
operator §-1.4 mandate: the winner's effect must APPEAR in the real retrieval
ORDERING produced by the live merge on REAL banked upstream data — NOT a
hand-picked snapshot chosen to make the effect fire.

What it proves on the banked fusion gold
(``tests/fixtures/upstream_golds/search_fusion_source_recall_gold.jsonl``, 25 q
of real per-engine ranked lists with planted split-relevance — a high-authority
source one engine buries below marketing/junk):

  1. flag-OFF  -> the legacy inline-dedup merge (first-seen-across-engines order)
                 is reproduced. The candidate ORDER is the byte-identical legacy
                 concatenation order. Used as the WRRF baseline to diff against.

  2. flag-ON   -> WRRF fuses on the per-engine RANKS. On >=1 discriminating row
                 the fused top-k ORDER DIFFERS from the OFF order, AND a buried
                 high-authority gold source (e.g. NEJM/Lancet ranked low by one
                 engine) is LIFTED above marketing/junk it sat below in the OFF
                 order, AND source-recall@k of the gold_relevant_urls is >= the
                 OFF order's recall@k (fusion never loses a gold source — §-1.3
                 fusion re-orders, never drops).

  Fail-loud: WRRF order == OFF order on ALL rows (effect did not fire) => exit 1.
             Any gold source PRESENT in the OFF union but MISSING from the WRRF
             union (a source was dropped) => exit 1.

Real-data / LAW VI:
  * The gold path is env-overridable (PG_W3_FIRE_TEST_GOLD); the default points
    at the banked real gold in the main tree.
  * recall@k cutoff is env-overridable (PG_W3_FIRE_TEST_TOPK, default 10).
  * No network, no LLM — WRRF is deterministic rank arithmetic, so the canary is
    a few milliseconds and fully reproducible.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The banked gold lives in tests/fixtures/upstream_golds/ on the main tree (it
# was added after the worktree base commit). LAW VI: env-overridable, with the
# main-tree path as the documented default so the canary runs on REAL data.
_DEFAULT_GOLD = (
    "C:/POLARIS/tests/fixtures/upstream_golds/search_fusion_source_recall_gold.jsonl"
)


def _fail(msg: str) -> None:
    print(f"FIRE-TEST FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


class _Cand:
    """Minimal candidate exposing .url (what wrrf_fuse reads)."""

    __slots__ = ("url",)

    def __init__(self, url: str) -> None:
        self.url = url


def _off_order(engine_lists: dict) -> list[str]:
    """Reproduce the legacy inline-dedup order: engines processed in their dict
    order, first-seen URL wins, rank position discarded. This is exactly what
    `_emit_candidate` does on the OFF path (seen_urls dedup, append order)."""
    seen: set[str] = set()
    order: list[str] = []
    for _engine, hits in engine_lists.items():
        for hit in hits:
            u = hit.get("url", "")
            if not u or u in seen:
                continue
            seen.add(u)
            order.append(u)
    return order


def main() -> None:
    gold_path = os.environ.get("PG_W3_FIRE_TEST_GOLD", _DEFAULT_GOLD)
    try:
        topk = max(1, int(os.environ.get("PG_W3_FIRE_TEST_TOPK", "10")))
    except ValueError:
        topk = 10

    gp = Path(gold_path)
    if not gp.exists():
        _fail(
            f"fusion gold not found at {gold_path} — the REAL banked per-engine "
            "ranked lists are required (LAW II: blocked, not faked)."
        )

    from src.polaris_graph.retrieval.search_fusion_wrrf import wrrf_fuse

    rows = [
        json.loads(line)
        for line in gp.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        _fail(f"fusion gold {gold_path} is empty")

    n_order_changed = 0
    n_authority_lifted = 0
    rows_with_lift_evidence = 0
    recall_off_total = 0
    recall_on_total = 0

    for row in rows:
        engine_lists = row.get("engine_lists", {})
        gold_urls = set(row.get("gold_relevant_urls", []) or [])
        if not engine_lists:
            continue

        # OFF order (legacy inline-dedup).
        off = _off_order(engine_lists)
        off_pos = {u: i for i, u in enumerate(off)}

        # ON order (WRRF fuse on the per-engine ranks).
        per_engine = {
            eng: [_Cand(h.get("url", "")) for h in hits if h.get("url")]
            for eng, hits in engine_lists.items()
        }
        result = wrrf_fuse(per_engine)
        on = [c.url for c in result.fused]
        on_pos = {u: i for i, u in enumerate(on)}

        # No-drop invariant: every URL in the OFF union must survive WRRF.
        off_set, on_set = set(off), set(on)
        dropped = off_set - on_set
        if dropped:
            _fail(
                f"row {row.get('id')}: WRRF DROPPED {len(dropped)} source(s) "
                f"present in the OFF union (e.g. {sorted(dropped)[:2]}) — §-1.3 "
                "fusion must never drop a source."
            )

        if off != on:
            n_order_changed += 1

        # Authority-lift evidence: a gold source that the OFF order ranks BELOW
        # at least one non-gold (junk/marketing) URL, but WRRF ranks ABOVE it.
        non_gold = [u for u in off_set if u not in gold_urls]
        row_has_lift = False
        for g in gold_urls:
            if g not in on_pos or g not in off_pos:
                continue
            for j in non_gold:
                if j not in on_pos or j not in off_pos:
                    continue
                buried_off = off_pos[g] > off_pos[j]      # gold below junk OFF
                lifted_on = on_pos[g] < on_pos[j]         # gold above junk ON
                if buried_off and lifted_on:
                    n_authority_lifted += 1
                    row_has_lift = True
        if row_has_lift:
            rows_with_lift_evidence += 1

        # recall@k of the gold sources (fusion must not lose recall).
        recall_off_total += sum(1 for g in gold_urls if off_pos.get(g, 1e9) < topk)
        recall_on_total += sum(1 for g in gold_urls if on_pos.get(g, 1e9) < topk)

    # ── Fail-loud assertions ──────────────────────────────────────────
    if n_order_changed == 0:
        _fail(
            "WRRF produced the SAME order as the legacy inline-dedup on EVERY "
            f"row ({len(rows)} rows) — the effect did NOT fire. The flag is a "
            "no-op on real data."
        )
    if rows_with_lift_evidence == 0:
        _fail(
            "WRRF changed order but NO buried high-authority gold source was "
            "lifted above a junk/marketing URL it sat below — the documented "
            "win did not appear in the ordering."
        )
    if recall_on_total < recall_off_total:
        _fail(
            f"WRRF recall@{topk} ({recall_on_total}) < legacy recall@{topk} "
            f"({recall_off_total}) — fusion LOST gold sources from the top-k."
        )

    # ── Parallel backend fan-out: set-identity + determinism vs serial ──
    # The gold has no live backends, so exercise the bounded-parallel reassembly
    # with deterministic stub backends. The parallel ON path must produce the
    # SAME candidate SET as the serial OFF path (no add/drop) AND a deterministic
    # declared-order reassembly (standard point 15), so tied WRRF scores never
    # reorder run-to-run.
    from src.polaris_graph.retrieval.domain_backends import (
        _run_backends_parallel,
    )
    from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
        SearchCandidate as _SC,
    )

    def _stub(tag: str, urls: list[str]):
        def _fn(_q: str, limit: int = 10):
            return [_SC(url=u, title="", snippet="", source=tag) for u in urls[:limit]]
        return _fn

    _specs = [
        ("arxiv", _stub("arxiv", ["https://arxiv.org/a", "https://shared.example/x"])),
        ("github", _stub("github", ["https://github.com/g", "https://shared.example/x"])),
        ("europe_pmc", _stub("europe_pmc", ["https://europepmc.org/e"])),
    ]
    # I-wire-001 W3 (#1310) P1-3: _run_backends_parallel now returns a 4-tuple —
    # (candidates, used, per, per_engine_lists). The flat `candidates` keeps its
    # legacy cross-deduped semantics (assertions below); `per_engine_lists` carries
    # the REAL per-engine ranked lists (pre-cross-dedup) that must reach wrrf_fuse.
    _runs = [
        _run_backends_parallel(
            _specs, ["q"], 10, early_break=True, log_prefix="firetest",
        )
        for _ in range(3)
    ]
    _orders = [[c.url for c in cands] for cands, _u, _p, _pe in _runs]
    if not all(o == _orders[0] for o in _orders):
        _fail(
            f"parallel backend fan-out is NON-deterministic across runs: {_orders} "
            "— declared-order reassembly is required (standard point 15)."
        )
    # Set-identity vs serial first-seen order (shared URL deduped once) — the flat
    # legacy list still cross-dedups, this stays TRUE.
    _expected_set = {"https://arxiv.org/a", "https://shared.example/x",
                     "https://github.com/g", "https://europepmc.org/e"}
    if set(_orders[0]) != _expected_set:
        _fail(
            f"parallel backend fan-out SET {set(_orders[0])} != serial SET "
            f"{_expected_set} — fan-out must add/drop no source."
        )
    # The cross-backend duplicate must be credited to the FIRST declared backend
    # (arxiv) in the FLAT list, exactly like the serial first-seen-wins dedup.
    if _orders[0].index("https://shared.example/x") != 1:
        _fail(
            "parallel fan-out did not credit the shared URL to the first declared "
            "backend (serial first-seen-wins semantics broken)."
        )

    # ── P1-3 PROOF: per-engine ranks SURVIVE to wrrf_fuse (the audit's fix). ──
    # A URL returned by TWO backends (shared.example/x: rank-2 in arxiv, rank-2 in
    # github) must survive in BOTH per-engine lists — the prior code cross-deduped
    # FIRST, so the shared URL appeared in ONLY the first backend's list before the
    # fuser, collapsing its second per-engine rank. Assert it is in both lists with
    # its real rank, then prove wrrf_fuse SEES both contributions.
    _cands0, _used0, _per0, _per_engine0 = _runs[0]
    _SHARED = "https://shared.example/x"
    _arxiv_list = _per_engine0.get("arxiv", [])
    _github_list = _per_engine0.get("github", [])
    _arxiv_urls = [c.url for c in _arxiv_list]
    _github_urls = [c.url for c in _github_list]
    if _SHARED not in _arxiv_urls:
        _fail(
            "P1-3 BROKEN: shared URL missing from the arxiv per-engine list "
            f"{_arxiv_urls} — per-engine rank did not survive _run_backends_parallel."
        )
    if _SHARED not in _github_urls:
        _fail(
            "P1-3 BROKEN: shared URL was CROSS-DEDUPED out of the github per-engine "
            f"list {_github_urls} — the second backend's duplicate rank was lost "
            "BEFORE wrrf_fuse (the exact P1-3 bug). per_engine_lists must keep it."
        )
    _arxiv_rank = _arxiv_urls.index(_SHARED) + 1   # 1-based
    _github_rank = _github_urls.index(_SHARED) + 1
    # Feed the REAL per-engine lists into wrrf_fuse and prove the shared URL's
    # fused score reflects BOTH engines' ranks (sum of two contributions), not one.
    from src.polaris_graph.retrieval.search_fusion_wrrf import wrrf_fuse as _wf
    _fused = _wf(_per_engine0)
    _shared_score = _fused.scores.get(_SHARED, 0.0)
    # Single-engine score (only arxiv's contribution) for comparison.
    _solo = _wf({"arxiv": _arxiv_list})
    _solo_score = _solo.scores.get(_SHARED, 0.0)
    if not (_shared_score > _solo_score):
        _fail(
            "P1-3 BROKEN: wrrf_fuse fused the shared URL on ONE engine's rank only "
            f"(both-engines score {_shared_score:.6f} not > arxiv-only "
            f"{_solo_score:.6f}) — the second per-engine rank never reached the "
            "fuser."
        )

    # ── P1-3 weight-lookup: a configured PG_SEARCH_FUSION_WRRF_WEIGHTS entry keyed
    # by the BARE backend name (e.g. arxiv:5.0) must match a NAMESPACED engine
    # (domain:arxiv / need:arxiv) — else the academic backends the weights exist
    # FOR silently get the default weight (the namespacing-vs-weights gap). ──
    _w_default = _wf({"domain:arxiv": _arxiv_list})
    _w_boosted = _wf({"domain:arxiv": _arxiv_list}, weights={"arxiv": 5.0})
    _a0 = _arxiv_list[0].url
    if not (_w_boosted.scores.get(_a0, 0.0) > _w_default.scores.get(_a0, 0.0)):
        _fail(
            "P1-3 weight-lookup BROKEN: a bare-name weight (arxiv:5.0) did NOT apply "
            "to the namespaced engine 'domain:arxiv' — configured per-engine weights "
            "for academic backends are silently ignored."
        )

    print(
        "FIRE-TEST PASS (W3 search-fusion WRRF):\n"
        f"  parallel backend fan-out  = deterministic across 3 runs, "
        f"set-identical to serial (order={_orders[0]})\n"
        f"  P1-3 per-engine ranks    = shared URL kept in BOTH lists "
        f"(arxiv rank {_arxiv_rank}, github rank {_github_rank}); wrrf_fuse "
        f"score both={_shared_score:.6f} > arxiv-only {_solo_score:.6f} "
        "(both per-engine ranks reached the fuser)\n"
        f"  rows                          = {len(rows)}\n"
        f"  rows where fused ORDER changed = {n_order_changed}\n"
        f"  rows with authority-LIFT       = {rows_with_lift_evidence}\n"
        f"  total authority-lift events    = {n_authority_lifted}\n"
        f"  gold recall@{topk}  OFF={recall_off_total}  ON={recall_on_total} "
        f"(ON >= OFF: {recall_on_total >= recall_off_total})\n"
        "  ASSERTED: a buried high-authority source ranks ABOVE junk after WRRF "
        "(effect appears in the real retrieval ordering); NO source dropped."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
