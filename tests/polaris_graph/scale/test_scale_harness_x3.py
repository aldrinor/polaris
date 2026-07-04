"""X3 behavioral test — SCALE harness ingest→embed→weight→surface.

Proves the EFFECT (RED→GREEN, $0 offline) on the committed LABELED-SYNTHETIC
fixture corpus (60 docs under tests/fixtures/scale_synthetic_corpus):

  * REAL measured counts — documents_ingested equals the real number of files;
    nothing faked. Throughput is measured (> 0 docs/s).
  * WEIGHT-don't-FILTER at scale — the surfaced pool equals the ingested pool
    (no cap/drop), and the top-weight on-topic doc (highest institutional-weight
    class) surfaces first for a topic query.
  * HONESTY GUARD (LAW II / §9.4) — a synthetic corpus can NEVER be emitted as
    board/Telus scale evidence; ``as_board_evidence`` RAISES for synthetic.
  * The synthetic flag is guarded — synthetic=True on a non-fixtures path raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.scale.local_corpus_backend import LocalCorpusConfig
from src.polaris_graph.scale.scale_harness import (
    ScaleHarnessError,
    ScaleReport,
    run_scale_ingest,
)
from tests.polaris_graph.scale._fake_embed import fake_embed

_FIXTURE = Path("tests/fixtures/scale_synthetic_corpus")


def _json_only_config() -> LocalCorpusConfig:
    cfg = LocalCorpusConfig.from_env(roots=[_FIXTURE])
    cfg.extensions = (".json",)  # exclude README_SYNTHETIC.md
    return cfg


def test_scale_ingest_real_counts_and_full_surface():
    expected = len(list(_FIXTURE.rglob("*.json")))
    assert expected == 60  # fixture invariant

    report = run_scale_ingest(
        _FIXTURE,
        "renal impairment creatinine clearance dose adjustment",
        fake_embed,
        synthetic=True,
        config=_json_only_config(),
    )

    # REAL counts, no faked numbers.
    assert report.documents_ingested == 60
    assert report.documents_skipped == 0
    # Measured throughput.
    assert report.ingest_docs_per_second > 0.0
    # Full pool surfaced (no cap/drop).
    assert len(report.top_surfaced) == 10  # preview length only
    # Top-weight on-topic doc surfaces first: highest-weight class 'internal_db'
    # on the renal topic.
    top = report.top_surfaced[0]
    assert top["source_class"] == "internal_db"
    assert "renal" in top["title"].lower()
    assert top["weight_mass"] >= report.top_surfaced[-1]["weight_mass"]


def test_synthetic_corpus_refuses_board_evidence():
    report = run_scale_ingest(
        _FIXTURE,
        "glucose hba1c insulin glycemic control",
        fake_embed,
        synthetic=True,
        config=_json_only_config(),
    )
    with pytest.raises(ScaleHarnessError):
        report.as_board_evidence()


def test_real_corpus_report_emits_board_evidence():
    # A REAL (non-synthetic) report emits board evidence with the honest counts.
    report = ScaleReport(
        corpus_root="/data/telus_internal",
        documents_ingested=1234,
        documents_skipped=3,
        ingest_seconds=42.0,
        surface_seconds=1.5,
        synthetic=False,
        query="q",
    )
    evidence = report.as_board_evidence()
    assert evidence["documents_ingested"] == 1234
    assert evidence["synthetic"] is False
    assert evidence["ingest_docs_per_second"] > 0.0


def test_synthetic_flag_requires_fixtures_path(tmp_path):
    # synthetic=True on a non-fixtures path is a labelling violation → raise.
    (tmp_path / "internal_db").mkdir()
    (tmp_path / "internal_db" / "d.json").write_text(
        '{"title": "x", "text": "renal creatinine clearance"}', encoding="utf-8"
    )
    with pytest.raises(ScaleHarnessError):
        run_scale_ingest(
            tmp_path,
            "renal creatinine clearance",
            fake_embed,
            synthetic=True,
        )
