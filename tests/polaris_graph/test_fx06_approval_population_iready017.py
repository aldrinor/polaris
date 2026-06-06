"""FX-06 (I-ready-017 #1120): corpus-approval scores the SAME population as adequacy + the report.

Bug (held drb_72): corpus_approval.json scored the FINAL post-merge dist (total_sources=145, padded
with agentic junk) while corpus_adequacy.json was written PRE-merge (total_sources=45) — the gate
scored a different population than adequacy + the report consumed. FX-06 re-writes corpus_adequacy.json
from the FINAL dist and adds a fail-loud invariant `adequacy.total_sources == dist.total_sources`.

These component tests prove the invariant the orchestrator relies on: an adequacy computed from a
dist's tier_counts has total_sources == that dist's total_sources (so writing adequacy from the
final dist makes the two artifacts agree); and that a pre-merge adequacy diverges from a post-merge
dist (the bug the invariant catches). Offline, no network.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.polaris_graph.nodes.corpus_adequacy_gate import assess_corpus_adequacy
from src.polaris_graph.nodes.corpus_approval_gate import compute_tier_distribution

_PROTOCOL = {
    "expected_tier_distribution": [
        {"tier": "T1", "min_fraction": 0.10, "max_fraction": 0.90},
        {"tier": "T4", "min_fraction": 0.0, "max_fraction": 0.60},
    ]
}
# Held drb_72 corpus_adequacy tier_counts (sum = 45 = the report-consumed set).
_HELD_45 = {"T1": 6, "T2": 3, "T4": 23, "T5": 2, "T6": 7, "UNKNOWN": 4}


def _sources(tier_counts: dict[str, int]) -> list:
    out: list = []
    i = 0
    for tier, n in tier_counts.items():
        for _ in range(n):
            out.append(SimpleNamespace(tier=tier, url=f"https://example.org/s{i}"))
            i += 1
    return out


def test_fx06_invariant_holds_when_adequacy_from_same_dist():
    """FX-06's guarantee: adequacy written from `dist.tier_counts` has total_sources == dist's."""
    srcs = _sources(_HELD_45)
    dist = compute_tier_distribution(srcs, _PROTOCOL)
    adequacy = assess_corpus_adequacy(
        tier_counts=dist.tier_counts,
        evidence_row_count=len(srcs),
        domain="workforce",
        protocol=_PROTOCOL,
    )
    assert dist.total_sources == 45
    assert adequacy.total_sources == dist.total_sources  # the invariant the orchestrator asserts


def test_fx06_divergence_detected_pre_vs_post_merge():
    """The bug: a PRE-merge adequacy (45) vs the POST-merge dist the approval scores (~145).
    The FX-06 fail-loud invariant catches exactly this inequality."""
    pre_dist = compute_tier_distribution(_sources(_HELD_45), _PROTOCOL)
    pre_adequacy = assess_corpus_adequacy(
        tier_counts=pre_dist.tier_counts,
        evidence_row_count=45,
        domain="workforce",
        protocol=_PROTOCOL,
    )
    # Post-merge dist padded to ~145 (the held approval total_sources).
    post_dist = compute_tier_distribution(
        _sources({"T1": 54, "T4": 46, "UNKNOWN": 45}), _PROTOCOL
    )
    assert post_dist.total_sources == 145
    # Pre-merge adequacy vs post-merge approval population diverge — the FX-06 invariant fails loud.
    assert pre_adequacy.total_sources != post_dist.total_sources
    assert (pre_adequacy.total_sources, post_dist.total_sources) == (45, 145)
