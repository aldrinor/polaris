"""WS-10 (I-deepfix-001) — Source Necessity SURFACING.

The DeepTRACE metric VI algorithm is ALREADY built and tested in
``scripts/dr_benchmark/deeptrace_scorer.py`` (``minimum_source_cover_size`` /
``necessary_source_count`` / ``compute_deeptrace_metrics``). This module does NOT re-implement it.
It is a thin, PURE disclosure builder that SURFACES the source-necessity number (DeepTRACE metric
VI) into the run manifest / disclosure block, so:

  * the DeepTRACE metric #6 can be read back from a real run, and
  * an audit can see the MINIMUM SOURCE COVER — the fewest listed sources whose union still supports
    every supported relevant statement — versus the redundant remainder.

Metric VI (per arXiv 2509.04499, "minimum vertex cover for source nodes") =
``size_of_minimum_source_cover / n_listed_sources``. The minimum cover is computed by greedy set
cover (the official answer-engine-eval reference implementation) in the WS-14 scorer. A statement
supported by two sources therefore contributes cover size 1 (necessity 0.5 of 2 listed), NOT 0 — the
old SOLE-supporter reading (a source that is the only supporter of some statement) understated it.
The sole-supporter count is retained here as a SECONDARY disclosure field ``n_sole_supporter`` (it is
a lower bound on the cover size), so nothing is lost.

§-1.3 (WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP): a "redundant" source is corroborated, not
useless. This module DISCLOSES the cover/redundant split; it NEVER drops, caps, thins, or filters a
source. "Redundant" here means "not in the minimum cover — every supported relevant statement it
supports is also covered by a cover source" — it stays in the corpus at full weight; we merely report
that fact.

Kill switch: ``PG_SOURCE_NECESSITY_DISCLOSURE`` (default ON). When set to an OFF value the builder
returns ``None`` so a caller reverts byte-identically (no disclosure key emitted).

PURE / offline. The faithfulness engine is untouched.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence

from scripts.dr_benchmark.deeptrace_scorer import (
    minimum_source_cover_size,
    necessary_source_count,
)

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

    Reuses ``minimum_source_cover_size`` from the WS-14 DeepTRACE scorer (the min-vertex-cover
    reading: the fewest listed sources whose union supports every supported relevant statement).
    Redundant = listed - cover-size (sources not needed by the minimum cover). The old sole-supporter
    count is surfaced as the SECONDARY field ``n_sole_supporter`` so nothing is lost.

    Args:
        citation_matrix: ``C[i][j] == 1`` iff statement ``i`` cites source ``j``. Used only for
            audit context (cited-source count) in the human-readable string; never to drop.
        support_matrix: ``S[i][j] == 1`` iff source ``j`` supports statement ``i`` (per the judge).
        relevant: ``relevant[i]`` is True iff statement ``i`` is relevant.
        n_sources: number of listed sources in the report.

    Returns:
        A dict with ``necessary_sources`` (= minimum source cover size), ``listed_sources``,
        ``source_necessity_ratio``, ``redundant_sources``, ``n_sole_supporter`` (secondary) and a
        human-readable ``disclosure`` string — or ``None`` when the ``PG_SOURCE_NECESSITY_DISCLOSURE``
        kill switch is OFF (byte-identical revert).
    """
    if not _disclosure_enabled():
        return None

    n = int(n_sources) if n_sources else 0
    if n < 0:
        n = 0

    # Minimum source cover size via the ALREADY-tested scorer (greedy set cover). It bounds columns by
    # min(len(row), n), so its result never exceeds n; redundant is therefore always non-negative.
    necessary = minimum_source_cover_size(support_matrix, relevant, n)
    redundant = max(0, n - necessary)
    ratio = (necessary / n) if n else 0.0
    cited = _cited_source_count(citation_matrix, n)
    # SECONDARY disclosure retained so nothing is lost: the old sole-supporter count (lower bound).
    n_sole_supporter = necessary_source_count(support_matrix, relevant, n)

    disclosure = (
        "Source necessity (DeepTRACE metric VI, minimum source cover): "
        f"{necessary} of {n} listed sources form the MINIMUM COVER (the fewest sources whose union "
        f"still supports every supported relevant statement); {redundant} are redundant (not needed "
        "by the minimum cover — every supported relevant statement they support is also covered by a "
        f"cover source). {cited} of {n} listed sources are cited. Necessity ratio {ratio:.4f}. "
        f"Sole-supporter count (secondary): {n_sole_supporter}. DISCLOSURE ONLY — redundant means "
        "corroborated, not dropped; every source stays in the corpus at full weight "
        "(WEIGHT-and-CONSOLIDATE)."
    )

    return {
        "necessary_sources": necessary,
        "listed_sources": n,
        "source_necessity_ratio": round(ratio, 4),
        "redundant_sources": redundant,
        "n_sole_supporter": n_sole_supporter,
        "disclosure": disclosure,
    }
