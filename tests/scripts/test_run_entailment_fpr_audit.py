"""Tests for I-bug-101 — entailment FPR audit harness.

The audit script is dry-run by default (no LLM call). Tests cover:
- smoke fixture loads and produces stub manifest
- JSONL golden file loads correctly
- malformed JSONL raises clear ValueError
- output path is created
- live mode flag is plumbed (does not actually exercise the live path
  without an API key — that is a manual / integration concern)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_entailment_fpr_audit import (  # noqa: E402
    SMOKE_FIXTURE,
    _load_pairs,
    run_fpr_audit,
)


def test_smoke_fixture_has_pairs():
    assert len(SMOKE_FIXTURE) >= 5
    for pair in SMOKE_FIXTURE:
        assert "sentence" in pair
        assert "span" in pair
        assert pair["sentence"]
        assert pair["span"]


def test_load_pairs_from_smoke():
    pairs = _load_pairs(golden_path=None, smoke=True)
    assert pairs == SMOKE_FIXTURE


def test_load_pairs_from_golden_jsonl(tmp_path: Path):
    golden = tmp_path / "pairs.jsonl"
    rows = [
        {"sentence": "S1", "span": "P1"},
        {"sentence": "S2", "span": "P2"},
    ]
    golden.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    loaded = _load_pairs(golden_path=golden, smoke=False)
    assert loaded == rows


def test_load_pairs_rejects_malformed_row(tmp_path: Path):
    golden = tmp_path / "pairs.jsonl"
    # Missing 'span' field
    golden.write_text(
        json.dumps({"sentence": "S1"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed pair"):
        _load_pairs(golden_path=golden, smoke=False)


def test_load_pairs_requires_golden_or_smoke():
    with pytest.raises(ValueError, match="--smoke or --golden"):
        _load_pairs(golden_path=None, smoke=False)


def test_dry_run_writes_stub_manifest(tmp_path: Path):
    output = tmp_path / "out/dist.json"
    pairs = [{"sentence": "S", "span": "P"}]
    result = run_fpr_audit(pairs, output, live=False)

    assert result["live"] is False
    assert result["n_pairs"] == 1
    assert "stub_reason" in result
    assert output.exists()
    on_disk = json.loads(output.read_text())
    assert on_disk == result


def test_dry_run_includes_pairs_preview(tmp_path: Path):
    """The dry-run manifest exposes the first 3 pairs for verification."""
    pairs = [{"sentence": f"S{i}", "span": f"P{i}"} for i in range(10)]
    result = run_fpr_audit(pairs, tmp_path / "out.json", live=False)
    assert len(result["pairs_preview"]) == 3
    assert result["pairs_preview"][0] == pairs[0]


def test_run_fpr_audit_creates_output_dir(tmp_path: Path):
    """Output dir is auto-created."""
    output = tmp_path / "deep/nested/path/dist.json"
    assert not output.parent.exists()
    run_fpr_audit([{"sentence": "S", "span": "P"}], output, live=False)
    assert output.parent.exists()
    assert output.exists()
