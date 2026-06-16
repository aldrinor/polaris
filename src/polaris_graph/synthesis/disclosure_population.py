"""I-cred-008 (Phase 8, L7) — per-claim disclosure POPULATION (pure module).

Populate the four inert Phase-1 disclosure fields on each post-``strict_verify`` ``SentenceVerification``
from the already-computed upstream signals — WITHOUT re-running or touching the verifier:
  * ``span_verdict``            = "SUPPORTS" if the sentence is verified, else "UNSUPPORTED" (SUPPORTS,
                                  not "EXISTS" — operator).
  * ``independent_origin_count`` = number of DISTINCT Phase-4 origin clusters among the sentence's cited
                                  evidence (unmapped evidence counts as its own origin).
  * ``credibility_weight``      = MIN Phase-2 credibility weight over the cited evidence (a sentence is
                                  only as credible as its weakest cited source); absent → None (unknown,
                                  never fabricated).
  * ``certainty_label``         = a deterministic, env-overridable bucket; UNKNOWN credibility → "low"
                                  (unknown must never inflate certainty — Codex #1157).

POSTURE (binding):
  * ADVISORY ONLY. NEVER changes ``is_verified`` / ``failure_reasons`` / ``tokens`` / ``sentence`` or any
    of ``strict_verify``'s six checks — they remain the only binding faithfulness gate. The four fields
    are side-outputs (Phase-1 proved them inert).
  * DEFAULT-OFF byte-identical: ``PG_SWEEP_CREDIBILITY_DISCLOSURE`` (no production caller; the RENDER that
    surfaces these fields is the flag-gated follow-up I-cred-008b).
  * PURE: inputs are NOT mutated — new verifications are produced with ``dataclasses.replace`` (so the
    module never imports ``provenance_generator`` / couples to the faithfulness path). LAW VI; snake_case.
"""
from __future__ import annotations

import dataclasses
import os
from typing import Any

_FLAG = "PG_SWEEP_CREDIBILITY_DISCLOSURE"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

_ENV_HIGH_CRED = "PG_DISCLOSURE_HIGH_CRED"
_ENV_LOW_CRED = "PG_DISCLOSURE_LOW_CRED"
_ENV_HIGH_MIN_ORIGINS = "PG_DISCLOSURE_HIGH_MIN_ORIGINS"
_DEFAULT_HIGH_CRED = 0.7
_DEFAULT_LOW_CRED = 0.4
_DEFAULT_HIGH_MIN_ORIGINS = 2

# A8 (I-arch-006) — SOFT, SURFACED-ONLY credibility flags. ADVISORY: they append a string to the SV's
# ``soft_warnings`` list (the existing disclosure carrier that already rides out to
# ``claim_disclosure.json``); they NEVER touch ``is_verified`` / ``span_verdict`` / the verifier, NEVER
# drop a source, NEVER gate or hold release (mirror of the supersession ``soft_warning`` pattern —
# §-1.3 WEIGHT/CONSOLIDATE, credibility is a LABEL not a DROP). Both default OFF (no caller passes the
# optional signal => byte-identical) and the env knobs only tune the (off-by-default) flag once enabled.
_ENV_MIN_HIGH_CRED_CORROBORATORS = "PG_DISCLOSURE_LEGAL_MIN_HIGH_CRED_CORROBORATORS"
_DEFAULT_MIN_HIGH_CRED_CORROBORATORS = 1
# The marker strings are stable identifiers (a renderer maps them to human text), kept short for the
# screen-reader / inline render and so a §-1.1 auditor can grep them.
WARN_LEGAL_NO_HIGH_CRED_CORROBORATOR = (
    "legal_claim_no_high_credibility_corroborator: this load-bearing legal claim rests only on "
    "lower-credibility source(s); no high-credibility corroborator was found (advisory flag — the "
    "claim is NOT dropped and the report is NOT held)"
)
WARN_BLANK_BIBLIOGRAPHY_TITLE = (
    "metadata_quality_blank_bibliography_title: a cited source has a blank or degenerate "
    "bibliography title (metadata-quality label only — does not affect verification or release)"
)


