"""X3 — SCALE harness: ingest→embed→weight→surface over a large corpus.

The Telus capability demonstration. Current runs are single-question scale;
large-corpus ingest→embed→rerank→tier-weight→surface THROUGHPUT is unproven in
the rendered pipeline. This harness drives the X1 local-corpus backend at scale
and measures REAL throughput + verifies the correct top-weight evidence
surfaces fast under bounded parallelism.

HONESTY (LAW II / §9.4): the Telus SCALE evidence must be REAL public/private
ingestion, never a synthetic demonstration. A synthetic corpus is a
test/fixture ONLY: it must live under ``tests/fixtures/`` and be flagged
``synthetic=True`` here. When flagged synthetic, :meth:`ScaleReport.as_board_evidence`
REFUSES to emit — a synthetic corpus can never be presented as a real scale
result or mixed into a scored board run. Document counts are the REAL ingested
counts; nothing is faked.

DNA (§-1.3): this is the SAME weight-and-consolidate pipeline demonstrated at
scale — no caps, no targets, no thinners, no faked numbers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.polaris_graph.scale.local_corpus_backend import (
    LocalCorpusBackend,
    LocalCorpusConfig,
    LocalCorpusError,
)

logger = logging.getLogger("polaris_graph.scale.harness")


class ScaleHarnessError(RuntimeError):
    """Raised when the scale harness cannot honour its honesty contract."""


@dataclass
class ScaleReport:
    """A REAL, measured scale-ingestion report (no faked numbers)."""

    corpus_root: str
    documents_ingested: int
    documents_skipped: int
    ingest_seconds: float
    surface_seconds: float
    synthetic: bool
    top_surfaced: list[dict[str, Any]] = field(default_factory=list)
    query: str = ""

    @property
    def ingest_docs_per_second(self) -> float:
        if self.ingest_seconds <= 0:
            return 0.0
        return self.documents_ingested / self.ingest_seconds

    def as_board_evidence(self) -> dict[str, Any]:
        """Return the report as board/Telus scale evidence.

        FAIL LOUD (§9.4): a synthetic corpus is a test fixture and MUST NOT be
        presented as a real scale result. This refuses to emit board evidence
        for a synthetic run.
        """
        if self.synthetic:
            raise ScaleHarnessError(
                "Refusing to emit board evidence from a SYNTHETIC corpus. "
                "Synthetic corpora are test fixtures only (LAW II / §9.4); the "
                "Telus SCALE evidence must be REAL public/private ingestion."
            )
        return {
            "corpus_root": self.corpus_root,
            "documents_ingested": self.documents_ingested,
            "documents_skipped": self.documents_skipped,
            "ingest_docs_per_second": round(self.ingest_docs_per_second, 4),
            "ingest_seconds": round(self.ingest_seconds, 4),
            "surface_seconds": round(self.surface_seconds, 4),
            "query": self.query,
            "top_surfaced": self.top_surfaced,
            "synthetic": False,
        }


def run_scale_ingest(
    corpus_root: str | Path,
    query: str,
    embed_fn: Callable[[list[str]], list[list[float]]],
    *,
    synthetic: bool,
    config: LocalCorpusConfig | None = None,
    top_n_preview: int = 10,
) -> ScaleReport:
    """Ingest ``corpus_root`` at scale and surface top-weight evidence for ``query``.

    ``synthetic`` MUST be stated explicitly by the caller — there is no default,
    so a synthetic fixture can never accidentally masquerade as a real corpus.
    A synthetic corpus is REQUIRED to live under a ``tests/fixtures`` path
    (fail-loud guard), matching §9.4.

    Returns a ``ScaleReport`` with REAL measured counts + timings.
    """
    root = Path(corpus_root)
    if synthetic and "fixtures" not in {p.lower() for p in root.parts}:
        raise ScaleHarnessError(
            f"synthetic=True but corpus_root {root} is not under a "
            "tests/fixtures path. A synthetic corpus MUST be a labelled fixture "
            "(LAW II / §9.4)."
        )

    cfg = config or LocalCorpusConfig.from_env(roots=[root])
    backend = LocalCorpusBackend(cfg)

    t0 = time.perf_counter()
    n_docs = backend.ingest(embed_fn)
    ingest_seconds = time.perf_counter() - t0

    t1 = time.perf_counter()
    surfaced = backend.search(query, embed_fn)
    surface_seconds = time.perf_counter() - t1

    if len(surfaced) != n_docs:
        # WEIGHT-don't-FILTER invariant: every ingested doc must surface. A
        # short surfaced list would mean something dropped sources.
        raise ScaleHarnessError(
            f"surface returned {len(surfaced)} of {n_docs} ingested docs — "
            "the harness must surface the FULL pool (no cap/drop, §-1.3)."
        )

    preview = [
        {
            "url": c.url,
            "title": c.title,
            "source_class": (c.metadata or {}).get("source_class"),
            "institutional_weight": (c.metadata or {}).get("institutional_weight"),
            "relevance": (c.metadata or {}).get("relevance"),
            "weight_mass": (c.metadata or {}).get("weight_mass"),
        }
        for c in surfaced[: max(0, top_n_preview)]
    ]

    report = ScaleReport(
        corpus_root=root.as_posix(),
        documents_ingested=n_docs,
        documents_skipped=len(backend.skipped),
        ingest_seconds=ingest_seconds,
        surface_seconds=surface_seconds,
        synthetic=synthetic,
        top_surfaced=preview,
        query=query,
    )
    logger.info(
        "scale harness: %d docs in %.3fs (%.1f docs/s), surfaced %d in %.3fs",
        n_docs,
        ingest_seconds,
        report.ingest_docs_per_second,
        len(surfaced),
        surface_seconds,
    )
    return report
