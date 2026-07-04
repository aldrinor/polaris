"""X1 behavioral test — internal-DB / large-attachment retrieval backend.

Proves the EFFECT in real ingested+surfaced output (RED→GREEN, $0 offline):

  * WEIGHT lifts, it does NOT filter — two internal docs with IDENTICAL content
    (hence identical relevance) surface in institutional-weight order: the
    ``internal_db`` doc (higher operator-set weight) ABOVE the default-class
    doc. If the backend ignored institutional weight, this ordering assert FAILS.
  * CONSOLIDATE, don't DROP — every ingested doc appears in the surfaced pool;
    the low-weight doc is KEPT, never dropped to hit a number.
  * Relevance still governs — an off-topic HIGH-weight doc ranks BELOW an
    on-topic doc, so the weight is a lift, not a rank-then-drop filter.
  * FAIL LOUD — a missing configured root and an empty-corpus config raise.
  * DISCLOSURE — each candidate carries its institutional weight + weight_basis
    in metadata.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.scale.local_corpus_backend import (
    LocalCorpusBackend,
    LocalCorpusConfig,
    LocalCorpusError,
)
from tests.polaris_graph.scale._fake_embed import fake_embed

_QUERY = "renal impairment creatinine clearance dose adjustment"
_ON_TOPIC = (
    "Renal impairment requires creatinine clearance based dose adjustment to "
    "avoid nephrotoxicity in patients with reduced glomerular filtration."
)
_OFF_TOPIC = (
    "Quarterly marketing spend on billboard advertising rose in the northern "
    "sales district with no clinical content whatsoever."
)


def _make_corpus(tmp_path):
    # internal_db/ → high operator-set weight (0.72). IDENTICAL title+text to the
    # low-weight doc below, so relevance is exactly equal and institutional
    # WEIGHT is the SOLE differentiator of rank.
    (tmp_path / "internal_db").mkdir()
    (tmp_path / "internal_db" / "high.json").write_text(
        json.dumps({"title": "clinical record", "text": _ON_TOPIC}),
        encoding="utf-8",
    )
    # root-level file → default class 'unclassified_internal' (0.30), SAME content.
    (tmp_path / "low.json").write_text(
        json.dumps({"title": "clinical record", "text": _ON_TOPIC}),
        encoding="utf-8",
    )
    # high-weight but OFF-topic → must rank below on-topic docs (relevance rules)
    (tmp_path / "internal_db" / "offtopic.json").write_text(
        json.dumps({"title": "clinical record", "text": _OFF_TOPIC}),
        encoding="utf-8",
    )
    return tmp_path


def test_institutional_weight_lifts_equal_relevance_doc(tmp_path):
    _make_corpus(tmp_path)
    cfg = LocalCorpusConfig.from_env(roots=[tmp_path])
    backend = LocalCorpusBackend(cfg)
    n = backend.ingest(fake_embed)
    assert n == 3

    ranked = backend.search(_QUERY, fake_embed)

    # No drop: the full pool surfaces.
    assert len(ranked) == 3
    urls = {c.url for c in ranked}
    assert any("high.json" in u for u in urls)
    assert any("low.json" in u for u in urls)
    assert any("offtopic.json" in u for u in urls)

    # Locate the two equal-relevance docs.
    high = next(c for c in ranked if "internal_db/high.json" in c.url)
    low = next(c for c in ranked if c.url.endswith("low.json"))
    offtopic = next(c for c in ranked if "offtopic.json" in c.url)

    # Same content → same relevance.
    assert high.metadata["relevance"] == pytest.approx(low.metadata["relevance"])

    # WEIGHT LIFTS: higher institutional weight → higher weight_mass → ranked first.
    assert high.metadata["institutional_weight"] > low.metadata["institutional_weight"]
    assert high.metadata["weight_mass"] > low.metadata["weight_mass"]
    order = [c.url for c in ranked]
    assert order.index(high.url) < order.index(low.url)

    # RELEVANCE still governs: off-topic high-weight doc ranks LAST despite its
    # high institutional weight — weight is a lift, not a filter that overrides
    # relevance.
    assert offtopic.metadata["relevance"] < high.metadata["relevance"]
    assert order.index(offtopic.url) == 2

    # DISCLOSURE: institutional weight + basis are surfaced in metadata.
    assert high.metadata["weight_basis"] == "operator_set_institutional"
    assert high.metadata["source_class"] == "internal_db"


def test_low_weight_source_is_kept_not_dropped(tmp_path):
    # A pile of low-weight docs must ALL survive — no cap/thin.
    (tmp_path / "unclassified_internal").mkdir()
    for i in range(12):
        (tmp_path / "unclassified_internal" / f"doc_{i}.json").write_text(
            json.dumps({"title": f"low {i}", "text": _ON_TOPIC + f" variant {i}"}),
            encoding="utf-8",
        )
    cfg = LocalCorpusConfig.from_env(roots=[tmp_path])
    backend = LocalCorpusBackend(cfg)
    n = backend.ingest(fake_embed)
    assert n == 12
    ranked = backend.search(_QUERY, fake_embed)
    assert len(ranked) == 12  # every low-weight source kept


def test_missing_root_fails_loud(tmp_path):
    missing = tmp_path / "does_not_exist"
    cfg = LocalCorpusConfig.from_env(roots=[missing])
    backend = LocalCorpusBackend(cfg)
    with pytest.raises(LocalCorpusError):
        backend.ingest(fake_embed)


def test_no_root_configured_fails_loud(monkeypatch):
    monkeypatch.delenv("PG_LOCAL_CORPUS_ROOTS", raising=False)
    with pytest.raises(LocalCorpusError):
        LocalCorpusConfig.from_env()


def test_search_before_ingest_fails_loud(tmp_path):
    (tmp_path / "internal_db").mkdir()
    cfg = LocalCorpusConfig.from_env(roots=[tmp_path])
    backend = LocalCorpusBackend(cfg)
    with pytest.raises(LocalCorpusError):
        backend.search(_QUERY, fake_embed)