def _blank_or_degenerate_title(title: Any) -> bool:
    """True when a bibliography title is missing / whitespace / a degenerate placeholder.

    A pure, deterministic metadata-quality predicate (A8). It is a SURFACE label only; it never
    drops the source and never touches verification. ``None`` and non-strings count as blank.
    """
    if title is None:
        return True
    text = str(title).strip()
    if not text:
        return True
    lowered = text.lower()
    # Common degenerate placeholders observed in scraped bibliographies (soft-404 / chrome furniture).
    degenerate = {"untitled", "no title", "n/a", "na", "page not found", "404 not found", "-"}
    return lowered in degenerate


def legal_corroborator_soft_warning(
    *,
    is_verified: bool,
    credibility_values: list,
    high_cred_threshold: float,
    min_high_cred_corroborators: int,
) -> str | None:
    """A8 SOFT flag: a load-bearing legal claim that lacks >= N high-credibility corroborator(s).

    Returns the stable ``WARN_LEGAL_NO_HIGH_CRED_CORROBORATOR`` marker string, or ``None`` when the
    claim DOES have enough high-credibility cited support (or has unknown credibility — unknown never
    fabricates a flag). PURE, advisory: the caller appends the string to ``soft_warnings``; this never
    drops the low-credibility source, never holds the report, never changes ``is_verified``.

    Only a VERIFIED claim is flagged: an unverified claim already carries the stronger "low / unverified"
    certainty label, so a second weaker flag would be noise (and §-1.3 says credibility is a WEIGHT, the
    verifier remains the only hard gate).
    """
    if not is_verified:
        return None
    known = [c for c in (credibility_values or []) if c is not None]
    if not known:
        # Unknown credibility must NOT fabricate a flag (mirror of certainty: unknown => no inflation).
        return None
    high_cred_count = sum(1 for c in known if c >= high_cred_threshold)
    if high_cred_count >= max(1, int(min_high_cred_corroborators)):
        return None
    return WARN_LEGAL_NO_HIGH_CRED_CORROBORATOR


def blank_title_metadata_warning(titles: list) -> str | None:
    """A8 metadata-quality SURFACE: any cited source with a blank / degenerate bibliography title.

    Returns the stable ``WARN_BLANK_BIBLIOGRAPHY_TITLE`` marker, or ``None`` when every cited title is
    present. PURE, advisory label only — never drops the source, never gates release.
    """
    for title in (titles or []):
        if _blank_or_degenerate_title(title):
            return WARN_BLANK_BIBLIOGRAPHY_TITLE
    return None


def credibility_disclosure_enabled() -> bool:
    """True unless ``PG_SWEEP_CREDIBILITY_DISCLOSURE`` is unset/falsey (default OFF => byte-identical)."""
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _cited_evidence_ids(sv: Any) -> list[str]:
    out: list[str] = []
    for token in (getattr(sv, "tokens", None) or []):
        eid = str(getattr(token, "evidence_id", "") or "")
        if eid:
            out.append(eid)
    return out


def _certainty_label(is_verified: bool, origin_count: int, credibility: float | None) -> str:
    """Deterministic, advisory certainty bucket. NEVER consulted by any verifier.

    ``origin_count`` is the count the row will SURFACE — i.e. when a basket is threaded
    (I-arch-002 [10] / design §5 FIX-4 Reading A) it is the basket's
    ``verified_support_origin_count``, so certainty is bucketed on the SAME verified count
    the row discloses (never the larger clustered/unverified count — that would let a row
    read "high / 1 verified origin", the inflation the redesign exists to remove).
    """
    if not is_verified:
        return "low"
    if credibility is None:
        return "low"  # unknown credibility must NOT inflate certainty (Codex #1157)
    high_cred = _float_env(_ENV_HIGH_CRED, _DEFAULT_HIGH_CRED)
    low_cred = _float_env(_ENV_LOW_CRED, _DEFAULT_LOW_CRED)
    high_min_origins = _int_env(_ENV_HIGH_MIN_ORIGINS, _DEFAULT_HIGH_MIN_ORIGINS)
    if origin_count >= high_min_origins and credibility >= high_cred:
        return "high"
    if origin_count < 1 or credibility < low_cred:
        return "low"
    return "moderate"


