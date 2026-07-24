"""Oracle Layer 2 (retrieval seam): freeze ``run_live_retrieval`` so the acceptance harness is
BROWSER-FREE and deterministic.

Monkeypatches ``src.polaris_graph.retrieval.live_retriever.run_live_retrieval`` (the single seam
every retrieval — the harness bootstrap AND the agent's ``search_more_evidence`` tool — funnels
through) to route through a :class:`~tests.oracle.cassette.Cassette`:
  * ``mode="record"`` — call the REAL retriever (uses the network ONCE at seed-creation time),
    freeze the behaviour-relevant, JSON-native slice of the result, and store it;
  * ``mode="replay"`` — reconstruct a ``LiveRetrievalResult`` from the frozen slice with NO network
    call (no Serper, no fetch, no browser).

Request identity = the deterministic retrieval call arguments that actually steer the result
(research_question + amplified_queries + domain + anchor_seed + the caps). The wall-clock-derived
``retrieval_deadline_monotonic`` is DELIBERATELY excluded from the key — it is a timing input, not a
behaviour selector, and would otherwise make every record/replay key differ. The stable ``call_id``
is an ordinal per identical request (assigned in call order), correct for the sequential retrieval
calls the harness issues (bootstrap calls first, then in-loop gap searches, in the same order across
record and replay).

Only the downstream-consumed, JSON-native fields are frozen (``evidence_rows`` + the scalar/bool
telemetry that ``merge_retrieval_results`` and the harness read). ``classified_sources`` is NOT
frozen (the outline agent's fold-in path works off ``evidence_rows``; ``merge_retrieval_results``
only url-dedups the sources and never surfaces them to the outline) — it is reconstructed as ``[]``,
which keeps the frozen artifact strictly JSON-native and byte-stable.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path
from typing import Any

from tests.oracle.cassette import Cassette, _canonical

_counter: dict[str, int] = {}
_counter_lock = threading.Lock()


def _reset_counter() -> None:
    with _counter_lock:
        _counter.clear()


def _call_id(method: str, req: dict) -> str:
    base = _canonical(method, req)
    with _counter_lock:
        n = _counter.get(base, 0)
        _counter[base] = n + 1
    return str(n)


# The result fields the downstream actually reads (harness `_bootstrap_seed`,
# `merge_retrieval_results`, the outline fold-in). Everything here is JSON-native. Scalar/bool
# telemetry defaults match the LiveRetrievalResult dataclass defaults so a reconstruction is a
# faithful stand-in for the frozen subset.
_SCALAR_INT_FIELDS = (
    "total_candidates_pre_filter", "candidates_kept_by_scope", "candidates_kept_by_offtopic",
    "candidates_fetched", "candidates_failed_fetch", "candidates_total", "candidates_processed",
    "retrieval_queries_skipped", "retrieval_candidates_unclassified",
)
_SCALAR_BOOL_FIELDS = (
    "corpus_truncated", "retrieval_wall_hit", "semantic_relevance_fell_back",
)


def _request(*, research_question, amplified_queries, protocol, max_serper, max_s2, fetch_cap,
             enable_openalex_enrich, enable_prefetch_filter, domain, seed_urls, seed_only,
             anchor_seed) -> dict:
    """LOGICAL retrieval-call identity, canonicalized. Identity = what the CALLER asked for
    (the question + the amplified sub-query + scope flags), NOT the throughput/cost knobs.

    The caps (``max_serper``/``max_s2``/``fetch_cap``) are DELIBERATELY EXCLUDED: they resolve from
    env-driven module defaults (PG_LIVE_FETCH_CAP etc.) that legitimately differ between the (budget-
    capped) record run and a plain replay, and they are a cost/throughput dial, not a behaviour
    selector — on replay we serve the frozen result regardless of the cap. Including them made a
    record@fetch_cap=12 miss a replay@fetch_cap=200 for the SAME logical gap search. Wall-clock
    deadline + non-JSON objects (research_frame/retrieval_policy/progress_cb) are likewise omitted
    (research_frame/protocol are always None for every champion caller here). The bootstrap vs
    gap-search calls stay distinct without the caps — they differ by anchor_seed + amplified_queries
    + research_question."""
    return {
        "research_question": research_question,
        "amplified_queries": list(amplified_queries) if amplified_queries else None,
        "protocol": protocol if isinstance(protocol, (dict, type(None))) else str(protocol),
        "enable_openalex_enrich": enable_openalex_enrich,
        "enable_prefetch_filter": enable_prefetch_filter,
        "domain": domain,
        "seed_urls": list(seed_urls) if seed_urls else None,
        "seed_only": seed_only, "anchor_seed": anchor_seed,
    }


def _result_to_dict(r) -> dict:
    def _json_row(row: dict) -> dict:
        # evidence_rows are already str/num/bool/None-valued; deep-copy through the cassette's
        # JSON-native check happens at store time. Cast defensively to plain dict.
        return {str(k): v for k, v in dict(row).items()}

    out: dict[str, Any] = {
        "evidence_rows": [_json_row(row) for row in (getattr(r, "evidence_rows", None) or [])],
        "api_calls": {str(k): int(v) for k, v in (getattr(r, "api_calls", None) or {}).items()},
        "notes": [str(n) for n in (getattr(r, "notes", None) or [])],
    }
    for f in _SCALAR_INT_FIELDS:
        out[f] = int(getattr(r, f, 0) or 0)
    for f in _SCALAR_BOOL_FIELDS:
        out[f] = bool(getattr(r, f, False))
    sidecar = getattr(r, "journal_metadata_sidecar", None)
    out["journal_metadata_sidecar"] = sidecar if isinstance(sidecar, dict) else None
    return out


def _dict_to_result(d: dict):
    from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult
    kwargs: dict[str, Any] = {
        "classified_sources": [],  # not frozen; fold-in works off evidence_rows (see module docstring)
        "evidence_rows": [dict(row) for row in d.get("evidence_rows", [])],
        "api_calls": dict(d.get("api_calls", {})),
        "notes": list(d.get("notes", [])),
        "journal_metadata_sidecar": d.get("journal_metadata_sidecar"),
    }
    for f in _SCALAR_INT_FIELDS:
        kwargs[f] = int(d.get(f, 0))
    for f in _SCALAR_BOOL_FIELDS:
        kwargs[f] = bool(d.get(f, False))
    return LiveRetrievalResult(**kwargs)


@contextlib.contextmanager
def retrieval_cassette(path: str | Path, mode: str):
    """Patch ``live_retriever.run_live_retrieval`` (and the harness's imported name) to
    record/replay through a cassette for the block's duration. No browser on replay."""
    from src.polaris_graph.retrieval import live_retriever as lr

    cas = Cassette(path, mode)
    _reset_counter()
    original = lr.run_live_retrieval

    def _wrapped(*, research_question, amplified_queries=None, protocol=None,
                 max_serper=None, max_s2=None, fetch_cap=None,
                 enable_openalex_enrich=True, enable_prefetch_filter=False, domain=None,
                 seed_urls=None, seed_only=False, anchor_seed=True,
                 retrieval_deadline_monotonic=None, research_frame=None, retrieval_policy=None,
                 **extra):
        # Caps are resolved (for the real call below) but NOT part of the cassette key — see
        # _request(): they are an env-driven cost dial that can differ record vs replay.
        ms = lr.DEFAULT_MAX_SERPER if max_serper is None else max_serper
        m2 = lr.DEFAULT_MAX_S2 if max_s2 is None else max_s2
        fc = lr.DEFAULT_FETCH_CAP if fetch_cap is None else fetch_cap
        req = _request(
            research_question=research_question, amplified_queries=amplified_queries,
            protocol=protocol, max_serper=ms, max_s2=m2, fetch_cap=fc,
            enable_openalex_enrich=enable_openalex_enrich,
            enable_prefetch_filter=enable_prefetch_filter, domain=domain,
            seed_urls=seed_urls, seed_only=seed_only, anchor_seed=anchor_seed,
        )
        cid = _call_id("run_live_retrieval", req)
        if mode == "record":
            key, args_snap = cas.record_begin("run_live_retrieval", req, cid)
            resp = original(
                research_question=research_question, amplified_queries=amplified_queries,
                protocol=protocol, max_serper=ms, max_s2=m2, fetch_cap=fc,
                enable_openalex_enrich=enable_openalex_enrich,
                enable_prefetch_filter=enable_prefetch_filter, domain=domain,
                seed_urls=seed_urls, seed_only=seed_only, anchor_seed=anchor_seed,
                retrieval_deadline_monotonic=retrieval_deadline_monotonic,
                research_frame=research_frame, retrieval_policy=retrieval_policy, **extra,
            )
            cas.record_end(key, "run_live_retrieval", args_snap, cid, _result_to_dict(resp))
            return resp
        return _dict_to_result(cas.replay("run_live_retrieval", req, cid))

    lr.run_live_retrieval = _wrapped
    # Also rebind ANY already-loaded module that imported ``run_live_retrieval`` by name at module
    # load (the harness bootstrap seam, ``_bootstrap_seed``). This is load-bearing: when the harness
    # runs as ``python tests/oracle/acceptance_portable.py`` it lives in ``sys.modules['__main__']``
    # (NOT the dotted name), so a plain ``import tests.oracle.acceptance_portable`` would patch a
    # SECOND module copy and leave the running harness's bootstrap calling the LIVE retriever (a
    # browser fetch on replay). We therefore sweep sys.modules and rebind every module whose
    # ``run_live_retrieval`` attribute is the original function object. The loop site inside
    # outline_agent re-imports from the module each call, so it picks up ``lr``'s patch directly.
    import sys as _sys  # noqa: PLC0415
    _rebound: list = []
    for _modname, _mod in list(_sys.modules.items()):
        if _mod is None or _mod is lr:
            continue
        if getattr(_mod, "run_live_retrieval", None) is original:
            _mod.run_live_retrieval = _wrapped
            _rebound.append(_mod)

    try:
        yield cas
    finally:
        lr.run_live_retrieval = original
        for _mod in _rebound:
            _mod.run_live_retrieval = original
        cas.finalize()
