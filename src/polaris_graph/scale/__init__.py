"""POLARIS SCALE workstream (WORKSTREAM X, I-deepfix-001 #1344).

Capability-first Telus SCALE deliverable — a parallel track that EARNS
internal-DB access by demonstrating the SAME weight-and-consolidate pipeline
at scale on a large internal DB + big attachment pile.

Modules here are NEW and self-contained (parallel-safety): they never edit the
existing retrieval / generator / synthesis files. They funnel ingested internal
documents into the SAME weighted pipeline by emitting the SAME ``SearchCandidate``
shape carrying an operator-set INSTITUTIONAL weight (disclosed), and they rank by
the SAME ``weight_mass`` semantics — a WEIGHT into the existing machine.

DNA (CLAUDE.md §-1.3): WEIGHT don't FILTER; CONSOLIDATE don't DROP; the
faithfulness engine is the only hard gate. Nothing here caps / targets / thins /
drops a source to move a number. Low-weight internal docs STAY at low weight.
"""

from src.polaris_graph.scale.local_corpus_backend import (
    LocalCorpusBackend,
    LocalCorpusConfig,
    LocalCorpusError,
)
from src.polaris_graph.scale.mineru_vllm_config import (
    MineruBackendConfigError,
    MineruVllmConfig,
    resolve_mineru_backend,
)
from src.polaris_graph.scale.scale_harness import (
    ScaleHarnessError,
    ScaleReport,
    run_scale_ingest,
)

__all__ = [
    "LocalCorpusBackend",
    "LocalCorpusConfig",
    "LocalCorpusError",
    "MineruBackendConfigError",
    "MineruVllmConfig",
    "resolve_mineru_backend",
    "ScaleHarnessError",
    "ScaleReport",
    "run_scale_ingest",
]
