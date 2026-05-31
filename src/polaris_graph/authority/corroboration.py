"""Signal D — corroboration / Knowledge-Based-Trust (the sovereign multiplier).

Phase 0a (GH #983). Data-driven (LAW VI). ZERO host names in code.

`corroboration_count` = number of INDEPENDENT registrable domains (eTLD+1) in
the current corpus asserting the same finding (post dedup-by-finding).
Independence uses the shared PSL table for true eTLD+1 (NOT the bare host),
so subdomains of one institution don't double-count (brief R2).

Phase-0a behaviour: single-source scoring has no corpus context yet, so
`corroboration_count` defaults to 1; the FIELD is emitted now with a stable
schema (smoke asserts it is present + defaults honestly). Live wiring lands in
a later phase. KBT rationale: arXiv 1502.03519 (domain-general).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SignalDResult:
    score: float
    corroboration_count: int
    reasons: list[str]


def registrable_domain(host: str, gov_suffixes: tuple[str, ...]) -> str:
    """Best-effort eTLD+1 using the shared PSL gov table for multi-level suffixes.

    For a host whose tail matches a known multi-level public suffix (e.g.
    `go.jp`, `gc.ca`), keep one extra label (`mhlw.go.jp`). Otherwise fall back
    to the last two labels (the common single-level-TLD case). This is the
    eTLD+1 needed for Signal-D independence; it intentionally relies on the same
    versioned PSL snapshot Signal B uses rather than a code literal.
    """
    if not host:
        return ""
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    # Longest matching multi-level suffix from the PSL table.
    best_suffix_labels = 0
    for suffix in gov_suffixes:
        s_labels = suffix.split(".")
        if len(s_labels) >= 2 and labels[-len(s_labels):] == s_labels:
            if len(s_labels) > best_suffix_labels:
                best_suffix_labels = len(s_labels)
    if best_suffix_labels:
        keep = best_suffix_labels + 1
        return ".".join(labels[-keep:])
    return ".".join(labels[-2:])


def count_independent_hosts(
    hosts: list[str], gov_suffixes: tuple[str, ...]
) -> int:
    """Count distinct registrable domains across `hosts`."""
    domains = {registrable_domain(h, gov_suffixes) for h in hosts if h}
    domains.discard("")
    return len(domains)


def compute_signal_d(
    corroboration_count: int, blend_weights: dict
) -> SignalDResult:
    """Compute the corroboration sub-score from the independent-host count."""
    count = max(1, int(corroboration_count))
    log_norm = blend_weights["corroboration_log_norm"]
    raw = math.log1p(count - 1) / log_norm if log_norm > 0 else 0.0
    score = 0.0 if raw < 0.0 else (1.0 if raw > 1.0 else raw)
    reasons: list[str] = []
    if count <= 1:
        reasons.append("corroboration_count=1 (no independent corroboration yet)")
    else:
        reasons.append(f"corroboration_count={count} independent registrable domains")
    return SignalDResult(score=score, corroboration_count=count, reasons=reasons)
