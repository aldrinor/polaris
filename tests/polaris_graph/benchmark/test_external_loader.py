"""Tests for external_loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from polaris_graph.benchmark.external_loader import (
    MAX_OUTPUT_BYTES,
    ExternalLoadReport,
    load_external_outputs,
)


# ---------- Happy paths ----------

def test_load_all_expected_files_present(tmp_path: Path):
    (tmp_path / "Q01.txt").write_text("aspirin output", encoding="utf-8")
    (tmp_path / "Q02.txt").write_text("metformin output", encoding="utf-8")
    report = load_external_outputs(
        "chatgpt", tmp_path, ["Q01", "Q02"]
    )
    assert set(report.loaded.keys()) == {"Q01", "Q02"}
    assert report.loaded["Q01"] == "aspirin output"
    assert report.coverage_ratio() == 1.0
    assert report.missing_question_ids == ()


def test_load_partial_coverage(tmp_path: Path):
    (tmp_path / "Q01.txt").write_text("only Q01", encoding="utf-8")
    report = load_external_outputs(
        "chatgpt", tmp_path, ["Q01", "Q02", "Q03"]
    )
    assert "Q01" in report.loaded
    assert "Q02" not in report.loaded
    assert "Q03" not in report.loaded
    assert set(report.missing_question_ids) == {"Q02", "Q03"}
    assert report.coverage_ratio() == pytest.approx(1 / 3)


def test_load_with_unicode_content(tmp_path: Path):
    text = "Métaformine effects in 65+ adults; outcomes ≥ 50% reduction"
    (tmp_path / "Q01.txt").write_text(text, encoding="utf-8")
    report = load_external_outputs("gemini", tmp_path, ["Q01"])
    assert report.loaded["Q01"] == text


# ---------- Missing / non-existent dirs ----------

def test_load_dir_does_not_exist(tmp_path: Path):
    nonexistent = tmp_path / "does_not_exist"
    report = load_external_outputs(
        "chatgpt", nonexistent, ["Q01", "Q02"]
    )
    assert report.loaded == {}
    assert set(report.missing_question_ids) == {"Q01", "Q02"}
    assert report.coverage_ratio() == 0.0


def test_load_dir_is_none(tmp_path: Path):
    report = load_external_outputs("chatgpt", None, ["Q01"])
    assert report.loaded == {}
    assert report.missing_question_ids == ("Q01",)


def test_load_dir_is_a_file_raises(tmp_path: Path):
    afile = tmp_path / "afile.txt"
    afile.write_text("not a dir")
    with pytest.raises(ValueError, match="not a directory"):
        load_external_outputs("chatgpt", afile, ["Q01"])


def test_load_empty_dir(tmp_path: Path):
    report = load_external_outputs(
        "chatgpt", tmp_path, ["Q01", "Q02"]
    )
    assert report.loaded == {}
    assert set(report.missing_question_ids) == {"Q01", "Q02"}


# ---------- Filtering ----------

def test_load_ignores_non_txt_files(tmp_path: Path):
    (tmp_path / "Q01.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "Q02.json").write_text("{}", encoding="utf-8")
    (tmp_path / "Q03.md").write_text("# heading", encoding="utf-8")
    report = load_external_outputs(
        "chatgpt", tmp_path, ["Q01", "Q02", "Q03"]
    )
    assert "Q01" in report.loaded
    assert "Q02" not in report.loaded
    assert "Q03" not in report.loaded
    assert "Q02.json" in report.extra_files
    assert "Q03.md" in report.extra_files


def test_load_ignores_subdirectories(tmp_path: Path):
    (tmp_path / "Q01.txt").write_text("ok", encoding="utf-8")
    subdir = tmp_path / "Q02"
    subdir.mkdir()
    report = load_external_outputs(
        "chatgpt", tmp_path, ["Q01", "Q02"]
    )
    assert "Q01" in report.loaded
    assert "Q02" not in report.loaded


def test_load_records_extras(tmp_path: Path):
    (tmp_path / "Q01.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "extra1.txt").write_text("not expected", encoding="utf-8")
    (tmp_path / "extra2.txt").write_text("also not", encoding="utf-8")
    report = load_external_outputs("chatgpt", tmp_path, ["Q01"])
    assert "Q01" in report.loaded
    assert set(report.extra_files) == {"extra1.txt", "extra2.txt"}


# ---------- Truncation ----------

def test_load_truncates_oversized_file(tmp_path: Path):
    big = "x" * (MAX_OUTPUT_BYTES + 1000)
    (tmp_path / "Q01.txt").write_text(big, encoding="utf-8")
    report = load_external_outputs("chatgpt", tmp_path, ["Q01"])
    assert "Q01" in report.loaded
    assert len(report.loaded["Q01"].encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert "Q01" in report.truncated_question_ids


def test_load_does_not_truncate_under_cap(tmp_path: Path):
    text = "x" * 1000
    (tmp_path / "Q01.txt").write_text(text, encoding="utf-8")
    report = load_external_outputs("chatgpt", tmp_path, ["Q01"])
    assert report.loaded["Q01"] == text
    assert report.truncated_question_ids == ()


# ---------- Error tolerance ----------

def test_load_invalid_utf8_falls_back_to_replace(tmp_path: Path):
    """Latin-1 / mixed-encoding files don't crash — bytes get replaced."""
    invalid_bytes = b"valid then \xff\xfe invalid"
    (tmp_path / "Q01.txt").write_bytes(invalid_bytes)
    report = load_external_outputs("chatgpt", tmp_path, ["Q01"])
    assert "Q01" in report.loaded
    # Decoded with errors='replace' so we get a replacement char (U+FFFD)
    # for the invalid bytes, but the rest survives
    assert "valid then" in report.loaded["Q01"]


# ---------- ExternalLoadReport helpers ----------

def test_coverage_ratio_full():
    report = ExternalLoadReport(
        system_name="x",
        output_dir=Path("/tmp"),
        expected_question_ids=("Q1", "Q2"),
        loaded={"Q1": "a", "Q2": "b"},
        missing_question_ids=(),
        extra_files=(),
        truncated_question_ids=(),
    )
    assert report.coverage_ratio() == 1.0


def test_coverage_ratio_zero_when_no_expected():
    report = ExternalLoadReport(
        system_name="x",
        output_dir=Path("/tmp"),
        expected_question_ids=(),
        loaded={},
        missing_question_ids=(),
        extra_files=(),
        truncated_question_ids=(),
    )
    # Vacuously full coverage when no questions expected
    assert report.coverage_ratio() == 1.0


def test_coverage_ratio_partial():
    report = ExternalLoadReport(
        system_name="x",
        output_dir=Path("/tmp"),
        expected_question_ids=("Q1", "Q2", "Q3", "Q4"),
        loaded={"Q1": "a", "Q3": "c"},
        missing_question_ids=("Q2", "Q4"),
        extra_files=(),
        truncated_question_ids=(),
    )
    assert report.coverage_ratio() == 0.5
