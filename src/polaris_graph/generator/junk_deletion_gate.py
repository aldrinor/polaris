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
      confirmed off-topic to the research question. DEFAULT path (Fix 1,
      ``is_row_deletable_offtopic``) deletes ONLY on the topic judge's affirmative
      OFF_SUBJECT stamp: a weight/reranker ``content_relevance_label``
      (``demoted`` / ``escalated_demoted``) can NEVER delete, and a positive relevance
      verdict (``relevant`` / ``escalated_relevant``) vetoes deletion UNCONDITIONALLY. Judge
      verdict ONLY, FAIL-OPEN (any uncertainty / missing verdict / error => KEEP), never a
      lexical/tier/number rule. The legacy weight-label reuse
      (``weighted_enrichment._is_confirmed_offtopic`` via ``is_row_confirmed_offtopic``) is
      reachable only behind ``PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0`` (byte-identical OFF).

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
# Fix 1 (I-deepfix-003 over-deletion): the off-topic DELETE fires ONLY on the topic judge's
# affirmative OFF_SUBJECT stamp; a weight/reranker ``content_relevance_label`` can NEVER
# delete. DEFAULT ON. OFF => byte-identical legacy weight-label path.
_TOPIC_JUDGE_ONLY_FLAG = "PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY"
# Fix 2 (I-deepfix-003 over-deletion): the off-topic DELETE fires ONLY on an OFF_SUBJECT
# stamp THIS run's topic judge produced. A STALE stamp reloaded from an earlier run's
# corpus_snapshot (the judge did NOT re-run this pass) demote-KEEPs. DEFAULT ON. OFF =>
# freshness is NOT enforced (byte-identical to the Fix-1-only path: any OFF_SUBJECT stamp
# deletes regardless of provenance).
_FRESH_VERDICT_FLAG = "PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

# An affirmative positive-relevance verdict from the content-relevance judge. A row carrying
# one is on-topic by the judge's own word and VETOES deletion unconditionally.
_POSITIVE_RELEVANCE_LABELS = frozenset({"relevant", "escalated_relevant"})
# String forms that mean an affirmative OFF_SUBJECT stamp (the deletable class of the OFF
# split). ``topic_off_subject`` is normally the bool True (Fix 3 sidecar); these tolerate a
# string representation without ever matching OFF_ASPECT or a weight label.
_OFF_SUBJECT_TRUE_TOKENS = frozenset({"off_subject", "offsubject", "true", "yes", "on", "1"})


def chrome_deletion_enabled() -> bool:
    """Kill-switch for the chrome-non-source deletion. DEFAULT ON. Falsey =>
    stamped-junk rows are KEPT (byte-identical to pre-carve-out)."""
    return os.getenv(_CHROME_FLAG, "1").strip().lower() not in _OFF_VALUES


def offtopic_deletion_enabled() -> bool:
    """Kill-switch for the confirmed-off-topic-source deletion. DEFAULT ON. Falsey =>
    confirmed-off-topic sources are KEPT (they fall back to the weight/ledger demote)."""
    return os.getenv(_OFFTOPIC_FLAG, "1").strip().lower() not in _OFF_VALUES


def topic_judge_only_deletion_enabled() -> bool:
    """Kill-switch ``PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY`` (DEFAULT ON). ON => an off-topic
    DELETE fires ONLY on the topic judge's affirmative OFF_SUBJECT stamp
    (``is_row_deletable_offtopic``): a weight/reranker ``content_relevance_label`` can NEVER
    delete, and a positive relevance verdict vetoes unconditionally. OFF => byte-identical
    legacy path (``is_row_confirmed_offtopic``, the weight-label reuse that hard-deleted 197
    on-topic rows in the I-deepfix-003 pass)."""
    return os.getenv(_TOPIC_JUDGE_ONLY_FLAG, "1").strip().lower() not in _OFF_VALUES


def fresh_verdict_only_deletion_enabled() -> bool:
    """Kill-switch ``PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY`` (DEFAULT ON, Fix 2). ON => an
    off-topic DELETE fires ONLY on an OFF_SUBJECT stamp THIS run's topic judge produced (the
    caller passes the fresh evidence_id set); a STALE snapshot stamp (reloaded from an earlier
    run, judge did NOT re-run) demote-KEEPs instead of deleting. OFF => freshness is NOT
    checked (byte-identical to the Fix-1-only path — any OFF_SUBJECT stamp is deletable). No
    effect when the caller passes ``fresh_off_subject_ids=None`` (freshness un-enforced)."""
    return os.getenv(_FRESH_VERDICT_FLAG, "1").strip().lower() not in _OFF_VALUES


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