def _verified_count_by_cluster(baskets: Any) -> dict:
    """``claim_cluster_id -> verified_support_origin_count`` (the ONLY strengthening count,
    design §5). ISOLATED per-member verified origins — NEVER ``total_clustered_origin_count``
    (the clustered, not-verified count, which this overwrite exists to stop surfacing)."""
    out: dict[str, int] = {}
    for basket in (baskets or []):
        ccid = str(getattr(basket, "claim_cluster_id", "") or "")
        if not ccid:
            continue
        out[ccid] = int(getattr(basket, "verified_support_origin_count", 0) or 0)
    return out


def _surfaced_verified_count(
    cited: list,
    verified_by_cluster: dict,
    cluster_id_by_evidence: dict,
) -> int | None:
    """The basket ``verified_support_origin_count`` to SURFACE on this sentence.

    Multi-cluster-sentence rule (design §5 FIX-4): a sentence whose cited tokens span >1
    claim_cluster is verified PER-CLUSTER; the surfaced count is that claim's OWN basket
    count, NEVER the sentence-wide origin count and NEVER a sum/union across clusters. When
    a sentence cites tokens from several clusters we surface the CONSERVATIVE single-basket
    value — the MIN of the cited clusters' verified counts. MIN (not MAX) because the design's
    safety posture is "counts go DOWN; when in doubt keep separate" (§0/§9.2): a multi-cluster
    sentence is only as corroborated as the weakest cluster it leans on, and over-stating
    verified origins is the inflation direction the redesign exists to remove. The checkable
    invariant holds either way: ``surfaced <= max single-basket verified count``, never their
    sum. Returns ``None`` when NO cited evidence maps to any threaded basket (leaves the legacy
    clustered count in place for that row rather than fabricating a zero).
    """
    counts: list[int] = []
    for eid in cited:
        for ccid in (cluster_id_by_evidence.get(eid) or []):
            ccid = str(ccid)
            if ccid in verified_by_cluster:
                counts.append(verified_by_cluster[ccid])
    if not counts:
        return None
    return min(counts)


