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
    """Deterministic, advisory certainty bucket. NEVER consulted by any verifier."""
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


def populate_disclosure(
    verifications: list,
    credibility_by_evidence: dict,
    origin_by_evidence: dict,
) -> list:
    """Return NEW ``SentenceVerification``s with the four disclosure fields populated — ADVISORY, pure.

    ``credibility_by_evidence``: ``evidence_id -> Phase-2 credibility_weight``.
    ``origin_by_evidence``: ``evidence_id -> Phase-4 origin_cluster_id``.
    Inputs are NOT mutated; ``strict_verify`` is NOT re-run; ``is_verified`` is NEVER changed.
    """
    cred_map = {str(k): v for k, v in (credibility_by_evidence or {}).items()}
    origin_map = {str(k): str(v) for k, v in (origin_by_evidence or {}).items()}

    out: list = []
    for sv in (verifications or []):
        is_verified = bool(getattr(sv, "is_verified", False))
        cited = _cited_evidence_ids(sv)
        # Distinct origin clusters among cited evidence; an unmapped evidence is its own origin.
        origin_count = len({origin_map.get(eid, f"singleton::{eid}") for eid in cited})
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
