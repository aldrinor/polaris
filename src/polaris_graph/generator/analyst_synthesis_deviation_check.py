"""I-deepfix-001 B13 (#1357) — bring the Analyst-Synthesis layer UNDER the faithfulness engine.

THE PROBLEM (forensic): ``analyst_synthesis.generate_analyst_synthesis`` is architecturally OUTSIDE
the faithfulness engine — its system prompt FORBIDS ``[#ev:]`` span tokens and cites by ``[N]``
bibliography markers only, so the per-sentence ``strict_verify`` entailment gate NEVER sees it. It is
the longest, most confident block in the report, and its grounded over-assertions (hedges upgraded to
assertions, interpolated specifics, model-asserted author names absent from the pool) ship UNGATED.

THE FIX (the operator-locked "verify AFTER compose = LABEL, never DELETE" pattern, §-1.3 BASKET
FAITHFULNESS / `feedback_always_release_verifier_labels_never_holds_2026_06_14`): this module is a
thin, additive DEVIATION CHECK over the already-composed synthesis prose. It:

  1. splits the synthesis into sentences (reusing ``provenance_generator.split_into_sentences``),
  2. for each sentence, parses its ``[N]`` markers (``report_claim_extractor._NUMBERED_RE``) and
     resolves ``N -> bibliography[N-1].evidence_id -> the cited evidence row's span``,
  3. asks a groundedness judge (the certified MiniMax-M2 Sentinel decomposition by default — a SECOND
     family vs the GLM/DeepSeek writer, so two-family holds) whether the cited span SUPPORTS the
     sentence,
  4. for an UNSUPPORTED sentence appends an inline confidence marker
     (``claim_labeler.render_confidence_marker(BUCKET_LOW)``), and for a sentence whose ``[N]`` resolve
     NO span (``BUCKET_NO_SOURCE``) — KEEP the sentence, NEVER delete it.

FAIL-CLOSED to ``BUCKET_LOW``: a judge error / transport flap / timeout LABELS the sentence low (over-
labeling is the SAFE direction for a previously-ungated layer), never a silent high, never a hold.

FAITHFULNESS ENGINE UNTOUCHED: ``strict_verify`` / NLI / 4-role D8 / provenance / span-grounding are
NOT modified. This is an additive, LABEL-only deviation leg over the previously-ungated synthesis
prose. The judge here is ADVISORY — it never drops a sentence, never changes ``is_verified``.

LAW VI: the leg is gated default-ON by ``PG_ANALYST_SYNTHESIS_DEVIATION_CHECK`` and shares the coarse
``PG_SWEEP_ANALYST_SYNTHESIS`` kill-switch (when the whole analyst layer is off, this never runs).

TESTABILITY / NO HANG (I-arch-006/007 lesson): the per-sentence groundedness call is INJECTABLE
(``judge_fn``) so a test passes a deterministic fake; the real path resolves a bounded, deadline-wrapped
Sentinel judge lazily. The calls run BOUNDED-PARALLEL (never a serial unbounded loop on a trickle
socket — the documented hang class).
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
from typing import Any, Callable

from src.polaris_graph.generator import claim_labeler
from src.polaris_graph.generator.provenance_generator import split_into_sentences
from src.polaris_graph.benchmark.report_claim_extractor import _NUMBERED_RE

logger = logging.getLogger(__name__)

# LAW VI flags. The leg is default-ON; the coarse analyst-layer kill-switch ALSO gates it (when the
# whole analyst layer is off, this module never runs because the caller returns before invoking it).
_ENV_ENABLED = "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK"
_ENV_ANALYST_KILL = "PG_SWEEP_ANALYST_SYNTHESIS"
# Bounded-parallel fan-out for the per-sentence groundedness calls (NEVER a serial unbounded loop on a
# trickle socket — the I-arch-006/007 hang class). LAW VI; default 8.
_ENV_MAX_INFLIGHT = "PG_ANALYST_SYNTHESIS_DEVIATION_MAX_INFLIGHT"
_DEFAULT_MAX_INFLIGHT = 8
# Per-call deadline (seconds). A judge socket flap fail-CLOSES to BUCKET_LOW (over-label = safe) rather
# than hanging the report. LAW VI; default 60s.
_ENV_DEADLINE_S = "PG_ANALYST_SYNTHESIS_DEVIATION_DEADLINE_S"
_DEFAULT_DEADLINE_S = 60.0

_OFF_VALUES = frozenset({"", "0", "false", "off", "no", "disabled"})

# I-deepfix-001 M6 (Layer 2) — PROMOTE mode. Default-OFF (LAW VI): a synthesis sentence the groundedness
# judge says IS grounded against its cited [N] span is positively labeled (KEEP-and-PROMOTE = a
# BUCKET_MODERATE "verified against the cited source" marker) instead of passing bare. Ungrounded /
# no-source sentences keep their existing hedge/label. This NEVER deletes a sentence and NEVER touches
# strict_verify — it is a pure label CHANGE, the inverse of the existing KEEP-and-LABEL on the grounded
# side. OFF (default) => grounded sentences pass through bare, byte-identical to the legacy leg.
_ENV_PROMOTE_GROUNDED = "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED"


def promote_grounded_enabled() -> bool:
    """True iff the default-OFF PROMOTE mode is active (M6 Layer 2). Requires the deviation check to be
    enabled (it shares that gate) AND the fine PROMOTE flag to be explicitly on."""
    promote_on = os.environ.get(_ENV_PROMOTE_GROUNDED, "0").strip().lower() not in _OFF_VALUES
    return promote_on and deviation_check_enabled()

# A confidence marker is appended ONCE per sentence; this guards against a double-append when the
# function is (defensively) called twice on already-labeled prose.
_ALREADY_LABELED_MARKER = "[confidence:"


def deviation_check_enabled() -> bool:
    """True iff the default-ON B13 deviation check is active. Requires BOTH the fine flag
    (``PG_ANALYST_SYNTHESIS_DEVIATION_CHECK``, default ON) AND the coarse analyst-layer flag
    (``PG_SWEEP_ANALYST_SYNTHESIS``, default ON) to be on."""
    fine_on = os.environ.get(_ENV_ENABLED, "1").strip().lower() not in _OFF_VALUES
    coarse_on = os.environ.get(_ENV_ANALYST_KILL, "1").strip() in ("1", "true", "True")
    return fine_on and coarse_on


def _max_inflight() -> int:
    try:
        value = int(os.environ.get(_ENV_MAX_INFLIGHT, _DEFAULT_MAX_INFLIGHT) or _DEFAULT_MAX_INFLIGHT)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_INFLIGHT
    return value if value >= 1 else _DEFAULT_MAX_INFLIGHT


def _deadline_s() -> float:
    try:
        value = float(os.environ.get(_ENV_DEADLINE_S, _DEFAULT_DEADLINE_S) or _DEFAULT_DEADLINE_S)
    except (TypeError, ValueError):
        return _DEFAULT_DEADLINE_S
    return value if value > 0 else _DEFAULT_DEADLINE_S


def _resolve_span_for_evidence_id(
    evidence_id: str, evidence_rows: list[dict[str, Any]]
) -> str:
    """Resolve an evidence_id to its cited span text (``direct_quote`` first, then ``statement``).
    Returns ``""`` when the id is not in the pool or carries no span text."""
    for row in evidence_rows or []:
        rid = str(row.get("evidence_id") or row.get("id") or "")
        if rid and rid == evidence_id:
            return str(row.get("direct_quote") or row.get("statement") or "")
    return ""


def _resolve_sentence_span(
    sentence: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> str:
    """Concatenate the cited spans for ALL ``[N]`` markers in ``sentence``. ``N`` indexes the
    bibliography 1-based -> ``bibliography[N-1].evidence_id`` -> the evidence row's span. Returns
    ``""`` when the sentence carries NO resolvable ``[N]`` span (=> the caller labels BUCKET_NO_SOURCE).
    PURE (no I/O)."""
    spans: list[str] = []
    for m in _NUMBERED_RE.finditer(sentence):
        try:
            n = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if n < 1 or n > len(bibliography or []):
            continue
        entry = bibliography[n - 1]
        eid = str(entry.get("evidence_id") or "")
        if not eid:
            continue
        span = _resolve_span_for_evidence_id(eid, evidence_rows)
        if span:
            spans.append(span)
    return "\n".join(spans)


def _default_sentinel_judge() -> "Callable[[str, str], bool]":
    """Build the real groundedness judge: the certified MiniMax-M2 Sentinel decomposition (a SECOND
    family vs the GLM/DeepSeek writer, so two-family holds). Returns a ``judge_fn(claim, span) -> bool``
    where True == the span SUPPORTS the claim. Resolved LAZILY so importing this module never
    constructs a transport. FAIL-CLOSED: any construction / call failure surfaces as ``False`` (=>
    BUCKET_LOW), never a silent True."""
    def _judge(claim: str, span: str) -> bool:
        if not span.strip():
            return False
        try:
            from src.polaris_graph.roles.sentinel_adapter import (
                _configured_sentinel_slug,
                run_sentinel,
            )
            from src.polaris_graph.roles.role_transport import EvidenceDocument
            from src.polaris_graph.roles.openrouter_role_transport import (
                OpenRouterRoleTransport,
                _default_role_http_client,
            )
            from src.polaris_graph.roles.sentinel_contract import SentinelVerdict
        except Exception as exc:  # pragma: no cover — wiring resolved at runtime on the paid path
            logger.warning("[analyst_deviation] sentinel imports unavailable (fail-closed LOW): %s", exc)
            return False
        try:
            slug = _configured_sentinel_slug()
            if not slug:
                logger.warning("[analyst_deviation] no Sentinel slug configured (fail-closed LOW)")
                return False
            transport = OpenRouterRoleTransport(_default_role_http_client())
            result, _records = run_sentinel(
                transport,
                claim,
                [EvidenceDocument(doc_id="span", text=span)],
                model_slug=slug,
            )
            # GROUNDED + a clean parse == supported. UNGROUNDED OR a fail-closed parse == NOT supported
            # (BUCKET_LOW). NEVER trust a non-clean parse as supported (lethal-inversion guard).
            return bool(result.verdict == SentinelVerdict.GROUNDED and result.parsed_ok)
        except Exception as exc:  # transport flap / cap-adjacent / parse error -> fail-closed LOW
            logger.warning("[analyst_deviation] sentinel call failed (fail-closed LOW): %s", exc)
            return False
    return _judge


def screen_synthesis_against_baskets(
    text: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    *,
    judge_fn: "Callable[[str, str], bool] | None" = None,
) -> "tuple[str, dict[str, int]]":
    """B13 deviation check: LABEL (never delete) analyst-synthesis sentences whose cited span does
    NOT support them. Returns ``(labeled_text, telemetry)``.

    For each synthesis sentence:
      * resolve its ``[N]`` markers -> cited evidence spans;
      * a sentence with NO resolvable cited span -> append ``BUCKET_NO_SOURCE`` marker (uncited /
        unresolvable claim, shown unverified);
      * a sentence whose judge says the span does NOT support it -> append ``BUCKET_LOW`` marker;
      * a supported sentence -> UNCHANGED.

    ``judge_fn`` (``(claim, span) -> bool``, True == supported) is INJECTABLE for offline tests; the
    default lazily builds the certified-Sentinel judge. FAIL-CLOSED: a judge that raises / times out
    LABELS the sentence BUCKET_LOW (over-label = safe). NEVER deletes a sentence; NEVER touches
    ``strict_verify``. Returns the input unchanged (telemetry zeroed) when the leg is disabled."""
    telemetry = {
        "synthesis_deviation_labeled_count": 0,
        "synthesis_deviation_unresolved_count": 0,
        "synthesis_deviation_promoted_count": 0,
    }
    if not text or not text.strip() or not deviation_check_enabled():
        return text, telemetry

    # I-deepfix-001 M6 (Layer 2): default-OFF PROMOTE mode — a grounded sentence is positively labeled
    # (KEEP-and-PROMOTE) instead of passing bare. Resolved once; OFF => grounded sentences stay bare.
    promote = promote_grounded_enabled()

    if judge_fn is None:
        judge_fn = _default_sentinel_judge()

    sentences = split_into_sentences(text)
    if not sentences:
        return text, telemetry

    # Resolve each sentence's cited span ONCE (pure). A sentence with no resolvable span never calls
    # the judge (it is a BUCKET_NO_SOURCE label, not an UNSUPPORTED verdict).
    spans = [_resolve_sentence_span(s, bibliography, evidence_rows) for s in sentences]

    # BOUNDED-PARALLEL groundedness for the sentences that DO resolve a span (never a serial unbounded
    # loop). A per-future deadline fail-CLOSES to "not supported" (=> BUCKET_LOW).
    supported: dict[int, bool] = {}
    judge_indices = [i for i, sp in enumerate(spans) if sp.strip()]
    if judge_indices:
        deadline = _deadline_s()
        # Codex wave-2 P1 (hang class): the judge futures run CONCURRENTLY in the
        # pool, so the batch is bounded by ONE TOTAL wall deadline, never the sum of
        # per-future deadlines. AND the pool is shut down with wait=False +
        # cancel_futures=True so a Sentinel worker still stuck in a slow role-
        # transport call is ABANDONED — the `with`-block shutdown(wait=True) would
        # otherwise re-block on the timed-out worker and stall the synthesis return.
        # Every unresolved sentence fail-CLOSES to LOW (not supported).
        pool = ThreadPoolExecutor(max_workers=_max_inflight())
        try:
            futures = {
                pool.submit(judge_fn, sentences[i], spans[i]): i for i in judge_indices
            }
            _end = time.monotonic() + deadline
            for fut, i in futures.items():
                _remaining = max(0.0, _end - time.monotonic())
                try:
                    supported[i] = bool(fut.result(timeout=_remaining))
                except (_FutureTimeout, Exception) as exc:  # fail-closed LOW on any judge fault
                    logger.warning(
                        "[analyst_deviation] groundedness judge fault on sentence %d "
                        "(fail-closed LOW): %s", i, exc,
                    )
                    supported[i] = False
        finally:
            # Never block the synthesis return on a stuck judge worker.
            pool.shutdown(wait=False, cancel_futures=True)
        # Any sentence whose future never resolved within the TOTAL deadline is
        # fail-closed to LOW (covers the case where the loop exhausted the wall
        # budget before reaching a later future).
        for i in judge_indices:
            supported.setdefault(i, False)

    out_sentences: list[str] = []
    for i, sentence in enumerate(sentences):
        # Idempotent: never double-label an already-labeled sentence.
        if _ALREADY_LABELED_MARKER in sentence:
            out_sentences.append(sentence)
            continue
        if not spans[i].strip():
            # No resolvable cited [N] span at all -> a genuinely uncited / unresolvable claim.
            marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_NO_SOURCE)
            out_sentences.append(f"{sentence} {marker}")
            telemetry["synthesis_deviation_unresolved_count"] += 1
            continue
        if supported.get(i, False):
            # Cited span SUPPORTS the sentence. PROMOTE mode (default-OFF): append a positive
            # BUCKET_MODERATE marker (KEEP-and-PROMOTE — the grounded sentence loses its ambiguity);
            # OFF => pass through bare (byte-identical legacy). NEVER deletes, NEVER touches strict_verify.
            if promote:
                marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_MODERATE)
                out_sentences.append(f"{sentence} {marker}")
                telemetry["synthesis_deviation_promoted_count"] += 1
            else:
                out_sentences.append(sentence)  # KEEP unchanged
            continue
        # Cited span does NOT support the sentence (or the judge fail-closed) -> LABEL low, KEEP.
        marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_LOW)
        out_sentences.append(f"{sentence} {marker}")
        telemetry["synthesis_deviation_labeled_count"] += 1

    return " ".join(out_sentences), telemetry
