"""I-deepfix-001 B14 (2026-06-28) — title<->body cross-wiring consistency gate.

A mis-stitched source (the serper/openalex METADATA title belongs to a different
page than the FETCHED body — a redirect-to-homepage, a wrong-anchor crawl, a
chrome shell whose title is the site name) makes the pipeline reason about ONE
source under TWO identities. This is CiteCheck's title-fidelity acceptance signal
applied to metadata-title-vs-fetched-body.

POSTURE (§-1.3 weight-not-filter): this NEVER drops a source. On a confirmed
mismatch it (a) RE-DERIVES the title from the body and (b) sets
``identity_consistent=False`` carried onto the evidence row, so downstream
generation / dedup can avoid reasoning about a corrupt identity. The source is
QUARANTINED to "title corrected + flagged", not deleted. Faithfulness engine
(strict_verify / NLI / 4-role / provenance / span-grounding) UNTOUCHED.

TWO-STAGE (CiteCheck/CiteAudit pattern):
  1. cheap normalized edit-distance / token-overlap PRE-SCREEN on every source;
  2. the LOCKED-SLATE reranker/embed similarity (reused via an injected callable —
     the same Qwen3 path content_relevance_judge uses) ONLY on flagged sources.

Pure leaf module: no network, no model import. The slate similarity is provided
by an injected ``similarity_fn(a, b) -> float`` so this is unit-testable offline
and the caller wires the real Qwen3 reranker/embedder. All knobs are env (LAW VI).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger("polaris_graph.title_body_consistency")

_ENV_FLAG = "PG_TITLE_BODY_CONSISTENCY"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

# Minimum slate-similarity below which the metadata title and the body are judged
# mis-stitched (env-overridable, LAW VI). Default 0.35 per the B14 fix plan.
_ENV_MIN_SIM = "PG_TITLE_BODY_MIN_SIM"
_DEFAULT_MIN_SIM = 0.35

# Edit-distance / token-overlap PRE-SCREEN: a source whose metadata title and
# body-derived title already overlap well skips the (costly) slate similarity.
_ENV_PRESCREEN_OVERLAP = "PG_TITLE_BODY_PRESCREEN_OVERLAP"
_DEFAULT_PRESCREEN_OVERLAP = 0.5

# Head window of the body fed to the slate similarity (topicality, bounded cost).
_ENV_BODY_CHARS = "PG_TITLE_BODY_BODY_CHARS"
_DEFAULT_BODY_CHARS = 512

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]+")


def title_body_consistency_enabled() -> bool:
    """B14 kill-switch. DEFAULT OFF (the fix plan's stated default) so the OFF path
    is byte-identical and the new evidence-row keys are ABSENT. Set
    ``PG_TITLE_BODY_CONSISTENCY=1`` to activate the gate."""
    return os.getenv(_ENV_FLAG, "0").strip().lower() not in _OFF_VALUES


def _min_sim() -> float:
    return _env_float(_ENV_MIN_SIM, _DEFAULT_MIN_SIM)


def _prescreen_overlap() -> float:
    return _env_float(_ENV_PRESCREEN_OVERLAP, _DEFAULT_PRESCREEN_OVERLAP)


def _body_chars() -> int:
    try:
        return max(64, int(os.getenv(_ENV_BODY_CHARS, str(_DEFAULT_BODY_CHARS))))
    except (TypeError, ValueError):
        return _DEFAULT_BODY_CHARS


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    # Clamp to [0, 1] — a similarity threshold outside that range is a misconfig.
    return min(max(val, 0.0), 1.0)


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 2}


def _token_overlap(a: str, b: str) -> float:
    """Containment overlap |a∩b| / min(|a|,|b|) on token sets — the cheap prescreen
    (a short real title fully inside the body title scores ~1.0)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    smaller = min(len(ta), len(tb))
    return len(inter) / smaller if smaller else 0.0


@dataclass
class TitleBodyVerdict:
    """Per-source identity outcome (a flag + a corrected title, never a drop)."""

    identity_consistent: bool
    title_source: str          # 'metadata' (kept) or 'rederived_from_body'
    resolved_title: str
    metadata_title: str
    body_title: str
    prescreen_overlap: float
    slate_similarity: Optional[float]  # None when the prescreen already passed
    reason: str = ""


def check_title_body_consistency(
    metadata_title: str,
    body_title: str,
    body_text: str,
    *,
    similarity_fn: Optional[Callable[[str, str], float]] = None,
) -> TitleBodyVerdict:
    """Judge whether ``metadata_title`` belongs to the fetched body.

    Stage 1 — cheap token-overlap prescreen. If the metadata title and the body-
    derived title overlap >= the prescreen floor, accept (no slate call).
    Stage 2 — only when the prescreen flags, call the injected ``similarity_fn``
    (the locked Qwen3 reranker/embed) between the metadata title and
    (body_title + body head). Below ``PG_TITLE_BODY_MIN_SIM`` ⇒ mis-stitched:
    RE-DERIVE the title from the body and flag ``identity_consistent=False``.

    NEVER drops a source — the worst outcome is a corrected title + a flag.
    """
    meta = (metadata_title or "").strip()
    body_t = (body_title or "").strip()
    # No body title to compare against — cannot judge; keep metadata, consistent.
    if not body_t:
        return TitleBodyVerdict(
            identity_consistent=True, title_source="metadata",
            resolved_title=meta, metadata_title=meta, body_title=body_t,
            prescreen_overlap=1.0, slate_similarity=None,
            reason="no body title — cannot judge, kept",
        )
    overlap = _token_overlap(meta, body_t)
    if overlap >= _prescreen_overlap():
        return TitleBodyVerdict(
            identity_consistent=True, title_source="metadata",
            resolved_title=meta, metadata_title=meta, body_title=body_t,
            prescreen_overlap=overlap, slate_similarity=None,
            reason="prescreen overlap passed",
        )
    # Flagged by the cheap prescreen — escalate to the slate similarity.
    sim: Optional[float] = None
    scorer_errored = False
    if similarity_fn is not None:
        body_window = (body_text or "")[: _body_chars()]
        try:
            sim = float(similarity_fn(meta, (body_t + " " + body_window).strip()))
        except Exception as exc:  # a slate failure must never drop/flag a source
            logger.warning(
                "[title_body] slate similarity failed (%s) — keeping metadata "
                "title (no drop, no flag on a scorer error).", str(exc)[:160],
            )
            sim = None
            scorer_errored = True
    # A scorer ERROR must NEVER flip the identity (no flag on a bug — LAW II loud
    # degrade keeps the metadata title). Only an actual slate signal below the floor
    # re-derives; with no slate fn at all we fall back to the prescreen overlap so
    # an essentially-zero-overlap title with no slate is still caught.
    if scorer_errored:
        return TitleBodyVerdict(
            identity_consistent=True, title_source="metadata",
            resolved_title=meta, metadata_title=meta, body_title=body_t,
            prescreen_overlap=overlap, slate_similarity=None,
            reason="slate scorer errored — kept metadata (no flag on a bug)",
        )
    effective = sim if sim is not None else overlap
    if effective < _min_sim():
        return TitleBodyVerdict(
            identity_consistent=False, title_source="rederived_from_body",
            resolved_title=body_t, metadata_title=meta, body_title=body_t,
            prescreen_overlap=overlap, slate_similarity=sim,
            reason="title<->body mismatch below floor — title re-derived, flagged",
        )
    return TitleBodyVerdict(
        identity_consistent=True, title_source="metadata",
        resolved_title=meta, metadata_title=meta, body_title=body_t,
        prescreen_overlap=overlap, slate_similarity=sim,
        reason="slate similarity cleared the floor",
    )


def consistency_keys(verdict: TitleBodyVerdict) -> dict[str, Any]:
    """The evidence-row keys to merge ON the B14 ON path. ABSENT on the OFF path
    so the OFF evidence row is byte-identical."""
    return {
        "identity_consistent": verdict.identity_consistent,
        "title_source": verdict.title_source,
    }