def _stamped_off_subject(row: Mapping[str, Any]) -> bool:
    """True iff the topic judge stamped this WHOLE source OFF_SUBJECT — a clearly different
    subject (the DELETABLE class of the OFF split, e.g. a scholar-mill / tourism / religion
    page in an AI-labor report). The Fix-3 sidecar is the bool ``topic_off_subject=True``; a
    string verdict ``topic_relevance_verdict == "OFF_SUBJECT"`` is tolerated as the same
    signal. Legacy ``topic_offtopic_demoted`` alone (which conflates OFF_ASPECT 'same entity,
    wrong aspect' with OFF_SUBJECT) does NOT count — a demote-keep aspect verdict is never a
    delete trigger, so only the explicit subject-level stamp deletes."""
    v = row.get("topic_off_subject")
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in _OFF_SUBJECT_TRUE_TOKENS:
        return True
    verdict = str(row.get("topic_relevance_verdict", "") or "").strip().lower()
    return verdict == "off_subject"


def is_row_deletable_offtopic(
    row: Mapping[str, Any],
    fresh_off_subject_ids: "Iterable[str] | None" = None,
) -> bool:
    """DELETE predicate for the confirmed-off-topic class (topic-judge-only path, Fix 1 + Fix 2).

    Returns True (row is DELETABLE) iff the topic judge AFFIRMATIVELY stamped this WHOLE
    source OFF_SUBJECT. Three hard guarantees keep this from over-deleting:

    * A weight/reranker ``content_relevance_label`` (``demoted`` / ``escalated_demoted``) is
      NEVER a delete trigger — those are weight-demote-to-0.25 KEEP labels (a Qwen3-Reranker
      numeric score / a GLM 'INSUFFICIENT' entailment), NOT topic verdicts. Reusing them as a
      DELETE trigger is exactly what hard-deleted 197 on-topic rows (St. Louis Fed, OECD, ILO,
      McKinsey, HBS, Wikipedia, 23 T1 journal papers) in the I-deepfix-003 pass.
    * An affirmative positive-relevance verdict (``content_relevance_label`` in
      {relevant, escalated_relevant}) VETOES deletion UNCONDITIONALLY — even against a
      stale/false OFF stamp. When the two judges disagree, the positive relevance wins.
    * Fix 2 (fresh-verdict-only): when ``fresh_off_subject_ids`` is supplied (a concrete set —
      the evidence_ids THIS run's topic judge freshly confirmed OFF_SUBJECT) AND
      ``PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY`` is ON, a row whose OFF_SUBJECT stamp is NOT in
      that set is a STALE snapshot stamp (an earlier run's verdict reloaded from
      corpus_snapshot) and demote-KEEPs — only a fresh verdict deletes. ``None`` (the default)
      => freshness is un-enforced (byte-identical to the Fix-1-only path).

    FAIL-OPEN: not a Mapping / no OFF_SUBJECT stamp / stale-only stamp / missing verdict / any
    error => NOT deletable (row KEPT). A predicate bug must NEVER delete a source."""
    try:
        if not isinstance(row, Mapping):
            return False
        label = str(row.get("content_relevance_label", "") or "").strip().lower()
        if label in _POSITIVE_RELEVANCE_LABELS:
            return False  # affirmative positive-relevance verdict — KEEP (unconditional veto)
        if not _stamped_off_subject(row):
            return False
        # Fix 2: a STALE snapshot OFF_SUBJECT stamp (not in this run's fresh set) demote-KEEPs.
        # Enforced only when the caller passes a concrete set AND the flag is ON.
        if fresh_off_subject_ids is not None and fresh_verdict_only_deletion_enabled():
            eid = str(row.get("evidence_id", "") or "")
            if eid not in {str(e) for e in fresh_off_subject_ids}:
                return False  # stale stamp — demote-keep, never delete on an old verdict
        return True
    except Exception as exc:  # noqa: BLE001 — never delete on a predicate bug
        logger.warning(
            "[junk_deletion_gate] deletable-offtopic predicate errored (%s) — row KEPT "
            "(fail-open).", str(exc)[:160],
        )
        return False


