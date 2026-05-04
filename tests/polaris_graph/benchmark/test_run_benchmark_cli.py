"""Tests for scripts/run_benchmark.py CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable as a module
SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_benchmark  # noqa: E402


def _write_test_config(path: Path) -> None:
    config_data = {
        "benchmark_id": "test_cli_run",
        "questions": [
            {
                "question_id": "Q01",
                "question_text": "Is aspirin effective for headache?",
                "scope_class": "clinical_efficacy",
                "expected_pico_axes": ["population", "intervention", "outcome"],
                "is_refusal_bait": False,
            }
        ],
    }
    path.write_text(json.dumps(config_data), encoding="utf-8")


def test_cli_parses_required_args(tmp_path: Path):
    args = run_benchmark.parse_args(
        [
            "--config", "x.json",
            "--output", "out/",
        ]
    )
    assert args.config == Path("x.json")
    assert args.output == Path("out/")
    assert args.polaris_url == "http://127.0.0.1:8000"  # default


def test_cli_parses_all_args():
    args = run_benchmark.parse_args(
        [
            "--config", "config.json",
            "--polaris-url", "http://localhost:9000",
            "--chatgpt-dir", "external/cg/",
            "--gemini-dir", "external/gm/",
            "--output", "results/",
            "--skip-polaris",
            "-v",
        ]
    )
    assert args.polaris_url == "http://localhost:9000"
    assert args.chatgpt_dir == Path("external/cg/")
    assert args.gemini_dir == Path("external/gm/")
    assert args.skip_polaris is True
    assert args.verbose == 1


def test_cli_verbose_flag_stacks():
    args = run_benchmark.parse_args(
        ["--config", "x", "--output", "y", "-vv"]
    )
    assert args.verbose == 2


def test_cli_missing_required_args_exits():
    with pytest.raises(SystemExit):
        run_benchmark.parse_args(["--config", "x.json"])
    with pytest.raises(SystemExit):
        run_benchmark.parse_args(["--output", "out/"])


def test_cli_main_skip_polaris_writes_outputs(tmp_path: Path, capsys):
    """Skip-polaris path should still produce scoreboard.json + summary.md + html."""
    config_path = tmp_path / "config.json"
    _write_test_config(config_path)
    output_dir = tmp_path / "results"

    rc = run_benchmark.main(
        [
            "--config", str(config_path),
            "--output", str(output_dir),
            "--skip-polaris",
        ]
    )
    assert rc == 0
    assert (output_dir / "scoreboard.json").exists()
    assert (output_dir / "summary.md").exists()
    assert (output_dir / "report.html").exists()

    # Final stdout should contain win counts
    captured = capsys.readouterr()
    assert "BEAT-BOTH benchmark complete" in captured.out
    assert "Questions: 1" in captured.out


def test_cli_main_with_external_outputs(tmp_path: Path):
    config_path = tmp_path / "config.json"
    _write_test_config(config_path)
    chatgpt_dir = tmp_path / "chatgpt"
    chatgpt_dir.mkdir()
    (chatgpt_dir / "Q01.txt").write_text(
        "Adults benefited from aspirin per https://nejm.org/study with intervention outcome.",
        encoding="utf-8",
    )
    gemini_dir = tmp_path / "gemini"
    gemini_dir.mkdir()
    output_dir = tmp_path / "results"

    rc = run_benchmark.main(
        [
            "--config", str(config_path),
            "--chatgpt-dir", str(chatgpt_dir),
            "--gemini-dir", str(gemini_dir),
            "--output", str(output_dir),
            "--skip-polaris",
        ]
    )
    assert rc == 0
    sb_data = json.loads((output_dir / "scoreboard.json").read_text(encoding="utf-8"))
    assert sb_data["benchmark_id"] == "test_cli_run"
    assert sb_data["aggregate"]["n_questions"] == 1


def test_cli_main_missing_config_exits_with_error(tmp_path: Path):
    output_dir = tmp_path / "results"
    with pytest.raises((FileNotFoundError, SystemExit)):
        run_benchmark.main(
            [
                "--config", str(tmp_path / "nonexistent.json"),
                "--output", str(output_dir),
                "--skip-polaris",
            ]
        )
