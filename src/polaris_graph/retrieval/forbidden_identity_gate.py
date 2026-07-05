"""P0-1 forbidden-source-by-IDENTITY pre-composition scope gate (I-deepfix-001).

The blocked-reference deny-list (``blocked_reference_registry``) removes an operator-PROHIBITED
source at fetch and at the corpus/selection seams. This module is the LAST-line, claim-level
backstop: given claim units that each carry their supporting sources, it REDACTS any claim
whose supporting source has a forbidden IDENTITY (DOI / DOAJ id / PII / title+author) —
**REGARDLESS of the D8 entailment verdict** on that claim.

Why regardless of D8: the leak this closes is a blocked mirror that was span-verified and
counted as VERIFIED independent SUPPORT in the corroboration / necessity ledgers. A claim can
be perfectly entailment-SUPPORTED and still be non-compliant if its support is an operator
do-not-view source. Compliance is a prohibition, NOT a faithfulness call — so the gate never
looks at the entailment / verdict field. This STRENGTHENS the faithfulness engine (it drops
MORE unfaithful/forbidden text); it never relaxes it.

Fail-LOUD: every redaction is logged AND written to a disclosed-redaction telemetry file —
never a silent drop. Empty registry (no appendix / kill-switch OFF) => the ORIGINAL claims
object is returned unchanged (byte-identical no-op). Pure / no network; never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from src.polaris_graph.retrieval.blocked_reference_registry import (
    BlockedRegistry,
    is_blocked_source,
)

logger = logging.getLogger("polaris_graph.forbidden_identity_gate")

# The keys under which a claim unit may carry its supporting sources (dict OR object).
_SUPPORT_KEYS = (
    "supporting_sources",
    "sources",
    "support",
    "supports",
    "citations",
    "basket",
    "members",
    "evidence",
)
_CLAIM_ID_KEYS = ("claim_id", "id", "claim_hash", "clm_hash", "num")


def _claim_field(claim: "Any", *names: str) -> "Any":
    if isinstance(claim, Mapping):
        for n in names:
            if n in claim and claim.get(n) is not None:
                return claim.get(n)
        return None
    for n in names:
        v = getattr(claim, n, None)
        if v is not None:
            return v
    return None


def _claim_supporting_sources(claim: "Any") -> list[Any]:
    """Every supporting-source unit a claim carries, across the known field shapes."""
    out: list[Any] = []
    for key in _SUPPORT_KEYS:
        val = _claim_field(claim, key)
        if val is None:
            continue
        if isinstance(val, (list, tuple)):
            out.extend(val)
        else:
            out.append(val)
    return out


def _claim_id(claim: "Any", index: int) -> str:
    cid = _claim_field(claim, *_CLAIM_ID_KEYS)
    return str(cid) if cid is not None else f"claim_{index}"


def scope_gate_redact_claims(
    claims: "list[Any] | None",
    registry: "BlockedRegistry | None",
    *,
    log: "Any" = None,
    run_dir: "Any" = None,
    label: str = "",
) -> "tuple[list[Any], list[dict[str, str]]]":
    """Redact every claim whose supporting source has a forbidden identity (P0-1 (c)).

    Returns ``(kept_claims, redacted_records)``. The verdict / entailment field of a claim is
    NEVER consulted — a forbidden support redacts the claim even when it is D8-SUPPORTED.

    Empty/None registry => the SAME ``claims`` object is returned + ``[]`` (byte-identical
    no-op, no telemetry written). Fail-LOUD on every redaction; never raises."""
    if claims is None:
        return ([], [])
    if registry is None or getattr(registry, "is_empty", True):
        return (claims, [])

    kept: list[Any] = []
    redacted: list[dict[str, str]] = []
    for idx, claim in enumerate(claims):
        hit_reason = ""
        blocked_url = ""
        try:
            for src in _claim_supporting_sources(claim):
                _hit, _reason = is_blocked_source(src, registry)
                if _hit:
                    hit_reason = _reason
                    _u = src.get("url") if isinstance(src, Mapping) else getattr(src, "url", "")
                    blocked_url = str(_u or "")
                    break
        except Exception as exc:  # noqa: BLE001 — never let a bad claim abort the gate
            logger.warning("[forbidden_identity_gate] claim scan skipped: %s", exc)
        if hit_reason:
            redacted.append(
                {
                    "claim_id": _claim_id(claim, idx),
                    "blocked_source_url": blocked_url[:300],
                    "reason": f"forbidden_identity:{hit_reason}"[:300],
                }
            )
        else:
            kept.append(claim)

    if redacted:
        _seam = f" [{label}]" if label else ""
        if log is not None:
            log(
                f"[forbidden_identity_gate]{_seam} REDACTED {len(redacted)} claim(s) "
                f"({len(claims)} -> {len(kept)}) whose supporting source is on the operator "
                "do-not-view deny-list [regardless of D8 verdict]"
            )
        if run_dir is not None:
            _fname = (
                "scope_gate_redacted.json"
                if not label
                else f"scope_gate_redacted_{label}.json"
            )
            try:
                (run_dir / _fname).write_text(
                    json.dumps(redacted, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8",
                )
            except Exception as _wx:  # noqa: BLE001 — telemetry best-effort
                if log is not None:
                    log(
                        f"[forbidden_identity_gate]{_seam} redaction-telemetry write "
                        f"skipped: {_wx}"
                    )

    return (kept, redacted)
