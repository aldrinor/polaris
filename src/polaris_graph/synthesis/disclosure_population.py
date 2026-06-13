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
    """
    cred_map = {str(k): v for k, v in (credibility_by_evidence or {}).items()}
    origin_map = {str(k): str(v) for k, v in (origin_by_evidence or {}).items()}
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
        out.append(dataclasses.replace(
            sv,
            span_verdict="SUPPORTS" if is_verified else "UNSUPPORTED",
            credibility_weight=credibility,
            independent_origin_count=origin_count,
            certainty_label=_certainty_label(is_verified, origin_count, credibility),
        ))
    return out
