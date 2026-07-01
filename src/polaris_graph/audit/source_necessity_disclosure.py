"""WS-10 (I-deepfix-001) — Source Necessity SURFACING.

The min-vertex-cover / sole-supporter algorithm is ALREADY built and tested in
``scripts/dr_benchmark/deeptrace_scorer.py`` (``necessary_source_count`` /
``compute_deeptrace_metrics``). This module does NOT re-implement it. It is a thin, PURE
disclosure builder that SURFACES the source-necessity number (DeepTRACE metric VI) into the
run manifest / disclosure block, so:

  * the DeepTRACE metric #6 can be read back from a real run, and
  * an audit can see which listed sources are NECESSARY (sole supporter of >=1 relevant
    statement) versus REDUNDANT (their support for every relevant statement is corroborated
    by at least one other source, or they support no relevant statement).

§-1.3 (WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP): a "redundant" source is corroborated,
not useless. This module DISCLOSES the necessary/redundant split; it NEVER drops, caps, thins,
or filters a source. "Redundant" here means "removing it would leave no relevant statement
un-supported" — it stays in the corpus at full weight; we merely report that fact.

Kill switch: ``PG_SOURCE_NECESSITY_DISCLOSURE`` (default ON). When set to an OFF value the
builder returns ``None`` so a caller reverts byte-identically (no disclosure key emitted).

PURE / offline. The faithfulness engine is untouched.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence

from scripts.dr_benchmark.deeptrace_scorer import necessary_source_count

_ENV_FLAG = "PG_SOURCE_NECESSITY_DISCLOSURE"
_OFF_VALUES = ("", "0", "false", "off", "no")


def _disclosure_enabled() -> bool:
    """Default-ON kill switch. OFF values: '', '0', 'false', 'off', 'no' (case-insensitive)."""
    return os.getenv(_ENV_FLAG, "1").strip().lower() not in _OFF_VALUES


def _cited_source_count(
    citation_matrix: Sequence[Sequence[int]],
    n_sources: int,
) -> int:
    """Number of distinct listed sources cited by at least one statement (audit context only —
    never used to drop a source)."""
    cited: set[int] = set()
    for row in citation_matrix:
        for j in range(min(len(row), n_sources)):
            if row[j]:
                cited.add(j)
    return len(cited)


def build_source_necessity_disclosure(
    citation_matrix: Sequence[Sequence[int]],
    support_matrix: Sequence[Sequence[int]],
    relevant: Sequence[bool],
    n_sources: int,
) -> Optional[dict[str, Any]]:
    """Build the source-necessity disclosure for a rendered run.

    Reuses ``necessary_source_count`` from the WS-14 DeepTRACE scorer (the sole-supporter reading:
    a source is NECESSARY iff it is the only supporter of at least one relevant, supported
    statement). Redundant = listed - necessary (corroborated or non-supporting sources).

    Args:
        citation_matrix: ``C[i][j] == 1`` iff statement ``i`` cites source ``j``. Used only for
            audit context (cited-source count) in the human-readable string; never to drop.
        support_matrix: ``S[i][j] == 1`` iff source ``j`` supports statement ``i`` (per the judge).
        relevant: ``relevant[i]`` is True iff statement ``i`` is relevant.
        n_sources: number of listed sources in the report.

    Returns:
        A dict with ``necessary_sources``, ``listed_sources``, ``source_necessity_ratio``,
        ``redundant_sources`` and a human-readable ``disclosure`` string — or ``None`` when the
        ``PG_SOURCE_NECESSITY_DISCLOSURE`` kill switch is OFF (byte-identical revert).
    """
    if not _disclosure_enabled():
        return None

    n = int(n_sources) if n_sources else 0
    if n < 0:
        n = 0

    # Sole-supporter count via the ALREADY-tested scorer. It bounds columns by min(len(row), n),
    # so its result never exceeds n; redundant is therefore always non-negative.
    necessary = necessary_source_count(support_matrix, relevant, n)
    redundant = max(0, n - necessary)
    ratio = (necessary / n) if n else 0.0
    cited = _cited_source_count(citation_matrix, n)

    disclosure = (
        "Source necessity (DeepTRACE metric VI, sole-supporter reading): "
        f"{necessary} of {n} listed sources are NECESSARY (each is the only supporter of at "
        f"least one relevant statement); {redundant} are redundant (their support for every "
        "relevant statement is corroborated by another source, or they support no relevant "
        f"statement). {cited} of {n} listed sources are cited. Necessity ratio "
        f"{ratio:.4f}. DISCLOSURE ONLY — redundant means corroborated, not dropped; every "
        "source stays in the corpus at full weight (WEIGHT-and-CONSOLIDATE)."
    )

    return {
        "necessary_sources": necessary,
        "listed_sources": n,
        "source_necessity_ratio": round(ratio, 4),
        "redundant_sources": redundant,
        "disclosure": disclosure,
    }
