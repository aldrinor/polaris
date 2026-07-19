"""Tests for the #958 fail-loud corpus-truncation gate signal. NO network / NO spend.

Asserts truncation is no longer a silent log WARNING: it is carried on LiveRetrievalResult, recorded in the
manifest's retrieval section by the SINGLE shared writer, exposed by a fail-safe predicate, and treated as
partial/invalid by the scorer backstop.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.benchmark.benchmark_run_capture import corpus_truncated_from_manifest
from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult


class _Retr:
    """Minimal retrieval-like object for the manifest-section writer."""
    def __init__(self, truncated, total, processed):
        self.total_candidates_pre_filter = 50
        self.candidates_fetched = processed
        self.candidates_failed_fetch = 0
        self.api_calls = {"fetch": processed}
        self.corpus_truncated = truncated
        self.candidates_total = total
        self.candidates_processed = processed


# ── predicate ────────────────────────────────────────────────────────────
def test_predicate_true_when_flagged():
    assert corpus_truncated_from_manifest({"retrieval": {"corpus_truncated": True}}) is True


def test_predicate_false_when_clean_or_absent():
    assert corpus_truncated_from_manifest({"retrieval": {"corpus_truncated": False}}) is False
    assert corpus_truncated_from_manifest({"retrieval": {}}) is False  # pre-#958 manifest
    assert corpus_truncated_from_manifest({}) is False
    assert corpus_truncated_from_manifest(None) is False  # type: ignore[arg-type]  fail-safe


# ── dataclass defaults ─────────────────────────────────────────────────────
def test_live_retrieval_result_defaults_not_truncated():
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[], total_candidates_pre_filter=0,
        candidates_kept_by_scope=0, candidates_kept_by_offtopic=0,
        candidates_fetched=0, candidates_failed_fetch=0,
    )
    assert r.corpus_truncated is False
    assert r.candidates_total == 0 and r.candidates_processed == 0


# ── shared manifest-section writer ──────────────────────────────────────────
def test_retrieval_manifest_section_carries_truncation():
    # imported lazily — run_honest_sweep_r3 is a heavy script module
    import importlib
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    sec = sweep._retrieval_manifest_section(_Retr(truncated=True, total=50, processed=12))
    assert sec["corpus_truncated"] is True
    assert sec["candidates_total"] == 50
    assert sec["candidates_processed"] == 12
    clean = sweep._retrieval_manifest_section(_Retr(truncated=False, total=50, processed=50))
    assert clean["corpus_truncated"] is False
    assert clean["candidates_processed"] == 50


# ── scorer backstop ─────────────────────────────────────────────────────────
def _write_manifest(run_dir, truncated):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": "success", "retrieval": {
            "corpus_truncated": truncated, "candidates_total": 50,
            "candidates_processed": 12 if truncated else 50,
        }}),
        encoding="utf-8",
    )


def test_scorer_backstop_rejects_truncated(tmp_path):
    from scripts.dr_benchmark.score_run import _check_polaris_gate, InvalidRunError
    run_dir = tmp_path / "run_trunc"
    _write_manifest(run_dir, truncated=True)
    with pytest.raises(InvalidRunError) as exc:
        _check_polaris_gate(run_dir)
    assert "corpus truncated" in str(exc.value).lower()


def test_scorer_backstop_clean_corpus_passes_truncation_check(tmp_path):
    """A non-truncated manifest must NOT trip the truncation backstop; it proceeds to
    the gate-artifact checks (which then fail for the MISSING gate result, a different error)."""
    from scripts.dr_benchmark.score_run import _check_polaris_gate, InvalidRunError
    run_dir = tmp_path / "run_clean"
    _write_manifest(run_dir, truncated=False)
    with pytest.raises(InvalidRunError) as exc:
        _check_polaris_gate(run_dir)
    # the error is about the missing gate result, NOT corpus truncation
    assert "corpus truncated" not in str(exc.value).lower()
