"""GH I-deepfix-003 (#1374) — junk-deletion grounding gate.

Operator rule change 2026-07-09 (CLAUDE.md §-1.3.1): the §-1.3 never-DROP rule is
LIFTED for genuine JUNK. Weighting junk to zero is insufficient — a zero-weight row
still sits in the evidence pool, the bibliography, and the per-claim corroboration
counts, where it pollutes a clinical report (a bot-detection page anchoring a claim; a
predatory PDF padding the count; an off-topic law/tourism source). Two classes are
hard-DELETED from the run-level grounding pool BEFORE generation:

  (a) CHROME NON-SOURCES — bot/captcha/cookie/404/login/empty pages. A failed fetch is
      not a source. The content-integrity detector stamps ``row["content_integrity_junk"]``
      upstream (the re-tier seam); this gate deletes the stamped rows.
  (b) SEMANTICALLY-CONFIRMED OFF-TOPIC whole sources — a source a SEMANTIC topic judge
      confirmed off-topic to the research question. Reuses
      ``weighted_enrichment._is_confirmed_offtopic`` (single source of truth). Judge
      verdict ONLY, FAIL-OPEN (any uncertainty => KEEP), never a lexical/tier/number rule.

STILL BINDING (§-1.3): credible ON-TOPIC sources, even low-tier / social / non-journal,
are NEVER deleted here (they are neither content-junk nor confirmed-off-topic). An
off-topic SPAN inside an on-topic source is handled at compose (the span screen), not
here. Duplicates consolidate elsewhere. The faithfulness engine is UNTOUCHED — deleting a
row can only SHRINK the grounding pool, so a claim citing a deleted junk row FAILS
strict_verify (it can never make one PASS). A deleted junk row was never a valid anchor.

MARQUEE/CONTRACT EXEMPTION: a required-entity / contract-bound anchor is on-topic by
construction and is NEVER deleted (its evidence_id is in ``exempt_ids``), mirroring the
topic gate's existing anchor exemption.

Deletion is DISCLOSED: every deleted row is RETURNED with its reason for the manifest + a
LOUD log + a Methods line (fail loud, never silent — LAW II).

Pure leaf module: no network, no model import, no faithfulness-engine import. Two env
kill-switches (LAW VI), DEFAULT ON. When the corpus has zero junk / off-topic rows the
groundable pool is byte-identical to the input.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Mapping

logger = logging.getLogger("polaris_graph.junk_deletion_gate")

_CHROME_FLAG = "PG_DELETE_CHROME_NONSOURCE"
_OFFTOPIC_FLAG = "PG_DELETE_OFFTOPIC_SOURCE"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})


def chrome_deletion_enabled() -> bool:
    """Kill-switch for the chrome-non-source deletion. DEFAULT ON. Falsey =>
    stamped-junk rows are KEPT (byte-identical to pre-carve-out)."""
    return os.getenv(_CHROME_FLAG, "1").strip().lower() not in _OFF_VALUES


def offtopic_deletion_enabled() -> bool:
    """Kill-switch for the confirmed-off-topic-source deletion. DEFAULT ON. Falsey =>
    confirmed-off-topic sources are KEPT (they fall back to the weight/ledger demote)."""
    return os.getenv(_OFFTOPIC_FLAG, "1").strip().lower() not in _OFF_VALUES


def is_row_content_junk(row: Mapping[str, Any]) -> bool:
    """True iff the content-integrity detector stamped this row as a chrome non-source
    (bot / cookie / 404 / login / empty). FAIL-OPEN: any error / missing / falsey flag
    => NOT junk (row KEPT). A predicate bug must NEVER delete a source."""
    try:
        v = row.get("content_integrity_junk")
        return bool(v) and str(v).strip().lower() not in _OFF_VALUES
    except Exception as exc:  # noqa: BLE001 — never delete on a predicate bug
        logger.warning(
            "[junk_deletion_gate] content-junk predicate errored (%s) — row KEPT "
            "(fail-open).", str(exc)[:160],
        )
        return False


def is_row_confirmed_offtopic(row: Mapping[str, Any]) -> bool:
    """True iff a SEMANTIC topic judge confirmed this WHOLE source off-topic to the
    research question. Reuses ``weighted_enrichment._is_confirmed_offtopic`` — the single
    source of truth the compose off-topic screen also uses — so the gate and the screen
    can never disagree. FAIL-OPEN: an unjudged / ``relevant`` / ``escalated_relevant`` /
    missing-verdict / error row is NOT off-topic (row KEPT)."""
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            _is_confirmed_offtopic,
        )
        return bool(_is_confirmed_offtopic(row))
    except Exception as exc:  # noqa: BLE001 — never delete on a predicate bug
        logger.warning(
            "[junk_deletion_gate] offtopic predicate errored (%s) — row KEPT "
            "(fail-open).", str(exc)[:160],
        )
        return False


def partition_rows(
    rows: list[dict[str, Any]],
    exempt_ids: "Iterable[str] | None" = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split the run-level grounding pool (``evidence_for_gen``) into
    ``(kept, deleted)``.

    A row is DELETED iff it is a chrome non-source (kill-switch A) OR a
    confirmed-off-topic source (kill-switch B), AND its ``evidence_id`` is NOT in
    ``exempt_ids`` (a marquee / contract-bound anchor is on-topic by construction and is
    never deleted). Each deleted row carries a ``deletion_reason`` for disclosure.

    Order-preserving; never mutates the input rows (a deleted row is copied before the
    reason is stamped); idempotent (re-running on a clean pool returns it unchanged with
    an empty deleted list). When BOTH kill-switches are OFF, returns ``(list(rows), [])``
    — byte-identical.
    """
    chrome_on = chrome_deletion_enabled()
    offtopic_on = offtopic_deletion_enabled()
    if not chrome_on and not offtopic_on:
        return list(rows), []
    exempt = {str(e) for e in (exempt_ids or ())}
    kept: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            kept.append(row)
            continue
        eid = str(row.get("evidence_id", "") or "")
        if eid and eid in exempt:
            kept.append(row)  # marquee / contract anchor — NEVER deleted
            continue
        reason = ""
        if chrome_on and is_row_content_junk(row):
            reason = "content_integrity_junk:" + str(
                row.get("content_integrity_class", "chrome") or "chrome"
            )
        elif offtopic_on and is_row_confirmed_offtopic(row):
            reason = "confirmed_offtopic"
        if reason:
            copied = dict(row)
            copied["deletion_reason"] = reason
            deleted.append(copied)
        else:
            kept.append(row)
    return kept, deleted


def disclosure_records(deleted_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact disclosure rows for the run telemetry — the audit trail that proves the
    pipeline found and DELETED each junk / off-topic source (recorded, never silent)."""
    out: list[dict[str, Any]] = []
    for row in deleted_rows:
        if not isinstance(row, Mapping):
            continue
        out.append({
            "evidence_id": row.get("evidence_id", ""),
            "title": row.get("source_title") or row.get("title") or "",
            "url": row.get("url") or row.get("source_url") or "",
            "deletion_reason": row.get("deletion_reason", ""),
            "excluded_from_grounding": True,
        })
    return out
