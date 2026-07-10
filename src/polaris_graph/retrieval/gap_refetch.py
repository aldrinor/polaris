"""S-X — bounded thin-section re-fetch (I-arch-plan ruling R10; doc 00 R8; Design 5 ORCH-4).

THE EXCEED MOVE. FS-Researcher (arXiv 2602.01566) FREEZES its knowledge base when the writer
starts ("web browsing tools removed") — a section discovered thin at compose time is stuck.
POLARIS does NOT freeze: when the S4 ORCH-3 reviser finds a section thin / undersupplied it emits
``gap_queries``; those route through the EXISTING per-query retrieval lane (the SAME
``per_query_retrieve`` every FS sub-query uses — so the new rows get the full scope-gate /
tier-classify / topic-judge / junk-gate / dedup treatment automatically and are first-class
citizens), ONE bounded round between the wave-1 compose and the recompose wave. The new rows fold
into the corpus as an S3 delta; the section-basket map rebuilds; only affected sections recompose.

This module is the S-X ENGINE. It is deliberately DECOUPLED from the orchestrator: it takes the
gap queries + the (injected) production retrieval lane + the (injected) merge factory, and returns
a delta ``LiveRetrievalResult`` + a disclosure. The reviser that EMITS the gap queries and the
recompose wave that CONSUMES the delta are the S4/S5 seams (WP-3a); they call ``run_gap_refetch``
and then ``fold_gap_delta``. Keeping the retrieval + fold logic here (injection-based, no
live_retriever import) makes the S-X contract unit-testable on a fixture, exactly like
``fs_researcher_query_gen`` (whose ``merge_retrieval_results`` this module reuses verbatim — same
global-renumber + telemetry-carry contract, never a re-implementation).

FAITHFULNESS (§-1.3 + §9.1.8): S-X only ADDS gap rows through the FROZEN lane. It NEVER drops,
caps, thins, or re-ranks a source. The budget is a SPEND cap on how many gap QUERIES are issued —
never a cap on sources returned and never a quality-number target. The faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance) is untouched: every recomposed sentence re-runs it
downstream. DATA-ONLY checkpoint, no verdict key.

DEFAULT OFF: the budget resolves to 0 unless a run explicitly asks for gap re-fetch, so an
unconfigured run performs NO fetch and writes NO ``gap_refetch.json`` — byte-identical to today
(R10 ships default-OFF; WAVE-5 activates it).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Reuse the REAL merge — global ev_id renumber + sidecar / telemetry carry, identical to the FS
# per-query merge. Light import (fs_researcher_query_gen pulls only stdlib; it never imports the
# 1000-line live_retriever), so this module stays offline-unit-testable.
from src.polaris_graph.retrieval.fs_researcher_query_gen import merge_retrieval_results

logger = logging.getLogger("polaris_graph.gap_refetch")

# (research_question=<query>, **kw) -> LiveRetrievalResult. Injected so this module never imports
# the live retriever and is testable on a stub — mirrors ``PerQueryRetrieveFn`` in the FS module.
PerQueryRetrieveFn = Callable[..., Any]

_GAP_REFETCH_CHECKPOINT = "gap_refetch.json"
_GAP_REFETCH_SCHEMA_VERSION = 1
_GAP_REFETCH_STAGE = "sx_thin_section_refetch"

# LAW VI — every knob reads at call time; no hardcoded value lives in the flow.
# Design 5 §6 + master §6: the budget's env source is PG_OUTLINE_GAP_QUERIES (default 0 = OFF).
_BUDGET_ENV = "PG_OUTLINE_GAP_QUERIES"
# §1.3 safety-ceiling family: a generous absolute cap that protects the box/wallet, NEVER a target.
_ABS_MAX_ENV = "PG_GAP_REFETCH_ABS_MAX"
_ABS_MAX_DEFAULT = 12

# DATA-ONLY invariant stamp (a §-1.1 auditor reads it off the artifact itself).
_FAITHFULNESS_INVARIANT = (
    "DATA ONLY; gap queries + realized per-query row counts. New rows re-enter the FROZEN "
    "per-query retrieval lane (scope-gate / tier / topic / junk / dedup) and re-run every "
    "faithfulness gate on fold/recompose. No verdict is persisted. The ev_ids in delta_result "
    "are DELTA-LOCAL (ev_000..) and MUST be renumbered against the existing pool on fold "
    "(fold_gap_delta) — they are NOT final ids."
)


@dataclass
class BudgetResolution:
    """Resolved gap-refetch spend budget (number of gap QUERIES allowed), with provenance.

    Precedence (master §1.3 / R9): RunConfig.stages.gap_refetch_budget > env PG_OUTLINE_GAP_QUERIES
    > code default 0. A generous abs ceiling (PG_GAP_REFETCH_ABS_MAX) clamps LOUDLY.
    """

    value: int          # the effective budget after ceiling clamp (0 => OFF)
    source: str         # "run_config" | "env" | "default"
    requested: int      # the pre-clamp requested value
    ceiling: int        # PG_GAP_REFETCH_ABS_MAX
    clamped: bool        # requested exceeded the ceiling (or was negative)


def resolve_gap_refetch_budget(run_config: Any = None) -> BudgetResolution:
    """Resolve the gap-refetch spend budget from RunConfig (duck-typed) → env → default 0.

    ``run_config`` is the (future) WP-0b RunConfig; when None or lacking the field we fall back to
    the env knob, so this is forward-compatible with the RunConfig rollout AND correct today
    (RunConfig not yet on the branch => run_config=None => env/default path). A malformed value
    fails OPEN to 0 (OFF is the safe, no-spend direction — mirrors ``_qgen_parallel_workers``).
    """
    requested: int | None = None
    source = "default"

    # (a) RunConfig.stages.gap_refetch_budget — duck-typed, never a hard import dependency.
    if run_config is not None:
        stages = getattr(run_config, "stages", None)
        rc_val = getattr(stages, "gap_refetch_budget", None) if stages is not None else None
        if rc_val is not None:
            try:
                requested = int(rc_val)
                source = "run_config"
            except (TypeError, ValueError):
                requested = None  # fall through to env

    # (b) env PG_OUTLINE_GAP_QUERIES (only if RunConfig did not supply a value).
    if requested is None:
        env_raw = os.getenv(_BUDGET_ENV)
        if env_raw is not None and env_raw.strip() != "":
            try:
                requested = int(env_raw.strip())
                source = "env"
            except ValueError:
                logger.warning(
                    "[gap_refetch] malformed %s=%r — treating as OFF (0)", _BUDGET_ENV, env_raw
                )
                requested = 0
                source = "env"

    # (c) code default.
    if requested is None:
        requested = 0
        source = "default"

    # Generous absolute ceiling — protects the box/wallet, never a quality target (§-1.3).
    try:
        ceiling = int(os.getenv(_ABS_MAX_ENV, str(_ABS_MAX_DEFAULT)))
    except ValueError:
        ceiling = _ABS_MAX_DEFAULT
    if ceiling < 0:
        ceiling = _ABS_MAX_DEFAULT

    value = max(0, min(requested, ceiling))
    clamped = requested > ceiling or requested < 0
    return BudgetResolution(
        value=value, source=source, requested=requested, ceiling=ceiling, clamped=clamped
    )


@dataclass
class GapRefetchOutcome:
    """Result of one bounded S-X re-fetch round.

    ``delta_result`` is the merged per-query ``LiveRetrievalResult`` (or None when nothing was
    fetched). Its ``evidence_rows`` carry DELTA-LOCAL ev_ids (ev_000..) — the caller MUST renumber
    them against the existing pool before folding (use ``fold_gap_delta``); they are not final ids.
    """

    active: bool                       # True iff the budget was > 0 AND gap_queries were supplied
    budget: int
    queries_requested: list[str] = field(default_factory=list)
    queries_issued: list[str] = field(default_factory=list)
    rows_added: int = 0
    delta_result: Any = None
    wall_hit: bool = False
    checkpoint_path: Path | None = None
    disclosure: dict = field(default_factory=dict)


def _normalize_queries(gap_queries: Any) -> list[str]:
    """Strip, drop empties, de-dup (first-seen, case-insensitive) — mirrors the FS seed-frontier."""
    out: list[str] = []
    seen: set[str] = set()
    for q in (gap_queries or []):
        if not isinstance(q, str):
            continue
        s = q.strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def run_gap_refetch(
    *,
    gap_queries: Any,
    per_query_retrieve: PerQueryRetrieveFn,
    result_factory: Callable[..., Any],
    budget: int,
    retrieve_kwargs: dict | None = None,
    run_dir: "Path | str | None" = None,
    section_titles: list[str] | None = None,
    wall_passed: Callable[[], bool] | None = None,
    merge_fn: Callable[[list[Any], Callable[..., Any]], Any] = merge_retrieval_results,
    log: Callable[[str], None] | None = None,
) -> GapRefetchOutcome:
    """Issue up to ``budget`` gap queries through the injected production lane and merge the delta.

    - OFF (``budget`` <= 0 OR no gap queries): NO fetch, NO ``gap_refetch.json`` written, empty
      outcome (``active=False``) — byte-identical to a run without S-X.
    - Each issued query fires ``per_query_retrieve(research_question=q, **retrieve_kwargs)`` — the
      SAME chokepoint (and therefore the SAME scope/tier/topic/junk/dedup gates) as every FS
      sub-query. ``wall_passed`` (the shared per-question retrieval wall, mirrored from
      ``_run_gap_round``) STOPS issuing further gap queries once it trips (disclosed, never silent).
    - The per-query results merge via ``merge_fn`` (default = the real ``merge_retrieval_results``)
      into ONE delta result whose ev_ids are delta-local (see ``GapRefetchOutcome`` / fold contract).
    - A DATA-ONLY ``gap_refetch.json`` is recorded (queries, per-query row counts, wall flag,
      triggering section titles) for the checkpoint index + Methods disclosure. Best-effort write:
      a failure is logged and never aborts a paid run.
    """
    _log = log or (lambda m: logger.info(m))
    requested = _normalize_queries(gap_queries)

    # ---- OFF path: no spend, no artifact, byte-identical -------------------------------------
    if budget <= 0 or not requested:
        reason = "budget_off" if budget <= 0 else "no_gap_queries"
        return GapRefetchOutcome(
            active=False,
            budget=budget,
            queries_requested=requested,
            disclosure={"active": False, "budget": budget, "reason": reason},
        )

    capped = requested[:budget]
    retrieve_kwargs = dict(retrieve_kwargs or {})
    results: list[Any] = []
    issued: list[str] = []
    per_query_row_counts: dict[str, int] = {}
    wall_hit = False

    for q in capped:
        if wall_passed is not None and wall_passed():
            wall_hit = True
            _log(
                "[gap_refetch] per-question retrieval wall hit — stopping gap round after "
                f"{len(issued)} of {len(capped)} budgeted queries (handing off what was gathered)"
            )
            break
        result = per_query_retrieve(research_question=q, **retrieve_kwargs)
        results.append(result)
        issued.append(q)
        per_query_row_counts[q] = len(list(getattr(result, "evidence_rows", None) or []))

    delta_result = merge_fn(results, result_factory) if results else None
    rows_added = len(list(getattr(delta_result, "evidence_rows", None) or [])) if delta_result else 0

    disclosure = {
        "active": True,
        "budget": budget,
        "queries_requested": requested,
        "queries_issued": issued,
        "rows_added": rows_added,
        "wall_hit": wall_hit,
        "section_titles": list(section_titles or []),
    }

    checkpoint_path = _write_gap_refetch_checkpoint(
        run_dir=run_dir,
        budget=budget,
        queries_requested=requested,
        queries_issued=issued,
        per_query_row_counts=per_query_row_counts,
        rows_added=rows_added,
        wall_hit=wall_hit,
        section_titles=list(section_titles or []),
        log=_log,
    )

    _log(
        f"[gap_refetch][activation] S-X thin-section re-fetch issued {len(issued)} of {budget} "
        f"budgeted gap queries; +{rows_added} delta rows"
        + (f" for sections {list(section_titles or [])}" if section_titles else "")
        + (" (WALL HIT)" if wall_hit else "")
    )

    return GapRefetchOutcome(
        active=True,
        budget=budget,
        queries_requested=requested,
        queries_issued=issued,
        rows_added=rows_added,
        delta_result=delta_result,
        wall_hit=wall_hit,
        checkpoint_path=checkpoint_path,
        disclosure=disclosure,
    )


def _write_gap_refetch_checkpoint(
    *,
    run_dir: "Path | str | None",
    budget: int,
    queries_requested: list[str],
    queries_issued: list[str],
    per_query_row_counts: dict[str, int],
    rows_added: int,
    wall_hit: bool,
    section_titles: list[str],
    log: Callable[[str], None],
) -> Path | None:
    """Atomic (temp + os.replace), DATA-ONLY intra-section checkpoint. Best-effort / fail-open.

    Mirrors the storm-outline checkpoint recipe (``write_storm_outline_checkpoint``): sorted-keys
    deterministic bytes, an explicit ``faithfulness_invariant`` stamp, NO verdict key.
    """
    if run_dir is None:
        return None
    try:
        payload = {
            "schema_version": _GAP_REFETCH_SCHEMA_VERSION,
            "stage": _GAP_REFETCH_STAGE,
            "budget": budget,
            "queries_requested": queries_requested,
            "queries_issued": queries_issued,
            "per_query_row_counts": per_query_row_counts,
            "rows_added": rows_added,
            "wall_hit": wall_hit,
            "section_titles": section_titles,
            "faithfulness_invariant": _FAITHFULNESS_INVARIANT,
        }
        path = Path(run_dir) / _GAP_REFETCH_CHECKPOINT
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)  # atomic publish
        return path
    except Exception as exc:  # noqa: BLE001 — FAIL-OPEN: checkpoint is best-effort, never a blocker
        log(f"[gap_refetch] checkpoint write skipped (fail-open): {exc}")
        return None


@dataclass
class FoldResult:
    """Result of folding a delta corpus into the existing pool (the S3-delta boundary)."""

    folded_rows: list[dict]        # existing rows + de-duped, globally-renumbered delta rows
    id_remap: dict[str, str]       # delta-local ev_id -> final pool ev_id (for the added rows)
    added: int                     # number of delta rows actually added (post source-URL dedup)


def _ev_index(evidence_id: Any) -> int:
    """Parse the numeric suffix of an ``ev_NNN`` id; -1 if unparseable."""
    try:
        return int(str(evidence_id).rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return -1


def fold_gap_delta(existing_rows: list[dict], delta_rows: list[dict]) -> FoldResult:
    """Fold delta gap rows into the existing pool: exact source-URL dedup + GLOBAL ev_id renumber.

    Follows the ``run_honest_sweep_r3._run_gap_round`` fold pattern (:14290+): global renumber so
    ids never collide with the existing ``{evidence_id: row}`` map and provenance stays intact,
    plus URL dedup so a source already in the pool is never double-counted. NOTE the dedup here is
    on the EXACT stripped ``source_url`` string; the production recompose seam may additionally
    apply the canonical-URL identity (the ``?utm_`` / query-param collapse the novelty metric uses)
    before or after this fold. §-1.3: this ADDS rows and CONSOLIDATES duplicates to one — it never
    deletes an existing row.
    """
    folded = [dict(r) for r in (existing_rows or [])]
    existing_urls = {
        (r.get("source_url") or "").strip()
        for r in folded
        if (r.get("source_url") or "").strip()
    }
    next_idx = (max((_ev_index(r.get("evidence_id")) for r in folded), default=-1)) + 1

    id_remap: dict[str, str] = {}
    added = 0
    for row in (delta_rows or []):
        url = (row.get("source_url") or "").strip()
        if url and url in existing_urls:
            continue  # CONSOLIDATE: duplicate source already in the pool — never double-count
        new_row = dict(row)
        old_id = row.get("evidence_id")
        new_id = f"ev_{next_idx:03d}"
        new_row["evidence_id"] = new_id
        if old_id is not None:
            id_remap[str(old_id)] = new_id
        folded.append(new_row)
        if url:
            existing_urls.add(url)
        next_idx += 1
        added += 1

    return FoldResult(folded_rows=folded, id_remap=id_remap, added=added)