def partition_rows(
    rows: list[dict[str, Any]],
    exempt_ids: "Iterable[str] | None" = None,
    fresh_off_subject_ids: "Iterable[str] | None" = None,
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
    # Fix 2: materialize the fresh OFF_SUBJECT id set ONCE (or None to leave freshness
    # un-enforced). A stale-stamp row whose id is absent demote-KEEPs (see
    # is_row_deletable_offtopic).
    fresh_ids = None if fresh_off_subject_ids is None else {str(e) for e in fresh_off_subject_ids}
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
        elif offtopic_on:
            # Fix 1: default-ON path deletes ONLY on the topic judge's OFF_SUBJECT stamp
            # (weight labels can never delete; positive relevance vetoes). The legacy
            # weight-label predicate stays reachable ONLY behind the OFF kill-switch so
            # ``PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0`` is byte-identical to pre-Fix-1.
            if topic_judge_only_deletion_enabled():
                if is_row_deletable_offtopic(row, fresh_off_subject_ids=fresh_ids):
                    reason = "confirmed_offtopic_subject"
            elif is_row_confirmed_offtopic(row):
                reason = "confirmed_offtopic"
        if reason:
            copied = dict(row)
            copied["deletion_reason"] = reason
            deleted.append(copied)
        else:
            kept.append(row)
    return kept, deleted


def _deletion_signal(reason: str) -> str:
    """Human-readable 'which signal fired' derived from the deletion_reason — a chrome class
    or the topic-judge OFF_SUBJECT stamp. Keeps the disclosure honest about the exact
    category (chrome non-source vs confirmed-off-topic) that removed each row."""
    if reason.startswith("content_integrity_junk"):
        cls = reason.split(":", 1)[1] if ":" in reason else "chrome"
        return "chrome:" + (cls or "chrome")
    if reason.startswith("confirmed_offtopic"):
        return "topic_judge_off_subject"
    return reason or "unknown"


def _judge_verdict_summary(row: Mapping[str, Any]) -> str:
    """Compact per-source verdict trail the row carried at deletion time (read-only — never a
    delete trigger here). Surfaces WHY the source was judged, so a reviewer can second-guess
    any deletion from the manifest alone."""
    parts: list[str] = []
    if _stamped_off_subject(row):
        parts.append("topic=OFF_SUBJECT")
    if row.get("topic_offtopic_demoted") is True:
        parts.append("topic_offtopic_demoted=True")
    label = str(row.get("content_relevance_label", "") or "").strip()
    if label:
        parts.append("content_relevance_label=" + label)
    verdict = str(row.get("topic_relevance_verdict", "") or "").strip()
    if verdict:
        parts.append("topic_relevance_verdict=" + verdict)
    ci_class = str(row.get("content_integrity_class", "") or "").strip()
    if ci_class:
        parts.append("content_integrity_class=" + ci_class)
    return ";".join(parts)


def disclosure_records(deleted_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact disclosure rows for the run telemetry — the audit trail that proves the
    pipeline found and DELETED each junk / off-topic source (recorded, never silent).

    Fix 5 (records half): each record now carries the per-source SIGNAL that fired
    (chrome class vs topic-judge OFF_SUBJECT), the JUDGE VERDICT trail, and the source TIER
    alongside the existing evidence_id / title / url / deletion_reason — enough to second-
    guess any single deletion straight from the manifest (fail-loud, never silent)."""
    out: list[dict[str, Any]] = []
    for row in deleted_rows:
        if not isinstance(row, Mapping):
            continue
        reason = str(row.get("deletion_reason", "") or "")
        out.append({
            "evidence_id": row.get("evidence_id", ""),
            "title": row.get("source_title") or row.get("title") or "",
            "url": row.get("url") or row.get("source_url") or "",
            "tier": row.get("tier") or row.get("source_tier") or "",
            "deletion_reason": reason,
            "signal": _deletion_signal(reason),
            "judge_verdict": _judge_verdict_summary(row),
            "excluded_from_grounding": True,
        })
    return out