def populate_disclosure(
    verifications: list,
    credibility_by_evidence: dict,
    origin_by_evidence: dict,
    *,
    baskets: list | None = None,
    cluster_id_by_evidence: dict | None = None,
    load_bearing_by_sentence: dict | None = None,
    title_by_evidence: dict | None = None,
) -> list:
    """Return NEW ``SentenceVerification``s with the four disclosure fields populated — ADVISORY, pure.

    ``credibility_by_evidence``: ``evidence_id -> Phase-2 credibility_weight``.
    ``origin_by_evidence``: ``evidence_id -> Phase-4 origin_cluster_id``.
    Inputs are NOT mutated; ``strict_verify`` is NOT re-run; ``is_verified`` is NEVER changed.

    I-arch-002 [10] / design §5 FIX-4 (Reading A): when the per-claim ``baskets`` AND the
    ``cluster_id_by_evidence`` binding (both from ``CredibilityAnalysis``, P3.2) are threaded
    in, ``independent_origin_count`` is OVERWRITTEN with the sentence's basket
    ``verified_support_origin_count`` (ISOLATED per-member verified origins) instead of the
    clustered, not-verified origin count — and ``certainty_label`` is bucketed on that SAME
    verified count. This is a single OVERWRITE of the existing field (NOT a parallel new field),
    so it propagates to BOTH operator JSON emitters that read ``independent_origin_count``
    (``quantified_analysis.py``:539 and ``run_honest_sweep_r3.py``:353). When ``baskets`` /
    ``cluster_id_by_evidence`` are absent (default OFF), or a row's cited evidence maps to no
    threaded basket, the legacy clustered ``origin_count`` is surfaced BYTE-IDENTICALLY.

    A8 (I-arch-006) SOFT flags — both OPTIONAL, default None => byte-identical:
      * ``load_bearing_by_sentence``: ``id(sv) -> bool`` (or any caller key it indexes per-sv; see the
        per-sv lookup below) marking a claim as a LOAD-BEARING LEGAL claim. When True AND the claim's
        cited credibility lacks a high-credibility corroborator, append
        ``WARN_LEGAL_NO_HIGH_CRED_CORROBORATOR`` to ``soft_warnings``. Advisory ONLY — never drops the
        low-credibility source, never holds release, never touches ``is_verified``.
      * ``title_by_evidence``: ``evidence_id -> bibliography title`` so a blank/degenerate title surfaces
        ``WARN_BLANK_BIBLIOGRAPHY_TITLE`` as a metadata-quality label. Advisory ONLY.
    Both flags only ADD to the ``soft_warnings`` list (the existing supersession carrier); they touch no
    other field. With both None the loop never computes a flag and the output is byte-identical.
    """
    cred_map = {str(k): v for k, v in (credibility_by_evidence or {}).items()}
    origin_map = {str(k): str(v) for k, v in (origin_by_evidence or {}).items()}
    title_map = {str(k): v for k, v in (title_by_evidence or {}).items()}
    # ``load_bearing_by_sentence`` is keyed by ``id(sv)`` of the INPUT verification objects (the caller
    # builds it from the same list it passes in). Absent => no claim is load-bearing => no legal flag.
    load_bearing_map = dict(load_bearing_by_sentence or {})
    high_cred_threshold = _float_env(_ENV_HIGH_CRED, _DEFAULT_HIGH_CRED)
    min_high_cred = _int_env(_ENV_MIN_HIGH_CRED_CORROBORATORS, _DEFAULT_MIN_HIGH_CRED_CORROBORATORS)
    # OVERWRITE source (design §5 FIX-4 Reading A). Empty unless a real basket is threaded =>
    # _surfaced_verified_count returns None => legacy clustered count, byte-identical.
    verified_by_cluster = _verified_count_by_cluster(baskets)
    binding = {
        str(k): [str(c) for c in (v or [])]
        for k, v in (cluster_id_by_evidence or {}).items()
    }

    out: list = []
    for sv in (verifications or []):
        is_verified = bool(getattr(sv, "is_verified", False))
        cited = _cited_evidence_ids(sv)
        # Distinct origin clusters among cited evidence; an unmapped evidence is its own origin.
        origin_count = len({origin_map.get(eid, f"singleton::{eid}") for eid in cited})
        # I-arch-002 [10]: overwrite with the basket's ISOLATED-verified count when threaded;
        # None => leave the legacy clustered count (default-OFF byte-identity).
        surfaced = _surfaced_verified_count(cited, verified_by_cluster, binding)
        if surfaced is not None:
            origin_count = surfaced
        # MIN credibility over cited evidence (conservative — weakest cited source); absent -> None.
        creds = [cred_map[eid] for eid in cited if eid in cred_map and cred_map[eid] is not None]
        credibility = min(creds) if creds else None
        # A8 SOFT flags — append-only to soft_warnings; both no-op unless the caller threaded the
        # optional signal (default OFF => byte-identical). NEVER touch is_verified / span_verdict.
        new_warnings: list[str] = []
        if load_bearing_map.get(id(sv), False):
            legal_warn = legal_corroborator_soft_warning(
                is_verified=is_verified,
                credibility_values=[cred_map.get(eid) for eid in cited],
                high_cred_threshold=high_cred_threshold,
                min_high_cred_corroborators=min_high_cred,
            )
            if legal_warn:
                new_warnings.append(legal_warn)
        if title_map:
            blank_warn = blank_title_metadata_warning(
                [title_map.get(eid) for eid in cited if eid in title_map]
            )
            if blank_warn:
                new_warnings.append(blank_warn)
        replace_kwargs: dict = dict(
            span_verdict="SUPPORTS" if is_verified else "UNSUPPORTED",
            credibility_weight=credibility,
            independent_origin_count=origin_count,
            certainty_label=_certainty_label(is_verified, origin_count, credibility),
        )
        if new_warnings:
            existing = list(getattr(sv, "soft_warnings", None) or [])
            for w in new_warnings:
                if w not in existing:
                    existing.append(w)
            replace_kwargs["soft_warnings"] = existing
        out.append(dataclasses.replace(sv, **replace_kwargs))
    return out
