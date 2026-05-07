"""Sovereignty guard: legal-cleared spans only (I-f15-006).

A bundle MUST refuse to ship verbatim source-text snapshots for sources
whose provenance does NOT explicitly declare `legal_cleared = True`.
The full EvidencePool (including every Source.full_text/snippet) is
serialized into evidence_pool.json by the bundle builder, so EVERY
source in the pool — cited or not — must be cleared.
"""

from __future__ import annotations

from polaris_graph.retrieval2.evidence_pool import EvidencePool

LEGAL_CLEARED_KEY = "legal_cleared"


def assert_all_pool_sources_legal_cleared(pool: EvidencePool) -> None:
    """Raise ValueError if any pool source lacks `provenance.legal_cleared = True`.

    Walks EVERY source in the pool (not only cited ones) because the
    full pool serializes into evidence_pool.json — uncited sources still
    get their full_text/snippet redistributed.
    """
    for source in pool.sources:
        if source.provenance.get(LEGAL_CLEARED_KEY) is not True:
            raise ValueError(
                f"copyrighted span: source {source.source_id!r} not legally "
                f"cleared for audit bundle redistribution"
            )
