"""I-deepfix-001 (#1344) Bug B — retraction grounding gate.

A RETRACTED / WITHDRAWN source must NEVER be a grounding surface for generated
prose. A retracted RCT's dose / contraindication / effect size is exactly the
clinical-safety hazard the §-1.1 line-by-line standard guards against: a sentence
grounded on a retracted study can PASS strict_verify (the cited span really does
contain the number, the words overlap) and still be clinically wrong, because the
study was withdrawn. The faithfulness engine checks sentence<->span fidelity, NOT
whether the source itself was retracted — so the exclusion must happen BEFORE
grounding, at the evidence pool, where the credibility engine already knows the
retraction flag.

§-1.3 posture (WEIGHT-not-FILTER): this is NOT a breadth cap. It is the
clinical-safety arm of the ONLY hard gate (faithfulness). A retracted source is
not a low-weight corroborator to keep in the basket — it is a withdrawn claim. But
the source is NOT silently vanished: every excluded row is RETURNED to the caller
and surfaced in disclosure telemetry + a LOUD log, so an auditor sees the pipeline
found it and excluded it (recorded, not dropped). The tier classifier's
``R0_retracted`` rule already states "Caller should filter retracted sources before
composition" — this module is that caller-side filter.

Single source of truth: the retraction predicate REUSES
``authority.supersession._is_truthy`` — the EXACT truthiness rule the credibility
engine already applies to the retraction/withdrawal flags — so the grounding gate
and the credibility down-weight can never disagree about what "retracted" means. A
string ``'false'`` / ``'0'`` / ``'no'`` / ``''`` or a MISSING flag is NOT retracted
(fail-open: a source with no retraction info grounds normally).

Pure leaf module: no network, no model import, no faithfulness-engine import. Env
kill-switch (LAW VI). DEFAULT ON — a clinical-safety gate. When the corpus has
zero retracted sources (the common case) the groundable pool is byte-identical to
the input, so default-ON changes nothing until a real retracted source appears.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Mapping

# Single source of truth for the retraction predicate. We deliberately reuse the
# credibility engine's private truthiness helper (operator directive 2026-06-30:
# "reuse supersession._is_truthy") so the grounding gate and the credibility
# down-weight agree byte-for-byte. If supersession ever renames it, this import
# fails LOUDLY at module load (LAW II) — the shared predicate moved and BOTH
# call-sites must be reconciled, not silently forked.
from src.polaris_graph.authority.supersession import _is_truthy as _supersession_is_truthy

logger = logging.getLogger("polaris_graph.retraction_gate")

_ENV_FLAG = "PG_RETRACTION_GROUNDING_GATE"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

# The retraction/withdrawal flag keys — IDENTICAL to authority.supersession's
# retraction check (``_is_truthy(row, "is_retracted", "retracted",
# "retraction_notice", "withdrawn")``), the single source of truth.
_RETRACTION_KEYS = ("is_retracted", "retracted", "retraction_notice", "withdrawn")


def retraction_gate_enabled() -> bool:
    """Kill-switch. DEFAULT ON (clinical-safety). Set ``PG_RETRACTION_GROUNDING_GATE``
    to a falsey value to disable — the groundable pool is then byte-identical to the
    input and no row is excluded."""
    return os.getenv(_ENV_FLAG, "1").strip().lower() not in _OFF_VALUES


def is_row_retracted(row: Mapping[str, Any]) -> bool:
    """True iff ``row`` carries a truthy retraction/withdrawal flag, using the SAME
    predicate the credibility engine uses. A string ``'false'`` / ``'0'`` / ``'no'``
    / ``''`` or a missing field is NOT retracted (fail-open). A predicate bug must
    NEVER exclude a source — on any internal error we treat the row as NOT retracted
    (loud-degrade, LAW II)."""
    try:
        return bool(_supersession_is_truthy(row, *_RETRACTION_KEYS))
    except Exception as exc:  # noqa: BLE001 — never exclude a source on a predicate bug
        logger.warning(
            "[retraction_gate] retraction predicate errored (%s) — treating row as "
            "NOT retracted (fail-open, no exclusion on a bug).", str(exc)[:160],
        )
        return False


def partition_pool(
    evidence_pool: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Split an ``{evidence_id: row}`` grounding pool into
    ``(groundable_pool, retracted_rows)``.

    * ``groundable_pool`` — the rows generation may ground against (retracted
      EXCLUDED). A NEW dict; the input is never mutated.
    * ``retracted_rows`` — the excluded retracted/withdrawn rows, RETURNED so the
      caller can disclose them (never silently dropped, §-1.3).

    Order-preserving. Idempotent: re-running on an already-clean pool returns it
    unchanged with an empty retracted list (so the caller may safely re-apply the
    gate after an M-52 corpus-pull re-adds rows). When the kill-switch is OFF,
    returns ``(dict(evidence_pool), [])`` — a byte-identical groundable pool.
    """
    if not retraction_gate_enabled():
        return dict(evidence_pool), []
    groundable: dict[str, dict[str, Any]] = {}
    retracted: list[dict[str, Any]] = []
    for ev_id, row in evidence_pool.items():
        if isinstance(row, Mapping) and is_row_retracted(row):
            retracted.append(row)
        else:
            groundable[ev_id] = row
    return groundable, retracted


def partition_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """List form of :func:`partition_pool` for the RUN-LEVEL grounding pool
    (``evidence_for_gen``), so EVERY downstream grounding surface — the multi-section
    generator, the quantified-analysis ``_q_ev_pool``, and the resume corpus snapshot —
    sees the same retracted-free pool from one chokepoint.

    Returns ``(groundable_rows, retracted_rows)``. Order-preserving; never mutates the
    input; idempotent. When the kill-switch is OFF, returns ``(list(rows), [])``.
    """
    if not retraction_gate_enabled():
        return list(rows), []
    groundable: list[dict[str, Any]] = []
    retracted: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping) and is_row_retracted(row):
            retracted.append(row)
        else:
            groundable.append(row)
    return groundable, retracted


def disclosure_records(retracted_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact disclosure rows for the run telemetry (the audit trail that proves
    the pipeline found and excluded each retracted source). The ``retraction_flag``
    names WHICH key was truthy, resolved through the SAME shared predicate so the
    disclosure cannot disagree with the exclusion decision."""
    out: list[dict[str, Any]] = []
    for row in retracted_rows:
        if not isinstance(row, Mapping):
            continue
        which = next(
            (k for k in _RETRACTION_KEYS if is_row_retracted({k: row.get(k)})), "",
        )
        out.append({
            "evidence_id": row.get("evidence_id", ""),
            "title": row.get("source_title") or row.get("title") or "",
            "url": row.get("url") or row.get("source_url") or "",
            "retraction_flag": which,
            "excluded_from_grounding": True,
        })
    return out
