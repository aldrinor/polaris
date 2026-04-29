"""M-INT-6 — LLMAugmentedInductor in operator-review queue.

Acceptance bar:
  1. Imported (LLMAugmentedInductor, InductorVerdict, KeywordInductor,
     MockTemplateAffinityClassifier)
  2. Invoked (`_induce_with_llm` from sweep)
  3. Run-log evidence (`[M-INT-6] inductor:` line + abstain →
     operator_review_queue.jsonl)
  4. PG_USE_AUTO_INDUCTION=0 disables (default 0)
  5. Precision metric on M-D1 set logged on demand
  6. M-D1 validation set still runs as a CI test (existing
     test_md1_auto_induction_harness.py)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_sweep_imports_inductor_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "LLMAugmentedInductor")
    assert hasattr(sweep, "LLMAugmentedInductorConfig")
    assert hasattr(sweep, "InductorVerdict")
    assert hasattr(sweep, "KeywordInductor")
    assert hasattr(sweep, "MockTemplateAffinityClassifier")
    assert hasattr(sweep, "_induce_with_llm")
    assert hasattr(sweep, "_build_inductor")
    assert hasattr(sweep, "_record_operator_review_item")


def test_induce_returns_verdict_with_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_AUTO_INDUCTION", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    summary = sweep._induce_with_llm(
        query="What is the cardiovascular efficacy of tirzepatide for T2DM?",
        run_dir=tmp_path,
    )
    assert summary is not None
    assert "decision" in summary
    assert summary["decision"] in {"accept", "abstain"}
    assert "confidence" in summary
    assert 0.0 <= summary["confidence"] <= 1.0


def test_disabled_flag_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_AUTO_INDUCTION", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._induce_with_llm(
        query="Some query",
        run_dir=tmp_path,
    )
    assert summary is None


def test_empty_query_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_AUTO_INDUCTION", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._induce_with_llm(
        query="",
        run_dir=tmp_path,
    )
    assert summary is None


def test_abstain_records_operator_review_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per FINAL_PLAN M-INT-6: abstain verdicts must surface
    in the operator-review queue (operator_review_queue.jsonl)."""
    monkeypatch.setenv("PG_USE_AUTO_INDUCTION", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    # Stub _build_inductor to return a known-abstaining inductor.
    from src.polaris_graph.auto_induction.precision_metrics import (
        InductorVerdict,
    )

    class _AbstainInductor:
        def induce(self, query):
            return InductorVerdict(
                decision="abstain",
                confidence=0.3,
                abstain_reason="stub: low confidence",
            )

    monkeypatch.setattr(sweep, "_build_inductor", lambda: _AbstainInductor())

    summary = sweep._induce_with_llm(
        query="Out-of-scope query for inductor stub test",
        run_dir=tmp_path,
    )
    assert summary is not None
    assert summary["decision"] == "abstain"

    # Operator-review queue file should have one entry.
    queue_file = tmp_path / "operator_review_queue.jsonl"
    assert queue_file.exists()
    lines = queue_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    item = json.loads(lines[0])
    assert item["query"] == "Out-of-scope query for inductor stub test"
    assert item["decision"] == "abstain"
    assert item["abstain_reason"] == "stub: low confidence"


def test_accept_does_not_record_operator_review_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept verdicts skip the queue."""
    monkeypatch.setenv("PG_USE_AUTO_INDUCTION", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    from src.polaris_graph.auto_induction.precision_metrics import (
        InductorVerdict,
    )

    # A test-shaped contract object — match_score from any
    # inductor accept path; we just need the InductorVerdict
    # contract validation to pass.
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _StubContract:
        slug: str = "test_slug"

    class _AcceptInductor:
        def induce(self, query):
            return InductorVerdict(
                decision="accept",
                induced_contract=_StubContract(),
                confidence=0.9,
            )

    monkeypatch.setattr(sweep, "_build_inductor", lambda: _AcceptInductor())

    summary = sweep._induce_with_llm(
        query="Accept-path query",
        run_dir=tmp_path,
    )
    assert summary["decision"] == "accept"
    queue_file = tmp_path / "operator_review_queue.jsonl"
    assert not queue_file.exists()


def test_inductor_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II — induction failure must not gate sweep."""
    monkeypatch.setenv("PG_USE_AUTO_INDUCTION", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    class _BrokenInductor:
        def induce(self, query):
            raise RuntimeError("simulated inductor crash")

    monkeypatch.setattr(sweep, "_build_inductor", lambda: _BrokenInductor())

    summary = sweep._induce_with_llm(
        query="Test", run_dir=tmp_path,
    )
    # Returns None on internal failure — does not raise.
    assert summary is None
