"""Signal B — institutional authority (the region generalizer).

Phase 0a (GH #983). Data-driven (LAW VI). ZERO host names in code.

Order of evidence (load-bearing, per brief §4 Signal B):
  1. ROR institution-type (OpenAlex authorships[].institutions[].ror) — LOAD-BEARING.
  2. PSL gov-style suffix on the host — FAST PRE-FILTER ONLY (a DNS boundary
     list, NOT a trust signal; misses canada.ca / bundesbank.de / rbi.org.in).
  3. Issuer self-description backstop — schema.org GovernmentOrganization /
     dc.publisher official-issuer pattern in the fetched structural content.

The ROR-type -> source_class map + the score weights + the PSL gov subset all
live in config/authority/{ror_type_class_map.yaml,psl_gov_suffixes.txt}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.polaris_graph.authority.source_class import (
    AuthorityConfidence,
    AuthoritySignals,
    SourceClass,
)

# Structural self-description regexes (NOT host names — schema.org / meta-tag
# shapes). These are the ONLY literals here and they are markup tokens, not
# hosts/suffixes/platforms, so they do not trip the S4 zero-host grep.
_SELF_DESC_OFFICIAL_RE = re.compile(
    r'"@type"\s*:\s*"GovernmentOrganization"'
    r'|<meta[^>]+name=["\']dc\.publisher["\'][^>]*'
    r'(?:ministry|government|regulatory|administration|authority)',
    re.IGNORECASE,
)


@dataclass
class SignalBResult:
    score: float
    source_class: SourceClass
    confidence: AuthorityConfidence
    reasons: list[str]
    fired: bool


def host_matches_gov_suffix(host: str, gov_suffixes: tuple[str, ...]) -> bool:
    """True if host equals or ends with '.'+suffix for any gov suffix."""
    if not host:
        return False
    host = host.lower().rstrip(".")
    for suffix in gov_suffixes:
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def _class_from_ror_type(
    inst_type: str, ror_map: dict
) -> tuple[SourceClass, AuthorityConfidence] | None:
    key = (inst_type or "").strip().lower()
    if not key:
        return None
    entry = ror_map["type_to_class"].get(key)
    if not entry:
        return None
    return SourceClass(entry["source_class"]), AuthorityConfidence(entry["confidence"])


def compute_signal_b(
    host: str,
    signals: AuthoritySignals,
    structural_content: str,
    ror_map: dict,
    gov_suffixes: tuple[str, ...],
) -> SignalBResult:
    """Compute institutional authority sub-score + a candidate source_class."""
    reasons: list[str] = []
    weights = ror_map["score_weights"]

    sub_scores: list[float] = []
    candidate_class: SourceClass | None = None
    candidate_conf: AuthorityConfidence | None = None

    # 1) ROR institution-type (load-bearing).
    ror_resolved = _class_from_ror_type(signals.institution_type, ror_map)
    if signals.ror_id and ror_resolved is not None:
        candidate_class, candidate_conf = ror_resolved
        sub_scores.append(weights["ror_resolved"])
        reasons.append(
            f"ROR institution type {signals.institution_type!r} "
            f"-> {candidate_class.value} (load-bearing)"
        )

    # 2) PSL gov-suffix pre-filter.
    if host_matches_gov_suffix(host, gov_suffixes):
        sub_scores.append(weights["psl_gov_suffix"])
        reasons.append("host carries a gov-style public suffix (PSL pre-filter)")
        if candidate_class is None:
            candidate_class = SourceClass.PRIMARY_OFFICIAL
            candidate_conf = AuthorityConfidence.MEDIUM

    # 3) Issuer self-description backstop.
    if structural_content and _SELF_DESC_OFFICIAL_RE.search(structural_content):
        sub_scores.append(weights["issuer_self_desc"])
        reasons.append("issuer self-describes as official (schema.org / dc.publisher)")
        if candidate_class is None:
            candidate_class = SourceClass.PRIMARY_OFFICIAL
            candidate_conf = AuthorityConfidence.LOW

    fired = bool(sub_scores)
    if not fired:
        return SignalBResult(
            score=ror_map["neutral_score"],
            source_class=SourceClass.UNKNOWN,
            confidence=AuthorityConfidence.LOW,
            reasons=["no institutional signal (no ROR, no gov suffix, no self-desc)"],
            fired=False,
        )

    return SignalBResult(
        score=max(sub_scores),
        source_class=candidate_class or SourceClass.UNKNOWN,
        confidence=candidate_conf or AuthorityConfidence.LOW,
        reasons=reasons,
        fired=True,
    )
