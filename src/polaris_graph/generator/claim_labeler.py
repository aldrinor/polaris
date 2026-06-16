"""I-perm-005 (#1199) — per-claim confidence LABELER (keep-and-label, never silently high).

Under the always-release reframe (I-perm-001), a non-VERIFIED claim is no longer DELETED by the
4-role redactor (`roles/report_redactor.reconcile_report_against_verdicts`) — it is KEPT and LABELED
with an honest per-claim confidence so the user judges. This module is the PURE deterministic core:
the Decision-B confidence bucket + the inline marker text. No LLM, no I/O, no global state.

THE clinical-safety invariant (Decision B): a non-VERIFIED claim can NEVER render `high`. `high`
requires verdict==VERIFIED AND credibility>=high AND origins>=2. Unknown credibility -> `low` (never
inflates). Zero resolvable cited evidence -> `no-source-found`. The bucket is a pure function of the
already-computed disclosure fields — it never re-runs a verifier and never flips `is_verified`. The
high/moderate/low thresholds are REUSED verbatim from `synthesis.disclosure_population._certainty_label`
(one source of truth, no drift); this module only adds the 4th `no-source-found` bucket + the marker.
"""

from __future__ import annotations

from typing import Optional

# The four rendered buckets (the discrete per-claim chip).
BUCKET_HIGH = "high"
BUCKET_MODERATE = "moderate"
BUCKET_LOW = "low"
BUCKET_NO_SOURCE = "no-source-found"

VALID_BUCKETS = (BUCKET_HIGH, BUCKET_MODERATE, BUCKET_LOW, BUCKET_NO_SOURCE)


def confidence_bucket(
    *,
    is_verified: bool,
    credibility: Optional[float],
    origin_count: int,
    has_cited_evidence: bool,
) -> str:
    """Decision-B per-claim confidence bucket (pure, deterministic, no LLM).

    - ``no-source-found`` when the claim resolves NO cited evidence at all (a genuinely ungrounded
      statement) — this is a first-class DISPLAYED outcome, not a hidden drop.
    - otherwise the high/moderate/low bucket from the shared disclosure thresholds, which already
      enforce: not-verified -> low; verified + unknown credibility -> low; high iff
      origins>=PG_DISCLOSURE_HIGH_MIN_ORIGINS AND credibility>=PG_DISCLOSURE_HIGH_CRED.

    A non-VERIFIED claim therefore can never be ``high`` (the lethal over-confidence the reframe
    must not introduce): `_certainty_label` returns `low` for `is_verified=False`.
    """
    if not has_cited_evidence:
        return BUCKET_NO_SOURCE
    # Reuse the disclosure certainty thresholds verbatim (single source of truth, no drift).
    from src.polaris_graph.synthesis.disclosure_population import _certainty_label  # noqa: PLC0415

    bucket = _certainty_label(is_verified, origin_count, credibility)
    return bucket if bucket in VALID_BUCKETS else BUCKET_LOW


# Human-facing marker text per bucket. The wording is deliberately unmistakable: a `low` /
# `no-source-found` chip must read as NOT-asserted-as-fact (the §-1.1 invariant that a low chip is
# never mistaken for support). Kept short for the screen-reader / inline render.
_MARKER_TEXT = {
    BUCKET_HIGH: "high confidence — verified against multiple independent sources",
    BUCKET_MODERATE: "moderate confidence — verified against the cited source",
    BUCKET_LOW: "low confidence — NOT confirmed by the cited source; treat as unverified",
    BUCKET_NO_SOURCE: "no grounded source was found for this statement; shown unverified",
}


def render_confidence_marker(bucket: str) -> str:
    """The inline marker appended to a KEPT claim, e.g. ``[confidence: low — NOT confirmed ...]``.

    Deterministic; unknown bucket falls back to the low wording (fail-safe: never imply support)."""
    text = _MARKER_TEXT.get(bucket, _MARKER_TEXT[BUCKET_LOW])
    label = bucket if bucket in VALID_BUCKETS else BUCKET_LOW
    return f"[confidence: {label} — {text}]"


def is_asserted_as_fact(bucket: str) -> bool:
    """True only for buckets that may read as an asserted fact (high/moderate). low / no-source-found
    must always be visibly hedged. Helper for renderers/UI that style the chip."""
    return bucket in (BUCKET_HIGH, BUCKET_MODERATE)


# A8 (I-arch-006) — render the SOFT advisory credibility/metadata flags carried on a claim's
# ``soft_warnings`` as short inline markers. ADVISORY/SURFACE only: these flags never drop a source,
# never hold a report, never change ``is_verified`` (they originate from
# ``synthesis.disclosure_population``'s soft-warning helpers, which are append-only to ``soft_warnings``).
_SOFT_FLAG_MARKER_TEXT = {
    "legal_claim_no_high_credibility_corroborator": (
        "thinly sourced — load-bearing legal claim with no high-credibility corroborator"
    ),
    "metadata_quality_blank_bibliography_title": (
        "metadata gap — a cited source has a blank/degenerate bibliography title"
    ),
}


def render_soft_flag_markers(soft_warnings: Optional[list]) -> list:
    """Map a claim's ``soft_warnings`` (stable id-prefixed strings) to short inline render markers.

    Returns one ``[note: <text>]`` string per RECOGNISED A8 soft flag, in input order, de-duplicated.
    Unrecognised warnings (e.g. supersession warnings owned by another module) are left to their own
    renderer and skipped here. Deterministic, pure, no I/O. Advisory only — surfacing a flag never
    affects whether the claim renders as fact (use ``is_asserted_as_fact`` for that)."""
    out: list = []
    seen: set = set()
    for raw in (soft_warnings or []):
        # Warnings are formatted as ``<stable_id>: <human detail>``; key on the stable id prefix.
        key = str(raw).split(":", 1)[0].strip()
        text = _SOFT_FLAG_MARKER_TEXT.get(key)
        if text is None or key in seen:
            continue
        seen.add(key)
        out.append(f"[note: {text}]")
    return out
