"""Tests for I-bug-107 — multi-run BEAT-BOTH aggregator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.aggregate_beat_both_runs import (  # noqa: E402
    _aggregate_polaris_scores,
    _compute_robust_verdicts,
    aggregate,
)


def _make_fake_manifest(polaris_value: float, dim: str = "narrative_length") -> dict:
    """Synthetic single-run BEAT-BOTH manifest matching real schema."""
    return {
        "polaris_scores": {
            dim: {"value": polaris_value, "higher_is_better": True, "rationale": "test"},
        },
        "chatgpt_scores": {
            dim: {"value": 100.0, "higher_is_better": True, "rationale": "baseline"},
        },
        "gemini_scores": {
            dim: {"value": 90.0, "higher_is_better": True, "rationale": "baseline"},
        },
    }


def _write(tmp: Path, name: str, manifest: dict) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def test_aggregate_computes_mean_and_stddev(tmp_path: Path):
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(50.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(60.0)),
        _write(tmp_path, "r3/manifest.json", _make_fake_manifest(70.0)),
    ]
    out = tmp_path / "agg/manifest.json"
    result = aggregate(paths, out)

    agg = result["polaris_scores_aggregate"]["narrative_length"]
    assert agg["mean"] == pytest.approx(60.0)
    assert agg["stddev"] == pytest.approx(10.0)
    assert agg["min"] == 50.0
    assert agg["max"] == 70.0
    assert agg["n"] == 3


def test_aggregate_writes_output_file(tmp_path: Path):
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(50.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(60.0)),
    ]
    out = tmp_path / "agg/manifest.json"
    aggregate(paths, out)
    assert out.exists()
    written = json.loads(out.read_text())
    assert written["n_runs"] == 2


def test_aggregate_requires_at_least_two_manifests(tmp_path: Path):
    paths = [_write(tmp_path, "r1/manifest.json", _make_fake_manifest(50.0))]
    with pytest.raises(ValueError, match="Need >=2"):
        aggregate(paths, tmp_path / "agg.json")


def test_robust_verdict_when_worst_case_beats_both(tmp_path: Path):
    """If (mean - stddev) > both competitor scores, verdict is robust.

    Uses canonical narrative_length tolerance (100.0). Values chosen so
    polaris_mean comfortably exceeds tolerance over both competitors.
    """
    # POLARIS: mean=400, stddev=10 → worst_case=390. Competitors 100/90.
    # 400 > 100+100=200 ✓, 400 > 90+100=190 ✓ → BEAT-BOTH.
    # 390 > 100 ✓, 390 > 90 ✓ → robust=True (strict).
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(390.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(400.0)),
        _write(tmp_path, "r3/manifest.json", _make_fake_manifest(410.0)),
    ]
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    assert verdict["verdict"] == "BEAT-BOTH"
    assert verdict["robust"] is True


def test_non_robust_verdict_when_high_variance(tmp_path: Path):
    """If (mean - stddev) does NOT beat both, robust=False even if mean does.

    Under canonical narrative_length tolerance (100.0), polaris_mean must
    exceed (chatgpt + 100) and (gemini + 100) for BEAT-BOTH. Use values
    where mean meets the tolerance bar but worst_case (mean - stddev)
    ties or undercuts a competitor.
    """
    # POLARIS: mean=210, stddev=120 → worst_case=90. ChatGPT 100, Gemini 90.
    # 210 > 100+100=200 ✓ (just), 210 > 90+100=190 ✓ → BEAT-BOTH.
    # worst_case=90 NOT > chatgpt(100) → robust=False.
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(90.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(210.0)),
        _write(tmp_path, "r3/manifest.json", _make_fake_manifest(330.0)),
    ]
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    assert verdict["verdict"] == "BEAT-BOTH"  # mean (210) > comps + tolerance
    assert verdict["robust"] is False  # but worst_case (90) does not beat chatgpt (100)


def test_canonical_tolerance_used_not_hand_rolled(tmp_path: Path):
    """I-bug-107 iter-1 diff P1 fix: tolerance is `tolerance_for(dim)`,
    not a 1% hand-rolled rule. narrative_length tolerance is 100.0.

    Codex example: narrative_length 1055 vs ChatGPT 1000 / Gemini 900.
    Under 1% rule (~10 word tolerance): BEAT-BOTH.
    Under canonical 100-word tolerance: TIE with ChatGPT (only beats Gemini).
    Verdict should be BEAT-ONE (beats Gemini, ties ChatGPT).
    """
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(1050.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(1060.0)),
    ]
    for p in paths:
        m = json.loads(p.read_text())
        m["chatgpt_scores"]["narrative_length"]["value"] = 1000.0
        m["gemini_scores"]["narrative_length"]["value"] = 900.0
        p.write_text(json.dumps(m))
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    # mean=1055 vs chatgpt=1000 (delta=55, < 100 tol → ties); vs gemini=900 (delta=155, > 100 → beats)
    assert verdict["verdict"] == "BEAT-ONE", (
        f"canonical tolerance must classify near-margin BEAT-ONE, got {verdict}"
    )


def test_ahead_one_behind_one_classifies_as_behind(tmp_path: Path):
    """I-bug-107 iter-2 diff P1 fix: ahead-one/behind-one resolves to
    BEHIND per canonical M-LIVE-2 taxonomy (run_m_live_2_beat_both.py:541),
    NOT BEAT-ONE.

    Codex example: narrative_length POLARIS=1200, ChatGPT=1000, Gemini=2000,
    tol=100 → ahead of ChatGPT (delta=200>100), behind Gemini (delta=-800).
    Canonical verdict: BEHIND.
    """
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(1190.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(1210.0)),
    ]
    for p in paths:
        m = json.loads(p.read_text())
        m["chatgpt_scores"]["narrative_length"]["value"] = 1000.0
        m["gemini_scores"]["narrative_length"]["value"] = 2000.0
        p.write_text(json.dumps(m))
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    assert verdict["verdict"] == "BEHIND", (
        f"ahead-one/behind-one MUST be BEHIND per canonical, got {verdict}"
    )


def test_behind_both_distinct_from_behind(tmp_path: Path):
    """Canonical taxonomy distinguishes BEHIND-BOTH (behind both
    competitors) from BEHIND (behind at least one). Aggregator must
    preserve the distinction.
    """
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(50.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(60.0)),
    ]
    for p in paths:
        m = json.loads(p.read_text())
        m["chatgpt_scores"]["narrative_length"]["value"] = 1000.0
        m["gemini_scores"]["narrative_length"]["value"] = 2000.0
        p.write_text(json.dumps(m))
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    assert verdict["verdict"] == "BEHIND-BOTH"


def test_all_zero_dimension_returns_na_not_tie(tmp_path: Path):
    """I-bug-107 iter-1 diff P2 fix: when all 3 manifests scored 0.0,
    verdict is N/A (not TIE) — matches canonical M-LIVE-2 logic at
    scripts/run_m_live_2_beat_both.py:492-494.
    """
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(0.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(0.0)),
    ]
    for p in paths:
        m = json.loads(p.read_text())
        m["chatgpt_scores"]["narrative_length"]["value"] = 0.0
        m["gemini_scores"]["narrative_length"]["value"] = 0.0
        p.write_text(json.dumps(m))
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    assert verdict["verdict"] == "N/A"
    assert verdict["robust"] is False


def test_summary_flags_high_variance_dimensions(tmp_path: Path):
    """Dimensions with stddev > 10% of mean are flagged as high-variance."""
    # mean=60, stddev=10 → 16.7% — flagged
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(50.0)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(60.0)),
        _write(tmp_path, "r3/manifest.json", _make_fake_manifest(70.0)),
    ]
    result = aggregate(paths, tmp_path / "agg.json")
    assert "narrative_length" in result["summary"]["high_variance_dimensions"]


def test_robust_strict_inequality_no_tolerance(tmp_path: Path):
    """I-bug-107 iter-1 P1 fix: robust uses STRICT (worst_case > both),
    NOT tolerance-based comparison. Codex flagged: mean=101, stddev=0.5,
    competitors=100/99 → worst_case=100.5 > both → robust=True.
    """
    # Need 2+ runs to compute stddev; pick values with mean=101, stddev=~0.5
    # 100.5, 101.5 → mean=101, stddev=0.7071...
    paths = [
        _write(tmp_path, "r1/manifest.json", _make_fake_manifest(100.5)),
        _write(tmp_path, "r2/manifest.json", _make_fake_manifest(101.5)),
    ]
    # Override competitor scores: chatgpt=100, gemini=99
    for p in paths:
        m = json.loads(p.read_text())
        m["chatgpt_scores"]["narrative_length"]["value"] = 100.0
        m["gemini_scores"]["narrative_length"]["value"] = 99.0
        p.write_text(json.dumps(m))

    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    # mean=101, stddev~0.71 → worst_case~100.29 > 100 → True; > 99 → True
    assert verdict["robust"] is True, (
        f"strict-inequality robust: worst_case={verdict['polaris_worst_case']} "
        f"vs chatgpt=100, gemini=99 → must be True"
    )


def test_incomplete_verdict_when_competitor_dimension_missing(tmp_path: Path):
    """I-bug-107 iter-1 P2 fix: if a competitor manifest is missing a
    dimension, verdict is INCOMPLETE — NOT silently fabricated as 0.0.
    """
    m = _make_fake_manifest(50.0, dim="narrative_length")
    # Remove dim from chatgpt scores entirely
    del m["chatgpt_scores"]["narrative_length"]
    paths = [
        _write(tmp_path, "r1/manifest.json", m),
        _write(tmp_path, "r2/manifest.json", m),
    ]
    result = aggregate(paths, tmp_path / "agg.json")
    verdict = result["per_dimension_verdicts"]["narrative_length"]
    assert verdict["verdict"] == "INCOMPLETE"
    assert verdict["robust"] is False
    assert verdict["chatgpt"] is None
    assert "reason" in verdict


def test_aggregate_handles_missing_dimension_gracefully(tmp_path: Path):
    """If one run is missing a dimension, the aggregate uses only the runs that have it."""
    m1 = _make_fake_manifest(50.0, dim="narrative_length")
    m2 = _make_fake_manifest(60.0, dim="narrative_length")
    # m3 has different dimension
    m3 = _make_fake_manifest(100.0, dim="other_dim")
    m3["chatgpt_scores"] = {"other_dim": {"value": 200.0, "higher_is_better": True, "rationale": "x"}}
    m3["gemini_scores"] = {"other_dim": {"value": 180.0, "higher_is_better": True, "rationale": "x"}}
    paths = [
        _write(tmp_path, "r1/manifest.json", m1),
        _write(tmp_path, "r2/manifest.json", m2),
        _write(tmp_path, "r3/manifest.json", m3),
    ]
    result = aggregate(paths, tmp_path / "agg.json")
    # narrative_length seen in 2 runs
    assert result["polaris_scores_aggregate"]["narrative_length"]["n"] == 2
    # other_dim seen in 1 run — has 1 value, stddev=0 (single sample)
    assert result["polaris_scores_aggregate"]["other_dim"]["n"] == 1
    assert result["polaris_scores_aggregate"]["other_dim"]["stddev"] == 0.0
