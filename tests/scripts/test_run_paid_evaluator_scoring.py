"""Tests for I-bench-002 — paid evaluator scoring harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_paid_evaluator_scoring import (  # noqa: E402
    RUBRIC_VERDICTS,
    build_evaluator_prompt,
    run_paid_evaluator,
    score_claim_dry_run,
)


def test_rubric_verdicts_match_clauseM_audit():
    """The 5 verdicts must match the line-by-line audit rubric per
    CLAUDE.md §-1.1.
    """
    assert set(RUBRIC_VERDICTS) == {
        "VERIFIED", "PARTIAL", "UNSUPPORTED", "FABRICATED", "UNREACHABLE",
    }


def test_evaluator_prompt_includes_framework_and_rubric():
    p = build_evaluator_prompt(
        sentence="Drug A reduced X by 1.5%",
        span="Drug A reduced X by 1.5% in adults",
        framework="GRADE",
    )
    assert "GRADE" in p
    for v in RUBRIC_VERDICTS:
        assert v in p
    assert "Drug A reduced X by 1.5%" in p
    assert "STRICT JSON" in p


def test_evaluator_prompt_supports_prisma_amstar():
    p1 = build_evaluator_prompt("S", "P", framework="PRISMA 2020")
    assert "PRISMA 2020" in p1
    p2 = build_evaluator_prompt("S", "P", framework="AMSTAR-2")
    assert "AMSTAR-2" in p2


def test_dry_run_emits_pending_placeholder():
    r = score_claim_dry_run("S", "P")
    assert r["verdict"] == "PENDING"
    assert "dry-run" in r["rationale"]


def test_run_paid_evaluator_dry_run_aggregates(tmp_path: Path):
    pairs = [
        {"sentence": "S1", "span": "P1"},
        {"sentence": "S2", "span": "P2"},
    ]
    result = run_paid_evaluator(pairs, tmp_path / "out.json", live=False)
    assert result["live"] is False
    assert result["n_claims"] == 2
    assert result["verdict_counts"]["PENDING"] == 2
    assert result["verified_rate"] is None  # only set on live runs


def test_run_paid_evaluator_live_requires_creds(tmp_path: Path):
    with pytest.raises(ValueError, match="live=True requires"):
        run_paid_evaluator(
            [{"sentence": "S", "span": "P"}],
            tmp_path / "out.json",
            live=True,
            # missing endpoint, api_key, model
        )


def test_run_paid_evaluator_skips_empty_sentences(tmp_path: Path):
    pairs = [
        {"sentence": "", "span": "P1"},
        {"sentence": "S2", "span": "P2"},
    ]
    result = run_paid_evaluator(pairs, tmp_path / "out.json", live=False)
    assert result["n_claims"] == 1


def test_output_manifest_persists_to_disk(tmp_path: Path):
    out = tmp_path / "deep/dir/scoring.json"
    pairs = [{"sentence": "S", "span": "P"}]
    run_paid_evaluator(pairs, out, live=False)
    assert out.exists()
    written = json.loads(out.read_text())
    assert written["milestone"] == "I-bench-002"


def test_load_from_verified_sentences_jsonl(tmp_path: Path):
    """JSONL extraction respects canonical {sentence_text} schema."""
    from scripts.run_paid_evaluator_scoring import (
        _load_sentences_with_spans_from_jsonl,
    )

    span = "Drug A reduced X by 1.5%"
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(
        json.dumps([{"evidence_id": "a", "direct_quote": span}]),
        encoding="utf-8",
    )
    verified_path = tmp_path / "verified.jsonl"
    verified_path.write_text(
        json.dumps({"sentence_text": f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]."}) + "\n",
        encoding="utf-8",
    )
    pairs = _load_sentences_with_spans_from_jsonl(verified_path, pool_path)
    assert len(pairs) == 1
    assert "1.5%" in pairs[0]["sentence"]
    assert pairs[0]["span"] == span
    assert pairs[0]["broken_pointers"] == ""


def test_load_preserves_unreachable_for_unknown_source(tmp_path: Path):
    """I-bench-002 iter-1 P1 fix: broken pointer state preserved
    so downstream UNREACHABLE verdict can fire."""
    from scripts.run_paid_evaluator_scoring import (
        _load_sentences_with_spans_from_jsonl,
    )

    pool_path = tmp_path / "pool.json"
    pool_path.write_text("[]", encoding="utf-8")  # empty pool
    verified_path = tmp_path / "verified.jsonl"
    verified_path.write_text(
        json.dumps({"sentence_text": "Claim [#ev:missing:0-10]."}) + "\n",
        encoding="utf-8",
    )
    pairs = _load_sentences_with_spans_from_jsonl(verified_path, pool_path)
    assert len(pairs) == 1
    assert pairs[0]["span"] == ""
    assert "unknown:missing" in pairs[0]["broken_pointers"]


def test_load_preserves_unreachable_for_oob_span(tmp_path: Path):
    from scripts.run_paid_evaluator_scoring import (
        _load_sentences_with_spans_from_jsonl,
    )

    pool_path = tmp_path / "pool.json"
    pool_path.write_text(
        json.dumps([{"evidence_id": "a", "direct_quote": "short"}]),
        encoding="utf-8",
    )
    verified_path = tmp_path / "verified.jsonl"
    verified_path.write_text(
        json.dumps({"sentence_text": "Claim [#ev:a:0-9999]."}) + "\n",
        encoding="utf-8",
    )
    pairs = _load_sentences_with_spans_from_jsonl(verified_path, pool_path)
    assert "oob:a:0-9999" in pairs[0]["broken_pointers"]


def test_broken_pointer_forces_unreachable_in_per_claim(tmp_path: Path):
    """I-bench-002 iter-1 diff P1 fix: broken pointers propagate into
    per_claim as UNREACHABLE verdict, NOT silently dropped + scored.
    """
    pairs = [
        {
            "sentence": "Mixed claim",
            "span": "valid span",
            "broken_pointers": "unknown:missing_id",
        },
        {
            "sentence": "Clean claim",
            "span": "clean span",
            "broken_pointers": "",
        },
    ]
    result = run_paid_evaluator(pairs, tmp_path / "out.json", live=False)
    assert result["per_claim"][0]["verdict"] == "UNREACHABLE"
    assert "unknown:missing_id" in result["per_claim"][0]["rationale"]
    assert result["per_claim"][1]["verdict"] == "PENDING"  # dry-run
    assert result["verdict_counts"]["UNREACHABLE"] == 1


def test_framework_propagates_to_manifest(tmp_path: Path):
    pairs = [{"sentence": "S", "span": "P"}]
    result = run_paid_evaluator(
        pairs, tmp_path / "o.json", live=False, framework="PRISMA 2020",
    )
    assert result["framework"] == "PRISMA 2020"
