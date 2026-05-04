"""Tests for scripts/seed_demo_benchmark.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import seed_demo_benchmark  # noqa: E402


def test_parse_args_defaults_config_to_clinical_n10():
    args = seed_demo_benchmark.parse_args(["--output", "out/"])
    assert args.output == Path("out/")
    # Default config resolves to repo's clinical_n10.json
    assert args.config.name == "clinical_n10.json"
    assert "benchmark" in args.config.parts


def test_parse_args_accepts_explicit_config():
    args = seed_demo_benchmark.parse_args(
        ["--config", "x.json", "--output", "y/"]
    )
    assert args.config == Path("x.json")
    assert args.output == Path("y/")


def test_parse_args_missing_output_exits():
    with pytest.raises(SystemExit):
        seed_demo_benchmark.parse_args(["--config", "x.json"])


def test_main_missing_config_returns_2(tmp_path: Path):
    rc = seed_demo_benchmark.main(
        [
            "--config", str(tmp_path / "no_such.json"),
            "--output", str(tmp_path / "out"),
        ]
    )
    assert rc == 2


def test_main_seeds_artifact_tree(tmp_path: Path, capsys):
    """End-to-end: seed produces scoreboard + summary + report."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "benchmark_id": "seed_smoke",
                "questions": [
                    {
                        "question_id": "Q01",
                        "question_text": "Is aspirin effective?",
                        "scope_class": "clinical_efficacy",
                        "expected_pico_axes": [
                            "population",
                            "intervention",
                            "outcome",
                        ],
                        "is_refusal_bait": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "seeded"

    rc = seed_demo_benchmark.main(
        ["--config", str(config_path), "--output", str(output_dir)]
    )
    assert rc == 0

    sb = output_dir / "scoreboard.json"
    summary = output_dir / "summary.md"
    report = output_dir / "report.html"
    assert sb.is_file()
    assert summary.is_file()
    assert report.is_file()

    sb_data = json.loads(sb.read_text(encoding="utf-8"))
    assert sb_data["benchmark_id"] == "seed_smoke"

    out = capsys.readouterr().out
    assert "Demo artifact seeded at" in out
    assert "POLARIS_BENCHMARK_RESULTS_DIR" in out


def test_main_creates_output_directory_if_missing(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "benchmark_id": "seed_mkdir",
                "questions": [
                    {
                        "question_id": "Q01",
                        "question_text": "x",
                        "scope_class": "clinical_efficacy",
                        "expected_pico_axes": ["population"],
                        "is_refusal_bait": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    nested = tmp_path / "deep" / "nested" / "path"
    rc = seed_demo_benchmark.main(
        ["--config", str(config_path), "--output", str(nested)]
    )
    assert rc == 0
    assert nested.is_dir()
